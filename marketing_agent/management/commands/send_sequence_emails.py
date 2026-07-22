"""
Django management command to send email sequence emails based on delays.

This command should be run periodically (e.g., every 5 minutes via Celery Beat) to:
1. Check for contacts that need the next step in their sequence
2. Calculate if the delay time has passed since the previous email
3. Send the next email in the sequence
4. Stop if contact replied or sequence completed

Usage:
    python manage.py send_sequence_emails
    python manage.py send_sequence_emails --dry-run
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q, F
from datetime import timedelta, datetime
from marketing_agent.models import (
    Campaign, EmailSequence, EmailSequenceStep, EmailSendHistory,
    Lead, CampaignContact, Reply, ReplySubSequenceRun
)
from marketing_agent.services.email_service import email_service
import logging
import os
import tempfile
import time

logger = logging.getLogger(__name__)

# Single-run lock file. This command is scheduled every ~5 min; if a slow SMTP
# send makes one run overlap the next (or a manual run overlaps the scheduled one),
# two runs process the same contact before sub_sequence_step is updated and send
# the SAME email twice (observed: identical sends at the same timestamp). The lock
# lets only one instance run at a time; a second instance exits immediately.
_LOCK_PATH = os.path.join(tempfile.gettempdir(), 'ppp_send_sequence_emails.lock')
# If a run crashes without releasing the lock, treat a lock older than this as
# stale so the command can't get wedged forever.
_LOCK_STALE_SECONDS = 30 * 60


class Command(BaseCommand):
    help = 'Automatically send email sequence emails based on delay timing and contact state'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without actually sending emails',
        )

    def _acquire_lock(self):
        """Atomically create the lock file. Returns True if we got the lock.
        Clears a stale lock (from a crashed run) first."""
        try:
            if os.path.exists(_LOCK_PATH):
                age = time.time() - os.path.getmtime(_LOCK_PATH)
                if age > _LOCK_STALE_SECONDS:
                    os.remove(_LOCK_PATH)
                    logger.warning('send_sequence_emails: removed stale lock (age %.0fs)', age)
            # O_CREAT | O_EXCL fails if the file already exists — atomic guard.
            fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            return False
        except Exception as e:
            # If locking itself breaks, don't block sending — just log it.
            logger.warning('send_sequence_emails: lock error (%s); proceeding without lock', e)
            return True

    def _release_lock(self):
        try:
            if os.path.exists(_LOCK_PATH):
                os.remove(_LOCK_PATH)
        except Exception:
            pass

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY RUN] No emails will be sent'))

        # Prevent overlapping runs from double-sending. A second concurrent run
        # exits here instead of re-processing the same contacts.
        if not self._acquire_lock():
            self.stdout.write(self.style.WARNING(
                'send_sequence_emails already running (lock held) — skipping this run.'
            ))
            return

        try:
            self._run(dry_run)
        finally:
            self._release_lock()

    def _run(self, dry_run):
        campaigns = Campaign.objects.filter(status='active')
        campaign_count = campaigns.count()

        if campaign_count == 0:
            return

        total_sent = 0
        total_checked = 0
        total_skipped = 0
        total_stopped = 0

        for campaign in campaigns:
            # Get active main sequences (not sub-sequences)
            sequences = campaign.email_sequences.filter(is_active=True, is_sub_sequence=False)

            # Ensure every lead has a CampaignContact per active MAIN sequence
            leads = list(campaign.leads.all())
            for seq in sequences:
                for lead in leads:
                    CampaignContact.objects.get_or_create(
                        campaign=campaign,
                        lead=lead,
                        sequence=seq,
                        defaults={'current_step': 0},
                    )

            # Clean up: delete contacts in sub-sequences that haven't replied (bug fix)
            sub_sequences_with_contacts = EmailSequence.objects.filter(
                campaign=campaign, is_sub_sequence=True, is_active=True
            )
            for sub_seq in sub_sequences_with_contacts:
                CampaignContact.objects.filter(
                    campaign=campaign, sequence=sub_seq, replied=False
                ).delete()

            sequence_count = sequences.count()
            if sequence_count == 0:
                continue

            # Reactivate contacts that were marked completed but have more steps now
            for seq in sequences:
                total_steps = seq.steps.count()
                reactivated = CampaignContact.objects.filter(
                    campaign=campaign, sequence=seq,
                    completed=True, current_step__lt=total_steps,
                ).update(completed=False, completed_at=None)
                if reactivated:
                    self.stdout.write(self.style.SUCCESS(
                        f'  Reactivated {reactivated} contact(s) for "{seq.name}" ({total_steps} steps now)'
                    ))

            # Get main sequence contacts
            all_contacts = CampaignContact.objects.filter(
                campaign=campaign, sequence__is_active=True,
                sequence__isnull=False, sequence__is_sub_sequence=False
            )

            main_contacts = all_contacts.filter(
                completed=False, replied=False
            ).select_related('lead', 'sequence').prefetch_related('sequence__steps')

            # Per-reply sub-sequence runs (the new model). Each reply that matched
            # a sub-sequence has its own run row, so a lead's different replies run
            # their sub-sequences in parallel. Assignment already happened in
            # reply_processor when the reply came in — the sender just advances runs.
            reply_runs = ReplySubSequenceRun.objects.filter(
                campaign=campaign, completed=False, cancelled=False,
            ).select_related('lead', 'sub_sequence', 'reply', 'contact').prefetch_related('sub_sequence__steps')

            # Process main sequence contacts
            for contact in main_contacts:
                total_checked += 1
                result = self._process_main_sequence_contact(contact, campaign, sequences, dry_run)
                if result == 'sent':
                    total_sent += 1
                elif result == 'skipped':
                    total_skipped += 1
                elif result == 'stopped':
                    total_stopped += 1

            # Process per-reply sub-sequence runs
            for run in reply_runs:
                total_checked += 1
                result = self._process_reply_run(run, campaign, dry_run)
                if result == 'sent':
                    total_sent += 1
                elif result == 'skipped':
                    total_skipped += 1
                elif result == 'stopped':
                    total_stopped += 1

        # Only print summary if something happened
        if total_sent > 0 or total_stopped > 0:
            self.stdout.write(self.style.SUCCESS(
                f'[Email Sequences] Sent: {total_sent} | Completed: {total_stopped} | Checked: {total_checked}'
            ))

    def _process_reply_run(self, run, campaign, dry_run):
        """Send the next step of ONE per-reply sub-sequence run.

        Mirrors the old per-contact sender but drives entirely off the run row
        (run.step / run.last_sent_at) and the reply's timestamp — so multiple runs
        for the same lead advance independently. Returns 'sent'/'skipped'/'stopped'.
        """
        lead = run.lead
        sub_sequence = run.sub_sequence

        if not sub_sequence or not sub_sequence.is_active:
            run.cancelled = True
            run.save(update_fields=['cancelled', 'updated_at'])
            return 'skipped'

        steps = sub_sequence.steps.all().order_by('step_order')
        step_count = steps.count()
        if step_count == 0:
            return 'skipped'

        next_step_number = run.step + 1
        if next_step_number > step_count:
            run.completed = True
            run.save(update_fields=['completed', 'updated_at'])
            return 'stopped'

        next_step = steps.filter(step_order=next_step_number).first()
        if not next_step:
            return 'skipped'

        # Timing: first step anchors off the reply time; later steps off last send.
        delay = timedelta(
            days=next_step.delay_days, hours=next_step.delay_hours,
            minutes=next_step.delay_minutes,
        )
        if run.step == 0:
            reference_time = (run.reply.replied_at if run.reply_id else None) or run.created_at
            send_time = reference_time + delay
            should_send = delay.total_seconds() <= 60 or timezone.now() >= send_time
        else:
            if not run.last_sent_at:
                # Shouldn't happen, but recover: treat as first step.
                run.step = 0
                run.save(update_fields=['step', 'updated_at'])
                return 'skipped'
            send_time = run.last_sent_at + delay
            should_send = timezone.now() >= send_time

        if not should_send:
            return 'skipped'

        if lead and lead.pk:
            lead.refresh_from_db(fields=['email', 'first_name', 'last_name', 'company', 'job_title'])

        if dry_run:
            self.stdout.write(f'  [DRY RUN] Sub-seq run step {next_step_number} -> {lead.email} ({sub_sequence.name})')
            return 'sent'

        email_account = sub_sequence.get_sending_account()
        result = email_service.send_email(
            template=next_step.template, lead=lead,
            campaign=campaign, email_account=email_account,
        )
        if result.get('success'):
            run.step = next_step_number
            run.last_sent_at = timezone.now()
            if next_step_number >= step_count:
                run.completed = True
            run.save(update_fields=['step', 'last_sent_at', 'completed', 'updated_at'])
            self.stdout.write(self.style.SUCCESS(
                f'  [SENT] Sub-seq run step {next_step_number} -> {lead.email} ({sub_sequence.name})'
            ))
            return 'stopped' if run.completed else 'sent'
        else:
            self.stdout.write(self.style.ERROR(
                f'  [FAIL] Sub-seq run step {next_step_number} -> {lead.email}: {result.get("error", "Unknown")}'
            ))
            return 'skipped'

    def _process_main_sequence_contact(self, contact, campaign, sequences, dry_run):
        """Process a contact in the main sequence. Returns 'sent', 'skipped', or 'stopped'"""
        lead = contact.lead

        if contact.replied:
            return 'stopped'

        sequence = contact.sequence
        if not sequence:
            sequence = sequences.first()
            if sequence:
                contact.sequence = sequence
                contact.save()
            else:
                return 'skipped'

        steps = sequence.steps.all().order_by('step_order')
        step_count = steps.count()

        if step_count == 0:
            return 'skipped'

        next_step_number = contact.current_step + 1

        if next_step_number > step_count:
            contact.mark_completed()
            return 'stopped'

        next_step = steps.filter(step_order=next_step_number).first()
        if not next_step:
            return 'skipped'

        # NOTE: We rely on current_step tracking (not EmailSendHistory) to determine
        # which step to send next. The current_step is advanced after each successful
        # send, so it is the source of truth for sequence progress.

        should_send, send_reason = self._should_send_email(contact, campaign, next_step)
        if not should_send:
            return 'skipped'

        return self._send_sequence_email(contact, campaign, sequence, next_step, next_step_number, step_count, dry_run)

    def _should_send_email(self, contact, campaign, next_step):
        """Determine if it's time to send the next email in main sequence"""
        delay = timedelta(
            days=next_step.delay_days, hours=next_step.delay_hours,
            minutes=next_step.delay_minutes
        )

        if contact.current_step == 0:
            reference_time = contact.started_at if contact.started_at else contact.created_at
            send_time = reference_time + delay

            if delay.total_seconds() <= 60:
                return True, 'First step - immediate'
            elif timezone.now() >= send_time:
                return True, 'First step delay passed'
            else:
                return False, ''
        else:
            if not contact.last_sent_at:
                contact.current_step = 0
                contact.save()
                return False, ''

            send_time = contact.last_sent_at + delay

            if timezone.now() >= send_time:
                return True, 'Delay passed'
            else:
                return False, ''

    def _send_sequence_email(self, contact, campaign, sequence, next_step, next_step_number, step_count, dry_run):
        """Send an email for a sequence step. Returns 'sent' or 'stopped'"""
        lead = contact.lead
        if lead and lead.pk:
            lead.refresh_from_db(fields=['email', 'first_name', 'last_name', 'company', 'job_title'])

        if not dry_run:
            email_account = sequence.get_sending_account()
            result = email_service.send_email(
                template=next_step.template, lead=lead,
                campaign=campaign, email_account=email_account
            )

            if result.get('success'):
                contact.advance_step(sent_at=timezone.now())
                self.stdout.write(self.style.SUCCESS(
                    f'  [SENT] Step {next_step_number}/{step_count} -> {lead.email} ({next_step.template.subject})'
                ))

                if next_step_number >= step_count:
                    contact.mark_completed()
                    return 'stopped'
                return 'sent'
            else:
                self.stdout.write(self.style.ERROR(
                    f'  [FAIL] Step {next_step_number} -> {lead.email}: {result.get("error", "Unknown")}'
                ))
                return 'skipped'
        else:
            self.stdout.write(f'  [DRY RUN] Step {next_step_number} -> {lead.email}')
            return 'sent'

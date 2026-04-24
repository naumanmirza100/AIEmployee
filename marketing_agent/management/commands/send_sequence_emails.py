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
    Lead, CampaignContact, Reply
)
from marketing_agent.services.email_service import email_service
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Automatically send email sequence emails based on delay timing and contact state'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without actually sending emails',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY RUN] No emails will be sent'))

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

            # Handle replied contacts - try to assign sub-sequences
            replied_without_sub = CampaignContact.objects.filter(
                campaign=campaign, replied=True, sub_sequence__isnull=True
            ).select_related('lead', 'sequence', 'sub_sequence')

            for contact in replied_without_sub:
                self._try_assign_sub_sequence(contact)

            # Get sub-sequence contacts
            sub_sequence_contacts = CampaignContact.objects.filter(
                campaign=campaign, replied=True,
                sub_sequence__is_active=True, sub_sequence__isnull=False,
                sub_sequence_completed=False
            ).select_related('lead', 'sub_sequence').prefetch_related('sub_sequence__steps')

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

            # Process sub-sequence contacts
            for contact in sub_sequence_contacts:
                total_checked += 1
                contact.refresh_from_db()
                result = self._process_sub_sequence_contact(contact, campaign, dry_run)
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

    def _try_assign_sub_sequence(self, contact):
        """Try to assign a sub-sequence to a replied contact."""
        if not contact.sequence or not contact.reply_interest_level:
            return

        target_interest = contact.reply_interest_level

        # Try exact interest match -> 'any' -> any active sub-sequence
        for filter_kwargs in [
            {'interest_level': target_interest},
            {'interest_level': 'any'},
            {},
        ]:
            sub_seq = EmailSequence.objects.filter(
                parent_sequence=contact.sequence,
                is_sub_sequence=True, is_active=True,
                **filter_kwargs
            ).first()
            if sub_seq:
                break

        if not sub_seq:
            return

        contact.sub_sequence = sub_seq
        contact.sub_sequence_step = 0
        contact.sub_sequence_last_sent_at = None
        contact.sub_sequence_completed = False
        if not contact.replied_at:
            contact.replied_at = timezone.now()
        contact.save()
        self.stdout.write(self.style.SUCCESS(
            f'  Sub-sequence "{sub_seq.name}" assigned to {contact.lead.email}'
        ))

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

    def _reply_was_to_sub_sequence_email(self, contact, campaign):
        """True if the contact's most recent reply was to a sub-sequence email.

        Trusts Reply.sub_sequence (set authoritatively in reply_processor when the
        triggering email was matched to a sub-seq template). Falls back to a
        template-based check only if that field is null — using any() so a template
        shared across main and sub still counts as sub when any linked step is sub.
        """
        latest = (
            Reply.objects.filter(campaign=campaign, lead=contact.lead)
            .select_related('sub_sequence', 'triggering_email', 'triggering_email__email_template')
            .order_by('-replied_at')
            .first()
        )
        if not latest:
            return False
        if latest.sub_sequence_id is not None:
            return True
        if not latest.triggering_email_id or not latest.triggering_email.email_template_id:
            return False
        template = latest.triggering_email.email_template
        steps = list(template.sequence_steps.select_related('sequence').all())
        if not steps:
            return False
        return any(step.sequence.is_sub_sequence for step in steps)

    def _process_sub_sequence_contact(self, contact, campaign, dry_run):
        """Process a contact in a sub-sequence (after they replied). Returns 'sent', 'skipped', or 'stopped'"""
        lead = contact.lead
        sub_sequence = contact.sub_sequence

        if not sub_sequence:
            return 'skipped'

        # Skip if reply was to a sub-sequence email
        if self._reply_was_to_sub_sequence_email(contact, campaign):
            contact.sub_sequence = None
            contact.sub_sequence_step = 0
            contact.sub_sequence_last_sent_at = None
            contact.sub_sequence_completed = False
            contact.save()
            return 'skipped'

        # Verify interest level match
        if sub_sequence.interest_level != 'any':
            if not contact.reply_interest_level or contact.reply_interest_level != sub_sequence.interest_level:
                # Clear wrong sub-sequence and try to find correct one
                contact.sub_sequence = None
                contact.sub_sequence_step = 0
                contact.sub_sequence_last_sent_at = None
                contact.sub_sequence_completed = False

                target_interest = contact.reply_interest_level or 'neutral'
                correct_sub = (
                    EmailSequence.objects.filter(
                        parent_sequence=contact.sequence, is_sub_sequence=True,
                        is_active=True, interest_level=target_interest
                    ).first()
                    or EmailSequence.objects.filter(
                        parent_sequence=contact.sequence, is_sub_sequence=True,
                        is_active=True, interest_level='any'
                    ).first()
                )

                if correct_sub:
                    contact.sub_sequence = correct_sub
                    contact.save()
                    sub_sequence = correct_sub
                else:
                    contact.save()
                    return 'skipped'

        steps = sub_sequence.steps.all().order_by('step_order')
        step_count = steps.count()

        if step_count == 0:
            return 'skipped'

        next_step_number = contact.sub_sequence_step + 1

        if next_step_number > step_count:
            contact.sub_sequence_completed = True
            contact.save()
            return 'stopped'

        next_step = steps.filter(step_order=next_step_number).first()
        if not next_step:
            return 'skipped'

        # Calculate if it's time to send
        should_send = False

        if contact.sub_sequence_step == 0:
            # First step - use replied_at as reference
            if not contact.replied_at:
                contact.replied_at = timezone.now()
                contact.save()

            reference_time = contact.replied_at
            delay = timedelta(
                days=next_step.delay_days, hours=next_step.delay_hours,
                minutes=next_step.delay_minutes
            )
            send_time = reference_time + delay

            if delay.total_seconds() <= 60:
                should_send = True
            elif timezone.now() >= send_time:
                should_send = True
            else:
                return 'skipped'
        else:
            # Subsequent steps - check delay from last sub-sequence email
            if not contact.sub_sequence_last_sent_at:
                contact.sub_sequence_step = 0
                contact.save()
                return 'skipped'

            delay = timedelta(
                days=next_step.delay_days, hours=next_step.delay_hours,
                minutes=next_step.delay_minutes
            )
            send_time = contact.sub_sequence_last_sent_at + delay

            if timezone.now() >= send_time:
                should_send = True
            else:
                return 'skipped'

        if should_send:
            if lead and lead.pk:
                lead.refresh_from_db(fields=['email', 'first_name', 'last_name', 'company', 'job_title'])

            if not dry_run:
                email_account = sub_sequence.get_sending_account()
                result = email_service.send_email(
                    template=next_step.template, lead=lead,
                    campaign=campaign, email_account=email_account
                )

                if result.get('success'):
                    contact.sub_sequence_step = next_step_number
                    contact.sub_sequence_last_sent_at = timezone.now()
                    contact.save()
                    self.stdout.write(self.style.SUCCESS(
                        f'  [SENT] Sub-seq step {next_step_number} -> {lead.email} ({sub_sequence.name})'
                    ))

                    if next_step_number >= step_count:
                        contact.sub_sequence_completed = True
                        contact.save()
                        return 'stopped'
                    return 'sent'
                else:
                    self.stdout.write(self.style.ERROR(
                        f'  [FAIL] Sub-seq step {next_step_number} -> {lead.email}: {result.get("error", "Unknown")}'
                    ))
                    return 'skipped'
            else:
                self.stdout.write(f'  [DRY RUN] Sub-seq step {next_step_number} -> {lead.email}')
                return 'sent'

        return 'skipped'

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

"""
Django management command to send email sequence emails based on delays.

This command should be run periodically (e.g., every 30 minutes via cron) to:
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
    Lead, CampaignContact
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
        
        self.stdout.write(self.style.SUCCESS(' Starting automated email sequence processing...'))
        self.stdout.write(f'Current time: {timezone.now()}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING(' DRY RUN MODE - No emails will be sent'))
        
        # Get all active campaigns
        campaigns = Campaign.objects.filter(status='active')
        campaign_count = campaigns.count()
        self.stdout.write(f'\n Found {campaign_count} active campaign(s)')
        
        if campaign_count == 0:
            self.stdout.write(self.style.WARNING('No active campaigns found. Make sure campaigns are set to "active" status.'))
            return
        
        total_sent = 0
        total_checked = 0
        total_skipped = 0
        total_stopped = 0
        
        # Process each campaign
        for campaign in campaigns:
            self.stdout.write(f'\n{"="*60}')
            self.stdout.write(f'Processing Campaign: {campaign.name} (ID: {campaign.id})')
            self.stdout.write(f'{"="*60}')
            
            # Get active sequences for this campaign
            # IMPORTANT: Only process MAIN sequences here (not sub-sequences)
            # Sub-sequences should NEVER have contacts created for all leads
            # They are only assigned when leads reply
            sequences = campaign.email_sequences.filter(is_active=True, is_sub_sequence=False)  # Only main sequences
            
            # Ensure every lead has a CampaignContact per active MAIN sequence only
            # Sub-sequences should NOT have contacts created here - they are created when leads reply
            leads = list(campaign.leads.all())
            for seq in sequences:
                for lead in leads:
                    CampaignContact.objects.get_or_create(
                        campaign=campaign,
                        lead=lead,
                        sequence=seq,
                        defaults={'current_step': 0},
                    )
            
            # CRITICAL: Double-check that no sub-sequences are being processed as main sequences
            # If any sub-sequences have contacts for all leads, that's a bug
            sub_sequences_with_contacts = EmailSequence.objects.filter(
                campaign=campaign,
                is_sub_sequence=True,
                is_active=True
            )
            for sub_seq in sub_sequences_with_contacts:
                sub_seq_contacts = CampaignContact.objects.filter(
                    campaign=campaign,
                    sequence=sub_seq,
                    replied=False  # Contacts in sub-sequences should ALWAYS have replied=True
                )
                if sub_seq_contacts.exists():
                    self.stdout.write(
                        self.style.ERROR(
                            f'  [ERROR] Found {sub_seq_contacts.count()} contacts in sub-sequence "{sub_seq.name}" '
                            f'that have NOT replied! This should never happen. Fixing...'
                        )
                    )
                    # Fix: Delete contacts in sub-sequences that haven't replied
                    sub_seq_contacts.delete()
            sequence_count = sequences.count()
            self.stdout.write(f'  Found {sequence_count} active sequence(s)')
            
            if sequence_count == 0:
                self.stdout.write(self.style.WARNING(f'  No active sequences found for campaign "{campaign.name}"'))
                continue
            
            # Get all contacts for this campaign
            # CRITICAL: Only get contacts from MAIN sequences (not sub-sequences)
            # Sub-sequences are handled separately and should only have contacts who replied
            all_contacts = CampaignContact.objects.filter(
                campaign=campaign,
                sequence__is_active=True,
                sequence__isnull=False,
                sequence__is_sub_sequence=False  # EXCLUDE sub-sequences from main contact processing
            )
            total_contacts = all_contacts.count()
            print("total_contacts", total_contacts)
            
            # Get active contacts (not completed and not replied) - MAIN SEQUENCE
            main_contacts = all_contacts.filter(
                completed=False,
                replied=False
            ).select_related('lead', 'sequence').prefetch_related('sequence__steps')
            
            # Get contacts in sub-sequences (replied AND interest level matches sub-sequence interest_level)
            # Only send sub-sequence emails to leads who:
            # 1. Have replied
            # 2. Have a sub-sequence assigned (or we'll try to assign one)
            # 3. The sub-sequence is active
            # 4. The sub-sequence is not completed
            # 5. Their reply_interest_level matches the sub-sequence's interest_level OR sub-sequence accepts 'any'
            
            # First, get all replied contacts
            replied_contacts_all = CampaignContact.objects.filter(
                campaign=campaign,
                replied=True
            ).select_related('lead', 'sequence', 'sub_sequence')
            
            # Try to assign sub-sequences to replied contacts that don't have one yet
            # This handles cases where mark_replied didn't assign a sub-sequence
            replied_without_sub = replied_contacts_all.filter(sub_sequence__isnull=True)
            self.stdout.write(f'  DEBUG: Replied contacts without sub-sequence: {replied_without_sub.count()}')
            
            for contact in replied_without_sub:
                if contact.sequence and contact.reply_interest_level:
                    # Try to find a matching sub-sequence
                    target_interest = contact.reply_interest_level
                    self.stdout.write(
                        f'  DEBUG: Checking {contact.lead.email} - sequence: {contact.sequence.name}, '
                        f'interest: {target_interest}'
                    )
                    
                    # Look for sub-sequences matching the interest level
                    sub_sequences = EmailSequence.objects.filter(
                        parent_sequence=contact.sequence,
                        is_sub_sequence=True,
                        is_active=True,
                        interest_level=target_interest
                    )
                    self.stdout.write(f'  DEBUG: Found {sub_sequences.count()} sub-sequences with interest={target_interest}')
                    
                    # If no exact match, try 'any'
                    if not sub_sequences.exists() and target_interest != 'any':
                        sub_sequences = EmailSequence.objects.filter(
                            parent_sequence=contact.sequence,
                            is_sub_sequence=True,
                            is_active=True,
                            interest_level='any'
                        )
                        self.stdout.write(f'  DEBUG: Found {sub_sequences.count()} sub-sequences with interest=any')
                    
                    # If still no match, get any active sub-sequence as fallback
                    if not sub_sequences.exists():
                        sub_sequences = EmailSequence.objects.filter(
                            parent_sequence=contact.sequence,
                            is_sub_sequence=True,
                            is_active=True
                        ).order_by('created_at')
                        self.stdout.write(f'  DEBUG: Found {sub_sequences.count()} sub-sequences (any active)')
                    
                    if sub_sequences.exists():
                        sub_sequence = sub_sequences.first()
                        contact.sub_sequence = sub_sequence
                        contact.sub_sequence_step = 0
                        contact.sub_sequence_last_sent_at = None
                        contact.sub_sequence_completed = False
                        contact.save()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  [AUTO-ASSIGNED] Sub-sequence "{sub_sequence.name}" to {contact.lead.email} '
                                f'(interest: {contact.reply_interest_level})'
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f'  [NO SUB-SEQUENCE] No matching sub-sequence found for {contact.lead.email} '
                                f'(sequence: {contact.sequence.name}, interest: {target_interest})'
                            )
                        )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'  [SKIP] {contact.lead.email} - sequence: {contact.sequence.name if contact.sequence else "None"}, '
                            f'interest: {contact.reply_interest_level or "None"}'
                        )
                    )
            
            # Now get contacts with sub-sequences assigned
            # Get all replied contacts with sub-sequences (don't filter by interest level here - that's handled in _process_sub_sequence_contact)
            sub_sequence_contacts = CampaignContact.objects.filter(
                campaign=campaign,
                replied=True,
                sub_sequence__is_active=True,
                sub_sequence__isnull=False,
                sub_sequence_completed=False
            ).select_related('lead', 'sub_sequence').prefetch_related('sub_sequence__steps')
            
            main_contact_count = main_contacts.count()
            sub_contact_count = sub_sequence_contacts.count()
            
            # Show breakdown of contact status
            completed_count = all_contacts.filter(completed=True).count()
            replied_count = all_contacts.filter(replied=True, completed=False).count()
            replied_with_sub = replied_count - sub_contact_count  # Replied but no sub-sequence
            
            self.stdout.write(f'  Total contacts: {total_contacts}')
            self.stdout.write(f'  Active main sequence contacts: {main_contact_count}')
            self.stdout.write(f'  Active sub-sequence contacts: {sub_contact_count}')
            if completed_count > 0:
                self.stdout.write(f'  Completed: {completed_count}')
            if replied_with_sub > 0:
                self.stdout.write(f'  Replied (no sub-sequence): {replied_with_sub}')
            
            # Process main sequence contacts
            if main_contact_count > 0:
                self.stdout.write(f'\n  Processing {main_contact_count} main sequence contact(s)...')
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
            if sub_contact_count > 0:
                self.stdout.write(f'\n  Processing {sub_contact_count} sub-sequence contact(s)...')
                for contact in sub_sequence_contacts:
                    total_checked += 1
                    result = self._process_sub_sequence_contact(contact, campaign, dry_run)
                    if result == 'sent':
                        total_sent += 1
                    elif result == 'skipped':
                        total_skipped += 1
                    elif result == 'stopped':
                        total_stopped += 1
            
            if main_contact_count == 0 and sub_contact_count == 0:
                if total_contacts == 0:
                    self.stdout.write(self.style.WARNING(f'  No contacts found for campaign "{campaign.name}"'))
                else:
                    self.stdout.write(self.style.WARNING(
                        f'  No active contacts found for campaign "{campaign.name}" '
                        f'(all {total_contacts} contact(s) are completed or replied)'
                    ))
                continue
        
        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f'\n{"="*60}\n'
                f' SUMMARY:\n'
                f'  Campaigns processed: {campaign_count}\n'
                f'  Contacts checked: {total_checked}\n'
                f'  Emails sent: {total_sent}\n'
                f'  Emails skipped (waiting): {total_skipped}\n'
                f'  Sequences completed/stopped: {total_stopped}\n'
                f'{"="*60}'
            )
        )
    
    def _process_main_sequence_contact(self, contact, campaign, sequences, dry_run):
        """Process a contact in the main sequence. Returns 'sent', 'skipped', or 'stopped'"""
        lead = contact.lead
        self.stdout.write(f'\n   Main Sequence Contact: {lead.email}')
        
        # SAFETY CHECK: If contact has replied, stop main sequence immediately
        # This prevents race conditions where reply was marked after query but before processing
        if contact.replied:
            self.stdout.write(
                self.style.WARNING(
                    f'     Contact {lead.email} has replied (interest: {contact.reply_interest_level or "N/A"}) - stopping main sequence'
                )
            )
            return 'stopped'
        
        # Determine which sequence to use
        sequence = contact.sequence
        if not sequence:
            # No sequence assigned - try to get first active sequence
            sequence = sequences.first()
            if sequence:
                contact.sequence = sequence
                contact.save()
                self.stdout.write(f'     Assigned sequence: {sequence.name}')
            else:
                self.stdout.write(self.style.WARNING('    No sequence available for this contact'))
                return 'skipped'
        
        # Get steps for this sequence
        steps = sequence.steps.all().order_by('step_order')
        step_count = steps.count()
        
        if step_count == 0:
            self.stdout.write(self.style.WARNING('     Sequence has no steps'))
            return 'skipped'
        
        # Determine next step number
        next_step_number = contact.current_step + 1
        
        # Check if sequence is already complete
        if next_step_number > step_count:
            self.stdout.write(self.style.SUCCESS(f'     Sequence complete (all {step_count} steps sent)'))
            contact.mark_completed()
            return 'stopped'
        
        # Get the next step
        next_step = steps.filter(step_order=next_step_number).first()
        
        if not next_step:
            self.stdout.write(self.style.WARNING(f'     Step {next_step_number} not found in sequence'))
            return 'skipped'
        
        # Check if this step was already sent (safety check)
        already_sent = EmailSendHistory.objects.filter(
            campaign=campaign,
            lead=lead,
            email_template=next_step.template
        ).exists()
        
        if already_sent:
            self.stdout.write(self.style.WARNING(f'     Step {next_step_number} already sent, advancing...'))
            contact.advance_step()
            return 'skipped'
        
        # Calculate if it's time to send
        should_send, send_reason = self._should_send_email(contact, campaign, next_step)
        
        if not should_send:
            return 'skipped'
        
        # Send the email
        return self._send_sequence_email(contact, campaign, sequence, next_step, next_step_number, step_count, dry_run)
    
    def _process_sub_sequence_contact(self, contact, campaign, dry_run):
        """Process a contact in a sub-sequence (after they replied). Returns 'sent', 'skipped', or 'stopped'"""
        lead = contact.lead
        sub_sequence = contact.sub_sequence
        
        if not sub_sequence:
            self.stdout.write(self.style.WARNING(f'   Sub-sequence contact {lead.email} has no sub_sequence assigned'))
            return 'skipped'
        
        # Verify that the contact's reply interest level matches the sub-sequence's interest level
        if sub_sequence.interest_level != 'any':
            if not contact.reply_interest_level or contact.reply_interest_level != sub_sequence.interest_level:
                # Wrong sub-sequence assigned - clear it and try to find the correct one
                self.stdout.write(
                    self.style.WARNING(
                        f'   Wrong sub-sequence assigned to {lead.email}: Reply interest level "{contact.reply_interest_level or "N/A"}" '
                        f'does not match sub-sequence interest level "{sub_sequence.interest_level}". Clearing and searching for correct one...'
                    )
                )
                
                # Clear the wrong sub-sequence
                contact.sub_sequence = None
                contact.sub_sequence_step = 0
                contact.sub_sequence_last_sent_at = None
                contact.sub_sequence_completed = False
                
                # Try to find the correct sub-sequence
                target_interest = contact.reply_interest_level or 'neutral'
                correct_sub_sequences = EmailSequence.objects.filter(
                    parent_sequence=contact.sequence,
                    is_sub_sequence=True,
                    is_active=True,
                    interest_level=target_interest
                )
                
                # If no exact match, try 'any'
                if not correct_sub_sequences.exists() and target_interest != 'any':
                    correct_sub_sequences = EmailSequence.objects.filter(
                        parent_sequence=contact.sequence,
                        is_sub_sequence=True,
                        is_active=True,
                        interest_level='any'
                    )
                
                if correct_sub_sequences.exists():
                    correct_sub_sequence = correct_sub_sequences.first()
                    contact.sub_sequence = correct_sub_sequence
                    contact.save()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'   [FIXED] Assigned correct sub-sequence "{correct_sub_sequence.name}" '
                            f'(interest: {correct_sub_sequence.interest_level}) to {lead.email}'
                        )
                    )
                    # Continue processing with the correct sub-sequence
                    sub_sequence = correct_sub_sequence
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'   No matching sub-sequence found for {lead.email} with interest level "{target_interest}"'
                        )
                    )
                    contact.save()
                    return 'skipped'
        
        self.stdout.write(
            f'\n   Sub-Sequence Contact: {lead.email} '
            f'(Sub-sequence: {sub_sequence.name}, Interest: {contact.reply_interest_level or "N/A"})'
        )
        
        # Get steps for sub-sequence
        steps = sub_sequence.steps.all().order_by('step_order')
        step_count = steps.count()
        
        if step_count == 0:
            self.stdout.write(self.style.WARNING('     Sub-sequence has no steps'))
            return 'skipped'
        
        # Determine next step number
        next_step_number = contact.sub_sequence_step + 1
        
        # Check if sub-sequence is already complete
        if next_step_number > step_count:
            self.stdout.write(self.style.SUCCESS(f'     Sub-sequence complete (all {step_count} steps sent)'))
            contact.sub_sequence_completed = True
            contact.save()
            return 'stopped'
        
        # Get the next step
        next_step = steps.filter(step_order=next_step_number).first()
        
        if not next_step:
            self.stdout.write(self.style.WARNING(f'     Step {next_step_number} not found in sub-sequence'))
            return 'skipped'
        
        # Calculate if it's time to send (based on sub_sequence_last_sent_at)
        should_send = False
        send_reason = ''
        
        if contact.sub_sequence_step == 0:
            # First step in sub-sequence - send immediately after reply
            should_send = True
            send_reason = 'First step in sub-sequence (reply received)'
        else:
            # Subsequent steps - check delay from last sub-sequence email
            if not contact.sub_sequence_last_sent_at:
                self.stdout.write(self.style.WARNING('    No sub_sequence_last_sent_at but step > 0, resetting...'))
                contact.sub_sequence_step = 0
                contact.save()
                return 'skipped'
            
            delay = timedelta(
                days=next_step.delay_days,
                hours=next_step.delay_hours,
                minutes=next_step.delay_minutes
            )
            send_time = contact.sub_sequence_last_sent_at + delay
            
            if timezone.now() >= send_time:
                should_send = True
                send_reason = f'Delay passed since last sub-sequence email ({contact.sub_sequence_last_sent_at})'
            else:
                time_remaining = send_time - timezone.now()
                self.stdout.write(f'   Waiting: {time_remaining} remaining (last sent: {contact.sub_sequence_last_sent_at})')
                return 'skipped'
        
        # Send the email
        if should_send:
            self.stdout.write(f'    Sending Sub-Sequence Step {next_step_number}: {next_step.template.subject}')
            self.stdout.write(f'      Reason: {send_reason}')
            
            if not dry_run:
                # Use sub-sequence's email account if set
                email_account = sub_sequence.email_account
                result = email_service.send_email(
                    template=next_step.template,
                    lead=lead,
                    campaign=campaign,
                    email_account=email_account
                )
                
                if result.get('success'):
                    # Update sub-sequence state
                    contact.sub_sequence_step = next_step_number
                    contact.sub_sequence_last_sent_at = timezone.now()
                    contact.save()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'     [SENT] Sub-sequence step {next_step_number} sent to {lead.email}'
                        )
                    )
                    
                    # Check if sub-sequence is now complete
                    if next_step_number >= step_count:
                        contact.sub_sequence_completed = True
                        contact.save()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'     Sub-sequence completed for {lead.email}'
                            )
                        )
                        return 'stopped'
                    return 'sent'
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f'    [FAIL] Failed to send: {result.get("error", "Unknown error")}'
                        )
                    )
                    return 'skipped'
            else:
                # Dry run
                self.stdout.write(
                    self.style.WARNING(
                        f'    [DRY RUN] Would send sub-sequence step {next_step_number} to {lead.email}'
                    )
                )
                return 'sent'
        
        return 'skipped'
    
    def _should_send_email(self, contact, campaign, next_step):
        """Determine if it's time to send the next email in main sequence"""
        from datetime import datetime
        
        should_send = False
        send_reason = ''
        
        if contact.current_step == 0:
            # First step - use contact creation time or started_at as reference
            # This ensures delays are calculated from when contact was added, not from current time
            # If started_at is set, use it; otherwise use created_at
            reference_time = contact.started_at if contact.started_at else contact.created_at
            
            delay = timedelta(
                days=next_step.delay_days,
                hours=next_step.delay_hours,
                minutes=next_step.delay_minutes
            )
            
            # Calculate send_time from reference_time
            send_time = reference_time + delay
            
            # For step 0, if delay is 0 or very small (≤ 1 minute), send immediately
            if delay.total_seconds() <= 60:  # 1 minute or less
                should_send = True
                send_reason = f'First step (delay: {delay.total_seconds()}s - sending immediately)'
            elif timezone.now() >= send_time:
                # Enough time has passed since contact was added
                should_send = True
                send_reason = f'First step delay passed (reference: {reference_time}, send_time: {send_time})'
            else:
                # Still waiting for the delay to pass
                time_remaining = send_time - timezone.now()
                self.stdout.write(f'    Waiting for first step: {time_remaining} remaining (delay: {delay}, reference: {reference_time}, send_time: {send_time})')
        else:
            # Subsequent steps - check delay from last sent
            if not contact.last_sent_at:
                self.stdout.write(self.style.WARNING('    No last_sent_at but current_step > 0, resetting...'))
                contact.current_step = 0
                contact.save()
                return False, ''
            
            delay = timedelta(
                days=next_step.delay_days,
                hours=next_step.delay_hours,
                minutes=next_step.delay_minutes
            )
            send_time = contact.last_sent_at + delay
            
            if timezone.now() >= send_time:
                should_send = True
                send_reason = f'Delay passed since last email ({contact.last_sent_at})'
            else:
                time_remaining = send_time - timezone.now()
                self.stdout.write(f'   Waiting: {time_remaining} remaining (last sent: {contact.last_sent_at})')
        
        return should_send, send_reason
    
    def _send_sequence_email(self, contact, campaign, sequence, next_step, next_step_number, step_count, dry_run):
        """Send an email for a sequence step. Returns 'sent' or 'stopped'"""
        lead = contact.lead
        
        self.stdout.write(f'    Sending Step {next_step_number}: {next_step.template.subject}')
        self.stdout.write(f'      Delay: {next_step.delay_days}d {next_step.delay_hours}h {next_step.delay_minutes}m')
        
        if not dry_run:
            # Use sequence's email account if set
            email_account = sequence.email_account
            result = email_service.send_email(
                template=next_step.template,
                lead=lead,
                campaign=campaign,
                email_account=email_account
            )
            
            if result.get('success'):
                # Update contact state
                contact.advance_step(sent_at=timezone.now())
                self.stdout.write(
                    self.style.SUCCESS(
                        f'     [SENT] Step {next_step_number} sent to {lead.email}'
                    )
                )
                
                # Check if sequence is now complete
                if next_step_number >= step_count:
                    contact.mark_completed()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'     Sequence completed for {lead.email}'
                        )
                    )
                    return 'stopped'
                return 'sent'
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f'    [FAIL] Failed to send: {result.get("error", "Unknown error")}'
                    )
                )
                return 'skipped'
        else:
            # Dry run
            self.stdout.write(
                self.style.WARNING(
                    f'    [DRY RUN] Would send step {next_step_number} to {lead.email}'
                )
            )
            return 'sent'

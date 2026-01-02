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
            sequences = campaign.email_sequences.filter(is_active=True)
            # Ensure every lead has a CampaignContact per active sequence
            leads = list(campaign.leads.all())
            for seq in sequences:
                for lead in leads:
                    CampaignContact.objects.get_or_create(
                        campaign=campaign,
                        lead=lead,
                        sequence=seq,
                        defaults={'current_step': 0},
                    )
            sequence_count = sequences.count()
            self.stdout.write(f'  Found {sequence_count} active sequence(s)')
            
            if sequence_count == 0:
                self.stdout.write(self.style.WARNING(f'  No active sequences found for campaign "{campaign.name}"'))
                continue
            
            # Get all contacts for this campaign
            # all_contacts = CampaignContact.objects.filter(campaign=campaign)
            all_contacts = CampaignContact.objects.filter(
                campaign=campaign,
                sequence__is_active=True,
                sequence__isnull=False,
            )
            total_contacts = all_contacts.count()
            print("total_contacts", total_contacts)
            
            # Get active contacts (not completed and not replied)
            contacts = all_contacts.filter(
                completed=False,
                replied=False
            ).select_related('lead', 'sequence').prefetch_related('sequence__steps')
            
            contact_count = contacts.count()
            
            # Show breakdown of contact status
            completed_count = all_contacts.filter(completed=True).count()
            replied_count = all_contacts.filter(replied=True, completed=False).count()
            
            self.stdout.write(f'  Total contacts: {total_contacts}')
            self.stdout.write(f'  Active contacts (not completed, not replied): {contact_count}')
            if completed_count > 0:
                self.stdout.write(f'  Completed: {completed_count}')
            if replied_count > 0:
                self.stdout.write(f'  Replied (automation stopped): {replied_count}')
            
            if contact_count == 0:
                if total_contacts == 0:
                    self.stdout.write(self.style.WARNING(f'  No contacts found for campaign "{campaign.name}"'))
                else:
                    self.stdout.write(self.style.WARNING(
                        f'  No active contacts found for campaign "{campaign.name}" '
                        f'(all {total_contacts} contact(s) are completed or replied)'
                    ))
                continue
            
            # Process each contact
            for contact in contacts:
                total_checked += 1
                lead = contact.lead
                self.stdout.write(f'\n   Contact: {lead.email}')
                
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
                        total_skipped += 1
                        continue
                
                # Get steps for this sequence
                steps = sequence.steps.all().order_by('step_order')
                step_count = steps.count()
                
                if step_count == 0:
                    self.stdout.write(self.style.WARNING('     Sequence has no steps'))
                    total_skipped += 1
                    continue
                
                # Determine next step number
                next_step_number = contact.current_step + 1
                
                # Check if sequence is already complete
                if next_step_number > step_count:
                    self.stdout.write(self.style.SUCCESS(f'     Sequence complete (all {step_count} steps sent)'))
                    contact.mark_completed()
                    total_stopped += 1
                    continue
                
                # Get the next step
                next_step = steps.filter(step_order=next_step_number).first()
                
                if not next_step:
                    self.stdout.write(self.style.WARNING(f'     Step {next_step_number} not found in sequence'))
                    total_skipped += 1
                    continue
                
                # Check if this step was already sent (safety check)
                already_sent = EmailSendHistory.objects.filter(
                    campaign=campaign,
                    lead=lead,
                    email_template=next_step.template
                ).exists()
                
                if already_sent:
                    self.stdout.write(self.style.WARNING(f'     Step {next_step_number} already sent, advancing...'))
                    contact.advance_step()
                    total_skipped += 1
                    continue
                
                # Calculate if it's time to send
                should_send = False
                send_reason = ''
                
                if contact.current_step == 0:
                    # First step - check campaign start date
                    if campaign.start_date:
                        reference_time = timezone.make_aware(
                            datetime.combine(campaign.start_date, datetime.min.time())
                        )
                    else:
                        reference_time = campaign.created_at
                    
                    delay = timedelta(
                        days=next_step.delay_days,
                        hours=next_step.delay_hours,
                        minutes=next_step.delay_minutes
                    )
                    send_time = reference_time + delay
                    
                    if timezone.now() >= send_time:
                        should_send = True
                        send_reason = f'First step delay passed (started: {reference_time})'
                    else:
                        time_remaining = send_time - timezone.now()
                        self.stdout.write(f'    Waiting for first step: {time_remaining} remaining')
                        total_skipped += 1
                        continue
                else:
                    # Subsequent steps - check delay from last sent
                    if not contact.last_sent_at:
                        # Shouldn't happen, but handle it
                        self.stdout.write(self.style.WARNING('    No last_sent_at but current_step > 0, resetting...'))
                        contact.current_step = 0
                        contact.save()
                        total_skipped += 1
                        continue
                    
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
                        total_skipped += 1
                        continue
                
                # Send the email
                if should_send:
                    self.stdout.write(f'    Sending Step {next_step_number}: {next_step.template.subject}')
                    self.stdout.write(f'      Reason: {send_reason}')
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
                            total_sent += 1
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
                                total_stopped += 1
                        else:
                            self.stdout.write(
                                self.style.ERROR(
                                    f'    [FAIL] Failed to send: {result.get("error", "Unknown error")}'
                                )
                            )
                    else:
                        # Dry run
                        total_sent += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f'    [DRY RUN] Would send step {next_step_number} to {lead.email}'
                            )
                        )
        
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

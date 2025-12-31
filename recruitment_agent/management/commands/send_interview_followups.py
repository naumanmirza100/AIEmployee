"""
Management command to send follow-up emails for interviews.

This command:
1. Sends follow-up emails to candidates who haven't confirmed their interview (PENDING status)
2. Sends reminder emails before scheduled interviews (SCHEDULED status)
3. Prevents sending emails for past/completed/cancelled interviews
4. Limits the number of follow-up emails sent per interview
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from recruitment_agent.models import Interview
from recruitment_agent.agents.interview_scheduling.interview_scheduling_agent import InterviewSchedulingAgent
from recruitment_agent.log_service import LogService


class Command(BaseCommand):
    help = 'Send follow-up emails for pending interviews and reminders for scheduled interviews'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without actually sending emails (for testing)',
        )
        parser.add_argument(
            '--followup-hours',
            type=int,
            default=48,
            help='Hours to wait before sending first follow-up (default: 48)',
        )
        parser.add_argument(
            '--reminder-hours',
            type=int,
            default=24,
            help='Hours before interview to send reminder (default: 24)',
        )
        parser.add_argument(
            '--max-followups',
            type=int,
            default=3,
            help='Maximum number of follow-up emails to send (default: 3)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        followup_hours = options['followup_hours']
        reminder_hours = options['reminder_hours']
        max_followups = options['max_followups']

        self.stdout.write(self.style.SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.SUCCESS('📧 INTERVIEW FOLLOW-UP EMAIL SYSTEM'))
        self.stdout.write(self.style.SUCCESS('='*70))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('⚠️  DRY RUN MODE - No emails will be sent\n'))
        
        # Initialize agent
        log_service = LogService()
        interview_agent = InterviewSchedulingAgent(log_service=log_service)
        
        now = timezone.now()
        stats = {
            'followups_sent': 0,
            'reminders_sent': 0,
            'skipped_past': 0,
            'skipped_completed': 0,
            'skipped_max_followups': 0,
            'skipped_too_soon': 0,
            'errors': 0,
        }

        # 1. Process PENDING interviews - Send follow-up emails
        self.stdout.write(self.style.SUCCESS('\n📋 Processing PENDING interviews (unconfirmed)...'))
        pending_interviews = Interview.objects.filter(
            status='PENDING',
            invitation_sent_at__isnull=False
        ).exclude(
            status__in=['COMPLETED', 'CANCELLED']
        )
        
        for interview in pending_interviews:
            try:
                # Get recruiter settings for timing (uses interview-specific or recruiter default)
                followup_delay = interview.get_followup_delay_hours()
                max_followups_setting = interview.get_max_followup_emails()
                min_between = interview.get_min_hours_between_followups()
                
                # Skip if interview invitation was sent less than followup_delay hours ago
                time_since_invitation = now - interview.invitation_sent_at
                if time_since_invitation < timedelta(hours=followup_delay):
                    stats['skipped_too_soon'] += 1
                    continue
                
                # Skip if we've already sent max follow-ups (using recruiter preference)
                if interview.followup_count >= max_followups_setting:
                    stats['skipped_max_followups'] += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f'  ⏭️  Interview #{interview.id}: Max follow-ups ({max_followups_setting}) already sent'
                        )
                    )
                    continue
                
                # Check if enough time has passed since last follow-up (using recruiter preference)
                if interview.last_followup_sent_at:
                    time_since_last_followup = now - interview.last_followup_sent_at
                    if time_since_last_followup < timedelta(hours=min_between):
                        stats['skipped_too_soon'] += 1
                        continue
                
                # Send follow-up email
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  📧 Sending follow-up #{interview.followup_count + 1} to {interview.candidate_email} '
                        f'(Interview #{interview.id})'
                    )
                )
                
                if not dry_run:
                    result = interview_agent.send_followup_reminder(interview.id)
                    if result.get('success'):
                        # Update interview record
                        interview.followup_count += 1
                        interview.last_followup_sent_at = now
                        interview.save(update_fields=['followup_count', 'last_followup_sent_at'])
                        stats['followups_sent'] += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'    ✅ Follow-up email sent successfully'
                            )
                        )
                    else:
                        stats['errors'] += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f'    ❌ Failed to send follow-up: {result.get("error", "Unknown error")}'
                            )
                        )
                else:
                    stats['followups_sent'] += 1
                    self.stdout.write(self.style.WARNING('    [DRY RUN] Would send follow-up email'))
                    
            except Exception as e:
                stats['errors'] += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'  ❌ Error processing interview #{interview.id}: {str(e)}'
                    )
                )

        # 2. Process SCHEDULED interviews - Send pre-interview reminders
        self.stdout.write(self.style.SUCCESS('\n📋 Processing SCHEDULED interviews (sending reminders)...'))
        scheduled_interviews = Interview.objects.filter(
            status='SCHEDULED',
            scheduled_datetime__isnull=False,
            scheduled_datetime__gt=now  # Only future interviews
        ).exclude(
            status__in=['COMPLETED', 'CANCELLED']
        )
        
        for interview in scheduled_interviews:
            try:
                # Skip if interview is in the past
                if interview.scheduled_datetime <= now:
                    stats['skipped_past'] += 1
                    continue
                
                # Skip if reminder already sent
                if interview.pre_interview_reminder_sent_at:
                    continue
                
                # Get recruiter settings for reminder timing
                reminder_hours_setting = interview.get_reminder_hours_before()
                
                # Calculate when reminder should be sent (using recruiter preference)
                reminder_time = interview.scheduled_datetime - timedelta(hours=reminder_hours_setting)
                
                # Only send if we're within 2 hours of the reminder time (to allow for cron scheduling)
                time_until_reminder = (reminder_time - now).total_seconds()
                
                if time_until_reminder > 7200:  # More than 2 hours away
                    # Too early, skip
                    continue
                elif time_until_reminder < -7200:  # More than 2 hours past
                    # Too late, skip (interview is very soon or passed)
                    stats['skipped_past'] += 1
                    continue
                
                # Send reminder
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  📧 Sending pre-interview reminder to {interview.candidate_email} '
                        f'(Interview #{interview.id} on {interview.scheduled_datetime.strftime("%Y-%m-%d %H:%M")})'
                    )
                )
                
                if not dry_run:
                    reminder_hours_setting = interview.get_reminder_hours_before()
                    result = interview_agent.send_pre_interview_reminder(
                        interview.id,
                        hours_before=reminder_hours_setting
                    )
                    if result.get('success'):
                        # Update interview record
                        interview.pre_interview_reminder_sent_at = now
                        interview.save(update_fields=['pre_interview_reminder_sent_at'])
                        stats['reminders_sent'] += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'    ✅ Reminder email sent successfully'
                            )
                        )
                    else:
                        stats['errors'] += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f'    ❌ Failed to send reminder: {result.get("error", "Unknown error")}'
                            )
                        )
                else:
                    stats['reminders_sent'] += 1
                    self.stdout.write(self.style.WARNING('    [DRY RUN] Would send reminder email'))
                    
            except Exception as e:
                stats['errors'] += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'  ❌ Error processing interview #{interview.id}: {str(e)}'
                    )
                )

        # 3. Mark past interviews as COMPLETED if they haven't been updated
        self.stdout.write(self.style.SUCCESS('\n📋 Checking for past interviews to mark as COMPLETED...'))
        past_interviews = Interview.objects.filter(
            status__in=['SCHEDULED', 'PENDING'],
            scheduled_datetime__lt=now - timedelta(hours=2)  # 2 hours after scheduled time
        ).exclude(
            status__in=['COMPLETED', 'CANCELLED']
        )
        
        completed_count = 0
        for interview in past_interviews:
            if not dry_run:
                interview.status = 'COMPLETED'
                interview.save(update_fields=['status'])
                completed_count += 1
            else:
                completed_count += 1
        
        if completed_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'  ✅ Marked {completed_count} past interview(s) as COMPLETED'
                )
            )

        # Print summary
        self.stdout.write(self.style.SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.SUCCESS('📊 SUMMARY'))
        self.stdout.write(self.style.SUCCESS('='*70))
        self.stdout.write(f"  ✅ Follow-up emails sent: {stats['followups_sent']}")
        self.stdout.write(f"  ✅ Reminder emails sent: {stats['reminders_sent']}")
        self.stdout.write(f"  ⏭️  Skipped (too soon): {stats['skipped_too_soon']}")
        self.stdout.write(f"  ⏭️  Skipped (max follow-ups): {stats['skipped_max_followups']}")
        self.stdout.write(f"  ⏭️  Skipped (past interviews): {stats['skipped_past']}")
        self.stdout.write(f"  ⏭️  Skipped (completed/cancelled): {stats['skipped_completed']}")
        self.stdout.write(f"  ❌ Errors: {stats['errors']}")
        if completed_count > 0:
            self.stdout.write(f"  ✅ Interviews marked as COMPLETED: {completed_count}")
        self.stdout.write(self.style.SUCCESS('='*70 + '\n'))


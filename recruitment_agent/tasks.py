"""
Background tasks for automatic interview follow-up email checking.
This runs periodically to check for interviews that need follow-up emails.
"""

from django.utils import timezone
from datetime import timedelta
from .models import Interview
from .agents.interview_scheduling.interview_scheduling_agent import InterviewSchedulingAgent
from .log_service import LogService
import logging

logger = logging.getLogger(__name__)

# Initialize agent (singleton pattern)
_interview_agent = None
_log_service = None

def get_interview_agent():
    """Get or create interview agent instance"""
    global _interview_agent, _log_service
    if _interview_agent is None:
        _log_service = LogService()
        _interview_agent = InterviewSchedulingAgent(log_service=_log_service)
    return _interview_agent


def check_and_send_followup_emails():
    """
    Background task to automatically check and send follow-up emails.
    This should be called periodically (e.g., every hour via cron or celery).
    """
    try:
        agent = get_interview_agent()
        now = timezone.now()
        stats = {
            'followups_sent': 0,
            'reminders_sent': 0,
            'errors': 0,
        }
        
        # 1. Check PENDING interviews for follow-up emails
        pending_interviews = Interview.objects.filter(
            status='PENDING',
            invitation_sent_at__isnull=False
        ).exclude(
            status__in=['COMPLETED', 'CANCELLED']
        )
        
        for interview in pending_interviews:
            try:
                # Skip if interview is in the past
                if interview.scheduled_datetime and interview.scheduled_datetime < now:
                    continue
                
                # Get recruiter settings for timing
                followup_delay = interview.get_followup_delay_hours()
                max_followups = interview.get_max_followup_emails()
                min_between = interview.get_min_hours_between_followups()
                
                # Check if enough hours have passed (using recruiter preference)
                time_since_invitation = now - interview.invitation_sent_at
                if time_since_invitation < timedelta(hours=followup_delay):
                    continue
                
                # Check if we've sent max follow-ups (using recruiter preference)
                if interview.followup_count >= max_followups:
                    continue
                
                # Check if enough time has passed since last follow-up (using recruiter preference)
                if interview.last_followup_sent_at:
                    time_since_last = now - interview.last_followup_sent_at
                    if time_since_last < timedelta(hours=min_between):
                        continue
                
                # Send follow-up email
                logger.info(f"Auto-sending follow-up #{interview.followup_count + 1} for interview #{interview.id}")
                result = agent.send_followup_reminder(interview.id)
                if result.get('success'):
                    interview.followup_count += 1
                    interview.last_followup_sent_at = now
                    interview.save(update_fields=['followup_count', 'last_followup_sent_at'])
                    stats['followups_sent'] += 1
                    logger.info(f"Follow-up email sent successfully for interview #{interview.id}")
                else:
                    stats['errors'] += 1
                    logger.error(f"Failed to send follow-up for interview #{interview.id}: {result.get('error')}")
                    
            except Exception as e:
                stats['errors'] += 1
                logger.error(f"Error processing interview #{interview.id}: {str(e)}", exc_info=True)
        
        # 2. Check SCHEDULED interviews for pre-interview reminders
        scheduled_interviews = Interview.objects.filter(
            status='SCHEDULED',
            scheduled_datetime__isnull=False,
            scheduled_datetime__gt=now,  # Only future interviews
            pre_interview_reminder_sent_at__isnull=True  # Haven't sent reminder yet
        )
        
        for interview in scheduled_interviews:
            try:
                # Get recruiter settings for reminder timing
                reminder_hours = interview.get_reminder_hours_before()
                
                # Calculate reminder time (using recruiter preference)
                reminder_time = interview.scheduled_datetime - timedelta(hours=reminder_hours)
                time_until_reminder = (reminder_time - now).total_seconds()
                
                # Send if we're within 2 hours of reminder time
                if -7200 <= time_until_reminder <= 7200:
                    logger.info(f"Auto-sending pre-interview reminder for interview #{interview.id}")
                    reminder_hours = interview.get_reminder_hours_before()
                    result = agent.send_pre_interview_reminder(interview.id, hours_before=reminder_hours)
                    if result.get('success'):
                        interview.pre_interview_reminder_sent_at = now
                        interview.save(update_fields=['pre_interview_reminder_sent_at'])
                        stats['reminders_sent'] += 1
                        logger.info(f"Pre-interview reminder sent successfully for interview #{interview.id}")
                    else:
                        stats['errors'] += 1
                        logger.error(f"Failed to send reminder for interview #{interview.id}: {result.get('error')}")
                        
            except Exception as e:
                stats['errors'] += 1
                logger.error(f"Error processing scheduled interview #{interview.id}: {str(e)}", exc_info=True)
        
        # 3. Auto-mark past interviews as COMPLETED
        past_interviews = Interview.objects.filter(
            status__in=['SCHEDULED', 'PENDING'],
            scheduled_datetime__lt=now - timedelta(hours=2)
        ).exclude(
            status__in=['COMPLETED', 'CANCELLED']
        )
        
        completed_count = 0
        for interview in past_interviews:
            interview.status = 'COMPLETED'
            interview.save(update_fields=['status'])
            completed_count += 1
            logger.info(f"Auto-marked interview #{interview.id} as COMPLETED")
        
        logger.info(f"Follow-up email check completed: {stats['followups_sent']} follow-ups, "
                   f"{stats['reminders_sent']} reminders, {stats['errors']} errors, "
                   f"{completed_count} marked as completed")
        
        return stats
        
    except Exception as e:
        logger.error(f"Error in check_and_send_followup_emails: {str(e)}", exc_info=True)
        return {'followups_sent': 0, 'reminders_sent': 0, 'errors': 1}


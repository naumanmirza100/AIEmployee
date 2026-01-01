"""
Django signals for automatic interview follow-up email management.
Automatically checks and sends follow-up emails when interviews are created or updated.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from .models import Interview
from .agents.interview_scheduling.interview_scheduling_agent import InterviewSchedulingAgent
from .log_service import LogService
import logging
import threading

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


def _check_and_send_followup_async(interview_id):
    """Check and send follow-up email in background thread"""
    try:
        interview = Interview.objects.get(id=interview_id)
        agent = get_interview_agent()
        now = timezone.now()
        
        # Check for PENDING interviews that need follow-up
        if interview.status == 'PENDING' and interview.invitation_sent_at:
            time_since_invitation = now - interview.invitation_sent_at
            
            # Get recruiter settings for timing
            followup_delay = interview.get_followup_delay_hours()
            max_followups = interview.get_max_followup_emails()
            min_between = interview.get_min_hours_between_followups()
            
            # Check if enough hours have passed (using recruiter preference)
            if (time_since_invitation >= timedelta(hours=followup_delay) and 
                interview.followup_count < max_followups):
                
                # Check if enough time has passed since last follow-up (using recruiter preference)
                should_send = False
                if not interview.last_followup_sent_at:
                    should_send = True
                else:
                    time_since_last = now - interview.last_followup_sent_at
                    if time_since_last >= timedelta(hours=min_between):
                        should_send = True
                
                if should_send:
                    # Don't send if interview is in the past
                    if interview.scheduled_datetime and interview.scheduled_datetime < now:
                        return
                    
                    logger.info(f"🤖 Auto-sending follow-up email for interview #{interview.id}")
                    result = agent.send_followup_reminder(interview.id)
                    if result.get('success'):
                        interview.followup_count += 1
                        interview.last_followup_sent_at = now
                        interview.save(update_fields=['followup_count', 'last_followup_sent_at'])
                        logger.info(f"✅ Follow-up email sent successfully for interview #{interview.id}")
        
        # Check for SCHEDULED interviews that need reminder
        elif interview.status == 'SCHEDULED' and interview.scheduled_datetime:
            # Only for future interviews
            if interview.scheduled_datetime > now:
                # Get recruiter settings for reminder timing
                reminder_hours = interview.get_reminder_hours_before()
                
                # Check if reminder should be sent (using recruiter preference)
                reminder_time = interview.scheduled_datetime - timedelta(hours=reminder_hours)
                time_until_reminder = (reminder_time - now).total_seconds()
                
                # Send if we're within 2 hours of reminder time and haven't sent yet
                if (not interview.pre_interview_reminder_sent_at and 
                    -7200 <= time_until_reminder <= 7200):
                    
                    logger.info(f"🤖 Auto-sending pre-interview reminder for interview #{interview.id}")
                    reminder_hours = interview.get_reminder_hours_before()
                    result = agent.send_pre_interview_reminder(interview.id, hours_before=reminder_hours)
                    if result.get('success'):
                        interview.pre_interview_reminder_sent_at = now
                        interview.save(update_fields=['pre_interview_reminder_sent_at'])
                        logger.info(f"✅ Pre-interview reminder sent successfully for interview #{interview.id}")
        
        # Auto-mark past interviews as COMPLETED
        if (interview.status in ['SCHEDULED', 'PENDING'] and 
            interview.scheduled_datetime and 
            interview.scheduled_datetime < now - timedelta(hours=2)):
            interview.status = 'COMPLETED'
            interview.save(update_fields=['status'])
            logger.info(f"✅ Auto-marked interview #{interview.id} as COMPLETED (past interview)")
            
    except Interview.DoesNotExist:
        logger.warning(f"Interview #{interview_id} not found in background check")
    except Exception as e:
        logger.error(f"Error in background follow-up check for interview #{interview_id}: {str(e)}", exc_info=True)


@receiver(post_save, sender=Interview)
def auto_check_interview_followups(sender, instance, created, **kwargs):
    """
    Automatically check and send follow-up emails when interview is saved.
    Runs in background thread to avoid blocking the request.
    """
    # Run in background thread to avoid blocking
    thread = threading.Thread(target=_check_and_send_followup_async, args=(instance.id,))
    thread.daemon = True
    thread.start()


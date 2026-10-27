"""
Background tasks for automatic interview follow-up email checking.

`check_and_send_followup_emails` is the one sender of follow-ups and pre-interview reminders, run by Celery beat
every five minutes (`send_interview_followups`). There used to be three: a thread in the web server every 30
seconds, a thread two seconds after every invitation and a thread on every save of an interview, none of them
checking the others, so a booking a day ahead could get the same reminder two or three times (CO-185). Each email is
now claimed with a conditional update before it is sent, and the claim is undone if the send fails.
"""

from django.utils import timezone
from django.db import connection, close_old_connections
from django.db.utils import OperationalError
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


def reminder_due(interview, now) -> bool:
    """The reminder goes once the set time before the interview is reached, while it is still ahead (CO-116).

    It went only within two hours either side of that time, so a booking made a day ahead for an interview with a
    48-hour reminder never got one, and a move skipped it. It is not sent when under two hours remain, nor for a
    booking made inside the reminder period: the confirmation, just sent, says the same."""
    start = interview.scheduled_datetime - timedelta(hours=interview.get_reminder_hours_before())
    if now < start or interview.scheduled_datetime - now < timedelta(hours=2):
        return False
    booked = interview.confirmation_sent_at       # when it got its time (booked, or set by the recruiter)
    return not (booked and booked >= start)


def check_and_send_followup_emails():
    """
    Background task to automatically check and send follow-up emails.
    This should be called periodically (e.g., every hour via cron or celery).
    """
    try:
        # Close stale MSSQL connections before starting any DB work
        close_old_connections()

        agent = get_interview_agent()
        now = timezone.now()
        stats = {
            'followups_sent': 0,
            'reminders_sent': 0,
            'errors': 0,
        }

        logger.info(f"Starting follow-up email check at {now}")

        # Candidates are emailed only while the company's Recruitment
        # subscription is active (core/modules.py). An interview whose company
        # cannot be worked out is handled as before.
        from django.db.models import Q
        from core.modules import active_company_ids
        paying = active_company_ids('recruitment_agent')
        of_paying_company = (
            Q(company_user__company_id__in=paying)
            | Q(company_user__isnull=True, cv_record__job_description__company_id__in=paying)
            | Q(company_user__isnull=True, cv_record__job_description__company__isnull=True)
        )

        # 1. Check PENDING interviews for follow-up emails
        # Materialise with list() so the cursor is released before iteration begins
        pending_interviews = list(Interview.objects.filter(
            of_paying_company,
            status='PENDING',
            invitation_sent_at__isnull=False
        ).exclude(
            status__in=['COMPLETED', 'CANCELLED']
        ).select_related('cv_record__job_description', 'company_user', 'recruiter'))
        
        logger.info(f"Found {len(pending_interviews)} PENDING interviews to check")
        
        for interview in pending_interviews:
            try:
                # Skip if job's scheduling date range has expired
                if interview.is_job_schedule_expired():
                    logger.info(f"Skipping follow-up for interview #{interview.id} - job schedule date range expired")
                    continue
                # The recruiter turned automatic follow-ups off.
                if not interview.sends_followups():
                    continue

                # Skip if interview is in the past
                if interview.scheduled_datetime and interview.scheduled_datetime < now:
                    continue
                
                # Get recruiter settings for timing
                followup_delay = interview.get_followup_delay_hours()
                max_followups = interview.get_max_followup_emails()
                min_between = interview.get_min_hours_between_followups()
                
                # Check if enough hours have passed (using recruiter preference)
                time_since_invitation = now - interview.invitation_sent_at
                time_since_invitation_hours = time_since_invitation.total_seconds() / 3600
                
                if time_since_invitation < timedelta(hours=followup_delay):
                    continue
                
                # Check if we've sent max follow-ups (using recruiter preference)
                if interview.followup_count >= max_followups:
                    continue
                
                # Check if enough time has passed since last follow-up (using recruiter preference)
                if interview.last_followup_sent_at:
                    time_since_last = now - interview.last_followup_sent_at
                    time_since_last_hours = time_since_last.total_seconds() / 3600
                    if time_since_last < timedelta(hours=min_between):
                        continue
                
                # Claim it: only the run that moves the count on sends.
                count, last = interview.followup_count, interview.last_followup_sent_at
                if not Interview.objects.filter(pk=interview.pk, followup_count=count).update(
                        followup_count=count + 1, last_followup_sent_at=now):
                    continue
                logger.info(f"Auto-sending follow-up #{count + 1} for interview #{interview.id}")
                result = agent.send_followup_reminder(interview.id)
                if result.get('success'):
                    stats['followups_sent'] += 1
                    logger.info(f"Follow-up email sent successfully for interview #{interview.id}")
                else:
                    Interview.objects.filter(pk=interview.pk, followup_count=count + 1).update(
                        followup_count=count, last_followup_sent_at=last)
                    stats['errors'] += 1
                    logger.error(f"Failed to send follow-up for interview #{interview.id}: {result.get('error')}")
                    
            except Exception as e:
                stats['errors'] += 1
                logger.error(f"Error processing interview #{interview.id}: {str(e)}", exc_info=True)
        
        # 2. Check SCHEDULED interviews for pre-interview reminders
        scheduled_interviews = list(Interview.objects.filter(
            of_paying_company,
            status='SCHEDULED',
            scheduled_datetime__isnull=False,
            scheduled_datetime__gt=now,  # Only future interviews
            pre_interview_reminder_sent_at__isnull=True  # Haven't sent reminder yet
        ).select_related('cv_record__job_description', 'company_user', 'recruiter'))
        
        for interview in scheduled_interviews:
            try:
                # Skip if job's scheduling date range has expired
                if interview.is_job_schedule_expired():
                    logger.info(f"Skipping reminder for interview #{interview.id} - job schedule date range expired")
                    continue
                # The recruiter turned automatic reminders off.
                if not interview.sends_reminders():
                    continue

                if not reminder_due(interview, now):
                    continue
                # Claim it: only the run that stamps it sends.
                if not Interview.objects.filter(pk=interview.pk, pre_interview_reminder_sent_at__isnull=True).update(
                        pre_interview_reminder_sent_at=now):
                    continue
                logger.info(f"Auto-sending pre-interview reminder for interview #{interview.id}")
                result = agent.send_pre_interview_reminder(interview.id)
                if result.get('success'):
                    stats['reminders_sent'] += 1
                    logger.info(f"Pre-interview reminder sent successfully for interview #{interview.id}")
                else:
                    Interview.objects.filter(pk=interview.pk).update(pre_interview_reminder_sent_at=None)
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

try:
    from celery import shared_task
except Exception:  # pragma: no cover - celery optional in some envs
    shared_task = None


def _pipeline_digests_impl():
    from .pipeline_digest import send_pipeline_digests
    return send_pipeline_digests()


if shared_task is not None:
    @shared_task(name='recruitment_agent.tasks.send_interview_followups')
    def send_interview_followups():
        return check_and_send_followup_emails()

    @shared_task(name='recruitment_agent.tasks.send_pipeline_digests')
    def send_pipeline_digests():
        return _pipeline_digests_impl()
else:  # pragma: no cover
    def send_pipeline_digests():
        return _pipeline_digests_impl()

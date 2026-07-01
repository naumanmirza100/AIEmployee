"""
Celery periodic tasks — AI Executive Meeting Assistant
"""

import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


@shared_task(name='meeting_agent.send_meeting_reminders')
def send_meeting_reminders():
    """
    Run every 5 minutes.
    Create ExecNotification reminders for meetings starting within the next 15 minutes.
    """
    from meeting_agent.models import ExecutiveMeeting, ExecNotification
    now = timezone.now()
    window_end = now + timedelta(minutes=15)

    upcoming = ExecutiveMeeting.objects.filter(
        status='scheduled',
        scheduled_at__gte=now,
        scheduled_at__lte=window_end,
    ).select_related('organizer')

    created_count = 0
    for meeting in upcoming:
        already_notified = ExecNotification.objects.filter(
            company_user=meeting.organizer,
            notification_type='meeting_reminder',
            meeting=meeting,
            created_at__gte=now - timedelta(minutes=20),
        ).exists()
        if already_notified:
            continue

        minutes_until = max(0, int((meeting.scheduled_at - now).total_seconds() / 60))
        ExecNotification.objects.create(
            company_user=meeting.organizer,
            notification_type='meeting_reminder',
            severity='warning',
            title=f"Meeting in {minutes_until} min: {meeting.title}",
            message=f"Your meeting '{meeting.title}' starts in approximately {minutes_until} minutes.",
            meeting=meeting,
            data={
                'meeting_id': meeting.id,
                'scheduled_at': meeting.scheduled_at.isoformat(),
                'duration_minutes': meeting.duration_minutes,
            },
        )
        created_count += 1

        # Also notify accepted participants
        for participant in meeting.participants.filter(
            response__in=['accepted', 'tentative']
        ).select_related('company_user'):
            already_p = ExecNotification.objects.filter(
                company_user=participant.company_user,
                notification_type='meeting_reminder',
                meeting=meeting,
                created_at__gte=now - timedelta(minutes=20),
            ).exists()
            if not already_p:
                ExecNotification.objects.create(
                    company_user=participant.company_user,
                    notification_type='meeting_reminder',
                    severity='warning',
                    title=f"Meeting in {minutes_until} min: {meeting.title}",
                    message=f"Meeting '{meeting.title}' starts in approximately {minutes_until} minutes.",
                    meeting=meeting,
                    data={'meeting_id': meeting.id, 'scheduled_at': meeting.scheduled_at.isoformat()},
                )
                created_count += 1

    if created_count:
        logger.info("[ExecMeeting] send_meeting_reminders: created %d reminder notifications", created_count)
    return {'created': created_count}


@shared_task(name='meeting_agent.run_proactive_notifications')
def run_proactive_notifications():
    """
    Run every 15 minutes.
    For each active company user who has executive meeting data,
    run the ProactiveNotificationAgent to scan and create notifications.
    Keeps it lightweight — only runs for users with pending tasks or upcoming meetings.
    """
    from meeting_agent.models import ExecutiveMeeting, ExecutiveTask
    from core.models import CompanyUser

    now = timezone.now()

    # Find company users who have tasks or meetings that need attention
    user_ids_with_tasks = set(
        ExecutiveTask.objects.filter(
            status__in=['todo', 'in_progress'],
            due_date__lte=(now + timedelta(days=1)).date(),
        ).values_list('company_user_id', flat=True)[:200]
    )
    user_ids_with_meetings = set(
        ExecutiveMeeting.objects.filter(
            status='scheduled',
            scheduled_at__lte=now + timedelta(hours=24),
        ).values_list('organizer_id', flat=True)[:200]
    )

    target_user_ids = user_ids_with_tasks | user_ids_with_meetings
    if not target_user_ids:
        return {'scanned': 0, 'total_created': 0}

    active_users = CompanyUser.objects.filter(
        id__in=target_user_ids,
        is_active=True,
    ).select_related('company')[:100]

    total_created = 0
    for company_user in active_users:
        try:
            from meeting_agent.ai_agents import ProactiveNotificationAgent
            agent = ProactiveNotificationAgent(company_id=company_user.company_id)
            created = agent.scan_and_create_notifications(company_user.id)
            total_created += len(created)
        except Exception as e:
            logger.warning("[ExecMeeting] proactive scan failed for user %s: %s", company_user.id, e)

    logger.info("[ExecMeeting] run_proactive_notifications: scanned %d users, created %d notifications", len(active_users), total_created)
    return {'scanned': len(active_users), 'total_created': total_created}


@shared_task(name='meeting_agent.cleanup_old_notifications')
def cleanup_old_notifications():
    """
    Run daily.
    Delete read notifications older than 30 days to keep the table clean.
    """
    from meeting_agent.models import ExecNotification
    cutoff = timezone.now() - timedelta(days=30)
    deleted, _ = ExecNotification.objects.filter(is_read=True, created_at__lt=cutoff).delete()
    logger.info("[ExecMeeting] cleanup_old_notifications: deleted %d old read notifications", deleted)
    return {'deleted': deleted}


@shared_task(name='meeting_agent.mark_completed_meetings')
def mark_completed_meetings():
    """
    Run every 30 minutes.
    Mark meetings whose scheduled_at + duration has passed as 'completed'
    if they are still in 'scheduled' or 'in_progress' status.
    """
    from meeting_agent.models import ExecutiveMeeting
    from datetime import timedelta as td
    now = timezone.now()

    completed_count = 0
    for meeting in ExecutiveMeeting.objects.filter(status__in=['scheduled', 'in_progress']):
        meeting_end = meeting.scheduled_at + td(minutes=meeting.duration_minutes)
        if meeting_end < now:
            meeting.status = 'completed'
            meeting.save(update_fields=['status'])
            completed_count += 1

    if completed_count:
        logger.info("[ExecMeeting] mark_completed_meetings: marked %d meetings as completed", completed_count)
    return {'completed': completed_count}

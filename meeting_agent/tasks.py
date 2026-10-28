"""
Celery periodic tasks — AI Executive Meeting Assistant
"""

import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)

AGENT_MEETINGS = '/exec-meeting/dashboard?tab=meetings'


@shared_task(name='meeting_agent.send_meeting_reminders')
def send_meeting_reminders():
    """
    Run every 5 minutes.
    Create ExecNotification reminders for meetings starting within the next 15 minutes.
    """
    from meeting_agent.bell import ring
    from meeting_agent.clock import real_start, when_text
    from meeting_agent.models import ExecutiveMeeting, ExecNotification
    now = timezone.now()
    window_end = now + timedelta(minutes=15)

    # Times are kept as typed (meeting_agent.clock), so the query takes the widest offset either side and each
    # meeting is then held to its real start. Compared as stored, Karachi's reminders came five hours late (CO-210).
    from core.modules import active_company_ids
    candidates = ExecutiveMeeting.objects.filter(
        organizer__company_id__in=active_company_ids('exec_meeting_agent'),   # not for a lapsed agent
        status='scheduled',
        scheduled_at__gte=now - timedelta(hours=15),
        scheduled_at__lte=window_end + timedelta(hours=15),
    ).select_related('organizer__company')
    upcoming = [m for m in candidates if now <= real_start(m) <= window_end]

    created_count = 0
    for meeting in upcoming:
        already_notified = ExecNotification.objects.filter(
            company_user=meeting.organizer,
            notification_type='meeting_reminder',
            meeting=meeting,
            created_at__gte=now - timedelta(minutes=20),
        ).exists()

        minutes_until = max(0, int((real_start(meeting) - now).total_seconds() / 60))
        # Skipping the whole meeting once the organiser had a reminder left the people invited with none (CO-259).
        # Each reminder also reaches the bell (meeting_agent.bell): this agent's own page is not where anyone looks.
        when = when_text(meeting)
        if not already_notified:
            ring([meeting.organizer], title=f'Meeting in {minutes_until} min: {meeting.title}'[:255],
                 message=f"Your meeting '{meeting.title}' starts at {when}.", kind='exec_meeting_reminder',
                 link=AGENT_MEETINGS, severity='warning', data={'meeting_id': meeting.id})
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
                ring([participant.company_user], title=f'Meeting in {minutes_until} min: {meeting.title}'[:255],
                     message=f"'{meeting.title}' starts at {when}." + (
                         f' Join: {meeting.meeting_link}' if meeting.meeting_link else ''),
                     kind='exec_meeting_reminder', link=AGENT_MEETINGS, severity='warning',
                     data={'meeting_id': meeting.id})
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
    from meeting_agent.models import ExecutiveTask, MeetingActionItem
    from core.models import CompanyUser
    from core.modules import active_company_ids

    # Everyone with an open task due by tomorrow, or an open action item past due, in a company with the agent.
    # It took the first 200 rows across every company, then 100 people, so once the platform had more, most people
    # were never checked (CO-260). Tomorrow covers every company's clock; the scan uses its own today.
    companies = active_company_ids('exec_meeting_agent')
    soon = (timezone.now() + timedelta(days=1)).date()
    owners = set(ExecutiveTask.objects.filter(company_user__company_id__in=companies,
                                              status__in=['todo', 'in_progress', 'review'], due_date__lte=soon)
                 .order_by().values_list('company_user_id', flat=True).distinct())
    owners |= set(MeetingActionItem.objects.filter(meeting__organizer__company_id__in=companies,
                                                   status__in=['open', 'in_progress'], due_date__lte=soon)
                  .order_by().values_list('meeting__organizer_id', flat=True).distinct())
    if not owners:
        return {'scanned': 0, 'total_created': 0}

    scanned = total_created = 0
    from meeting_agent.ai_agents import ProactiveNotificationAgent
    for company_user in CompanyUser.objects.filter(id__in=owners, is_active=True).iterator(chunk_size=200):
        scanned += 1
        try:
            agent = ProactiveNotificationAgent(company_id=company_user.company_id)
            total_created += len(agent.scan_and_create_notifications(company_user.id))
        except Exception as e:
            logger.warning("[ExecMeeting] proactive scan failed for user %s: %s", company_user.id, e)

    logger.info("[ExecMeeting] run_proactive_notifications: scanned %d users, created %d notifications",
                scanned, total_created)
    return {'scanned': scanned, 'total_created': total_created}


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
    from meeting_agent.clock import real_end
    from meeting_agent.models import ExecutiveMeeting
    now = timezone.now()

    # Over when it really ends: west of UTC, comparing the typed time marked a meeting completed hours before it
    # started, which also took it off the shared calendar (CO-210).
    completed_count = 0
    for meeting in (ExecutiveMeeting.objects.filter(status__in=['scheduled', 'in_progress'])
                    .select_related('organizer__company')):
        if real_end(meeting) < now:
            meeting.status = 'completed'
            meeting.save(update_fields=['status'])
            completed_count += 1

    if completed_count:
        logger.info("[ExecMeeting] mark_completed_meetings: marked %d meetings as completed", completed_count)
    return {'completed': completed_count}

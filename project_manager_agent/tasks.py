"""
Celery tasks for the Project Manager Agent.
Includes meeting reminders and other scheduled tasks.
"""

from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(name='project_manager_agent.send_meeting_reminders')
def send_meeting_reminders():
    """
    Send reminders for upcoming meetings.
    Runs every 5 minutes. Sends:
    - 1-hour reminder (55-65 min before meeting)
    - 15-minute reminder (10-20 min before meeting)
    """
    from project_manager_agent.models import ScheduledMeeting, MeetingParticipant
    from core.models import Notification
    from project_manager_agent.models import PMNotification
    from django.core.mail import send_mail
    from django.conf import settings as django_settings

    now = timezone.now()
    from_email = getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')

    # Find meetings happening in the next 65 minutes that are accepted/pending
    upcoming = ScheduledMeeting.objects.filter(
        proposed_time__gt=now,
        proposed_time__lte=now + timedelta(minutes=65),
        status__in=['accepted', 'pending', 'partially_accepted'],
    ).select_related('organizer', 'invitee').prefetch_related('participants__user')

    reminders_sent = 0

    for meeting in upcoming:
        minutes_until = (meeting.proposed_time - now).total_seconds() / 60
        time_display = meeting.proposed_time.strftime('%I:%M %p')

        # Determine reminder type
        if 55 <= minutes_until <= 65:
            reminder_type = '1hr'
            reminder_text = f"in 1 hour (at {time_display})"
        elif 10 <= minutes_until <= 20:
            reminder_type = '15min'
            reminder_text = f"in 15 minutes (at {time_display})"
        else:
            continue

        # Check if we already sent this reminder (use meeting.description as a simple flag)
        # We'll use a JSONField-safe approach by checking existing notifications
        reminder_key = f"meeting_reminder_{meeting.id}_{reminder_type}"

        # Notify organizer (CompanyUser)
        already_notified_organizer = PMNotification.objects.filter(
            company_user=meeting.organizer,
            data__contains={'reminder_key': reminder_key},
        ).exists()

        if not already_notified_organizer:
            PMNotification.objects.create(
                company_user=meeting.organizer,
                notification_type='custom',
                severity='info',
                title=f"Meeting Reminder: {meeting.title}",
                message=f'Your meeting "{meeting.title}" starts {reminder_text}.',
                data={'meeting_id': meeting.id, 'type': 'meeting_reminder', 'reminder_key': reminder_key},
            )
            # Email organizer
            try:
                send_mail(
                    subject=f"Reminder: {meeting.title} starts {reminder_text}",
                    message=f'Your meeting "{meeting.title}" starts {reminder_text}.',
                    from_email=from_email,
                    recipient_list=[meeting.organizer.email],
                    fail_silently=True,
                )
            except Exception:
                pass
            reminders_sent += 1

        # Notify each participant (project User)
        for participant in meeting.participants.filter(status__in=['accepted', 'pending']):
            already_notified = Notification.objects.filter(
                user=participant.user,
                type='meeting_reminder',
                link=reminder_key,
            ).exists()

            if not already_notified:
                Notification.objects.create(
                    user=participant.user,
                    type='meeting_reminder',
                    notification_type='meeting_request',
                    title=f"Meeting Reminder: {meeting.title}",
                    message=f'Meeting "{meeting.title}" starts {reminder_text}.',
                    link=reminder_key,
                )
                # Email participant
                if participant.user.email:
                    try:
                        send_mail(
                            subject=f"Reminder: {meeting.title} starts {reminder_text}",
                            message=f'Meeting "{meeting.title}" starts {reminder_text}.',
                            from_email=from_email,
                            recipient_list=[participant.user.email],
                            fail_silently=True,
                        )
                    except Exception:
                        pass
                reminders_sent += 1

    logger.info(f"[MEETING REMINDERS] Sent {reminders_sent} reminders for {upcoming.count()} upcoming meetings")
    return {'reminders_sent': reminders_sent}


@shared_task(name='project_manager_agent.check_stale_meetings')
def check_stale_meetings():
    """
    Check for stale meeting requests (pending for 48+ hours).
    Sends a reminder after 48h, auto-withdraws after 7 days.
    Runs daily.
    """
    from project_manager_agent.models import ScheduledMeeting, PMNotification
    from core.models import Notification
    from django.core.mail import send_mail
    from django.conf import settings as django_settings

    now = timezone.now()
    from_email = getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')

    stale_48h = ScheduledMeeting.objects.filter(
        status='pending',
        created_at__lte=now - timedelta(hours=48),
        created_at__gt=now - timedelta(days=7),
    ).select_related('organizer', 'invitee').prefetch_related('participants__user')

    reminders_sent = 0
    for meeting in stale_48h:
        reminder_key = f"stale_reminder_{meeting.id}"
        # Check if we already sent this reminder
        already_sent = PMNotification.objects.filter(
            company_user=meeting.organizer,
            data__contains={'reminder_key': reminder_key},
        ).exists()
        if already_sent:
            continue

        # Notify organizer
        pending_names = [
            p.user.get_full_name() or p.user.username
            for p in meeting.participants.filter(status='pending')
        ]
        if not pending_names:
            continue

        PMNotification.objects.create(
            company_user=meeting.organizer,
            notification_type='custom',
            severity='warning',
            title=f"No Response: {meeting.title}",
            message=f'No response for "{meeting.title}" from {", ".join(pending_names)} after 48 hours. Consider sending a reminder or withdrawing.',
            data={'meeting_id': meeting.id, 'type': 'stale_meeting', 'reminder_key': reminder_key},
        )

        # Send reminder to pending participants
        for p in meeting.participants.filter(status='pending'):
            Notification.objects.create(
                user=p.user,
                type='meeting_reminder',
                notification_type='meeting_request',
                title=f"Pending Meeting: {meeting.title}",
                message=f'Reminder: {meeting.organizer.full_name} is waiting for your response to "{meeting.title}".',
                action_url=f'/meetings/{meeting.id}/respond',
            )
        reminders_sent += 1

    # Auto-withdraw meetings older than 7 days with no response
    auto_withdrawn = 0
    very_stale = ScheduledMeeting.objects.filter(
        status='pending',
        created_at__lte=now - timedelta(days=7),
    ).select_related('organizer', 'invitee').prefetch_related('participants__user')

    for meeting in very_stale:
        meeting.status = 'withdrawn'
        meeting.save(update_fields=['status', 'updated_at'])

        PMNotification.objects.create(
            company_user=meeting.organizer,
            notification_type='custom',
            severity='info',
            title=f"Meeting Auto-Withdrawn: {meeting.title}",
            message=f'"{meeting.title}" was automatically withdrawn after 7 days with no response.',
            data={'meeting_id': meeting.id, 'type': 'auto_withdrawn'},
        )
        for p in meeting.participants.all():
            Notification.objects.create(
                user=p.user,
                type='meeting_withdrawn',
                notification_type='meeting_request',
                title=f"Meeting Withdrawn: {meeting.title}",
                message=f'The meeting "{meeting.title}" has been automatically withdrawn due to no response.',
            )
        auto_withdrawn += 1

    logger.info(f"[STALE MEETINGS] Sent {reminders_sent} stale reminders, auto-withdrew {auto_withdrawn} meetings")
    return {'reminders_sent': reminders_sent, 'auto_withdrawn': auto_withdrawn}


@shared_task(name='project_manager_agent.cleanup_old_notifications')
def cleanup_old_notifications():
    """
    Clean up old notifications to prevent database bloat.
    - Delete read PMNotifications older than 30 days
    - Delete read User Notifications older than 30 days
    - Keep max 200 notifications per user (delete oldest beyond that)
    Runs daily.
    """
    from project_manager_agent.models import PMNotification
    from core.models import Notification

    now = timezone.now()
    cutoff = now - timedelta(days=30)

    # Clean old read PM notifications
    pm_deleted = PMNotification.objects.filter(
        is_read=True, created_at__lt=cutoff
    ).delete()[0]

    # Clean old read user notifications
    user_deleted = Notification.objects.filter(
        is_read=True, created_at__lt=cutoff
    ).delete()[0]

    # Cap per-user PM notifications at 200
    from django.db.models import Subquery, OuterRef
    from core.models import CompanyUser
    pm_capped = 0
    for cu in CompanyUser.objects.all():
        notif_ids = PMNotification.objects.filter(
            company_user=cu
        ).order_by('-created_at').values_list('id', flat=True)[200:]
        if notif_ids:
            count = PMNotification.objects.filter(id__in=list(notif_ids)).delete()[0]
            pm_capped += count

    logger.info(f"[NOTIFICATION CLEANUP] Deleted: {pm_deleted} PM, {user_deleted} User notifications (30d+). Capped: {pm_capped}")
    return {'pm_deleted': pm_deleted, 'user_deleted': user_deleted, 'pm_capped': pm_capped}

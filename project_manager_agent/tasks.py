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
        # M-F1 — render local time in the meeting's timezone, not the server's.
        # `meeting.timezone_name` defaults to UTC; reminders previously formatted
        # in whatever the worker process happened to use, mis-leading recipients
        # about when the meeting actually starts in their wall clock.
        try:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            tz_name = (getattr(meeting, 'timezone_name', None) or 'UTC').strip() or 'UTC'
            try:
                local_dt = meeting.proposed_time.astimezone(ZoneInfo(tz_name))
                tz_label = tz_name
            except (ZoneInfoNotFoundError, Exception):
                local_dt = meeting.proposed_time
                tz_label = 'UTC'
            time_display = f"{local_dt.strftime('%I:%M %p')} {tz_label}"
        except Exception:
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
            from project_manager_agent.notifications import dispatch_pm_notification
            dispatch_pm_notification(
                company_user=meeting.organizer,
                notification_type='custom',
                severity='info',
                title=f"Meeting Reminder: {meeting.title}",
                message=f'Your meeting "{meeting.title}" starts {reminder_text}.',
                data={'meeting_id': meeting.id, 'type': 'meeting_reminder', 'reminder_key': reminder_key},
                context={
                    'meeting_title': meeting.title,
                    'reminder_text': reminder_text,
                    'time_display': time_display,
                },
                extra_emails=[meeting.organizer.email] if meeting.organizer.email else [],
            )
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

        from project_manager_agent.notifications import dispatch_pm_notification
        dispatch_pm_notification(
            company_user=meeting.organizer,
            notification_type='custom',
            severity='warning',
            title=f"No Response: {meeting.title}",
            message=f'No response for "{meeting.title}" from {", ".join(pending_names)} after 48 hours. Consider sending a reminder or withdrawing.',
            data={'meeting_id': meeting.id, 'type': 'stale_meeting', 'reminder_key': reminder_key},
            context={
                'meeting_title': meeting.title,
                'pending_names': ', '.join(pending_names),
            },
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

        from project_manager_agent.notifications import dispatch_pm_notification
        dispatch_pm_notification(
            company_user=meeting.organizer,
            notification_type='custom',
            severity='info',
            title=f"Meeting Auto-Withdrawn: {meeting.title}",
            message=f'"{meeting.title}" was automatically withdrawn after 7 days with no response.',
            data={'meeting_id': meeting.id, 'type': 'auto_withdrawn'},
            context={'meeting_title': meeting.title},
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


def _advance_recurrence_date(rec):
    """Compute the next run date for a TaskRecurrence after generating one."""
    from datetime import timedelta as _td
    cur = rec.next_run_date
    if rec.frequency == 'daily':
        return cur + _td(days=max(1, rec.interval))
    if rec.frequency == 'weekly':
        # If weekdays are specified, pick the next matching weekday across `interval` weeks.
        if rec.weekdays.strip():
            try:
                wanted = sorted({int(w) for w in rec.weekdays.split(',') if w.strip() != ''})
            except ValueError:
                wanted = []
            if wanted:
                # Look ahead up to 7 * interval days
                step = 1
                horizon = 7 * max(1, rec.interval)
                while step <= horizon:
                    candidate = cur + _td(days=step)
                    if candidate.weekday() in wanted:
                        return candidate
                    step += 1
        return cur + _td(weeks=max(1, rec.interval))
    if rec.frequency == 'monthly':
        # Add N months — clamp day if the target month is shorter.
        n = max(1, rec.interval)
        year = cur.year + (cur.month - 1 + n) // 12
        month = (cur.month - 1 + n) % 12 + 1
        # Clamp day
        import calendar as _cal
        day = min(cur.day, _cal.monthrange(year, month)[1])
        from datetime import date as _date
        return _date(year, month, day)
    # Fallback
    return cur + _td(days=1)


@shared_task(name='project_manager_agent.generate_recurring_tasks')
def generate_recurring_tasks():
    """
    Materialise pending recurring task occurrences (T-F2).
    Runs daily. For every active TaskRecurrence whose `next_run_date` is on or
    before today, clones the template task as a new Task with status='todo' and
    advances the recurrence schedule.
    """
    from core.models import TaskRecurrence, Task
    from django.db import transaction

    today = timezone.localdate()
    generated = 0
    deactivated = 0

    active_recurrences = TaskRecurrence.objects.filter(
        is_active=True, next_run_date__lte=today,
    ).select_related('template_task', 'template_task__project', 'template_task__assignee')

    for rec in active_recurrences:
        # Cap-by-end-date
        if rec.ends_on and rec.next_run_date > rec.ends_on:
            rec.is_active = False
            rec.save(update_fields=['is_active', 'updated_at'])
            deactivated += 1
            continue
        if rec.max_occurrences is not None and rec.count_generated >= rec.max_occurrences:
            rec.is_active = False
            rec.save(update_fields=['is_active', 'updated_at'])
            deactivated += 1
            continue

        template = rec.template_task
        try:
            with transaction.atomic():
                from datetime import datetime as _dt, time as _time
                # New occurrence due_date = the planned run date at end-of-day in local time.
                due_dt = timezone.make_aware(
                    _dt.combine(rec.next_run_date, _time(hour=23, minute=59)),
                    timezone.get_current_timezone(),
                )
                new_task = Task.objects.create(
                    title=template.title,
                    description=template.description,
                    project=template.project,
                    assignee=template.assignee,
                    status='todo',
                    priority=template.priority,
                    due_date=due_dt,
                    estimated_hours=template.estimated_hours,
                )
                rec.count_generated += 1
                rec.last_generated_on = rec.next_run_date
                rec.next_run_date = _advance_recurrence_date(rec)
                # Re-check cutoff after advancing
                if rec.ends_on and rec.next_run_date > rec.ends_on:
                    rec.is_active = False
                if rec.max_occurrences is not None and rec.count_generated >= rec.max_occurrences:
                    rec.is_active = False
                rec.save(update_fields=[
                    'count_generated', 'last_generated_on', 'next_run_date', 'is_active', 'updated_at',
                ])
                generated += 1
        except Exception as exc:
            logger.exception(f"[RECURRING TASKS] Failed to generate from recurrence {rec.id}: {exc}")

    logger.info(f"[RECURRING TASKS] Generated {generated} new tasks; deactivated {deactivated} recurrences")
    return {'generated': generated, 'deactivated': deactivated}


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


# --------------------------------------------------------------------------
# Project Pilot async pipeline
# --------------------------------------------------------------------------

@shared_task(name='project_manager_agent.run_project_pilot_job',
             bind=True, max_retries=1, default_retry_delay=30)
def run_project_pilot_job(self, job_id):
    """Run a ProjectPilotJob end-to-end: extract text → LLM → create Project/
    Task rows. Stamps results back onto the job row so the frontend polling
    endpoint can pick them up.

    The pipeline itself is unchanged — this task is just an async wrapper
    around `run_project_pilot_pipeline`. The upload endpoint saves the file
    to disk, creates the job row, and enqueues this task; the browser then
    polls `/project-pilot/jobs/<id>/status` until `status='ready'`.
    """
    import os
    import time
    from pathlib import Path
    from django.conf import settings

    from project_manager_agent.models import ProjectPilotJob
    from project_manager_agent.project_pilot_pipeline import run_project_pilot_pipeline

    job = ProjectPilotJob.objects.filter(id=job_id).first()
    if not job:
        logger.warning("run_project_pilot_job: job %s not found", job_id)
        return {'status': 'not_found', 'job_id': job_id}

    if job.status not in ('queued', 'processing'):
        # Someone already worked on this job (retry raced?). Skip.
        logger.info("run_project_pilot_job: job %s already %s, skipping",
                    job_id, job.status)
        return {'status': job.status, 'job_id': job_id}

    _t_overall = time.time()
    timing_ms = {}
    job.status = 'processing'
    job.save(update_fields=['status', 'updated_at'])

    try:
        # 1. Load the file from disk and extract text.
        # `file_path` is stored relative to MEDIA_ROOT.
        from api.views.pm_agent import _extract_text_from_file
        _t = time.time()
        abs_path = Path(settings.MEDIA_ROOT) / job.file_path
        if not abs_path.exists():
            raise FileNotFoundError(f"Upload disappeared: {job.file_path}")

        # `_extract_text_from_file` expects a file-like object with `.name`,
        # `.size`, `.seek`, `.read`, and (for docx) `.chunks`. Wrap the
        # on-disk file so we can pass it in.
        with open(abs_path, 'rb') as fh:
            _wrapper = _DiskFileWrapper(fh, job.file_name, abs_path.stat().st_size)
            extracted_text = _extract_text_from_file(_wrapper)
        timing_ms['text_extract_ms'] = int((time.time() - _t) * 1000)

        # 2. Reload company_user (Celery worker doesn't share request state).
        from core.models import CompanyUser
        company_user = CompanyUser.objects.filter(id=job.company_user_id).first()
        if not company_user:
            raise ValueError(f"CompanyUser {job.company_user_id} not found")

        # 3. Run the pipeline (LLM + action execution).
        _t = time.time()
        result = run_project_pilot_pipeline(
            company_user=company_user,
            extracted_text=extracted_text,
            file_name=job.file_name,
            user_prompt=job.user_prompt or '',
            project_id=job.project_id,
            chat_history=job.chat_history or [],
        )
        timing_ms['pipeline_ms'] = int((time.time() - _t) * 1000)
        timing_ms['total_ms'] = int((time.time() - _t_overall) * 1000)

        # 4. Stamp results onto the job.
        job.answer = result.get('answer', '') or ''
        job.action_results = result.get('action_results', []) or []
        job.cannot_do = result.get('cannot_do', '') or ''
        job.timing_ms = timing_ms
        job.status = 'ready'
        job.completed_at = timezone.now()
        job.save()
        logger.info("run_project_pilot_job: job %s done, %d action_results, timing_ms=%s",
                    job_id, len(job.action_results), timing_ms)
        return {'status': 'ready', 'job_id': job_id}

    except Exception as exc:
        logger.exception("run_project_pilot_job: job %s failed", job_id)
        try:
            job.status = 'failed'
            job.error_message = f"{type(exc).__name__}: {exc}"[:2000]
            job.timing_ms = {**timing_ms, 'total_ms': int((time.time() - _t_overall) * 1000)}
            job.completed_at = timezone.now()
            job.save(update_fields=['status', 'error_message', 'timing_ms',
                                    'completed_at', 'updated_at'])
        except Exception:
            logger.exception("run_project_pilot_job: also failed to stamp 'failed' on job %s",
                             job_id)
        return {'status': 'failed', 'job_id': job_id}


class _DiskFileWrapper:
    """Adapter to expose an on-disk file with the interface Django's
    `UploadedFile` uses — so `_extract_text_from_file` can be called from
    the Celery task without changing its signature.

    Only implements the methods the extraction function actually uses:
    `.name`, `.size`, `.seek`, `.read`, `.chunks` (docx branch).
    """
    def __init__(self, fh, name, size):
        self._fh = fh
        self.name = name
        self.size = size

    def seek(self, pos):
        return self._fh.seek(pos)

    def read(self, n=-1):
        return self._fh.read(n) if n != -1 else self._fh.read()

    def chunks(self, chunk_size=64 * 1024):
        while True:
            data = self._fh.read(chunk_size)
            if not data:
                break
            yield data

"""A place to meet for a Project Manager meeting, made once everyone invited has accepted.

The executive scheduler gives each meeting a Jitsi link and a Join button. Project Manager's meetings had none:
people agreed a time and then had nowhere to meet. Asked for on 25 Oct 2026, the way it works here:

- The link is made when the meeting is final, that is when every person invited has accepted
  (`ScheduledMeeting.update_overall_status`, or the organiser accepting a time someone suggested). Not before.
- Everyone is told then, in the app and by email: the meeting is on, here is the link, please join five minutes
  before the start. Each attendee gets a notice of their own; the organiser gets it in the notice of the reply that
  completed the meeting (`organiser_note`), so that is one notice, not two.
- Five minutes before the start the reminder job (`tasks.send_meeting_reminders`) sends the link again.

A meeting that is moved and accepted again keeps its link; everyone is told the new time with it.
"""
from __future__ import annotations

import logging
import secrets
import string

logger = logging.getLogger(__name__)

JOIN_EARLY_MINUTES = 5
MEETINGS_PAGE = '/me/meetings'


def new_link():
    slug = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(12))
    return f'https://meet.jit.si/payperproject-{slug}'


def join_early_text(meeting):
    return f'Join here: {meeting.meeting_link} — please join {JOIN_EARLY_MINUTES} minutes before the start.'


def organiser_note(meeting):
    """What the organiser's notice of a reply adds when that reply made the meeting final."""
    if meeting.status == 'accepted' and meeting.meeting_link:
        return f' Everyone has accepted. {join_early_text(meeting)}'
    return ''


def on_final(meeting):
    """Everyone has accepted: give the meeting its link (it keeps one it has) and tell everyone. Never raises:
    telling people must not undo the acceptance that caused it."""
    try:
        if not meeting.meeting_link:
            meeting.meeting_link = new_link()
            meeting.save(update_fields=['meeting_link', 'updated_at'])
        _announce(meeting)
    except Exception:
        logger.exception('Could not give meeting %s its link', meeting.pk)


def _announce(meeting):
    from core.models import Notification
    from core.scheduling import when_text

    when = when_text(meeting.proposed_time, meeting.timezone_name)
    title = f'Meeting confirmed: {meeting.title}'
    message = f'Everyone has accepted "{meeting.title}" on {when}. {join_early_text(meeting)}'
    for participant in meeting.participants.select_related('user'):
        user = participant.user
        Notification.objects.create(
            user=user, type='meeting_confirmed', notification_type='meeting_request',
            title=title, message=message, action_url=MEETINGS_PAGE,
        )
        if user.email:
            _email(user.email, meeting, when)


def _email(address, meeting, when):
    from django.conf import settings
    from django.core.mail import EmailMultiAlternatives
    from django.utils.html import escape

    link = escape(meeting.meeting_link)
    html = f"""
    <h2>Meeting confirmed</h2>
    <p>Everyone has accepted <strong>{escape(meeting.title)}</strong>.</p>
    <p><strong>When:</strong> {escape(when)} ({meeting.duration_minutes} minutes)</p>
    <div style="margin:22px 0;">
      <a href="{link}" style="background:#059669;color:#fff;text-decoration:none;padding:12px 26px;
         border-radius:8px;font-weight:600;display:inline-block;">Join meeting</a>
    </div>
    <p style="color:#374151;">Please join {JOIN_EARLY_MINUTES} minutes before the start.</p>
    <p style="color:#6b7280;font-size:12px;word-break:break-all;">{link}</p>
    """
    try:
        mail = EmailMultiAlternatives(
            subject=f'Meeting confirmed: {meeting.title}',
            body=f'Everyone has accepted "{meeting.title}" on {when}. {join_early_text(meeting)}',
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'), to=[address])
        mail.attach_alternative(html, 'text/html')
        mail.send(fail_silently=True)
    except Exception as exc:
        logger.warning('Meeting link email to %s failed: %s', address, exc)

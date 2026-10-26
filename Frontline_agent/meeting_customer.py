"""The customer of a Frontline call: their invitation, any change, and the reminders.

Frontline's meetings are calls with a customer, but only staff were invited: the customer was a line in the
description and was told nothing — no invitation, no link, no reminder. Staff got two reminders by email only.

Now, as Project Manager's and HR's meetings:
- the customer (`customer_email`) is emailed the invitation with the time in the meeting's zone, the link to join and
  a calendar file; and is told when the call is moved or cancelled;
- everyone, staff and customer, is reminded a day, an hour, 15 minutes and 5 minutes before, each saying how many
  minutes are really left, with the link (Frontline_agent.tasks.send_meeting_reminders).

A customer is never asked to accept: there is no screen for them to answer on. The link is made when the call is
booked, as before.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: (stamp, minutes before, (early, late)): the reminder is sent when the call is that far off, give or take.
REMINDERS = (
    ('reminder_24h_sent_at', 24 * 60, (3, 2)),
    ('reminder_60m_sent_at', 60, (5, 5)),
    ('reminder_15m_sent_at', 15, (5, 5)),
    ('reminder_5m_sent_at', 5, (3, 3)),
)


def when_text(meeting):
    from core.scheduling import when_text as _when_text
    return _when_text(meeting.scheduled_at, meeting.timezone_name)


def time_left(minutes_left):
    """'in 3 hours', 'in 14 minutes': the real time left (the job runs every five minutes, so a "15-minute" reminder
    can go out with 11 left)."""
    if minutes_left >= 120:
        return f'in {round(minutes_left / 60)} hours'
    n = max(1, round(minutes_left))
    return f'in {n} minute{"" if n == 1 else "s"}'


def join_text(meeting):
    from project_manager_agent.meeting_links import JOIN_EARLY_MINUTES
    if not meeting.meeting_link:
        return ''
    return f'Join here: {meeting.meeting_link} — please join {JOIN_EARLY_MINUTES} minutes before the start.'


def reminder_text(meeting, minutes_left):
    """'"Call with Gulberg Bakehouse" starts in 14 minutes (at Tuesday, October 27, 2026 at 03:00 PM Asia/Karachi).'
    and the link to join."""
    text = f'"{meeting.title}" starts {time_left(minutes_left)} (at {when_text(meeting)}).'
    join = join_text(meeting)
    return f'{text} {join}' if join else text


def _company_name(meeting):
    return (getattr(meeting.company, 'name', '') or '').strip() or 'our team'


def _sender(meeting):
    from django.conf import settings
    company = meeting.company
    from_email = ((getattr(company, 'support_from_email', '') or '').strip()
                  or getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'))
    return from_email, (getattr(company, 'support_from_email', '') or '').strip() or None


def calendar_file(meeting, cancel=False):
    """The call as an .ics file for the customer's own calendar."""
    from datetime import timedelta
    from django.utils import timezone
    from project_manager_agent.ics_generator import _escape, _format_dt
    start = meeting.scheduled_at
    end = start + timedelta(minutes=meeting.duration_minutes or 30)
    description = join_text(meeting) or (meeting.description or '')
    lines = [
        'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//PayPerProject//Frontline//EN',
        f'METHOD:{"CANCEL" if cancel else "REQUEST"}', 'BEGIN:VEVENT',
        f'UID:frontline-meeting-{meeting.id}@aiemployee.app', f'DTSTAMP:{_format_dt(timezone.now())}',
        f'DTSTART:{_format_dt(start)}', f'DTEND:{_format_dt(end)}',
        f'SUMMARY:{_escape(meeting.title)}', f'DESCRIPTION:{_escape(description)}',
    ]
    if meeting.meeting_link:
        lines.append(f'LOCATION:{_escape(meeting.meeting_link)}')
    lines += [f'STATUS:{"CANCELLED" if cancel else "CONFIRMED"}', 'END:VEVENT', 'END:VCALENDAR']
    return '\r\n'.join(lines) + '\r\n'


def _send(meeting, subject, heading, lines, *, button=True, cancel=False):
    from django.core.mail import EmailMultiAlternatives
    from django.utils.html import escape
    to = (meeting.customer_email or '').strip()
    if not to:
        return False
    from_email, reply_to = _sender(meeting)
    name = (meeting.customer_name or '').strip()
    hello = f'Hello {name},' if name else 'Hello,'
    text = '\n\n'.join([hello, *lines, f'— {_company_name(meeting)}'])
    link = escape(meeting.meeting_link or '')
    html = (f'<p>{escape(hello)}</p>' + ''.join(f'<p>{escape(line)}</p>' for line in lines)
            + (f'<div style="margin:22px 0;"><a href="{link}" style="background:#059669;color:#fff;'
               'text-decoration:none;padding:12px 26px;border-radius:8px;font-weight:600;display:inline-block;">'
               'Join the call</a></div>' if button and meeting.meeting_link and not cancel else '')
            + f'<p>— {escape(_company_name(meeting))}</p>')
    email = EmailMultiAlternatives(subject=subject, body=text, from_email=from_email, to=[to],
                                   reply_to=[reply_to] if reply_to else None)
    email.attach_alternative(f'<h2>{escape(heading)}</h2>{html}', 'text/html')
    if meeting.scheduled_at:
        email.attach('call.ics', calendar_file(meeting, cancel=cancel), 'text/calendar')
    email.send(fail_silently=False)
    return True


def tell_customer(meeting, what):
    """Email the customer that the call was `booked`, `moved` or `cancelled`. After the save is committed; never
    raises. A call with no customer address tells nobody."""
    if not (meeting.customer_email or '').strip():
        return False
    from django.db import transaction
    company = _company_name(meeting)
    length = f' ({meeting.duration_minutes} minutes)' if meeting.duration_minutes else ''
    if what == 'cancelled':
        subject, heading = f'Cancelled: {meeting.title}', 'Call cancelled'
        lines = [f'{company} has cancelled "{meeting.title}", which was {when_text(meeting)}.',
                 'Reply to this email if you would like another time.']
    elif what == 'moved':
        subject, heading = f'New time: {meeting.title}', 'Call moved'
        lines = [f'{company} has moved "{meeting.title}". It is now {when_text(meeting)}{length}.']
    else:
        subject, heading = f'Call booked: {meeting.title}', 'Call booked'
        lines = [f'{company} has booked "{meeting.title}" with you for {when_text(meeting)}{length}.']
    if what != 'cancelled':
        join = join_text(meeting)
        if join:
            lines.append(join)
        lines.append('The attached calendar file adds it to your calendar. You will get a reminder before it '
                     'starts.')

    def send():
        try:
            _send(meeting, subject, heading, lines, cancel=what == 'cancelled')
        except Exception:
            logger.exception('Frontline meeting %s: the customer was not emailed (%s)', meeting.pk, what)

    transaction.on_commit(send)
    return True


def remind_customer(meeting, minutes_left):
    """The customer's reminder; False when there is nobody to send it to."""
    if not (meeting.customer_email or '').strip():
        return False
    lines = [reminder_text(meeting, minutes_left)]
    return _send(meeting, f'Reminder: {meeting.title} starts {time_left(minutes_left)}', 'Reminder', lines)

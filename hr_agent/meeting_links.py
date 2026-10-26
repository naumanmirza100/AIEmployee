"""An HR meeting's place to meet, its confirmation and its reminders' wording, as Project Manager's
(project_manager_agent/meeting_links.py).

HR had a link field that nothing filled: people agreed a time and had nowhere to meet, nobody was told when everyone
had accepted, and the reminders came only by email, a day and a quarter of an hour before. Asked for on 26 Oct 2026,
"make it like that of pm too, with meeting link, and reminder, and all":

- When every person invited has accepted (`HRMeeting.update_response_status`, or HR accepting a time someone
  suggested), the meeting gets a Jitsi link, unless one was typed in, and every attendee is told in their bell and
  by email, with a Join button and "please join 5 minutes before the start".
- The organiser's side hears it in the notice of the reply that completed the meeting (`organiser_note`): the
  dashboard login that booked it (`booked_by`), the organizer's own login, or else the company's HR admins.
- The reminder job (`tasks.send_hr_meeting_reminders`) says how many minutes are left, and the link.
"""
from __future__ import annotations

import logging

from project_manager_agent.meeting_links import JOIN_EARLY_MINUTES, MEETINGS_PAGE, join_early_text, new_link

logger = logging.getLogger(__name__)

__all__ = ['JOIN_EARLY_MINUTES', 'MEETINGS_PAGE', 'is_final', 'organiser_note', 'organiser_logins', 'on_final',
           'join_note']


def is_final(meeting):
    """Everyone has accepted and the meeting is still on."""
    return meeting.response_status == 'accepted' and meeting.status in ('scheduled', 'rescheduled')


def organiser_note(meeting):
    """What the organiser's notice of a reply adds when that reply made the meeting final."""
    if is_final(meeting) and meeting.meeting_link:
        return f' Everyone has accepted. {join_early_text(meeting)}'
    return ''


def join_note(meeting, *, last_reminder=False):
    """The link line of a reminder: "Join now" in the last one, "please join early" before, once everyone has
    accepted; a link typed in by hand is given as it is."""
    if not meeting.meeting_link:
        return ''
    if is_final(meeting):
        return (f' Join now: {meeting.meeting_link}' if last_reminder
                else f' Please join {JOIN_EARLY_MINUTES} minutes early: {meeting.meeting_link}')
    return f' Meeting link: {meeting.meeting_link}'


def organiser_logins(meeting):
    """Who to tell on the organiser's side: ([dashboard logins], [employee logins]). The login that booked it and
    the organizer's own (their dashboard login if they have one, else their employee login); the company's HR admins
    when there is neither."""
    from hr_agent.alerts import hr_admins
    from hr_agent.handover import dashboard_login
    company_users, employees = [], []
    if meeting.booked_by_id and meeting.booked_by.is_active:
        company_users.append(meeting.booked_by)
    organizer = meeting.organizer if meeting.organizer_id else None
    if organizer is not None:
        own = dashboard_login(organizer)
        if own is not None:
            if own.pk != meeting.booked_by_id:
                company_users.append(own)
        elif organizer.user_id:
            employees.append(organizer.user)
    if not company_users and not employees:
        company_users = hr_admins(meeting.company_id)
    return company_users, employees


def attendee_logins(meeting, *, include_declined=False):
    """The employee logins of the people invited (not the organizer)."""
    rows = meeting.participant_rows.select_related('employee__user')
    return [row.employee.user for row in rows
            if row.employee.user_id and (include_declined or row.status != 'rejected')]


def on_final(meeting):
    """Everyone has accepted: give the meeting its link (it keeps one it has) and tell every attendee. Never raises:
    telling people must not undo the acceptance that caused it."""
    try:
        if not meeting.meeting_link:
            meeting.meeting_link = new_link()
            meeting.save(update_fields=['meeting_link', 'updated_at'])
        _announce(meeting)
    except Exception:
        logger.exception('Could not give HR meeting %s its link', meeting.pk)


def _announce(meeting):
    from django.db import transaction

    from core.notification_utils import notify_employees
    from core.scheduling import when_text
    from project_manager_agent.meeting_links import _email

    when = when_text(meeting.scheduled_at, meeting.timezone_name)
    title = f'Meeting confirmed: {meeting.title}'
    message = f'Everyone has accepted "{meeting.title}" on {when}. {join_early_text(meeting)}'
    people = attendee_logins(meeting)
    notify_employees(people, title=title, message=message, link=MEETINGS_PAGE, kind='hr_meeting_confirmed')
    for user in people:
        address = (user.email or '').strip()
        if address and not address.lower().endswith('.invalid'):
            # After the reply is saved: nobody is emailed about an acceptance that was rolled back.
            transaction.on_commit(lambda a=address: _email(a, meeting, when))

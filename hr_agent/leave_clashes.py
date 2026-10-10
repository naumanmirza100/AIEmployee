"""What a leave request lands on: the meetings and interviews the person is
already booked into on those days.

Approving leave used to change the request and the balance, and nothing else.
The bookings stayed as they were, the approver saw no warning, and whoever ran
those meetings found out when the person did not turn up. The shared calendar
only refused *new* bookings from then on.

`booked_during` is what the approval dialog shows before the decision, and what
is looked at again when the decision is saved. `tell_organisers` then tells
whoever runs each meeting. Nothing here moves or cancels a meeting.
"""
from __future__ import annotations

import logging

from core.scheduling.conflicts import clock_label, find_conflicts, when_label, zone_info
from core.scheduling.sources import SOURCES

logger = logging.getLogger(__name__)

#: Where each agent's meetings are managed, for the organiser's alert.
SCREENS = {
    'pm': '/project-manager/dashboard?tab=meeting-scheduler',
    'hr': '/hr/dashboard?tab=meetings',
    'frontline': '/frontline/dashboard',
    'recruitment': '/recruitment/interviews',
}
#: A month of leave can cover dozens of bookings; this many are listed and alerted for.
LIMIT = 20


def why_not_checked(leave_request) -> str:
    """'' when the person's calendar can be looked through. Otherwise why not:
    'no_login' (only an employee login has a calendar) or 'hours' (leave of a
    few hours does not say which hours)."""
    if leave_request.partial_day_period == 'hours':
        return 'hours'
    if not leave_request.employee_id or not leave_request.employee.user_id:
        return 'no_login'
    return ''


def booked_during(leave_request, *, reveal_private=False) -> list:
    """Every meeting and interview the person is booked into while this leave
    runs, soonest first, as `Clash` rows. Their other leave is left out, and so
    is this request itself.

    Private bookings keep their titles to themselves: an HR meeting shows its
    title only to an HR admin (`reveal_private`), and an interview's title,
    which names the candidate, to nobody here.
    """
    if why_not_checked(leave_request):
        return []
    starts, ends = SOURCES['leave'].window(leave_request)
    clashes = find_conflicts([leave_request.employee.user_id], starts, ends,
                             viewer_source='hr', reveal_private=reveal_private)
    return [c for c in clashes if c.source != 'leave']


def rows(clashes, tz_name='UTC') -> list[dict]:
    """The clashes as the approval dialog lists them, times on `tz_name`'s clock."""
    zone = zone_info(tz_name)
    out = []
    for clash in clashes[:LIMIT]:
        s, e = clash.starts_at.astimezone(zone), clash.ends_at.astimezone(zone)
        out.append({
            'source': clash.source,
            'meeting_id': clash.source_id,
            'kind': clash.source_label,
            'title': clash.title,
            'when': f"{s:%a %d %b}, {clock_label(s)}–{clock_label(e)}",
            'starts_at': clash.starts_at.isoformat(),
            'ends_at': clash.ends_at.isoformat(),
        })
    return out


def _runs_it(source, meeting, company_id):
    """Whoever runs a meeting, as (their dashboard login or None, their
    employee login or None, what the meeting is called to them)."""
    from hr_agent.handover import company_user_for_login, dashboard_login

    if source == 'pm':
        return meeting.organizer, None, f'"{meeting.title}"'
    if source == 'hr':
        organizer = meeting.organizer
        if organizer is None:
            return None, None, f'"{meeting.title}"'
        login = dashboard_login(organizer)
        return login, organizer.user, f'"{meeting.title}"'
    if source == 'frontline':
        user = meeting.organizer
        return company_user_for_login(user, company_id), user, f'"{meeting.title}"'
    if source == 'recruitment':
        login = meeting.company_user or (
            company_user_for_login(meeting.recruiter, company_id) if meeting.recruiter_id else None)
        return login, meeting.recruiter, f'the interview with {meeting.candidate_name}'
    return None, None, 'a meeting'


def tell_organisers(leave_request, clashes) -> int:
    """Once leave is approved: tell whoever runs each meeting it lands on, in
    their bell, once for each meeting. Someone who runs meetings from My Space
    only is told there, and by email. The person going on leave is not told
    about their own meetings. Returns how many alerts went out; never raises.
    """
    from core.notification_utils import notify_company_users, notify_employees
    from hr_agent.alerts import leave_dates
    from hr_agent.handover import dashboard_login

    try:
        emp = leave_request.employee
        own_login = dashboard_login(emp)
        own_login_id = own_login.id if own_login is not None else None
        told = 0
        # One person's calendar holds each meeting once, so one row is one meeting.
        for clash in clashes[:LIMIT]:
            meeting = SOURCES[clash.source].model.objects.filter(pk=clash.source_id).first()
            if meeting is None:
                continue
            login, user, name = _runs_it(clash.source, meeting, emp.company_id)
            zone = getattr(meeting, 'timezone_name', '') or emp.zone
            title = f"{emp.full_name} will be on leave during a meeting you run"
            message = (f"{emp.full_name} is on leave {leave_dates(leave_request)} and is booked into {name}, "
                       f"{when_label(clash.starts_at, zone)}. The meeting has not been changed: "
                       "move it, or go ahead without them.")
            if login is not None and login.is_active:
                if login.id != own_login_id:
                    told += notify_company_users([login], title=title, message=message, severity='warning',
                                                 link=SCREENS.get(clash.source), kind='hr_leave_clash')
            elif user is not None and user.pk != emp.user_id:
                told += notify_employees([user], title=title, message=message, link='/me/meetings',
                                         kind='hr_leave_clash', email_subject=title)
        return told
    except Exception:
        logger.exception("Could not tell organisers about leave request %s", getattr(leave_request, 'pk', None))
        return 0

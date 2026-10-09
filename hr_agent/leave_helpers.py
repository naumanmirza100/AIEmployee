"""Leave / holiday helpers — pure functions, no DB writes here.

* ``working_days_between(start, end, company)`` — counts weekdays in
  ``[start, end]`` minus any matching ``Holiday`` rows for the company.
* ``resolve_approver_for_leave(employee, company)`` — picks the ``Employee``
  to approve a request: the asker's ``manager`` if they have a dashboard login
  to decide it with, otherwise None (the HR admins decide).
"""
from __future__ import annotations

from datetime import date as _date, timedelta


def working_days_between(start: _date, end: _date, company) -> float:
    """Inclusive working-day count between ``start`` and ``end`` for the
    company, excluding weekends + matching company Holiday rows.

    A ``Holiday`` with ``is_working_day=True`` reverses the rule (lets HR
    mark a bridge day as a working day even though it's around an official
    holiday).
    """
    if not start or not end or end < start:
        return 0.0

    from hr_agent.models import Holiday  # local — avoids app-load loops

    # Pull all holidays once for the [start, end] window.
    holidays = {
        h.date: bool(h.is_working_day)
        for h in Holiday.objects.filter(
            company=company, date__gte=start, date__lte=end,
        ).only('date', 'is_working_day')
    }

    days = 0
    cursor = start
    while cursor <= end:
        weekday = cursor.weekday()  # Mon=0 ... Sun=6
        is_weekend = weekday >= 5
        # Holiday on a weekend doesn't add — only matters on a weekday.
        # Holiday flagged is_working_day=True overrides "this is a holiday day off".
        if cursor in holidays:
            # explicit override
            if holidays[cursor]:  # is_working_day = True
                days += 1
            # else: it's a holiday — skip
        elif not is_weekend:
            days += 1
        cursor += timedelta(days=1)
    return float(days)


def can_decide_leave(employee) -> bool:
    """Can this person decide a leave request? Deciding one, and seeing the
    leave screens at all, takes a dashboard login that is switched on: theirs
    by the link on their HR record, or by their work address."""
    from core.models import CompanyUser

    if employee is None or not employee.company_id:
        return False
    if employee.company_user_id:
        return bool(employee.company_user.is_active)
    email = (employee.work_email or '').strip()
    return bool(email) and CompanyUser.objects.filter(
        company_id=employee.company_id, email__iexact=email, is_active=True).exists()


def resolve_approver_for_leave(employee, company):
    """Who a leave request is sent to: the asker's manager, if they can decide
    it. Otherwise nobody (``None``).

    A request with no approver is put before the HR admins: it is on their My
    work list and under "All" on the leave screen. A request sent to a manager
    with only a My Space login used to wait on nobody's list. The older
    fall-backs (an HR login, then any login at all) are gone: they looked a
    login up through its HR record, so they could name a colleague who is
    neither the manager nor in HR.
    """
    if not employee or not company or not employee.manager_id:
        return None
    manager = employee.manager
    return manager if can_decide_leave(manager) else None


_PART_LABELS = {'morning': 'morning', 'afternoon': 'afternoon', 'hours': 'part of the day'}


def leave_label(start: _date, end: _date, part: str = '') -> str:
    """'On leave 6–10 Oct', 'On leave 6 Oct (morning)'."""
    if start == end:
        text = f"On leave {start.day} {start:%b}"
    elif (start.year, start.month) == (end.year, end.month):
        text = f"On leave {start.day}–{end.day} {end:%b}"
    else:
        text = f"On leave {start.day} {start:%b}–{end.day} {end:%b}"
    if part in _PART_LABELS:
        text += f" ({_PART_LABELS[part]})"
    return text


def approved_leave_by_login(user_ids, from_date: _date, to_date: _date) -> dict:
    """{login user id: [{start, end, part, label}]} — approved leave of the
    employees behind these logins that overlaps [from_date, to_date].

    Only approved leave: a pending request may still be turned down. Used to
    warn before giving someone work due while they're away.
    """
    from hr_agent.models import LeaveRequest

    ids = [int(u) for u in user_ids if u]
    if not ids:
        return {}
    rows = (LeaveRequest.objects
            .filter(status='approved', employee__user_id__in=ids,
                    start_date__lte=to_date, end_date__gte=from_date)
            .values_list('employee__user_id', 'start_date', 'end_date', 'partial_day_period')
            .order_by('start_date'))
    out: dict = {}
    for user_id, start, end, part in rows:
        out.setdefault(user_id, []).append({
            'start': start.isoformat(), 'end': end.isoformat(), 'part': part or '',
            'label': leave_label(start, end, part or ''),
        })
    return out

"""Leave / holiday helpers — pure functions, no DB writes here.

* ``working_days_between(start, end, company)`` — counts weekdays in
  ``[start, end]`` minus any matching ``Holiday`` rows for the company.
* ``resolve_approver_for_leave(employee, company)`` — picks the right
  ``Employee`` to approve a request: the asker's ``manager`` if set,
  otherwise the first HR-roled CompanyUser's Employee, otherwise None.
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


def resolve_approver_for_leave(employee, company):
    """Pick the right Employee to approve a leave request.

    Order of preference:
      1. The asker's direct manager (``Employee.manager``).
      2. Any active company user with the ``hr_agent`` role,
         mapped to their backing Employee row.
      3. The first active CompanyUser of the company (last-resort fallback).

    Returns an ``Employee`` instance (the approver) or ``None``.
    """
    from core.models import CompanyUser
    from hr_agent.models import Employee

    if not employee or not company:
        return None
    if employee.manager_id:
        return employee.manager

    # HR-roled approver
    hr_user = CompanyUser.objects.filter(
        company=company, is_active=True, role='hr_agent',
    ).first()
    if hr_user:
        emp = Employee.objects.filter(company=company, company_user=hr_user).first()
        if emp:
            return emp

    # Last-resort — any active company user, prefer non-self.
    fallback = (CompanyUser.objects
                .filter(company=company, is_active=True)
                .exclude(pk=getattr(employee.company_user, 'pk', None))
                .first())
    if fallback:
        emp = Employee.objects.filter(company=company, company_user=fallback).first()
        if emp:
            return emp
    return None


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

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

"""Whose clock a person's leave is read on, and keeping the calendar right when
that changes.

Leave is recorded in days and half days. The shared calendar works in hours,
so it has to know when the person's day starts. It reads `Employee.zone`: the
record's own time zone, or the company's when the record has none.

Every record used to start as 'UTC', which nobody had chosen. For someone in
Karachi left on that default, an afternoon off blocked 6 pm to 5 am their
time, so a meeting at 3 pm that afternoon was accepted. New records now start
blank and follow the company. The ones made before still say 'UTC', and one
that was chosen cannot be told from one that was only the default, so they are
moved across only when an HR admin asks (`follow_company`).

A change of zone moves leave that is already approved. It is moved here, at
once, not left to the nightly rebuild of the calendar.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

#: What every record was given before a record's zone could be blank.
OLD_DEFAULT = 'UTC'


def resync_leave(employee_ids) -> int:
    """Rewrite the calendar rows of these people's approved leave that has not
    ended, at the hours their zone now gives. Returns how many requests."""
    from core.scheduling.sync import safe_sync
    from hr_agent.models import LeaveRequest

    ids = [int(e) for e in employee_ids if e]
    if not ids:
        return 0
    recent = timezone.now().date() - timedelta(days=1)
    requests = (LeaveRequest.objects
                .filter(employee_id__in=ids, status='approved', end_date__gte=recent)
                .select_related('employee__company'))
    count = 0
    for request in requests.iterator(chunk_size=200):
        safe_sync('leave', request)
        count += 1
    return count


def on_old_default(company):
    """Records still on the zone they were given before a record could follow
    the company: the ones `follow_company` would change."""
    from hr_agent.models import Employee
    return Employee.objects.filter(company=company, timezone_name=OLD_DEFAULT)


def following(company):
    """Records with no zone of their own."""
    from hr_agent.models import Employee
    return Employee.objects.filter(company=company, timezone_name='')


def follow_company(company) -> int:
    """Move every record still on the old default onto the company's zone, and
    their approved leave with them. Only on request: see the note above."""
    ids = list(on_old_default(company).values_list('id', flat=True))
    if ids:
        from hr_agent.models import Employee
        Employee.objects.filter(pk__in=ids).update(timezone_name='', updated_at=timezone.now())
        resync_leave(ids)
    return len(ids)


def set_company_zone(company, name) -> None:
    """Set the company's time zone to `name`: a valid IANA name, or '' for
    "not set". Everyone who follows it has their approved leave moved, and so
    have the company's executive meetings, whose typed times are read on it."""
    company.timezone_name = name
    company.save(update_fields=['timezone_name'])
    resync_leave(following(company).values_list('id', flat=True))
    try:
        from meeting_agent.clock import resync_company
        resync_company(company)
    except Exception:
        logger.exception("could not move the executive meetings of company %s to its new time zone", company.pk)


def summary(company) -> dict:
    """What the leave screen says about the company's clock."""
    from core.scheduling import zone_name
    return {
        'company_zone': zone_name(company.timezone_name, default=''),
        'following': following(company).count(),
        'on_old_default': on_old_default(company).count(),
        'old_default': OLD_DEFAULT,
    }

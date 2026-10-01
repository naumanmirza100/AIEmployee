"""Who should take a customer who's waiting for a person?

A hand-off used to go to a shared queue with nobody's availability in view:
whoever noticed it took it, and it could sit there while the one person free
to answer was the one not looking. This suggests the best-placed colleague —
it never assigns on its own; one click in the queue does:

  1. not busy right now on the shared calendar — no meeting, interview or
     approved leave in progress (core.scheduling, the same calendar every
     agent books against);
  2. on the Frontline team (role `frontline_agent`) before anyone else;
  3. the fewest open tickets.
"""
from __future__ import annotations

from django.db.models import Count
from django.utils import timezone

FRONTLINE_ROLES = ('frontline_agent',)
OPEN_STATUSES = ('new', 'open', 'in_progress')


def suggest_assignee(company, *, now=None) -> dict | None:
    """{id, name, reason, open_tickets} of the company login to suggest, or
    None when nobody is available."""
    from core.models import CalendarBlock, CompanyUser
    from core.scheduling.identity import login_user_id_for_company_user
    from Frontline_agent.models import Ticket

    now = now or timezone.now()
    candidates = list(CompanyUser.objects.filter(company=company, is_active=True))
    if not candidates:
        return None

    # Their calendar identity (employee login) for busy time, and the login
    # Frontline stores on tickets, can differ; each is looked up as it's used.
    calendar_login = {cu.id: login_user_id_for_company_user(cu) for cu in candidates}
    busy_now = set(CalendarBlock.objects
                   .filter(user_id__in=[u for u in calendar_login.values() if u],
                           starts_at__lte=now, ends_at__gt=now)
                   .values_list('user_id', flat=True))
    load = dict(Ticket.objects
                .filter(company=company, status__in=OPEN_STATUSES,
                        assigned_to_id__in=[cu.login_user_id for cu in candidates if cu.login_user_id])
                .values_list('assigned_to_id').annotate(n=Count('id')))

    ranked = []
    for cu in candidates:
        if calendar_login[cu.id] in busy_now:
            continue
        on_team = cu.role in FRONTLINE_ROLES
        ranked.append((0 if on_team else 1, load.get(cu.login_user_id, 0), (cu.full_name or cu.email).lower(), cu))
    if not ranked:
        return None
    ranked.sort(key=lambda r: r[:3])
    team_rank, open_tickets, _, cu = ranked[0]

    reasons = [f"{open_tickets} open ticket{'' if open_tickets == 1 else 's'}"]
    if team_rank == 0:
        reasons.append('on the Frontline team')
    reasons.append('free right now' if calendar_login[cu.id] else 'no calendar to check')
    return {'id': cu.id, 'name': cu.full_name or cu.email, 'reason': ', '.join(reasons),
            'open_tickets': open_tickets}

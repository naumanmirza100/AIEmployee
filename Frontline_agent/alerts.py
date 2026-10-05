"""Frontline events that need someone, sent to the bell of the logins who act.

A customer asking for a person, or a ticket given to someone, used to raise
nothing in the app; the only in-app notifications Frontline wrote came from
its old template views, into a table company logins never read. These go to
the company feed via `core.notification_utils`.
"""
from __future__ import annotations

from django.core.cache import cache

from core.models import CompanyUser
from core.notification_utils import notify_company_users

#: Who hears about a customer waiting for a person: the company's admins,
#: plus anyone given the Frontline agent role. The hand-off queue itself stays
#: open to every login.
HANDOFF_ALERT_ROLES = ('owner', 'admin', 'frontline_agent')

_HANDOFF_WHY = {
    'customer_requested': 'The customer asked for a person.',
    'low_confidence': "The AI couldn't find a reliable answer.",
    'manual_escalation': 'It was escalated by an agent.',
    'sla_risk': 'It is at risk of missing its response time.',
}


def handoff_requested(ticket):
    if not ticket.company_id:
        return 0
    recipients = CompanyUser.objects.filter(company_id=ticket.company_id, is_active=True,
                                            role__in=HANDOFF_ALERT_ROLES)
    # The suggestion is extra: it must never stop the hand-off being raised.
    try:
        from Frontline_agent.routing import suggest_assignee
        best = suggest_assignee(ticket.company)
    except Exception:
        best = None
    who = f" Best placed: {best['name']} ({best['reason']})." if best else ''
    return notify_company_users(
        recipients,
        title=f"Customer waiting for a person: {ticket.title[:120]}",
        message=f"{_HANDOFF_WHY.get(ticket.handoff_reason, '')}{who} Take it from Hand-offs.".strip(),
        link='/frontline/dashboard?tab=handoffs',
        severity='warning',
        kind='frontline_handoff',
    )


def widget_cannot_answer(company, reason=''):
    """The website chat could not use the AI: tokens used up, the key refused,
    or the agent switched off. Visitors are told to try again later, so without
    this nobody at the company would know. Once an hour per company at most:
    every visitor message hits the same wall."""
    if not cache.add(f'frontline-widget-cannot-answer:{company.id}', 1, 3600):
        return 0
    recipients = CompanyUser.objects.filter(company_id=company.id, is_active=True,
                                            role__in=HANDOFF_ALERT_ROLES)
    return notify_company_users(
        recipients,
        title='Your website chat cannot answer visitors',
        message=(f"{reason} " if reason else '') + (
            'Visitors are told to try again later. Anyone who asks for a person still reaches Hand-offs.'),
        link='/company/settings/api-keys',
        severity='critical',
        kind='frontline_widget_cannot_answer',
    )


def tickets_assigned(tickets, assignee, actor=None):
    """One alert, however many tickets — a bulk assignment of twenty would
    otherwise bury everything else in the bell. Nothing when you assign a
    ticket to yourself."""
    tickets = list(tickets)
    assigned_self = isinstance(actor, CompanyUser) and actor.pk == getattr(assignee, 'pk', None)
    if not tickets or assignee is None or assigned_self:
        return 0
    if len(tickets) == 1:
        t = tickets[0]
        title = f"Ticket assigned to you: #{t.id} {t.title[:120]}"
        message = f"Priority: {t.get_priority_display()}."
    else:
        title = f"{len(tickets)} tickets assigned to you"
        message = ', '.join(f"#{t.id}" for t in tickets[:10]) + (' …' if len(tickets) > 10 else '')
    return notify_company_users([assignee], title=title, message=message,
                                link='/frontline/dashboard?tab=tickets',
                                kind='frontline_ticket_assigned')

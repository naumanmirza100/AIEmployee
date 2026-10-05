"""Frontline events that need someone, sent to the bell of the logins who act.

A customer asking for a person, or a ticket given to someone, used to raise
nothing in the app; the only in-app notifications Frontline wrote came from
its old template views, into a table company logins never read. These go to
the company feed via `core.notification_utils`.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from django.core.cache import cache
from django.utils import timezone

from core.models import CompanyUser
from core.notification_utils import notify_company_users

#: Who hears about a customer waiting for a person: the company's admins,
#: plus anyone given the Support (Frontline agent) role. The hand-off queue
#: itself stays open to every login.
HANDOFF_ALERT_ROLES = ('owner', 'admin', 'frontline_agent')


def handoff_recipients(company_id):
    """The logins to tell about a customer waiting for a person.

    Admins and the people given the Support role. A company that has given
    nobody that role has not said who handles support, so everyone is told:
    it used to be the admins alone, which in practice meant the founder's
    login and nobody else. Each login's own notification settings still apply.
    """
    logins = CompanyUser.objects.filter(company_id=company_id, is_active=True)
    if logins.filter(role='frontline_agent').exists():
        return logins.filter(role__in=HANDOFF_ALERT_ROLES)
    return logins


def hears_handoffs(company_user) -> bool:
    return bool(company_user and company_user.is_active
                and handoff_recipients(company_user.company_id).filter(pk=company_user.pk).exists())

HANDOFF_WHY = {
    'customer_requested': 'The customer asked for a person.',
    'low_confidence': "The AI couldn't find a reliable answer.",
    'manual_escalation': 'It was escalated by an agent.',
    'sla_risk': 'It is at risk of missing its response time.',
}


def handoff_requested(ticket):
    if not ticket.company_id:
        return 0
    recipients = handoff_recipients(ticket.company_id)
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
        message=f"{HANDOFF_WHY.get(ticket.handoff_reason, '')}{who} Take it from Hand-offs.".strip(),
        link='/frontline/dashboard?tab=handoffs',
        severity='warning',
        kind='frontline_handoff',
    )


#: A customer still waiting is raised again this often, for this long.
HANDOFF_REMIND_EVERY = timedelta(hours=1)
HANDOFF_REMIND_FOR = timedelta(hours=24)


def handoffs_still_waiting(now=None):
    """Raise the alert again for every hand-off nobody has taken.

    It used to be said once. If nobody was looking at that moment the customer
    simply waited. Repeats hourly for a day, per ticket; the ticket records
    when it was last said, so this is safe to run as often as you like.
    """
    from Frontline_agent.models import Ticket
    from core.modules import active_company_ids

    now = now or timezone.now()
    waiting = (Ticket.objects
               .filter(handoff_status='pending', company_id__in=active_company_ids('frontline_agent'),
                       handoff_requested_at__lte=now - HANDOFF_REMIND_EVERY,
                       handoff_requested_at__gte=now - HANDOFF_REMIND_FOR)
               .exclude(status__in=('resolved', 'closed'))
               .select_related('company'))
    reminded = 0
    for ticket in waiting:
        context = dict(ticket.handoff_context or {})
        last = context.get('reminded_at')
        if last and datetime.fromisoformat(last) > now - HANDOFF_REMIND_EVERY:
            continue
        minutes = int((now - ticket.handoff_requested_at).total_seconds() // 60)
        hours, rest = divmod(minutes, 60)
        waited = f"{hours} h {rest} min" if rest else f"{hours} h"
        notify_company_users(
            handoff_recipients(ticket.company_id),
            title=f"Still waiting for a person ({waited}): {ticket.title[:100]}",
            message=f"{HANDOFF_WHY.get(ticket.handoff_reason, '')} Nobody has taken it yet. Take it from Hand-offs.".strip(),
            link='/frontline/dashboard?tab=handoffs',
            severity='critical',
            kind='frontline_handoff',
        )
        context['reminded_at'] = now.isoformat()
        Ticket.objects.filter(pk=ticket.pk, handoff_status='pending').update(handoff_context=context)
        reminded += 1
    return reminded


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

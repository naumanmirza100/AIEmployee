"""The things that must move together when a ticket's status or SLA changes.

Every write path used to do its own version of this, and they disagreed:
`resolved_at` was stamped by a single endpoint and only when a resolution came
with it, the SLA clock was resumed by two paths that computed different
deadlines, and hand-offs were never released at all. See FL-DATA-11, -12 and
-15 in MDS/FRONTLINE_AGENT_AUDIT.md.

`apply_status_change` mutates the in-memory ticket and returns the field names
it touched, so it fits both `save(update_fields=...)` callers and bulk loops.
`after_status_change` runs the follow-ups that write on their own, so it goes
*after* the caller's save.
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = ('resolved', 'closed', 'auto_resolved')


def apply_status_change(ticket, new_status):
    """Move `ticket` to `new_status` and keep `resolved_at` honest.

    Returns the changed field names (empty when the status isn't actually
    changing, so callers can skip a pointless write).
    """
    new_status = (new_status or '').strip()
    old_status = ticket.status
    if not new_status or new_status == old_status:
        return []

    ticket.status = new_status
    changed = ['status']

    becomes_terminal = new_status in TERMINAL_STATUSES
    was_terminal = old_status in TERMINAL_STATUSES

    if becomes_terminal and not ticket.resolved_at:
        # Tickets closed from the grid used to land in a terminal status with
        # `resolved_at` still NULL, and the agent-performance report requires
        # both — so those agents showed zero resolved tickets (FL-DATA-11).
        ticket.resolved_at = timezone.now()
        changed.append('resolved_at')
    elif was_terminal and not becomes_terminal and ticket.resolved_at:
        # Reopened. A stale `resolved_at` made the ticket count as resolved
        # and open at the same time.
        ticket.resolved_at = None
        changed.append('resolved_at')

    return changed


def after_status_change(ticket):
    """Follow-ups a terminal status implies. Call this after the save.

    Separate from `apply_status_change` because each of these writes on its
    own: releasing the hand-off saves the ticket, and the survey creates a row
    and sends an email.
    """
    if ticket is None or ticket.status not in TERMINAL_STATUSES:
        return
    try:
        from Frontline_agent.handoff import resolve_handoff
        resolve_handoff(ticket)
    except Exception:
        logger.exception("resolve_handoff failed for ticket %s", getattr(ticket, 'id', None))
    try:
        from Frontline_agent.satisfaction import ensure_satisfaction_survey
        ensure_satisfaction_survey(ticket)
    except Exception:
        logger.exception("CSAT survey failed for ticket %s", getattr(ticket, 'id', None))


def resume_sla(ticket):
    """Resume a paused SLA clock, exactly once. Returns the seconds credited,
    or None when there was nothing to resume (or someone else got there first).

    Two things were wrong before (FL-DATA-12). The view read `sla_paused_at`,
    computed the paused duration and wrote it back without a lock, so a
    double-submitting tab credited the time twice and pushed the deadline out
    twice. And the inbound-email path credited the accumulator but did *not*
    move `sla_due_at`, so the same real event produced two different deadlines
    depending on which code ran — leaving the SLA dashboard and the escalation
    job working from different numbers.

    Moving the deadline is the canonical behaviour: if pausing the clock
    doesn't move the target, pausing means nothing.
    """
    from Frontline_agent.models import Ticket

    if ticket is None or not ticket.sla_paused_at:
        return None

    now = timezone.now()
    paused_for = max(0, int((now - ticket.sla_paused_at).total_seconds()))
    updates = {
        'sla_paused_at': None,
        'sla_paused_accumulated_seconds': (ticket.sla_paused_accumulated_seconds or 0) + paused_for,
        'updated_at': now,
    }
    if ticket.sla_due_at:
        updates['sla_due_at'] = ticket.sla_due_at + timedelta(seconds=paused_for)

    # Guarded: only the caller that still sees a paused clock credits the time.
    applied = (Ticket.objects
               .filter(pk=ticket.pk, sla_paused_at__isnull=False)
               .update(**updates))
    if not applied:
        return None

    for field, value in updates.items():
        setattr(ticket, field, value)
    return paused_for

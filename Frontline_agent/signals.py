"""
Signals for Frontline Agent.
Runs workflow triggers on ticket update (post_save) so any ticket update path fires triggers.
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Ticket

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Ticket)
def run_workflow_triggers_on_ticket_update(sender, instance, created, **kwargs):
    """
    When a ticket is updated (not created), run workflow triggers for ticket_updated.
    Uses lazy import to avoid circular import with api.views.frontline_agent.
    """
    if created:
        return
    if not getattr(instance, 'company_id', None):
        return
    try:
        from api.views.frontline_agent import _run_workflow_triggers
        user = getattr(instance, 'created_by', None)
        if not user:
            logger.warning("Ticket %s has no created_by, skipping workflow triggers", instance.id)
            return
        _run_workflow_triggers(
            instance.company_id,
            'ticket_updated',
            instance,
            executed_by_user=user,
            old_status=None,
        )
    except Exception as e:
        logger.exception("run_workflow_triggers_on_ticket_update failed: %s", e)

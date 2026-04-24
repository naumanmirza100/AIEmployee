"""
Signals for Frontline Agent.
Runs workflow triggers on ticket update (post_save) so any ticket update path fires triggers.
Also mirrors Contact rows to HubSpot when the tenant has the integration enabled.
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Ticket, Contact

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Ticket)
def run_workflow_triggers_on_ticket_update(sender, instance, created, **kwargs):
    """
    When a ticket is updated (not created), run workflow triggers for ticket_updated.
    Uses lazy import to avoid circular import with api.views.frontline_agent.

    Re-entrancy guard: if we're already inside a workflow run (the workflow's
    own `update_ticket` step is writing), skip. Without this guard a workflow
    that modifies the ticket it was triggered by can loop — only the trigger
    condition no longer matching stops it today, which is luck, not a contract.
    """
    if created:
        return
    if not getattr(instance, 'company_id', None):
        return
    # Check for re-entrancy *before* any DB work so we don't even spin up the view import.
    try:
        from .workflow_context import is_workflow_executing, current_workflow_id
        if is_workflow_executing():
            logger.debug(
                "Ticket %s post_save skipped: already inside workflow %s",
                instance.id, current_workflow_id(),
            )
            return
    except Exception:
        # If the guard module fails to import, fail open (old behaviour) rather than
        # dropping all signals. The next code path will still run.
        logger.exception("workflow_context guard import failed — proceeding without guard")
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


@receiver(post_save, sender=Contact)
def mirror_contact_to_hubspot(sender, instance, created, **kwargs):
    """Fan-out: push Contact changes to HubSpot when the tenant opted in.

    Dispatches a Celery job — keeps the request path fast and isolates CRM
    outages from our own writes. We deliberately fire on both create and
    update so downstream edits (name, phone, tags) flow through.
    """
    try:
        company = getattr(instance, 'company', None)
        if not company:
            return
        cfg = getattr(company, 'hubspot_config', None) or {}
        if not cfg.get('enabled') or not cfg.get('access_token'):
            return
        # Avoid recursion: the sync task itself saves `external_id`/`external_synced_at`
        # on the Contact, which fires this signal again. Detect that case by
        # checking `update_fields` — the sync only updates those three fields plus updated_at.
        update_fields = kwargs.get('update_fields') or set()
        sync_cols = {'external_source', 'external_id', 'external_synced_at', 'updated_at'}
        if update_fields and set(update_fields).issubset(sync_cols):
            return
        from Frontline_agent.tasks import sync_contact_to_hubspot
        sync_contact_to_hubspot.delay(instance.id)
    except Exception as e:
        logger.exception("mirror_contact_to_hubspot dispatch failed: %s", e)

"""Django signals that trigger CRM sync on SDR model changes."""
from __future__ import annotations

import logging
import threading

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _get_agent(company):
    from crm_sync_agent.agents.crm_sync_agent import CRMSyncAgent
    return CRMSyncAgent(company)


def _has_active_integrations(company) -> bool:
    from crm_sync_agent.models import CRMIntegration
    return CRMIntegration.objects.filter(company=company, is_active=True).exists()


def _process_async(company):
    """Process pending queue in a background thread (no Celery needed)."""
    def _run():
        try:
            _get_agent(company).process_pending(limit=20)
        except Exception:
            logger.exception('CRM background process error (company=%s)', getattr(company, 'pk', '?'))
    threading.Thread(target=_run, daemon=True).start()


def _company_from_lead(lead):
    """SDRLead belongs to a CompanyUser; traverse to Company."""
    try:
        return lead.company_user.company
    except Exception:
        return None


# ------------------------------------------------------------------ #
# SDR Lead — sync contact on create / update
# ------------------------------------------------------------------ #

@receiver(post_save, sender='ai_sdr_agent.SDRLead')
def on_sdr_lead_saved(sender, instance, created, **kwargs):
    try:
        # Sync leads that have at least some identifying info (email OR linkedin OR name)
        has_identity = instance.email or instance.linkedin_url or instance.full_name or instance.first_name
        if not has_identity:
            return
        company = _company_from_lead(instance)
        if not company:
            return
        if not _has_active_integrations(company):
            return
        _get_agent(company).enqueue_sdr_lead(instance)
        _process_async(company)
    except Exception:
        logger.exception('CRM signal error on SDRLead save (lead=%s)', getattr(instance, 'pk', '?'))


# ------------------------------------------------------------------ #
# SDR Outreach Log — log email activity on successful send
# ------------------------------------------------------------------ #

@receiver(post_save, sender='ai_sdr_agent.SDROutreachLog')
def on_outreach_log_saved(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        if getattr(instance, 'status', None) != 'sent':
            return
        enrollment = getattr(instance, 'enrollment', None)
        if not enrollment:
            return
        lead = getattr(enrollment, 'lead', None)
        if not lead or not lead.email:
            return
        company = _company_from_lead(lead)
        if not company:
            return
        if not _has_active_integrations(company):
            return
        _get_agent(company).enqueue_email_sent(instance)
        _process_async(company)
    except Exception:
        logger.exception(
            'CRM signal error on SDROutreachLog save (log=%s)',
            getattr(instance, 'pk', '?'),
        )


# ------------------------------------------------------------------ #
# SDR Meeting — log meeting on creation
# ------------------------------------------------------------------ #

@receiver(post_save, sender='ai_sdr_agent.SDRMeeting')
def on_sdr_meeting_saved(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        lead = getattr(instance, 'lead', None)
        if not lead or not lead.email:
            return
        company = _company_from_lead(lead)
        if not company:
            return
        if not _has_active_integrations(company):
            return
        _get_agent(company).enqueue_meeting(instance)
        _process_async(company)
    except Exception:
        logger.exception(
            'CRM signal error on SDRMeeting save (meeting=%s)',
            getattr(instance, 'pk', '?'),
        )


# ------------------------------------------------------------------ #
# SDR Campaign Enrollment — log note when a reply is detected
# ------------------------------------------------------------------ #

@receiver(post_save, sender='ai_sdr_agent.SDRCampaignEnrollment')
def on_enrollment_reply(sender, instance, created, **kwargs):
    if created:
        return
    try:
        # Only fire when a reply was just recorded (reply_received_at freshly set)
        if not getattr(instance, 'reply_received_at', None):
            return
        # Check if reply_sentiment changed (indicates a new reply was processed)
        if not getattr(instance, 'reply_sentiment', None):
            return
        lead = getattr(instance, 'lead', None)
        if not lead or not lead.email:
            return
        company = _company_from_lead(lead)
        if not company:
            return
        if not _has_active_integrations(company):
            return
        _get_agent(company).enqueue_reply_note(instance)
        _process_async(company)
    except Exception:
        logger.exception(
            'CRM signal error on SDRCampaignEnrollment save (enrollment=%s)',
            getattr(instance, 'pk', '?'),
        )

"""Django signals that trigger CRM sync on SDR model changes."""
from __future__ import annotations

import logging


from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _get_agent(company):
    from crm_sync_agent.agents.crm_sync_agent import CRMSyncAgent
    return CRMSyncAgent(company)


def _has_active_integrations(company) -> bool:
    from crm_sync_agent.models import CRMIntegration
    return CRMIntegration.objects.filter(company=company, is_active=True).exists()


#: Seconds after a save before the company's queue is worked through; saves within it share one run.
RUN_AFTER_SECONDS = 10


def _process_async(company):
    """Work through the company's queue shortly, once for a burst of saves.

    Each save started its own thread over the same waiting entries: an import of a few hundred leads, or a
    sequence sending fifty emails, started that many, and two threads could send the same entry (CO-206). Now one
    queued run per company and burst (entries are also claimed one by one); without Celery the two-minute
    scheduled job does it. Not for a company whose CRM Sync subscription is not active (core/modules.py)."""
    from core.modules import has_module
    if not has_module(company, 'crm_sync_agent'):
        return
    from django.core.cache import cache
    from django.db import transaction
    if not cache.add(f'crm-sync-run-{company.pk}', 1, RUN_AFTER_SECONDS):
        return

    def _queue():
        try:
            from crm_sync_agent.tasks import process_crm_sync_queue
            process_crm_sync_queue.apply_async(kwargs={'company_id': company.pk}, countdown=RUN_AFTER_SECONDS)
        except Exception:
            logger.warning('CRM sync: no task queue just now; the scheduled job will send company %s\'s entries',
                           getattr(company, 'pk', '?'))
    transaction.on_commit(_queue)


def queue_inbox_email(email) -> None:
    """Reply Draft's AI has read an email: if it is from a customer or a lead and the company has CRM Sync, it goes
    to the CRM. Called by reply_draft_agent's triage job, which saves with update() and so sends no signal."""
    try:
        company = _company_of_mailbox(email.email_account)
        if company is None or not _has_active_integrations(company):
            return
        _get_agent(company).enqueue_inbox_email(email)
        _process_async(company)
    except Exception:
        logger.exception('CRM: could not queue inbox email %s', getattr(email, 'pk', '?'))


def queue_inbox_reply(draft, to_email, subject, body) -> None:
    """A reply has been sent from Reply Draft: it goes to the CRM on the recipient's contact."""
    try:
        company = _company_of_mailbox(draft.email_account)
        if company is None or not _has_active_integrations(company):
            return
        _get_agent(company).enqueue_inbox_reply(draft, to_email, subject, body)
        _process_async(company)
    except Exception:
        logger.exception('CRM: could not queue reply %s', getattr(draft, 'pk', '?'))


def _company_of_mailbox(account):
    from core.logins import company_id_for
    from core.models import Company
    from core.modules import has_module
    company_id = company_id_for(account.owner) if account is not None else None
    company = Company.objects.filter(pk=company_id).first() if company_id else None
    return company if company is not None and has_module(company, 'crm_sync_agent') else None


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
# SDR Meeting — log the meeting once it has a time
# ------------------------------------------------------------------ #

def log_meeting(meeting) -> None:
    """Send a sales meeting to the CRM, once, when its time is settled.

    It used to be sent the moment the AI created it, before any time was
    chosen, and the CRM recorded it at that moment; when the lead later picked
    a time the CRM was never told. `enqueue_meeting` sends each meeting once,
    so calling this again for the same meeting does nothing.
    """
    # 'cancelled' too: one already in the CRM is marked cancelled there; one that never went is not sent (CO-275).
    if not meeting.scheduled_at or meeting.status not in ('scheduled', 'completed', 'cancelled'):
        return
    lead = getattr(meeting, 'lead', None)
    if not lead or not lead.email:
        return
    company = _company_from_lead(lead)
    if not company or not _has_active_integrations(company):
        return
    _get_agent(company).enqueue_meeting(meeting)
    _process_async(company)


@receiver(post_save, sender='ai_sdr_agent.SDRMeeting')
def on_sdr_meeting_saved(sender, instance, created, **kwargs):
    try:
        log_meeting(instance)
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
        # A reply has been recorded. (This read `reply_received_at`, a field
        # the enrollment does not have, so no reply ever reached the CRM.)
        # `enqueue_reply_note` sends one note per reply, however many times the
        # enrollment is saved afterwards.
        if not getattr(instance, 'replied_at', None):
            return
        if not (getattr(instance, 'reply_content', '') or getattr(instance, 'reply_sentiment', '')):
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

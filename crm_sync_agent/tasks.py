"""Celery tasks for the CRM Sync Agent.

Scheduled via CELERY_BEAT_SCHEDULE in settings.py:
  - process-crm-sync-queue     every 2 minutes
  - retry-failed-crm-syncs     every 30 minutes
  - ping-crm-integrations      every hour
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='crm_sync_agent.tasks.process_crm_sync_queue', max_retries=0)
def process_crm_sync_queue(self, company_id: int | None = None):
    """
    Process pending CRM sync queue items.

    If `company_id` is given, only process items for that company.
    Otherwise, process all companies with pending items (up to 100 per company).
    """
    from core.models import Company
    from crm_sync_agent.models import CRMSyncQueue
    from crm_sync_agent.agents.crm_sync_agent import CRMSyncAgent

    from core.modules import active_company_ids

    now = timezone.now()
    # Nothing is pushed to a CRM for a company whose CRM Sync subscription is
    # not active (core/modules.py). Its queue waits.
    paying = active_company_ids('crm_sync_agent')

    if company_id:
        companies = Company.objects.filter(pk=company_id, id__in=paying)
    else:
        # Only fetch companies that actually have pending work
        company_ids = (
            CRMSyncQueue.objects
            .filter(
                status__in=[CRMSyncQueue.STATUS_PENDING, CRMSyncQueue.STATUS_FAILED],
                scheduled_at__lte=now,
            )
            .values_list('company_id', flat=True)
            .distinct()
        )
        companies = Company.objects.filter(pk__in=company_ids, id__in=paying)

    total_stats = {'processed': 0, 'succeeded': 0, 'failed': 0, 'skipped': 0}

    for company in companies:
        try:
            agent = CRMSyncAgent(company)
            stats = agent.process_pending(limit=100)
            for k, v in stats.items():
                total_stats[k] = total_stats.get(k, 0) + v
        except Exception:
            logger.exception('Error processing CRM sync queue for company %d', company.pk)

    if total_stats['processed']:
        logger.info(
            'CRM sync queue: processed=%d succeeded=%d failed=%d skipped=%d',
            total_stats['processed'],
            total_stats['succeeded'],
            total_stats['failed'],
            total_stats['skipped'],
        )
    return total_stats


@shared_task(name='crm_sync_agent.tasks.retry_failed_crm_syncs')
def retry_failed_crm_syncs():
    """
    Re-schedule failed queue items whose scheduled_at is still in the past
    so that the next process_crm_sync_queue run picks them up.
    This handles items that were failed but whose back-off window has now expired.
    """
    from crm_sync_agent.models import CRMSyncQueue

    now = timezone.now()
    # Items that failed, haven't maxed out retries, and are past their scheduled_at
    ready = CRMSyncQueue.objects.filter(
        status=CRMSyncQueue.STATUS_FAILED,
        scheduled_at__lte=now,
        attempts__lt=3,
    )
    count = ready.update(status=CRMSyncQueue.STATUS_PENDING)
    if count:
        logger.info('CRM sync: re-queued %d failed items for retry', count)
    return count


@shared_task(name='crm_sync_agent.tasks.ping_crm_integrations')
def ping_crm_integrations():
    """
    Health-check every active CRM integration and update last_ping_ok.
    Runs hourly. Useful for surfacing credential failures in the dashboard.
    """
    from crm_sync_agent.models import CRMIntegration
    from crm_sync_agent.agents.crm_sync_agent import CRMSyncAgent

    from core.modules import active_company_ids
    integrations = (CRMIntegration.objects
                    .filter(is_active=True, company_id__in=active_company_ids('crm_sync_agent'))
                    .select_related('company'))
    results = {'ok': 0, 'failed': 0}

    for integration in integrations:
        try:
            agent = CRMSyncAgent(integration.company)
            connector = agent._get_connector(integration)
            ok = connector.ping()
        except Exception as exc:
            logger.warning(
                'CRM ping failed for integration %d (%s): %s',
                integration.pk, integration.provider, exc,
            )
            ok = False

        integration.last_ping_at = timezone.now()
        integration.last_ping_ok = ok
        integration.save(update_fields=['last_ping_at', 'last_ping_ok'])

        if ok:
            results['ok'] += 1
        else:
            results['failed'] += 1

    logger.info('CRM integration ping: ok=%d failed=%d', results['ok'], results['failed'])
    return results


def queue_everything(agent, company) -> dict:
    """Queue all of a company's AI SDR leads, sent emails and timed meetings
    for its CRM. Used by "Sync All Leads", from the queue and directly.
    Safe to repeat: contacts are upserted, and a meeting or email already in
    the CRM is not sent twice."""
    from ai_sdr_agent.models import SDRLead, SDRMeeting, SDROutreachLog

    counts = {'leads': 0, 'emails': 0, 'meetings': 0}

    def each(kind, rows, enqueue):
        for row in rows.iterator(chunk_size=200):
            try:
                enqueue(row)
                counts[kind] += 1
            except Exception:
                logger.exception('CRM full sync: could not queue %s %s', kind, row.pk)

    # A lead belongs to a salesperson's login, not to the company directly.
    # This filtered on a `company` field leads do not have, so the job failed
    # on its first step every time and "Sync queued" never synced anything.
    each('leads', SDRLead.objects.filter(company_user__company=company), agent.enqueue_sdr_lead)
    each('emails', SDROutreachLog.objects.filter(
        status='sent', enrollment__lead__company_user__company=company,
    ).select_related('enrollment__lead'), agent.enqueue_email_sent)
    each('meetings', SDRMeeting.objects.filter(
        lead__company_user__company=company, scheduled_at__isnull=False,
        status__in=('scheduled', 'completed'),
    ).select_related('lead'), agent.enqueue_meeting)
    return counts


@shared_task(name='crm_sync_agent.tasks.sync_sdr_leads_to_crm')
def sync_sdr_leads_to_crm(company_id: int | None = None):
    """
    Full re-sync of all SDR leads to CRM. Intended for initial setup or
    after connecting a new integration. Idempotent — upserts, never duplicates.
    """
    from core.models import Company
    from core.modules import active_company_ids
    from crm_sync_agent.models import CRMIntegration
    from crm_sync_agent.agents.crm_sync_agent import CRMSyncAgent

    paying = active_company_ids('crm_sync_agent')
    if company_id:
        companies = Company.objects.filter(pk=company_id, id__in=paying)
    else:
        company_ids = CRMIntegration.objects.filter(
            is_active=True, sync_contacts=True
        ).values_list('company_id', flat=True).distinct()
        companies = Company.objects.filter(pk__in=company_ids, id__in=paying)

    enqueued = 0
    for company in companies:
        agent = CRMSyncAgent(company)
        if not agent._integrations:
            continue
        enqueued += sum(queue_everything(agent, company).values())

    logger.info('CRM full sync: queued %d items', enqueued)
    return enqueued

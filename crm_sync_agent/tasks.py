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

    now = timezone.now()

    if company_id:
        companies = Company.objects.filter(pk=company_id)
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
        companies = Company.objects.filter(pk__in=company_ids)

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

    integrations = CRMIntegration.objects.filter(is_active=True).select_related('company')
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


@shared_task(name='crm_sync_agent.tasks.sync_sdr_leads_to_crm')
def sync_sdr_leads_to_crm(company_id: int | None = None):
    """
    Full re-sync of all SDR leads to CRM. Intended for initial setup or
    after connecting a new integration. Idempotent — upserts, never duplicates.
    """
    from core.models import Company
    from ai_sdr_agent.models import SDRLead
    from crm_sync_agent.models import CRMIntegration
    from crm_sync_agent.agents.crm_sync_agent import CRMSyncAgent

    if company_id:
        companies = Company.objects.filter(pk=company_id)
    else:
        company_ids = CRMIntegration.objects.filter(
            is_active=True, sync_contacts=True
        ).values_list('company_id', flat=True).distinct()
        companies = Company.objects.filter(pk__in=company_ids)

    enqueued = 0
    for company in companies:
        agent = CRMSyncAgent(company)
        if not agent._integrations:
            continue
        leads = SDRLead.objects.filter(company=company).exclude(email='')
        for lead in leads.iterator(chunk_size=200):
            try:
                agent.enqueue_sdr_lead(lead)
                enqueued += 1
            except Exception:
                logger.exception('Error enqueuing lead %d for CRM sync', lead.pk)

    logger.info('CRM full lead sync: enqueued %d contact items', enqueued)
    return enqueued

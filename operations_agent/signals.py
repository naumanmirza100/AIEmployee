"""
Operations Agent — Signal Handlers

Auto-generate OperationsNotification records when interesting things happen:

  • A summary is saved with `importance_level = critical`  → anomaly_detected (critical)
  • A summary contains upcoming deadlines (next 7 days)   → threshold_breach (warning),
    when the summary is ready and again each morning (tasks.alert_operations_deadlines)
  • A summary extracts 2+ risks                            → anomaly_detected (warning)
  • A summary extracts 2+ opportunities                    → metric_change (info)
  • A document fails to process                            → document_update (critical)

Each notification is attributed to the company and deduped by (type, source_id) so
re-saving a summary doesn't flood the inbox.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    OperationsDocument,
    OperationsDocumentSummary,
    OperationsNotification,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _parse_deadline_date(value) -> Optional[date]:
    """Best-effort parse of a deadline date from the summary's `deadlines` field."""
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    # Try a handful of common formats
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%B %d, %Y', '%d %b %Y', '%d %B %Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _create_once(company, notification_type: str, severity: str, title: str,
                 message: str, data: dict, dedupe_key: str) -> Optional[OperationsNotification]:
    """Create a notification only if an equivalent one doesn't already exist."""
    existing = OperationsNotification.objects.filter(
        company=company,
        notification_type=notification_type,
        data__dedupe_key=dedupe_key,
    ).exists()
    if existing:
        return None
    payload = dict(data or {})
    payload['dedupe_key'] = dedupe_key
    return OperationsNotification.objects.create(
        company=company,
        notification_type=notification_type,
        severity=severity,
        title=title[:255],
        message=message,
        data=payload,
    )


DEADLINE_HORIZON_DAYS = 7


def upcoming_deadlines(summary, today: date) -> list:
    """The summary's deadlines that fall between today and a week from now, soonest first."""
    horizon = today + timedelta(days=DEADLINE_HORIZON_DAYS)
    upcoming = []
    for d in summary.deadlines or []:
        if isinstance(d, dict):
            parsed = _parse_deadline_date(d.get('date') or d.get('deadline'))
            desc = (d.get('description') or d.get('title') or d.get('text') or '').strip()
        else:
            continue            # a deadline written as plain text has no date to count down to
        if parsed and today <= parsed <= horizon:
            upcoming.append({'date': parsed.isoformat(), 'description': desc or 'Deadline',
                             'days_left': (parsed - today).days})
    return sorted(upcoming, key=lambda x: x['days_left'])


def _deadline_key(item) -> str:
    return f"{item.get('date')}:{(item.get('description') or '').strip().lower()[:80]}"


def alert_upcoming_deadlines(summary, today: Optional[date] = None) -> Optional[OperationsNotification]:
    """One alert for this summary's deadlines that are within the next week and have had no alert yet.

    Called when the summary is ready and every morning by `tasks.alert_operations_deadlines`: a deadline further
    out than a week used to get no alert at all, and now gets one when it comes within the week. A deadline is
    alerted once, whichever of the two finds it first.
    """
    today = today or timezone.now().date()
    upcoming = upcoming_deadlines(summary, today)
    if not upcoming:
        return None
    alerted = {
        _deadline_key(d)
        for data in OperationsNotification.objects.filter(
            company_id=summary.company_id, notification_type='threshold_breach', data__summary_id=summary.id,
        ).values_list('data', flat=True)
        for d in ((data or {}).get('deadlines') or []) if isinstance(d, dict)
    }
    fresh = [d for d in upcoming if _deadline_key(d) not in alerted]
    if not fresh:
        return None
    filename = summary.original_filename or 'Untitled document'
    soonest = fresh[0]
    days = soonest['days_left']
    when = 'today' if days == 0 else f'in {days} day{"s" if days != 1 else ""}'
    title = f'Deadline {when}' if len(fresh) == 1 else f'{len(fresh)} upcoming deadlines in {filename}'
    when_label = date.fromisoformat(soonest['date']).strftime('%d %b %Y').lstrip('0')   # "2 Nov 2026", not ISO
    message = (f'{soonest["description"]} — by {when_label} ({filename})' if len(fresh) == 1
               else 'Review the summary for the full list of deadlines.')
    keys = ','.join(sorted(_deadline_key(d) for d in fresh))
    created = _create_once(
        company=summary.company,
        notification_type='threshold_breach',
        severity='warning',
        title=title,
        message=message,
        data={'summary_id': summary.id, 'source': 'summary', 'filename': filename, 'deadlines': fresh},
        dedupe_key=f'summary:{summary.id}:deadlines:{hashlib.sha1(keys.encode()).hexdigest()[:12]}',
    )
    if created is not None:
        _ring_bell(summary, f'{title}: {filename}' if len(fresh) == 1 else title, message, 'operations_deadline')
    return created


def _ring_bell(summary, title, message, kind):
    """An alert that needs someone reaches the bell of whoever summarised the file, once.

    A deadline within a week ("renew the lease by 2 November") and a critical document stayed on Operations' own
    Notifications page, which nobody opens to look (found on the live run, 28 Oct 2026)."""
    from core.notification_utils import notify_company_users
    if not summary.created_by_id:
        return
    try:
        notify_company_users([summary.created_by], title=title[:255], message=(message or '')[:300],
                             link=f'/operations/summarization/{summary.id}', severity='warning', kind=kind,
                             data={'summary_id': summary.id})
    except Exception:
        logger.exception('Operations: could not ring the bell for summary %s', summary.id)


# ──────────────────────────────────────────────
# Summary signals
# ──────────────────────────────────────────────

@receiver(post_save, sender=OperationsDocumentSummary)
def notifications_for_summary(sender, instance: OperationsDocumentSummary,
                              created: bool, **kwargs):
    """Fire when a summary is ready. Deduped via `dedupe_key`, so later saves add nothing.

    It used to run only when the row was created, and the row is created empty and filled in by the AI afterwards,
    so none of these alerts ever fired (CO-173). It now waits until the summary is ready.
    """
    if instance.processing_status != 'ready':
        return

    try:
        filename = instance.original_filename or 'Untitled document'

        # 1) Critical importance
        if (instance.importance_level or '').lower() == 'critical':
            critical = _create_once(
                company=instance.company,
                notification_type='anomaly_detected',
                severity='critical',
                title=f'Critical document: {filename}',
                message=(instance.importance_reason
                         or 'This document has been flagged as critical importance.'),
                data={
                    'summary_id': instance.id,
                    'source': 'summary',
                    'category': instance.document_category or '',
                },
                dedupe_key=f'summary:{instance.id}:critical',
            )
            if critical is not None:
                _ring_bell(instance, critical.title, critical.message, 'operations_critical_document')

        # 2) Upcoming deadlines (≤ 7 days)
        alert_upcoming_deadlines(instance)

        # 3) Risks detected (2 or more)
        risks = [r for r in (instance.risks or []) if r]
        if len(risks) >= 2:
            _create_once(
                company=instance.company,
                notification_type='anomaly_detected',
                severity='warning',
                title=f'{len(risks)} risks flagged in {filename}',
                message='Review the summary\'s Risks section for details.',
                data={
                    'summary_id': instance.id,
                    'source': 'summary',
                    'risk_count': len(risks),
                },
                dedupe_key=f'summary:{instance.id}:risks',
            )

        # 4) Opportunities detected (2 or more)
        opps = [o for o in (instance.opportunities or []) if o]
        if len(opps) >= 2:
            _create_once(
                company=instance.company,
                notification_type='metric_change',
                severity='info',
                title=f'{len(opps)} opportunities in {filename}',
                message='The AI surfaced several opportunities worth reviewing.',
                data={
                    'summary_id': instance.id,
                    'source': 'summary',
                    'opportunity_count': len(opps),
                },
                dedupe_key=f'summary:{instance.id}:opportunities',
            )

    except Exception as e:
        logger.error(f'notifications_for_summary failed: {e}', exc_info=True)


# ──────────────────────────────────────────────
# Document signals
# ──────────────────────────────────────────────

def _tell_uploader(document):
    """A document that could not be read reaches its uploader's bell, once.

    Operations' alerts stayed on its own Notifications page, so someone who uploaded
    a file and moved on never learnt that it had failed."""
    from core.notification_utils import notify_company_users
    if not document.uploaded_by_id:
        return
    notify_company_users(
        [document.uploaded_by], title=f'Could not read {document.original_filename}'[:255],
        message=(f'{(document.processing_error or "").strip()[:300]} '
                 'Open Documents in Operations to retry it or upload it again.').strip(),
        link='/operations/documents', severity='warning', kind='operations_document_failed',
        data={'document_id': document.id})


@receiver(post_save, sender=OperationsDocument)
def notifications_for_document(sender, instance: OperationsDocument,
                               created: bool, **kwargs):
    """Fire when a document's processing status changes."""
    try:
        # Processing failed (permanent)
        if instance.processing_error and not instance.is_processed:
            created_alert = _create_once(
                company=instance.company,
                notification_type='document_update',
                severity='critical',
                title=f'Could not process {instance.original_filename}',
                message=instance.processing_error[:500],
                data={
                    'document_id': instance.id,
                    'source': 'document',
                },
                dedupe_key=f'document:{instance.id}:failed',
            )
            if created_alert is not None:
                _tell_uploader(instance)
            return

        # Successfully processed → subtle info notification (the first time)
        if instance.is_processed and instance.processed_at:
            _create_once(
                company=instance.company,
                notification_type='report_ready',
                severity='info',
                title=f'{instance.original_filename} is ready',
                message=f'Processed {instance.page_count or 0} page(s). You can now ask questions about it.',
                data={
                    'document_id': instance.id,
                    'source': 'document',
                    'pages': instance.page_count or 0,
                },
                dedupe_key=f'document:{instance.id}:processed',
            )

    except Exception as e:
        logger.error(f'notifications_for_document failed: {e}', exc_info=True)

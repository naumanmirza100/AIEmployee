"""
Operations Agent — Signal Handlers

Auto-generate OperationsNotification records when interesting things happen:

  • A summary is saved with `importance_level = critical`  → anomaly_detected (critical)
  • A summary contains upcoming deadlines (next 7 days)   → threshold_breach (warning)
  • A summary extracts 2+ risks                            → anomaly_detected (warning)
  • A summary extracts 2+ opportunities                    → metric_change (info)
  • A document fails to process                            → document_update (critical)

Each notification is attributed to the company and deduped by (type, source_id) so
re-saving a summary doesn't flood the inbox.
"""

from __future__ import annotations

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


# ──────────────────────────────────────────────
# Summary signals
# ──────────────────────────────────────────────

@receiver(post_save, sender=OperationsDocumentSummary)
def notifications_for_summary(sender, instance: OperationsDocumentSummary,
                              created: bool, **kwargs):
    """Fire on each summary save. Deduped via `dedupe_key` so edits don't spam."""
    if not created:
        return

    try:
        filename = instance.original_filename or 'Untitled document'

        # 1) Critical importance
        if (instance.importance_level or '').lower() == 'critical':
            _create_once(
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

        # 2) Upcoming deadlines (≤ 7 days)
        today = timezone.now().date()
        horizon = today + timedelta(days=7)
        deadlines = instance.deadlines or []
        upcoming = []
        for d in deadlines:
            if isinstance(d, dict):
                parsed = _parse_deadline_date(d.get('date') or d.get('deadline'))
                desc = (d.get('description') or d.get('title')
                        or d.get('text') or '').strip()
            elif isinstance(d, str):
                parsed = None
                desc = d.strip()
            else:
                continue
            if parsed and today <= parsed <= horizon:
                days_left = (parsed - today).days
                upcoming.append({
                    'date': parsed.isoformat(),
                    'description': desc or 'Deadline',
                    'days_left': days_left,
                })

        if upcoming:
            soonest = min(upcoming, key=lambda x: x['days_left'])
            count = len(upcoming)
            title = (
                f'Deadline in {soonest["days_left"]} day{"s" if soonest["days_left"] != 1 else ""}'
                if count == 1 else
                f'{count} upcoming deadlines in {filename}'
            )
            msg = (
                f'{soonest["description"]} — {soonest["date"]}' if count == 1 else
                'Review the summary for the full list of deadlines.'
            )
            _create_once(
                company=instance.company,
                notification_type='threshold_breach',
                severity='warning',
                title=title,
                message=msg,
                data={
                    'summary_id': instance.id,
                    'source': 'summary',
                    'filename': filename,
                    'deadlines': upcoming,
                },
                dedupe_key=f'summary:{instance.id}:deadlines',
            )

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

@receiver(post_save, sender=OperationsDocument)
def notifications_for_document(sender, instance: OperationsDocument,
                               created: bool, **kwargs):
    """Fire when a document's processing status changes."""
    try:
        # Processing failed (permanent)
        if instance.processing_error and not instance.is_processed:
            _create_once(
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

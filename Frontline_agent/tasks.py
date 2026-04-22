"""
Frontline Agent periodic + on-demand tasks.
"""
import json
import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name='Frontline_agent.tasks.process_document',
             bind=True, max_retries=2, default_retry_delay=60)
def process_document(self, document_id):
    """Parse + chunk + embed an uploaded document. Writes progress to the Document row
    so the client can poll `processing_status` / `chunks_processed` / `chunks_total`.

    Safe to retry: existing DocumentChunks are cleared at the start so re-runs produce
    a clean index."""
    from django.conf import settings
    from Frontline_agent.models import Document, DocumentChunk
    from Frontline_agent.document_processor import DocumentProcessor
    from core.Fronline_agent.embedding_service import EmbeddingService

    document = Document.objects.filter(id=document_id).first()
    if not document:
        logger.warning("process_document: Document %s not found", document_id)
        return {'status': 'not_found', 'document_id': document_id}

    document.processing_status = 'processing'
    document.processing_error = ''
    document.chunks_processed = 0
    document.chunks_total = 0
    document.save(update_fields=['processing_status', 'processing_error',
                                 'chunks_processed', 'chunks_total', 'updated_at'])

    # Remove any stale chunks from a previous partial run
    DocumentChunk.objects.filter(document=document).delete()

    try:
        processor = DocumentProcessor()
        result = processor.process_document(document.file_path, document.title)
        if not result.get('success'):
            raise RuntimeError(result.get('error') or 'process_document failed')

        extracted_text = result.get('extracted_text', '') or ''
        document.document_content = extracted_text
        document.file_hash = result.get('file_hash', document.file_hash)

        # Chunk with the per-tenant / upload-override settings (fallback to globals)
        chunk_size = int(document.processed_data.get('chunk_size')
                         or getattr(settings, 'FRONTLINE_CHUNK_SIZE', 4000))
        overlap = int(document.processed_data.get('chunk_overlap')
                      or getattr(settings, 'FRONTLINE_CHUNK_OVERLAP', 200))
        overlap = max(0, min(overlap, max(0, chunk_size - 1)))

        text_to_chunk = f"{document.title}\n{document.description}\n{extracted_text}".strip()
        chunks = []
        start = 0
        step = max(1, chunk_size - overlap)
        while start < len(text_to_chunk):
            chunks.append(text_to_chunk[start:start + chunk_size])
            start += step

        document.chunks_total = len(chunks)
        document.save(update_fields=['document_content', 'file_hash',
                                     'chunks_total', 'updated_at'])

        embedding_service = EmbeddingService()
        has_embeddings = embedding_service.is_available()
        batch_size = 20
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            embeddings = embedding_service.generate_embeddings_batch(batch) if has_embeddings else [None] * len(batch)
            rows = [
                DocumentChunk(
                    document=document,
                    chunk_index=i + j,
                    chunk_text=chunk_text,
                    embedding=(json.dumps(emb) if emb else None),
                )
                for j, (chunk_text, emb) in enumerate(zip(batch, embeddings))
            ]
            DocumentChunk.objects.bulk_create(rows)
            document.chunks_processed = i + len(batch)
            document.save(update_fields=['chunks_processed', 'updated_at'])

        document.processing_status = 'ready'
        document.is_indexed = True
        document.processed = True
        document.embedding_model = embedding_service.embedding_model if has_embeddings else None
        document.save(update_fields=['processing_status', 'is_indexed', 'processed',
                                     'embedding_model', 'updated_at'])
        logger.info("process_document: doc %s ready (%d chunks)", document_id, document.chunks_total)
        return {'status': 'ready', 'document_id': document_id, 'chunks': document.chunks_total}

    except Exception as exc:
        logger.exception("process_document failed for doc %s: %s", document_id, exc)
        try:
            # Celery auto-retry with backoff; on final failure mark the doc as failed.
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            pass
        except Exception:
            # Retry scheduled — fall through to leave status as 'processing'
            return {'status': 'retrying', 'document_id': document_id}
        document.processing_status = 'failed'
        document.processing_error = f"{type(exc).__name__}: {exc}"[:4000]
        document.save(update_fields=['processing_status', 'processing_error', 'updated_at'])
        return {'status': 'failed', 'document_id': document_id}


@shared_task(name='Frontline_agent.tasks.send_weekly_analytics_digest')
def send_weekly_analytics_digest():
    """Email each company's active users a 7-day analytics summary.
    Runs weekly. Computes KPIs per company over the last 7 days and emails the
    digest via Django's send_mail using the default FROM address."""
    from datetime import timedelta as _td
    from django.conf import settings
    from django.core.mail import send_mail
    from core.models import Company, CompanyUser
    from Frontline_agent.models import Ticket, FrontlineMeeting

    now = timezone.now()
    window_start = now - _td(days=7)
    companies_sent = 0
    users_emailed = 0

    resolved_statuses = {'resolved', 'closed', 'auto_resolved'}

    for company in Company.objects.filter(is_active=True):
        tickets = Ticket.objects.filter(company=company, created_at__gte=window_start)
        total = tickets.count()
        if total == 0:
            continue  # Skip quiet weeks — no digest is better than a "zero" email.

        resolved = sum(1 for t in tickets.only('status') if t.status in resolved_statuses)
        auto_resolved = tickets.filter(auto_resolved=True).count()
        by_priority = {p: tickets.filter(priority=p).count() for p in ('urgent', 'high', 'medium', 'low')}
        breached = tickets.filter(
            sla_due_at__isnull=False, sla_due_at__lt=now,
        ).exclude(status__in=list(resolved_statuses)).count()
        meetings = FrontlineMeeting.objects.filter(
            company=company, created_at__gte=window_start,
        ).count()

        subject = f"Frontline weekly digest — {company.name}"
        body_lines = [
            f"Frontline Agent — 7-day summary for {company.name} "
            f"({window_start.date()} → {now.date()})",
            "",
            f"  Tickets created:    {total}",
            f"  Resolved:           {resolved} ({round(100.0*resolved/total,1)}%)",
            f"  Auto-resolved:      {auto_resolved} ({round(100.0*auto_resolved/total,1)}%)",
            f"  SLA-breached open:  {breached}",
            "",
            "  By priority:",
            f"    urgent:  {by_priority['urgent']}",
            f"    high:    {by_priority['high']}",
            f"    medium:  {by_priority['medium']}",
            f"    low:     {by_priority['low']}",
            "",
            f"  Meetings created:   {meetings}",
        ]
        body = "\n".join(body_lines)

        recipients = list(
            CompanyUser.objects.filter(company=company, is_active=True)
            .exclude(email='').values_list('email', flat=True)
        )
        if not recipients:
            continue
        try:
            send_mail(
                subject=subject, message=body,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
                recipient_list=recipients, fail_silently=False,
            )
            companies_sent += 1
            users_emailed += len(recipients)
        except Exception as exc:
            logger.warning("Weekly digest send failed for company %s: %s", company.id, exc)

    logger.info("send_weekly_analytics_digest: companies=%d users=%d",
                companies_sent, users_emailed)
    return {'companies': companies_sent, 'users': users_emailed}


@shared_task(name='Frontline_agent.tasks.send_meeting_reminders')
def send_meeting_reminders():
    """Send 24h and 15-minute reminder emails for upcoming frontline meetings.

    Runs every 5 minutes. Picks meetings whose scheduled_at falls within one of the
    two reminder windows and hasn't had that reminder marked sent yet. Uses a small
    window (±2.5 minutes) around the target so a 5-minute poll cadence never misses
    a meeting."""
    from datetime import timedelta as _td
    from django.core.mail import send_mail
    from django.conf import settings
    from Frontline_agent.models import FrontlineMeeting

    now = timezone.now()
    results = {'r24h_sent': 0, 'r15m_sent': 0, 'skipped': 0, 'failed': 0}

    def _recipients(meeting):
        emails = set()
        if meeting.organizer and meeting.organizer.email:
            emails.add(meeting.organizer.email)
        for p in meeting.participants.all():
            if p.email:
                emails.add(p.email)
        return list(emails)

    def _send(meeting, window_label):
        subject = f"Reminder ({window_label}): {meeting.title}"
        when = meeting.scheduled_at.isoformat() if meeting.scheduled_at else '(unknown)'
        body_parts = [
            f"This is a reminder that '{meeting.title}' is scheduled for {when} ({meeting.timezone_name}).",
            f"Duration: {meeting.duration_minutes} minutes.",
        ]
        if meeting.meeting_link:
            body_parts.append(f"Meeting link: {meeting.meeting_link}")
        if meeting.location:
            body_parts.append(f"Location: {meeting.location}")
        if meeting.description:
            body_parts.append("")
            body_parts.append(meeting.description)
        body = "\n\n".join(body_parts)

        recipients = _recipients(meeting)
        if not recipients:
            return False
        try:
            send_mail(
                subject=subject, message=body,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
                recipient_list=recipients, fail_silently=False,
            )
            return True
        except Exception as exc:
            logger.warning("Meeting reminder send failed for meeting %s: %s", meeting.id, exc)
            return False

    # 24h reminder: scheduled_at is ~24h from now (window 23h57m..24h02m) and not yet sent.
    r24_lo = now + _td(hours=24) - _td(minutes=3)
    r24_hi = now + _td(hours=24) + _td(minutes=2)
    for m in FrontlineMeeting.objects.filter(
        status__in=['scheduled', 'rescheduled'],
        scheduled_at__gte=r24_lo, scheduled_at__lte=r24_hi,
        reminder_24h_sent_at__isnull=True,
    ):
        if _send(m, '24 hours'):
            m.reminder_24h_sent_at = now
            m.save(update_fields=['reminder_24h_sent_at', 'updated_at'])
            results['r24h_sent'] += 1
        else:
            results['failed'] += 1

    # 15-minute reminder: scheduled_at is ~15m from now (window 12m..17m) and not yet sent.
    r15_lo = now + _td(minutes=12)
    r15_hi = now + _td(minutes=17)
    for m in FrontlineMeeting.objects.filter(
        status__in=['scheduled', 'rescheduled'],
        scheduled_at__gte=r15_lo, scheduled_at__lte=r15_hi,
        reminder_15m_sent_at__isnull=True,
    ):
        if _send(m, '15 minutes'):
            m.reminder_15m_sent_at = now
            m.save(update_fields=['reminder_15m_sent_at', 'updated_at'])
            results['r15m_sent'] += 1
        else:
            results['failed'] += 1

    if any(results[k] for k in ('r24h_sent', 'r15m_sent', 'failed')):
        logger.info("send_meeting_reminders: %s", results)
    return results


@shared_task(name='Frontline_agent.tasks.prune_expired_documents')
def prune_expired_documents():
    """Delete documents whose retention window has passed.
    Runs daily. Cascades delete DocumentChunks via FK."""
    from Frontline_agent.models import Document
    now = timezone.now()
    # Only consider rows with a positive retention_days
    candidates = Document.objects.filter(retention_days__isnull=False, retention_days__gt=0)
    deleted = 0
    # Evaluated in Python because retention is a per-row offset, not a simple cutoff.
    for doc in candidates.only('id', 'retention_days', 'created_at', 'file_path').iterator():
        expires_at = doc.created_at + timedelta(days=int(doc.retention_days))
        if expires_at <= now:
            try:
                # Delete the underlying file too (best-effort)
                try:
                    from pathlib import Path
                    from django.conf import settings as _s
                    p = Path(_s.MEDIA_ROOT) / doc.file_path
                    if p.exists():
                        p.unlink()
                except Exception as e:
                    logger.warning("prune: failed to delete file for doc %s: %s", doc.id, e)
                doc_pk = doc.id
                doc.delete()
                deleted += 1
                logger.info("prune: deleted expired doc %s", doc_pk)
            except Exception as e:
                logger.exception("prune: failed to delete doc %s: %s", doc.id, e)
    return {'deleted': deleted}


@shared_task(name='Frontline_agent.tasks.wake_snoozed_tickets')
def wake_snoozed_tickets():
    """
    Clear the snooze on tickets whose snoozed_until has passed.
    Runs on a short cadence so woken tickets reappear in queues promptly.
    """
    from Frontline_agent.models import Ticket

    now = timezone.now()
    qs = Ticket.objects.filter(snoozed_until__isnull=False, snoozed_until__lte=now)
    count = qs.update(snoozed_until=None)
    if count:
        logger.info("Woke %d snoozed tickets", count)
    return {'woken': count}


# Exponential retry ladder (minutes): after attempt 1 fails, wait 5m; after attempt 2, 30m; after 3, 2h.
_RETRY_BACKOFF_MINUTES = [5, 30, 120]


def _schedule_retry(notif, error_msg):
    """Record a failure and schedule the next retry, or mark dead-lettered."""
    from Frontline_agent.models import ScheduledNotification

    notif.attempts = (notif.attempts or 0) + 1
    notif.last_error = (error_msg or '')[:4000]
    if notif.attempts >= (notif.max_attempts or 3):
        notif.status = 'dead_lettered'
        notif.dead_lettered_at = timezone.now()
        notif.next_retry_at = None
        notif.save(update_fields=['attempts', 'last_error', 'status',
                                  'dead_lettered_at', 'next_retry_at'])
        logger.warning(
            "Notification %s dead-lettered after %d attempts: %s",
            notif.id, notif.attempts, error_msg,
        )
        return
    # Pick the backoff for this attempt; stay on the last slot if attempts > ladder length.
    idx = min(notif.attempts - 1, len(_RETRY_BACKOFF_MINUTES) - 1)
    wait_minutes = _RETRY_BACKOFF_MINUTES[idx]
    notif.status = 'pending'
    notif.next_retry_at = timezone.now() + timedelta(minutes=wait_minutes)
    notif.save(update_fields=['attempts', 'last_error', 'status', 'next_retry_at'])
    logger.info(
        "Notification %s retry %d/%d scheduled in %dm",
        notif.id, notif.attempts, notif.max_attempts, wait_minutes,
    )


@shared_task(name='Frontline_agent.tasks.process_scheduled_notifications')
def process_scheduled_notifications():
    """
    Walk pending notifications whose scheduled_at (and next_retry_at, if set) have passed.
    Send each, honouring recipient quiet hours; on failure apply exponential backoff;
    on exhaustion dead-letter.
    """
    from Frontline_agent.models import ScheduledNotification
    # Local imports to avoid circulars with api.views
    from api.views.frontline_agent import (
        _render_template_body, _generate_llm_notification_body, _send_notification_email,
        _build_unsubscribe_url,
    )
    from Frontline_agent.notification_utils import (
        get_recipient_preferences, in_quiet_hours, next_allowed_send_time,
    )

    from django.db.models import Q

    now = timezone.now()
    due = ScheduledNotification.objects.filter(
        status='pending', scheduled_at__lte=now,
    ).filter(Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now))

    processed = sent = deferred = failed = dead = 0

    # Guard: cap per-tick work to avoid a giant loop under backlog
    for notif in due[:200]:
        processed += 1
        template = notif.template
        if not template:
            _schedule_retry(notif, 'Template was deleted')
            failed += 1
            continue

        recipient_email = (notif.recipient_email or '').strip()
        if not recipient_email and notif.recipient_user_id:
            recipient_email = (notif.recipient_user.email or '').strip()
        if not recipient_email:
            _schedule_retry(notif, 'No recipient_email')
            failed += 1
            continue

        # Quiet-hours: defer without consuming a retry attempt
        prefs = get_recipient_preferences(notif.company_id, recipient_email)
        if prefs and in_quiet_hours(prefs, now):
            notif.next_retry_at = next_allowed_send_time(prefs, now)
            notif.deferred_reason = 'quiet_hours'
            notif.save(update_fields=['next_retry_at', 'deferred_reason'])
            deferred += 1
            logger.info("Notification %s deferred for quiet hours until %s",
                        notif.id, notif.next_retry_at)
            continue

        # Render + optional LLM personalization
        context = dict(notif.context or {})
        if prefs:
            # Attach an unsubscribe URL for the recipient's own CompanyUser
            context.setdefault('unsubscribe_url', _build_unsubscribe_url(prefs.company_user_id))
        body = _render_template_body(template.body, context)
        personalized_body = _generate_llm_notification_body(template, context, notif.company_id)
        if personalized_body:
            body = personalized_body
        subject = _render_template_body(template.subject, context)

        ok = False
        err = None
        try:
            if template.channel == 'email':
                ok = _send_notification_email(recipient_email, subject, body)
            else:
                err = f"Channel '{template.channel}' not implemented"
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"

        if ok:
            notif.status = 'sent'
            notif.sent_at = timezone.now()
            notif.next_retry_at = None
            notif.deferred_reason = ''
            notif.attempts = (notif.attempts or 0) + 1
            notif.save(update_fields=['status', 'sent_at', 'next_retry_at',
                                      'deferred_reason', 'attempts'])
            sent += 1
        else:
            _schedule_retry(notif, err or 'Send failed')
            if notif.status == 'dead_lettered':
                dead += 1
            else:
                failed += 1

    if processed:
        logger.info(
            "process_scheduled_notifications: processed=%d sent=%d deferred=%d failed=%d dead=%d",
            processed, sent, deferred, failed, dead,
        )
    return {'processed': processed, 'sent': sent, 'deferred': deferred,
            'failed': failed, 'dead_lettered': dead}

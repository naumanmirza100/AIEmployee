"""
Frontline Agent periodic + on-demand tasks.
"""
import json
import logging
from datetime import timedelta
from pathlib import Path
from celery import shared_task
from django.utils import timezone
from django.conf import settings

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
    from core.Frontline_agent.embedding_service import EmbeddingService

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
        # document.file_path is stored relative to MEDIA_ROOT (the upload view does
        # `.relative_to(settings.MEDIA_ROOT)` before saving). DocumentProcessor
        # opens the path directly, so we must resolve it to an absolute path here
        # — the Celery worker's CWD isn't MEDIA_ROOT, which silently made every
        # upload fail with "File does not exist" and stay stuck in 'processing'.
        import os as _os
        fp = document.file_path
        if fp and not _os.path.isabs(fp):
            fp = str(Path(settings.MEDIA_ROOT) / fp)
        # The second arg feeds `get_file_format` which keys off the extension.
        # Previously we passed `document.title` here — titles have no extension
        # (e.g. "nlp"), so format came back as 'other' and every upload failed
        # with "Unsupported file format: other". Use the stored filename instead.
        filename_with_ext = _os.path.basename(fp)
        processor = DocumentProcessor()
        result = processor.process_document(fp, filename_with_ext)
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
        # Invalidate the company's FAISS index so next query rebuilds from the new chunks.
        try:
            if has_embeddings and document.company_id:
                from Frontline_agent.vector_store import mark_index_dirty
                mark_index_dirty(document.company_id)
        except Exception:
            logger.exception("process_document: failed to mark vector index dirty")
        logger.info("process_document: doc %s ready (%d chunks)", document_id, document.chunks_total)
        return {'status': 'ready', 'document_id': document_id, 'chunks': document.chunks_total}

    except Exception as exc:
        logger.exception("process_document failed for doc %s: %s", document_id, exc)
        # Stamp 'failed' FIRST so the doc never stays stuck in 'processing' when:
        #   (a) we're running eagerly via `.apply()` and `self.retry()` can't
        #       actually reschedule anything, or
        #   (b) the broker is unreachable and the retry call itself raises.
        # Celery will still retry on top of this if we're running async — if
        # a retry eventually succeeds, the success path overwrites the status
        # back to 'ready'.
        try:
            document.processing_status = 'failed'
            document.processing_error = f"{type(exc).__name__}: {exc}"[:4000]
            document.save(update_fields=['processing_status', 'processing_error', 'updated_at'])
        except Exception:
            logger.exception("process_document: failed to stamp 'failed' status for doc %s",
                             document_id)
        # In eager mode (e.g. the upload view's inline fallback) there's no
        # broker to schedule a retry against — bail with the failure we just stamped.
        try:
            is_eager = bool(getattr(self.request, 'is_eager', False))
        except Exception:
            is_eager = False
        if is_eager:
            return {'status': 'failed', 'document_id': document_id,
                    'error': f"{type(exc).__name__}: {exc}"[:400]}
        # Async Celery path: let the retry machinery take another shot.
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {'status': 'failed', 'document_id': document_id}
        except Exception:
            # Retry was scheduled — the doc currently reads 'failed', but on a
            # successful retry the happy-path branch above will flip it to 'ready'.
            return {'status': 'retrying', 'document_id': document_id}


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

    # 24h reminder: fire whenever the meeting is <= 24h away AND > 15m away (so the
    # 15-minute reminder stage owns the final stretch) AND the 24h reminder hasn't
    # been sent yet. The previous narrow ±window was correct only if cron was
    # punctual; if a worker slipped even 3 minutes, meetings in the missed band
    # lost their reminder. "Still upcoming + not yet sent" is the real condition.
    r24_cutoff_upper = now + _td(hours=24)
    r24_cutoff_lower = now + _td(minutes=15)   # don't double with the 15m stage
    for m in FrontlineMeeting.objects.filter(
        status__in=['scheduled', 'rescheduled'],
        scheduled_at__gt=r24_cutoff_lower,
        scheduled_at__lte=r24_cutoff_upper,
        reminder_24h_sent_at__isnull=True,
    ):
        if _send(m, '24 hours'):
            m.reminder_24h_sent_at = now
            m.save(update_fields=['reminder_24h_sent_at', 'updated_at'])
            results['r24h_sent'] += 1
        else:
            results['failed'] += 1

    # 15-minute reminder: fire whenever the meeting is <= 15m away AND hasn't
    # already started (>= now). Same stateful logic as above. The old ±2.5m
    # window missed meetings when cron lagged; this does not.
    r15_upper = now + _td(minutes=15)
    for m in FrontlineMeeting.objects.filter(
        status__in=['scheduled', 'rescheduled'],
        scheduled_at__gte=now,
        scheduled_at__lte=r15_upper,
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
    # Track companies whose chunk set shrinks so we can invalidate their FAISS index.
    dirty_companies = set()
    # Evaluated in Python because retention is a per-row offset, not a simple cutoff.
    for doc in candidates.only('id', 'retention_days', 'created_at', 'file_path', 'company_id').iterator():
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
                doc_company_id = doc.company_id
                doc.delete()
                deleted += 1
                if doc_company_id:
                    dirty_companies.add(doc_company_id)
                logger.info("prune: deleted expired doc %s", doc_pk)
            except Exception as e:
                logger.exception("prune: failed to delete doc %s: %s", doc.id, e)
    # Mark every affected company's vector index dirty so the next query rebuilds
    # without the deleted chunks.
    if dirty_companies:
        try:
            from Frontline_agent.vector_store import mark_index_dirty
            for cid in dirty_companies:
                mark_index_dirty(cid)
        except Exception:
            logger.exception("prune: failed to invalidate vector indexes")
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


# --------------------------------------------------------------------------
# Inbound email → ticket
# --------------------------------------------------------------------------

@shared_task(name='Frontline_agent.tasks.process_inbound_email',
             bind=True, max_retries=3, default_retry_delay=30)
def process_inbound_email(self, payload: dict):
    """Turn a normalized inbound-email payload into a Ticket + TicketMessage.

    Payload shape matches the dict produced by `inbound_email.ParsedInboundEmail`
    with `company_id` resolved by the webhook view. Attachments are passed as
    a list of {filename, content_type, content_b64, sha256, size_bytes} and
    materialized into TicketAttachment rows + files under MEDIA_ROOT.

    Side effects on a customer reply:
      - Re-open a ticket that is resolved/closed/auto_resolved.
      - Auto-resume SLA if the ticket was previously sla_paused_at.
      - Update `updated_at` via save().
    """
    import base64
    from pathlib import Path
    from django.conf import settings as _s
    from django.contrib.auth.models import User
    from Frontline_agent.models import Ticket, TicketMessage, TicketAttachment
    from Frontline_agent.inbound_email import sanitize_html, strip_quoted_reply

    try:
        company_id = payload.get('company_id')
        if not company_id:
            logger.warning("process_inbound_email: no company_id in payload")
            return {'status': 'ignored', 'reason': 'no_company_id'}

        from core.models import Company
        company = Company.objects.filter(pk=company_id, is_active=True).first()
        if not company:
            return {'status': 'ignored', 'reason': 'company_inactive'}

        from_addr = (payload.get('from_address') or '').strip().lower()
        subject = (payload.get('subject') or '').strip() or '(no subject)'
        body_text_raw = payload.get('body_text') or ''
        body_html_raw = payload.get('body_html') or ''
        body_text = strip_quoted_reply(body_text_raw)
        body_html = sanitize_html(body_html_raw)

        ticket_id = payload.get('existing_ticket_id')
        ticket = Ticket.objects.filter(pk=ticket_id, company=company).first() if ticket_id else None

        # Upsert Contact + attach to ticket. Cheap — one get_or_create + a small update.
        from Frontline_agent.contacts import upsert_contact_from_email, link_ticket_to_contact
        contact = upsert_contact_from_email(
            company=company,
            email=from_addr,
            name=(payload.get('from_name') or '').strip(),
        )

        if not ticket:
            # New thread — create a ticket.
            creator_user = _ensure_system_user()
            ticket = Ticket.objects.create(
                title=subject[:200],
                description=(body_text or body_html_raw or '')[:10000],
                status='new',
                priority='medium',
                company=company,
                created_by=creator_user,
                intent='email_inbound',
                entities={'from_email': from_addr},
                contact=contact,
            )
            if contact:
                # Keep denormalized counters fresh after the insert.
                link_ticket_to_contact(ticket, contact)
            logger.info("Inbound email → new ticket %s for company %s", ticket.id, company.id)

        # Hand-off detection: any inbound message that asks for a human escalates
        # the ticket. Cheap check, runs for both new threads and replies.
        try:
            from Frontline_agent.handoff import detect_handoff_request, trigger_handoff
            if detect_handoff_request(body_text or body_html_raw or subject):
                trigger_handoff(
                    ticket, reason='customer_requested',
                    context={'channel': 'email', 'from_email': from_addr,
                             'customer_text': (body_text or '')[:2000]},
                )
        except Exception:
            logger.exception("inbound-email handoff detection failed")
        else:
            # Reply on an existing thread — re-open + resume SLA if needed.
            changed_fields = []
            if ticket.status in ('resolved', 'closed', 'auto_resolved'):
                ticket.status = 'open'
                ticket.resolved_at = None
                changed_fields += ['status', 'resolved_at']
            if ticket.sla_paused_at:
                paused_delta = (timezone.now() - ticket.sla_paused_at).total_seconds()
                ticket.sla_paused_accumulated_seconds = (
                    (ticket.sla_paused_accumulated_seconds or 0) + int(paused_delta)
                )
                ticket.sla_paused_at = None
                changed_fields += ['sla_paused_at', 'sla_paused_accumulated_seconds']
            if changed_fields:
                changed_fields.append('updated_at')
                ticket.save(update_fields=list(set(changed_fields)))
            # If this pre-existing ticket had no contact (created before this feature),
            # attach it now so the Customer-360 panel picks it up.
            if contact and not ticket.contact_id:
                link_ticket_to_contact(ticket, contact)
            elif contact:
                # Just refresh the denormalized last_seen_at / count
                from Frontline_agent.contacts import recompute_contact_stats
                recompute_contact_stats(contact)

        # Create the inbound TicketMessage row.
        msg = TicketMessage.objects.create(
            ticket=ticket,
            direction='inbound',
            channel='email',
            from_address=from_addr[:320],
            from_name=(payload.get('from_name') or '')[:255],
            to_addresses=payload.get('to_addresses') or [],
            cc_addresses=payload.get('cc_addresses') or [],
            subject=subject[:998],
            body_text=body_text[:500000],
            body_html=body_html[:500000],
            message_id=(payload.get('message_id') or '')[:998],
            in_reply_to=(payload.get('in_reply_to') or '')[:998],
            references=payload.get('references') or [],
            raw_payload={'provider': payload.get('provider'), 'headers': payload.get('raw_headers') or {}},
            is_auto_reply=bool(payload.get('is_auto_reply')),
        )

        # Persist attachments.
        base_dir = Path(_s.MEDIA_ROOT) / 'frontline_ticket_attachments' / str(company.id) / str(ticket.id)
        base_dir.mkdir(parents=True, exist_ok=True)
        for att in payload.get('attachments') or []:
            try:
                content_b64 = att.get('content_b64') or ''
                raw_bytes = base64.b64decode(content_b64) if content_b64 else b''
                if not raw_bytes:
                    continue
                sha = att.get('sha256') or ''
                if not sha:
                    import hashlib as _h
                    sha = _h.sha256(raw_bytes).hexdigest()
                filename = (att.get('filename') or 'attachment.bin')[:240]
                # sanitize to avoid traversal
                from Frontline_agent.document_processor import DocumentProcessor
                safe_name = DocumentProcessor.sanitize_filename(filename)
                out_path = base_dir / f"{sha[:16]}-{safe_name}"
                with open(out_path, 'wb') as fh:
                    fh.write(raw_bytes)
                TicketAttachment.objects.create(
                    ticket_message=msg,
                    filename=filename,
                    content_type=att.get('content_type', '')[:120],
                    size_bytes=len(raw_bytes),
                    storage_path=str(out_path.relative_to(_s.MEDIA_ROOT)),
                    sha256=sha[:64],
                )
            except Exception as exc:
                logger.warning("Failed to persist attachment on msg %s: %s", msg.id, exc)

        return {'status': 'ok', 'ticket_id': ticket.id, 'message_id': msg.id,
                'was_new_ticket': ticket_id is None}

    except Exception as exc:
        logger.exception("process_inbound_email failed: %s", exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {'status': 'failed', 'error': str(exc)[:400]}


# --------------------------------------------------------------------------
# Workflow pause / resume — non-blocking `wait` step
# --------------------------------------------------------------------------

@shared_task(name='Frontline_agent.tasks.resume_workflow_execution',
             bind=True, max_retries=3, default_retry_delay=30)
def resume_workflow_execution(self, execution_id: int):
    """Resume a paused FrontlineWorkflowExecution.

    Reads the pause snapshot saved by `_execute_workflow_steps` into
    `execution.pause_state`, re-enters the executor with the remaining-steps
    list and accumulated results, and finalizes the execution on completion
    (or schedules another resume if the workflow hits another `wait`).
    """
    from Frontline_agent.models import FrontlineWorkflowExecution
    from api.views.frontline_agent import _execute_workflow_steps

    execution = (FrontlineWorkflowExecution.objects
                 .select_related('workflow')
                 .filter(pk=execution_id).first())
    if not execution:
        logger.warning("resume_workflow_execution: execution %s not found", execution_id)
        return {'status': 'missing', 'execution_id': execution_id}
    if execution.status != 'paused':
        # Could have been cancelled, or a duplicate resume fired. Idempotent no-op.
        logger.info("resume_workflow_execution: execution %s status=%s, skipping",
                    execution_id, execution.status)
        return {'status': 'noop', 'execution_id': execution_id, 'current_status': execution.status}
    workflow = execution.workflow
    if workflow is None:
        execution.status = 'failed'
        execution.error_message = 'Workflow deleted while execution was paused'
        execution.completed_at = timezone.now()
        execution.save(update_fields=['status', 'error_message', 'completed_at'])
        return {'status': 'failed', 'execution_id': execution_id, 'reason': 'workflow_missing'}

    snap = execution.pause_state or {}
    remaining_steps = list(snap.get('remaining_steps') or [])
    results_so_far = list(snap.get('results_so_far') or [])
    elapsed_active = float(snap.get('elapsed_active_seconds') or 0.0)
    context_data = dict(snap.get('context_data') or execution.context_data or {})

    # Move back to in_progress while the resume runs so another scheduled
    # resume can't pick the same row if Celery double-delivered.
    execution.status = 'in_progress'
    execution.save(update_fields=['status'])

    try:
        success, result_data, err = _execute_workflow_steps(
            workflow, context_data, execution.executed_by,
            simulate=False,
            execution=execution,
            _steps_override=remaining_steps,
            _prior_results=results_so_far,
            _prior_elapsed=elapsed_active,
        )
    except Exception as exc:
        logger.exception("resume_workflow_execution: executor crashed on execution %s", execution_id)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            execution.status = 'failed'
            execution.error_message = f"{type(exc).__name__}: {exc}"[:4000]
            execution.completed_at = timezone.now()
            execution.save(update_fields=['status', 'error_message', 'completed_at'])
        return {'status': 'retrying_or_failed', 'execution_id': execution_id}

    # If the executor paused AGAIN, state was already persisted by
    # _persist_and_schedule_resume. Just acknowledge and return.
    if result_data and result_data.get('paused'):
        return {'status': 'paused_again', 'execution_id': execution_id,
                'wait_seconds': result_data.get('wait_seconds')}

    # Terminal: the remainder ran to completion (or failed).
    execution.status = 'completed' if success else 'failed'
    execution.result_data = result_data or {}
    execution.error_message = err
    execution.completed_at = timezone.now()
    execution.resume_at = None
    execution.pause_state = {}
    execution.save(update_fields=['status', 'result_data', 'error_message',
                                  'completed_at', 'resume_at', 'pause_state'])
    return {'status': execution.status, 'execution_id': execution_id}


def _ensure_system_user():
    """Return a single reusable 'frontline-inbound' Django user to own tickets
    created from inbound email. Created on first call; idempotent."""
    from django.contrib.auth.models import User
    user, _ = User.objects.get_or_create(
        username='frontline_inbound',
        defaults={'email': 'noreply-inbound@frontline.local', 'is_active': True},
    )
    return user


# --------------------------------------------------------------------------
# HubSpot contact sync (Phase 3 §3.3)
# --------------------------------------------------------------------------

@shared_task(name='Frontline_agent.tasks.sync_contact_to_hubspot',
             bind=True, max_retries=4, default_retry_delay=60)
def sync_contact_to_hubspot(self, contact_id: int):
    """Push one Contact row into the tenant's HubSpot portal.

    Idempotent — `HubSpotClient.upsert_contact` searches by email first so
    re-runs don't duplicate the record. Non-retriable errors (bad token /
    bad payload) flip `hubspot_config.enabled = False` to stop the bleed,
    and record the message in `last_error` so the UI can surface it.
    """
    from Frontline_agent.models import Contact
    from Frontline_agent.crm.hubspot import HubSpotClient, HubSpotError
    from django.utils import timezone as _tz

    contact = Contact.objects.select_related('company').filter(pk=contact_id).first()
    if not contact:
        return {'status': 'missing', 'contact_id': contact_id}
    company = contact.company
    if not company:
        return {'status': 'no_company', 'contact_id': contact_id}

    cfg = company.hubspot_config or {}
    if not cfg.get('enabled') or not cfg.get('access_token'):
        return {'status': 'disabled', 'contact_id': contact_id}

    try:
        client = HubSpotClient(access_token=cfg['access_token'])
        hs_id = client.upsert_contact(
            email=contact.email,
            name=contact.name or '',
            phone=contact.phone or '',
        )
        # Persist the mirror id so we can do updates instead of searches next time.
        contact.external_source = 'hubspot'
        contact.external_id = (hs_id or '')[:128]
        contact.external_synced_at = _tz.now()
        contact.save(update_fields=['external_source', 'external_id',
                                    'external_synced_at', 'updated_at'])
        # Clear any sticky error on success.
        if cfg.get('last_error'):
            cfg['last_error'] = ''
            company.hubspot_config = cfg
            company.save(update_fields=['hubspot_config', 'updated_at'])
        return {'status': 'ok', 'contact_id': contact.id, 'hubspot_id': hs_id}
    except HubSpotError as exc:
        msg = str(exc)[:400]
        if not exc.retriable:
            # Shut sync off for this tenant so we don't keep calling with a bad token.
            cfg['enabled'] = False
            cfg['last_error'] = msg
            company.hubspot_config = cfg
            company.save(update_fields=['hubspot_config', 'updated_at'])
            logger.warning("HubSpot sync disabled for company %s: %s", company.id, msg)
            return {'status': 'disabled_after_error', 'error': msg}
        # Retriable — back off with Celery's retry machinery.
        try:
            raise self.retry(exc=exc, countdown=min(60 * (2 ** self.request.retries), 1800))
        except self.MaxRetriesExceededError:
            cfg['last_error'] = msg
            company.hubspot_config = cfg
            company.save(update_fields=['hubspot_config', 'updated_at'])
            return {'status': 'failed', 'error': msg}


@shared_task(name='Frontline_agent.tasks.hubspot_sync_all_contacts')
def hubspot_sync_all_contacts(company_id: int, batch_size: int = 200):
    """Backfill task — enqueue a per-contact sync for every Contact in a company.
    Invoked by `POST /frontline/crm/hubspot/sync-all/`. Each row is its own
    Celery job so failures on one don't block the rest."""
    from Frontline_agent.models import Contact
    ids = list(Contact.objects.filter(company_id=company_id).values_list('id', flat=True))
    for i in range(0, len(ids), batch_size):
        for cid in ids[i:i + batch_size]:
            sync_contact_to_hubspot.delay(cid)
    return {'enqueued': len(ids), 'company_id': company_id}

"""HR Support Agent — Celery tasks.

Mirrors the Frontline agent's task layout where it makes sense, so the same
shape (broker-probe-then-fallback, status-stamp-before-retry) carries over.
"""
import json
import logging
from datetime import timedelta
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone


logger = logging.getLogger(__name__)


# Document types that get LLM auto-extraction immediately after embedding.
# We pick the per-type schema so the LLM extracts only the fields we'll use
# downstream (drawer UI, expiry-date walker, etc.).
_AUTO_EXTRACT_TYPES = {'offer_letter', 'contract', 'payslip', 'id_proof'}
_EXTRACT_SCHEMAS = {
    'offer_letter': [
        'employee_name', 'job_title', 'department', 'start_date',
        'compensation', 'currency', 'reporting_manager',
        'work_location', 'probation_period_months',
    ],
    'contract': [
        'employee_name', 'job_title', 'department', 'start_date', 'end_date',
        'compensation', 'currency', 'reporting_manager', 'work_location',
        'probation_period_months', 'notice_period_days',
    ],
    'payslip': [
        'employee_name', 'pay_period_start', 'pay_period_end',
        'gross_salary', 'net_salary', 'currency',
        'tax_deductions', 'other_deductions',
    ],
    'id_proof': [
        'employee_name', 'document_number', 'issuing_country',
        'issued_date', 'expiry_date',
    ],
}


# Default retention windows (days) by HR document type.
# Numbers tuned to common compliance minimums — tenants override per-doc.
RETENTION_DEFAULTS_DAYS = {
    'payroll': 365 * 7,            # 7 years (US IRS / most jurisdictions)
    'payslip': 365 * 7,
    'contract': 365 * 7,
    'offer_letter': 365 * 5,
    'performance_review': 365 * 5,
    'leave_form': 365 * 3,
    'id_proof': 365 * 3,
    'compliance': 365 * 7,
    'training': 365 * 3,
    'benefits': 365 * 5,
    # Living docs — no retention by default
    'handbook': None,
    'policy': None,
    'procedure': None,
    'other': None,
}


# --------------------------------------------------------------------------
# process_hr_document — parse + chunk + embed an uploaded HRDocument
# --------------------------------------------------------------------------

@shared_task(name='hr_agent.tasks.process_hr_document',
             bind=True, max_retries=2, default_retry_delay=60)
def process_hr_document(self, document_id):
    """Parse, chunk, and embed an uploaded HRDocument.

    Reuses Frontline's `DocumentProcessor` for text extraction + the same
    `EmbeddingService`. On success, sets `processing_status='ready'` and
    `is_indexed=True` so retrieval picks the doc up.

    Failure handling matches Frontline's hardened pattern:
      * Stamp the doc as 'failed' BEFORE attempting retry, so an eager run
        (broker down → inline fallback) doesn't leave the row stuck in
        'processing'.
      * In eager mode (`self.request.is_eager`) skip the retry call entirely
        because there's no broker to schedule against.
    """
    from hr_agent.models import HRDocument, HRDocumentChunk
    from Frontline_agent.document_processor import DocumentProcessor
    from core.Frontline_agent.embedding_service import EmbeddingService

    import os as _os

    document = HRDocument.objects.filter(id=document_id).first()
    if not document:
        logger.warning("process_hr_document: HRDocument %s not found", document_id)
        return {'status': 'not_found', 'document_id': document_id}

    document.processing_status = 'processing'
    document.processing_error = ''
    document.chunks_processed = 0
    document.chunks_total = 0
    document.save(update_fields=['processing_status', 'processing_error',
                                 'chunks_processed', 'chunks_total', 'updated_at'])

    HRDocumentChunk.objects.filter(document=document).delete()

    try:
        # Resolve relative path against MEDIA_ROOT (Celery worker CWD isn't MEDIA_ROOT).
        fp = document.file_path
        if fp and not _os.path.isabs(fp):
            fp = str(Path(settings.MEDIA_ROOT) / fp)
        # `get_file_format` keys off the extension — pass the basename, not the title.
        filename_with_ext = _os.path.basename(fp)
        processor = DocumentProcessor()
        result = processor.process_document(fp, filename_with_ext)
        if not result.get('success'):
            raise RuntimeError(result.get('error') or 'process_hr_document failed')

        extracted_text = result.get('extracted_text', '') or ''
        document.document_content = extracted_text
        document.file_hash = result.get('file_hash', document.file_hash)

        chunk_size = int(getattr(settings, 'HR_CHUNK_SIZE',
                                 getattr(settings, 'FRONTLINE_CHUNK_SIZE', 4000)))
        overlap = int(getattr(settings, 'HR_CHUNK_OVERLAP',
                              getattr(settings, 'FRONTLINE_CHUNK_OVERLAP', 200)))
        overlap = max(0, min(overlap, max(0, chunk_size - 1)))

        text_to_chunk = f"{document.title}\n{document.description}\n{extracted_text}".strip()
        # Section-aware chunking for handbook / policy / procedure / training /
        # compliance / benefits — splits on headings (Markdown #, ALL-CAPS,
        # `Article X`, `Section X.Y`, `4.2 Title`) so citations point at a
        # whole section rather than a sentence fragment. Falls back to fixed
        # chunks when no headings exist. Other doc types use the naive split.
        from hr_agent.chunking import chunk_with_headings, SECTION_AWARE_TYPES
        if document.document_type in SECTION_AWARE_TYPES:
            chunks = chunk_with_headings(
                text_to_chunk, max_chunk_size=chunk_size, overlap=overlap,
            )
            logger.info("process_hr_document: doc %s chunked section-aware (%d sections)",
                        document_id, len(chunks))
        else:
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
                HRDocumentChunk(
                    document=document,
                    chunk_index=i + j,
                    chunk_text=chunk_text,
                    embedding=(json.dumps(emb) if emb else None),
                )
                for j, (chunk_text, emb) in enumerate(zip(batch, embeddings))
            ]
            HRDocumentChunk.objects.bulk_create(rows)
            document.chunks_processed = i + len(batch)
            document.save(update_fields=['chunks_processed', 'updated_at'])

        document.processing_status = 'ready'
        document.is_indexed = True
        document.embedding_model = embedding_service.embedding_model if has_embeddings else ''
        document.save(update_fields=['processing_status', 'is_indexed',
                                     'embedding_model', 'updated_at'])
        logger.info("process_hr_document: doc %s ready (%d chunks)", document_id, document.chunks_total)

        # Auto-extract for structured doc types — populates `extracted_fields`
        # so the document-expiry walker, the employee detail drawer, and the
        # offer-letter cards have data without a manual "Extract" click.
        # Best-effort: errors here log + move on, the doc is still 'ready'.
        if document.document_type in _AUTO_EXTRACT_TYPES and (extracted_text or '').strip():
            try:
                from core.HR_agent.hr_agent import HRAgent
                schema = _EXTRACT_SCHEMAS.get(document.document_type)
                agent = HRAgent(company_id=document.company_id)
                result = agent.extract_from_document(extracted_text, schema=schema)
                if result.get('success') and isinstance(result.get('data'), dict):
                    document.extracted_fields = {
                        **(document.extracted_fields or {}), **result['data'],
                    }
                    document.save(update_fields=['extracted_fields', 'updated_at'])
                    logger.info("process_hr_document: doc %s auto-extracted %d fields",
                                document_id, len(result['data']))
            except Exception:
                logger.exception("process_hr_document: auto-extract failed for doc %s",
                                 document_id)
        return {'status': 'ready', 'document_id': document_id, 'chunks': document.chunks_total}

    except Exception as exc:
        logger.exception("process_hr_document failed for doc %s: %s", document_id, exc)
        try:
            document.processing_status = 'failed'
            document.processing_error = f"{type(exc).__name__}: {exc}"[:4000]
            document.save(update_fields=['processing_status', 'processing_error', 'updated_at'])
        except Exception:
            logger.exception("Failed to stamp 'failed' on HRDocument %s", document_id)

        try:
            is_eager = bool(getattr(self.request, 'is_eager', False))
        except Exception:
            is_eager = False
        if is_eager:
            return {'status': 'failed', 'document_id': document_id,
                    'error': f"{type(exc).__name__}: {exc}"[:400]}
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {'status': 'failed', 'document_id': document_id}
        except Exception:
            return {'status': 'retrying', 'document_id': document_id}


# --------------------------------------------------------------------------
# Leave accrual — credits employees per their LeaveAccrualPolicy
# --------------------------------------------------------------------------

@shared_task(name='hr_agent.tasks.accrue_leave_balances')
def accrue_leave_balances():
    """Run every active `LeaveAccrualPolicy` and credit each active Employee
    in the policy's company. Idempotent within a period via `last_run_at`:
      * monthly  → at most once per calendar month
      * biweekly → at most once per 14 days
      * annual   → at most once per calendar year

    Per active employee in the company, top up `LeaveBalance.accrued_days`
    by `policy.days_per_period`, capped at `policy.max_balance` if set.
    """
    from decimal import Decimal
    from hr_agent.models import LeaveAccrualPolicy, LeaveBalance, Employee

    now = timezone.now()
    today = now.date()
    results = {'policies_run': 0, 'rows_credited': 0, 'skipped': 0}

    for pol in LeaveAccrualPolicy.objects.filter(is_active=True).select_related('company'):
        # Period gate
        if pol.last_run_at:
            last = pol.last_run_at
            if pol.period == 'monthly' and (last.year, last.month) == (now.year, now.month):
                results['skipped'] += 1; continue
            if pol.period == 'biweekly' and (now - last).days < 14:
                results['skipped'] += 1; continue
            if pol.period == 'annual' and last.year == now.year:
                results['skipped'] += 1; continue

        emp_qs = Employee.objects.filter(
            company=pol.company,
            employment_status__in=['active', 'probation', 'on_leave'],
        )
        delta = Decimal(str(pol.days_per_period))
        cap = pol.max_balance  # may be None

        credited = 0
        for emp in emp_qs.only('id'):
            bal, _ = LeaveBalance.objects.get_or_create(
                employee_id=emp.id, leave_type=pol.leave_type,
            )
            new_accrued = (bal.accrued_days or 0) + delta
            if cap is not None:
                # Cap on accrued + carryover, leaving used as-is.
                projected_total = new_accrued + (bal.carried_over_days or 0)
                if projected_total > cap:
                    new_accrued = cap - (bal.carried_over_days or 0)
                    if new_accrued < (bal.accrued_days or 0):
                        # Already over the cap — don't change.
                        continue
            bal.accrued_days = new_accrued
            bal.save(update_fields=['accrued_days', 'updated_at'])
            credited += 1

        pol.last_run_at = now
        pol.save(update_fields=['last_run_at', 'updated_at'])
        results['policies_run'] += 1
        results['rows_credited'] += credited
        logger.info("accrue_leave_balances: policy %s (%s/%s) credited %d employees",
                    pol.id, pol.leave_type, pol.period, credited)

    if results['policies_run'] or results['skipped']:
        logger.info("accrue_leave_balances: %s", results)
    return results


# --------------------------------------------------------------------------
# Workflow resume (paired with `hr_agent.workflow_engine`)
# --------------------------------------------------------------------------

@shared_task(name='hr_agent.tasks.resume_hr_workflow_execution',
             bind=True, max_retries=3, default_retry_delay=30)
def resume_hr_workflow_execution(self, execution_id: int):
    """Continue a paused `HRWorkflowExecution` after a `wait` step. Reads the
    pause snapshot from `execution.pause_state`, re-enters the executor with
    the remaining steps + accumulated results + active-time budget. On
    completion (or further pauses), updates the execution row."""
    from hr_agent.models import HRWorkflowExecution
    from hr_agent.workflow_engine import execute_workflow

    execution = (HRWorkflowExecution.objects
                 .select_related('workflow').filter(pk=execution_id).first())
    if not execution:
        logger.warning("resume_hr_workflow_execution: %s not found", execution_id)
        return {'status': 'missing', 'execution_id': execution_id}
    if execution.status != 'paused':
        logger.info("resume_hr_workflow_execution: %s status=%s, skipping",
                    execution_id, execution.status)
        return {'status': 'noop', 'execution_id': execution_id,
                'current_status': execution.status}
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

    execution.status = 'in_progress'
    execution.save(update_fields=['status'])

    try:
        success, result_data, err = execute_workflow(
            workflow, context_data, execution.executed_by, simulate=False,
            execution=execution,
            _steps_override=remaining_steps,
            _prior_results=results_so_far,
            _prior_elapsed=elapsed_active,
        )
    except Exception as exc:
        logger.exception("resume_hr_workflow_execution: executor crashed (exec=%s)", execution_id)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            execution.status = 'failed'
            execution.error_message = f"{type(exc).__name__}: {exc}"[:4000]
            execution.completed_at = timezone.now()
            execution.save(update_fields=['status', 'error_message', 'completed_at'])
        return {'status': 'retrying_or_failed', 'execution_id': execution_id}

    if result_data and result_data.get('paused'):
        return {'status': 'paused_again', 'execution_id': execution_id,
                'wait_seconds': result_data.get('wait_seconds')}

    execution.status = 'completed' if success else 'failed'
    execution.result_data = result_data or {}
    execution.error_message = err
    execution.completed_at = timezone.now()
    execution.resume_at = None
    execution.pause_state = {}
    execution.save(update_fields=['status', 'result_data', 'error_message',
                                  'completed_at', 'resume_at', 'pause_state'])
    return {'status': execution.status, 'execution_id': execution_id}


# --------------------------------------------------------------------------
# Notification scheduler tasks (Batch 3) — implemented below
# --------------------------------------------------------------------------

# Exponential retry ladder (minutes).
_NOTIFY_RETRY_BACKOFF_MINUTES = [5, 30, 120]


def _schedule_notify_retry(notif, error_msg):
    """Mirrors Frontline's _schedule_retry but for HRScheduledNotification."""
    notif.attempts = (notif.attempts or 0) + 1
    notif.last_error = (error_msg or '')[:4000]
    if notif.attempts >= (notif.max_attempts or 3):
        notif.status = 'dead_lettered'
        notif.dead_lettered_at = timezone.now()
        notif.next_retry_at = None
        notif.save(update_fields=['attempts', 'last_error', 'status',
                                  'dead_lettered_at', 'next_retry_at'])
        logger.warning("HR notification %s dead-lettered after %d attempts: %s",
                       notif.id, notif.attempts, error_msg)
        return
    idx = min(notif.attempts - 1, len(_NOTIFY_RETRY_BACKOFF_MINUTES) - 1)
    wait_minutes = _NOTIFY_RETRY_BACKOFF_MINUTES[idx]
    notif.status = 'pending'
    notif.next_retry_at = timezone.now() + timedelta(minutes=wait_minutes)
    notif.save(update_fields=['attempts', 'last_error', 'status', 'next_retry_at'])


@shared_task(name='hr_agent.tasks.process_hr_scheduled_notifications')
def process_hr_scheduled_notifications():
    """Sender for `HRScheduledNotification` — picks pending rows whose
    `scheduled_at` has passed, sends via Django's email backend, and applies
    exponential backoff on failures with eventual dead-lettering.

    Capped at 200 rows per tick. Beat cron should run every 60s.
    """
    from django.core.mail import send_mail
    from django.db.models import Q
    from hr_agent.models import HRScheduledNotification

    now = timezone.now()
    due = HRScheduledNotification.objects.filter(
        status='pending', scheduled_at__lte=now,
    ).filter(Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now))

    processed = sent = failed = dead = 0

    for notif in due[:200]:
        processed += 1
        template = notif.template
        if not template:
            _schedule_notify_retry(notif, 'Template was deleted')
            failed += 1
            continue

        recipient_email = (notif.recipient_email or '').strip()
        if not recipient_email and notif.recipient_employee_id:
            recipient_email = (notif.recipient_employee.work_email or '').strip()
        if not recipient_email:
            _schedule_notify_retry(notif, 'No recipient_email')
            failed += 1
            continue

        # Render template body — light templating with {{placeholders}}
        body = _render_template_body(template.body, notif.context or {})
        subject = _render_template_body(template.subject or template.name, notif.context or {})

        ok, err = False, None
        try:
            if template.channel == 'email':
                send_mail(
                    subject=subject or 'HR Notification',
                    message=body,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
                    recipient_list=[recipient_email],
                    fail_silently=False,
                )
                ok = True
            else:
                err = f"Channel '{template.channel}' not implemented for hr_agent"
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"

        if ok:
            notif.status = 'sent'
            notif.sent_at = timezone.now()
            notif.next_retry_at = None
            notif.attempts = (notif.attempts or 0) + 1
            notif.save(update_fields=['status', 'sent_at', 'next_retry_at', 'attempts'])
            sent += 1
        else:
            _schedule_notify_retry(notif, err or 'Send failed')
            if notif.status == 'dead_lettered':
                dead += 1
            else:
                failed += 1

    if processed:
        logger.info("process_hr_scheduled_notifications: processed=%d sent=%d failed=%d dead=%d",
                    processed, sent, failed, dead)
    return {'processed': processed, 'sent': sent, 'failed': failed, 'dead_lettered': dead}


def _render_template_body(body, context):
    """Tiny `{{key}}` template substitution. Same shape as Frontline's
    `_render_template_body` so HR templates feel familiar to authors."""
    if not body:
        return ''
    out = body
    for k, v in (context or {}).items():
        out = out.replace('{{' + str(k) + '}}', str(v) if v is not None else '')
    return out


@shared_task(name='hr_agent.tasks.walk_hr_time_based_events')
def walk_hr_time_based_events():
    """Walk time-based HR events and fan out into `HRScheduledNotification`
    rows so the regular sender picks them up.

    Events fanned out today:
      * **probation_ending** — match templates with
        ``trigger_config.on='probation_ending'``; when an employee's
        probation_end_date is exactly N days away (default 7), schedule one
        notification per template. Idempotent — checks for existing pending
        rows for the same (template, employee, scheduled_at) tuple.
      * **birthday** / **work_anniversary** — same pattern, against
        date_of_birth / work_anniversary_month_day.
      * **document_expiring** — for HRDocument rows with `extracted_fields.expiry_date`
        in the next 30 days.

    Run daily via Beat (e.g. once at 06:00 UTC).
    """
    from datetime import date as _date
    from hr_agent.models import (
        Employee, HRDocument, HRNotificationTemplate, HRScheduledNotification,
    )

    today = timezone.now().date()
    created_total = 0

    from django.db.models import Q

    for tpl in HRNotificationTemplate.objects.all():
        cfg = tpl.trigger_config or {}
        event = cfg.get('on') or tpl.notification_type
        days_before = int(cfg.get('days_before') or 0)
        target_date = today + timedelta(days=days_before) if days_before else today

        if event == 'probation_ending':
            qs = Employee.objects.filter(
                company_id=tpl.company_id,
                probation_end_date=target_date,
            )
            for emp in qs:
                created_total += _ensure_scheduled(tpl, emp, target_date,
                                                   context={'event_date': target_date.isoformat(),
                                                            'employee_name': emp.full_name})

        elif event == 'birthday':
            qs = Employee.objects.filter(
                company_id=tpl.company_id,
                date_of_birth__month=today.month,
                date_of_birth__day=today.day,
            )
            for emp in qs:
                created_total += _ensure_scheduled(tpl, emp, today,
                                                   context={'event_date': today.isoformat(),
                                                            'employee_name': emp.full_name})

        elif event == 'work_anniversary':
            md = today.strftime('%m-%d')
            # Match either the explicit anniversary string OR the start_date's month+day.
            qs = Employee.objects.filter(company_id=tpl.company_id).filter(
                Q(work_anniversary_month_day=md)
                | Q(start_date__month=today.month, start_date__day=today.day)
            )
            for emp in qs:
                created_total += _ensure_scheduled(tpl, emp, today,
                                                   context={'event_date': today.isoformat(),
                                                            'employee_name': emp.full_name})

        elif event == 'document_expiring':
            soon = today + timedelta(days=days_before or 30)
            docs = HRDocument.objects.filter(company_id=tpl.company_id).exclude(
                extracted_fields__expiry_date__isnull=True,
            )
            for d in docs:
                expiry = (d.extracted_fields or {}).get('expiry_date')
                try:
                    expiry_dt = _date.fromisoformat(str(expiry))
                except (TypeError, ValueError):
                    continue
                if today <= expiry_dt <= soon and d.employee_id:
                    created_total += _ensure_scheduled(
                        tpl, d.employee, expiry_dt,
                        context={'event_date': expiry_dt.isoformat(),
                                 'document_title': d.title,
                                 'employee_name': d.employee.full_name},
                        related_document_id=d.id,
                    )

    logger.info("walk_hr_time_based_events: scheduled %d notifications", created_total)
    return {'scheduled': created_total}


def _ensure_scheduled(template, employee, when, *, context=None, related_document_id=None):
    """Create exactly one HRScheduledNotification per (template, employee, day)
    to keep daily walks idempotent. Returns 1 on create, 0 on existing."""
    from hr_agent.models import HRScheduledNotification

    day_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    exists = HRScheduledNotification.objects.filter(
        template=template, recipient_employee=employee,
        scheduled_at__gte=day_start, scheduled_at__lt=day_end,
    ).exists()
    if exists:
        return 0
    HRScheduledNotification.objects.create(
        company_id=template.company_id,
        template=template,
        recipient_employee=employee,
        recipient_email=employee.work_email,
        scheduled_at=timezone.now(),  # send next tick
        status='pending',
        context=context or {},
        related_document_id=related_document_id,
    )
    return 1


# --------------------------------------------------------------------------
# Meeting reminders — port of Frontline's send_meeting_reminders
# --------------------------------------------------------------------------

@shared_task(name='hr_agent.tasks.send_hr_meeting_reminders')
def send_hr_meeting_reminders():
    """24h + 15min reminder emails for upcoming HR meetings.

    Mirrors `Frontline_agent.tasks.send_meeting_reminders` shape. Run every 5
    minutes via Beat. Asymmetric -3m..+2m window around each anchor avoids
    missed reminders on a punctual cron and matches Frontline's convention.
    """
    from datetime import timedelta as _td
    from django.core.mail import send_mail
    from hr_agent.models import HRMeeting

    now = timezone.now()
    results = {'r24h_sent': 0, 'r15m_sent': 0, 'failed': 0}

    def _recipients(m: 'HRMeeting'):
        emails = set()
        if m.organizer and m.organizer.work_email:
            emails.add(m.organizer.work_email)
        for p in m.participants.all():
            if p.work_email:
                emails.add(p.work_email)
        return list(emails)

    def _send(m, label):
        subject = f"Reminder ({label}): {m.title}"
        when = m.scheduled_at.isoformat() if m.scheduled_at else '(unknown)'
        parts = [
            f"This is a reminder that '{m.title}' is scheduled for {when} ({m.timezone_name}).",
            f"Type: {m.get_meeting_type_display()}.",
            f"Duration: {m.duration_minutes} minutes.",
        ]
        if m.meeting_link:
            parts.append(f"Meeting link: {m.meeting_link}")
        if m.location:
            parts.append(f"Location: {m.location}")
        if m.description:
            parts.append(""); parts.append(m.description)
        recipients = _recipients(m)
        if not recipients:
            return False
        try:
            send_mail(
                subject=subject, message="\n\n".join(parts),
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
                recipient_list=recipients, fail_silently=False,
            )
            return True
        except Exception as exc:
            logger.warning("HR meeting reminder send failed for meeting %s: %s", m.id, exc)
            return False

    r24_lo = now + _td(hours=24) - _td(minutes=3)
    r24_hi = now + _td(hours=24) + _td(minutes=2)
    for m in HRMeeting.objects.filter(
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

    r15_lo = now + _td(minutes=12)
    r15_hi = now + _td(minutes=17)
    for m in HRMeeting.objects.filter(
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
        logger.info("send_hr_meeting_reminders: %s", results)
    return results

"""HR Support Agent — DRF views.

Scaffold-stage views: each of the five sub-agents has at least one working
endpoint plus stubs (clearly marked) for the deeper functionality. Same
auth + throttle pattern as Frontline:

    @api_view([...])
    @authentication_classes([CompanyUserTokenAuthentication])
    @permission_classes([IsCompanyUserOnly])
    @throttle_classes([HRCRUDThrottle])
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path

from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.response import Response
from django.conf import settings
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Count, Q

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.models import CompanyUser

from hr_agent.models import (
    Employee, LeaveBalance, LeaveRequest,
    HRDocument, HRDocumentChunk,
    HRWorkflow, HRWorkflowExecution,
    HRMeeting,
    HRNotificationTemplate, HRScheduledNotification,
    HRKnowledgeChat, HRKnowledgeChatMessage,
)
from hr_agent.throttling import (
    HRPublicThrottle, HRLLMThrottle, HRUploadThrottle, HRCRUDThrottle,
)
from core.HR_agent.hr_agent import HRAgent
# Re-use Frontline's hardened helpers — file validation + broker probe.
from Frontline_agent.document_processor import DocumentProcessor

logger = logging.getLogger(__name__)


def _hr_celery_broker_ready(timeout_seconds: float = 0.5) -> bool:
    """TCP probe of the Celery broker — fast-fails when Redis is down so
    upload doesn't stall in Kombu's ~100s connect-retry loop. Same shape as
    `api.views.frontline_agent._celery_broker_ready`."""
    import socket
    from urllib.parse import urlparse
    from celery import current_app
    try:
        url = current_app.conf.broker_url or ''
        parsed = urlparse(url)
        host = parsed.hostname or 'localhost'
        default_port = 6379 if (parsed.scheme or '').startswith('redis') else 5672
        port = parsed.port or default_port
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except Exception:
        return False


def _hr_get_or_create_user_for_company_user(company_user):
    """Get or create a Django User for a CompanyUser. Mirrors the Frontline
    helper — needed because the `uploaded_by` FK on HRDocument points at
    `auth.User`, not `core.CompanyUser`."""
    try:
        return User.objects.get(email=company_user.email)
    except User.DoesNotExist:
        username = f"company_user_{company_user.id}_{company_user.email}"
        return User.objects.create_user(
            username=username, email=company_user.email, password=None,
            first_name=(company_user.full_name.split()[0] if company_user.full_name else ''),
            last_name=(' '.join(company_user.full_name.split()[1:])
                       if company_user.full_name and len(company_user.full_name.split()) > 1 else ''),
        )


# ============================================================================
# Helpers
# ============================================================================

def _company_employee_or_404(request, employee_id):
    """Lookup an Employee scoped to the caller's company."""
    company = request.user.company
    emp = Employee.objects.filter(pk=employee_id, company=company).first()
    if not emp:
        return None, Response(
            {'status': 'error', 'message': 'Employee not found'},
            status=status.HTTP_404_NOT_FOUND,
        )
    return emp, None


def _resolve_asker_role(company_user: CompanyUser) -> str:
    """Map a CompanyUser.role to a knowledge confidentiality bucket."""
    role = (company_user.role or '').lower()
    if role in ('owner', 'admin', 'hr_agent'):
        return 'hr'
    if role == 'manager':
        return 'manager'
    return 'employee'


def _serialize_employee(e: Employee) -> dict:
    return {
        'id': e.id,
        'full_name': e.full_name,
        'work_email': e.work_email,
        'job_title': e.job_title,
        'department': e.department,
        'manager_id': e.manager_id,
        'employment_status': e.employment_status,
        'employment_type': e.employment_type,
        'start_date': e.start_date.isoformat() if e.start_date else None,
        'probation_end_date': e.probation_end_date.isoformat() if e.probation_end_date else None,
        'date_of_birth': e.date_of_birth.isoformat() if e.date_of_birth else None,
        'timezone_name': e.timezone_name,
    }


# ============================================================================
# Employees — basic CRUD (HR foundation)
# ============================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_employees(request):
    """List employees in the caller's company. Supports ?q=substring,
    ?department=, ?status=, ?limit/?offset (defaults 50/0)."""
    try:
        company = request.user.company
        qs = Employee.objects.filter(company=company)
        q = (request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(Q(full_name__icontains=q) | Q(work_email__icontains=q))
        if request.GET.get('department'):
            qs = qs.filter(department__iexact=request.GET['department'])
        if request.GET.get('status'):
            qs = qs.filter(employment_status=request.GET['status'])
        try:
            limit = max(1, min(int(request.GET.get('limit') or 50), 200))
            offset = max(0, int(request.GET.get('offset') or 0))
        except ValueError:
            limit, offset = 50, 0
        total = qs.count()
        rows = [_serialize_employee(e) for e in qs.order_by('full_name')[offset:offset + limit]]
        return Response({'status': 'success', 'data': rows,
                         'pagination': {'total': total, 'limit': limit, 'offset': offset}})
    except Exception:
        logger.exception("list_employees failed")
        return Response({'status': 'error', 'message': 'Failed to list employees'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def create_employee(request):
    try:
        company = request.user.company
        d = request.data or {}
        email = (d.get('work_email') or '').strip().lower()
        if not email or '@' not in email:
            return Response({'status': 'error', 'message': 'work_email is required'},
                            status=status.HTTP_400_BAD_REQUEST)
        if Employee.objects.filter(company=company, work_email__iexact=email).exists():
            return Response({'status': 'error', 'message': 'Employee with this email already exists'},
                            status=status.HTTP_400_BAD_REQUEST)
        e = Employee.objects.create(
            company=company,
            full_name=(d.get('full_name') or '').strip()[:255],
            work_email=email,
            personal_email=(d.get('personal_email') or '')[:254],
            phone=(d.get('phone') or '')[:40],
            job_title=(d.get('job_title') or '')[:160],
            department=(d.get('department') or '')[:120],
            employment_status=d.get('employment_status') or 'active',
            employment_type=d.get('employment_type') or 'full_time',
        )
        return Response({'status': 'success', 'data': _serialize_employee(e)},
                        status=status.HTTP_201_CREATED)
    except Exception:
        logger.exception("create_employee failed")
        return Response({'status': 'error', 'message': 'Failed to create employee'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# 1. Knowledge Q&A
# ============================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRLLMThrottle])
def hr_knowledge_qa(request):
    """Ask the HR knowledge agent. Personalises the answer to the asking
    employee when the CompanyUser is linked to one (the HRAgent stitches in
    leave balance / manager / department from `Employee`)."""
    try:
        company_user = request.user
        company = company_user.company
        question = (request.data.get('question') or '').strip()
        if not question:
            return Response({'status': 'error', 'message': 'question is required'},
                            status=status.HTTP_400_BAD_REQUEST)
        asker_employee = (Employee.objects.filter(company=company, company_user=company_user).first()
                          or Employee.objects.filter(company=company, work_email__iexact=company_user.email).first())
        agent = HRAgent(company_id=company.id)
        result = agent.answer_question(
            question,
            asker_role=_resolve_asker_role(company_user),
            asker_employee=asker_employee,
        )
        return Response({'status': 'success', 'data': result})
    except Exception:
        logger.exception("hr_knowledge_qa failed")
        return Response({'status': 'error', 'message': 'Failed to answer question'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# 2. Document Processing
# ============================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_hr_documents(request):
    """List HR documents visible to the caller (gated by confidentiality)."""
    try:
        company = request.user.company
        cu = request.user
        role = _resolve_asker_role(cu)
        qs = HRDocument.objects.filter(company=company)
        from core.HR_agent.services import _allowed_confidentialities
        qs = qs.filter(confidentiality__in=_allowed_confidentialities(role))
        if role != 'hr':
            asker_emp = Employee.objects.filter(company=company, company_user=cu).first()
            qs = qs.filter(Q(employee__isnull=True) | Q(employee=asker_emp))
        doc_type = request.GET.get('document_type')
        if doc_type:
            qs = qs.filter(document_type=doc_type)
        rows = [{
            'id': d.id, 'title': d.title, 'document_type': d.document_type,
            'confidentiality': d.confidentiality,
            'employee_id': d.employee_id,
            'file_format': d.file_format, 'file_size': d.file_size,
            'processing_status': d.processing_status, 'is_indexed': d.is_indexed,
            'chunks_processed': d.chunks_processed, 'chunks_total': d.chunks_total,
            'created_at': d.created_at.isoformat(),
        } for d in qs.order_by('-created_at')[:200]]
        return Response({'status': 'success', 'data': rows, 'count': len(rows)})
    except Exception:
        logger.exception("list_hr_documents failed")
        return Response({'status': 'error', 'message': 'Failed to list documents'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRUploadThrottle])
def upload_hr_document(request):
    """Upload an HR document. Validates content (magic bytes), saves to disk
    under MEDIA_ROOT/hr_documents/<company>/, creates the `HRDocument` row,
    then dispatches `process_hr_document` to Celery for parse + chunk + embed.

    Body (multipart/form-data):
        file               required
        title              optional (defaults to filename)
        description        optional
        document_type      one of HRDocument.DOCUMENT_TYPE_CHOICES (default 'policy')
        confidentiality    one of public|employee|manager|hr_only (default 'employee')
        employee_id        optional — FK to a personal-doc owner
        retention_days     optional override; otherwise defaults from
                           `RETENTION_DEFAULTS_DAYS` per document_type
    """
    try:
        company_user = request.user
        company = company_user.company
        user = _hr_get_or_create_user_for_company_user(company_user)

        if 'file' not in request.FILES:
            return Response({'status': 'error', 'message': 'No file provided'},
                            status=status.HTTP_400_BAD_REQUEST)

        uploaded = request.FILES['file']
        if uploaded.size > 50 * 1024 * 1024:
            return Response({'status': 'error', 'message': 'File size exceeds 50MB limit'},
                            status=status.HTTP_400_BAD_REQUEST)

        title = (request.POST.get('title') or uploaded.name).strip() or uploaded.name
        description = (request.POST.get('description') or '').strip()
        document_type = (request.POST.get('document_type') or 'policy').strip()
        confidentiality = (request.POST.get('confidentiality') or 'employee').strip().lower()
        if confidentiality not in ('public', 'employee', 'manager', 'hr_only'):
            confidentiality = 'employee'

        # Optional personal-doc link
        employee = None
        if request.POST.get('employee_id'):
            employee = Employee.objects.filter(pk=request.POST['employee_id'], company=company).first()
            if not employee:
                return Response({'status': 'error', 'message': 'employee_id not found for this company'},
                                status=status.HTTP_400_BAD_REQUEST)

        # Validate + read once
        safe_filename = DocumentProcessor.sanitize_filename(uploaded.name)
        file_bytes = uploaded.read()
        ok, _detected_fmt, content_err = DocumentProcessor.validate_content(file_bytes, safe_filename)
        if not ok:
            return Response(
                {'status': 'error', 'message': content_err or 'File content validation failed'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_hash = hashlib.sha256(file_bytes).hexdigest()

        # Dedupe within the company — same content twice is almost always a mistake
        existing = HRDocument.objects.filter(company=company, file_hash=file_hash).first()
        if existing:
            return Response({
                'status': 'error',
                'message': 'A document with this content already exists',
                'document_id': existing.id,
            }, status=status.HTTP_400_BAD_REQUEST)

        # Persist file under MEDIA_ROOT/hr_documents/<company>/
        upload_dir = Path(settings.MEDIA_ROOT) / 'hr_documents' / str(company.id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        storage_filename = f"{file_hash[:16]}_{safe_filename}"
        file_path = upload_dir / storage_filename
        with open(file_path, 'wb') as f:
            f.write(file_bytes)

        file_format = DocumentProcessor.get_file_format(safe_filename)

        # Retention default by document_type — caller can override
        from hr_agent.tasks import RETENTION_DEFAULTS_DAYS
        retention_days = request.POST.get('retention_days')
        if retention_days:
            try:
                retention_days = max(1, min(36500, int(retention_days)))
            except ValueError:
                retention_days = RETENTION_DEFAULTS_DAYS.get(document_type)
        else:
            retention_days = RETENTION_DEFAULTS_DAYS.get(document_type)

        document = HRDocument.objects.create(
            company=company,
            title=title[:200],
            description=description,
            document_type=document_type,
            confidentiality=confidentiality,
            employee=employee,
            uploaded_by=user,
            file_path=str(file_path.relative_to(settings.MEDIA_ROOT)),
            file_size=uploaded.size,
            mime_type=uploaded.content_type or '',
            file_format=file_format,
            file_hash=file_hash,
            processing_status='pending',
            retention_days=retention_days,
        )

        # Dispatch processing — broker probe → fall back to inline if Redis is down,
        # so the request doesn't stall in Celery's ~100s connection retry loop.
        from hr_agent.tasks import process_hr_document
        dispatch_mode = 'async'
        if _hr_celery_broker_ready(timeout_seconds=0.5):
            try:
                process_hr_document.apply_async(args=[document.id], retry=False)
            except Exception:
                logger.exception("process_hr_document: Celery dispatch failed, running inline")
                dispatch_mode = 'inline'
        else:
            logger.warning("process_hr_document: Celery broker unreachable — running inline")
            dispatch_mode = 'inline'

        if dispatch_mode == 'inline':
            try:
                process_hr_document.apply(args=[document.id])
            except Exception:
                logger.exception("Inline process_hr_document fallback failed for HR doc %s",
                                 document.id)
            document.refresh_from_db()

        return Response({
            'status': 'accepted',
            'data': {
                'document_id': document.id,
                'title': document.title,
                'file_format': document.file_format,
                'document_type': document.document_type,
                'confidentiality': document.confidentiality,
                'employee_id': document.employee_id,
                'retention_days': document.retention_days,
                'processing_status': document.processing_status,
                'dispatch_mode': dispatch_mode,
                'message': (
                    'Upload processed inline (Celery broker was unreachable).'
                    if dispatch_mode == 'inline'
                    else 'Upload accepted. Processing in the background.'
                ),
            },
        }, status=status.HTTP_202_ACCEPTED)
    except Exception:
        logger.exception("upload_hr_document failed")
        return Response(
            {'status': 'error', 'message': 'Failed to upload document'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRLLMThrottle])
def summarize_hr_document(request, document_id):
    """LLM summary of an HR document — uses the HRAgent's prompt that focuses
    on scope, eligibility, deadlines, and numeric thresholds."""
    try:
        company = request.user.company
        d = get_object_or_404(HRDocument, id=document_id, company=company)
        if not (d.document_content or '').strip():
            return Response({'status': 'error', 'message': 'Document has no extracted text yet'},
                            status=status.HTTP_400_BAD_REQUEST)
        max_sentences = (request.data or {}).get('max_sentences')
        agent = HRAgent(company_id=company.id)
        result = agent.summarize_document(d.document_content, max_sentences=max_sentences)
        if not result.get('success'):
            return Response({'status': 'error', 'message': result.get('error') or 'Summarize failed'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({'status': 'success', 'data': {
            'document_id': d.id, 'title': d.title, 'summary': result.get('summary'),
        }})
    except Exception:
        logger.exception("summarize_hr_document failed")
        return Response({'status': 'error', 'message': 'Failed to summarize document'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRLLMThrottle])
def extract_hr_document(request, document_id):
    """LLM-extract structured fields from an HR document (offer letter →
    {employee_name, role, start_date, salary, ...})."""
    try:
        company = request.user.company
        d = get_object_or_404(HRDocument, id=document_id, company=company)
        if not (d.document_content or '').strip():
            return Response({'status': 'error', 'message': 'Document has no extracted text yet'},
                            status=status.HTTP_400_BAD_REQUEST)
        schema = (request.data or {}).get('schema')
        agent = HRAgent(company_id=company.id)
        result = agent.extract_from_document(d.document_content, schema=schema)
        if not result.get('success'):
            return Response({'status': 'error', 'message': result.get('error') or 'Extract failed',
                             'raw': result.get('raw')},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        # Persist what we found onto the row so future calls can use it
        d.extracted_fields = {**(d.extracted_fields or {}), **(result.get('data') or {})}
        d.save(update_fields=['extracted_fields', 'updated_at'])
        return Response({'status': 'success', 'data': {
            'document_id': d.id, 'extracted': result.get('data'),
        }})
    except Exception:
        logger.exception("extract_hr_document failed")
        return Response({'status': 'error', 'message': 'Failed to extract from document'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# 3. Workflow / SOP Runner
# ============================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_hr_workflows(request):
    company = request.user.company
    qs = HRWorkflow.objects.filter(company=company).order_by('-updated_at')[:200]
    rows = [{
        'id': w.id, 'name': w.name, 'description': w.description,
        'trigger_conditions': w.trigger_conditions, 'steps': w.steps,
        'is_active': w.is_active, 'requires_approval': w.requires_approval,
        'timeout_seconds': w.timeout_seconds,
        'created_at': w.created_at.isoformat(), 'updated_at': w.updated_at.isoformat(),
    } for w in qs]
    return Response({'status': 'success', 'data': rows})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def create_hr_workflow(request):
    company = request.user.company
    d = request.data or {}
    name = (d.get('name') or '').strip()
    if not name:
        return Response({'status': 'error', 'message': 'name is required'},
                        status=status.HTTP_400_BAD_REQUEST)
    w = HRWorkflow.objects.create(
        company=company, name=name, description=d.get('description') or '',
        trigger_conditions=d.get('trigger_conditions') or {},
        steps=d.get('steps') or [], is_active=d.get('is_active', True),
        requires_approval=bool(d.get('requires_approval', False)),
        timeout_seconds=int(d.get('timeout_seconds') or 0),
    )
    return Response({'status': 'success', 'data': {'id': w.id, 'name': w.name}},
                    status=status.HTTP_201_CREATED)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def execute_hr_workflow(request, workflow_id):
    """Run an HR workflow with the supplied context. Returns 202 + the paused
    snapshot when a `wait` step is hit (the resume task takes over); 200 on
    immediate completion; 500 on executor error."""
    try:
        company = request.user.company
        user = _hr_get_or_create_user_for_company_user(request.user)
        w = HRWorkflow.objects.filter(company=company, id=workflow_id, is_active=True).first()
        if not w:
            return Response({'status': 'error', 'message': 'Workflow not found or inactive'},
                            status=status.HTTP_404_NOT_FOUND)
        data = request.data or {}
        context_data = dict(data.get('context') or {})
        # Always seed company_id so HR step handlers can scope inserts (e.g. schedule_meeting).
        context_data.setdefault('company_id', company.id)

        exec_obj = HRWorkflowExecution.objects.create(
            workflow=w, workflow_name=w.name, executed_by=user,
            employee_id=context_data.get('employee_id') or None,
            status='in_progress', context_data=context_data,
        )

        from hr_agent.workflow_engine import execute_workflow as _exec
        success, result_data, err = _exec(w, context_data, user, simulate=bool(data.get('simulate')),
                                          execution=exec_obj)

        if result_data and result_data.get('paused'):
            return Response({
                'status': 'accepted',
                'data': {
                    'execution_id': exec_obj.id,
                    'status': 'paused',
                    'wait_seconds': result_data.get('wait_seconds'),
                    'resume_at': exec_obj.resume_at.isoformat() if exec_obj.resume_at else None,
                    'result_data': result_data,
                },
            }, status=status.HTTP_202_ACCEPTED)

        exec_obj.status = 'completed' if success else 'failed'
        exec_obj.result_data = result_data or {}
        exec_obj.error_message = err
        exec_obj.completed_at = timezone.now()
        exec_obj.save()
        return Response({'status': 'success',
                         'data': {'execution_id': exec_obj.id,
                                  'status': exec_obj.status,
                                  'result_data': result_data}})
    except Exception:
        logger.exception("execute_hr_workflow failed")
        return Response({'status': 'error', 'message': 'Failed to execute workflow'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# 4. Proactive Notifications
# ============================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_hr_notification_templates(request):
    company = request.user.company
    qs = HRNotificationTemplate.objects.filter(company=company).order_by('-updated_at')[:200]
    rows = [{
        'id': t.id, 'name': t.name, 'channel': t.channel,
        'notification_type': t.notification_type,
        'subject': t.subject, 'body': t.body,
        'trigger_config': t.trigger_config,
        'use_llm_personalization': t.use_llm_personalization,
    } for t in qs]
    return Response({'status': 'success', 'data': rows})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def create_hr_notification_template(request):
    company = request.user.company
    d = request.data or {}
    name = (d.get('name') or '').strip()
    body = (d.get('body') or '').strip()
    if not name or not body:
        return Response({'status': 'error', 'message': 'name and body are required'},
                        status=status.HTTP_400_BAD_REQUEST)
    t = HRNotificationTemplate.objects.create(
        company=company, name=name, body=body,
        subject=d.get('subject') or '',
        channel=d.get('channel') or 'email',
        notification_type=d.get('notification_type') or 'system',
        trigger_config=d.get('trigger_config') or {},
        use_llm_personalization=bool(d.get('use_llm_personalization', False)),
    )
    return Response({'status': 'success', 'data': {'id': t.id, 'name': t.name}},
                    status=status.HTTP_201_CREATED)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_hr_scheduled_notifications(request):
    company = request.user.company
    qs = HRScheduledNotification.objects.filter(company=company).order_by('-scheduled_at')[:200]
    rows = [{
        'id': n.id, 'template_id': n.template_id, 'status': n.status,
        'recipient_employee_id': n.recipient_employee_id, 'recipient_email': n.recipient_email,
        'scheduled_at': n.scheduled_at.isoformat() if n.scheduled_at else None,
        'sent_at': n.sent_at.isoformat() if n.sent_at else None,
        'attempts': n.attempts, 'error_message': n.error_message,
    } for n in qs]
    return Response({'status': 'success', 'data': rows})


# ============================================================================
# 5. Meeting Scheduling
# ============================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_hr_meetings(request):
    """List HR meetings; private ones are visible only to participants + HR."""
    company = request.user.company
    cu = request.user
    role = _resolve_asker_role(cu)
    qs = HRMeeting.objects.filter(company=company)
    if role != 'hr':
        asker_emp = Employee.objects.filter(company=company, company_user=cu).first()
        emp_id = asker_emp.id if asker_emp else None
        public_or_mine = Q(visibility='company')
        if emp_id:
            public_or_mine |= Q(participants__id=emp_id) | Q(organizer_id=emp_id)
        qs = qs.filter(public_or_mine).distinct()
    rows = []
    for m in qs.order_by('-scheduled_at')[:200]:
        rows.append({
            'id': m.id, 'title': m.title, 'meeting_type': m.meeting_type,
            'visibility': m.visibility, 'status': m.status,
            'scheduled_at': m.scheduled_at.isoformat() if m.scheduled_at else None,
            'duration_minutes': m.duration_minutes,
            'meeting_link': m.meeting_link, 'location': m.location,
            'organizer_id': m.organizer_id,
        })
    return Response({'status': 'success', 'data': rows})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def create_hr_meeting(request):
    company = request.user.company
    d = request.data or {}
    sched_raw = d.get('scheduled_at')
    if not sched_raw or not d.get('title'):
        return Response({'status': 'error', 'message': 'title and scheduled_at are required'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        sched = datetime.fromisoformat(str(sched_raw).replace('Z', '+00:00'))
    except ValueError:
        return Response({'status': 'error', 'message': 'scheduled_at must be ISO-8601'},
                        status=status.HTTP_400_BAD_REQUEST)
    meeting_type = d.get('meeting_type') or 'one_on_one'
    # Default visibility: private for sensitive types, company-visible otherwise.
    default_visibility = 'private' if meeting_type in ('exit_interview', 'grievance_hearing',
                                                       'performance_review') else 'company'
    visibility = d.get('visibility') or default_visibility
    organizer = None
    if d.get('organizer_id'):
        organizer = Employee.objects.filter(pk=d['organizer_id'], company=company).first()
    m = HRMeeting.objects.create(
        company=company,
        title=str(d['title'])[:200],
        description=d.get('description') or '',
        meeting_type=meeting_type, visibility=visibility,
        organizer=organizer,
        scheduled_at=sched,
        duration_minutes=int(d.get('duration_minutes') or 30),
        timezone_name=d.get('timezone_name') or 'UTC',
        meeting_link=d.get('meeting_link') or None,
        location=d.get('location') or '',
    )
    if d.get('participant_ids'):
        valid = Employee.objects.filter(pk__in=d['participant_ids'], company=company)
        m.participants.set(valid)
    return Response({'status': 'success', 'data': {'id': m.id, 'title': m.title,
                                                   'visibility': m.visibility}},
                    status=status.HTTP_201_CREATED)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def hr_meeting_availability(request):
    """Cheap availability check — finds clashes against existing HRMeetings.
    Returns `available: True` / `False` with a list of clashing meeting ids."""
    company = request.user.company
    start = request.GET.get('start')
    end = request.GET.get('end')
    if not start or not end:
        return Response({'status': 'error', 'message': 'start and end query params required'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        s = datetime.fromisoformat(start.replace('Z', '+00:00'))
        e = datetime.fromisoformat(end.replace('Z', '+00:00'))
    except ValueError:
        return Response({'status': 'error', 'message': 'start/end must be ISO-8601'},
                        status=status.HTTP_400_BAD_REQUEST)
    clashes = HRMeeting.objects.filter(
        company=company, status='scheduled',
        scheduled_at__lt=e,
    ).extra(where=["DATEADD(MINUTE, duration_minutes, scheduled_at) > %s"], params=[s])
    # `extra(where=)` is MSSQL-specific syntax. If portability matters later,
    # replace with a Python-side check after fetching candidate rows.
    ids = list(clashes.values_list('id', flat=True))
    return Response({'status': 'success', 'data': {'available': not ids, 'clashes': ids}})


# ============================================================================
# Leave requests — bonus first-class HR object
# ============================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def submit_leave_request(request):
    """Create a LeaveRequest. The workflow runner will pick up the
    `leave_request_submitted` event and run any matching HRWorkflow
    (manager approval, calendar update, confirmation email)."""
    try:
        company = request.user.company
        d = request.data or {}
        emp = Employee.objects.filter(pk=d.get('employee_id'), company=company).first()
        if not emp:
            return Response({'status': 'error', 'message': 'employee_id required + must belong to your company'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            sd = datetime.fromisoformat(d['start_date']).date()
            ed = datetime.fromisoformat(d['end_date']).date()
        except (KeyError, ValueError):
            return Response({'status': 'error', 'message': 'start_date and end_date are required (YYYY-MM-DD)'},
                            status=status.HTTP_400_BAD_REQUEST)
        if ed < sd:
            return Response({'status': 'error', 'message': 'end_date must be on or after start_date'},
                            status=status.HTTP_400_BAD_REQUEST)
        days_requested = d.get('days_requested') or ((ed - sd).days + 1)
        lr = LeaveRequest.objects.create(
            employee=emp,
            leave_type=d.get('leave_type') or 'vacation',
            start_date=sd, end_date=ed,
            days_requested=days_requested,
            reason=(d.get('reason') or '')[:2000],
            status='pending',
        )
        return Response({'status': 'success', 'data': {
            'id': lr.id, 'employee_id': emp.id, 'status': lr.status,
            'days_requested': float(lr.days_requested),
        }}, status=status.HTTP_201_CREATED)
    except Exception:
        logger.exception("submit_leave_request failed")
        return Response({'status': 'error', 'message': 'Failed to submit leave request'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def decide_leave_request(request, request_id):
    """Approve or reject a pending leave request. Body: {action: 'approve'|'reject', note?: str}."""
    try:
        company = request.user.company
        lr = LeaveRequest.objects.filter(pk=request_id, employee__company=company).first()
        if not lr:
            return Response({'status': 'error', 'message': 'Leave request not found'},
                            status=status.HTTP_404_NOT_FOUND)
        if lr.status != 'pending':
            return Response({'status': 'error', 'message': f'Leave request is {lr.status}, not pending'},
                            status=status.HTTP_400_BAD_REQUEST)
        action = (request.data or {}).get('action')
        if action not in ('approve', 'reject'):
            return Response({'status': 'error', 'message': "action must be 'approve' or 'reject'"},
                            status=status.HTTP_400_BAD_REQUEST)
        lr.status = 'approved' if action == 'approve' else 'rejected'
        lr.approval_note = (request.data.get('note') or '')[:2000]
        lr.decided_at = timezone.now()
        lr.save(update_fields=['status', 'approval_note', 'decided_at', 'updated_at'])
        return Response({'status': 'success', 'data': {'id': lr.id, 'status': lr.status}})
    except Exception:
        logger.exception("decide_leave_request failed")
        return Response({'status': 'error', 'message': 'Failed to decide leave request'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# Dashboard — light overview
# ============================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def hr_dashboard(request):
    """Single roll-up endpoint for the HR landing page."""
    try:
        company = request.user.company
        now = timezone.now()
        in_30 = now + timedelta(days=30)
        data = {
            'employees': {
                'total': Employee.objects.filter(company=company).count(),
                'active': Employee.objects.filter(company=company, employment_status='active').count(),
                'on_leave': Employee.objects.filter(company=company, employment_status='on_leave').count(),
                'on_probation': Employee.objects.filter(company=company, employment_status='probation').count(),
            },
            'leave_requests': {
                'pending': LeaveRequest.objects.filter(employee__company=company, status='pending').count(),
            },
            'meetings_upcoming': HRMeeting.objects.filter(
                company=company, status='scheduled', scheduled_at__gte=now,
            ).count(),
            'documents': {
                'total': HRDocument.objects.filter(company=company).count(),
                'indexed': HRDocument.objects.filter(company=company, is_indexed=True).count(),
                'failed': HRDocument.objects.filter(company=company, processing_status='failed').count(),
            },
            'probation_ending_soon': Employee.objects.filter(
                company=company,
                probation_end_date__isnull=False,
                probation_end_date__lte=in_30.date(),
                probation_end_date__gte=now.date(),
            ).count(),
        }
        return Response({'status': 'success', 'data': data})
    except Exception:
        logger.exception("hr_dashboard failed")
        return Response({'status': 'error', 'message': 'Failed to load HR dashboard'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

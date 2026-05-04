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
import json
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
    HRMeetingSchedulerChat, HRMeetingSchedulerChatMessage,
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
        # Underlying Django auth.User — same identity the PM Knowledge QA agent
        # returns when asked about company users.
        'user_id': e.user_id,
        'username': e.user.username if e.user_id else None,
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
    ?department=, ?status=, ?limit/?offset (defaults 50/0).

    Backfills any CompanyUser without a backing Employee before listing —
    employees in HR are the company users of the same tenant. The
    CompanyUser→Employee sync signal handles new/updated rows; this catches
    pre-existing CompanyUsers from before the sync was wired.
    """
    try:
        company = request.user.company
        # Backfill — idempotent + cheap.
        from hr_agent.signals import backfill_employees_for_company
        try:
            backfill_employees_for_company(company.id)
        except Exception:
            logger.exception("list_employees: backfill failed for company %s", company.id)
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
    leave balance / manager / department from `Employee`).

    Optional body fields:
      ``chat_history``: list of ``{role: 'user'|'assistant', content: str}``
        — last few turns for multi-turn coherence.
    """
    try:
        company_user = request.user
        company = company_user.company
        question = (request.data.get('question') or '').strip()
        if not question:
            return Response({'status': 'error', 'message': 'question is required'},
                            status=status.HTTP_400_BAD_REQUEST)
        asker_employee = (Employee.objects.filter(company=company, company_user=company_user).first()
                          or Employee.objects.filter(company=company, work_email__iexact=company_user.email).first())

        # Multi-turn — prepend the last few turns to the question so the
        # retriever has something to ground on for follow-ups like "what about
        # for managers?". Cap length so prompts don't balloon.
        history = request.data.get('chat_history') or []
        contextualized = question
        if isinstance(history, list) and history:
            recent = []
            for turn in history[-6:]:
                if not isinstance(turn, dict):
                    continue
                role = (turn.get('role') or '').lower()
                content = (turn.get('content') or '')[:1500]
                if role in ('user', 'assistant') and content:
                    recent.append(f"{role.capitalize()}: {content}")
            if recent:
                contextualized = "Previous conversation:\n" + "\n".join(recent) + "\n\nCurrent question: " + question

        agent = HRAgent(company_id=company.id)
        result = agent.answer_question(
            contextualized,
            asker_role=_resolve_asker_role(company_user),
            asker_employee=asker_employee,
        )
        return Response({'status': 'success', 'data': result})
    except Exception:
        logger.exception("hr_knowledge_qa failed")
        return Response({'status': 'error', 'message': 'Failed to answer question'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# HR Knowledge Q&A — chat persistence (mirrors PM agent's chat shape)
# ============================================================================

def _normalize_chat(chat: HRKnowledgeChat) -> dict:
    """Compact wire shape; messages oldest-first."""
    msgs = []
    for m in chat.messages.order_by('created_at'):
        item = {'role': m.role, 'content': m.content}
        if m.response_data:
            item['responseData'] = m.response_data
        msgs.append(item)
    return {
        'id': str(chat.id),
        'title': chat.title or 'HR chat',
        'messages': msgs,
        'updatedAt': chat.updated_at.isoformat() if chat.updated_at else None,
        'timestamp': chat.updated_at.isoformat() if chat.updated_at else None,
    }


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_hr_knowledge_chats(request):
    """List the caller's HR Q&A chats (most recent first, capped at 50)."""
    try:
        chats = (HRKnowledgeChat.objects.filter(company_user=request.user)
                 .order_by('-updated_at')[:50])
        return Response({'status': 'success',
                         'data': [_normalize_chat(c) for c in chats]})
    except Exception:
        logger.exception("list_hr_knowledge_chats failed")
        return Response({'status': 'error', 'message': 'Failed to list chats'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def create_hr_knowledge_chat(request):
    """Create a new chat with optional initial messages."""
    try:
        d = request.data or {}
        title = (d.get('title') or 'HR chat')[:255]
        chat = HRKnowledgeChat.objects.create(company_user=request.user, title=title)
        for m in (d.get('messages') or []):
            if not isinstance(m, dict):
                continue
            role = (m.get('role') or '').lower()
            if role not in ('user', 'assistant'):
                continue
            HRKnowledgeChatMessage.objects.create(
                chat=chat, role=role,
                content=str(m.get('content') or '')[:50000],
                response_data=m.get('responseData'),
            )
        chat.refresh_from_db()
        return Response({'status': 'success', 'data': _normalize_chat(chat)},
                        status=status.HTTP_201_CREATED)
    except Exception:
        logger.exception("create_hr_knowledge_chat failed")
        return Response({'status': 'error', 'message': 'Failed to create chat'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def update_hr_knowledge_chat(request, chat_id):
    """Replace title and/or message list. Caller sends the full message
    array (PM agent's pattern) so we don't have to merge deltas — simple,
    deterministic, idempotent."""
    try:
        chat = HRKnowledgeChat.objects.filter(pk=chat_id, company_user=request.user).first()
        if not chat:
            return Response({'status': 'error', 'message': 'Chat not found'},
                            status=status.HTTP_404_NOT_FOUND)
        d = request.data or {}
        if 'title' in d:
            chat.title = (d['title'] or 'HR chat')[:255]
        chat.save()
        if 'messages' in d:
            HRKnowledgeChatMessage.objects.filter(chat=chat).delete()
            for m in d.get('messages') or []:
                if not isinstance(m, dict):
                    continue
                role = (m.get('role') or '').lower()
                if role not in ('user', 'assistant'):
                    continue
                HRKnowledgeChatMessage.objects.create(
                    chat=chat, role=role,
                    content=str(m.get('content') or '')[:50000],
                    response_data=m.get('responseData'),
                )
        chat.refresh_from_db()
        return Response({'status': 'success', 'data': _normalize_chat(chat)})
    except Exception:
        logger.exception("update_hr_knowledge_chat failed")
        return Response({'status': 'error', 'message': 'Failed to update chat'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def delete_hr_knowledge_chat(request, chat_id):
    try:
        deleted, _ = HRKnowledgeChat.objects.filter(
            pk=chat_id, company_user=request.user,
        ).delete()
        if not deleted:
            return Response({'status': 'error', 'message': 'Chat not found'},
                            status=status.HTTP_404_NOT_FOUND)
        return Response({'status': 'success', 'data': {'deleted': True}})
    except Exception:
        logger.exception("delete_hr_knowledge_chat failed")
        return Response({'status': 'error', 'message': 'Failed to delete chat'},
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

# --- Per-document GET / DELETE ----------------------------------------------

def _serialize_hr_document(d: HRDocument, *, include_content: bool = False) -> dict:
    out = {
        'id': d.id, 'title': d.title, 'description': d.description,
        'document_type': d.document_type, 'confidentiality': d.confidentiality,
        'employee_id': d.employee_id,
        'file_format': d.file_format, 'file_size': d.file_size,
        'mime_type': d.mime_type,
        'processing_status': d.processing_status,
        'processing_error': d.processing_error,
        'is_indexed': d.is_indexed,
        'chunks_processed': d.chunks_processed, 'chunks_total': d.chunks_total,
        'extracted_fields': d.extracted_fields or {},
        'retention_days': d.retention_days,
        'created_at': d.created_at.isoformat() if d.created_at else None,
        'updated_at': d.updated_at.isoformat() if d.updated_at else None,
    }
    if include_content:
        out['document_content'] = (d.document_content or '')[:50000]
    return out


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def get_hr_document(request, document_id):
    """Single document detail incl. extracted text (capped at 50k chars)."""
    try:
        company = request.user.company
        d = HRDocument.objects.filter(pk=document_id, company=company).first()
        if not d:
            return Response({'status': 'error', 'message': 'Document not found'},
                            status=status.HTTP_404_NOT_FOUND)
        return Response({'status': 'success', 'data': _serialize_hr_document(d, include_content=True)})
    except Exception:
        logger.exception("get_hr_document failed")
        return Response({'status': 'error', 'message': 'Failed to load document'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def delete_hr_document(request, document_id):
    """Delete an HR document (and its file on disk + indexed chunks via FK CASCADE)."""
    try:
        company = request.user.company
        d = HRDocument.objects.filter(pk=document_id, company=company).first()
        if not d:
            return Response({'status': 'error', 'message': 'Document not found'},
                            status=status.HTTP_404_NOT_FOUND)
        # Best-effort file unlink — don't fail the API call if storage is gone.
        try:
            from django.conf import settings as _s
            from pathlib import Path as _P
            if d.file_path:
                p = _P(_s.MEDIA_ROOT) / d.file_path
                if p.exists():
                    p.unlink()
        except Exception:
            logger.warning("delete_hr_document: failed to unlink file for doc %s", d.id)
        deleted_id = d.id
        d.delete()
        return Response({'status': 'success', 'data': {'deleted_id': deleted_id}})
    except Exception:
        logger.exception("delete_hr_document failed")
        return Response({'status': 'error', 'message': 'Failed to delete document'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# Workflow / SOP runner
# ============================================================================

# --- Workflow CRUD --------------------------------------------------------

def _serialize_hr_workflow(w: HRWorkflow) -> dict:
    return {
        'id': w.id, 'name': w.name, 'description': w.description,
        'trigger_conditions': w.trigger_conditions or {},
        'steps': w.steps or [],
        'is_active': w.is_active, 'requires_approval': w.requires_approval,
        'timeout_seconds': w.timeout_seconds,
        'created_at': w.created_at.isoformat() if w.created_at else None,
        'updated_at': w.updated_at.isoformat() if w.updated_at else None,
    }


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def get_hr_workflow(request, workflow_id):
    company = request.user.company
    w = HRWorkflow.objects.filter(pk=workflow_id, company=company).first()
    if not w:
        return Response({'status': 'error', 'message': 'Workflow not found'},
                        status=status.HTTP_404_NOT_FOUND)
    return Response({'status': 'success', 'data': _serialize_hr_workflow(w)})


@api_view(['PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def update_hr_workflow(request, workflow_id):
    """Update name/description/trigger/steps/is_active/timeout."""
    company = request.user.company
    w = HRWorkflow.objects.filter(pk=workflow_id, company=company).first()
    if not w:
        return Response({'status': 'error', 'message': 'Workflow not found'},
                        status=status.HTTP_404_NOT_FOUND)
    d = request.data or {}
    dirty = []
    if 'name' in d:
        name = (d['name'] or '').strip()
        if not name:
            return Response({'status': 'error', 'message': 'name cannot be blank'},
                            status=status.HTTP_400_BAD_REQUEST)
        w.name = name[:200]
        dirty.append('name')
    if 'description' in d:
        w.description = str(d['description'] or '')
        dirty.append('description')
    if 'trigger_conditions' in d:
        tc = d['trigger_conditions']
        if not isinstance(tc, dict):
            return Response({'status': 'error', 'message': 'trigger_conditions must be a dict'},
                            status=status.HTTP_400_BAD_REQUEST)
        w.trigger_conditions = tc
        dirty.append('trigger_conditions')
    if 'steps' in d:
        steps = d['steps']
        if not isinstance(steps, list):
            return Response({'status': 'error', 'message': 'steps must be a list'},
                            status=status.HTTP_400_BAD_REQUEST)
        w.steps = steps
        dirty.append('steps')
    if 'is_active' in d:
        w.is_active = bool(d['is_active'])
        dirty.append('is_active')
    if 'requires_approval' in d:
        w.requires_approval = bool(d['requires_approval'])
        dirty.append('requires_approval')
    if 'timeout_seconds' in d:
        try:
            w.timeout_seconds = max(0, int(d['timeout_seconds']))
            dirty.append('timeout_seconds')
        except (TypeError, ValueError):
            pass
    if dirty:
        dirty.append('updated_at')
        w.save(update_fields=list(set(dirty)))
    return Response({'status': 'success', 'data': _serialize_hr_workflow(w)})


@api_view(['DELETE', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def delete_hr_workflow(request, workflow_id):
    company = request.user.company
    w = HRWorkflow.objects.filter(pk=workflow_id, company=company).first()
    if not w:
        return Response({'status': 'error', 'message': 'Workflow not found'},
                        status=status.HTTP_404_NOT_FOUND)
    deleted_id = w.id
    w.delete()
    return Response({'status': 'success', 'data': {'deleted_id': deleted_id}})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_hr_workflow_executions(request):
    """Recent execution history. ``?workflow_id=`` filters to a single workflow."""
    company = request.user.company
    qs = HRWorkflowExecution.objects.filter(workflow__company=company).order_by('-started_at')
    wf_id = request.GET.get('workflow_id')
    if wf_id:
        qs = qs.filter(workflow_id=wf_id)
    rows = [{
        'id': e.id, 'workflow_id': e.workflow_id, 'workflow_name': e.workflow_name,
        'status': e.status,
        'employee_id': e.employee_id,
        'started_at': e.started_at.isoformat() if e.started_at else None,
        'completed_at': e.completed_at.isoformat() if e.completed_at else None,
        'resume_at': e.resume_at.isoformat() if e.resume_at else None,
        'error_message': e.error_message,
        'steps_completed': (e.result_data or {}).get('steps_completed') if isinstance(e.result_data, dict) else None,
    } for e in qs[:100]]
    return Response({'status': 'success', 'data': rows})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_hr_workflows(request):
    company = request.user.company
    qs = HRWorkflow.objects.filter(company=company).order_by('-updated_at')[:200]
    return Response({'status': 'success',
                     'data': [_serialize_hr_workflow(w) for w in qs]})


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


# ============================================================================
# Meeting Scheduling Agent — chat + LLM scheduling, mirrors PM agent
# ============================================================================

def _serialize_hr_meeting(m: HRMeeting) -> dict:
    """Compact wire shape used by both list endpoints and the scheduler chat."""
    return {
        'id': m.id,
        'title': m.title,
        'description': m.description,
        'meeting_type': m.meeting_type,
        'visibility': m.visibility,
        'status': m.status,
        'organizer_id': m.organizer_id,
        'organizer_name': m.organizer.full_name if m.organizer_id else None,
        'participant_ids': list(m.participants.values_list('id', flat=True)),
        'participants': [
            {'id': p.id, 'full_name': p.full_name, 'work_email': p.work_email}
            for p in m.participants.all()
        ],
        'scheduled_at': m.scheduled_at.isoformat() if m.scheduled_at else None,
        'duration_minutes': m.duration_minutes,
        'timezone_name': m.timezone_name,
        'meeting_link': m.meeting_link,
        'location': m.location,
        'notes': m.notes,
        'transcript': m.transcript,
        'action_items': m.action_items or [],
        'created_at': m.created_at.isoformat() if m.created_at else None,
        'updated_at': m.updated_at.isoformat() if m.updated_at else None,
    }


def _serialize_meeting_chat(chat: HRMeetingSchedulerChat) -> dict:
    msgs = []
    for m in chat.messages.order_by('created_at'):
        item = {'role': m.role, 'content': m.content}
        if m.response_data:
            item['responseData'] = m.response_data
        msgs.append(item)
    return {
        'id': str(chat.id),
        'title': chat.title or 'Meeting chat',
        'messages': msgs,
        'updatedAt': chat.updated_at.isoformat() if chat.updated_at else None,
        'timestamp': chat.updated_at.isoformat() if chat.updated_at else None,
    }


# ----- Chat CRUD ---------------------------------------------------------

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_hr_meeting_scheduler_chats(request):
    try:
        chats = (HRMeetingSchedulerChat.objects.filter(company_user=request.user)
                 .order_by('-updated_at')[:50])
        return Response({'status': 'success',
                         'data': [_serialize_meeting_chat(c) for c in chats]})
    except Exception:
        logger.exception("list_hr_meeting_scheduler_chats failed")
        return Response({'status': 'error', 'message': 'Failed to list chats'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def create_hr_meeting_scheduler_chat(request):
    try:
        d = request.data or {}
        title = (d.get('title') or 'Meeting chat')[:255]
        chat = HRMeetingSchedulerChat.objects.create(
            company_user=request.user, title=title,
        )
        for m in (d.get('messages') or []):
            if not isinstance(m, dict):
                continue
            role = (m.get('role') or '').lower()
            if role not in ('user', 'assistant'):
                continue
            HRMeetingSchedulerChatMessage.objects.create(
                chat=chat, role=role,
                content=str(m.get('content') or '')[:50000],
                response_data=m.get('responseData'),
            )
        chat.refresh_from_db()
        return Response({'status': 'success', 'data': _serialize_meeting_chat(chat)},
                        status=status.HTTP_201_CREATED)
    except Exception:
        logger.exception("create_hr_meeting_scheduler_chat failed")
        return Response({'status': 'error', 'message': 'Failed to create chat'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def update_hr_meeting_scheduler_chat(request, chat_id):
    try:
        chat = HRMeetingSchedulerChat.objects.filter(
            pk=chat_id, company_user=request.user,
        ).first()
        if not chat:
            return Response({'status': 'error', 'message': 'Chat not found'},
                            status=status.HTTP_404_NOT_FOUND)
        d = request.data or {}
        if 'title' in d:
            chat.title = (d['title'] or 'Meeting chat')[:255]
        chat.save()
        if 'messages' in d:
            HRMeetingSchedulerChatMessage.objects.filter(chat=chat).delete()
            for m in d.get('messages') or []:
                if not isinstance(m, dict):
                    continue
                role = (m.get('role') or '').lower()
                if role not in ('user', 'assistant'):
                    continue
                HRMeetingSchedulerChatMessage.objects.create(
                    chat=chat, role=role,
                    content=str(m.get('content') or '')[:50000],
                    response_data=m.get('responseData'),
                )
        chat.refresh_from_db()
        return Response({'status': 'success', 'data': _serialize_meeting_chat(chat)})
    except Exception:
        logger.exception("update_hr_meeting_scheduler_chat failed")
        return Response({'status': 'error', 'message': 'Failed to update chat'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def delete_hr_meeting_scheduler_chat(request, chat_id):
    try:
        deleted, _ = HRMeetingSchedulerChat.objects.filter(
            pk=chat_id, company_user=request.user,
        ).delete()
        if not deleted:
            return Response({'status': 'error', 'message': 'Chat not found'},
                            status=status.HTTP_404_NOT_FOUND)
        return Response({'status': 'success', 'data': {'deleted': True}})
    except Exception:
        logger.exception("delete_hr_meeting_scheduler_chat failed")
        return Response({'status': 'error', 'message': 'Failed to delete chat'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ----- LLM-driven natural-language scheduling -----------------------------

def _parse_iso_dt(s: str):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRLLMThrottle])
def hr_meeting_schedule(request):
    """Natural-language meeting scheduling. Body: ``{message: str}`` plus an
    optional ``chat_history`` list of recent turns. The LLM interprets the
    message + the company's employee directory and returns a JSON intent;
    we materialise that into an `HRMeeting` row and reply in chat.

    Returns ``{reply: str, meeting: serialized | None, parsed: {...}}``.
    """
    try:
        company_user = request.user
        company = company_user.company
        message = (request.data.get('message') or '').strip()
        if not message:
            return Response({'status': 'error', 'message': 'message is required'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Build a tiny employee directory the LLM can name-match against.
        emp_rows = list(Employee.objects.filter(company=company)
                        .values('id', 'full_name', 'work_email', 'job_title')[:200])
        directory_lines = [
            f"- id={e['id']}, name={e['full_name']!r}, email={e['work_email']}, role={e['job_title'] or 'n/a'}"
            for e in emp_rows
        ]

        # Resolve the asking employee (organizer default).
        asker = (Employee.objects.filter(company=company, company_user=company_user).first()
                 or Employee.objects.filter(company=company, work_email__iexact=company_user.email).first())
        organizer_id = asker.id if asker else None

        history_text = ''
        history = request.data.get('chat_history') or []
        if isinstance(history, list) and history:
            recent = []
            for turn in history[-6:]:
                if not isinstance(turn, dict):
                    continue
                role = (turn.get('role') or '').lower()
                content = (turn.get('content') or '')[:1000]
                if role in ('user', 'assistant') and content:
                    recent.append(f"{role.capitalize()}: {content}")
            if recent:
                history_text = "Previous conversation:\n" + "\n".join(recent) + "\n\n"

        from datetime import timezone as _dtz
        now_iso = timezone.now().astimezone(_dtz.utc).isoformat()

        prompt = (
            f"{history_text}You are an HR meeting scheduling assistant. Today (UTC) is "
            f"{now_iso}. From the user's request, extract a meeting intent and return ONLY "
            "a JSON object with these keys (use null when a value is not specified):\n"
            "  {\"intent\": \"create\"|\"update\"|\"cancel\"|\"clarify\",\n"
            "   \"title\": str|null, \"description\": str|null,\n"
            "   \"meeting_type\": one of [onboarding_orientation, one_on_one, performance_review,\n"
            "                              mid_year_check_in, exit_interview, grievance_hearing,\n"
            "                              training_session, benefits_consult, other]|null,\n"
            "   \"scheduled_at\": ISO-8601 UTC datetime|null, \"duration_minutes\": int|null,\n"
            "   \"participant_ids\": [int]|null,  // pick ids from the directory below by name match\n"
            "   \"location\": str|null, \"meeting_link\": str|null,\n"
            "   \"reply\": str  // friendly natural-language reply to show the user\n"
            "  }\n"
            "Default duration_minutes=30 when unspecified. Default meeting_type='one_on_one'.\n"
            f"Visibility for exit_interview/grievance_hearing/performance_review will be set to private automatically.\n\n"
            f"Employee directory ({len(emp_rows)} rows):\n" + "\n".join(directory_lines) + "\n\n"
            f"User message: {message}"
        )

        agent = HRAgent(company_id=company.id)
        try:
            raw = agent._call_llm(
                prompt=prompt,
                system_prompt=(
                    "You are a precise meeting-scheduling assistant. Output ONLY a single valid "
                    "JSON object — no commentary, no markdown fences."
                ),
                temperature=0.1, max_tokens=600,
            )
        except Exception as exc:
            logger.exception("hr_meeting_schedule: LLM call failed")
            return Response({'status': 'error',
                             'data': {'reply': f"LLM call failed: {exc}", 'meeting': None}},
                            status=status.HTTP_502_BAD_GATEWAY)

        s = (raw or '').strip()
        if s.startswith('```'):
            s = s.split('```', 2)[1]
            if s.startswith('json'):
                s = s[4:]
            s = s.strip('` \n')
        try:
            parsed = json.loads(s)
        except Exception:
            return Response({'status': 'success', 'data': {
                'reply': raw or 'I need a bit more info to schedule that.',
                'meeting': None, 'parsed': None,
            }})

        intent = (parsed.get('intent') or 'clarify').lower()
        meeting_payload = None

        if intent == 'create':
            sched = _parse_iso_dt(parsed.get('scheduled_at'))
            if not sched:
                # No valid time → reply only, don't create.
                return Response({'status': 'success', 'data': {
                    'reply': parsed.get('reply') or 'Could you specify the date and time?',
                    'meeting': None, 'parsed': parsed,
                }})
            mtype = (parsed.get('meeting_type') or 'one_on_one')
            visibility = ('private'
                          if mtype in ('exit_interview', 'grievance_hearing', 'performance_review')
                          else 'company')
            organizer = None
            if organizer_id:
                organizer = Employee.objects.filter(pk=organizer_id, company=company).first()
            m = HRMeeting.objects.create(
                company=company,
                title=(parsed.get('title') or 'HR meeting')[:200],
                description=(parsed.get('description') or '')[:5000],
                meeting_type=mtype,
                visibility=visibility,
                organizer=organizer,
                scheduled_at=sched,
                duration_minutes=int(parsed.get('duration_minutes') or 30),
                timezone_name=parsed.get('timezone_name') or 'UTC',
                meeting_link=parsed.get('meeting_link') or None,
                location=parsed.get('location') or '',
            )
            pids = parsed.get('participant_ids') or []
            if isinstance(pids, list) and pids:
                valid = Employee.objects.filter(pk__in=pids, company=company)
                m.participants.set(valid)
            meeting_payload = _serialize_hr_meeting(m)

        return Response({'status': 'success', 'data': {
            'reply': parsed.get('reply') or 'Done.',
            'meeting': meeting_payload,
            'parsed': parsed,
        }})
    except Exception:
        logger.exception("hr_meeting_schedule failed")
        return Response({'status': 'error', 'message': 'Failed to schedule meeting'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ----- Per-meeting CRUD ---------------------------------------------------

def _hr_meeting_or_404(request, meeting_id):
    company = request.user.company
    m = HRMeeting.objects.filter(pk=meeting_id, company=company).first()
    if not m:
        return None, Response({'status': 'error', 'message': 'Meeting not found'},
                              status=status.HTTP_404_NOT_FOUND)
    return m, None


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def get_hr_meeting(request, meeting_id):
    m, err = _hr_meeting_or_404(request, meeting_id)
    if err:
        return err
    return Response({'status': 'success', 'data': _serialize_hr_meeting(m)})


@api_view(['PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def update_hr_meeting(request, meeting_id):
    """Update title / description / scheduled_at / duration / participants /
    notes / location / meeting_link / status."""
    m, err = _hr_meeting_or_404(request, meeting_id)
    if err:
        return err
    d = request.data or {}
    dirty = []
    if 'title' in d:
        m.title = str(d['title'] or '')[:200]
        dirty.append('title')
    if 'description' in d:
        m.description = str(d['description'] or '')[:5000]
        dirty.append('description')
    if 'scheduled_at' in d:
        sched = _parse_iso_dt(d['scheduled_at'])
        if sched is None:
            return Response({'status': 'error', 'message': 'scheduled_at must be ISO-8601'},
                            status=status.HTTP_400_BAD_REQUEST)
        m.scheduled_at = sched
        dirty.append('scheduled_at')
        # Reset reminder flags so updated meetings get fresh reminders.
        m.reminder_24h_sent_at = None
        m.reminder_15m_sent_at = None
        dirty.extend(['reminder_24h_sent_at', 'reminder_15m_sent_at'])
    if 'duration_minutes' in d:
        try:
            m.duration_minutes = max(5, min(480, int(d['duration_minutes'])))
        except (TypeError, ValueError):
            pass
        else:
            dirty.append('duration_minutes')
    if 'meeting_link' in d:
        m.meeting_link = (d['meeting_link'] or None)
        dirty.append('meeting_link')
    if 'location' in d:
        m.location = str(d['location'] or '')[:500]
        dirty.append('location')
    if 'notes' in d:
        m.notes = str(d['notes'] or '')
        dirty.append('notes')
    if 'transcript' in d:
        m.transcript = str(d['transcript'] or '')
        dirty.append('transcript')
    if 'status' in d and d['status'] in ('scheduled', 'completed', 'cancelled', 'rescheduled'):
        m.status = d['status']
        dirty.append('status')
    if 'visibility' in d and d['visibility'] in ('company', 'private'):
        m.visibility = d['visibility']
        dirty.append('visibility')
    if dirty:
        dirty.append('updated_at')
        m.save(update_fields=list(set(dirty)))
    if 'participant_ids' in d:
        ids = d.get('participant_ids') or []
        if isinstance(ids, list):
            valid = Employee.objects.filter(pk__in=ids, company=request.user.company)
            m.participants.set(valid)
    m.refresh_from_db()
    return Response({'status': 'success', 'data': _serialize_hr_meeting(m)})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def cancel_hr_meeting(request, meeting_id):
    """Cancel a meeting (status='cancelled'). Body may include a `reason`
    that goes into `notes`."""
    m, err = _hr_meeting_or_404(request, meeting_id)
    if err:
        return err
    reason = (request.data or {}).get('reason') or ''
    m.status = 'cancelled'
    if reason:
        prefix = '\n\n[Cancelled] ' if m.notes else '[Cancelled] '
        m.notes = (m.notes or '') + prefix + reason
    m.save(update_fields=['status', 'notes', 'updated_at'])
    return Response({'status': 'success', 'data': _serialize_hr_meeting(m)})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRLLMThrottle])
def extract_hr_meeting_action_items(request, meeting_id):
    """LLM-extract structured action items from a meeting's transcript and
    save them onto `HRMeeting.action_items`. Returns the extracted list."""
    m, err = _hr_meeting_or_404(request, meeting_id)
    if err:
        return err
    transcript = (m.transcript or '').strip()
    if not transcript:
        return Response({'status': 'error', 'message': 'Meeting has no transcript yet'},
                        status=status.HTTP_400_BAD_REQUEST)
    agent = HRAgent(company_id=request.user.company.id)
    prompt = (
        "From the meeting transcript delimited by <transcript>, extract a list of concrete "
        "action items. Each must be something someone agreed to do. Return ONLY a JSON array; "
        "each entry: {\"text\": str, \"owner_name\": str|null, \"due_date\": YYYY-MM-DD|null}. "
        "At most 15 items.\n\n"
        f"<transcript>\n{transcript[:12000]}\n</transcript>"
    )
    try:
        raw = agent._call_llm(
            prompt=prompt,
            system_prompt="You extract structured action items. Output valid JSON only.",
            temperature=0.0, max_tokens=900,
        )
    except Exception as exc:
        logger.exception("extract_hr_meeting_action_items LLM failed")
        return Response({'status': 'error', 'message': f'LLM call failed: {exc}'},
                        status=status.HTTP_502_BAD_GATEWAY)
    s = (raw or '').strip()
    if s.startswith('```'):
        s = s.split('```', 2)[1]
        if s.startswith('json'):
            s = s[4:]
        s = s.strip('` \n')
    items = []
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            items = [{
                'text': str(it.get('text') or '')[:500],
                'owner_name': str(it.get('owner_name')) if it.get('owner_name') else None,
                'due_date': str(it.get('due_date')) if it.get('due_date') else None,
            } for it in parsed if isinstance(it, dict) and it.get('text')]
    except Exception:
        logger.warning("extract_hr_meeting_action_items: LLM JSON unparseable: %r", raw[:200])
    m.action_items = items
    m.save(update_fields=['action_items', 'updated_at'])
    return Response({'status': 'success', 'data': {'action_items': items, 'meeting_id': m.id}})

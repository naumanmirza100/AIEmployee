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
import re
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
    Department, HRAuditLog, PerformanceGoal, PerformanceReviewCycle,
    HRDocumentAccessLog,
)
from hr_agent.throttling import (
    HRPublicThrottle, HRLLMThrottle, HRUploadThrottle, HRCRUDThrottle,
)
from core.HR_agent.hr_agent import HRAgent
from core.api_key_service import KeyServiceError
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
    user = User.objects.filter(email=company_user.email).first()
    if user:
        return user
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


# Employment status lifecycle. Each key is a current state; the set is the
# allowed *next* states for a non-admin caller. HR-admins can override any
# transition (they often need to correct mid-lifecycle mistakes).
_EMPLOYMENT_STATUS_TRANSITIONS: dict[str, set[str]] = {
    'candidate':  {'onboarding', 'offboarded'},   # offer accepted → onboard, or rescinded → offboarded
    'onboarding': {'active', 'probation', 'offboarded'},
    'active':     {'on_leave', 'probation', 'notice', 'offboarded'},
    'probation':  {'active', 'notice', 'offboarded'},
    'on_leave':   {'active', 'notice', 'offboarded'},
    'notice':     {'active', 'offboarded'},        # active = resignation rescinded
    'offboarded': set(),                            # terminal — HR-admin override only
}


def _validate_employment_transition(current: str, target: str, *, is_admin: bool):
    """Return (ok, error_message). Same-state writes are no-ops. HR-admins
    bypass the transition map entirely so they can correct lifecycle mistakes."""
    if current == target:
        return True, None
    if is_admin:
        return True, None
    allowed = _EMPLOYMENT_STATUS_TRANSITIONS.get(current, set())
    if target not in allowed:
        return False, (
            f"Illegal employment_status transition {current!r} → {target!r}. "
            f"Allowed from {current!r}: {sorted(allowed) or 'none — HR-admin override required'}."
        )
    return True, None


def _validate_goal_weight_sum(employee, cycle_id, new_weight: int,
                              *, exclude_goal_id=None):
    """Reject when adding/updating this goal's weight would push the cycle
    total past 100%. ``exclude_goal_id`` is the goal being updated (so we
    don't double-count its OLD weight against the new one).

    Returns (ok, error_message, current_sum). When ``cycle_id`` is None we
    skip the check entirely — goals outside a cycle don't roll up into
    weighted scoring.
    """
    if not cycle_id:
        return True, None, 0
    from hr_agent.models import PerformanceGoal
    from django.db.models import Sum
    qs = PerformanceGoal.objects.filter(employee=employee, cycle_id=cycle_id)
    if exclude_goal_id is not None:
        qs = qs.exclude(pk=exclude_goal_id)
    current_sum = int(qs.aggregate(s=Sum('weight_pct'))['s'] or 0)
    projected = current_sum + max(0, int(new_weight or 0))
    if projected > 100:
        return False, (
            f"Goal weights for this cycle would total {projected}% "
            f"(other goals: {current_sum}% + this goal: {new_weight}%). "
            f"Cycle weight total must be ≤ 100%."
        ), current_sum
    return True, None, current_sum


def _resolve_asker_role(company_user: CompanyUser) -> str:
    """Map a CompanyUser.role to a knowledge confidentiality bucket.

    ``company_user`` is the default dashboard-login role — those are operators
    of the tenant, not workforce — so it maps to 'hr' for retrieval gating.
    Workforce uses `Employee` rows (with an optional CompanyUser link).
    Explicit ``employee`` / ``manager`` roles override the default.
    """
    role = (company_user.role or '').lower()
    if role in ('owner', 'admin', 'hr_agent', 'company_user'):
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
        'department_id': e.department_obj_id,
        'department_name': e.department_obj.name if e.department_obj_id else None,
        'manager_id': e.manager_id,
        'employment_status': e.employment_status,
        'employment_type': e.employment_type,
        'start_date': e.start_date.isoformat() if e.start_date else None,
        'probation_end_date': e.probation_end_date.isoformat() if e.probation_end_date else None,
        'date_of_birth': e.date_of_birth.isoformat() if e.date_of_birth else None,
        'timezone_name': e.timezone_name,
    }


def _serialize_department(d) -> dict:
    return {
        'id': d.id, 'name': d.name, 'code': d.code,
        'parent_id': d.parent_id,
        'head_id': d.head_id,
        'description': d.description,
        'is_active': d.is_active,
        'employee_count': getattr(d, '_employee_count', None),
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
        if request.GET.get('department_id'):
            qs = qs.filter(department_obj_id=request.GET['department_id'])
        elif request.GET.get('department'):
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
        # Resolve department: prefer FK (department_id), fall back to string lookup,
        # else create a Department row from the string so we never lose the input.
        department_string = (d.get('department') or '').strip()[:120]
        department_obj = None
        dept_id = d.get('department_id')
        if dept_id:
            department_obj = Department.objects.filter(company=company, pk=dept_id).first()
            if department_obj:
                department_string = department_string or department_obj.name
        elif department_string:
            department_obj = Department.objects.filter(
                company=company, name__iexact=department_string,
            ).first() or Department.objects.create(company=company, name=department_string)
        e = Employee.objects.create(
            company=company,
            full_name=(d.get('full_name') or '').strip()[:255],
            work_email=email,
            personal_email=(d.get('personal_email') or '')[:254],
            phone=(d.get('phone') or '')[:40],
            job_title=(d.get('job_title') or '')[:160],
            department=department_string,
            department_obj=department_obj,
            employment_status=d.get('employment_status') or 'active',
            employment_type=d.get('employment_type') or 'full_time',
        )
        _write_audit_log(request.user, company, 'employee.create',
                         'employee', e.id, before=None,
                         after={'full_name': e.full_name, 'work_email': e.work_email,
                                'job_title': e.job_title, 'department': e.department,
                                'department_id': department_obj.id if department_obj else None,
                                'employment_status': e.employment_status,
                                'employment_type': e.employment_type})
        return Response({'status': 'success', 'data': _serialize_employee(e)},
                        status=status.HTTP_201_CREATED)
    except Exception:
        logger.exception("create_employee failed")
        return Response({'status': 'error', 'message': 'Failed to create employee'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# Departments — first-class hierarchy + dropdown source
# ============================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_departments(request):
    company = request.user.company
    qs = (Department.objects.filter(company=company)
          .annotate(_employee_count=Count('employees'))
          .order_by('name'))
    if request.GET.get('active_only'):
        qs = qs.filter(is_active=True)
    return Response({'status': 'success',
                     'data': [_serialize_department(d) for d in qs]})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def create_department(request):
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR-admin role required'},
                        status=status.HTTP_403_FORBIDDEN)
    company = request.user.company
    d = request.data or {}
    name = (d.get('name') or '').strip()
    if not name:
        return Response({'status': 'error', 'message': 'name is required'},
                        status=status.HTTP_400_BAD_REQUEST)
    if Department.objects.filter(company=company, name__iexact=name).exists():
        return Response({'status': 'error', 'message': 'Department with this name already exists'},
                        status=status.HTTP_400_BAD_REQUEST)
    parent_id = d.get('parent_id')
    parent = (Department.objects.filter(company=company, pk=parent_id).first()
              if parent_id else None)
    head_id = d.get('head_id')
    head = (Employee.objects.filter(company=company, pk=head_id).first()
            if head_id else None)
    dept = Department.objects.create(
        company=company, name=name[:120],
        code=(d.get('code') or '')[:32],
        description=d.get('description') or '',
        parent=parent, head=head,
        is_active=bool(d.get('is_active', True)),
    )
    _write_audit_log(request.user, company, 'department.create', 'Department', dept.id,
                     before=None,
                     after={'name': dept.name, 'code': dept.code,
                            'parent_id': dept.parent_id, 'head_id': dept.head_id,
                            'is_active': dept.is_active})
    return Response({'status': 'success', 'data': _serialize_department(dept)},
                    status=status.HTTP_201_CREATED)


@api_view(['PATCH', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def update_department(request, dept_id):
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR-admin role required'},
                        status=status.HTTP_403_FORBIDDEN)
    company = request.user.company
    dept = Department.objects.filter(company=company, pk=dept_id).first()
    if not dept:
        return Response({'status': 'error', 'message': 'Department not found'},
                        status=status.HTTP_404_NOT_FOUND)
    d = request.data or {}
    fields_changed = []
    before = {'name': dept.name, 'code': dept.code,
              'is_active': dept.is_active,
              'parent_id': dept.parent_id, 'head_id': dept.head_id}
    if 'name' in d:
        new_name = (d['name'] or '').strip()[:120]
        if new_name and new_name.lower() != dept.name.lower():
            if Department.objects.filter(company=company, name__iexact=new_name).exclude(pk=dept.pk).exists():
                return Response({'status': 'error', 'message': 'Another department already has that name'},
                                status=status.HTTP_400_BAD_REQUEST)
            dept.name = new_name
            fields_changed.append('name')
    if 'code' in d:
        dept.code = (d['code'] or '')[:32]
        fields_changed.append('code')
    if 'description' in d:
        dept.description = d['description'] or ''
        fields_changed.append('description')
    if 'is_active' in d:
        dept.is_active = bool(d['is_active'])
        fields_changed.append('is_active')
    if 'parent_id' in d:
        pid = d['parent_id']
        if pid in (None, '', 0):
            dept.parent = None
        else:
            parent = Department.objects.filter(company=company, pk=pid).first()
            if not parent or parent.pk == dept.pk:
                return Response({'status': 'error', 'message': 'Invalid parent_id'},
                                status=status.HTTP_400_BAD_REQUEST)
            # Walk up the candidate parent's ancestors to detect A→B→C→A cycles.
            cursor = parent
            depth = 0
            while cursor is not None and depth < 50:
                if cursor.parent_id == dept.pk:
                    return Response({
                        'status': 'error',
                        'message': 'Setting this parent would create a circular department hierarchy.',
                    }, status=status.HTTP_400_BAD_REQUEST)
                cursor = cursor.parent
                depth += 1
            dept.parent = parent
        fields_changed.append('parent')
    if 'head_id' in d:
        hid = d['head_id']
        if hid in (None, '', 0):
            dept.head = None
        else:
            head = Employee.objects.filter(company=company, pk=hid).first()
            if not head:
                return Response({'status': 'error', 'message': 'Invalid head_id'},
                                status=status.HTTP_400_BAD_REQUEST)
            dept.head = head
        fields_changed.append('head')
    if fields_changed:
        fields_changed.append('updated_at')
        dept.save(update_fields=fields_changed)
        _write_audit_log(request.user, company, 'department.update', 'Department', dept.id,
                         before,
                         after={'name': dept.name, 'code': dept.code,
                                'is_active': dept.is_active,
                                'parent_id': dept.parent_id, 'head_id': dept.head_id,
                                'fields_changed': sorted(set(fields_changed) - {'updated_at'})})
    return Response({'status': 'success', 'data': _serialize_department(dept)})


@api_view(['DELETE', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def delete_department(request, dept_id):
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR-admin role required'},
                        status=status.HTTP_403_FORBIDDEN)
    company = request.user.company
    dept = Department.objects.filter(company=company, pk=dept_id).first()
    if not dept:
        return Response({'status': 'error', 'message': 'Department not found'},
                        status=status.HTTP_404_NOT_FOUND)
    snap = {'name': dept.name, 'code': dept.code,
            'parent_id': dept.parent_id, 'head_id': dept.head_id}
    # Detach employees rather than cascading: keep them in the table but
    # null the FK + clear the legacy string. Children become roots.
    detached = Employee.objects.filter(department_obj=dept).update(department_obj=None, department='')
    reparented = Department.objects.filter(parent=dept).update(parent=None)
    dept.delete()
    _write_audit_log(request.user, company, 'department.delete', 'Department', int(dept_id),
                     before=snap,
                     after={'employees_detached': int(detached or 0),
                            'children_reparented': int(reparented or 0)})
    return Response({'status': 'success', 'data': {'deleted_id': int(dept_id)}})


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
        # F1 — compliance log: an HR doc being quoted into a Q&A answer is
        # functionally a read of that doc. The direct-read endpoints already log
        # via `_log_document_access`; without this, the agent could surface
        # payslips/contracts in chat without a paper trail. Batch the inserts so
        # one Q&A turn isn't N individual round-trips.
        try:
            citations = (result or {}).get('citations') or []
            doc_ids = []
            for c in citations:
                if not isinstance(c, dict):
                    continue
                did = c.get('document_id')
                if did:
                    try:
                        doc_ids.append(int(did))
                    except (TypeError, ValueError):
                        continue
            doc_ids = list(dict.fromkeys(doc_ids))  # de-dupe but preserve order
            if doc_ids:
                docs = list(HRDocument.objects.filter(
                    company=company, pk__in=doc_ids,
                ).only('id', 'company_id'))
                ip = (request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
                      or request.META.get('REMOTE_ADDR') or None)
                ua = (request.META.get('HTTP_USER_AGENT') or '')[:400]
                from hr_agent.models import HRDocumentAccessLog as _HRDAL
                _HRDAL.objects.bulk_create([
                    _HRDAL(company=company, actor=company_user, document=d,
                           action='read', ip_address=ip, user_agent=ua)
                    for d in docs
                ])
        except Exception:
            # Logging failure must never break the user's Q&A response.
            logger.exception("hr_knowledge_qa: failed to log document access for citations")
        return Response({'status': 'success', 'data': result})
    except KeyServiceError:
        raise
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
        _MAX_MESSAGES = 500
        incoming = [m for m in (d.get('messages') or []) if isinstance(m, dict)]
        if len(incoming) > _MAX_MESSAGES:
            return Response({
                'status': 'error',
                'message': f'Message count exceeds limit of {_MAX_MESSAGES}.',
            }, status=status.HTTP_400_BAD_REQUEST)
        chat = HRKnowledgeChat.objects.create(company_user=request.user, title=title)
        for m in incoming:
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
        _MAX_MESSAGES = 500
        if 'messages' in d:
            incoming = [m for m in (d.get('messages') or []) if isinstance(m, dict)]
            if len(incoming) > _MAX_MESSAGES:
                return Response({
                    'status': 'error',
                    'message': f'Message count exceeds limit of {_MAX_MESSAGES}.',
                }, status=status.HTTP_400_BAD_REQUEST)
            HRKnowledgeChatMessage.objects.filter(chat=chat).delete()
            for m in incoming:
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
    """List HR documents visible to the caller (gated by confidentiality).

    Supports:
      ?document_type=   filter by type
      ?q=               substring search on title
      ?limit=           page size (default 50, max 200)
      ?offset=          page start (default 0)
    Returns ``pagination.total`` for the frontend to render page controls.
    """
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
        q = (request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(title__icontains=q)
        try:
            limit = max(1, min(int(request.GET.get('limit') or 50), 200))
            offset = max(0, int(request.GET.get('offset') or 0))
        except ValueError:
            limit, offset = 50, 0
        total = qs.count()
        rows = [{
            'id': d.id, 'title': d.title, 'document_type': d.document_type,
            'confidentiality': d.confidentiality,
            'employee_id': d.employee_id,
            'file_format': d.file_format, 'file_size': d.file_size,
            'processing_status': d.processing_status, 'is_indexed': d.is_indexed,
            'chunks_processed': d.chunks_processed, 'chunks_total': d.chunks_total,
            'version': d.version,
            'parent_document_id': d.parent_document_id,
            'superseded_by_id': d.superseded_by_id,
            'is_outdated': d.is_outdated,
            'created_at': d.created_at.isoformat(),
        } for d in qs.order_by('-created_at')[offset:offset + limit]]
        return Response({'status': 'success', 'data': rows,
                         'pagination': {'total': total, 'limit': limit, 'offset': offset}})
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

        # Optional supersede — when set, the new doc replaces the old one in
        # retrieval (parent gets `superseded_by` pointed at the new row).
        parent_document = None
        parent_document_id = request.POST.get('parent_document_id')
        if parent_document_id:
            parent_document = HRDocument.objects.filter(
                pk=parent_document_id, company=company,
            ).first()
            if not parent_document:
                return Response({'status': 'error', 'message': 'parent_document_id not found for this company'},
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
            parent_document=parent_document,
            version=(parent_document.version + 1) if parent_document else 1,
        )

        # Point the old revision at the new one so retrieval skips it.
        if parent_document:
            parent_document.superseded_by = document
            parent_document.save(update_fields=['superseded_by', 'updated_at'])

        # Audit — document uploads are sensitive (offer letters, payslips, contracts).
        _write_audit_log(
            request.user, company,
            'document.upload',
            'document', document.id,
            created={
                'title': document.title,
                'document_type': document.document_type,
                'confidentiality': document.confidentiality,
                'employee_id': document.employee_id,
                'file_format': document.file_format,
                'file_size': document.file_size,
                'version': document.version,
                'parent_document_id': document.parent_document_id,
            },
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
        _log_document_access(request, d, action='summarize')
        return Response({'status': 'success', 'data': {
            'document_id': d.id, 'title': d.title, 'summary': result.get('summary'),
        }})
    except KeyServiceError:
        raise
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
        _log_document_access(request, d, action='extract')
        return Response({'status': 'success', 'data': {
            'document_id': d.id, 'extracted': result.get('data'),
        }})
    except KeyServiceError:
        raise
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
        'version': d.version,
        'parent_document_id': d.parent_document_id,
        'superseded_by_id': d.superseded_by_id,
        'created_at': d.created_at.isoformat() if d.created_at else None,
        'updated_at': d.updated_at.isoformat() if d.updated_at else None,
    }
    if include_content:
        out['document_content'] = (d.document_content or '')[:50000]
    return out


def _log_document_access(request, document, action: str = 'read') -> None:
    """Fire-and-forget access-log writer. Compliance reads need a who/when/what
    trail even when the operation itself is a benign view."""
    try:
        ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() \
            or request.META.get('REMOTE_ADDR') or None
        ua = (request.META.get('HTTP_USER_AGENT') or '')[:400]
        HRDocumentAccessLog.objects.create(
            company=document.company, actor=request.user,
            document=document, action=action,
            ip_address=ip, user_agent=ua,
        )
    except Exception:
        logger.exception("_log_document_access failed for doc %s action=%s",
                         getattr(document, 'id', None), action)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def get_hr_document(request, document_id):
    """Single document detail incl. extracted text (capped at 50k chars).

    Writes an HRDocumentAccessLog row so compliance can answer "who read
    this confidential doc, and when?"."""
    try:
        company = request.user.company
        d = HRDocument.objects.filter(pk=document_id, company=company).first()
        if not d:
            return Response({'status': 'error', 'message': 'Document not found'},
                            status=status.HTTP_404_NOT_FOUND)
        _log_document_access(request, d, action='read')
        return Response({'status': 'success', 'data': _serialize_hr_document(d, include_content=True)})
    except Exception:
        logger.exception("get_hr_document failed")
        return Response({'status': 'error', 'message': 'Failed to load document'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def get_hr_document_status(request, document_id):
    """Lightweight indexing-progress endpoint. Returns just the fields the UI
    needs to render an "indexing…" progress bar. Skips the access-log write
    that `get_hr_document` does, so a 1-2s poll loop doesn't spam the audit
    trail (indexing progress is not a document *read*)."""
    try:
        company = request.user.company
        d = (HRDocument.objects
             .filter(pk=document_id, company=company)
             .only('id', 'processing_status', 'processing_error',
                   'is_indexed', 'chunks_processed', 'chunks_total',
                   'file_size', 'updated_at')
             .first())
        if not d:
            return Response({'status': 'error', 'message': 'Document not found'},
                            status=status.HTTP_404_NOT_FOUND)
        total = int(d.chunks_total or 0)
        done = int(d.chunks_processed or 0)
        percent = int(round((done / total) * 100)) if total > 0 else (
            100 if d.is_indexed else 0
        )
        return Response({'status': 'success', 'data': {
            'id': d.id,
            'processing_status': d.processing_status,
            'processing_error': d.processing_error or '',
            'is_indexed': bool(d.is_indexed),
            'chunks_processed': done,
            'chunks_total': total,
            'percent': percent,
            'updated_at': d.updated_at.isoformat() if d.updated_at else None,
        }})
    except Exception:
        logger.exception("get_hr_document_status failed")
        return Response({'status': 'error', 'message': 'Failed to load status'},
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
        snap = {'title': d.title, 'document_type': d.document_type,
                'confidentiality': d.confidentiality,
                'file_path': d.file_path, 'file_size': d.file_size,
                'employee_id': getattr(d, 'employee_id', None)}
        d.delete()
        _write_audit_log(request.user, company, 'hr_document.delete',
                         'HRDocument', deleted_id, before=snap, after=None)
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
    rows = []
    for e in qs[:100]:
        rd = e.result_data if isinstance(e.result_data, dict) else {}
        rows.append({
            'id': e.id, 'workflow_id': e.workflow_id, 'workflow_name': e.workflow_name,
            'status': e.status,
            'employee_id': e.employee_id,
            'started_at': e.started_at.isoformat() if e.started_at else None,
            'completed_at': e.completed_at.isoformat() if e.completed_at else None,
            'resume_at': e.resume_at.isoformat() if e.resume_at else None,
            'error_message': e.error_message,
            'steps_completed': rd.get('steps_completed'),
            'awaiting_approval': bool(rd.get('awaiting_approval')) or e.status == 'awaiting_approval',
            'approval_request': rd.get('approval_request'),
        })
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


def _serialize_execution_brief(e):
    """Compact view of one HRWorkflowExecution — used in detail / approve responses."""
    rd = e.result_data if isinstance(e.result_data, dict) else {}
    return {
        'id': e.id,
        'workflow_id': e.workflow_id,
        'workflow_name': e.workflow_name,
        'status': e.status,
        'employee_id': e.employee_id,
        'started_at': e.started_at.isoformat() if e.started_at else None,
        'completed_at': e.completed_at.isoformat() if e.completed_at else None,
        'resume_at': e.resume_at.isoformat() if e.resume_at else None,
        'awaiting_approval': bool(rd.get('awaiting_approval')),
        'approval_request': rd.get('approval_request'),
        'steps_completed': rd.get('steps_completed'),
        'error_message': e.error_message,
    }


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def approve_hr_workflow_execution(request, execution_id):
    """Approve a workflow that has paused on a ``wait_for_approval`` step and
    let it resume. Only HR-admins (or the named approver) may call this.

    The pause state is already on disk; we flip status to ``paused`` so the
    existing resume task picks up unchanged, then run it inline for an
    immediate response."""
    company = request.user.company
    company_user = request.user
    e = HRWorkflowExecution.objects.filter(workflow__company=company, pk=execution_id).first()
    if not e:
        return Response({'status': 'error', 'message': 'Execution not found'},
                        status=status.HTTP_404_NOT_FOUND)
    if e.status != 'awaiting_approval':
        return Response({'status': 'error',
                         'message': f'Execution is {e.status}, not awaiting_approval'},
                        status=status.HTTP_400_BAD_REQUEST)

    # Permission: approver_user_id from the pause snapshot (if set) wins; else HR-admin.
    snap = e.pause_state or {}
    req = snap.get('approval_request') or {}
    approver_user_id = req.get('approver_user_id')
    if approver_user_id:
        # Caller's CompanyUser.user FK must match the named approver.
        caller_user_id = getattr(company_user, 'user_id', None)
        if str(caller_user_id) != str(approver_user_id) and not _is_hr_admin(company_user):
            return Response({'status': 'error', 'message': 'Not authorized to approve this execution'},
                            status=status.HTTP_403_FORBIDDEN)
    elif not _is_hr_admin(company_user):
        return Response({'status': 'error', 'message': 'HR-admin role required'},
                        status=status.HTTP_403_FORBIDDEN)

    # Record who approved + comment, then flip status so the resume task accepts it.
    comment = (request.data or {}).get('comment') or ''
    rd = e.result_data if isinstance(e.result_data, dict) else {}
    approval_log = list(rd.get('approval_log') or [])
    approval_log.append({
        'action': 'approved', 'by_company_user_id': company_user.id,
        'at': timezone.now().isoformat(), 'comment': comment[:1000],
    })
    rd['approval_log'] = approval_log
    e.result_data = rd
    e.status = 'paused'  # contract: resume_hr_workflow_execution only resumes 'paused'
    e.save(update_fields=['status', 'result_data'])

    try:
        from hr_agent.tasks import resume_hr_workflow_execution as _resume
        # Run inline so the caller gets the post-approval state immediately.
        _resume(e.id)
    except Exception:
        logger.exception("approve_hr_workflow_execution: resume failed (exec=%s)", e.id)
        return Response({'status': 'error', 'message': 'Approve recorded but resume failed'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    e.refresh_from_db()
    return Response({'status': 'success', 'data': _serialize_execution_brief(e)})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def reject_hr_workflow_execution(request, execution_id):
    """Reject a workflow paused on ``wait_for_approval``. Marks the execution
    as ``rejected`` and records the reason. Remaining steps are NOT run."""
    company = request.user.company
    company_user = request.user
    e = HRWorkflowExecution.objects.filter(workflow__company=company, pk=execution_id).first()
    if not e:
        return Response({'status': 'error', 'message': 'Execution not found'},
                        status=status.HTTP_404_NOT_FOUND)
    if e.status != 'awaiting_approval':
        return Response({'status': 'error',
                         'message': f'Execution is {e.status}, not awaiting_approval'},
                        status=status.HTTP_400_BAD_REQUEST)

    snap = e.pause_state or {}
    req = snap.get('approval_request') or {}
    approver_user_id = req.get('approver_user_id')
    if approver_user_id:
        caller_user_id = getattr(company_user, 'user_id', None)
        if str(caller_user_id) != str(approver_user_id) and not _is_hr_admin(company_user):
            return Response({'status': 'error', 'message': 'Not authorized to reject this execution'},
                            status=status.HTTP_403_FORBIDDEN)
    elif not _is_hr_admin(company_user):
        return Response({'status': 'error', 'message': 'HR-admin role required'},
                        status=status.HTTP_403_FORBIDDEN)

    reason = ((request.data or {}).get('reason') or '').strip()
    rd = e.result_data if isinstance(e.result_data, dict) else {}
    approval_log = list(rd.get('approval_log') or [])
    approval_log.append({
        'action': 'rejected', 'by_company_user_id': company_user.id,
        'at': timezone.now().isoformat(), 'reason': reason[:1000],
    })
    rd['approval_log'] = approval_log

    e.result_data = rd
    e.status = 'rejected'
    e.error_message = (f'Rejected by company_user={company_user.id}'
                       + (f': {reason}' if reason else ''))[:4000]
    e.completed_at = timezone.now()
    e.resume_at = None
    e.save(update_fields=['status', 'result_data', 'error_message',
                          'completed_at', 'resume_at'])
    return Response({'status': 'success', 'data': _serialize_execution_brief(e)})


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
    trigger_config = d.get('trigger_config') or {}
    if trigger_config:
        event_on = trigger_config.get('on')
        if not event_on:
            return Response({
                'status': 'error',
                'message': "trigger_config must include an 'on' key specifying the event name.",
            }, status=status.HTTP_400_BAD_REQUEST)
        if event_on not in _HR_NOTIFICATION_KNOWN_EVENTS:
            return Response({
                'status': 'error',
                'message': (
                    f"Unknown trigger event '{event_on}'. "
                    f"Recognised events: {', '.join(sorted(_HR_NOTIFICATION_KNOWN_EVENTS))}."
                ),
            }, status=status.HTTP_400_BAD_REQUEST)
    t = HRNotificationTemplate.objects.create(
        company=company, name=name, body=body,
        subject=d.get('subject') or '',
        channel=d.get('channel') or 'email',
        notification_type=d.get('notification_type') or 'system',
        trigger_config=trigger_config,
        use_llm_personalization=bool(d.get('use_llm_personalization', False)),
    )
    _write_audit_log(request.user, company, 'hr_notification_template.create',
                     'HRNotificationTemplate', t.id,
                     before=None,
                     after={'name': t.name, 'channel': t.channel,
                            'notification_type': t.notification_type,
                            'trigger_config': t.trigger_config})
    return Response({'status': 'success', 'data': {'id': t.id, 'name': t.name}},
                    status=status.HTTP_201_CREATED)


# Small set of trigger events we accept from the client. Kept module-level so
# `create_` and `update_` stay in sync — if you add a new event, both endpoints
# pick it up automatically.
_HR_NOTIFICATION_KNOWN_EVENTS = {
    'probation_ending', 'birthday', 'work_anniversary',
    'document_expiring', 'review_due',
}


@api_view(['PATCH', 'PUT'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def update_hr_notification_template(request, template_id):
    """Edit an HR notification template. All fields optional — only the
    keys present in the request body are updated. Mirrors the same event
    validation as create so a bad `trigger_config.on` fails cleanly instead
    of silently persisting garbage that would fire nothing at run time."""
    company = request.user.company
    try:
        t = HRNotificationTemplate.objects.get(id=template_id, company=company)
    except HRNotificationTemplate.DoesNotExist:
        return Response({'status': 'error', 'message': 'Template not found'},
                        status=status.HTTP_404_NOT_FOUND)

    d = request.data or {}
    dirty = []
    before = {'name': t.name, 'channel': t.channel,
              'notification_type': t.notification_type,
              'subject': t.subject,
              'trigger_config': t.trigger_config,
              'use_llm_personalization': t.use_llm_personalization}

    if 'name' in d:
        name = str(d.get('name') or '').strip()
        if not name:
            return Response({'status': 'error', 'message': 'name cannot be empty'},
                            status=status.HTTP_400_BAD_REQUEST)
        t.name = name[:200]
        dirty.append('name')
    if 'body' in d:
        body = str(d.get('body') or '').strip()
        if not body:
            return Response({'status': 'error', 'message': 'body cannot be empty'},
                            status=status.HTTP_400_BAD_REQUEST)
        t.body = body
        dirty.append('body')
    if 'subject' in d:
        t.subject = str(d.get('subject') or '')[:500]
        dirty.append('subject')
    if 'channel' in d:
        t.channel = str(d.get('channel') or 'email').strip()[:20]
        dirty.append('channel')
    if 'notification_type' in d:
        t.notification_type = str(d.get('notification_type') or 'system').strip()[:50]
        dirty.append('notification_type')
    if 'use_llm_personalization' in d:
        t.use_llm_personalization = bool(d.get('use_llm_personalization'))
        dirty.append('use_llm_personalization')
    if 'trigger_config' in d:
        trigger_config = d.get('trigger_config') or {}
        if trigger_config:
            event_on = trigger_config.get('on')
            if not event_on:
                return Response({'status': 'error',
                                 'message': "trigger_config must include an 'on' key."},
                                status=status.HTTP_400_BAD_REQUEST)
            if event_on not in _HR_NOTIFICATION_KNOWN_EVENTS:
                return Response({'status': 'error', 'message': (
                    f"Unknown trigger event '{event_on}'. Recognised: "
                    f"{', '.join(sorted(_HR_NOTIFICATION_KNOWN_EVENTS))}."
                )}, status=status.HTTP_400_BAD_REQUEST)
        t.trigger_config = trigger_config
        dirty.append('trigger_config')

    if not dirty:
        return Response({'status': 'error',
                         'message': 'No editable fields provided.'},
                        status=status.HTTP_400_BAD_REQUEST)

    dirty.append('updated_at')
    t.save(update_fields=list(set(dirty)))
    _write_audit_log(request.user, company, 'hr_notification_template.update',
                     'HRNotificationTemplate', t.id, before,
                     after={'name': t.name, 'channel': t.channel,
                            'notification_type': t.notification_type,
                            'subject': t.subject,
                            'trigger_config': t.trigger_config,
                            'use_llm_personalization': t.use_llm_personalization,
                            'fields_changed': sorted(set(dirty) - {'updated_at'})})
    return Response({'status': 'success', 'data': {
        'id': t.id, 'name': t.name, 'channel': t.channel,
        'notification_type': t.notification_type,
        'subject': t.subject, 'body': t.body,
        'trigger_config': t.trigger_config,
        'use_llm_personalization': t.use_llm_personalization,
    }})


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def delete_hr_notification_template(request, template_id):
    """Delete an HR notification template. Scheduled notifications that
    already reference this template stay (`template_id` becomes null on the
    row via FK-null-on-delete, if the model allows; otherwise cascade). The
    template is company-scoped, so this endpoint only ever touches the
    caller's own data."""
    company = request.user.company
    try:
        t = HRNotificationTemplate.objects.get(id=template_id, company=company)
    except HRNotificationTemplate.DoesNotExist:
        return Response({'status': 'error', 'message': 'Template not found'},
                        status=status.HTTP_404_NOT_FOUND)
    snap = {'name': t.name, 'channel': t.channel,
            'notification_type': t.notification_type,
            'subject': t.subject,
            'trigger_config': t.trigger_config}
    template_name = t.name
    t.delete()
    _write_audit_log(request.user, company, 'hr_notification_template.delete',
                     'HRNotificationTemplate', int(template_id),
                     before=snap, after=None)
    return Response({'status': 'success', 'data': {'id': int(template_id), 'name': template_name}})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def send_hr_notification_now(request):
    """Fire a template right now — for testing a new template, sending a
    one-off HR announcement, or resending a stuck scheduled notification.

    Body:
      * ``template_id``          (int, required) — must be a template in the
                                  caller's company.
      * ``recipient_email``      (str, optional) — direct address.
      * ``recipient_employee_id`` (int, optional) — resolves to the
                                  employee's `work_email` if `recipient_email`
                                  isn't set. At least one of the two must be
                                  usable at dispatch time.
      * ``context``              (dict, optional) — substitution values for
                                  the template placeholders. Missing keys
                                  format to empty strings, not KeyError.

    Restricted to HR admins so ordinary employees can't fan mail out
    through the office notification channels.

    Writes an ``HRScheduledNotification`` row for the sent (or failed)
    dispatch so it lands in the same audit view as walker-fanned messages.
    """
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR admin only.'},
                        status=status.HTTP_403_FORBIDDEN)
    company = request.user.company
    d = request.data or {}
    try:
        template_id = int(d.get('template_id'))
    except (TypeError, ValueError):
        return Response({'status': 'error', 'message': 'template_id is required'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        template = HRNotificationTemplate.objects.get(id=template_id, company=company)
    except HRNotificationTemplate.DoesNotExist:
        return Response({'status': 'error', 'message': 'Template not found'},
                        status=status.HTTP_404_NOT_FOUND)

    recipient_email = (d.get('recipient_email') or '').strip()
    recipient_employee = None
    rec_emp_id = d.get('recipient_employee_id')
    if rec_emp_id:
        try:
            recipient_employee = Employee.objects.get(id=int(rec_emp_id), company=company)
        except (Employee.DoesNotExist, TypeError, ValueError):
            return Response({'status': 'error', 'message': 'recipient_employee_id not found'},
                            status=status.HTTP_400_BAD_REQUEST)
        if not recipient_email:
            recipient_email = getattr(recipient_employee, 'work_email', '') or ''

    # For non-email channels the recipient address is a fallback log field,
    # not the routing key — Slack/Teams post into the company's channel.
    is_addressable_channel = (template.channel or 'email').lower() == 'email'
    if is_addressable_channel and not recipient_email:
        return Response({'status': 'error',
                         'message': 'recipient_email (or an employee with work_email) is required for email templates.'},
                        status=status.HTTP_400_BAD_REQUEST)

    # ── Render the subject + body using the caller's context. ────
    context = d.get('context') or {}
    # Provide a couple of automatic keys for convenience so simple templates
    # like "Welcome {{employee_name}}" work when a recipient_employee is set.
    if recipient_employee:
        context.setdefault('employee_name', recipient_employee.full_name)
    # `format_map` with a defaultdict-like tolerates missing keys instead of
    # raising KeyError, which is the friendlier behaviour for a manual
    # "send now" (the sender might be testing before filling every slot).
    class _SafeDict(dict):
        def __missing__(self, key):
            return f'{{{key}}}'  # leave the placeholder visible so it's obvious what's unresolved
    safe = _SafeDict(context)
    try:
        rendered_subject = (template.subject or '').format_map(safe)
        rendered_body = (template.body or '').format_map(safe)
    except (IndexError, ValueError):
        # e.g. template used `{0}` positional; fall back to raw
        rendered_subject = template.subject or ''
        rendered_body = template.body or ''

    ok, channel_used = _dispatch_hr_notification(
        template, recipient_email, rendered_subject, rendered_body, company,
    )
    now = timezone.now()
    scheduled = HRScheduledNotification.objects.create(
        company=company,
        template=template,
        recipient_employee=recipient_employee,
        recipient_email=recipient_email,
        scheduled_at=now,
        status='sent' if ok else 'failed',
        sent_at=now if ok else None,
        error_message=None if ok else f'send-now via {channel_used} returned false',
        attempts=1,
        context=context,
    )
    return Response({'status': 'success', 'data': {
        'ok': ok,
        'channel_used': channel_used,
        'scheduled_notification_id': scheduled.id,
        'rendered_subject': rendered_subject,
        'template_id': template.id,
    }})


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
    _write_audit_log(request.user, company, 'hr_meeting.create', 'HRMeeting', m.id,
                     before=None,
                     after={'title': m.title, 'meeting_type': m.meeting_type,
                            'visibility': m.visibility,
                            'scheduled_at': m.scheduled_at.isoformat() if m.scheduled_at else None,
                            'duration_minutes': m.duration_minutes,
                            'organizer_id': m.organizer_id,
                            'participant_count': m.participants.count()})
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
    """Create a LeaveRequest. Computes working days (skips weekends + company
    holidays), auto-assigns the manager (or HR fallback) as approver, and
    fires the `leave_request_submitted` workflow signal."""
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

        from hr_agent.leave_helpers import working_days_between, resolve_approver_for_leave

        # F2 — partial-day metadata. When set, the request represents less than
        # a full working day on a single date; we derive days_requested from
        # the period rather than the date span.
        partial_period = (d.get('partial_day_period') or '').strip().lower()
        valid_periods = {'', 'morning', 'afternoon', 'hours'}
        if partial_period not in valid_periods:
            return Response({
                'status': 'error',
                'message': f"partial_day_period must be one of {sorted(valid_periods - {''})} or omitted for a full day.",
            }, status=status.HTTP_400_BAD_REQUEST)
        partial_hours_val = None
        if partial_period:
            if sd != ed:
                return Response({
                    'status': 'error',
                    'message': 'Partial-day requests must have start_date == end_date.',
                }, status=status.HTTP_400_BAD_REQUEST)
            if partial_period == 'hours':
                try:
                    partial_hours_val = float(d.get('partial_hours'))
                except (TypeError, ValueError):
                    return Response({
                        'status': 'error',
                        'message': 'partial_hours is required (decimal hours, e.g. 2.5) when partial_day_period="hours".',
                    }, status=status.HTTP_400_BAD_REQUEST)
                if not (0 < partial_hours_val < 8):
                    return Response({
                        'status': 'error',
                        'message': 'partial_hours must be > 0 and < 8 (anything >= 8 should be a full day).',
                    }, status=status.HTTP_400_BAD_REQUEST)
                days_requested = round(partial_hours_val / 8.0, 2)
            else:  # morning / afternoon
                days_requested = 0.5
        else:
            # Caller can override (e.g. legacy half-day requests); otherwise compute.
            days_requested = d.get('days_requested')
            if days_requested in (None, ''):
                days_requested = working_days_between(sd, ed, company)
            else:
                try:
                    days_requested = float(days_requested)
                except (TypeError, ValueError):
                    days_requested = working_days_between(sd, ed, company)

        approver = resolve_approver_for_leave(emp, company)
        lr = LeaveRequest.objects.create(
            employee=emp,
            leave_type=d.get('leave_type') or 'vacation',
            start_date=sd, end_date=ed,
            days_requested=days_requested,
            partial_day_period=partial_period,
            partial_hours=partial_hours_val,
            reason=(d.get('reason') or '')[:2000],
            status='pending',
            approver=approver,
        )
        return Response({'status': 'success', 'data': {
            'id': lr.id, 'employee_id': emp.id, 'status': lr.status,
            'days_requested': float(lr.days_requested),
            'partial_day_period': lr.partial_day_period,
            'partial_hours': float(lr.partial_hours) if lr.partial_hours is not None else None,
            'approver_id': lr.approver_id,
            'approver_name': lr.approver.full_name if lr.approver_id else None,
        }}, status=status.HTTP_201_CREATED)
    except Exception:
        logger.exception("submit_leave_request failed")
        return Response({'status': 'error', 'message': 'Failed to submit leave request'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def update_leave_request(request, request_id):
    """Edit a still-pending leave request.
    Only the original submitting employee (or HR-admin) may do this.
    Once the request is approved / rejected it is locked."""
    try:
        company = request.user.company
        lr = LeaveRequest.objects.filter(pk=request_id, employee__company=company).first()
        if not lr:
            return Response({'status': 'error', 'message': 'Leave request not found'},
                            status=status.HTTP_404_NOT_FOUND)

        is_admin = _is_hr_admin(request.user)
        caller_user_id = getattr(request.user, 'user_id', None)
        is_owner = caller_user_id and str(caller_user_id) == str(lr.employee.user_id)
        if not (is_admin or is_owner):
            return Response({'status': 'error', 'message': 'Not authorized to edit this leave request'},
                            status=status.HTTP_403_FORBIDDEN)
        if lr.status != 'pending':
            return Response({
                'status': 'error',
                'message': f'Leave request is already {lr.status} and cannot be edited.',
            }, status=status.HTTP_400_BAD_REQUEST)

        d = request.data or {}
        fields = []
        before = {'leave_type': lr.leave_type, 'reason': lr.reason,
                  'start_date': lr.start_date.isoformat(),
                  'end_date': lr.end_date.isoformat(),
                  'days_requested': float(lr.days_requested or 0)}
        if 'leave_type' in d:
            lr.leave_type = d['leave_type'] or lr.leave_type
            fields.append('leave_type')
        if 'reason' in d:
            lr.reason = (d['reason'] or '')[:2000]
            fields.append('reason')
        if 'start_date' in d or 'end_date' in d:
            try:
                sd = datetime.fromisoformat(d['start_date']).date() if 'start_date' in d else lr.start_date
                ed = datetime.fromisoformat(d['end_date']).date() if 'end_date' in d else lr.end_date
            except (TypeError, ValueError):
                return Response({'status': 'error', 'message': 'Dates must be YYYY-MM-DD'},
                                status=status.HTTP_400_BAD_REQUEST)
            if ed < sd:
                return Response({'status': 'error', 'message': 'end_date must be on or after start_date'},
                                status=status.HTTP_400_BAD_REQUEST)
            lr.start_date, lr.end_date = sd, ed
            fields += ['start_date', 'end_date']
            # Recompute working days unless the caller overrides explicitly.
            days = d.get('days_requested')
            if days in (None, ''):
                from hr_agent.leave_helpers import working_days_between
                lr.days_requested = working_days_between(sd, ed, company)
            else:
                try:
                    lr.days_requested = float(days)
                except (TypeError, ValueError):
                    from hr_agent.leave_helpers import working_days_between
                    lr.days_requested = working_days_between(sd, ed, company)
            fields.append('days_requested')
        if fields:
            fields.append('updated_at')
            lr.save(update_fields=fields)
            _write_audit_log(request.user, company, 'leave_request.update',
                             'leave_request', lr.id, before,
                             after={'leave_type': lr.leave_type, 'reason': lr.reason,
                                    'start_date': lr.start_date.isoformat(),
                                    'end_date': lr.end_date.isoformat(),
                                    'days_requested': float(lr.days_requested or 0),
                                    'fields_changed': sorted(set(fields) - {'updated_at'})})
        return Response({'status': 'success', 'data': {
            'id': lr.id, 'status': lr.status,
            'start_date': lr.start_date.isoformat(), 'end_date': lr.end_date.isoformat(),
            'leave_type': lr.leave_type, 'days_requested': float(lr.days_requested),
            'reason': lr.reason,
        }})
    except Exception:
        logger.exception("update_leave_request failed")
        return Response({'status': 'error', 'message': 'Failed to update leave request'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def cancel_leave_request(request, request_id):
    """Withdraw a still-pending leave request. Owner or HR-admin only — the
    approver does not cancel; they reject. Distinct status from `rejected` so
    the audit trail tells the right story ("I changed my mind" vs "denied").
    Locks once decided."""
    try:
        company = request.user.company
        lr = LeaveRequest.objects.filter(pk=request_id, employee__company=company).first()
        if not lr:
            return Response({'status': 'error', 'message': 'Leave request not found'},
                            status=status.HTTP_404_NOT_FOUND)
        is_admin = _is_hr_admin(request.user)
        caller_user_id = getattr(request.user, 'user_id', None)
        is_owner = caller_user_id and str(caller_user_id) == str(lr.employee.user_id)
        if not (is_admin or is_owner):
            return Response({'status': 'error', 'message': 'Only the submitter or HR-admin can cancel this request'},
                            status=status.HTTP_403_FORBIDDEN)
        if lr.status != 'pending':
            return Response({
                'status': 'error',
                'message': f'Leave request is already {lr.status} and cannot be cancelled.',
            }, status=status.HTTP_400_BAD_REQUEST)

        prev_status = lr.status
        lr.status = 'cancelled'
        lr.decided_at = timezone.now()
        lr.approval_note = (request.data.get('note') or '')[:2000]
        lr.save(update_fields=['status', 'decided_at', 'approval_note', 'updated_at'])

        _write_audit_log(
            request.user, company, 'leave_request.cancel',
            'leave_request', lr.id,
            before={'status': prev_status},
            after={'status': lr.status, 'employee_id': lr.employee_id,
                   'days_requested': float(lr.days_requested or 0)},
        )
        return Response({'status': 'success', 'data': {'id': lr.id, 'status': lr.status}})
    except Exception:
        logger.exception("cancel_leave_request failed")
        return Response({'status': 'error', 'message': 'Failed to cancel leave request'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def withdraw_leave_request(request, request_id):
    """Withdraw an already-*approved* leave. Distinct from cancel (which acts on
    pending requests): withdraw restores the `used_days` that were deducted at
    approval time, so the employee's balance goes back up.

    Guardrails:
      * Only owner or HR-admin can withdraw.
      * Only status='approved' is withdrawable — cancelled/rejected/pending
        can't come here.
      * Once the leave has fully passed (end_date < today), only HR-admin can
        withdraw. The rationale: an employee retroactively withdrawing leave
        they already took would let them double-dip on balance. HR-admin can
        still do it (data corrections happen), but it's flagged in audit.
      * `reason` is required — the audit trail is the whole point.
    """
    try:
        from django.db import transaction
        from django.db.models import F
        company = request.user.company
        reason = (request.data.get('reason') or '').strip()
        if not reason:
            return Response({'status': 'error', 'message': 'reason is required for withdraw'},
                            status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            lr = (LeaveRequest.objects
                  .select_for_update()
                  .filter(pk=request_id, employee__company=company)
                  .first())
            if not lr:
                return Response({'status': 'error', 'message': 'Leave request not found'},
                                status=status.HTTP_404_NOT_FOUND)

            is_admin = _is_hr_admin(request.user)
            caller_user_id = getattr(request.user, 'user_id', None)
            is_owner = caller_user_id and str(caller_user_id) == str(lr.employee.user_id)
            if not (is_admin or is_owner):
                return Response({'status': 'error',
                                 'message': 'Only the submitter or HR-admin can withdraw this leave'},
                                status=status.HTTP_403_FORBIDDEN)

            if lr.status != 'approved':
                return Response({
                    'status': 'error',
                    'message': (f"Leave request is {lr.status} — only approved leaves can be withdrawn. "
                                f"Use cancel for a pending request."),
                }, status=status.HTTP_400_BAD_REQUEST)

            today = timezone.now().date()
            already_taken = lr.end_date and lr.end_date < today
            if already_taken and not is_admin:
                return Response({
                    'status': 'error',
                    'message': ('This leave has already ended. Only HR-admin can withdraw a '
                                'past leave (contact HR for a correction).'),
                }, status=status.HTTP_400_BAD_REQUEST)

            prev_status = lr.status
            lr.status = 'withdrawn'
            lr.decided_at = timezone.now()
            note_prefix = '[withdraw] ' + reason
            lr.approval_note = (note_prefix + (('\n\nPrev note:\n' + lr.approval_note)
                                               if lr.approval_note else ''))[:2000]
            lr.save(update_fields=['status', 'decided_at', 'approval_note', 'updated_at'])

            # Restore used_days. Mirror-image of the approve deduction: same
            # F() atomic update, same year-scoped LeaveBalance row. If the
            # balance row doesn't exist for whatever reason (approved before
            # our LeaveBalance code existed?), skip silently rather than fail.
            restored = 0.0
            try:
                from hr_agent.models import LeaveBalance
                from datetime import date as _date
                year_start = _date(lr.start_date.year, 1, 1)
                bal = LeaveBalance.objects.filter(
                    employee_id=lr.employee_id, leave_type=lr.leave_type,
                    period_start=year_start,
                ).first()
                if bal:
                    days = float(lr.days_requested or 0)
                    # Floor at 0 — never let used_days go negative. If the
                    # balance was manually zeroed since approval, we can't
                    # restore more than what's there.
                    from django.db.models import Case, When, Value, DecimalField
                    LeaveBalance.objects.filter(pk=bal.pk).update(
                        used_days=Case(
                            When(used_days__lte=days, then=Value(0)),
                            default=F('used_days') - days,
                            output_field=DecimalField(max_digits=6, decimal_places=2),
                        ),
                        updated_at=timezone.now(),
                    )
                    restored = days
            except Exception:
                logger.exception("withdraw_leave_request: failed to restore LeaveBalance for lr %s", lr.id)

        _write_audit_log(
            request.user, company, 'leave_request.withdraw',
            'leave_request', lr.id,
            before={'status': prev_status},
            after={'status': lr.status, 'employee_id': lr.employee_id,
                   'leave_type': lr.leave_type,
                   'days_requested': float(lr.days_requested or 0),
                   'days_restored': restored,
                   'after_end_date': bool(already_taken),
                   'reason': reason[:500]},
        )
        return Response({'status': 'success',
                         'data': {'id': lr.id, 'status': lr.status,
                                  'days_restored': restored}})
    except Exception:
        logger.exception("withdraw_leave_request failed")
        return Response({'status': 'error', 'message': 'Failed to withdraw leave request'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def decide_leave_request(request, request_id):
    """Approve or reject a pending leave request. Permission rules:
      * The request's `approver` (set at submit time, defaults to manager).
      * Any HR-roled CompanyUser (role='hr_agent', or company `owner`/`admin`).
    Body: ``{action: 'approve'|'reject', note?: str}``.

    On approval, deducts ``days_requested`` from the employee's
    ``LeaveBalance.used_days`` for that leave_type.
    """
    try:
        from django.db import transaction
        from django.db.models import F
        company = request.user.company
        action = (request.data or {}).get('action')
        if action not in ('approve', 'reject'):
            return Response({'status': 'error', 'message': "action must be 'approve' or 'reject'"},
                            status=status.HTTP_400_BAD_REQUEST)

        # Race-safe: lock the LeaveRequest row before we read its status.
        # Without select_for_update, two concurrent approve calls both read
        # status='pending', both flip to 'approved', and both decrement
        # LeaveBalance — taking the balance down twice the requested days.
        # The lock serialises them; the second one sees status='approved'
        # post-lock and returns the 400 below.
        cu = request.user
        with transaction.atomic():
            lr = (LeaveRequest.objects
                  .select_for_update()
                  .filter(pk=request_id, employee__company=company)
                  .first())
            if not lr:
                return Response({'status': 'error', 'message': 'Leave request not found'},
                                status=status.HTTP_404_NOT_FOUND)
            if lr.status != 'pending':
                return Response({'status': 'error', 'message': f'Leave request is {lr.status}, not pending'},
                                status=status.HTTP_400_BAD_REQUEST)

            # Permission gate
            is_hr_admin = (cu.role or '').lower() in ('hr_agent', 'owner', 'admin', 'company_user')
            approver_emp = (Employee.objects.filter(company=company, company_user=cu).first()
                            or Employee.objects.filter(company=company, work_email__iexact=cu.email).first())
            is_assigned_approver = bool(lr.approver_id and approver_emp and lr.approver_id == approver_emp.id)
            if not (is_hr_admin or is_assigned_approver):
                return Response({'status': 'error',
                                 'message': "You aren't authorized to decide this request — "
                                            "must be the assigned approver or HR admin."},
                                status=status.HTTP_403_FORBIDDEN)

            prev_status = lr.status
            lr.status = 'approved' if action == 'approve' else 'rejected'
            lr.approval_note = (request.data.get('note') or '')[:2000]
            lr.decided_at = timezone.now()
            lr.save(update_fields=['status', 'approval_note', 'decided_at', 'updated_at'])

            # Bump used_days on approval. F() expression is atomic at the DB
            # level — no read-modify-write window — so even if a second
            # request slipped past the lock (it can't, but defence in depth),
            # the increment wouldn't compound.
            if lr.status == 'approved':
                try:
                    from hr_agent.models import LeaveBalance
                    from datetime import date as _date
                    # Scope the balance to the leave year so used_days doesn't
                    # bleed across annual accrual cycles.
                    year_start = _date(lr.start_date.year, 1, 1)
                    bal, _ = LeaveBalance.objects.get_or_create(
                        employee_id=lr.employee_id,
                        leave_type=lr.leave_type,
                        period_start=year_start,
                    )
                    LeaveBalance.objects.filter(pk=bal.pk).update(
                        used_days=F('used_days') + (lr.days_requested or 0),
                        updated_at=timezone.now(),
                    )
                except Exception:
                    logger.exception("decide_leave_request: failed to bump LeaveBalance for lr %s", lr.id)

        # Audit — leave decisions are the most compliance-sensitive HR action.
        # Written AFTER the atomic block commits so a logging failure can't
        # roll back the actual approval.
        _write_audit_log(
            cu, company,
            f'leave_request.{action}',
            'leave_request', lr.id,
            before={'status': prev_status},
            after={
                'status': lr.status,
                'approval_note': lr.approval_note,
                'decided_at': lr.decided_at.isoformat(),
                'employee_id': lr.employee_id,
                'leave_type': lr.leave_type,
                'days_requested': float(lr.days_requested or 0),
            },
        )

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


def _is_int(v) -> bool:
    try:
        int(v)
        return True
    except (TypeError, ValueError):
        return False


# Time-reference tokens the user might use to indicate a date/time. If the
# raw message contains none of these, we know the LLM invented a time and
# override to `needs_time`.
_HR_TIME_TOKENS = (
    'today', 'tomorrow', 'tonight', 'this morning', 'this afternoon',
    'this evening', 'this week', 'next week', 'next month', 'next year',
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
    'mon ', 'tue ', 'wed ', 'thu ', 'fri ', 'sat ', 'sun ',
    'january', 'february', 'march', 'april', 'may', 'june', 'july',
    'august', 'september', 'october', 'november', 'december',
    ' jan ', ' feb ', ' mar ', ' apr ', ' jun ', ' jul ',
    ' aug ', ' sep ', ' oct ', ' nov ', ' dec ',
    ' am', ' pm', 'a.m', 'p.m',
    "o'clock", 'oclock', 'noon', 'midnight',
    ':00', ':15', ':30', ':45',
    'in an hour', 'in a hour', 'in half an hour',
)
_HR_TIME_REGEX = re.compile(
    r'\b('
    r'\d{1,2}\s*[:.]\s*\d{2}'         # 14:30, 2.30
    r'|\d{1,2}\s*(am|pm|a\.m|p\.m)'  # 3pm, 10 am
    r'|\d{4}-\d{2}-\d{2}'             # 2026-07-08
    r'|\d{1,2}/\d{1,2}(/\d{2,4})?'    # 7/8, 7/8/26
    r'|\d{1,2}(st|nd|rd|th)'          # 5th, 21st
    r'|in\s+\d+\s+(min|minute|hour|day|week|month)'
    r')\b',
    re.IGNORECASE,
)


def _hr_message_has_time_reference(message: str) -> bool:
    """Cheap heuristic: does the user's message contain any temporal
    reference at all? Used to catch cases where the LLM invents a time
    ("tomorrow at midnight") that the user never asked for."""
    if not message:
        return False
    low = message.lower()
    if any(tok in low for tok in _HR_TIME_TOKENS):
        return True
    return bool(_HR_TIME_REGEX.search(message))


def _hr_find_users_in_message(message: str, all_emps):
    """Deterministically scan the raw user message for employee references.
    Mirrors the two-pass algorithm from the PM meeting scheduler agent so
    HR gets the same quality of matching. Returns::

        {
          'all_matched': [Employee, ...],   # every user unambiguously found
          'ambiguous_token': str|None,      # a token that matched multiple people
          'ambiguous_candidates': [Employee, ...],
        }

    Matching cascade per pass:
      Pass 1 (strong, consumes tokens): full name, work email, email prefix.
      Pass 2 (partial, uses only unconsumed tokens): any name-token whose
      length ≥ 3 characters and hasn't already been claimed by a pass-1 hit.

    "Consumed" tokens keep us from double-matching users whose names are
    anagrams or share tokens (the PM code's example: "Fatima Noor" vs
    "Noor Fatima")."""
    if not message:
        return {'all_matched': [], 'ambiguous_token': None, 'ambiguous_candidates': []}

    msg_lower = message.lower()

    def _name_tokens(full_name: str):
        return [p for p in (full_name or '').lower().split() if len(p) >= 3]

    found_ids = set()
    found = []
    consumed = set()

    # ── Pass 1a: strongest — full-name matches across ALL employees first.
    # We do this before email/prefix so that a full-name hit gets to consume
    # its tokens before another employee's email prefix (which might be one
    # of those same tokens) can match. Prevents "fatima noor" from double-
    # matching both "Fatima Noor" (full name) and "Noor Fatima" (whose email
    # prefix "noor" would otherwise hit).
    for e in all_emps:
        full = (e.full_name or '').strip().lower()
        if full and re.search(r'\b' + re.escape(full) + r'\b', msg_lower):
            if e.id not in found_ids:
                found.append(e)
                found_ids.add(e.id)
                consumed.update(_name_tokens(e.full_name))

    # Precompute which name-tokens are shared across employees. We use
    # this to reject an email-prefix match if the prefix is also somebody
    # else's first/last name (would otherwise silently pick the wrong Ali).
    from collections import Counter as _Counter
    token_counts = _Counter()
    for e in all_emps:
        for t in _name_tokens(e.full_name):
            token_counts[t] += 1

    # ── Pass 1b: full email / email prefix matches. Full email is always
    # strong; email prefix is strong only if no other employee shares it
    # as a name-token AND it isn't already consumed by a pass-1a hit.
    for e in all_emps:
        if e.id in found_ids:
            continue
        email = (e.work_email or '').strip().lower()
        if not email:
            continue
        prefix = email.split('@')[0] if '@' in email else email

        strong = False
        if email in msg_lower:
            strong = True
        elif (len(prefix) >= 3
              and prefix not in consumed
              and token_counts.get(prefix, 0) <= 1
              and re.search(r'\b' + re.escape(prefix) + r'\b', msg_lower)):
            strong = True

        if strong:
            found.append(e)
            found_ids.add(e.id)
            consumed.update(_name_tokens(e.full_name))

    # ── Pass 2: partial matches on unconsumed tokens (first/last/middle name). ──
    # Track ambiguity: if a token matches multiple people, we bubble that up
    # so the caller can ask the user to disambiguate.
    ambiguous_token = None
    ambiguous_candidates = []
    for e in all_emps:
        if e.id in found_ids:
            continue
        tokens = _name_tokens(e.full_name)
        useful = [t for t in tokens if t not in consumed]
        if not useful:
            continue
        for tok in useful:
            if re.search(r'\b' + re.escape(tok) + r'\b', msg_lower):
                # Check other unmatched employees for the same token → ambiguity.
                same_token = [
                    other for other in all_emps
                    if other.id not in found_ids
                    and tok in _name_tokens(other.full_name)
                    and tok not in consumed
                ]
                if len(same_token) > 1:
                    ambiguous_token = tok
                    ambiguous_candidates = same_token[:5]
                    # Don't add any — ambiguous.
                else:
                    found.append(e)
                    found_ids.add(e.id)
                break

    return {
        'all_matched': found,
        'ambiguous_token': ambiguous_token,
        'ambiguous_candidates': ambiguous_candidates,
    }


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

    Participant safety: names the LLM extracts are resolved SERVER-SIDE
    against the real employee table. If a mentioned participant doesn't
    exist (or is ambiguous), we override the LLM's reply and refuse to
    create the meeting — the LLM otherwise happily hallucinates people.
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
        # Cache the full Employee objects for our own name resolver below.
        all_emps = list(Employee.objects.filter(company=company))
        directory_hint = "\n".join(
            f"  • {e['full_name']} ({e['job_title'] or 'no title'})"
            for e in emp_rows[:15]
        ) + (f"\n  … and {len(emp_rows) - 15} more" if len(emp_rows) > 15 else '')

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
            "   \"participant_names\": [str]|null,  // raw names from the user's message, verbatim.\n"
            "                          //   ALWAYS include this when the user mentions people, even if\n"
            "                          //   the name is not in the directory.\n"
            "   \"participant_ids\": [int]|null,  // pick ids ONLY from the directory below by\n"
            "                          //   exact/first-name match. If unsure, leave null and the\n"
            "                          //   server will resolve or ask for clarification.\n"
            "   \"location\": str|null, \"meeting_link\": str|null,\n"
            "   \"reply\": str  // friendly natural-language reply. NEVER claim to have scheduled\n"
            "                   //   a meeting — the server decides that. If a mentioned name is\n"
            "                   //   not in the directory below, set intent='clarify' and say so.\n"
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
        except KeyServiceError:
            raise
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

        # ---- Deterministic participant resolution ------------------------
        # We do NOT trust the LLM's participant_names or participant_ids for
        # the initial resolve — we scan the RAW USER MESSAGE ourselves using
        # the same two-pass algorithm the PM scheduler uses. The LLM's
        # extracted names are only used as a fallback for the "not-found"
        # error message.
        det = _hr_find_users_in_message(message, all_emps)
        all_matched_emps = det['all_matched']

        # Ambiguous single-token match (e.g. two employees both named "Ali").
        # We surface this even if other participants matched cleanly — the
        # user has to pick before we can schedule, otherwise the wrong
        # Fatima ends up in the invite.
        if det['ambiguous_candidates']:
            cand_lines = "\n".join(
                f"  • {e.full_name} ({e.job_title or 'no title'}, {e.work_email})"
                for e in det['ambiguous_candidates']
            )
            override_reply = (
                f"I found more than one match for \"{det['ambiguous_token']}\". "
                f"Which one did you mean?\n\n{cand_lines}"
            )
            return Response({'status': 'success', 'data': {
                'reply': override_reply,
                'meeting': None,
                'parsed': parsed,
                'action': 'ambiguous_user',
                'unresolved': {
                    'ambiguous_token': det['ambiguous_token'],
                    'ambiguous_candidates': [
                        {'id': e.id, 'full_name': e.full_name,
                         'work_email': e.work_email, 'job_title': e.job_title}
                        for e in det['ambiguous_candidates']
                    ],
                },
            }})

        # ---- User-not-found: only apply when the user clearly intended to
        # name someone but none of them exist. We look for LLM-extracted
        # participant_names as evidence of intent — if the user said
        # "schedule with X" and we found no X in the directory, we ask.
        raw_names = parsed.get('participant_names') or []
        if not isinstance(raw_names, list):
            raw_names = []
        if not all_matched_emps and raw_names:
            names_str = ', '.join(f'"{n}"' for n in raw_names)
            override_reply = (
                f"I couldn't find {names_str} in your company directory. "
                f"Please pick from these employees:\n\n{directory_hint}"
            )
            return Response({'status': 'success', 'data': {
                'reply': override_reply,
                'meeting': None,
                'parsed': parsed,
                'action': 'user_not_found',
                'unresolved': {
                    'not_found': raw_names,
                    'directory': [{'id': e['id'], 'full_name': e['full_name'],
                                   'job_title': e['job_title']} for e in emp_rows[:25]],
                },
            }})

        # ---- Combine deterministic matches with any explicit IDs the LLM
        # extracted (drop any that don't map to a real company employee). ---
        validated_ids = {e.id for e in all_matched_emps}
        llm_ids = parsed.get('participant_ids') or []
        if isinstance(llm_ids, list):
            allowed = set(Employee.objects.filter(
                pk__in=[int(x) for x in llm_ids if _is_int(x)], company=company,
            ).values_list('id', flat=True))
            validated_ids.update(allowed)

        if intent == 'create':
            # ---- Time resolution + hallucination guard -------------------
            # The LLM will sometimes invent a time ("tomorrow at midnight")
            # even when the user said nothing about when. If the raw message
            # has no temporal reference at all, we treat the LLM's
            # `scheduled_at` as bogus and ask for a real time.
            sched = None
            if _hr_message_has_time_reference(message):
                sched = _parse_iso_dt(parsed.get('scheduled_at'))

            if not sched:
                # We still know who this meeting is (probably) with — return
                # that context so the frontend can render a date/time picker
                # with the participants pre-filled.
                names_display = ', '.join(e.full_name for e in all_matched_emps) or 'the participants'
                return Response({'status': 'success', 'data': {
                    'reply': (
                        f"When should the meeting with **{names_display}** happen? "
                        "Please pick a date and time."
                    ),
                    'meeting': None,
                    'parsed': parsed,
                    'action': 'needs_time',
                    'needs_time': True,
                    'pending_intent': {
                        'title': parsed.get('title') or None,
                        'description': parsed.get('description') or '',
                        'meeting_type': parsed.get('meeting_type') or 'one_on_one',
                        'duration_minutes': int(parsed.get('duration_minutes') or 30),
                        'participant_ids': sorted(validated_ids),
                        'participant_names': [e.full_name for e in all_matched_emps],
                        'location': parsed.get('location') or '',
                        'meeting_link': parsed.get('meeting_link') or None,
                    },
                }})

            # Require at least one resolved participant OR the asker themselves,
            # otherwise the meeting has no one to meet with.
            if not validated_ids:
                return Response({'status': 'success', 'data': {
                    'reply': (
                        "Who should this meeting be with? Please tell me the participant's "
                        f"name from the directory:\n\n{directory_hint}"
                    ),
                    'meeting': None, 'parsed': parsed,
                    'action': 'user_not_found',
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
            valid = Employee.objects.filter(pk__in=validated_ids, company=company)
            m.participants.set(valid)
            meeting_payload = _serialize_hr_meeting(m)

            # Build a strong success reply so the frontend never has to guess.
            names_display = ', '.join(e.full_name for e in all_matched_emps) or 'the participants'
            time_display = sched.strftime('%A, %B %d, %Y at %I:%M %p')
            override_reply = (
                f"**Meeting Scheduled Successfully!**\n\n"
                f"**Title:** {m.title}\n"
                f"**With:** {names_display}\n"
                f"**When:** {time_display}\n"
                f"**Duration:** {m.duration_minutes} minutes\n"
            )
            return Response({'status': 'success', 'data': {
                'reply': override_reply,
                'meeting': meeting_payload,
                'parsed': parsed,
                'action': 'scheduled',
                'resolved_participants': [
                    {'id': e.id, 'full_name': e.full_name, 'work_email': e.work_email}
                    for e in all_matched_emps
                ],
            }})

        return Response({'status': 'success', 'data': {
            'reply': parsed.get('reply') or 'Done.',
            'meeting': meeting_payload,
            'parsed': parsed,
            'action': intent,
            'resolved_participants': [
                {'id': e.id, 'full_name': e.full_name, 'work_email': e.work_email}
                for e in all_matched_emps
            ],
        }})
    except KeyServiceError:
        raise
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
    before = {'title': m.title, 'status': m.status,
              'scheduled_at': m.scheduled_at.isoformat() if m.scheduled_at else None,
              'duration_minutes': m.duration_minutes,
              'visibility': m.visibility}
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
    participants_changed = False
    if 'participant_ids' in d:
        ids = d.get('participant_ids') or []
        if isinstance(ids, list):
            valid = Employee.objects.filter(pk__in=ids, company=request.user.company)
            m.participants.set(valid)
            participants_changed = True
    m.refresh_from_db()
    if dirty or participants_changed:
        _write_audit_log(request.user, request.user.company, 'hr_meeting.update',
                         'HRMeeting', m.id, before,
                         after={'title': m.title, 'status': m.status,
                                'scheduled_at': m.scheduled_at.isoformat() if m.scheduled_at else None,
                                'duration_minutes': m.duration_minutes,
                                'visibility': m.visibility,
                                'participant_count': m.participants.count() if participants_changed else None,
                                'fields_changed': sorted(set(dirty) - {'updated_at',
                                                                      'reminder_24h_sent_at',
                                                                      'reminder_15m_sent_at'})})
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
    prev_status = m.status
    m.status = 'cancelled'
    if reason:
        prefix = '\n\n[Cancelled] ' if m.notes else '[Cancelled] '
        m.notes = (m.notes or '') + prefix + reason
    m.save(update_fields=['status', 'notes', 'updated_at'])
    # Audit — cancellation was the only meeting mutation not logged. Compliance
    # queries like "who cancelled this exit interview?" now have an answer.
    _write_audit_log(
        request.user, request.user.company,
        'meeting.cancel', 'meeting', m.id,
        before={'status': prev_status},
        after={'status': 'cancelled', 'reason': reason[:500],
               'meeting_type': m.meeting_type,
               'scheduled_at': m.scheduled_at.isoformat() if m.scheduled_at else None},
    )
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
    except KeyServiceError:
        raise
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


# ============================================================================
# Leave requests — list with mine / pending filters
# ============================================================================

def _serialize_leave_request(lr) -> dict:
    return {
        'id': lr.id,
        'employee_id': lr.employee_id,
        'employee_name': lr.employee.full_name if lr.employee_id else None,
        'employee_email': lr.employee.work_email if lr.employee_id else None,
        'leave_type': lr.leave_type,
        'start_date': lr.start_date.isoformat() if lr.start_date else None,
        'end_date': lr.end_date.isoformat() if lr.end_date else None,
        'days_requested': float(lr.days_requested or 0),
        'reason': lr.reason or '',
        'status': lr.status,
        'approver_id': lr.approver_id,
        'approver_name': lr.approver.full_name if lr.approver_id else None,
        'approval_note': lr.approval_note or '',
        'decided_at': lr.decided_at.isoformat() if lr.decided_at else None,
        'created_at': lr.created_at.isoformat() if lr.created_at else None,
    }


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_leave_requests(request):
    """List leave requests in the caller's company.

    Filters (query params):
      ``?status=pending|approved|rejected|cancelled``
      ``?mine=1`` — only requests submitted BY the caller
      ``?pending_for_me=1`` — only pending requests where the caller is the approver
    """
    try:
        company = request.user.company
        qs = LeaveRequest.objects.filter(employee__company=company).select_related(
            'employee', 'approver',
        ).order_by('-created_at')

        if request.GET.get('status'):
            qs = qs.filter(status=request.GET['status'])

        if request.GET.get('mine') == '1':
            asker_emp = (Employee.objects.filter(company=company, company_user=request.user).first()
                         or Employee.objects.filter(company=company, work_email__iexact=request.user.email).first())
            if asker_emp:
                qs = qs.filter(employee=asker_emp)
            else:
                qs = qs.none()

        if request.GET.get('pending_for_me') == '1':
            asker_emp = (Employee.objects.filter(company=company, company_user=request.user).first()
                         or Employee.objects.filter(company=company, work_email__iexact=request.user.email).first())
            if asker_emp:
                qs = qs.filter(status='pending', approver=asker_emp)
            else:
                qs = qs.none()

        rows = [_serialize_leave_request(lr) for lr in qs[:200]]
        return Response({'status': 'success', 'data': rows, 'count': len(rows)})
    except Exception:
        logger.exception("list_leave_requests failed")
        return Response({'status': 'error', 'message': 'Failed to list leave requests'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# Holidays
# ============================================================================

def _serialize_holiday(h) -> dict:
    return {
        'id': h.id, 'name': h.name, 'date': h.date.isoformat() if h.date else None,
        'region': h.region or '', 'is_working_day': h.is_working_day,
        'notes': h.notes or '',
    }


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_holidays(request):
    from hr_agent.models import Holiday
    company = request.user.company
    qs = Holiday.objects.filter(company=company).order_by('date')
    year = request.GET.get('year')
    if year:
        try:
            qs = qs.filter(date__year=int(year))
        except ValueError:
            pass
    return Response({'status': 'success', 'data': [_serialize_holiday(h) for h in qs[:1000]]})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def create_holiday(request):
    from hr_agent.models import Holiday
    company = request.user.company
    d = request.data or {}
    name = (d.get('name') or '').strip()
    if not name or not d.get('date'):
        return Response({'status': 'error', 'message': 'name and date (YYYY-MM-DD) are required'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        date_val = datetime.fromisoformat(d['date']).date()
    except ValueError:
        return Response({'status': 'error', 'message': 'date must be YYYY-MM-DD'},
                        status=status.HTTP_400_BAD_REQUEST)
    h, created = Holiday.objects.get_or_create(
        company=company, date=date_val, region=(d.get('region') or '').strip(),
        defaults={
            'name': name[:200],
            'is_working_day': bool(d.get('is_working_day', False)),
            'notes': d.get('notes') or '',
        },
    )
    before = None if created else {'name': h.name, 'is_working_day': h.is_working_day,
                                   'notes': h.notes}
    if not created:
        h.name = name[:200]
        h.is_working_day = bool(d.get('is_working_day', False))
        h.notes = d.get('notes') or ''
        h.save()
    _write_audit_log(request.user, company,
                     'holiday.create' if created else 'holiday.update',
                     'Holiday', h.id, before,
                     after={'name': h.name, 'date': h.date.isoformat(),
                            'region': h.region, 'is_working_day': h.is_working_day})
    return Response({'status': 'success', 'data': _serialize_holiday(h)},
                    status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(['DELETE', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def delete_holiday(request, holiday_id):
    from hr_agent.models import Holiday
    company = request.user.company
    h = Holiday.objects.filter(pk=holiday_id, company=company).first()
    if not h:
        return Response({'status': 'error', 'message': 'Holiday not found'},
                        status=status.HTTP_404_NOT_FOUND)
    snap = {'name': h.name, 'date': h.date.isoformat(), 'region': h.region}
    h.delete()
    _write_audit_log(request.user, company, 'holiday.delete',
                     'Holiday', int(holiday_id), before=snap, after=None)
    return Response({'status': 'success', 'data': {'deleted_id': int(holiday_id)}})


# ============================================================================
# Leave accrual policies
# ============================================================================

def _serialize_accrual_policy(p) -> dict:
    return {
        'id': p.id, 'leave_type': p.leave_type, 'period': p.period,
        'days_per_period': float(p.days_per_period or 0),
        'max_balance': float(p.max_balance) if p.max_balance is not None else None,
        'is_active': p.is_active,
        'last_run_at': p.last_run_at.isoformat() if p.last_run_at else None,
    }


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_accrual_policies(request):
    from hr_agent.models import LeaveAccrualPolicy
    qs = LeaveAccrualPolicy.objects.filter(company=request.user.company).order_by('leave_type')
    return Response({'status': 'success', 'data': [_serialize_accrual_policy(p) for p in qs]})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def upsert_accrual_policy(request):
    """Create or update an accrual policy for (company, leave_type)."""
    from hr_agent.models import LeaveAccrualPolicy
    company = request.user.company
    d = request.data or {}
    leave_type = (d.get('leave_type') or '').strip().lower()
    if leave_type not in {c[0] for c in LeaveBalance.LEAVE_TYPE_CHOICES}:
        return Response({'status': 'error', 'message': 'invalid leave_type'},
                        status=status.HTTP_400_BAD_REQUEST)
    p, created = LeaveAccrualPolicy.objects.get_or_create(company=company, leave_type=leave_type)
    before = None if created else {'period': p.period,
                                   'days_per_period': float(p.days_per_period or 0),
                                   'max_balance': float(p.max_balance) if p.max_balance is not None else None,
                                   'is_active': p.is_active}
    p.period = d.get('period') if d.get('period') in ('monthly', 'biweekly', 'annual') else (p.period or 'monthly')
    if 'days_per_period' in d:
        try:
            p.days_per_period = max(0, float(d['days_per_period']))
        except (TypeError, ValueError):
            pass
    if 'max_balance' in d:
        if d['max_balance'] in (None, ''):
            p.max_balance = None
        else:
            try:
                p.max_balance = max(0, float(d['max_balance']))
            except (TypeError, ValueError):
                pass
    if 'is_active' in d:
        p.is_active = bool(d['is_active'])
    p.save()
    _write_audit_log(request.user, company,
                     'accrual_policy.create' if created else 'accrual_policy.update',
                     'LeaveAccrualPolicy', p.id, before,
                     after={'leave_type': p.leave_type, 'period': p.period,
                            'days_per_period': float(p.days_per_period or 0),
                            'max_balance': float(p.max_balance) if p.max_balance is not None else None,
                            'is_active': p.is_active})
    return Response({'status': 'success', 'data': _serialize_accrual_policy(p)})


@api_view(['DELETE', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def delete_accrual_policy(request, policy_id):
    from hr_agent.models import LeaveAccrualPolicy
    company = request.user.company
    p = LeaveAccrualPolicy.objects.filter(pk=policy_id, company=company).first()
    if not p:
        return Response({'status': 'error', 'message': 'Policy not found'},
                        status=status.HTTP_404_NOT_FOUND)
    snap = {'leave_type': p.leave_type, 'period': p.period,
            'days_per_period': float(p.days_per_period or 0)}
    p.delete()
    _write_audit_log(request.user, company, 'accrual_policy.delete',
                     'LeaveAccrualPolicy', int(policy_id), before=snap, after=None)
    return Response({'status': 'success', 'data': {'deleted_id': int(policy_id)}})


# ============================================================================
# Employee detail (for the drawer UI)
# ============================================================================

def _build_employee_bundle(emp: Employee, company) -> dict:
    """Common bundle used by both ``get_employee_detail`` and the self-service
    ``/hr/me`` endpoint — profile, manager chain, balances, docs, leaves, meetings."""
    chain = []
    cur = emp.manager
    seen: set = set()
    while cur and cur.id not in seen and len(chain) < 5:
        chain.append({'id': cur.id, 'full_name': cur.full_name, 'job_title': cur.job_title})
        seen.add(cur.id)
        cur = cur.manager

    balances = list(emp.leave_balances.values('leave_type', 'accrued_days', 'used_days',
                                              'carried_over_days', 'period_start', 'period_end'))
    for b in balances:
        for k in ('accrued_days', 'used_days', 'carried_over_days'):
            b[k] = float(b[k] or 0)
        b['remaining'] = b['accrued_days'] + b['carried_over_days'] - b['used_days']
        for k in ('period_start', 'period_end'):
            b[k] = b[k].isoformat() if b.get(k) else None

    personal_docs = HRDocument.objects.filter(
        company=company, employee=emp,
    ).order_by('-created_at')[:50]
    leave_rows = LeaveRequest.objects.filter(employee=emp).order_by('-created_at')[:20]
    meetings = HRMeeting.objects.filter(
        company=company, participants=emp,
    ).order_by('-scheduled_at')[:10]
    goals = PerformanceGoal.objects.filter(employee=emp).order_by('-created_at')[:50]
    # Reviews are only included if released to the employee. Used in /me so an
    # employee sees their own closed reviews; harmless on the admin drawer
    # because the drawer also reads from list_employee_reviews separately.
    from hr_agent.models import PerformanceReview
    visible_reviews = PerformanceReview.objects.filter(
        employee=emp, visible_to_employee=True,
    ).select_related('cycle', 'reviewer').order_by('-cycle__period_start')[:10]

    return {
        'employee': _serialize_employee(emp),
        'manager_chain': chain,
        'leave_balances': balances,
        'personal_documents': [_serialize_hr_document(d) for d in personal_docs],
        'leave_requests': [_serialize_leave_request(lr) for lr in leave_rows],
        'meetings': [{
            'id': m.id, 'title': m.title, 'meeting_type': m.meeting_type,
            'scheduled_at': m.scheduled_at.isoformat() if m.scheduled_at else None,
            'status': m.status,
        } for m in meetings],
        'goals': [{
            'id': g.id, 'title': g.title, 'status': g.status,
            'progress_pct': g.progress_pct, 'weight_pct': g.weight_pct,
            'target_value': g.target_value, 'current_value': g.current_value,
            'due_date': g.due_date.isoformat() if g.due_date else None,
            'description': g.description,
            'cycle_id': g.cycle_id,
        } for g in goals],
        'released_reviews': [{
            'id': r.id,
            'cycle_id': r.cycle_id,
            'cycle_name': r.cycle.name if r.cycle_id else None,
            'period_start': r.cycle.period_start.isoformat() if r.cycle_id and r.cycle.period_start else None,
            'period_end': r.cycle.period_end.isoformat() if r.cycle_id and r.cycle.period_end else None,
            'reviewer_name': r.reviewer.full_name if r.reviewer_id else None,
            'overall_rating': r.overall_rating,
            'manager_summary': r.manager_summary,
            'strengths': r.strengths,
            'growth_areas': r.growth_areas,
            'status': r.status,
            'finalized_at': r.finalized_at.isoformat() if r.finalized_at else None,
        } for r in visible_reviews],
    }


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def get_employee_detail(request, employee_id):
    """Bundle every relevant view of one employee for the drawer:
    profile, manager chain, leave balances, personal documents, recent
    leave requests, recent meetings, recent workflow executions."""
    try:
        emp, err = _company_employee_or_404(request, employee_id)
        if err:
            return err
        return Response({'status': 'success',
                         'data': _build_employee_bundle(emp, request.user.company)})
    except Exception:
        logger.exception("get_employee_detail failed")
        return Response({'status': 'error', 'message': 'Failed to load employee detail'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def get_my_hr_profile(request):
    """Self-service entry point. Resolves the caller to their Employee row
    and returns the same bundle shape as ``get_employee_detail`` — no
    ``employee_id`` required from the client."""
    try:
        cu = request.user
        company = cu.company
        emp = (Employee.objects.filter(company=company, company_user=cu).first()
               or Employee.objects.filter(company=company, work_email__iexact=cu.email).first())
        if not emp:
            return Response({
                'status': 'error',
                'message': "No HR Employee record found for your account. Ask HR to set one up.",
            }, status=status.HTTP_404_NOT_FOUND)
        return Response({'status': 'success', 'data': _build_employee_bundle(emp, company)})
    except Exception:
        logger.exception("get_my_hr_profile failed")
        return Response({'status': 'error', 'message': 'Failed to load your profile'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# Compensation history (HR-only)
# ============================================================================

def _is_hr_admin(company_user) -> bool:
    """`hr_only` reads are restricted to roles in this set.

    ``company_user`` is the default role for dashboard logins — these are
    operators, not workforce. Workforce is modeled as the `Employee` row.
    So unless the CompanyUser is explicitly tagged as a non-admin role
    (e.g. ``'employee'`` or ``'manager'`` if a tenant chooses to use those),
    dashboard logins get HR-admin access for their own company.
    """
    return (company_user.role or '').lower() in (
        'hr_agent', 'owner', 'admin', 'company_user',
    )


def _write_audit_log(actor_cu, company, action: str, target_type: str, target_id: int,
                     *, before: dict | None = None, after: dict | None = None,
                     created: dict | None = None, deleted: dict | None = None) -> None:
    """Fire-and-forget audit log writer. Never raises — a logging failure
    must not roll back the main operation."""
    try:
        if created is not None:
            diff = {'created': created}
        elif deleted is not None:
            diff = {'deleted': deleted}
        else:
            diff = {}
            if before is not None:
                diff['before'] = before
            if after is not None:
                diff['after'] = after
        HRAuditLog.objects.create(
            company=company,
            actor=actor_cu,
            action=action,
            target_type=target_type,
            target_id=target_id,
            diff=diff,
        )
    except Exception:
        logger.exception("_write_audit_log failed: %s on %s:%s", action, target_type, target_id)


# ============================================================================
# Employee — update (PATCH/POST)
# ============================================================================

@api_view(['PATCH', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def update_employee(request, employee_id):
    """Update mutable fields on an existing employee.

    HR-admins can edit all fields. An employee can update their own ``phone``
    and ``timezone_name`` only (self-service). All HR-admin changes are written
    to ``HRAuditLog`` for the diff trail.
    """
    try:
        emp, err = _company_employee_or_404(request, employee_id)
        if err:
            return err

        company = request.user.company
        is_admin = _is_hr_admin(request.user)
        caller_user_id = getattr(request.user, 'user_id', None)
        is_self = caller_user_id and str(caller_user_id) == str(emp.user_id)

        if not (is_admin or is_self):
            return Response({'status': 'error', 'message': 'HR-admin access required'},
                            status=status.HTTP_403_FORBIDDEN)

        d = request.data or {}
        fields = []
        before = _serialize_employee(emp)

        # Self-service fields (any authenticated caller, for themselves).
        if 'phone' in d:
            emp.phone = (d['phone'] or '')[:40]
            fields.append('phone')
        if 'timezone_name' in d:
            emp.timezone_name = (d['timezone_name'] or 'UTC')[:64]
            fields.append('timezone_name')

        # HR-admin-only fields.
        if is_admin:
            if 'full_name' in d:
                name = (d['full_name'] or '').strip()[:255]
                if name:
                    emp.full_name = name
                    fields.append('full_name')
            if 'job_title' in d:
                emp.job_title = (d['job_title'] or '')[:160]
                fields.append('job_title')
            if 'personal_email' in d:
                emp.personal_email = (d['personal_email'] or '')[:254]
                fields.append('personal_email')
            if 'employment_status' in d:
                val = d['employment_status']
                if val not in dict(Employee.EMPLOYMENT_STATUS_CHOICES):
                    return Response({
                        'status': 'error',
                        'message': f"Unknown employment_status {val!r}. Must be one of "
                                   f"{sorted(dict(Employee.EMPLOYMENT_STATUS_CHOICES))}.",
                    }, status=status.HTTP_400_BAD_REQUEST)
                ok, err = _validate_employment_transition(
                    emp.employment_status, val, is_admin=is_admin,
                )
                if not ok:
                    return Response({'status': 'error', 'message': err},
                                    status=status.HTTP_400_BAD_REQUEST)
                emp.employment_status = val
                fields.append('employment_status')
            if 'employment_type' in d:
                val = d['employment_type']
                if val in dict(Employee.EMPLOYMENT_TYPE_CHOICES):
                    emp.employment_type = val
                    fields.append('employment_type')
            if 'start_date' in d:
                emp.start_date = _parse_iso_date(d['start_date'])
                fields.append('start_date')
            if 'probation_end_date' in d:
                emp.probation_end_date = _parse_iso_date(d['probation_end_date'])
                fields.append('probation_end_date')
            if 'manager_id' in d:
                mid = d['manager_id']
                if mid in (None, '', 0, '0'):
                    emp.manager = None
                else:
                    mgr = Employee.objects.filter(company=company, pk=mid).first()
                    if mgr and mgr.pk != emp.pk:
                        emp.manager = mgr
                fields.append('manager')
            # Department — prefer FK, fall back to string, auto-create if needed.
            dept_id = d.get('department_id')
            dept_str = (d.get('department') or '').strip()[:120]
            if dept_id is not None or dept_str:
                if dept_id:
                    dept = Department.objects.filter(company=company, pk=dept_id).first()
                    if dept:
                        emp.department_obj = dept
                        emp.department = dept_str or dept.name
                        if 'department_obj' not in fields:
                            fields.extend(['department_obj', 'department'])
                elif dept_str:
                    dept = (Department.objects.filter(company=company, name__iexact=dept_str).first()
                            or Department.objects.create(company=company, name=dept_str))
                    emp.department_obj = dept
                    emp.department = dept_str
                    if 'department_obj' not in fields:
                        fields.extend(['department_obj', 'department'])

        if not fields:
            return Response({'status': 'success', 'data': _serialize_employee(emp),
                             'message': 'No recognised fields to update'})

        fields_to_save = list(set(fields)) + ['updated_at']
        emp.save(update_fields=fields_to_save)

        after = _serialize_employee(emp)
        _write_audit_log(request.user, company, 'employee.update', 'employee', emp.id,
                         before=before, after=after)

        return Response({'status': 'success', 'data': _serialize_employee(emp)})
    except Exception:
        logger.exception("update_employee failed")
        return Response({'status': 'error', 'message': 'Failed to update employee'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# Employee lifecycle — deactivate / reactivate
#
# Before this pair, an HR admin who wanted to offboard someone had to go
# through the general `update_employee` endpoint and set `employment_status`
# to 'offboarded'. That works but has two problems:
#   1. The audit log entry is a generic diff instead of a distinct
#      "employee.deactivate" event that reporting/DLP can key off.
#   2. There's no dedicated round-trip for reactivation, so a mistake
#      requires the operator to remember which status the employee was in
#      previously (active / probation / on_leave / …). We now stash the
#      pre-deactivation status into audit metadata so reactivate can put
#      it back to the same state.
# ============================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def deactivate_employee(request, employee_id):
    """Mark an employee as offboarded. HR-admin only.

    Body:
      * ``reason`` (str, optional) — free text; goes into the audit log.

    Idempotent: calling on an already-offboarded employee returns success
    without mutating (200, `already_offboarded=True`). The pre-deactivate
    status is stashed in `before` so `reactivate_employee` can restore it.
    """
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR admin only.'},
                        status=status.HTTP_403_FORBIDDEN)
    emp, err = _company_employee_or_404(request, employee_id)
    if err:
        return err
    if emp.employment_status == 'offboarded':
        return Response({'status': 'success', 'data': {
            'id': emp.id, 'employment_status': emp.employment_status,
            'already_offboarded': True,
        }})
    d = request.data or {}
    reason = (d.get('reason') or '').strip()[:500]
    previous_status = emp.employment_status
    emp.employment_status = 'offboarded'
    emp.save(update_fields=['employment_status', 'updated_at'])
    _write_audit_log(
        request.user, request.user.company,
        'employee.deactivate', 'employee', emp.id,
        before={'employment_status': previous_status},
        after={'employment_status': 'offboarded', 'reason': reason},
    )
    return Response({'status': 'success', 'data': {
        'id': emp.id, 'employment_status': emp.employment_status,
        'previous_status': previous_status,
    }})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def reactivate_employee(request, employee_id):
    """Reverse an earlier deactivation. HR-admin only.

    Body:
      * ``target_status`` (str, optional) — override the reactivated status.
                            Defaults to 'active'. Accepts any valid choice
                            except 'offboarded' (that's what deactivate does).
      * ``reason``        (str, optional).

    Not-idempotent on the audit trail (each call writes a log entry) but
    idempotent on the model (calling on an already-active employee just
    logs and returns).
    """
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR admin only.'},
                        status=status.HTTP_403_FORBIDDEN)
    emp, err = _company_employee_or_404(request, employee_id)
    if err:
        return err
    d = request.data or {}
    target = (d.get('target_status') or 'active').strip()
    valid = {c[0] for c in Employee.EMPLOYMENT_STATUS_CHOICES} - {'offboarded'}
    if target not in valid:
        return Response({'status': 'error',
                         'message': f"target_status must be one of {sorted(valid)}"},
                        status=status.HTTP_400_BAD_REQUEST)
    reason = (d.get('reason') or '').strip()[:500]
    previous_status = emp.employment_status
    emp.employment_status = target
    emp.save(update_fields=['employment_status', 'updated_at'])
    _write_audit_log(
        request.user, request.user.company,
        'employee.reactivate', 'employee', emp.id,
        before={'employment_status': previous_status},
        after={'employment_status': target, 'reason': reason},
    )
    return Response({'status': 'success', 'data': {
        'id': emp.id, 'employment_status': emp.employment_status,
        'previous_status': previous_status,
    }})


# ============================================================================
# Audit log — HR-admin read-only view
# ============================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_hr_audit_log(request):
    """Recent HR audit events for the company. HR-admin only.

    Optional query params:
      ``?target_type=employee|compensation|review``
      ``?target_id=<pk>``  (scope to a single row)
      ``?limit=`` / ``?offset=`` (default 50/0, max 200)
    """
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR-admin access required'},
                        status=status.HTTP_403_FORBIDDEN)
    try:
        company = request.user.company
        qs = HRAuditLog.objects.filter(company=company).order_by('-created_at')
        if request.GET.get('target_type'):
            qs = qs.filter(target_type=request.GET['target_type'])
        if request.GET.get('target_id'):
            qs = qs.filter(target_id=request.GET['target_id'])
        try:
            limit = max(1, min(int(request.GET.get('limit') or 50), 200))
            offset = max(0, int(request.GET.get('offset') or 0))
        except ValueError:
            limit, offset = 50, 0
        total = qs.count()
        rows = []
        for log in qs.select_related('actor')[offset:offset + limit]:
            rows.append({
                'id': log.id,
                'action': log.action,
                'target_type': log.target_type,
                'target_id': log.target_id,
                'actor_id': log.actor_id,
                'actor_name': log.actor.full_name if log.actor_id else None,
                'diff': log.diff,
                'created_at': log.created_at.isoformat(),
            })
        return Response({'status': 'success', 'data': rows,
                         'pagination': {'total': total, 'limit': limit, 'offset': offset}})
    except Exception:
        logger.exception("list_hr_audit_log failed")
        return Response({'status': 'error', 'message': 'Failed to load audit log'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _serialize_compensation(c) -> dict:
    base = float(c.base_salary) if c.base_salary is not None else None
    bonus_pct = float(c.bonus_target_pct) if c.bonus_target_pct is not None else None
    equity = float(c.equity_grant_value) if c.equity_grant_value is not None else None
    # Target comp = base + (base * bonus%/100) + equity_grant_value. Missing
    # parts are treated as zero so a base-only comp row still surfaces a total.
    total = None
    if base is not None:
        total = base
        if bonus_pct is not None:
            total += base * (bonus_pct / 100.0)
        if equity is not None:
            total += equity
        total = round(total, 2)
    return {
        'id': c.id,
        'employee_id': c.employee_id,
        'effective_date': c.effective_date.isoformat() if c.effective_date else None,
        'base_salary': base,
        'currency': c.currency,
        'pay_frequency': c.pay_frequency,
        'bonus_target_pct': bonus_pct,
        'equity_grant_value': equity,
        'total_target_compensation': total,
        'grade': c.grade or '',
        'reason': c.reason,
        'notes': c.notes or '',
        'created_at': c.created_at.isoformat() if c.created_at else None,
    }


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_compensation_history(request, employee_id):
    """Compensation history for a single employee. HR-admins only — anyone
    else gets 403 even if they happen to be the same employee."""
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR-admin access required'},
                        status=status.HTTP_403_FORBIDDEN)
    emp, err = _company_employee_or_404(request, employee_id)
    if err:
        return err
    from hr_agent.models import Compensation
    rows = Compensation.objects.filter(employee=emp).order_by('-effective_date', '-id')
    return Response({'status': 'success', 'data': [_serialize_compensation(c) for c in rows]})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def create_compensation(request, employee_id):
    """Record a new compensation change (e.g. annual raise, promotion). The
    new row becomes the employee's "current" pay — older rows are kept."""
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR-admin access required'},
                        status=status.HTTP_403_FORBIDDEN)
    emp, err = _company_employee_or_404(request, employee_id)
    if err:
        return err
    from hr_agent.models import Compensation
    d = request.data or {}
    if 'base_salary' not in d or 'effective_date' not in d:
        return Response({'status': 'error', 'message': 'effective_date and base_salary are required'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        from decimal import Decimal
        base_salary = Decimal(str(d['base_salary']))
    except Exception:
        return Response({'status': 'error', 'message': 'base_salary must be numeric'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        eff = datetime.fromisoformat(d['effective_date']).date()
    except (TypeError, ValueError):
        return Response({'status': 'error', 'message': 'effective_date must be YYYY-MM-DD'},
                        status=status.HTTP_400_BAD_REQUEST)

    # Guard against out-of-order history — "current salary" queries rely on
    # ordering by effective_date desc, so a backdated row silently becomes
    # the new "current" if we allow it.
    latest = Compensation.objects.filter(employee=emp).order_by('-effective_date').first()
    if latest and eff < latest.effective_date:
        return Response({
            'status': 'error',
            'message': (
                f'effective_date {eff} is earlier than the most recent compensation '
                f'record ({latest.effective_date}). Backdating is not allowed. '
                f'If you need to correct a past record, delete the later entry first.'
            ),
        }, status=status.HTTP_400_BAD_REQUEST)

    user = _hr_get_or_create_user_for_company_user(request.user)
    c = Compensation.objects.create(
        employee=emp,
        effective_date=eff,
        base_salary=base_salary,
        currency=(d.get('currency') or 'USD').upper()[:3],
        pay_frequency=d.get('pay_frequency') or 'annual',
        bonus_target_pct=d.get('bonus_target_pct') or None,
        equity_grant_value=d.get('equity_grant_value') or None,
        grade=(d.get('grade') or '')[:40],
        reason=d.get('reason') or 'other',
        notes=(d.get('notes') or '')[:5000],
        recorded_by=user,
    )
    serialized = _serialize_compensation(c)
    _write_audit_log(request.user, request.user.company, 'compensation.create',
                     'compensation', c.id, created=serialized)
    return Response({'status': 'success', 'data': serialized},
                    status=status.HTTP_201_CREATED)


@api_view(['DELETE', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def delete_compensation(request, comp_id):
    """Remove a single compensation row (corrections / typos). HR-admin only."""
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR-admin access required'},
                        status=status.HTTP_403_FORBIDDEN)
    from hr_agent.models import Compensation
    comp_qs = Compensation.objects.filter(pk=comp_id, employee__company=request.user.company)
    comp_obj = comp_qs.first()
    if not comp_obj:
        return Response({'status': 'error', 'message': 'Compensation row not found'},
                        status=status.HTTP_404_NOT_FOUND)
    snap = _serialize_compensation(comp_obj)
    comp_obj.delete()
    _write_audit_log(request.user, request.user.company, 'compensation.delete',
                     'compensation', int(comp_id), deleted=snap)
    return Response({'status': 'success', 'data': {'deleted_id': int(comp_id)}})


# ============================================================================
# Performance reviews — cycles + per-employee reviews
# ============================================================================

def _serialize_review_cycle(c) -> dict:
    return {
        'id': c.id, 'name': c.name, 'description': c.description,
        'period_start': c.period_start.isoformat() if c.period_start else None,
        'period_end': c.period_end.isoformat() if c.period_end else None,
        'self_review_due': c.self_review_due.isoformat() if c.self_review_due else None,
        'manager_review_due': c.manager_review_due.isoformat() if c.manager_review_due else None,
        'calibration_due': c.calibration_due.isoformat() if c.calibration_due else None,
        'status': c.status,
        'review_count': getattr(c, '_review_count', None),
        'created_at': c.created_at.isoformat() if c.created_at else None,
    }


def _serialize_perf_review(r) -> dict:
    return {
        'id': r.id,
        'cycle_id': r.cycle_id,
        'cycle_name': r.cycle.name if r.cycle_id else None,
        'employee_id': r.employee_id,
        'employee_name': r.employee.full_name if r.employee_id else None,
        'reviewer_id': r.reviewer_id,
        'reviewer_name': r.reviewer.full_name if r.reviewer_id else None,
        'status': r.status,
        'self_summary': r.self_summary,
        'manager_summary': r.manager_summary,
        'strengths': r.strengths,
        'growth_areas': r.growth_areas,
        'goals': r.goals or [],
        'overall_rating': r.overall_rating,
        'self_submitted_at': r.self_submitted_at.isoformat() if r.self_submitted_at else None,
        'manager_submitted_at': r.manager_submitted_at.isoformat() if r.manager_submitted_at else None,
        'finalized_at': r.finalized_at.isoformat() if r.finalized_at else None,
        'visible_to_employee': r.visible_to_employee,
    }


def _parse_iso_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_review_cycles(request):
    from hr_agent.models import PerformanceReviewCycle
    company = request.user.company
    qs = (PerformanceReviewCycle.objects.filter(company=company)
          .annotate(_review_count=Count('reviews'))
          .order_by('-period_start', '-id'))
    return Response({'status': 'success',
                     'data': [_serialize_review_cycle(c) for c in qs]})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def create_review_cycle(request):
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR-admin role required'},
                        status=status.HTTP_403_FORBIDDEN)
    from hr_agent.models import PerformanceReviewCycle
    company = request.user.company
    d = request.data or {}
    name = (d.get('name') or '').strip()
    period_start = _parse_iso_date(d.get('period_start'))
    period_end = _parse_iso_date(d.get('period_end'))
    if not (name and period_start and period_end):
        return Response({'status': 'error',
                         'message': 'name, period_start, period_end are required (YYYY-MM-DD)'},
                        status=status.HTTP_400_BAD_REQUEST)
    if period_end < period_start:
        return Response({'status': 'error', 'message': 'period_end must be after period_start'},
                        status=status.HTTP_400_BAD_REQUEST)
    user = _hr_get_or_create_user_for_company_user(request.user)
    cycle = PerformanceReviewCycle.objects.create(
        company=company, name=name[:120],
        description=d.get('description') or '',
        period_start=period_start, period_end=period_end,
        self_review_due=_parse_iso_date(d.get('self_review_due')),
        manager_review_due=_parse_iso_date(d.get('manager_review_due')),
        calibration_due=_parse_iso_date(d.get('calibration_due')),
        status=d.get('status') if d.get('status') in
        ('draft', 'active', 'closed', 'cancelled') else 'draft',
        created_by=user,
    )
    _write_audit_log(request.user, company, 'review_cycle.create',
                     'PerformanceReviewCycle', cycle.id, before=None,
                     after={'name': cycle.name, 'status': cycle.status,
                            'period_start': cycle.period_start.isoformat(),
                            'period_end': cycle.period_end.isoformat()})
    return Response({'status': 'success', 'data': _serialize_review_cycle(cycle)},
                    status=status.HTTP_201_CREATED)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def activate_review_cycle(request, cycle_id):
    """Flip a draft cycle to active and generate one PerformanceReview row per
    active employee in the company. Idempotent — won't duplicate existing rows."""
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR-admin role required'},
                        status=status.HTTP_403_FORBIDDEN)
    from hr_agent.models import PerformanceReviewCycle, PerformanceReview
    company = request.user.company
    cycle = PerformanceReviewCycle.objects.filter(company=company, pk=cycle_id).first()
    if not cycle:
        return Response({'status': 'error', 'message': 'Cycle not found'},
                        status=status.HTTP_404_NOT_FOUND)

    existing_emp_ids = set(cycle.reviews.values_list('employee_id', flat=True))
    eligible = Employee.objects.filter(
        company=company, employment_status__in=['active', 'probation', 'on_leave', 'notice'],
    ).exclude(pk__in=existing_emp_ids)
    created = 0
    for emp in eligible.iterator(chunk_size=500):
        PerformanceReview.objects.create(
            cycle=cycle, employee=emp, reviewer=emp.manager,
            status='not_started',
        )
        created += 1
    if cycle.status != 'active':
        cycle.status = 'active'
        cycle.save(update_fields=['status', 'updated_at'])
    return Response({'status': 'success',
                     'data': {**_serialize_review_cycle(cycle), 'reviews_created': created}})


@api_view(['DELETE', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def delete_review_cycle(request, cycle_id):
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR-admin role required'},
                        status=status.HTTP_403_FORBIDDEN)
    from hr_agent.models import PerformanceReviewCycle
    company = request.user.company
    cycle = PerformanceReviewCycle.objects.filter(pk=cycle_id, company=company).first()
    if not cycle:
        return Response({'status': 'error', 'message': 'Cycle not found'},
                        status=status.HTTP_404_NOT_FOUND)
    snap = {'name': cycle.name, 'status': cycle.status,
            'period_start': cycle.period_start.isoformat(),
            'period_end': cycle.period_end.isoformat(),
            'review_count': cycle.reviews.count()}
    cycle.delete()
    _write_audit_log(request.user, company, 'review_cycle.delete',
                     'PerformanceReviewCycle', int(cycle_id),
                     before=snap, after=None)
    return Response({'status': 'success', 'data': {'deleted_id': int(cycle_id)}})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def close_review_cycle(request, cycle_id):
    """Flip an active cycle to `closed` so the cycle becomes read-only. Optionally
    releases every review to its employee (``release_reviews=true``) — otherwise
    ratings stay HR-only until someone flips ``visible_to_employee`` per row."""
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR-admin role required'},
                        status=status.HTTP_403_FORBIDDEN)
    from hr_agent.models import PerformanceReviewCycle, PerformanceReview
    company = request.user.company
    cycle = PerformanceReviewCycle.objects.filter(company=company, pk=cycle_id).first()
    if not cycle:
        return Response({'status': 'error', 'message': 'Cycle not found'},
                        status=status.HTTP_404_NOT_FOUND)
    if cycle.status == 'closed':
        return Response({'status': 'success',
                         'data': {**_serialize_review_cycle(cycle), 'released': 0}})

    before = {'status': cycle.status}
    cycle.status = 'closed'
    cycle.save(update_fields=['status', 'updated_at'])

    released = 0
    if str(request.data.get('release_reviews', '')).lower() in ('1', 'true', 'yes'):
        released = PerformanceReview.objects.filter(
            cycle=cycle, visible_to_employee=False,
        ).update(visible_to_employee=True, status='closed')

    _write_audit_log(request.user, company, 'review_cycle_closed',
                     'PerformanceReviewCycle', cycle.pk, before,
                     {'status': 'closed', 'released': released,
                      'reason': (request.data.get('reason') or '')[:500]})

    return Response({'status': 'success',
                     'data': {**_serialize_review_cycle(cycle), 'released': released}})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def reopen_review_cycle(request, cycle_id):
    """Flip a closed cycle back to `active` so late submissions can land. Does
    NOT re-hide already-released reviews — that would surprise employees who've
    already seen their rating."""
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR-admin role required'},
                        status=status.HTTP_403_FORBIDDEN)
    from hr_agent.models import PerformanceReviewCycle
    company = request.user.company
    cycle = PerformanceReviewCycle.objects.filter(company=company, pk=cycle_id).first()
    if not cycle:
        return Response({'status': 'error', 'message': 'Cycle not found'},
                        status=status.HTTP_404_NOT_FOUND)
    if cycle.status not in ('closed', 'cancelled'):
        return Response({'status': 'error',
                         'message': f"Cannot reopen a cycle in status '{cycle.status}'."},
                        status=status.HTTP_400_BAD_REQUEST)

    before = {'status': cycle.status}
    cycle.status = 'active'
    cycle.save(update_fields=['status', 'updated_at'])
    _write_audit_log(request.user, company, 'review_cycle_reopened',
                     'PerformanceReviewCycle', cycle.pk, before,
                     {'status': 'active',
                      'reason': (request.data.get('reason') or '')[:500]})

    return Response({'status': 'success', 'data': _serialize_review_cycle(cycle)})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_employee_reviews(request, employee_id):
    """Performance review history for one employee. The reviewee, their manager
    chain, and HR-admins see everything; everyone else only sees ``visible_to_employee``."""
    from hr_agent.models import PerformanceReview
    emp, err = _company_employee_or_404(request, employee_id)
    if err:
        return err
    qs = PerformanceReview.objects.filter(employee=emp).select_related('cycle', 'reviewer')
    if not _is_hr_admin(request.user):
        # Self-view only sees released reviews.
        caller_user_id = getattr(request.user, 'user_id', None)
        if str(caller_user_id) != str(emp.user_id):
            qs = qs.filter(visible_to_employee=True)
    return Response({'status': 'success',
                     'data': [_serialize_perf_review(r) for r in qs.order_by('-cycle__period_start')]})


@api_view(['PATCH', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def update_perf_review(request, review_id):
    """Update one review. Self-review fields editable by the reviewee until
    submitted; manager-review fields by the reviewer or HR-admin."""
    from hr_agent.models import PerformanceReview
    company = request.user.company
    r = (PerformanceReview.objects.select_related('cycle', 'employee', 'reviewer')
         .filter(pk=review_id, cycle__company=company).first())
    if not r:
        return Response({'status': 'error', 'message': 'Review not found'},
                        status=status.HTTP_404_NOT_FOUND)

    caller_user_id = getattr(request.user, 'user_id', None)
    is_admin = _is_hr_admin(request.user)
    is_reviewee = caller_user_id and str(caller_user_id) == str(r.employee.user_id)
    is_reviewer = caller_user_id and r.reviewer_id and str(caller_user_id) == str(r.reviewer.user_id)
    if not (is_admin or is_reviewee or is_reviewer):
        return Response({'status': 'error', 'message': 'Not authorized to edit this review'},
                        status=status.HTTP_403_FORBIDDEN)

    d = request.data or {}
    fields = []
    before_review = _serialize_perf_review(r)

    # Deadline gates — non-admin writers can't edit a self-review past
    # `cycle.self_review_due`, or a manager-review past `cycle.manager_review_due`.
    # HR-admins can always back-fill (they often need to correct late submissions).
    today = timezone.now().date()
    cycle = r.cycle if r.cycle_id else None
    self_keys = {'self_summary', 'submit_self'}
    manager_keys = {'manager_summary', 'strengths', 'growth_areas', 'goals',
                    'overall_rating', 'submit_manager'}
    if not is_admin:
        if cycle and cycle.self_review_due and today > cycle.self_review_due \
                and any(k in d for k in self_keys):
            return Response({
                'status': 'error',
                'message': (
                    f"Self-review deadline ({cycle.self_review_due.isoformat()}) "
                    f"has passed. Ask HR to reopen the cycle if you need to submit late."
                ),
            }, status=status.HTTP_400_BAD_REQUEST)
        if cycle and cycle.manager_review_due and today > cycle.manager_review_due \
                and any(k in d for k in manager_keys):
            return Response({
                'status': 'error',
                'message': (
                    f"Manager-review deadline ({cycle.manager_review_due.isoformat()}) "
                    f"has passed. Ask HR to reopen the cycle if you need to submit late."
                ),
            }, status=status.HTTP_400_BAD_REQUEST)

    # Self-review fields
    if 'self_summary' in d and (is_reviewee or is_admin):
        if r.self_submitted_at and not is_admin:
            return Response({'status': 'error', 'message': 'Self-review already submitted'},
                            status=status.HTTP_400_BAD_REQUEST)
        r.self_summary = d['self_summary'] or ''
        fields.append('self_summary')
    if 'submit_self' in d and (is_reviewee or is_admin) and d['submit_self']:
        r.self_submitted_at = timezone.now()
        fields.append('self_submitted_at')
        if r.status in ('not_started', 'self_in_progress'):
            r.status = 'manager_in_progress'
            fields.append('status')

    # Manager fields
    if 'manager_summary' in d and (is_reviewer or is_admin):
        r.manager_summary = d['manager_summary'] or ''
        fields.append('manager_summary')
    if 'strengths' in d and (is_reviewer or is_admin):
        r.strengths = d['strengths'] or ''
        fields.append('strengths')
    if 'growth_areas' in d and (is_reviewer or is_admin):
        r.growth_areas = d['growth_areas'] or ''
        fields.append('growth_areas')
    if 'goals' in d and (is_reviewer or is_admin) and isinstance(d['goals'], list):
        r.goals = d['goals']
        fields.append('goals')
    if 'overall_rating' in d and (is_reviewer or is_admin):
        rating = d['overall_rating']
        if rating not in (None, '', 1, 2, 3, 4, 5, '1', '2', '3', '4', '5'):
            return Response({'status': 'error', 'message': 'overall_rating must be 1..5'},
                            status=status.HTTP_400_BAD_REQUEST)
        r.overall_rating = int(rating) if rating not in (None, '') else None
        fields.append('overall_rating')
    if 'submit_manager' in d and (is_reviewer or is_admin) and d['submit_manager']:
        r.manager_submitted_at = timezone.now()
        fields.append('manager_submitted_at')
        if r.status in ('not_started', 'self_in_progress', 'manager_in_progress'):
            r.status = 'awaiting_calibration'
            fields.append('status')

    # Final release / retract
    if 'release' in d and is_admin and d['release']:
        r.visible_to_employee = True
        r.finalized_at = timezone.now()
        r.status = 'closed'
        fields.extend(['visible_to_employee', 'finalized_at', 'status'])
    elif 'unrelease' in d and is_admin and d['unrelease']:
        r.visible_to_employee = False
        r.status = 'awaiting_calibration'
        fields.extend(['visible_to_employee', 'status'])

    if 'status' in d and is_admin and d['status'] in dict(r.STATUS_CHOICES):
        r.status = d['status']
        if 'status' not in fields:
            fields.append('status')

    if fields:
        fields.append('updated_at')
        r.save(update_fields=fields)
        _write_audit_log(request.user, company, 'review.update', 'review', r.id,
                         before=before_review, after=_serialize_perf_review(r))
    return Response({'status': 'success', 'data': _serialize_perf_review(r)})


# ============================================================================
# Built-in workflow templates — clone-to-instantiate
# ============================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_workflow_templates(request):
    """Lists the canonical workflow templates (onboarding, offboarding, 30-day
    check-in) so HR can clone one rather than building a workflow from scratch."""
    from hr_agent.workflow_templates import list_template_summaries
    return Response({'status': 'success', 'data': list_template_summaries()})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def create_workflow_from_template(request):
    """Clone a built-in template into a new HRWorkflow row. HR-admin only.
    Body: ``{template_key, name?}``."""
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR-admin access required'},
                        status=status.HTTP_403_FORBIDDEN)
    from hr_agent.workflow_templates import get_template
    d = request.data or {}
    key = (d.get('template_key') or '').strip()
    spec = get_template(key)
    if not spec:
        return Response({'status': 'error', 'message': f"Unknown template_key '{key}'"},
                        status=status.HTTP_400_BAD_REQUEST)
    name = (d.get('name') or spec['name']).strip()[:200]
    w = HRWorkflow.objects.create(
        company=request.user.company,
        name=name,
        description=spec.get('description', ''),
        trigger_conditions=spec.get('trigger_conditions') or {},
        steps=spec.get('steps') or [],
        requires_approval=bool(spec.get('requires_approval')),
        timeout_seconds=int(spec.get('timeout_seconds') or 0),
        is_active=True,
    )
    _write_audit_log(request.user, request.user.company, 'workflow.from_template',
                     'workflow', w.id, created={'template_key': key, 'name': w.name})
    return Response({'status': 'success', 'data': {'id': w.id, 'name': w.name}},
                    status=status.HTTP_201_CREATED)


# ============================================================================
# Performance goals / OKRs
# ============================================================================

def _serialize_goal(g: PerformanceGoal) -> dict:
    return {
        'id': g.id,
        'employee_id': g.employee_id,
        'cycle_id': g.cycle_id,
        'parent_id': g.parent_id,
        'title': g.title,
        'description': g.description,
        'success_criteria': g.success_criteria,
        'status': g.status,
        'weight_pct': g.weight_pct,
        'target_value': g.target_value,
        'current_value': g.current_value,
        'progress_pct': g.progress_pct,
        'due_date': g.due_date.isoformat() if g.due_date else None,
        'assigned_by_id': g.assigned_by_id,
        'assigned_by_name': g.assigned_by.full_name if g.assigned_by_id else None,
        'closed_at': g.closed_at.isoformat() if g.closed_at else None,
        'created_at': g.created_at.isoformat() if g.created_at else None,
        'updated_at': g.updated_at.isoformat() if g.updated_at else None,
    }


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_employee_goals(request, employee_id):
    """List goals for an employee. Visible to the employee themselves, their
    manager, and HR-admins. Optional ``?cycle_id=`` filter."""
    emp, err = _company_employee_or_404(request, employee_id)
    if err:
        return err
    caller_user_id = getattr(request.user, 'user_id', None)
    is_self = caller_user_id and str(caller_user_id) == str(emp.user_id)
    is_admin = _is_hr_admin(request.user)
    is_manager = False
    if not (is_self or is_admin):
        caller_emp = (Employee.objects.filter(company=request.user.company, company_user=request.user).first()
                      or Employee.objects.filter(company=request.user.company, work_email__iexact=request.user.email).first())
        is_manager = bool(caller_emp and emp.manager_id == caller_emp.id)
    if not (is_self or is_admin or is_manager):
        return Response({'status': 'error', 'message': 'Not authorized to view this employee\'s goals'},
                        status=status.HTTP_403_FORBIDDEN)
    qs = PerformanceGoal.objects.filter(employee=emp)
    cycle_id = request.GET.get('cycle_id')
    if cycle_id:
        qs = qs.filter(cycle_id=cycle_id)
    return Response({'status': 'success', 'data': [_serialize_goal(g) for g in qs]})


# ============================================================================
# Leave balances — dedicated read + admin-adjust
#
# `get_employee_detail` already returns balances as part of its bundle, but
# there was no lightweight standalone read (annoying for widgets that only
# want balances) and — worse — no way for HR to hand-correct a wrong accrual
# without direct DB access. These two endpoints fix both.
# ============================================================================

def _serialize_leave_balance(row) -> dict:
    return {
        'id': row.id,
        'leave_type': row.leave_type,
        'accrued_days': float(row.accrued_days or 0),
        'used_days': float(row.used_days or 0),
        'carried_over_days': float(row.carried_over_days or 0),
        'remaining': row.remaining,
        'period_start': row.period_start.isoformat() if row.period_start else None,
        'period_end': row.period_end.isoformat() if row.period_end else None,
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
    }


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_leave_balances(request, employee_id):
    """Dedicated balances read for one employee. Employees can read their
    own; managers can read their reports'; HR-admins can read anyone in
    the company. Order is unspecified — clients that care should sort by
    `leave_type` themselves."""
    emp, err = _company_employee_or_404(request, employee_id)
    if err:
        return err
    is_admin = _is_hr_admin(request.user)
    caller_emp = (Employee.objects.filter(company=request.user.company, company_user=request.user).first()
                  or Employee.objects.filter(company=request.user.company, work_email__iexact=request.user.email).first())
    if not is_admin:
        # self or their reports only
        is_self = caller_emp and caller_emp.id == emp.id
        is_report = caller_emp and emp.manager_id == caller_emp.id
        if not (is_self or is_report):
            return Response({'status': 'error', 'message': 'Not authorized.'},
                            status=status.HTTP_403_FORBIDDEN)
    rows = list(emp.leave_balances.all())
    return Response({'status': 'success', 'data': [_serialize_leave_balance(r) for r in rows]})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def adjust_leave_balance(request, employee_id):
    """HR-admin only. Adjust an employee's leave balance for a specific
    leave_type. Use the ``delta_*`` deltas to bump values relatively (the
    typical case — "add 2 vacation days"), or ``set_*`` to hard-set an
    absolute value (rare — post-migration correction).

    Body:
      * ``leave_type``  (str, required)     — vacation / sick / parental / etc.
      * ``delta_accrued_days``    (float)   — add to accrued (can be negative)
      * ``delta_used_days``       (float)   — add to used (can be negative)
      * ``delta_carried_over_days`` (float)
      * ``set_accrued_days``      (float)   — hard set; ignores delta on this field
      * ``set_used_days``         (float)
      * ``set_carried_over_days`` (float)
      * ``reason``      (str, required)     — free text explaining the change,
                                              written to the audit log.

    Creates the row if it doesn't exist yet (with period_start=None so it
    matches the model's `unique_together`).
    """
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR admin only.'},
                        status=status.HTTP_403_FORBIDDEN)
    emp, err = _company_employee_or_404(request, employee_id)
    if err:
        return err
    d = request.data or {}
    leave_type = (d.get('leave_type') or '').strip()
    valid_types = {c[0] for c in LeaveBalance.LEAVE_TYPE_CHOICES}
    if leave_type not in valid_types:
        return Response({'status': 'error',
                         'message': f"leave_type must be one of {sorted(valid_types)}"},
                        status=status.HTTP_400_BAD_REQUEST)
    reason = (d.get('reason') or '').strip()
    if not reason:
        return Response({'status': 'error',
                         'message': 'reason is required — it goes to the audit log.'},
                        status=status.HTTP_400_BAD_REQUEST)

    # Look up (or create) the row. We look at the current period-open row
    # (`period_start=None` is the "always-on" bucket, which is how balances
    # start out before an accrual policy tags them).
    row = emp.leave_balances.filter(leave_type=leave_type).order_by('-period_start').first()
    created = False
    if row is None:
        row = LeaveBalance.objects.create(employee=emp, leave_type=leave_type)
        created = True

    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    before = {
        'accrued_days': float(row.accrued_days or 0),
        'used_days': float(row.used_days or 0),
        'carried_over_days': float(row.carried_over_days or 0),
    }

    for field, set_key, delta_key in (
        ('accrued_days',      'set_accrued_days',      'delta_accrued_days'),
        ('used_days',         'set_used_days',         'delta_used_days'),
        ('carried_over_days', 'set_carried_over_days', 'delta_carried_over_days'),
    ):
        if set_key in d and d[set_key] is not None:
            v = _num(d[set_key])
            if v is not None:
                setattr(row, field, max(0.0, v))  # never negative
        elif delta_key in d and d[delta_key] is not None:
            v = _num(d[delta_key])
            if v is not None:
                setattr(row, field, max(0.0, float(getattr(row, field) or 0) + v))

    row.save()
    after = {
        'accrued_days': float(row.accrued_days or 0),
        'used_days': float(row.used_days or 0),
        'carried_over_days': float(row.carried_over_days or 0),
    }
    # Audit log with the diff. Uses the same helper the rest of the HR
    # code uses so the log shape is consistent.
    _write_audit_log(
        request.user, request.user.company,
        'leave_balance.adjust', 'leave_balance', row.id,
        before=before, after={**after, 'reason': reason, 'leave_type': leave_type, 'created': created},
    )
    return Response({'status': 'success', 'data': _serialize_leave_balance(row)})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def create_employee_goal(request, employee_id):
    """Create a goal for an employee. Manager or HR-admin only."""
    emp, err = _company_employee_or_404(request, employee_id)
    if err:
        return err
    is_admin = _is_hr_admin(request.user)
    caller_emp = (Employee.objects.filter(company=request.user.company, company_user=request.user).first()
                  or Employee.objects.filter(company=request.user.company, work_email__iexact=request.user.email).first())
    is_manager = bool(caller_emp and emp.manager_id == caller_emp.id)
    if not (is_admin or is_manager):
        return Response({'status': 'error', 'message': 'Only the manager or HR-admin can set goals'},
                        status=status.HTTP_403_FORBIDDEN)
    d = request.data or {}
    title = (d.get('title') or '').strip()
    if not title:
        return Response({'status': 'error', 'message': 'title is required'},
                        status=status.HTTP_400_BAD_REQUEST)
    due_date = None
    if d.get('due_date'):
        try:
            due_date = datetime.fromisoformat(d['due_date']).date()
        except (TypeError, ValueError):
            return Response({'status': 'error', 'message': 'due_date must be YYYY-MM-DD'},
                            status=status.HTTP_400_BAD_REQUEST)
    cycle_id = d.get('cycle_id')
    if cycle_id and not PerformanceReviewCycle.objects.filter(
            company=request.user.company, pk=cycle_id).exists():
        return Response({'status': 'error', 'message': 'cycle_id not found for this company'},
                        status=status.HTTP_400_BAD_REQUEST)
    parent_id = d.get('parent_id')
    if parent_id and not PerformanceGoal.objects.filter(
            employee__company=request.user.company, pk=parent_id).exists():
        return Response({'status': 'error', 'message': 'parent_id not found'},
                        status=status.HTTP_400_BAD_REQUEST)
    new_weight = max(0, min(100, int(d.get('weight_pct') or 0)))
    # Sum-check cycle weights so they can't add up past 100%. Only enforced
    # when a cycle is attached — goals outside a cycle don't roll up.
    ok, err, _cur = _validate_goal_weight_sum(emp, cycle_id or None, new_weight)
    if not ok:
        return Response({'status': 'error', 'message': err},
                        status=status.HTTP_400_BAD_REQUEST)
    g = PerformanceGoal.objects.create(
        employee=emp,
        cycle_id=cycle_id or None,
        parent_id=parent_id or None,
        title=title[:240],
        description=(d.get('description') or '')[:5000],
        success_criteria=(d.get('success_criteria') or '')[:5000],
        status=d.get('status') or 'open',
        weight_pct=new_weight,
        target_value=(d.get('target_value') or '')[:80],
        current_value=(d.get('current_value') or '')[:80],
        progress_pct=max(0, min(100, int(d.get('progress_pct') or 0))),
        due_date=due_date,
        assigned_by=caller_emp,
    )
    _write_audit_log(request.user, request.user.company, 'goal.create',
                     'goal', g.id, created=_serialize_goal(g))
    return Response({'status': 'success', 'data': _serialize_goal(g)},
                    status=status.HTTP_201_CREATED)


@api_view(['POST', 'PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def update_employee_goal(request, goal_id):
    """Update a goal. Employee can update progress/status on their own goals;
    manager/HR can edit any field."""
    g = PerformanceGoal.objects.filter(
        employee__company=request.user.company, pk=goal_id).select_related('employee').first()
    if not g:
        return Response({'status': 'error', 'message': 'Goal not found'},
                        status=status.HTTP_404_NOT_FOUND)
    is_admin = _is_hr_admin(request.user)
    caller_user_id = getattr(request.user, 'user_id', None)
    is_self = caller_user_id and str(caller_user_id) == str(g.employee.user_id)
    caller_emp = (Employee.objects.filter(company=request.user.company, company_user=request.user).first()
                  or Employee.objects.filter(company=request.user.company, work_email__iexact=request.user.email).first())
    is_manager = bool(caller_emp and g.employee.manager_id == caller_emp.id)
    if not (is_admin or is_self or is_manager):
        return Response({'status': 'error', 'message': 'Not authorized to update this goal'},
                        status=status.HTTP_403_FORBIDDEN)

    before = _serialize_goal(g)
    d = request.data or {}
    fields = []
    # Self can only update progress fields; manager/admin can edit anything.
    self_only_keys = {'progress_pct', 'current_value', 'status'}
    for k in list(d.keys()):
        if not (is_admin or is_manager) and k not in self_only_keys:
            continue
        if k == 'title' and d[k]:
            g.title = str(d[k])[:240]; fields.append('title')
        elif k == 'description':
            g.description = (d[k] or '')[:5000]; fields.append('description')
        elif k == 'success_criteria':
            g.success_criteria = (d[k] or '')[:5000]; fields.append('success_criteria')
        elif k == 'status' and d[k]:
            g.status = str(d[k])
            fields.append('status')
            if d[k] in ('met', 'missed', 'dropped', 'partially_met'):
                g.closed_at = timezone.now()
                fields.append('closed_at')
        elif k == 'weight_pct':
            try:
                proposed = max(0, min(100, int(d[k] or 0)))
            except (TypeError, ValueError):
                proposed = None
            if proposed is not None:
                ok, err, _cur = _validate_goal_weight_sum(
                    g.employee, g.cycle_id, proposed, exclude_goal_id=g.id,
                )
                if not ok:
                    return Response({'status': 'error', 'message': err},
                                    status=status.HTTP_400_BAD_REQUEST)
                g.weight_pct = proposed
                fields.append('weight_pct')
        elif k == 'progress_pct':
            try:
                g.progress_pct = max(0, min(100, int(d[k] or 0))); fields.append('progress_pct')
            except (TypeError, ValueError):
                pass
        elif k == 'target_value':
            g.target_value = (d[k] or '')[:80]; fields.append('target_value')
        elif k == 'current_value':
            g.current_value = (d[k] or '')[:80]; fields.append('current_value')
        elif k == 'due_date':
            if d[k] in (None, ''):
                g.due_date = None; fields.append('due_date')
            else:
                try:
                    g.due_date = datetime.fromisoformat(d[k]).date(); fields.append('due_date')
                except (TypeError, ValueError):
                    return Response({'status': 'error', 'message': 'due_date must be YYYY-MM-DD'},
                                    status=status.HTTP_400_BAD_REQUEST)
        elif k == 'cycle_id':
            if d[k] in (None, ''):
                g.cycle_id = None; fields.append('cycle_id')
            elif PerformanceReviewCycle.objects.filter(
                    company=request.user.company, pk=d[k]).exists():
                g.cycle_id = d[k]; fields.append('cycle_id')
    if fields:
        fields.append('updated_at')
        g.save(update_fields=fields)
        _write_audit_log(request.user, request.user.company, 'goal.update',
                         'goal', g.id, before=before, after=_serialize_goal(g))
    return Response({'status': 'success', 'data': _serialize_goal(g)})


@api_view(['POST', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def delete_employee_goal(request, goal_id):
    """Delete a goal. Manager or HR-admin only."""
    g = PerformanceGoal.objects.filter(
        employee__company=request.user.company, pk=goal_id).select_related('employee').first()
    if not g:
        return Response({'status': 'error', 'message': 'Goal not found'},
                        status=status.HTTP_404_NOT_FOUND)
    is_admin = _is_hr_admin(request.user)
    caller_emp = (Employee.objects.filter(company=request.user.company, company_user=request.user).first()
                  or Employee.objects.filter(company=request.user.company, work_email__iexact=request.user.email).first())
    is_manager = bool(caller_emp and g.employee.manager_id == caller_emp.id)
    if not (is_admin or is_manager):
        return Response({'status': 'error', 'message': 'Only the manager or HR-admin can delete goals'},
                        status=status.HTTP_403_FORBIDDEN)
    snapshot = _serialize_goal(g)
    g.delete()
    _write_audit_log(request.user, request.user.company, 'goal.delete',
                     'goal', goal_id, deleted=snapshot)
    return Response({'status': 'success', 'data': {'id': goal_id, 'deleted': True}})


# ============================================================================
# Manager portal — "my team" rollup
# ============================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def manager_team_summary(request):
    """Return the calling manager's direct reports with per-employee summary
    (leave balances, pending requests, upcoming meetings, open goals).

    HR-admins can pass ``?manager_id=`` to view any manager's team. Anyone else
    only ever sees their own team and only if they actually manage someone.
    """
    company = request.user.company
    is_admin = _is_hr_admin(request.user)
    if is_admin and request.GET.get('manager_id'):
        manager = Employee.objects.filter(company=company, pk=request.GET['manager_id']).first()
    else:
        manager = (Employee.objects.filter(company=company, company_user=request.user).first()
                   or Employee.objects.filter(company=company, work_email__iexact=request.user.email).first())
    if not manager:
        return Response({'status': 'error', 'message': 'No employee record found for the caller'},
                        status=status.HTTP_404_NOT_FOUND)

    reports = Employee.objects.filter(company=company, manager=manager)
    now = timezone.now()
    today = now.date()
    report_ids = list(reports.values_list('id', flat=True))

    # Bulk pulls — one query per dataset, then map by employee_id.
    pending_leaves = {}
    for lr in LeaveRequest.objects.filter(employee_id__in=report_ids, status='pending'):
        pending_leaves.setdefault(lr.employee_id, []).append({
            'id': lr.id, 'leave_type': lr.leave_type,
            'start_date': lr.start_date.isoformat() if lr.start_date else None,
            'end_date': lr.end_date.isoformat() if lr.end_date else None,
            'days_requested': float(lr.days_requested or 0),
        })
    balances_by_emp = {}
    for b in LeaveBalance.objects.filter(employee_id__in=report_ids):
        balances_by_emp.setdefault(b.employee_id, []).append({
            'leave_type': b.leave_type, 'remaining': float(b.remaining),
        })
    upcoming_meetings = {}
    for m in HRMeeting.objects.filter(
            company=company, status__in=['scheduled', 'rescheduled'],
            scheduled_at__gte=now, scheduled_at__lte=now + timedelta(days=14),
            participants__id__in=report_ids).distinct():
        for p in m.participants.filter(id__in=report_ids):
            upcoming_meetings.setdefault(p.id, []).append({
                'id': m.id, 'title': m.title,
                'scheduled_at': m.scheduled_at.isoformat() if m.scheduled_at else None,
                'meeting_type': m.meeting_type,
            })
    open_goals = {}
    for g in PerformanceGoal.objects.filter(
            employee_id__in=report_ids, status__in=['open', 'in_progress']):
        open_goals.setdefault(g.employee_id, []).append({
            'id': g.id, 'title': g.title, 'status': g.status,
            'progress_pct': g.progress_pct,
            'due_date': g.due_date.isoformat() if g.due_date else None,
        })

    team = []
    for r in reports:
        team.append({
            'id': r.id,
            'full_name': r.full_name,
            'job_title': r.job_title,
            'work_email': r.work_email,
            'employment_status': r.employment_status,
            'probation_ending_in_days': (
                (r.probation_end_date - today).days
                if r.probation_end_date and r.probation_end_date >= today else None
            ),
            'leave_balances': balances_by_emp.get(r.id, []),
            'pending_leave_requests': pending_leaves.get(r.id, []),
            'upcoming_meetings': upcoming_meetings.get(r.id, []),
            'open_goals': open_goals.get(r.id, []),
        })
    return Response({'status': 'success', 'data': {
        'manager': {'id': manager.id, 'full_name': manager.full_name},
        'team': team,
        'team_size': len(team),
    }})


# ============================================================================
# Org chart — department tree + employee leaves
# ============================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def org_chart(request):
    """Returns a department tree with employees as leaves.

    Shape:
      [{ id, name, type: 'department', head: {id, full_name} | None,
         employees: [{id, full_name, job_title, manager_id}],
         children: [...] }, ...]

    Departments with no parent become roots. Employees with no department are
    bucketed under a synthetic "(Unassigned)" root so they don't disappear.
    """
    company = request.user.company
    departments = list(Department.objects.filter(company=company, is_active=True)
                       .select_related('head'))
    employees = list(Employee.objects.filter(
        company=company, employment_status__in=['active', 'on_leave', 'probation']
    ).only('id', 'full_name', 'job_title', 'manager_id', 'department', 'department_obj_id'))

    # Group employees by department FK (or string fallback for legacy rows).
    emp_by_dept_id: dict[int, list[dict]] = {}
    unassigned: list[dict] = []
    dept_name_to_id = {d.name.lower(): d.id for d in departments}
    for e in employees:
        wire = {'id': e.id, 'full_name': e.full_name,
                'job_title': e.job_title, 'manager_id': e.manager_id}
        if e.department_obj_id:
            emp_by_dept_id.setdefault(e.department_obj_id, []).append(wire)
        elif e.department and e.department.lower() in dept_name_to_id:
            emp_by_dept_id.setdefault(dept_name_to_id[e.department.lower()], []).append(wire)
        else:
            unassigned.append(wire)

    # Build parent -> children map for departments.
    children_of: dict[int | None, list] = {}
    for d in departments:
        children_of.setdefault(d.parent_id, []).append(d)

    def _build(dept):
        return {
            'id': dept.id, 'name': dept.name, 'type': 'department',
            'head': ({'id': dept.head.id, 'full_name': dept.head.full_name}
                     if dept.head_id else None),
            'employees': emp_by_dept_id.get(dept.id, []),
            'children': [_build(child) for child in children_of.get(dept.id, [])],
        }

    roots = [_build(d) for d in children_of.get(None, [])]
    if unassigned:
        roots.append({
            'id': None, 'name': '(Unassigned)', 'type': 'department',
            'head': None, 'employees': unassigned, 'children': [],
        })
    return Response({'status': 'success', 'data': roots})


# ============================================================================
# Document version chain
# ============================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_hr_document_versions(request, document_id):
    """Return the full version chain for a document. Walks up via
    ``parent_document`` then down via ``superseded_by`` so any node in the
    chain returns the same ordered list. The current (non-superseded) row is
    flagged ``is_current=True``."""
    company = request.user.company
    anchor = HRDocument.objects.filter(company=company, pk=document_id).first()
    if not anchor:
        return Response({'status': 'error', 'message': 'Document not found'},
                        status=status.HTTP_404_NOT_FOUND)
    # Walk to the root: the oldest ancestor with no parent.
    root = anchor
    seen_up: set = set()
    while root.parent_document_id and root.parent_document_id not in seen_up:
        seen_up.add(root.id)
        parent = HRDocument.objects.filter(company=company, pk=root.parent_document_id).first()
        if not parent:
            break
        root = parent
    # Walk forward via superseded_by to collect the chain in order.
    chain = [root]
    seen_down = {root.id}
    cur = root
    while cur.superseded_by_id and cur.superseded_by_id not in seen_down:
        nxt = HRDocument.objects.filter(company=company, pk=cur.superseded_by_id).first()
        if not nxt:
            break
        chain.append(nxt)
        seen_down.add(nxt.id)
        cur = nxt
    rows = [{
        'id': d.id, 'title': d.title, 'version': d.version,
        'document_type': d.document_type, 'confidentiality': d.confidentiality,
        'file_format': d.file_format, 'file_size': d.file_size,
        'processing_status': d.processing_status,
        'parent_document_id': d.parent_document_id,
        'superseded_by_id': d.superseded_by_id,
        'is_current': d.superseded_by_id is None,
        'created_at': d.created_at.isoformat() if d.created_at else None,
    } for d in chain]
    return Response({'status': 'success', 'data': rows})


# ============================================================================
# GDPR — anonymize employee + document access log
# ============================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def anonymize_employee(request, employee_id):
    """GDPR "right to delete" — scrub PII on an employee row in place rather
    than hard-deleting it. Audit trail references stay intact because the row
    still exists; only personal fields are zeroed.

    Scrubs: full_name, work_email, personal_email, phone, date_of_birth,
    custom_fields, plus all personal documents (title, description, content,
    extracted_fields, on-disk file).

    Preserves: id (audit FK target), company, employment_status, employment_type,
    start_date, end_date, manager link, leave history (aggregate counts),
    performance reviews (free-text fields are also scrubbed), goals.

    HR-admin only. Irreversible.
    """
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR-admin access required'},
                        status=status.HTTP_403_FORBIDDEN)
    emp, err = _company_employee_or_404(request, employee_id)
    if err:
        return err
    if emp.anonymized_at:
        return Response({'status': 'error', 'message': 'Employee is already anonymized'},
                        status=status.HTTP_400_BAD_REQUEST)

    before_snapshot = {
        'full_name': emp.full_name, 'work_email': emp.work_email,
        'phone': emp.phone or '', 'date_of_birth': emp.date_of_birth.isoformat() if emp.date_of_birth else None,
    }

    # Scrub PII fields on the employee row.
    redact_tag = f'[redacted #{emp.id}]'
    emp.full_name = redact_tag
    # work_email is unique_together with company — keep it unique via a tombstone.
    emp.work_email = f'redacted-{emp.id}@redacted.invalid'
    emp.personal_email = ''
    emp.phone = ''
    emp.date_of_birth = None
    emp.work_anniversary_month_day = ''
    emp.custom_fields = {}
    emp.anonymized_at = timezone.now()
    emp.save(update_fields=[
        'full_name', 'work_email', 'personal_email', 'phone',
        'date_of_birth', 'work_anniversary_month_day', 'custom_fields',
        'anonymized_at', 'updated_at',
    ])

    # Scrub personal documents — both DB row and on-disk file.
    personal_docs = HRDocument.objects.filter(company=request.user.company, employee=emp)
    docs_scrubbed = 0
    for d in personal_docs:
        try:
            if d.file_path:
                from django.conf import settings as _s
                full = Path(_s.MEDIA_ROOT) / d.file_path
                if full.exists():
                    full.unlink()
        except Exception:
            logger.exception("anonymize_employee: file unlink failed for doc %s", d.id)
        d.title = f'[redacted personal doc #{d.id}]'
        d.description = ''
        d.document_content = ''
        d.extracted_fields = {}
        d.file_path = ''
        d.save(update_fields=['title', 'description', 'document_content',
                              'extracted_fields', 'file_path', 'updated_at'])
        d.chunks.all().delete()
        docs_scrubbed += 1

    # Scrub free-text fields on performance reviews (manager_summary etc. could
    # contain personal references). Ratings + status stay so aggregate analytics
    # remain useful.
    from hr_agent.models import PerformanceReview
    PerformanceReview.objects.filter(employee=emp).update(
        self_summary='[redacted]', manager_summary='[redacted]',
        strengths='[redacted]', growth_areas='[redacted]', goals=[],
    )

    # Scrub free-text reason on leave requests (keep dates + status for accrual maths).
    LeaveRequest.objects.filter(employee=emp).update(reason='[redacted]', approval_note='[redacted]')

    _write_audit_log(request.user, request.user.company, 'employee.anonymize',
                     'employee', emp.id, before=before_snapshot,
                     after={'anonymized_at': emp.anonymized_at.isoformat(),
                            'documents_scrubbed': docs_scrubbed})
    return Response({'status': 'success', 'data': {
        'id': emp.id,
        'anonymized_at': emp.anonymized_at.isoformat(),
        'documents_scrubbed': docs_scrubbed,
    }})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def list_hr_document_access_log(request, document_id):
    """Who read this document, and when? HR-admin only. Pagination via
    ``limit`` / ``offset`` query params (defaults 50/0, hard cap 200)."""
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR-admin access required'},
                        status=status.HTTP_403_FORBIDDEN)
    company = request.user.company
    d = HRDocument.objects.filter(company=company, pk=document_id).first()
    if not d:
        return Response({'status': 'error', 'message': 'Document not found'},
                        status=status.HTTP_404_NOT_FOUND)
    try:
        limit = max(1, min(int(request.GET.get('limit') or 50), 200))
        offset = max(0, int(request.GET.get('offset') or 0))
    except ValueError:
        limit, offset = 50, 0
    qs = HRDocumentAccessLog.objects.filter(document=d).select_related('actor')
    total = qs.count()
    rows = [{
        'id': r.id,
        'action': r.action,
        'actor_id': r.actor_id,
        'actor_email': r.actor.email if r.actor_id else None,
        'actor_name': r.actor.full_name if r.actor_id else None,
        'ip_address': r.ip_address,
        'user_agent': r.user_agent,
        'created_at': r.created_at.isoformat() if r.created_at else None,
    } for r in qs[offset:offset + limit]]
    return Response({'status': 'success', 'data': rows,
                     'pagination': {'total': total, 'limit': limit, 'offset': offset}})


# ============================================================================
# GDPR right-to-export (F3) — Article 15 / 20 data-portability bundle
# ============================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def export_employee_data(request, employee_id):
    """GDPR Article 15 / 20 data-portability export.

    Returns a ZIP containing the employee's profile, leave history, comp
    history, performance reviews, goals, personal documents (file copies),
    and audit-log entries that reference them. HR-admin OR self only.

    Synchronous — fine for typical employee record sizes (<100 MB). If a
    long-tenured employee with thousands of documents stresses this, move
    to a Celery task that emails a download link.
    """
    import io
    import zipfile
    from django.http import HttpResponse

    emp, err = _company_employee_or_404(request, employee_id)
    if err:
        return err
    company = request.user.company
    caller_user_id = getattr(request.user, 'user_id', None)
    is_self = caller_user_id and str(caller_user_id) == str(emp.user_id)
    is_admin = _is_hr_admin(request.user)
    if not (is_self or is_admin):
        return Response({'status': 'error',
                         'message': 'Only the employee themselves or an HR-admin can export this record.'},
                        status=status.HTTP_403_FORBIDDEN)

    from hr_agent.models import (
        LeaveBalance, LeaveRequest, HRDocument, PerformanceReview,
        PerformanceGoal, HRAuditLog, HRDocumentAccessLog,
    )
    try:
        from hr_agent.models import Compensation
    except ImportError:
        Compensation = None

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Profile (serialised employee row)
        zf.writestr('profile.json', json.dumps(_serialize_employee(emp), indent=2, default=str))

        # Leave history
        leave_rows = list(LeaveRequest.objects.filter(employee=emp).values(
            'id', 'leave_type', 'start_date', 'end_date', 'days_requested',
            'status', 'reason', 'approval_note', 'decided_at', 'created_at',
        ))
        zf.writestr('leave_requests.json', json.dumps(leave_rows, indent=2, default=str))
        balance_rows = list(LeaveBalance.objects.filter(employee=emp).values(
            'leave_type', 'accrued_days', 'used_days', 'carried_over_days',
            'period_start', 'period_end',
        ))
        zf.writestr('leave_balances.json', json.dumps(balance_rows, indent=2, default=str))

        # Compensation history (HR-admin only includes raw amounts; self gets
        # their own data per GDPR right-of-access, so include here too).
        if Compensation is not None:
            comp_rows = list(Compensation.objects.filter(employee=emp).values(
                'effective_date', 'base_salary', 'currency', 'pay_frequency',
                'bonus_target_pct', 'equity_grant_value', 'grade', 'reason',
                'notes', 'created_at',
            ))
            zf.writestr('compensation.json', json.dumps(comp_rows, indent=2, default=str))

        # Performance reviews. For self exports we still include unreleased
        # reviews because GDPR right-of-access entitles the subject to ALL
        # personal data the company holds, including in-progress manager
        # commentary about them.
        review_rows = list(PerformanceReview.objects.filter(employee=emp).values(
            'cycle__name', 'status', 'self_summary', 'manager_summary',
            'strengths', 'growth_areas', 'goals', 'overall_rating',
            'visible_to_employee', 'self_submitted_at', 'manager_submitted_at',
            'finalized_at', 'created_at',
        ))
        zf.writestr('performance_reviews.json', json.dumps(review_rows, indent=2, default=str))

        # Goals (own, plus parent linkage)
        goal_rows = list(PerformanceGoal.objects.filter(employee=emp).values(
            'title', 'description', 'success_criteria', 'status', 'weight_pct',
            'target_value', 'current_value', 'progress_pct', 'due_date',
            'closed_at', 'created_at',
        ))
        zf.writestr('goals.json', json.dumps(goal_rows, indent=2, default=str))

        # Audit log entries referencing this employee
        audit_rows = list(HRAuditLog.objects.filter(
            company=company, target_type='employee', target_id=emp.id,
        ).values('action', 'target_type', 'target_id', 'diff', 'created_at',
                 'actor__email'))
        zf.writestr('audit_log.json', json.dumps(audit_rows, indent=2, default=str))

        # Document access log — who has read this employee's personal docs
        access_rows = list(HRDocumentAccessLog.objects.filter(
            company=company, document__employee=emp,
        ).values('action', 'document_id', 'ip_address', 'user_agent',
                 'created_at', 'actor__email'))
        zf.writestr('document_access_log.json', json.dumps(access_rows, indent=2, default=str))

        # Personal documents — actual file bytes when present on disk
        from django.conf import settings as _s
        personal_docs = HRDocument.objects.filter(company=company, employee=emp)
        doc_index = []
        for d in personal_docs:
            doc_index.append({
                'id': d.id, 'title': d.title, 'document_type': d.document_type,
                'confidentiality': d.confidentiality, 'file_path': d.file_path,
                'file_format': d.file_format, 'file_size': d.file_size,
                'extracted_fields': d.extracted_fields or {},
                'created_at': d.created_at.isoformat() if d.created_at else None,
            })
            if d.file_path:
                try:
                    full = Path(_s.MEDIA_ROOT) / d.file_path
                    if full.exists() and full.is_file():
                        with open(full, 'rb') as fh:
                            zf.writestr(f'documents/{d.id}_{Path(d.file_path).name}', fh.read())
                except Exception:
                    logger.exception("export_employee_data: failed to read file for doc %s", d.id)
        zf.writestr('documents/_index.json', json.dumps(doc_index, indent=2, default=str))

        # README
        zf.writestr('README.txt',
            "GDPR Data Export\n"
            "================\n"
            f"Employee: {emp.full_name} (id={emp.id})\n"
            f"Generated: {timezone.now().isoformat()}\n"
            f"Generated by: {request.user.email}\n\n"
            "This archive contains all personal data the company holds about\n"
            "you. JSON files are structured per category; the `documents/`\n"
            "directory contains the actual file bytes for each personal\n"
            "document, indexed in `documents/_index.json`.\n")

    # Audit the export itself — GDPR exports are auditable events.
    _write_audit_log(
        request.user, company, 'employee.gdpr_export', 'employee', emp.id,
        after={'exported_by': request.user.email,
               'self_export': bool(is_self),
               'admin_export': bool(is_admin),
               'bytes': buf.tell()},
    )

    buf.seek(0)
    resp = HttpResponse(buf.read(), content_type='application/zip')
    safe_name = ''.join(c if c.isalnum() else '_' for c in (emp.full_name or f'employee_{emp.id}'))[:60]
    resp['Content-Disposition'] = f'attachment; filename="{safe_name}_gdpr_export.zip"'
    return resp


# ============================================================================
# HR document soft-deprecation + re-ingest (D-F2, D-F3)
# ============================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def mark_hr_document_outdated(request, document_id):
    """Soft-deprecate an HR doc: excluded from retrieval immediately, kept on
    disk so HR can review or restore. Distinct from `superseded_by` (which
    requires uploading a replacement). HR-admin only."""
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR-admin access required'},
                        status=status.HTTP_403_FORBIDDEN)
    company = request.user.company
    d = HRDocument.objects.filter(company=company, pk=document_id).first()
    if not d:
        return Response({'status': 'error', 'message': 'Document not found'},
                        status=status.HTTP_404_NOT_FOUND)
    if d.is_outdated:
        return Response({'status': 'success', 'data': {'id': d.id, 'is_outdated': True, 'already': True}})
    d.is_outdated = True
    d.save(update_fields=['is_outdated', 'updated_at'])
    _write_audit_log(request.user, company, 'hr_document.mark_outdated',
                     'hr_document', d.id, after={'is_outdated': True})
    return Response({'status': 'success', 'data': {'id': d.id, 'is_outdated': True}})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def unmark_hr_document_outdated(request, document_id):
    """Restore a soft-deprecated HR doc back into retrieval. HR-admin only."""
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR-admin access required'},
                        status=status.HTTP_403_FORBIDDEN)
    company = request.user.company
    d = HRDocument.objects.filter(company=company, pk=document_id).first()
    if not d:
        return Response({'status': 'error', 'message': 'Document not found'},
                        status=status.HTTP_404_NOT_FOUND)
    if not d.is_outdated:
        return Response({'status': 'success', 'data': {'id': d.id, 'is_outdated': False, 'already': True}})
    d.is_outdated = False
    d.save(update_fields=['is_outdated', 'updated_at'])
    _write_audit_log(request.user, company, 'hr_document.unmark_outdated',
                     'hr_document', d.id, after={'is_outdated': False})
    return Response({'status': 'success', 'data': {'id': d.id, 'is_outdated': False}})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([HRCRUDThrottle])
def reingest_hr_document(request, document_id):
    """Re-run the ingestion pipeline on an HR doc — useful when processing
    landed in `failed`, or after fixing OCR settings, or after updating the
    embedding model. Wipes existing chunks + flips status back to
    `processing`, then dispatches the Celery task. HR-admin only."""
    if not _is_hr_admin(request.user):
        return Response({'status': 'error', 'message': 'HR-admin access required'},
                        status=status.HTTP_403_FORBIDDEN)
    company = request.user.company
    d = HRDocument.objects.filter(company=company, pk=document_id).first()
    if not d:
        return Response({'status': 'error', 'message': 'Document not found'},
                        status=status.HTTP_404_NOT_FOUND)
    d.chunks.all().delete()
    d.chunks_processed = 0
    d.chunks_total = 0
    d.is_indexed = False
    d.processing_status = 'processing'
    d.processing_error = ''
    d.save(update_fields=['chunks_processed', 'chunks_total', 'is_indexed',
                          'processing_status', 'processing_error', 'updated_at'])
    try:
        from hr_agent.tasks import process_hr_document
        process_hr_document.delay(d.id)
    except Exception as exc:
        logger.exception("reingest_hr_document: failed to dispatch process_hr_document for doc %s", d.id)
        d.processing_status = 'failed'
        d.processing_error = f'Failed to enqueue: {exc}'
        d.save(update_fields=['processing_status', 'processing_error', 'updated_at'])
        return Response({'status': 'error',
                         'message': f'Failed to enqueue ingestion: {exc}'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    _write_audit_log(request.user, company, 'hr_document.reingest',
                     'hr_document', d.id,
                     after={'processing_status': d.processing_status})
    return Response({'status': 'success', 'data': {
        'id': d.id, 'processing_status': d.processing_status,
    }})


# ============================================================================
# HR Slack + Teams send adapters (N-F1)
# ============================================================================

def _send_hr_notification_slack(company, subject, body):
    """POST to the tenant's HR Slack webhook URL. Returns False with a log
    line when no URL is configured — caller can queue / fail."""
    url = (getattr(company, 'hr_slack_webhook_url', '') or '').strip()
    if not url:
        logger.warning("HR Slack send skipped — no hr_slack_webhook_url for company %s",
                       getattr(company, 'id', '?'))
        return False
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError
    text = f"*{subject}*\n{body}" if subject else body
    payload = json.dumps({'text': text}).encode('utf-8')
    req = Request(url, data=payload, method='POST',
                  headers={'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=15) as resp:
            return 200 <= int(resp.status) < 300
    except (URLError, HTTPError, OSError) as exc:
        logger.warning("HR Slack send failed for company %s: %s",
                       getattr(company, 'id', '?'), exc)
        return False


def _send_hr_notification_teams(company, subject, body):
    """POST to the tenant's HR Teams webhook URL. Same MessageCard envelope
    Frontline uses."""
    url = (getattr(company, 'hr_teams_webhook_url', '') or '').strip()
    if not url:
        logger.warning("HR Teams send skipped — no hr_teams_webhook_url for company %s",
                       getattr(company, 'id', '?'))
        return False
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError
    title = subject or 'HR Notification'
    payload = json.dumps({
        '@type': 'MessageCard',
        '@context': 'https://schema.org/extensions',
        'summary': title[:200],
        'title': title,
        'text': body,
    }).encode('utf-8')
    req = Request(url, data=payload, method='POST',
                  headers={'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=15) as resp:
            return 200 <= int(resp.status) < 300
    except (URLError, HTTPError, OSError) as exc:
        logger.warning("HR Teams send failed for company %s: %s",
                       getattr(company, 'id', '?'), exc)
        return False


def _dispatch_hr_notification(template, recipient_email, subject, body, company):
    """Route a rendered HR notification to the right channel adapter. Returns
    ``(ok, channel_used)``. Defaults to email for empty/unknown channels so a
    typo can't silently drop notifications."""
    channel = (getattr(template, 'channel', 'email') or 'email').lower()
    if channel == 'slack':
        return _send_hr_notification_slack(company, subject, body), 'slack'
    if channel == 'teams':
        return _send_hr_notification_teams(company, subject, body), 'teams'
    if channel in ('sms', 'in_app'):
        logger.warning("HR channel %r not implemented yet — notification dropped (template=%s)",
                       channel, getattr(template, 'id', '?'))
        return False, channel
    # Default to email (back-compat). Use the existing per-template email
    # helpers / Celery sender for retries; here just send synchronously.
    try:
        from django.core.mail import send_mail
        send_mail(
            subject=subject or 'Notification',
            message=body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
            recipient_list=[recipient_email] if recipient_email else [],
            fail_silently=False,
        )
        return True, 'email'
    except Exception:
        logger.exception("HR email send failed for template %s recipient %s",
                         getattr(template, 'id', '?'), recipient_email)
        return False, 'email'

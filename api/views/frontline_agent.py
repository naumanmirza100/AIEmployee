"""
Frontline Agent API Views for Company Users
Similar structure to marketing_agent.py and recruitment_agent.py
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from Frontline_agent.throttling import (
    FrontlinePublicThrottle,
    FrontlineLLMThrottle,
    FrontlineUploadThrottle,
)
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q, Count
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.conf import settings
from datetime import timedelta, datetime
import json
import logging
import csv
import re
import os
import hashlib
import uuid
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.models import CompanyUser, Company
from Frontline_agent.models import (
    Document, Ticket, TicketNote, KnowledgeBase, FrontlineQAChat, FrontlineQAChatMessage,
    NotificationTemplate, ScheduledNotification, FrontlineWorkflow, FrontlineWorkflowExecution,
    FrontlineWorkflowVersion, FrontlineMeeting,
    SavedGraphPrompt, KBFeedback, FrontlineNotificationPreferences, DocumentChunk,
)
from Frontline_agent.document_processor import DocumentProcessor
from core.Fronline_agent.frontline_agent import FrontlineAgent
from core.Fronline_agent.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


def _parse_rag_params(data):
    """Pull optional RAG tuning params from a request dict. Returns
    (min_similarity, max_age_days, max_results, enable_rewrite) with safe defaults
    and hard caps so callers can't request runaway LLM work.
    """
    def _as_float(v, lo=0.0, hi=1.0):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return max(lo, min(hi, f))

    def _as_int(v, lo, hi):
        try:
            i = int(v)
        except (TypeError, ValueError):
            return None
        return max(lo, min(hi, i))

    min_similarity = _as_float(data.get('min_similarity')) if data.get('min_similarity') is not None else None
    max_age_days = _as_int(data.get('max_age_days'), 1, 3650) if data.get('max_age_days') is not None else None
    max_results = _as_int(data.get('max_results'), 1, 10) or 5
    enable_rewrite = bool(data.get('enable_rewrite', False))
    return min_similarity, max_age_days, max_results, enable_rewrite


def _run_notification_triggers(company_id, event_type, ticket, old_status=None):
    """
    Evaluate notification template trigger_config and create ScheduledNotification when
    template has trigger_config.on == event_type (e.g. ticket_created, ticket_updated).
    """
    try:
        templates = NotificationTemplate.objects.filter(
            company_id=company_id,
            trigger_config__on=event_type,
        )
        for t in templates:
            cfg = t.trigger_config or {}
            if cfg.get('on') != event_type:
                continue
            recipient_email = getattr(ticket.created_by, 'email', '') or ''
            if not _should_send_notification_to_recipient(company_id, recipient_email, t.channel, event_type):
                logger.info(f"Notification trigger: skipped template {t.id} for {recipient_email} (user preferences)")
                continue
            delay_minutes = int(cfg.get('delay_minutes', 0))
            scheduled_at = timezone.now() + timedelta(minutes=delay_minutes)
            context = {
                'ticket_id': ticket.id,
                'ticket_title': ticket.title,
                'resolution': ticket.resolution or '',
                'customer_name': getattr(ticket.created_by, 'email', '') or '',
            }
            ScheduledNotification.objects.create(
                company_id=company_id,
                template=t,
                scheduled_at=scheduled_at,
                status='pending',
                recipient_email=recipient_email,
                related_ticket=ticket,
                context=context,
            )
            logger.info(f"Notification trigger: created scheduled notification for template {t.id} (event={event_type}, ticket={ticket.id})")
    except Exception as e:
        logger.exception("_run_notification_triggers failed: %s", e)


def _run_workflow_triggers(company_id, event_type, ticket, executed_by_user, old_status=None):
    """
    Run workflows whose trigger_conditions match this ticket event.
    trigger_conditions: {"on": "ticket_created"|"ticket_updated", "category": "...", "priority": "...", "status": "..." (for ticket_updated = new status)}.
    executed_by_user: Django User (e.g. from _get_or_create_user_for_company_user(company_user)).
    """
    try:
        workflows = FrontlineWorkflow.objects.filter(company_id=company_id, is_active=True)
        for w in workflows:
            tc = (w.trigger_conditions or {})
            if tc.get('on') != event_type:
                continue
            if tc.get('category') is not None and ticket.category != tc.get('category'):
                continue
            if tc.get('priority') is not None and ticket.priority != tc.get('priority'):
                continue
            if event_type == 'ticket_updated' and tc.get('status') is not None and ticket.status != tc.get('status'):
                continue
            context_data = {
                'ticket_id': ticket.id,
                'ticket_title': ticket.title,
                'description': getattr(ticket, 'description', '') or '',
                'resolution': (ticket.resolution or ''),
                'customer_name': getattr(ticket.created_by, 'email', '') or '',
                'recipient_email': getattr(ticket.created_by, 'email', '') or '',
                'status': ticket.status,
                'priority': ticket.priority,
                'category': ticket.category,
            }
            if event_type == 'ticket_updated' and old_status is not None:
                context_data['old_status'] = old_status
            try:
                exec_obj = FrontlineWorkflowExecution.objects.create(
                    workflow=w,
                    workflow_name=w.name,
                    workflow_description=w.description or '',
                    executed_by=executed_by_user,
                    status='awaiting_approval' if w.requires_approval else 'in_progress',
                    context_data=context_data,
                )
                if w.requires_approval:
                    logger.info(f"Workflow trigger: workflow {w.id} requires approval. Status: awaiting_approval.")
                else:
                    success, result_data, err = _execute_workflow_steps(w, context_data, executed_by_user)
                    exec_obj.status = 'completed' if success else 'failed'
                    exec_obj.result_data = result_data or {}
                    exec_obj.error_message = err
                    exec_obj.completed_at = timezone.now()
                    exec_obj.save()
                    logger.info(f"Workflow trigger: executed workflow {w.id} ({w.name}) for event={event_type} ticket={ticket.id}, status={exec_obj.status}")
            except Exception as e:
                logger.exception("Workflow trigger: execution failed for workflow %s (ticket %s): %s", w.id, ticket.id, e)
    except Exception as e:
        logger.exception("_run_workflow_triggers failed: %s", e)


def _get_or_create_user_for_company_user(company_user):
    """
    Get or create a Django User for a CompanyUser.
    This is needed because some models use User, not CompanyUser.
    """
    try:
        # Try to find existing user with matching email
        user = User.objects.get(email=company_user.email)
        return user
    except User.DoesNotExist:
        # Create a new User for this company user
        username = f"company_user_{company_user.id}_{company_user.email}"
        user = User.objects.create_user(
            username=username,
            email=company_user.email,
            password=None,  # Password not used for company users
            first_name=company_user.full_name.split()[0] if company_user.full_name else '',
            last_name=' '.join(company_user.full_name.split()[1:]) if company_user.full_name and len(company_user.full_name.split()) > 1 else ''
        )
        return user


def _sla_due_at_for_priority(priority):
    """Return SLA due datetime for a ticket priority (urgent=4h, high=8h, medium=24h, low=48h)."""
    from datetime import timedelta
    hours = {'urgent': 4, 'high': 8, 'medium': 24, 'low': 48}.get((priority or 'medium').lower(), 24)
    return timezone.now() + timedelta(hours=hours)


def _should_send_notification_to_recipient(company_id, recipient_email, channel, event_type=None):
    """
    Check if the recipient (by email, same company) has notification preferences that allow this send.
    event_type: 'ticket_created' | 'ticket_updated' | 'ticket_assigned' | None (manual/workflow -> use workflow_email_enabled).
    Returns True if we should send, False if user opted out.
    """
    if not recipient_email or not company_id:
        return True
    try:
        cu = CompanyUser.objects.filter(company_id=company_id, email=recipient_email.strip(), is_active=True).first()
        if not cu:
            return True
        prefs = getattr(cu, 'frontline_notification_preferences', None)
        if not prefs:
            return True
        if channel == 'email':
            if not prefs.email_enabled:
                return False
            if event_type == 'ticket_created':
                return prefs.ticket_created_email
            if event_type == 'ticket_updated':
                return prefs.ticket_updated_email
            if event_type == 'ticket_assigned':
                return prefs.ticket_assigned_email
            # manual send or workflow send_email step
            return prefs.workflow_email_enabled
        if channel == 'in_app':
            return prefs.in_app_enabled
        return True
    except Exception as e:
        logger.warning("_should_send_notification_to_recipient check failed: %s", e)
        return True


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def frontline_dashboard(request):
    """
    Frontline Agent Dashboard - Returns overview stats for company user
    """
    try:
        company_user = request.user
        company = company_user.company
        user = _get_or_create_user_for_company_user(company_user)
        
        # Get company's documents
        documents = Document.objects.filter(company=company)
        tickets = Ticket.objects.filter(created_by=user)
        
        # Get stats
        total_documents = documents.count()
        indexed_documents = documents.filter(is_indexed=True).count()
        total_tickets = tickets.count()
        open_tickets = tickets.filter(status__in=['new', 'open', 'in_progress']).count()
        resolved_tickets = tickets.filter(status__in=['resolved', 'closed', 'auto_resolved']).count()
        auto_resolved_tickets = tickets.filter(auto_resolved=True).count()
        
        recent_documents = documents.order_by('-created_at')[:10]
        recent_tickets = tickets.order_by('-created_at')[:10]
        
        return Response({
            'status': 'success',
            'data': {
                'stats': {
                    'total_documents': total_documents,
                    'indexed_documents': indexed_documents,
                    'total_tickets': total_tickets,
                    'open_tickets': open_tickets,
                    'resolved_tickets': resolved_tickets,
                    'auto_resolved_tickets': auto_resolved_tickets,
                },
                'recent_documents': [
                    {
                        'id': d.id,
                        'title': d.title,
                        'file_format': d.file_format,
                        'document_type': d.document_type,
                        'is_indexed': d.is_indexed,
                        'processed': d.processed,
                        'created_at': d.created_at.isoformat(),
                    }
                    for d in recent_documents
                ],
                'recent_tickets': [
                    {
                        'id': t.id,
                        'title': t.title,
                        'status': t.status,
                        'priority': t.priority,
                        'category': t.category,
                        'auto_resolved': t.auto_resolved,
                        'created_at': t.created_at.isoformat(),
                    }
                    for t in recent_tickets
                ]
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("frontline_dashboard failed")
        return Response(
            {'status': 'error', 'message': 'Failed to load frontline dashboard', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def frontline_widget_config(request):
    """Get the authenticated tenant's widget config (for the admin UI).
    Returns widget_key, allowed_origins CSV, and the resolved widget config dict."""
    try:
        from Frontline_agent.widget_utils import resolved_widget_config
        company_user = request.user
        company = company_user.company
        if not company.frontline_widget_key:
            company.frontline_widget_key = str(uuid.uuid4())
            company.save(update_fields=['frontline_widget_key'])
        return Response({
            'status': 'success',
            'data': {
                'widget_key': company.frontline_widget_key,
                'allowed_origins': getattr(company, 'frontline_allowed_origins', '') or '',
                'config': resolved_widget_config(company),
                'hcaptcha_site_key': (getattr(settings, 'HCAPTCHA_SITE_KEY', '') or None),
            }
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("frontline_widget_config failed")
        return Response(
            {'status': 'error', 'message': 'Failed to load widget config', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["PATCH"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_frontline_widget_config(request):
    """Save the tenant's widget theming + operating hours + pre-chat config.
    Also accepts `allowed_origins` (CSV) for origin pinning."""
    try:
        from Frontline_agent.widget_utils import DEFAULT_WIDGET_CONFIG, resolved_widget_config
        company = request.user.company
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))

        if 'allowed_origins' in data:
            company.frontline_allowed_origins = str(data['allowed_origins'] or '')[:2000]

        if 'config' in data and isinstance(data['config'], dict):
            # Shallow-validate against the known top-level keys so garbage fields
            # don't poison the JSON column. Deep structure is the tenant's call.
            allowed_top_level = set(DEFAULT_WIDGET_CONFIG.keys())
            saved = company.frontline_widget_config or {}
            for k, v in data['config'].items():
                if k in allowed_top_level:
                    saved[k] = v
            company.frontline_widget_config = saved

        company.save(update_fields=['frontline_allowed_origins',
                                    'frontline_widget_config', 'updated_at'])
        return Response({'status': 'success', 'data': {
            'allowed_origins': company.frontline_allowed_origins,
            'config': resolved_widget_config(company),
        }})
    except Exception as e:
        logger.exception("update_frontline_widget_config failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([])
@authentication_classes([])
@throttle_classes([FrontlinePublicThrottle])
def public_widget_config(request):
    """Public endpoint the embed script calls on page load to fetch theming,
    pre-chat form definition, operating-hours status, and whether a CAPTCHA is
    required for the next POST. Auth is the widget_key itself."""
    try:
        from Frontline_agent.widget_utils import resolved_widget_config, is_within_operating_hours
        # Tolerate the key arriving via query, header, or body.
        company, err = _get_company_by_widget_key(request)
        if err:
            return err
        cfg = resolved_widget_config(company)
        is_open, reason = is_within_operating_hours(cfg)
        return Response({'status': 'success', 'data': {
            'theme': cfg.get('theme'),
            'pre_chat_form': cfg.get('pre_chat_form'),
            'operating_hours': {
                'enabled': bool((cfg.get('operating_hours') or {}).get('enabled')),
                'is_open': is_open,
                'offline_message': (cfg.get('operating_hours') or {}).get('offline_message'),
            },
            'require_captcha': bool(cfg.get('require_captcha')),
            'hcaptcha_site_key': (getattr(settings, 'HCAPTCHA_SITE_KEY', '') or None),
            'max_attachment_bytes': cfg.get('max_attachment_bytes'),
            'allowed_attachment_mime': cfg.get('allowed_attachment_mime'),
        }})
    except Exception as e:
        logger.exception("public_widget_config failed")
        return Response({'status': 'error', 'message': 'Failed to load widget config'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_documents(request):
    """List all documents for company user"""
    try:
        company_user = request.user
        company = company_user.company
        
        documents = Document.objects.filter(company=company).order_by('-created_at')
        
        # Optional filters
        document_type = request.GET.get('document_type')
        if document_type:
            documents = documents.filter(document_type=document_type)
        
        is_indexed = request.GET.get('is_indexed')
        if is_indexed is not None:
            is_indexed_bool = is_indexed.lower() == 'true'
            documents = documents.filter(is_indexed=is_indexed_bool)
        
        # Pagination
        page = int(request.GET.get('page', 1))
        limit = int(request.GET.get('limit', 20))
        offset = (page - 1) * limit
        
        total = documents.count()
        documents_page = documents[offset:offset + limit]
        
        return Response({
            'status': 'success',
            'data': {
                'documents': [
                    {
                        'id': d.id,
                        'title': d.title,
                        'description': d.description,
                        'document_type': d.document_type,
                        'file_format': d.file_format,
                        'file_size': d.file_size,
                        'is_indexed': d.is_indexed,
                        'processed': d.processed,
                        'processing_status': d.processing_status,
                        'chunks_processed': d.chunks_processed,
                        'chunks_total': d.chunks_total,
                        'processing_error': d.processing_error or None,
                        'version': d.version,
                        'parent_document_id': d.parent_document_id,
                        'superseded_by_id': d.superseded_by_id,
                        'visibility': d.visibility,
                        'retention_days': d.retention_days,
                        'created_at': d.created_at.isoformat(),
                        'updated_at': d.updated_at.isoformat(),
                    }
                    for d in documents_page
                ],
                'total': total,
                'page': page,
                'limit': limit,
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("list_documents failed")
        return Response(
            {'status': 'error', 'message': 'Failed to list documents', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([FrontlineUploadThrottle])
def upload_document(request):
    """Upload and process a document"""
    try:
        company_user = request.user
        company = company_user.company
        user = _get_or_create_user_for_company_user(company_user)
        
        if 'file' not in request.FILES:
            return Response(
                {'status': 'error', 'message': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        uploaded_file = request.FILES['file']
        title = request.POST.get('title', uploaded_file.name)
        description = request.POST.get('description', '')
        document_type = request.POST.get('document_type', 'knowledge_base')

        # Validate file size (50MB max) - increased to support large documents with 100+ pages
        if uploaded_file.size > 50 * 1024 * 1024:
            return Response(
                {'status': 'error', 'message': 'File size exceeds 50MB limit'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Sanitize filename (strips path separators, safe characters only)
        safe_filename = DocumentProcessor.sanitize_filename(uploaded_file.name)

        # Read once into memory so we can validate, hash, and write without re-reading a spent pointer
        file_bytes = uploaded_file.read()

        # Magic-byte / content validation: reject disguised files (e.g. .exe renamed to .pdf)
        content_ok, _detected_fmt, content_err = DocumentProcessor.validate_content(file_bytes, safe_filename)
        if not content_ok:
            return Response(
                {'status': 'error', 'message': content_err or 'File content validation failed'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Compute content hash once and use it for both dedupe and storage naming
        file_hash_full = hashlib.sha256(file_bytes).hexdigest()

        # Dedupe against previous uploads in this company
        existing_doc = Document.objects.filter(company=company, file_hash=file_hash_full).first()
        if existing_doc:
            return Response({
                'status': 'error',
                'message': 'Document with same content already exists',
                'document_id': existing_doc.id
            }, status=status.HTTP_400_BAD_REQUEST)

        # Create uploads directory if it doesn't exist
        upload_dir = Path(settings.MEDIA_ROOT) / 'frontline_documents' / str(company.id)
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Storage name: short hash prefix + sanitized original name
        storage_filename = f"{file_hash_full[:16]}_{safe_filename}"
        file_path = upload_dir / storage_filename

        # Save the bytes we already read — no second read of the upload stream
        with open(file_path, 'wb') as f:
            f.write(file_bytes)
        
        # Derive file format from the sanitized filename (consistent with stored file).
        file_format = DocumentProcessor.get_file_format(safe_filename)

        # Clamp chunking / retention / visibility params from the request against safe bounds.
        def _clamp_int(raw, lo, hi, fallback):
            try:
                v = int(raw)
            except (TypeError, ValueError):
                return fallback
            return max(lo, min(hi, v))

        default_size = int(getattr(settings, 'FRONTLINE_CHUNK_SIZE', 4000))
        default_overlap = int(getattr(settings, 'FRONTLINE_CHUNK_OVERLAP', 200))
        size_min = int(getattr(settings, 'FRONTLINE_CHUNK_SIZE_MIN', 500))
        size_max = int(getattr(settings, 'FRONTLINE_CHUNK_SIZE_MAX', 16000))
        chunk_size = _clamp_int(request.POST.get('chunk_size'), size_min, size_max, default_size)
        chunk_overlap = _clamp_int(
            request.POST.get('chunk_overlap'), 0, max(0, chunk_size - 1), default_overlap,
        )

        retention_days = request.POST.get('retention_days')
        retention_days = _clamp_int(retention_days, 1, 36500, None) if retention_days else None

        visibility = (request.POST.get('visibility') or 'company').strip().lower()
        if visibility not in ('company', 'private'):
            visibility = 'company'

        # Optional: new version of an existing doc. parent_document_id must belong
        # to the same company; its superseded_by pointer is updated after creation.
        parent_document = None
        parent_document_id = request.POST.get('parent_document_id')
        if parent_document_id:
            parent_document = Document.objects.filter(
                id=parent_document_id, company=company,
            ).first()
            if not parent_document:
                return Response(
                    {'status': 'error', 'message': 'parent_document_id not found for this company'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        document = Document.objects.create(
            title=title,
            description=description,
            document_type=document_type,
            file_path=str(file_path.relative_to(settings.MEDIA_ROOT)),
            file_size=uploaded_file.size,
            mime_type=uploaded_file.content_type,
            file_format=file_format,
            uploaded_by=user,
            company=company,
            file_hash=file_hash_full,
            processing_status='pending',
            visibility=visibility,
            retention_days=retention_days,
            parent_document=parent_document,
            version=(parent_document.version + 1) if parent_document else 1,
            processed_data={
                'file_format': file_format,
                'chunk_size': chunk_size,
                'chunk_overlap': chunk_overlap,
            },
        )

        # If this is a new version, point the old one at the new one so retrieval skips it.
        if parent_document:
            parent_document.superseded_by = document
            parent_document.save(update_fields=['superseded_by', 'updated_at'])

        # Optional private allowlist: assign the uploader so they always retain access.
        if visibility == 'private':
            document.allowed_users.add(company_user)

        # Enqueue async parse+chunk+embed. Worker updates processing_status / progress fields.
        from Frontline_agent.tasks import process_document as _process_document
        _process_document.delay(document.id)

        return Response({
            'status': 'accepted',
            'data': {
                'document_id': document.id,
                'title': document.title,
                'file_format': document.file_format,
                'processing_status': document.processing_status,
                'version': document.version,
                'parent_document_id': document.parent_document_id,
                'visibility': document.visibility,
                'retention_days': document.retention_days,
                'message': 'Upload accepted. Processing in the background — poll the status endpoint.',
                'status_url': f"/api/frontline/documents/{document.id}/status/",
            },
        }, status=status.HTTP_202_ACCEPTED)

    except Exception as e:
        logger.exception("upload_document failed")
        return Response(
            {'status': 'error', 'message': 'Failed to upload document', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def document_processing_status(request, document_id):
    """Poll a document's async-processing state. Client should stop polling once
    `processing_status` is 'ready' or 'failed'."""
    try:
        company = request.user.company
        d = Document.objects.filter(id=document_id, company=company).first()
        if not d:
            return Response({'status': 'error', 'message': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)
        total = max(1, d.chunks_total or 0)
        return Response({'status': 'success', 'data': {
            'id': d.id,
            'processing_status': d.processing_status,
            'chunks_processed': d.chunks_processed,
            'chunks_total': d.chunks_total,
            'progress_percent': round(100.0 * (d.chunks_processed or 0) / total, 1) if d.chunks_total else (
                100.0 if d.processing_status == 'ready' else 0.0
            ),
            'processing_error': d.processing_error or None,
            'version': d.version,
            'parent_document_id': d.parent_document_id,
            'superseded_by_id': d.superseded_by_id,
            'visibility': d.visibility,
            'retention_days': d.retention_days,
        }})
    except Exception as e:
        logger.exception("document_processing_status failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["PATCH"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_document_metadata(request, document_id):
    """Update non-content metadata: title, description, document_type, visibility,
    allowed_users, retention_days. File content and chunks are untouched — upload a
    new version to replace content."""
    try:
        company = request.user.company
        d = Document.objects.filter(id=document_id, company=company).first()
        if not d:
            return Response({'status': 'error', 'message': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))

        if 'title' in data:
            d.title = str(data['title'])[:200]
        if 'description' in data:
            d.description = str(data['description'])
        if 'document_type' in data:
            valid = {c[0] for c in Document.DOCUMENT_TYPE_CHOICES}
            dt = str(data['document_type'])
            if dt in valid:
                d.document_type = dt
        if 'visibility' in data:
            v = str(data['visibility']).lower()
            if v in ('company', 'private'):
                d.visibility = v
        if 'retention_days' in data:
            raw = data['retention_days']
            try:
                d.retention_days = max(1, min(36500, int(raw))) if raw else None
            except (TypeError, ValueError):
                pass

        d.save()

        # Replace allowed_users set if provided (only meaningful when private).
        if 'allowed_user_ids' in data and isinstance(data['allowed_user_ids'], list):
            ids = [int(x) for x in data['allowed_user_ids'] if str(x).isdigit()]
            valid_users = CompanyUser.objects.filter(id__in=ids, company=company)
            d.allowed_users.set(valid_users)

        return Response({'status': 'success', 'data': {
            'id': d.id,
            'title': d.title,
            'visibility': d.visibility,
            'retention_days': d.retention_days,
            'allowed_user_ids': list(d.allowed_users.values_list('id', flat=True)),
        }})
    except Exception as e:
        logger.exception("update_document_metadata failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_document(request, document_id):
    """Get document details"""
    try:
        company_user = request.user
        company = company_user.company
        
        document = get_object_or_404(Document, id=document_id, company=company)
        
        return Response({
            'status': 'success',
            'data': {
                'id': document.id,
                'title': document.title,
                'description': document.description,
                'document_type': document.document_type,
                'file_format': document.file_format,
                'file_size': document.file_size,
                'is_indexed': document.is_indexed,
                'processed': document.processed,
                'document_content': document.document_content[:5000] if document.document_content else '',  # First 5000 chars
                'created_at': document.created_at.isoformat(),
                'updated_at': document.updated_at.isoformat(),
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("get_document failed")
        return Response(
            {'status': 'error', 'message': 'Failed to get document', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([FrontlineLLMThrottle])
def summarize_document(request, document_id):
    """Summarize a document by ID. Body: optional { \"max_sentences\": 5, \"by_section\": false }."""
    try:
        company_user = request.user
        company = company_user.company
        document = get_object_or_404(Document, id=document_id, company=company)
        content = document.document_content or ""
        if not content.strip():
            return Response({
                'status': 'error',
                'message': 'Document has no text content to summarize',
            }, status=status.HTTP_400_BAD_REQUEST)
        data = json.loads(request.body) if request.body else {}
        max_sentences = data.get('max_sentences')
        by_section = data.get('by_section', False)
        agent = FrontlineAgent(company_id=company.id)
        result = agent.summarize_document(content, max_sentences=max_sentences, by_section=by_section)
        if not result.get('success'):
            return Response({
                'status': 'error',
                'message': result.get('error', 'Summarization failed'),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({
            'status': 'success',
            'data': {
                'document_id': document.id,
                'title': document.title,
                'summary': result.get('summary'),
            },
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("summarize_document failed")
        return Response(
            {'status': 'error', 'message': 'Failed to summarize document', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([FrontlineLLMThrottle])
def extract_document(request, document_id):
    """Extract structured data from a document. Body: optional { \"schema\": [\"parties\", \"dates\", \"amounts\"] }."""
    try:
        company_user = request.user
        company = company_user.company
        document = get_object_or_404(Document, id=document_id, company=company)
        content = document.document_content or ""
        if not content.strip():
            return Response({
                'status': 'error',
                'message': 'Document has no text content to extract from',
            }, status=status.HTTP_400_BAD_REQUEST)
        data = json.loads(request.body) if request.body else {}
        schema = data.get('schema')
        agent = FrontlineAgent(company_id=company.id)
        result = agent.extract_from_document(content, schema=schema)
        if not result.get('success'):
            return Response({
                'status': 'error',
                'message': result.get('error', 'Extraction failed'),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({
            'status': 'success',
            'data': {
                'document_id': document.id,
                'title': document.title,
                'extracted': result.get('data'),
            },
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("extract_document failed")
        return Response(
            {'status': 'error', 'message': 'Failed to extract from document', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_document(request, document_id):
    """Delete a document"""
    try:
        company_user = request.user
        company = company_user.company
        
        document = get_object_or_404(Document, id=document_id, company=company)
        
        # Delete file if exists
        if document.file_path:
            file_path = Path(settings.MEDIA_ROOT) / document.file_path
            if file_path.exists():
                file_path.unlink()
        
        document.delete()
        
        return Response({
            'status': 'success',
            'message': 'Document deleted successfully'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("delete_document failed")
        return Response(
            {'status': 'error', 'message': 'Failed to delete document', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def _build_knowledge_gap_task_description(question: str, agent_response: str) -> str:
    """Build description for a KB-gap ticket task so the user can add a document later."""
    return f"""**User query:** {question}

**Agent response:** {agent_response or "The knowledge base does not currently contain verified information about this topic."}

**Your task:** Add a document to the Knowledge Base so the agent can answer this and similar questions in the future.

**How to resolve:**
1. Go to the **Documents** tab and upload a document (PDF, DOCX, TXT, or similar) that covers the topic above.
2. Ensure the document clearly explains the relevant information (definitions, steps, or FAQs).
3. Once the document is uploaded and indexed, the agent will be able to answer similar questions automatically.
4. Close this ticket from the Ticket Tasks tab when done.
"""


def _origin_matches(request_origin: str, allowed_origins_csv: str) -> bool:
    """Check whether request_origin is in the company's comma-separated allowlist.

    Matching is case-insensitive on scheme+host[:port]; trailing slashes are stripped.
    Empty allowlist means "any origin" (back-compat for existing widgets).
    """
    allowlist = [o.strip().rstrip('/').lower() for o in (allowed_origins_csv or '').split(',') if o.strip()]
    if not allowlist:
        return True
    if not request_origin:
        return False
    return request_origin.strip().rstrip('/').lower() in allowlist


def _get_company_by_widget_key(request):
    """Resolve company from widget_key in body (POST) or query/header. Returns (company, error_response) or (company, None).

    Also enforces the company's frontline_allowed_origins allowlist against the
    request's Origin / Referer header. Empty allowlist = back-compat (any origin).
    """
    widget_key = None
    if request.method == 'POST' and request.body:
        try:
            data = json.loads(request.body)
            widget_key = (data.get('widget_key') or data.get('key') or '').strip()
        except Exception:
            pass
    if not widget_key:
        widget_key = (request.GET.get('widget_key') or request.GET.get('key') or '').strip()
    if not widget_key:
        widget_key = (request.headers.get('X-Widget-Key') or request.headers.get('X-Frontline-Widget-Key') or '').strip()
    if not widget_key:
        return None, Response(
            {'status': 'error', 'message': 'widget_key is required (body, query, or X-Widget-Key header)'},
            status=status.HTTP_400_BAD_REQUEST
        )
    company = Company.objects.filter(frontline_widget_key=widget_key, is_active=True).first()
    if not company:
        return None, Response(
            {'status': 'error', 'message': 'Invalid widget key'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Origin validation: if the company has configured allowed origins, the caller's
    # Origin (or Referer) must match. Prevents a scraped widget key from being used elsewhere.
    allowed = getattr(company, 'frontline_allowed_origins', '') or ''
    if allowed.strip():
        origin = (request.headers.get('Origin') or '').strip()
        if not origin:
            referer = (request.headers.get('Referer') or '').strip()
            if referer:
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(referer)
                    if parsed.scheme and parsed.netloc:
                        origin = f"{parsed.scheme}://{parsed.netloc}"
                except Exception:
                    origin = ''
        if not _origin_matches(origin, allowed):
            logger.warning(
                "Widget-key origin rejected: key=%s company=%s origin=%s",
                widget_key[:8] + '...', company.id, origin or '(none)',
            )
            return None, Response(
                {'status': 'error', 'message': 'Origin not allowed for this widget key'},
                status=status.HTTP_403_FORBIDDEN
            )
    return company, None


def _client_ip(request):
    """Extract the caller's IP honouring a single level of X-Forwarded-For
    (common case for our deployment). Falls back to REMOTE_ADDR."""
    xff = (request.META.get('HTTP_X_FORWARDED_FOR') or '').strip()
    if xff:
        return xff.split(',')[0].strip()
    return (request.META.get('REMOTE_ADDR') or '').strip()


def _check_widget_gates(request, company, body_data):
    """Enforce operating hours + CAPTCHA on a widget POST. Returns Response on
    reject, None on pass."""
    from Frontline_agent.widget_utils import (
        resolved_widget_config, is_within_operating_hours, verify_hcaptcha,
    )
    cfg = resolved_widget_config(company)

    is_open, _reason = is_within_operating_hours(cfg)
    if not is_open:
        return Response({
            'status': 'closed',
            'message': (cfg.get('operating_hours') or {}).get('offline_message')
                        or "We're offline right now. Please try again later.",
        }, status=status.HTTP_200_OK)

    if cfg.get('require_captcha'):
        token = (body_data or {}).get('captcha_token') or request.headers.get('X-Captcha-Token') or ''
        ok, reason = verify_hcaptcha(token, remote_ip=_client_ip(request))
        if not ok:
            return Response(
                {'status': 'error', 'message': 'CAPTCHA verification failed', 'reason': reason},
                status=status.HTTP_403_FORBIDDEN,
            )
    return None


@api_view(["POST"])
@permission_classes([])
@authentication_classes([])
@throttle_classes([FrontlinePublicThrottle])
def public_qa(request):
    """Public Knowledge Q&A for embedded chat/widget. No auth. Identify company by widget_key in body or X-Widget-Key header."""
    try:
        company, err = _get_company_by_widget_key(request)
        if err:
            return err
        data = json.loads(request.body) if request.body else {}
        gate = _check_widget_gates(request, company, data)
        if gate is not None:
            return gate
        question = (data.get('question') or '').strip()
        if not question:
            return Response(
                {'status': 'error', 'message': 'question is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        scope_document_type = data.get('scope_document_type')
        if scope_document_type is not None:
            scope_document_type = [scope_document_type] if isinstance(scope_document_type, str) else list(scope_document_type)
        scope_document_ids = data.get('scope_document_ids')
        if scope_document_ids is not None:
            scope_document_ids = [int(x) for x in scope_document_ids if x is not None]
        min_similarity, max_age_days, max_results, enable_rewrite = _parse_rag_params(data)
        agent = FrontlineAgent(company_id=company.id)
        result = agent.answer_question(
            question,
            company_id=company.id,
            scope_document_type=scope_document_type,
            scope_document_ids=scope_document_ids,
            min_similarity=min_similarity,
            max_age_days=max_age_days,
            max_results=max_results,
            enable_rewrite=enable_rewrite,
        )
        return Response({
            'status': 'success',
            'data': result
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("public_qa failed")
        return Response(
            {'status': 'error', 'message': 'Failed to process question', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@permission_classes([])
@authentication_classes([])
@throttle_classes([FrontlinePublicThrottle])
def public_submit(request):
    """Public web form submit (contact/support). Creates a ticket for the company. No auth.

    Accepts either application/json or multipart/form-data (for optional attachment).
    Body / form fields: widget_key, name, email, message, captcha_token, [file]."""
    try:
        company, err = _get_company_by_widget_key(request)
        if err:
            return err
        # Handle both JSON and multipart: prefer request.data, fall back to json.loads.
        if request.content_type and 'multipart' in request.content_type:
            data = dict(request.POST.items())
        else:
            data = json.loads(request.body) if request.body else {}
        gate = _check_widget_gates(request, company, data)
        if gate is not None:
            return gate
        name = (data.get('name') or data.get('full_name') or '').strip()
        email = (data.get('email') or '').strip()
        message = (data.get('message') or data.get('question') or data.get('description') or '').strip()
        if not message:
            return Response(
                {'status': 'error', 'message': 'message is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        # Assign ticket to first company user
        company_user = CompanyUser.objects.filter(company=company, is_active=True).order_by('id').first()
        if not company_user:
            return Response(
                {'status': 'error', 'message': 'Company has no users configured'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        user = _get_or_create_user_for_company_user(company_user)
        title = f"Web form: {(name or email or 'Contact')[:50]}"
        description = f"From: {name or 'N/A'}\nEmail: {email or 'N/A'}\n\n{message}"
        ticket = Ticket.objects.create(
            title=title,
            description=description,
            status='new',
            priority='medium',
            category='other',
            company=company,
            created_by=user,
            assigned_to=user,
            auto_resolved=False,
            sla_due_at=_sla_due_at_for_priority('medium'),
        )

        # Optional attachment — single file for now. Validates MIME + size against
        # the tenant's widget config; stores under media/frontline_widget_uploads/<company>/.
        attachment_info = None
        uploaded_file = request.FILES.get('file') if hasattr(request, 'FILES') else None
        if uploaded_file:
            from Frontline_agent.widget_utils import resolved_widget_config
            cfg = resolved_widget_config(company)
            max_bytes = int(cfg.get('max_attachment_bytes') or 10 * 1024 * 1024)
            allowed_mime = set(cfg.get('allowed_attachment_mime') or [])
            if uploaded_file.size > max_bytes:
                attachment_info = {'skipped': True, 'reason': 'too_large',
                                   'size': uploaded_file.size, 'max': max_bytes}
            elif allowed_mime and (uploaded_file.content_type or '').lower() not in {m.lower() for m in allowed_mime}:
                attachment_info = {'skipped': True, 'reason': 'disallowed_mime',
                                   'mime': uploaded_file.content_type}
            else:
                try:
                    safe_name = DocumentProcessor.sanitize_filename(uploaded_file.name)
                    upload_dir = Path(settings.MEDIA_ROOT) / 'frontline_widget_uploads' / str(company.id)
                    upload_dir.mkdir(parents=True, exist_ok=True)
                    stored = upload_dir / f"t{ticket.id}_{safe_name}"
                    with open(stored, 'wb') as fh:
                        for chunk in uploaded_file.chunks():
                            fh.write(chunk)
                    rel = str(stored.relative_to(settings.MEDIA_ROOT))
                    # Append the attachment path to the ticket description so agents see it.
                    ticket.description = (ticket.description or '') + f"\n\n[Attachment] {rel}"
                    ticket.save(update_fields=['description', 'updated_at'])
                    attachment_info = {'stored_path': rel, 'size': uploaded_file.size,
                                       'mime': uploaded_file.content_type}
                except Exception as exc:
                    logger.warning("public_submit attachment save failed: %s", exc)
                    attachment_info = {'skipped': True, 'reason': 'save_failed'}

        _run_notification_triggers(company.id, 'ticket_created', ticket)
        _run_workflow_triggers(company.id, 'ticket_created', ticket, user)
        return Response({
            'status': 'success',
            'message': 'Submitted successfully. We will get back to you soon.',
            'data': {'ticket_id': ticket.id, 'attachment': attachment_info},
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.exception("public_submit failed")
        return Response(
            {'status': 'error', 'message': 'Failed to submit', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([FrontlineLLMThrottle])
def knowledge_qa(request):
    """Knowledge Q&A - Answer questions using knowledge base and uploaded documents.
    When the agent has no verified info, a ticket task is created for the company user (Ticket Tasks tab)."""
    try:
        company_user = request.user
        company = company_user.company
        
        data = json.loads(request.body) if request.body else {}
        question = data.get('question', '').strip()
        
        if not question:
            return Response(
                {'status': 'error', 'message': 'Question is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Optional Q&A scope: restrict to document type(s) and/or specific document IDs
        scope_document_type = data.get('scope_document_type')
        if scope_document_type is not None:
            scope_document_type = [scope_document_type] if isinstance(scope_document_type, str) else list(scope_document_type)
        scope_document_ids = data.get('scope_document_ids')
        if scope_document_ids is not None:
            scope_document_ids = [int(x) for x in scope_document_ids if x is not None]

        # Optional retrieval tuning params (all safely defaulted if absent)
        min_similarity, max_age_days, max_results, enable_rewrite = _parse_rag_params(data)

        # Initialize agent with company_id
        agent = FrontlineAgent(company_id=company.id)
        result = agent.answer_question(
            question,
            company_id=company.id,
            scope_document_type=scope_document_type,
            scope_document_ids=scope_document_ids,
            min_similarity=min_similarity,
            max_age_days=max_age_days,
            max_results=max_results,
            enable_rewrite=enable_rewrite,
            company_user_id=company_user.id,
        )
        
        # When agent doesn't have verified info, create a ticket task assigned to this company user
        ticket_task_created = False
        ticket_task_id = None
        if result.get('has_verified_info') is False:
            try:
                user = _get_or_create_user_for_company_user(company_user)
                title = f"KB gap: {question[:60]}{'...' if len(question) > 60 else ''}"
                description = _build_knowledge_gap_task_description(
                    question,
                    result.get('answer') or "I don't have verified information about this topic in our knowledge base."
                )
                ticket = Ticket.objects.create(
                    title=title,
                    description=description,
                    status='new',
                    priority='medium',
                    category='knowledge_gap',
                    company=company,
                    created_by=user,
                    assigned_to=user,
                    auto_resolved=False,
                    sla_due_at=_sla_due_at_for_priority('medium'),
                )
                ticket_task_created = True
                ticket_task_id = ticket.id
                logger.info(f"Created KB-gap ticket task {ticket.id} for company_user {company_user.id}, question: {question[:50]}")
                _run_notification_triggers(company.id, 'ticket_created', ticket)
                _run_workflow_triggers(company.id, 'ticket_created', ticket, user)
            except Exception as e:
                logger.exception("Failed to create KB-gap ticket task: %s", e)
            
            # Ensure response text mentions that a task was created
            if ticket_task_created:
                result = dict(result)
                result['answer'] = (
                    result.get('answer', '') +
                    " A ticket task has been created for you. Go to your **Company Dashboard** and open the **Ticket Tasks** tab to see it. "
                    "Add a document in the Frontline Agent (Documents tab) to expand the knowledge base, then close the ticket in Ticket Tasks when done."
                )
                result['ticket_task_created'] = True
                result['ticket_task_id'] = ticket_task_id
        
        return Response({
            'status': 'success',
            'data': result
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("knowledge_qa failed")
        return Response(
            {'status': 'error', 'message': 'Failed to process question', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def knowledge_feedback(request):
    """Submit helpful/not helpful feedback for a knowledge-base answer. Improves docs and RAG."""
    try:
        company_user = request.user
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))
        question = (data.get('question') or '').strip()
        helpful = data.get('helpful')
        document_id = data.get('document_id')
        if not question:
            return Response({'status': 'error', 'message': 'question is required'}, status=status.HTTP_400_BAD_REQUEST)
        if helpful is None:
            return Response({'status': 'error', 'message': 'helpful (true/false) is required'}, status=status.HTTP_400_BAD_REQUEST)
        doc = None
        if document_id is not None:
            doc = Document.objects.filter(id=document_id, company=company_user.company).first()
        KBFeedback.objects.create(
            company_user=company_user,
            question=question,
            helpful=bool(helpful),
            document=doc,
        )
        return Response({'status': 'success', 'message': 'Feedback recorded'})
    except Exception as e:
        logger.exception("knowledge_feedback failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([FrontlineLLMThrottle])
def search_knowledge(request):
    """Search knowledge base and uploaded documents"""
    try:
        company_user = request.user
        company = company_user.company
        
        query = request.GET.get('q', '').strip()
        max_results = int(request.GET.get('max_results', 5))
        scope_document_type = request.GET.get('scope_document_type')
        if scope_document_type is not None:
            scope_document_type = [s.strip() for s in scope_document_type.split(',') if s.strip()]
        scope_document_ids = request.GET.get('scope_document_ids')
        if scope_document_ids is not None:
            scope_document_ids = [int(x) for x in scope_document_ids.split(',') if str(x).strip().isdigit()]
        
        if not query:
            return Response(
                {'status': 'error', 'message': 'Query parameter (q) is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Initialize agent with company_id
        agent = FrontlineAgent(company_id=company.id)
        result = agent.search_knowledge(
            query,
            company_id=company.id,
            max_results=max_results,
            scope_document_type=scope_document_type or None,
            scope_document_ids=scope_document_ids or None,
        )
        
        return Response({
            'status': 'success',
            'data': result
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("search_knowledge failed")
        return Response(
            {'status': 'error', 'message': 'Failed to search knowledge base', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_ticket_tasks(request):
    """List ticket tasks (KB-gap tasks) assigned to this company user. Shown in Ticket Tasks tab."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        tickets = Ticket.objects.filter(
            assigned_to=user,
            category='knowledge_gap',
        ).order_by('-created_at')
        data = [
            {
                'id': t.id,
                'title': t.title,
                'description': t.description,
                'status': t.status,
                'priority': t.priority,
                'created_at': t.created_at.isoformat(),
                'updated_at': t.updated_at.isoformat(),
            }
            for t in tickets
        ]
        return Response({'status': 'success', 'data': data})
    except Exception as e:
        logger.exception("list_ticket_tasks failed")
        return Response(
            {'status': 'error', 'message': 'Failed to list ticket tasks', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_tickets(request):
    """List support tickets with filters and pagination. Scoped to tickets created by this company user."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        qs = Ticket.objects.filter(created_by=user).order_by('-created_at')

        status_filter = request.GET.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        priority_filter = request.GET.get('priority')
        if priority_filter:
            qs = qs.filter(priority=priority_filter)
        category_filter = request.GET.get('category')
        if category_filter:
            qs = qs.filter(category=category_filter)
        date_from = request.GET.get('date_from')
        if date_from:
            try:
                from datetime import datetime
                dt = datetime.strptime(date_from, '%Y-%m-%d')
                qs = qs.filter(created_at__date__gte=dt.date())
            except ValueError:
                pass
        date_to = request.GET.get('date_to')
        if date_to:
            try:
                from datetime import datetime
                dt = datetime.strptime(date_to, '%Y-%m-%d')
                qs = qs.filter(created_at__date__lte=dt.date())
            except ValueError:
                pass

        page = max(1, int(request.GET.get('page', 1)))
        limit = min(100, max(1, int(request.GET.get('limit', 20))))
        total = qs.count()
        total_pages = (total + limit - 1) // limit if limit else 1
        offset = (page - 1) * limit
        tickets = list(qs[offset:offset + limit])
        now = timezone.now()
        at_risk_threshold = now + timedelta(hours=2)  # due within 2 hours = at risk
        resolved_statuses = {'resolved', 'closed', 'auto_resolved'}

        # Bulk count notes to avoid N+1 on the per-ticket serialization
        ticket_ids = [t.id for t in tickets]
        notes_count_map = {}
        if ticket_ids:
            from django.db.models import Count
            notes_count_map = dict(
                TicketNote.objects.filter(ticket_id__in=ticket_ids)
                .values_list('ticket_id')
                .annotate(c=Count('id'))
                .values_list('ticket_id', 'c')
            )

        def _ticket_row(t):
            is_snoozed = bool(t.snoozed_until and t.snoozed_until > now)
            row = {
                'id': t.id,
                'title': t.title,
                'description': t.description,
                'status': t.status,
                'priority': t.priority,
                'category': t.category,
                'auto_resolved': t.auto_resolved,
                'resolution': t.resolution,
                'created_at': t.created_at.isoformat(),
                'updated_at': t.updated_at.isoformat(),
                'resolved_at': t.resolved_at.isoformat() if t.resolved_at else None,
                'sla_due_at': t.sla_due_at.isoformat() if t.sla_due_at else None,
                'snoozed_until': t.snoozed_until.isoformat() if t.snoozed_until else None,
                'is_snoozed': is_snoozed,
                'sla_paused_at': t.sla_paused_at.isoformat() if t.sla_paused_at else None,
                'is_sla_paused': t.sla_paused_at is not None,
                'last_triaged_at': t.last_triaged_at.isoformat() if t.last_triaged_at else None,
                'notes_count': notes_count_map.get(t.id, 0),
                'intent': t.intent,
                'entities': t.entities,
            }
            # Aging: a paused or snoozed ticket cannot be "at risk" — its clock is not running
            if (t.sla_due_at and t.status not in resolved_statuses
                    and not is_snoozed and t.sla_paused_at is None):
                row['sla_breached'] = t.sla_due_at < now
                row['sla_at_risk'] = t.sla_due_at <= at_risk_threshold and t.sla_due_at >= now
            else:
                row['sla_breached'] = False
                row['sla_at_risk'] = False
            return row

        data = [_ticket_row(t) for t in tickets]
        return Response({
            'status': 'success',
            'data': data,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'total_pages': total_pages,
            },
        })
    except Exception as e:
        logger.exception("list_tickets failed")
        return Response(
            {'status': 'error', 'message': 'Failed to list tickets', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_tickets_aging(request):
    """List tickets that are SLA breached or at risk (due within 2 hours). Same scope as list_tickets."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        now = timezone.now()
        at_risk_threshold = now + timedelta(hours=2)
        resolved_statuses = {'resolved', 'closed', 'auto_resolved'}
        qs = Ticket.objects.filter(
            created_by=user,
            sla_due_at__isnull=False,
            sla_paused_at__isnull=True,  # paused tickets don't age
        ).exclude(status__in=resolved_statuses).order_by('sla_due_at')
        # Exclude snoozed tickets (snoozed_until in the future)
        qs = qs.filter(Q(snoozed_until__isnull=True) | Q(snoozed_until__lte=now))
        breached = [t for t in qs if t.sla_due_at < now]
        at_risk = [t for t in qs if t.sla_due_at >= now and t.sla_due_at <= at_risk_threshold]
        data = {
            'breached': [{'id': t.id, 'title': t.title, 'status': t.status, 'priority': t.priority, 'sla_due_at': t.sla_due_at.isoformat(), 'intent': t.intent, 'entities': t.entities} for t in breached],
            'at_risk': [{'id': t.id, 'title': t.title, 'status': t.status, 'priority': t.priority, 'sla_due_at': t.sla_due_at.isoformat(), 'intent': t.intent, 'entities': t.entities} for t in at_risk],
            'count_breached': len(breached),
            'count_at_risk': len(at_risk),
        }
        return Response({'status': 'success', 'data': data})
    except Exception as e:
        logger.exception("list_tickets_aging failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["PATCH", "PUT"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_ticket_task(request, ticket_id):
    """Update a ticket task (e.g. mark as resolved). Only own KB-gap tasks."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        ticket = Ticket.objects.filter(
            id=ticket_id,
            assigned_to=user,
            category='knowledge_gap',
        ).first()
        if not ticket:
            return Response(
                {'status': 'error', 'message': 'Ticket task not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))
        old_status = ticket.status
        if 'status' in data:
            ticket.status = data['status']
        if 'resolution' in data:
            ticket.resolution = data['resolution']
            if data.get('status') in ('resolved', 'closed'):
                ticket.resolved_at = timezone.now()
        ticket.save()
        if old_status != ticket.status:
            _run_notification_triggers(company_user.company_id, 'ticket_updated', ticket, old_status=old_status)
            # Workflow triggers for ticket_updated run via post_save signal (Frontline_agent.signals)
        return Response({
            'status': 'success',
            'data': {
                'id': ticket.id,
                'title': ticket.title,
                'status': ticket.status,
                'updated_at': ticket.updated_at.isoformat(),
            },
        })
    except Exception as e:
        logger.exception("update_ticket_task failed")
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ---------- Ticket lifecycle helpers (Phase 2 Batch 2) ----------

def _get_company_ticket_or_404(request, ticket_id):
    """Fetch a ticket that belongs to the caller's company. Returns (ticket, error_response)."""
    company_user = request.user
    company = company_user.company
    ticket = Ticket.objects.filter(id=ticket_id, company=company).first()
    if not ticket:
        return None, Response(
            {'status': 'error', 'message': 'Ticket not found'},
            status=status.HTTP_404_NOT_FOUND,
        )
    return ticket, None


def _serialize_note(n):
    return {
        'id': n.id,
        'body': n.body,
        'is_internal': n.is_internal,
        'author_id': n.author_id,
        'author_name': (n.author.get_full_name() or n.author.username) if n.author else None,
        'created_at': n.created_at.isoformat(),
        'updated_at': n.updated_at.isoformat(),
    }


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_ticket_notes(request, ticket_id):
    """List notes on a ticket (company-scoped)."""
    try:
        ticket, err = _get_company_ticket_or_404(request, ticket_id)
        if err:
            return err
        notes = ticket.notes.select_related('author').all()
        return Response({'status': 'success', 'data': [_serialize_note(n) for n in notes]})
    except Exception as e:
        logger.exception("list_ticket_notes failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_ticket_note(request, ticket_id):
    """Add an internal note to a ticket. Body: {body: str, is_internal?: bool}."""
    try:
        ticket, err = _get_company_ticket_or_404(request, ticket_id)
        if err:
            return err
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))
        body = (data.get('body') or '').strip()
        if not body:
            return Response({'status': 'error', 'message': 'body is required'}, status=status.HTTP_400_BAD_REQUEST)
        author = _get_or_create_user_for_company_user(request.user)
        note = TicketNote.objects.create(
            ticket=ticket,
            author=author,
            body=body,
            is_internal=bool(data.get('is_internal', True)),
        )
        return Response({'status': 'success', 'data': _serialize_note(note)}, status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.exception("create_ticket_note failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["PATCH", "DELETE"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_or_delete_ticket_note(request, ticket_id, note_id):
    """Edit or delete a note. Only the author can modify their own note."""
    try:
        ticket, err = _get_company_ticket_or_404(request, ticket_id)
        if err:
            return err
        author = _get_or_create_user_for_company_user(request.user)
        note = TicketNote.objects.filter(id=note_id, ticket=ticket).first()
        if not note:
            return Response({'status': 'error', 'message': 'Note not found'}, status=status.HTTP_404_NOT_FOUND)
        if note.author_id and note.author_id != author.id:
            return Response({'status': 'error', 'message': 'Only the note author can modify it'},
                            status=status.HTTP_403_FORBIDDEN)
        if request.method == 'DELETE':
            note.delete()
            return Response({'status': 'success'})
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))
        body = (data.get('body') or '').strip()
        if not body:
            return Response({'status': 'error', 'message': 'body is required'}, status=status.HTTP_400_BAD_REQUEST)
        note.body = body
        if 'is_internal' in data:
            note.is_internal = bool(data['is_internal'])
        note.save(update_fields=['body', 'is_internal', 'updated_at'])
        return Response({'status': 'success', 'data': _serialize_note(note)})
    except Exception as e:
        logger.exception("update_or_delete_ticket_note failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def snooze_ticket(request, ticket_id):
    """Snooze a ticket. Body accepts either:
    - {"snoozed_until": "2026-04-20T09:00:00Z"}  (ISO-8601)
    - {"hours": 24}  (snooze for N hours from now)
    """
    try:
        ticket, err = _get_company_ticket_or_404(request, ticket_id)
        if err:
            return err
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))
        until = None
        if data.get('snoozed_until'):
            try:
                from datetime import datetime
                raw = data['snoozed_until'].replace('Z', '+00:00')
                until = datetime.fromisoformat(raw)
                if until.tzinfo is None:
                    until = timezone.make_aware(until, timezone.utc)
            except Exception:
                return Response({'status': 'error', 'message': 'Invalid snoozed_until (ISO-8601 expected)'},
                                status=status.HTTP_400_BAD_REQUEST)
        elif data.get('hours') is not None:
            try:
                hours = float(data['hours'])
            except (TypeError, ValueError):
                return Response({'status': 'error', 'message': 'hours must be a number'},
                                status=status.HTTP_400_BAD_REQUEST)
            if hours <= 0 or hours > 24 * 90:  # cap at ~90 days
                return Response({'status': 'error', 'message': 'hours must be > 0 and <= 2160'},
                                status=status.HTTP_400_BAD_REQUEST)
            until = timezone.now() + timedelta(hours=hours)
        else:
            return Response({'status': 'error', 'message': 'snoozed_until or hours required'},
                            status=status.HTTP_400_BAD_REQUEST)
        if until <= timezone.now():
            return Response({'status': 'error', 'message': 'snoozed_until must be in the future'},
                            status=status.HTTP_400_BAD_REQUEST)
        ticket.snoozed_until = until
        ticket.save(update_fields=['snoozed_until', 'updated_at'])
        return Response({'status': 'success', 'data': {
            'id': ticket.id, 'snoozed_until': ticket.snoozed_until.isoformat(),
        }})
    except Exception as e:
        logger.exception("snooze_ticket failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def unsnooze_ticket(request, ticket_id):
    """Clear a ticket's snooze — it returns to the active queue immediately."""
    try:
        ticket, err = _get_company_ticket_or_404(request, ticket_id)
        if err:
            return err
        ticket.snoozed_until = None
        ticket.save(update_fields=['snoozed_until', 'updated_at'])
        return Response({'status': 'success', 'data': {'id': ticket.id, 'snoozed_until': None}})
    except Exception as e:
        logger.exception("unsnooze_ticket failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def pause_ticket_sla(request, ticket_id):
    """Pause the SLA clock (e.g. waiting on customer). Idempotent — re-pausing is a no-op."""
    try:
        ticket, err = _get_company_ticket_or_404(request, ticket_id)
        if err:
            return err
        if ticket.sla_paused_at is None:
            ticket.sla_paused_at = timezone.now()
            ticket.save(update_fields=['sla_paused_at', 'updated_at'])
        return Response({'status': 'success', 'data': {
            'id': ticket.id,
            'sla_paused_at': ticket.sla_paused_at.isoformat() if ticket.sla_paused_at else None,
            'sla_paused_accumulated_seconds': ticket.sla_paused_accumulated_seconds,
        }})
    except Exception as e:
        logger.exception("pause_ticket_sla failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def resume_ticket_sla(request, ticket_id):
    """Resume the SLA clock. Extends sla_due_at by the paused duration so the
    SLA target reflects actual working time, not calendar time."""
    try:
        ticket, err = _get_company_ticket_or_404(request, ticket_id)
        if err:
            return err
        if ticket.sla_paused_at is None:
            return Response({'status': 'success', 'data': {
                'id': ticket.id,
                'sla_paused_at': None,
                'sla_paused_accumulated_seconds': ticket.sla_paused_accumulated_seconds,
                'message': 'SLA was not paused',
            }})
        paused_for = (timezone.now() - ticket.sla_paused_at).total_seconds()
        paused_for = max(0, int(paused_for))
        ticket.sla_paused_accumulated_seconds = (ticket.sla_paused_accumulated_seconds or 0) + paused_for
        # Push the due date out by the paused duration so SLA math is preserved
        if ticket.sla_due_at:
            ticket.sla_due_at = ticket.sla_due_at + timedelta(seconds=paused_for)
        ticket.sla_paused_at = None
        ticket.save(update_fields=['sla_paused_at', 'sla_paused_accumulated_seconds', 'sla_due_at', 'updated_at'])
        return Response({'status': 'success', 'data': {
            'id': ticket.id,
            'sla_paused_at': None,
            'sla_paused_accumulated_seconds': ticket.sla_paused_accumulated_seconds,
            'sla_due_at': ticket.sla_due_at.isoformat() if ticket.sla_due_at else None,
            'paused_for_seconds': paused_for,
        }})
    except Exception as e:
        logger.exception("resume_ticket_sla failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([FrontlineLLMThrottle])
def retriage_ticket(request, ticket_id):
    """Re-run classification (category + priority + intent + entities) on a ticket.

    Typically called after the description has been updated. If the LLM suggests
    a different category/priority, the ticket is updated accordingly.
    """
    try:
        ticket, err = _get_company_ticket_or_404(request, ticket_id)
        if err:
            return err
        company = request.user.company
        agent = FrontlineAgent(company_id=company.id)
        llm_extraction = agent._extract_ticket_intent(ticket.title, ticket.description) or {}
        classification = agent.ticket_service.classify_ticket(ticket.title, ticket.description)

        old_category, old_priority = ticket.category, ticket.priority
        updated_fields = ['last_triaged_at', 'updated_at']

        valid_categories = {'technical', 'billing', 'account', 'feature_request', 'bug', 'other'}
        valid_priorities = {'low', 'medium', 'high', 'urgent'}

        suggested_cat = (llm_extraction.get('suggested_category')
                         or classification.get('category') or '').lower()
        suggested_pri = (llm_extraction.get('suggested_priority')
                         or classification.get('priority') or '').lower()

        if suggested_cat in valid_categories and suggested_cat != ticket.category:
            ticket.category = suggested_cat
            updated_fields.append('category')
        if suggested_pri in valid_priorities and suggested_pri != ticket.priority:
            ticket.priority = suggested_pri
            updated_fields.append('priority')
        if llm_extraction.get('intent'):
            ticket.intent = llm_extraction['intent']
            updated_fields.append('intent')
        if llm_extraction.get('entities'):
            ticket.entities = llm_extraction['entities']
            updated_fields.append('entities')

        ticket.last_triaged_at = timezone.now()
        ticket.save(update_fields=list(set(updated_fields)))

        return Response({'status': 'success', 'data': {
            'id': ticket.id,
            'old_category': old_category, 'new_category': ticket.category,
            'old_priority': old_priority, 'new_priority': ticket.priority,
            'intent': ticket.intent,
            'entities': ticket.entities,
            'last_triaged_at': ticket.last_triaged_at.isoformat(),
        }})
    except Exception as e:
        logger.exception("retriage_ticket failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([FrontlineLLMThrottle])
def create_ticket(request):
    """Create and process a support ticket"""
    try:
        company_user = request.user
        company = company_user.company
        user = _get_or_create_user_for_company_user(company_user)
        
        data = json.loads(request.body) if request.body else {}
        title = data.get('title', '').strip()
        description = data.get('description', '').strip() or data.get('message', '').strip()
        
        if not description:
            return Response(
                {'status': 'error', 'message': 'Description is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not title:
            title = description[:100] if description else 'Support Request'
        
        # Initialize agent with company_id
        agent = FrontlineAgent(company_id=company.id)
        result = agent.process_ticket(title, description, user.id)
        
        if not result.get('success', False):
            return Response(
                {'status': 'error', 'message': result.get('error', 'Failed to process ticket')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        ticket_id = result.get('ticket_id')
        if ticket_id:
            ticket = Ticket.objects.filter(id=ticket_id).first()
            if ticket:
                _run_notification_triggers(company.id, 'ticket_created', ticket)
                _run_workflow_triggers(company.id, 'ticket_created', ticket, user)
        return Response({
            'status': 'success',
            'data': result
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.exception("create_ticket failed")
        return Response(
            {'status': 'error', 'message': 'Failed to create ticket', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ---------- Frontline Knowledge QA Chats (persisted in DB) ----------

@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_qa_chats(request):
    """List all QA chats for the company user. Returns chats with messages."""
    try:
        company_user = request.user
        chats = FrontlineQAChat.objects.filter(company_user=company_user).order_by('-updated_at')[:50]
        result = []
        for chat in chats:
            messages = []
            for msg in chat.messages.order_by('created_at'):
                m = {'role': msg.role, 'content': msg.content}
                if msg.response_data:
                    m['responseData'] = msg.response_data
                messages.append(m)
            result.append({
                'id': str(chat.id),
                'title': chat.title or 'Chat',
                'messages': messages,
                'updatedAt': chat.updated_at.isoformat(),
                'timestamp': chat.updated_at.isoformat(),
            })
        return Response({'status': 'success', 'data': result})
    except Exception as e:
        logger.exception("list_qa_chats error")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_qa_chat(request):
    """Create a new QA chat with optional initial messages."""
    try:
        company_user = request.user
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body) if request.body else {})
        title = (data.get('title') or 'Chat')[:255]
        messages_data = data.get('messages') or []
        chat = FrontlineQAChat.objects.create(company_user=company_user, title=title)
        for m in messages_data:
            FrontlineQAChatMessage.objects.create(
                chat=chat,
                role=m.get('role', 'user'),
                content=m.get('content', ''),
                response_data=m.get('responseData'),
            )
        chat.refresh_from_db()
        messages = []
        for msg in chat.messages.order_by('created_at'):
            msg_dict = {'role': msg.role, 'content': msg.content}
            if msg.response_data:
                msg_dict['responseData'] = msg.response_data
            messages.append(msg_dict)
        return Response({
            'status': 'success',
            'data': {
                'id': str(chat.id),
                'title': chat.title,
                'messages': messages,
                'updatedAt': chat.updated_at.isoformat(),
                'timestamp': chat.updated_at.isoformat(),
            },
        })
    except Exception as e:
        logger.exception("create_qa_chat error")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["PATCH", "PUT"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_qa_chat(request, chat_id):
    """Update a QA chat: add messages, optionally update title."""
    try:
        company_user = request.user
        chat = FrontlineQAChat.objects.filter(company_user=company_user, id=chat_id).first()
        if not chat:
            return Response({'status': 'error', 'message': 'Chat not found.'}, status=status.HTTP_404_NOT_FOUND)
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body) if request.body else {})
        if data.get('title'):
            chat.title = str(data['title'])[:255]
            chat.save(update_fields=['title', 'updated_at'])
        messages_data = data.get('messages')
        if messages_data is not None:
            for m in messages_data:
                FrontlineQAChatMessage.objects.create(
                    chat=chat,
                    role=m.get('role', 'user'),
                    content=m.get('content', ''),
                    response_data=m.get('responseData'),
                )
        chat.refresh_from_db()
        messages = []
        for msg in chat.messages.order_by('created_at'):
            msg_dict = {'role': msg.role, 'content': msg.content}
            if msg.response_data:
                msg_dict['responseData'] = msg.response_data
            messages.append(msg_dict)
        return Response({
            'status': 'success',
            'data': {
                'id': str(chat.id),
                'title': chat.title,
                'messages': messages,
                'updatedAt': chat.updated_at.isoformat(),
                'timestamp': chat.updated_at.isoformat(),
            },
        })
    except Exception as e:
        logger.exception("update_qa_chat error")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["DELETE"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_qa_chat(request, chat_id):
    """Delete a QA chat and all its messages (CASCADE)."""
    try:
        company_user = request.user
        chat = FrontlineQAChat.objects.filter(company_user=company_user, id=chat_id).first()
        if not chat:
            return Response({'status': 'error', 'message': 'Chat not found.'}, status=status.HTTP_404_NOT_FOUND)
        chat.delete()
        return Response({'status': 'success', 'message': 'Chat deleted.'})
    except Exception as e:
        logger.exception("delete_qa_chat error")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------- Proactive Notifications (templates + schedule/send) ----------

def _render_template_body(body, context):
    """Replace {{key}} placeholders in body with context values."""
    if not body or not context:
        return body
    text = body
    for key, value in (context or {}).items():
        text = re.sub(r'\{\{\s*' + re.escape(str(key)) + r'\s*\}\}', str(value or ''), text, flags=re.IGNORECASE)
    return text


def _generate_llm_notification_body(template, context, company_id):
    """
    If the template has use_llm_personalization, generate a short personalized body via LLM.
    Returns the generated body string, or None to use the template body.
    """
    if not getattr(template, 'use_llm_personalization', False):
        return None
    try:
        agent = FrontlineAgent(company_id=company_id)
        result = agent.generate_notification_body(context, template_body_hint=template.body)
        return result
    except Exception as e:
        logger.warning("LLM notification body generation failed: %s", e)
        return None


def _send_notification_email(recipient_email, subject, body):
    """Send email via Django's email backend."""
    try:
        from django.core.mail import send_mail
        send_mail(
            subject=subject or 'Notification',
            message=body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
            recipient_list=[recipient_email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        logger.exception("Send notification email failed: %s", e)
        return False


def _build_unsubscribe_url(company_user_id, scope='email'):
    """Produce a public one-click unsubscribe URL. Requires SITE_URL (or BACKEND_URL)
    in settings so the link works from an email client."""
    from Frontline_agent.notification_utils import make_unsubscribe_token
    token = make_unsubscribe_token(company_user_id, scope)
    base = (getattr(settings, 'SITE_URL', '')
            or getattr(settings, 'BACKEND_URL', '')
            or '').rstrip('/')
    return f"{base}/api/frontline/unsubscribe/?t={token}"


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_notification_templates(request):
    """List notification templates for the company."""
    try:
        company = request.user.company
        qs = NotificationTemplate.objects.filter(company=company).order_by('-updated_at')
        data = [{'id': t.id, 'name': t.name, 'subject': t.subject, 'body': t.body, 'notification_type': t.notification_type, 'channel': t.channel, 'trigger_config': getattr(t, 'trigger_config', {}), 'use_llm_personalization': getattr(t, 'use_llm_personalization', False), 'created_at': t.created_at.isoformat(), 'updated_at': t.updated_at.isoformat()} for t in qs]
        return Response({'status': 'success', 'data': data})
    except Exception as e:
        logger.exception("list_notification_templates failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_notification_template(request):
    """Create a notification template."""
    try:
        company = request.user.company
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))
        name = (data.get('name') or '').strip()
        if not name:
            return Response({'status': 'error', 'message': 'name is required'}, status=status.HTTP_400_BAD_REQUEST)
        t = NotificationTemplate.objects.create(
            company=company,
            name=name,
            subject=(data.get('subject') or '')[:300],
            body=data.get('body') or '',
            notification_type=data.get('notification_type') or 'ticket_update',
            channel=data.get('channel') or 'email',
            use_llm_personalization=bool(data.get('use_llm_personalization', False)),
        )
        return Response({'status': 'success', 'data': {'id': t.id, 'name': t.name, 'subject': t.subject, 'body': t.body, 'notification_type': t.notification_type, 'channel': t.channel, 'use_llm_personalization': t.use_llm_personalization}})
    except Exception as e:
        logger.exception("create_notification_template failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_notification_template(request, template_id):
    """Get a single notification template."""
    try:
        company = request.user.company
        t = NotificationTemplate.objects.filter(company=company, id=template_id).first()
        if not t:
            return Response({'status': 'error', 'message': 'Template not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'status': 'success', 'data': {'id': t.id, 'name': t.name, 'subject': t.subject, 'body': t.body, 'notification_type': t.notification_type, 'channel': t.channel, 'trigger_config': getattr(t, 'trigger_config', {}), 'use_llm_personalization': getattr(t, 'use_llm_personalization', False)}})
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["PATCH", "PUT"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_notification_template(request, template_id):
    """Update a notification template."""
    try:
        company = request.user.company
        t = NotificationTemplate.objects.filter(company=company, id=template_id).first()
        if not t:
            return Response({'status': 'error', 'message': 'Template not found'}, status=status.HTTP_404_NOT_FOUND)
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))
        if 'name' in data:
            t.name = (data['name'] or '')[:200]
        if 'subject' in data:
            t.subject = (data['subject'] or '')[:300]
        if 'body' in data:
            t.body = data['body']
        if 'notification_type' in data:
            t.notification_type = data['notification_type']
        if 'channel' in data:
            t.channel = data['channel']
        if 'use_llm_personalization' in data:
            t.use_llm_personalization = bool(data['use_llm_personalization'])
        t.save()
        return Response({'status': 'success', 'data': {'id': t.id, 'name': t.name, 'subject': t.subject, 'body': t.body, 'use_llm_personalization': t.use_llm_personalization}})
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["DELETE"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_notification_template(request, template_id):
    """Delete a notification template."""
    try:
        company = request.user.company
        t = NotificationTemplate.objects.filter(company=company, id=template_id).first()
        if not t:
            return Response({'status': 'error', 'message': 'Template not found'}, status=status.HTTP_404_NOT_FOUND)
        t.delete()
        return Response({'status': 'success', 'message': 'Template deleted'})
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_notification_preferences(request):
    """Get current user's notification preferences. Creates default if missing."""
    try:
        company_user = request.user
        prefs, _ = FrontlineNotificationPreferences.objects.get_or_create(
            company_user=company_user,
            defaults={
                'email_enabled': True,
                'in_app_enabled': True,
                'ticket_created_email': True,
                'ticket_updated_email': True,
                'ticket_assigned_email': True,
                'workflow_email_enabled': True,
            },
        )
        data = {
            'email_enabled': prefs.email_enabled,
            'in_app_enabled': prefs.in_app_enabled,
            'ticket_created_email': prefs.ticket_created_email,
            'ticket_updated_email': prefs.ticket_updated_email,
            'ticket_assigned_email': prefs.ticket_assigned_email,
            'workflow_email_enabled': prefs.workflow_email_enabled,
            'timezone_name': prefs.timezone_name,
            'quiet_hours_enabled': prefs.quiet_hours_enabled,
            'quiet_hours_start': prefs.quiet_hours_start,
            'quiet_hours_end': prefs.quiet_hours_end,
            'updated_at': prefs.updated_at.isoformat(),
        }
        return Response({'status': 'success', 'data': data})
    except Exception as e:
        logger.exception("get_notification_preferences failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["PATCH", "PUT"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_notification_preferences(request):
    """Update current user's notification preferences."""
    try:
        company_user = request.user
        prefs, _ = FrontlineNotificationPreferences.objects.get_or_create(
            company_user=company_user,
            defaults={
                'email_enabled': True,
                'in_app_enabled': True,
                'ticket_created_email': True,
                'ticket_updated_email': True,
                'ticket_assigned_email': True,
                'workflow_email_enabled': True,
            },
        )
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))
        if 'email_enabled' in data:
            prefs.email_enabled = bool(data['email_enabled'])
        if 'in_app_enabled' in data:
            prefs.in_app_enabled = bool(data['in_app_enabled'])
        if 'ticket_created_email' in data:
            prefs.ticket_created_email = bool(data['ticket_created_email'])
        if 'ticket_updated_email' in data:
            prefs.ticket_updated_email = bool(data['ticket_updated_email'])
        if 'ticket_assigned_email' in data:
            prefs.ticket_assigned_email = bool(data['ticket_assigned_email'])
        if 'workflow_email_enabled' in data:
            prefs.workflow_email_enabled = bool(data['workflow_email_enabled'])
        # Quiet-hours controls
        if 'timezone_name' in data:
            tz_name = str(data['timezone_name'] or 'UTC').strip()[:64]
            prefs.timezone_name = tz_name or 'UTC'
        if 'quiet_hours_enabled' in data:
            prefs.quiet_hours_enabled = bool(data['quiet_hours_enabled'])
        if 'quiet_hours_start' in data:
            prefs.quiet_hours_start = str(data['quiet_hours_start'] or '22:00')[:5]
        if 'quiet_hours_end' in data:
            prefs.quiet_hours_end = str(data['quiet_hours_end'] or '08:00')[:5]
        prefs.save()
        return Response({
            'status': 'success',
            'data': {
                'email_enabled': prefs.email_enabled,
                'in_app_enabled': prefs.in_app_enabled,
                'ticket_created_email': prefs.ticket_created_email,
                'ticket_updated_email': prefs.ticket_updated_email,
                'ticket_assigned_email': prefs.ticket_assigned_email,
                'workflow_email_enabled': prefs.workflow_email_enabled,
                'timezone_name': prefs.timezone_name,
                'quiet_hours_enabled': prefs.quiet_hours_enabled,
                'quiet_hours_start': prefs.quiet_hours_start,
                'quiet_hours_end': prefs.quiet_hours_end,
                'updated_at': prefs.updated_at.isoformat(),
            },
        })
    except Exception as e:
        logger.exception("update_notification_preferences failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_scheduled_notifications(request):
    """List scheduled/sent notifications for the company with optional filters."""
    try:
        company = request.user.company
        qs = ScheduledNotification.objects.filter(company=company).order_by('-scheduled_at')
        status_filter = request.GET.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        limit = min(100, max(1, int(request.GET.get('limit', 50))))
        qs = qs[:limit]
        data = []
        for n in qs:
            data.append({
                'id': n.id, 'template_id': n.template_id, 'scheduled_at': n.scheduled_at.isoformat(),
                'status': n.status, 'recipient_email': n.recipient_email, 'related_ticket_id': n.related_ticket_id,
                'sent_at': n.sent_at.isoformat() if n.sent_at else None, 'error_message': n.error_message,
                'created_at': n.created_at.isoformat(),
            })
        return Response({'status': 'success', 'data': data})
    except Exception as e:
        logger.exception("list_scheduled_notifications failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def schedule_notification(request):
    """Schedule a notification (template + recipient + optional ticket + context)."""
    try:
        company = request.user.company
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))
        template_id = data.get('template_id')
        recipient_email = (data.get('recipient_email') or '').strip()
        scheduled_at_str = data.get('scheduled_at')
        ticket_id = data.get('ticket_id')
        context = data.get('context') or {}
        if not scheduled_at_str:
            return Response({'status': 'error', 'message': 'scheduled_at is required (ISO format)'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            scheduled_at = datetime.fromisoformat(scheduled_at_str.replace('Z', '+00:00'))
        except Exception:
            return Response({'status': 'error', 'message': 'Invalid scheduled_at format'}, status=status.HTTP_400_BAD_REQUEST)
        template = None
        if template_id:
            template = NotificationTemplate.objects.filter(company=company, id=template_id).first()
            if not template:
                return Response({'status': 'error', 'message': 'Template not found'}, status=status.HTTP_404_NOT_FOUND)
        related_ticket = None
        if ticket_id:
            user = _get_or_create_user_for_company_user(request.user)
            related_ticket = Ticket.objects.filter(id=ticket_id, created_by=user).first()
            if related_ticket:
                context.setdefault('ticket_id', related_ticket.id)
                context.setdefault('ticket_title', related_ticket.title)
                context.setdefault('resolution', related_ticket.resolution or '')
        n = ScheduledNotification.objects.create(
            company=company, template=template, scheduled_at=scheduled_at, status='pending',
            recipient_email=recipient_email or '', related_ticket=related_ticket, context=context,
        )
        return Response({'status': 'success', 'data': {'id': n.id, 'scheduled_at': n.scheduled_at.isoformat(), 'status': n.status}})
    except Exception as e:
        logger.exception("schedule_notification failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def send_notification_now(request):
    """Send a notification immediately (template + recipient + optional ticket + context)."""
    try:
        company = request.user.company
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))
        template_id = data.get('template_id')
        recipient_email = (data.get('recipient_email') or '').strip()
        ticket_id = data.get('ticket_id')
        context = data.get('context') or {}
        if not template_id:
            return Response({'status': 'error', 'message': 'template_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        template = NotificationTemplate.objects.filter(company=company, id=template_id).first()
        if not template:
            return Response({'status': 'error', 'message': 'Template not found'}, status=status.HTTP_404_NOT_FOUND)
        if not recipient_email:
            return Response({'status': 'error', 'message': 'recipient_email is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not _should_send_notification_to_recipient(company.id, recipient_email, template.channel, None):
            return Response({'status': 'skipped', 'message': 'Recipient has disabled notification emails.'}, status=status.HTTP_200_OK)
        related_ticket = None
        if ticket_id:
            user = _get_or_create_user_for_company_user(request.user)
            related_ticket = Ticket.objects.filter(id=ticket_id, created_by=user).first()
            if related_ticket:
                context.setdefault('ticket_id', related_ticket.id)
                context.setdefault('ticket_title', related_ticket.title)
                context.setdefault('resolution', related_ticket.resolution or '')

        # Quiet-hours: if the recipient is in a quiet window, queue it for the Celery
        # worker to deliver when the window closes rather than sending right now.
        from Frontline_agent.notification_utils import (
            get_recipient_preferences, in_quiet_hours, next_allowed_send_time,
        )
        prefs = get_recipient_preferences(company.id, recipient_email)
        now = timezone.now()
        if prefs and in_quiet_hours(prefs, now):
            deferred_until = next_allowed_send_time(prefs, now)
            n = ScheduledNotification.objects.create(
                company=company, template=template, scheduled_at=deferred_until,
                status='pending', recipient_email=recipient_email,
                related_ticket=related_ticket, context=context,
                next_retry_at=deferred_until, deferred_reason='quiet_hours',
            )
            return Response({
                'status': 'deferred',
                'message': 'Recipient is in quiet hours — queued for delivery.',
                'data': {'id': n.id, 'scheduled_at': deferred_until.isoformat(),
                         'reason': 'quiet_hours'},
            }, status=status.HTTP_202_ACCEPTED)

        if prefs:
            context.setdefault('unsubscribe_url', _build_unsubscribe_url(prefs.company_user_id))
        body = _render_template_body(template.body, context)
        personalized_body = _generate_llm_notification_body(template, context, company.id)
        if personalized_body:
            body = personalized_body
        subject = _render_template_body(template.subject, context)
        if template.channel == 'email':
            ok = _send_notification_email(recipient_email, subject, body)
        else:
            ok = False
            logger.warning("SMS/in_app send not implemented, logging only")
        if ok:
            n = ScheduledNotification.objects.create(
                company=company, template=template, scheduled_at=timezone.now(), status='sent',
                recipient_email=recipient_email, related_ticket=related_ticket, context=context, sent_at=timezone.now(),
            )
            return Response({'status': 'success', 'data': {'id': n.id, 'status': 'sent'}})
        n = ScheduledNotification.objects.create(
            company=company, template=template, scheduled_at=timezone.now(), status='failed',
            recipient_email=recipient_email, related_ticket=related_ticket, context=context, error_message='Send failed',
        )
        return Response({'status': 'error', 'message': 'Failed to send email'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        logger.exception("send_notification_now failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------- Notifications: preview / DLQ / retry / unsubscribe (Phase 2 Batch 3) ----------

@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def preview_notification_template(request, template_id):
    """Render a template with a sample context (no send, no DB write).
    Body: {context?: {...}}  — placeholders not present in context render as empty.
    Returns the resolved subject + body so admins can eyeball the output before saving."""
    try:
        company = request.user.company
        template = NotificationTemplate.objects.filter(id=template_id, company=company).first()
        if not template:
            return Response({'status': 'error', 'message': 'Template not found'}, status=status.HTTP_404_NOT_FOUND)
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))
        context = data.get('context') or {}
        # Friendly sample defaults for common placeholders so preview isn't all blank
        sample_defaults = {
            'ticket_id': 42,
            'ticket_title': 'Sample ticket title',
            'customer_name': 'Jane Customer',
            'resolution': 'This is a sample resolution body.',
            'recipient_email': 'sample@example.com',
            'unsubscribe_url': f"{(getattr(settings, 'SITE_URL', '') or '').rstrip('/')}/api/frontline/unsubscribe/?t=SAMPLE",
        }
        for k, v in sample_defaults.items():
            context.setdefault(k, v)
        return Response({'status': 'success', 'data': {
            'subject': _render_template_body(template.subject, context),
            'body': _render_template_body(template.body, context),
            'channel': template.channel,
            'context_used': context,
        }})
    except Exception as e:
        logger.exception("preview_notification_template failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_dead_lettered_notifications(request):
    """Return the dead-letter queue for this company (paged)."""
    try:
        company = request.user.company
        page = max(1, int(request.GET.get('page', 1)))
        limit = min(100, max(1, int(request.GET.get('limit', 20))))
        qs = ScheduledNotification.objects.filter(
            company=company, status='dead_lettered',
        ).order_by('-dead_lettered_at')
        total = qs.count()
        offset = (page - 1) * limit
        rows = [{
            'id': n.id,
            'recipient_email': n.recipient_email,
            'template_id': n.template_id,
            'template_name': n.template.name if n.template else None,
            'attempts': n.attempts,
            'max_attempts': n.max_attempts,
            'last_error': n.last_error,
            'scheduled_at': n.scheduled_at.isoformat() if n.scheduled_at else None,
            'dead_lettered_at': n.dead_lettered_at.isoformat() if n.dead_lettered_at else None,
            'related_ticket_id': n.related_ticket_id,
        } for n in qs[offset:offset + limit]]
        return Response({'status': 'success', 'data': rows, 'pagination': {
            'page': page, 'limit': limit, 'total': total,
            'total_pages': (total + limit - 1) // limit if limit else 1,
        }})
    except Exception as e:
        logger.exception("list_dead_lettered_notifications failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def retry_dead_lettered_notification(request, notification_id):
    """Move a dead-lettered or failed notification back to pending with a fresh attempts budget."""
    try:
        company = request.user.company
        n = ScheduledNotification.objects.filter(id=notification_id, company=company).first()
        if not n:
            return Response({'status': 'error', 'message': 'Notification not found'}, status=status.HTTP_404_NOT_FOUND)
        if n.status not in ('dead_lettered', 'failed'):
            return Response({'status': 'error', 'message': 'Only dead-lettered or failed notifications can be retried'},
                            status=status.HTTP_400_BAD_REQUEST)
        n.status = 'pending'
        n.attempts = 0
        n.next_retry_at = timezone.now()
        n.dead_lettered_at = None
        n.last_error = ''
        n.deferred_reason = ''
        n.save(update_fields=['status', 'attempts', 'next_retry_at',
                              'dead_lettered_at', 'last_error', 'deferred_reason'])
        return Response({'status': 'success', 'data': {'id': n.id, 'status': n.status}})
    except Exception as e:
        logger.exception("retry_dead_lettered_notification failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET", "POST"])
@permission_classes([])
@authentication_classes([])
@throttle_classes([FrontlinePublicThrottle])
def public_unsubscribe(request):
    """Public one-click unsubscribe endpoint. No auth — identifies the recipient
    by a signed token.

    GET  → return the recipient's current prefs (lightweight JSON confirmation page).
    POST → flip email_enabled to False and confirm.
    """
    try:
        from Frontline_agent.notification_utils import read_unsubscribe_token
        from Frontline_agent.models import FrontlineNotificationPreferences
        from core.models import CompanyUser

        token = (request.GET.get('t') or (request.data or {}).get('t') or '').strip()
        decoded = read_unsubscribe_token(token)
        if not decoded:
            return Response({'status': 'error', 'message': 'Invalid or expired unsubscribe link.'},
                            status=status.HTTP_400_BAD_REQUEST)
        company_user_id, scope = decoded

        company_user = CompanyUser.objects.filter(id=company_user_id, is_active=True).first()
        if not company_user:
            return Response({'status': 'error', 'message': 'Recipient not found.'},
                            status=status.HTTP_404_NOT_FOUND)

        prefs, _ = FrontlineNotificationPreferences.objects.get_or_create(company_user=company_user)

        if request.method == 'GET':
            return Response({'status': 'success', 'data': {
                'recipient_email': company_user.email,
                'email_enabled': prefs.email_enabled,
                'scope': scope,
                'message': ('You are currently opted IN to emails.'
                            if prefs.email_enabled else 'You are already unsubscribed.'),
            }})

        # POST: perform unsubscribe
        if scope == 'email':
            prefs.email_enabled = False
            prefs.save(update_fields=['email_enabled', 'updated_at'])
        # Reserved: other scopes (e.g. sms) could toggle other channels here.
        return Response({'status': 'success', 'data': {
            'recipient_email': company_user.email,
            'email_enabled': prefs.email_enabled,
            'message': 'You have been unsubscribed. It may take a few minutes for in-flight messages to stop.',
        }})
    except Exception as e:
        logger.exception("public_unsubscribe failed")
        return Response({'status': 'error', 'message': 'Failed to process unsubscribe'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------- Meetings (Phase 2 Batch 6) ----------


def _generate_jitsi_link():
    """Produce a fresh Jitsi Meet URL. Uses a long random slug so it's effectively
    unguessable for outsiders. Customers who prefer Zoom/Meet/Teams supply their
    own meeting_link in the create payload."""
    import secrets
    slug = f"fl-{secrets.token_urlsafe(12)}"
    return f"https://meet.jit.si/{slug}"


def _validate_meeting_link(raw):
    """Validate a meeting_link URL. Returns (clean_or_None, error_or_None).

    Rules: scheme must be http or https; netloc must be present; localhost +
    private ranges are allowed only when settings.DEBUG is True, since a link
    that points at 127.0.0.1 is almost always a misconfiguration in prod and a
    potential SSRF tripwire if any downstream code fetches the URL."""
    if raw in (None, ''):
        return None, None
    s = str(raw).strip()
    if len(s) > 2000:
        return None, 'meeting_link is too long (max 2000 chars)'
    try:
        from urllib.parse import urlparse
        p = urlparse(s)
    except Exception:
        return None, 'meeting_link is not a valid URL'
    if p.scheme not in ('http', 'https'):
        return None, "meeting_link must use http:// or https://"
    if not p.netloc:
        return None, 'meeting_link is missing a host'
    host = (p.hostname or '').lower()
    if not settings.DEBUG:
        blocked = {'localhost', '127.0.0.1', '0.0.0.0', '::1'}
        if host in blocked or host.endswith('.localhost') or host.startswith('169.254.'):
            return None, 'meeting_link host is not allowed'
    return s, None


def _serialize_meeting(m, include_transcript=False):
    row = {
        'id': m.id,
        'title': m.title,
        'description': m.description,
        'scheduled_at': m.scheduled_at.isoformat() if m.scheduled_at else None,
        'duration_minutes': m.duration_minutes,
        'timezone_name': m.timezone_name,
        'meeting_link': m.meeting_link,
        'location': m.location,
        'status': m.status,
        'organizer_id': m.organizer_id,
        'participant_user_ids': list(m.participants.values_list('id', flat=True)),
        'reminder_24h_sent_at': m.reminder_24h_sent_at.isoformat() if m.reminder_24h_sent_at else None,
        'reminder_15m_sent_at': m.reminder_15m_sent_at.isoformat() if m.reminder_15m_sent_at else None,
        'action_items': m.action_items or [],
        'notes': m.notes,
        'created_at': m.created_at.isoformat(),
        'updated_at': m.updated_at.isoformat(),
    }
    if include_transcript:
        row['transcript'] = m.transcript or ''
    return row


def _get_company_meeting_or_404(request, meeting_id):
    company = request.user.company
    m = FrontlineMeeting.objects.filter(id=meeting_id, company=company).first()
    if not m:
        return None, Response({'status': 'error', 'message': 'Meeting not found'},
                              status=status.HTTP_404_NOT_FOUND)
    return m, None


def _parse_iso_aware(raw):
    """Parse an ISO-8601 string to a tz-aware UTC datetime, or None."""
    if not raw:
        return None
    try:
        from datetime import datetime
        s = raw.replace('Z', '+00:00') if isinstance(raw, str) else raw
        dt = datetime.fromisoformat(s) if isinstance(s, str) else s
        if dt.tzinfo is None:
            dt = timezone.make_aware(dt, timezone.utc)
        return dt
    except Exception:
        return None


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_meetings(request):
    """List meetings for the caller's company.

    Query params: status, date_from, date_to (ISO-8601), organizer_id, page, limit.
    """
    try:
        company = request.user.company
        qs = FrontlineMeeting.objects.filter(company=company).order_by('-scheduled_at')

        st = request.GET.get('status')
        if st:
            qs = qs.filter(status=st)
        date_from = _parse_iso_aware(request.GET.get('date_from'))
        if date_from:
            qs = qs.filter(scheduled_at__gte=date_from)
        date_to = _parse_iso_aware(request.GET.get('date_to'))
        if date_to:
            qs = qs.filter(scheduled_at__lte=date_to)
        organizer_id = request.GET.get('organizer_id')
        if organizer_id:
            qs = qs.filter(organizer_id=organizer_id)

        page = max(1, int(request.GET.get('page', 1)))
        limit = min(100, max(1, int(request.GET.get('limit', 20))))
        total = qs.count()
        offset = (page - 1) * limit
        rows = [_serialize_meeting(m) for m in qs[offset:offset + limit]]
        return Response({'status': 'success', 'data': rows, 'pagination': {
            'page': page, 'limit': limit, 'total': total,
            'total_pages': (total + limit - 1) // limit if limit else 1,
        }})
    except Exception as e:
        logger.exception("list_meetings failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_meeting(request):
    """Create a meeting. If `meeting_link` is empty and `auto_jitsi` is not False,
    a fresh Jitsi link is auto-generated."""
    try:
        company_user = request.user
        company = company_user.company
        organizer = _get_or_create_user_for_company_user(company_user)
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))

        title = (data.get('title') or '').strip()
        scheduled_raw = data.get('scheduled_at')
        if not title or not scheduled_raw:
            return Response({'status': 'error', 'message': 'title and scheduled_at are required'},
                            status=status.HTTP_400_BAD_REQUEST)
        scheduled_at = _parse_iso_aware(scheduled_raw)
        if not scheduled_at:
            return Response({'status': 'error', 'message': 'Invalid scheduled_at (ISO-8601 expected)'},
                            status=status.HTTP_400_BAD_REQUEST)

        duration_minutes = max(5, min(24 * 60, int(data.get('duration_minutes') or 60)))
        meeting_link = (data.get('meeting_link') or '').strip()
        auto_jitsi = bool(data.get('auto_jitsi', True))
        if meeting_link:
            clean, err_msg = _validate_meeting_link(meeting_link)
            if err_msg:
                return Response({'status': 'error', 'message': err_msg},
                                status=status.HTTP_400_BAD_REQUEST)
            meeting_link = clean
        elif auto_jitsi:
            meeting_link = _generate_jitsi_link()
        tz_name = (data.get('timezone_name') or 'UTC').strip()[:64] or 'UTC'

        m = FrontlineMeeting.objects.create(
            title=title[:200],
            description=data.get('description') or '',
            company=company,
            organizer=organizer,
            scheduled_at=scheduled_at,
            duration_minutes=duration_minutes,
            timezone_name=tz_name,
            meeting_link=meeting_link or None,
            location=(data.get('location') or '')[:500],
            status='scheduled',
        )

        # Participants: accept either company_user_ids (preferred) or participant_user_ids (raw User ids).
        company_user_ids = data.get('participant_company_user_ids') or []
        user_ids = list(data.get('participant_user_ids') or [])
        if company_user_ids:
            for cuid in company_user_ids:
                cu = CompanyUser.objects.filter(id=cuid, company=company, is_active=True).first()
                if cu:
                    user_ids.append(_get_or_create_user_for_company_user(cu).id)
        if user_ids:
            from django.contrib.auth.models import User as _User
            m.participants.set(_User.objects.filter(id__in=set(user_ids)))

        return Response({'status': 'success', 'data': _serialize_meeting(m)},
                        status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.exception("create_meeting failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_meeting(request, meeting_id):
    """Get a single meeting (includes transcript)."""
    try:
        m, err = _get_company_meeting_or_404(request, meeting_id)
        if err:
            return err
        return Response({'status': 'success', 'data': _serialize_meeting(m, include_transcript=True)})
    except Exception as e:
        logger.exception("get_meeting failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["PATCH"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_meeting(request, meeting_id):
    """Update meeting fields. Re-sending a reminder after edit is signalled by the
    caller via clearing reminder_24h_sent_at / reminder_15m_sent_at."""
    try:
        m, err = _get_company_meeting_or_404(request, meeting_id)
        if err:
            return err
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))

        if 'title' in data:
            m.title = str(data['title'])[:200]
        if 'description' in data:
            m.description = str(data['description'])
        if 'scheduled_at' in data:
            dt = _parse_iso_aware(data['scheduled_at'])
            if not dt:
                return Response({'status': 'error', 'message': 'Invalid scheduled_at'},
                                status=status.HTTP_400_BAD_REQUEST)
            m.scheduled_at = dt
            # Schedule change → reset reminder flags so Celery will re-send.
            m.reminder_24h_sent_at = None
            m.reminder_15m_sent_at = None
        if 'duration_minutes' in data:
            try:
                m.duration_minutes = max(5, min(24 * 60, int(data['duration_minutes'])))
            except (TypeError, ValueError):
                pass
        if 'timezone_name' in data:
            m.timezone_name = str(data['timezone_name'])[:64] or 'UTC'
        if 'meeting_link' in data:
            raw = (str(data['meeting_link']) or '').strip()
            if raw:
                clean, err_msg = _validate_meeting_link(raw)
                if err_msg:
                    return Response({'status': 'error', 'message': err_msg},
                                    status=status.HTTP_400_BAD_REQUEST)
                m.meeting_link = clean
            else:
                m.meeting_link = None
        if 'location' in data:
            m.location = str(data['location'])[:500]
        if 'status' in data:
            valid = {c[0] for c in FrontlineMeeting.STATUS_CHOICES}
            if data['status'] in valid:
                m.status = data['status']
        if 'notes' in data:
            m.notes = str(data['notes'])
        if 'transcript' in data:
            m.transcript = str(data['transcript'])

        m.save()

        if 'participant_company_user_ids' in data:
            company = request.user.company
            user_ids = []
            for cuid in data['participant_company_user_ids']:
                cu = CompanyUser.objects.filter(id=cuid, company=company, is_active=True).first()
                if cu:
                    user_ids.append(_get_or_create_user_for_company_user(cu).id)
            from django.contrib.auth.models import User as _User
            m.participants.set(_User.objects.filter(id__in=set(user_ids)))

        return Response({'status': 'success', 'data': _serialize_meeting(m)})
    except Exception as e:
        logger.exception("update_meeting failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["DELETE"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_meeting(request, meeting_id):
    """Delete a meeting."""
    try:
        m, err = _get_company_meeting_or_404(request, meeting_id)
        if err:
            return err
        m.delete()
        return Response({'status': 'success'})
    except Exception as e:
        logger.exception("delete_meeting failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def check_meeting_availability(request):
    """Check whether a candidate meeting slot conflicts with existing meetings for
    any of the listed participants.

    Query params:
      start             ISO-8601, required
      duration_minutes  default 60
      participant_company_user_ids   comma-separated company-user IDs

    Returns: {available: bool, conflicts: [{meeting_id, user_id, scheduled_at, title}]}.
    """
    try:
        company = request.user.company
        start = _parse_iso_aware(request.GET.get('start'))
        if not start:
            return Response({'status': 'error', 'message': 'Valid start (ISO-8601) is required'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            duration = max(5, min(24 * 60, int(request.GET.get('duration_minutes', 60))))
        except (TypeError, ValueError):
            duration = 60
        end = start + timedelta(minutes=duration)

        cu_ids = [int(x) for x in (request.GET.get('participant_company_user_ids', '') or '').split(',') if x.strip().isdigit()]
        user_ids = []
        for cuid in cu_ids:
            cu = CompanyUser.objects.filter(id=cuid, company=company, is_active=True).first()
            if cu:
                user_ids.append(_get_or_create_user_for_company_user(cu).id)
        if not user_ids:
            return Response({'status': 'success', 'data': {'available': True, 'conflicts': []}})

        # Find meetings in the same company that overlap [start, end) and involve any of the users
        # (either as organizer or as participant).
        from django.db.models import Q as _Q
        candidates = FrontlineMeeting.objects.filter(
            company=company,
            status__in=['scheduled', 'rescheduled'],
            scheduled_at__lt=end,
        ).filter(_Q(organizer_id__in=user_ids) | _Q(participants__id__in=user_ids)).distinct()

        conflicts = []
        for m in candidates:
            m_end = m.scheduled_at + timedelta(minutes=(m.duration_minutes or 60))
            if m_end > start:  # overlap
                # Which user(s) clash?
                involved = set()
                if m.organizer_id in user_ids:
                    involved.add(m.organizer_id)
                involved.update(m.participants.filter(id__in=user_ids).values_list('id', flat=True))
                for uid in involved:
                    conflicts.append({
                        'meeting_id': m.id,
                        'user_id': uid,
                        'scheduled_at': m.scheduled_at.isoformat(),
                        'duration_minutes': m.duration_minutes,
                        'title': m.title,
                    })

        return Response({'status': 'success', 'data': {
            'available': not conflicts,
            'conflicts': conflicts,
        }})
    except Exception as e:
        logger.exception("check_meeting_availability failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([FrontlineLLMThrottle])
def extract_meeting_action_items(request, meeting_id):
    """Extract action items from the meeting's transcript using the LLM.

    Stores the list on `meeting.action_items`. Optional body: {create_tickets: bool}
    — when true, each extracted item also becomes a frontline Ticket so an agent can
    act on it and track SLA."""
    try:
        company = request.user.company
        m, err = _get_company_meeting_or_404(request, meeting_id)
        if err:
            return err
        transcript = (m.transcript or '').strip()
        if not transcript:
            return Response({'status': 'error', 'message': 'Meeting has no transcript to extract from'},
                            status=status.HTTP_400_BAD_REQUEST)

        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))
        create_tickets = bool(data.get('create_tickets', False))

        # Single cheap LLM call. Strict JSON output; best-effort parse.
        agent = FrontlineAgent(company_id=company.id)
        prompt = (
            "From the meeting transcript delimited by <transcript>, extract a list of concrete "
            "action items. Each item must be something someone agreed to do. Return ONLY a JSON "
            "array, no markdown. Each item: {\"text\": string, \"owner_name\": string|null, "
            "\"due_date\": \"YYYY-MM-DD\"|null}. Return at most 15 items.\n\n"
            f"<transcript>\n{transcript[:12000]}\n</transcript>"
        )
        raw = agent._call_llm(
            prompt=prompt,
            system_prompt="You extract structured action items from meeting transcripts. Output valid JSON only.",
            temperature=0.2,
            max_tokens=900,
        )
        items = []
        if raw:
            s = raw.strip()
            if s.startswith('```'):
                s = s.split('```', 2)[1]
                if s.startswith('json'):
                    s = s[4:]
                s = s.strip('` \n')
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    items = [{
                        'text': str(it.get('text') or '')[:500],
                        'owner_name': (str(it.get('owner_name')) if it.get('owner_name') else None),
                        'due_date': (str(it.get('due_date')) if it.get('due_date') else None),
                    } for it in parsed if isinstance(it, dict) and it.get('text')]
            except Exception as exc:
                logger.warning("Action-item LLM output unparseable: %s; raw=%r", exc, raw[:200])

        m.action_items = items
        m.save(update_fields=['action_items', 'updated_at'])

        created_ticket_ids = []
        if create_tickets and items:
            creator = _get_or_create_user_for_company_user(request.user)
            for it in items:
                t = Ticket.objects.create(
                    title=f"[Meeting follow-up] {it['text'][:160]}",
                    description=(f"Action item from meeting '{m.title}' on "
                                 f"{m.scheduled_at.isoformat() if m.scheduled_at else '(unknown date)'}\n\n"
                                 f"Text: {it['text']}\n"
                                 f"Owner: {it.get('owner_name') or 'Unassigned'}\n"
                                 f"Due: {it.get('due_date') or 'None'}"),
                    status='open',
                    priority='medium',
                    category='other',
                    company=company,
                    created_by=creator,
                )
                created_ticket_ids.append(t.id)
                it['ticket_id'] = t.id
            # Save again with ticket_id references baked in.
            m.action_items = items
            m.save(update_fields=['action_items', 'updated_at'])

        return Response({'status': 'success', 'data': {
            'meeting_id': m.id,
            'action_items': items,
            'count': len(items),
            'created_ticket_ids': created_ticket_ids,
        }})
    except Exception as e:
        logger.exception("extract_meeting_action_items failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------- Workflow / SOP Runner ----------


def _run_single_step(step, step_index, step_path, workflow, context_data, simulate):
    """Execute a single non-branch step. Returns (ok, result_entry, fatal_error_str_or_None).

    `simulate=True` reports what would happen without any side effects — no emails,
    no webhooks, no DB writes.
    """
    step_type = (step.get('type') or '').lower()
    base = {'step': step_index, 'step_path': step_path, 'type': step_type}

    if step_type == 'send_email':
        template_id = step.get('template_id')
        raw_recipient = (step.get('recipient_email') or context_data.get('recipient_email') or '{{recipient_email}}').strip()
        recipient = _render_template_body(raw_recipient, context_data).strip()
        if not (template_id and recipient):
            return False, {**base, 'done': False, 'error': 'Missing template_id or recipient'}, None
        template = NotificationTemplate.objects.filter(id=template_id).first()
        if not template:
            return False, {**base, 'done': False, 'error': 'Template not found'}, None
        if not _should_send_notification_to_recipient(workflow.company_id, recipient, 'email', None):
            return True, {**base, 'done': True, 'skipped': 'recipient_preferences'}, None
        if simulate:
            return True, {**base, 'done': True, 'simulated': True, 'recipient': recipient,
                          'template_id': template_id}, None
        merged = {**context_data, **step.get('context', {})}
        body = _render_template_body(template.body, merged)
        personalized_body = _generate_llm_notification_body(template, merged, workflow.company_id)
        if personalized_body:
            body = personalized_body
        subject = _render_template_body(template.subject, merged)
        ok = _send_notification_email(recipient, subject, body)
        if not ok:
            return False, {**base, 'done': False, 'error': 'Email send failed'}, None
        return True, {**base, 'done': True}, None

    if step_type == 'update_ticket':
        ticket_id = context_data.get('ticket_id') or step.get('ticket_id')
        if not ticket_id:
            return False, {**base, 'done': False, 'error': 'Missing ticket_id'}, None
        if simulate:
            return True, {**base, 'done': True, 'simulated': True, 'ticket_id': ticket_id,
                          'would_set': {k: step[k] for k in ('status', 'resolution') if k in step}}, None
        ticket = Ticket.objects.filter(id=ticket_id).first()
        if not ticket:
            return False, {**base, 'done': False, 'error': 'Ticket not found'}, None
        if 'status' in step:
            ticket.status = step['status']
        if 'resolution' in step:
            ticket.resolution = step['resolution']
        ticket.save()
        return True, {**base, 'done': True}, None

    if step_type in ('webhook', 'http_webhook'):
        url = (step.get('url') or '').strip()
        if not url:
            return False, {**base, 'done': False, 'error': 'Missing url'}, None
        method = (step.get('method') or 'POST').upper()
        if simulate:
            return True, {**base, 'done': True, 'simulated': True, 'url': url, 'method': method}, None
        merged = {**context_data, **step.get('context', {})}
        body_raw = step.get('body') or '{}'
        try:
            body_str = _render_template_body(body_raw, merged) if isinstance(body_raw, str) else json.dumps(body_raw)
            payload = body_str.encode('utf-8') if body_str else b''
        except Exception:
            payload = b'{}'
        headers = dict(step.get('headers') or {})
        if payload and 'Content-Type' not in {h.lower() for h in headers}:
            headers['Content-Type'] = 'application/json'
        req = Request(url, data=payload if method != 'GET' else None, method=method, headers=headers)
        try:
            with urlopen(req, timeout=int(step.get('timeout_seconds', 30))) as resp:
                status_code = resp.status
            if status_code >= 400:
                return False, {**base, 'done': False, 'status_code': status_code,
                               'error': f'HTTP {status_code}'}, None
            return True, {**base, 'done': True, 'status_code': status_code}, None
        except (URLError, HTTPError, OSError) as e:
            return False, {**base, 'done': False, 'error': str(e)}, None

    if step_type == 'slack':
        webhook_url = (step.get('webhook_url') or '').strip()
        if not webhook_url:
            return False, {**base, 'done': False, 'error': 'Missing webhook_url'}, None
        if simulate:
            return True, {**base, 'done': True, 'simulated': True, 'webhook_url': webhook_url}, None
        merged = {**context_data, **step.get('context', {})}
        text = _render_template_body(step.get('text') or 'Workflow step executed.', merged)
        payload = json.dumps({'text': text}).encode('utf-8')
        req = Request(webhook_url, data=payload, method='POST', headers={'Content-Type': 'application/json'})
        try:
            with urlopen(req, timeout=15) as resp:
                status_code = resp.status
            return True, {**base, 'done': True, 'status_code': status_code}, None
        except (URLError, HTTPError, OSError) as e:
            return False, {**base, 'done': False, 'error': str(e)}, None

    if step_type == 'assign':
        ticket_id = context_data.get('ticket_id') or step.get('ticket_id')
        assign_to_company_user_id = step.get('assign_to_company_user_id')
        if not (ticket_id and assign_to_company_user_id is not None):
            return False, {**base, 'done': False, 'error': 'Missing ticket_id or assign_to_company_user_id'}, None
        if simulate:
            return True, {**base, 'done': True, 'simulated': True,
                          'ticket_id': ticket_id, 'assignee': assign_to_company_user_id}, None
        ticket = Ticket.objects.filter(id=ticket_id).first()
        company_user = CompanyUser.objects.filter(
            id=assign_to_company_user_id, company=workflow.company, is_active=True,
        ).first()
        if not (ticket and company_user):
            return False, {**base, 'done': False, 'error': 'Ticket or assignee not found'}, None
        assign_user = _get_or_create_user_for_company_user(company_user)
        ticket.assigned_to = assign_user
        ticket.save()
        return True, {**base, 'done': True}, None

    if step_type in ('wait', 'wait_for_duration'):
        # Cap at 300s per step to avoid stuck workers. For long waits use an external scheduler.
        seconds = max(0, min(300, int(step.get('seconds') or 0)))
        if simulate:
            return True, {**base, 'done': True, 'simulated': True, 'seconds': seconds}, None
        if seconds > 0:
            import time as _t
            _t.sleep(seconds)
        return True, {**base, 'done': True, 'waited_seconds': seconds}, None

    # Unknown step types are no-ops (forward-compat)
    return True, {**base, 'done': True, 'note': 'unknown step type treated as no-op'}, None


def _execute_step_list(steps, workflow, context_data, simulate, start_monotonic, timeout, path_prefix=''):
    """Walk a list of steps linearly. Handles `branch` recursively. Enforces the
    workflow timeout by checking monotonic time between steps.

    Returns (success_bool, result_list, fatal_error_str_or_None).
    """
    import time as _t
    from Frontline_agent.workflow_conditions import evaluate as _eval_cond

    results = []
    for i, step in enumerate(steps or []):
        step_path = f"{path_prefix}{i}"
        step_type = (step.get('type') or '').lower()

        # Timeout check before each step — don't bother starting if we're already past budget.
        if timeout and (_t.monotonic() - start_monotonic) > timeout:
            results.append({'step': i, 'step_path': step_path, 'type': step_type,
                            'done': False, 'error': 'workflow_timeout'})
            return False, results, 'workflow_timeout'

        if step_type == 'branch':
            cond = step.get('condition')
            branch_taken = 'if_true' if _eval_cond(cond, context_data) else 'if_false'
            nested = step.get(branch_taken) or []
            results.append({'step': i, 'step_path': step_path, 'type': 'branch',
                            'done': True, 'branch_taken': branch_taken, 'nested_count': len(nested)})
            nested_ok, nested_results, nested_err = _execute_step_list(
                nested, workflow, context_data, simulate, start_monotonic, timeout,
                path_prefix=f"{step_path}.{branch_taken}.",
            )
            results.extend(nested_results)
            if not nested_ok:
                return False, results, nested_err
            continue

        # Regular step — run with per-step retry configuration.
        retries = max(0, min(5, int(step.get('retries', 0))))
        backoff_seconds = max(0, min(300, int(step.get('backoff_seconds', 5))))
        attempt = 0
        while True:
            attempt += 1
            ok, result_entry, fatal = _run_single_step(step, i, step_path, workflow, context_data, simulate)
            result_entry['attempt'] = attempt
            if ok:
                results.append(result_entry)
                break
            if attempt > retries:
                results.append(result_entry)
                # A failed non-retryable step aborts the run so downstream steps don't
                # fire on a broken precondition. Branch steps are the only way to
                # "continue on failure" — users can wrap this step in a branch.
                return False, results, result_entry.get('error', 'step_failed')
            if timeout and (_t.monotonic() - start_monotonic) > timeout:
                results.append({**result_entry, 'error': 'workflow_timeout'})
                return False, results, 'workflow_timeout'
            if simulate:
                # In dry-run we don't actually wait; just note the retry would happen.
                results.append({**result_entry, 'would_retry_in_seconds': backoff_seconds})
                continue
            if backoff_seconds:
                import time as _t2
                _t2.sleep(backoff_seconds)

    return True, results, None


def _execute_workflow_steps(workflow, context_data, user, simulate=False):
    """Execute a workflow's steps. Returns (success, result_data, error_message).

    Honours `workflow.timeout_seconds` (0 = unlimited), per-step retries with
    backoff, and a recursive `branch` step type. Pass `simulate=True` to run a
    dry-run that produces the same report shape without side effects.
    """
    import time as _t
    steps = workflow.steps or []
    timeout = int(getattr(workflow, 'timeout_seconds', 0) or 0)
    start = _t.monotonic()
    ok, results, err = _execute_step_list(
        steps, workflow, context_data, simulate, start, timeout,
    )
    return ok, {'steps_completed': sum(1 for r in results if r.get('done')),
                'results': results, 'simulated': simulate,
                'elapsed_seconds': round(_t.monotonic() - start, 3)}, err


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_workflows(request):
    """List workflows for the company."""
    try:
        company = request.user.company
        qs = FrontlineWorkflow.objects.filter(company=company).order_by('-updated_at')
        data = [{
            'id': w.id, 'name': w.name, 'description': w.description,
            'trigger_conditions': w.trigger_conditions, 'steps': w.steps,
            'is_active': w.is_active, 'requires_approval': w.requires_approval,
            'timeout_seconds': getattr(w, 'timeout_seconds', 0) or 0,
            'version': w.version,
            'created_at': w.created_at.isoformat(), 'updated_at': w.updated_at.isoformat(),
        } for w in qs]
        return Response({'status': 'success', 'data': data})
    except Exception as e:
        logger.exception("list_workflows failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_workflow(request):
    """Create a workflow."""
    try:
        company = request.user.company
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))
        name = (data.get('name') or '').strip()
        if not name:
            return Response({'status': 'error', 'message': 'name is required'}, status=status.HTTP_400_BAD_REQUEST)
        w = FrontlineWorkflow.objects.create(
            company=company, name=name, description=data.get('description') or '',
            trigger_conditions=data.get('trigger_conditions') or {}, steps=data.get('steps') or [], is_active=data.get('is_active', True),
        )
        return Response({'status': 'success', 'data': {'id': w.id, 'name': w.name, 'steps': w.steps}})
    except Exception as e:
        logger.exception("create_workflow failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_workflow(request, workflow_id):
    """Get a single workflow."""
    try:
        company = request.user.company
        w = FrontlineWorkflow.objects.filter(company=company, id=workflow_id).first()
        if not w:
            return Response({'status': 'error', 'message': 'Workflow not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'status': 'success', 'data': {
            'id': w.id, 'name': w.name, 'description': w.description,
            'trigger_conditions': w.trigger_conditions, 'steps': w.steps,
            'is_active': w.is_active,
            'requires_approval': w.requires_approval,
            'timeout_seconds': getattr(w, 'timeout_seconds', 0) or 0,
            'version': w.version,
        }})
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _snapshot_workflow(w, saved_by=None):
    """Create an immutable FrontlineWorkflowVersion from the current workflow state."""
    FrontlineWorkflowVersion.objects.create(
        workflow=w,
        version=w.version or 1,
        snapshot={
            'name': w.name,
            'description': w.description,
            'trigger_conditions': w.trigger_conditions,
            'steps': w.steps,
            'requires_approval': w.requires_approval,
            'is_active': w.is_active,
            'timeout_seconds': getattr(w, 'timeout_seconds', 0) or 0,
        },
        saved_by=saved_by,
    )


@api_view(["PATCH", "PUT"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_workflow(request, workflow_id):
    """Update a workflow. Snapshots the previous state to FrontlineWorkflowVersion
    before applying changes so rollback is always available."""
    try:
        company = request.user.company
        w = FrontlineWorkflow.objects.filter(company=company, id=workflow_id).first()
        if not w:
            return Response({'status': 'error', 'message': 'Workflow not found'}, status=status.HTTP_404_NOT_FOUND)
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))

        # Snapshot the current state before mutating so we can roll back.
        user = _get_or_create_user_for_company_user(request.user)
        _snapshot_workflow(w, saved_by=user)

        if 'name' in data:
            w.name = (data['name'] or '')[:200]
        if 'description' in data:
            w.description = data['description']
        if 'trigger_conditions' in data:
            w.trigger_conditions = data['trigger_conditions']
        if 'steps' in data:
            w.steps = data['steps']
        if 'is_active' in data:
            w.is_active = bool(data['is_active'])
        if 'requires_approval' in data:
            w.requires_approval = bool(data['requires_approval'])
        if 'timeout_seconds' in data:
            try:
                ts = int(data['timeout_seconds'] or 0)
            except (TypeError, ValueError):
                ts = 0
            w.timeout_seconds = max(0, min(3600, ts))  # cap 1 hour
        w.version = (w.version or 1) + 1
        w.save()
        return Response({'status': 'success', 'data': {
            'id': w.id, 'name': w.name, 'version': w.version,
        }})
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_workflow_versions(request, workflow_id):
    """List historical versions of a workflow (most recent first)."""
    try:
        company = request.user.company
        w = FrontlineWorkflow.objects.filter(company=company, id=workflow_id).first()
        if not w:
            return Response({'status': 'error', 'message': 'Workflow not found'}, status=status.HTTP_404_NOT_FOUND)
        versions = w.versions.select_related('saved_by').order_by('-version')[:100]
        return Response({'status': 'success', 'data': [{
            'id': v.id,
            'version': v.version,
            'created_at': v.created_at.isoformat(),
            'saved_by_id': v.saved_by_id,
            'saved_by_name': (v.saved_by.get_full_name() or v.saved_by.username) if v.saved_by else None,
            'snapshot': v.snapshot,
        } for v in versions]})
    except Exception as e:
        logger.exception("list_workflow_versions failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def rollback_workflow(request, workflow_id, version):
    """Rollback a workflow to a previous version. The current state is snapshotted
    first so rollback itself is reversible."""
    try:
        company = request.user.company
        w = FrontlineWorkflow.objects.filter(company=company, id=workflow_id).first()
        if not w:
            return Response({'status': 'error', 'message': 'Workflow not found'}, status=status.HTTP_404_NOT_FOUND)
        v = w.versions.filter(version=int(version)).first()
        if not v:
            return Response({'status': 'error', 'message': 'Version not found'}, status=status.HTTP_404_NOT_FOUND)
        user = _get_or_create_user_for_company_user(request.user)
        _snapshot_workflow(w, saved_by=user)
        snap = v.snapshot or {}
        w.name = snap.get('name', w.name)
        w.description = snap.get('description', w.description)
        w.trigger_conditions = snap.get('trigger_conditions', w.trigger_conditions)
        w.steps = snap.get('steps', w.steps)
        w.requires_approval = snap.get('requires_approval', w.requires_approval)
        w.is_active = snap.get('is_active', w.is_active)
        w.timeout_seconds = snap.get('timeout_seconds', getattr(w, 'timeout_seconds', 0))
        w.version = (w.version or 1) + 1
        w.save()
        return Response({'status': 'success', 'data': {
            'id': w.id, 'version': w.version, 'rolled_back_to_version': v.version,
        }})
    except Exception as e:
        logger.exception("rollback_workflow failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def dry_run_workflow(request, workflow_id):
    """Simulate a workflow execution with a given context. Side-effect-free: no emails,
    webhooks, or DB writes. Returns the same result_data shape with `simulated: true`
    entries showing what *would* happen."""
    try:
        company = request.user.company
        user = _get_or_create_user_for_company_user(request.user)
        w = FrontlineWorkflow.objects.filter(company=company, id=workflow_id).first()
        if not w:
            return Response({'status': 'error', 'message': 'Workflow not found'}, status=status.HTTP_404_NOT_FOUND)
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))
        context_data = data.get('context') or {}
        success, result_data, err = _execute_workflow_steps(w, context_data, user, simulate=True)
        return Response({'status': 'success', 'data': {
            'workflow_id': w.id, 'simulated': True,
            'success': success, 'error': err, 'result_data': result_data,
        }})
    except Exception as e:
        logger.exception("dry_run_workflow failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["DELETE"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_workflow(request, workflow_id):
    """Delete a workflow."""
    try:
        company = request.user.company
        w = FrontlineWorkflow.objects.filter(company=company, id=workflow_id).first()
        if not w:
            return Response({'status': 'error', 'message': 'Workflow not found'}, status=status.HTTP_404_NOT_FOUND)
        w.delete()
        return Response({'status': 'success', 'message': 'Workflow deleted'})
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def execute_workflow(request, workflow_id):
    """Execute a workflow with context (e.g. ticket_id, recipient_email)."""
    try:
        company = request.user.company
        user = _get_or_create_user_for_company_user(request.user)
        w = FrontlineWorkflow.objects.filter(company=company, id=workflow_id, is_active=True).first()
        if not w:
            return Response({'status': 'error', 'message': 'Workflow not found or inactive'}, status=status.HTTP_404_NOT_FOUND)
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))
        context_data = data.get('context') or {}
        exec_obj = FrontlineWorkflowExecution.objects.create(
            workflow=w, workflow_name=w.name, workflow_description=w.description, executed_by=user, status='in_progress', context_data=context_data,
        )
        success, result_data, err = _execute_workflow_steps(w, context_data, user)
        exec_obj.status = 'completed' if success else 'failed'
        exec_obj.result_data = result_data
        exec_obj.error_message = err
        exec_obj.completed_at = timezone.now()
        exec_obj.save()
        return Response({'status': 'success', 'data': {'execution_id': exec_obj.id, 'status': exec_obj.status, 'result_data': result_data}})
    except Exception as e:
        logger.exception("execute_workflow failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_workflow_executions(request):
    """List workflow executions for the company."""
    try:
        company = request.user.company
        workflow_id = request.GET.get('workflow_id')
        qs = FrontlineWorkflowExecution.objects.filter(workflow__company=company).order_by('-started_at')
        if workflow_id:
            qs = qs.filter(workflow_id=workflow_id)
        qs = qs[:50]
        data = [{'id': e.id, 'workflow_id': e.workflow_id, 'workflow_name': e.workflow_name, 'status': e.status, 'started_at': e.started_at.isoformat(), 'completed_at': e.completed_at.isoformat() if e.completed_at else None, 'error_message': e.error_message} for e in qs]
        return Response({'status': 'success', 'data': data})
    except Exception as e:
        logger.exception("list_workflow_executions failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def approve_workflow_execution(request, execution_id):
    """Approve or reject a paused workflow execution."""
    try:
        import json
        company = request.user.company
        user = _get_or_create_user_for_company_user(request.user)
        exec_obj = get_object_or_404(FrontlineWorkflowExecution, id=execution_id, workflow__company=company)
        
        # Parse data safely
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))
        action = data.get('action', 'approve')
        
        if exec_obj.status != 'awaiting_approval':
            return Response({'status': 'error', 'message': f"Execution is in {exec_obj.status} state, not awaiting_approval."}, status=status.HTTP_400_BAD_REQUEST)
        
        if action == 'approve':
            exec_obj.status = 'in_progress'
            exec_obj.save()
            
            success, result_data, err = _execute_workflow_steps(exec_obj.workflow, exec_obj.context_data, user)
            exec_obj.status = 'completed' if success else 'failed'
            exec_obj.result_data = result_data or {}
            exec_obj.error_message = err
            exec_obj.completed_at = timezone.now()
            exec_obj.save()
            return Response({'status': 'success', 'data': {'status': exec_obj.status, 'result': result_data}})
            
        elif action == 'reject':
            exec_obj.status = 'rejected'
            exec_obj.completed_at = timezone.now()
            exec_obj.save()
            return Response({'status': 'success', 'data': {'status': 'rejected'}})
        else:
            return Response({'status': 'error', 'message': 'Invalid action. Must be approve or reject'}, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.exception("approve_workflow_execution failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_workflow_company_users(request):
    """List company users for the current company (for workflow assign step dropdown)."""
    try:
        company = request.user.company
        qs = CompanyUser.objects.filter(company=company, is_active=True).order_by('full_name', 'email')
        data = [{'id': cu.id, 'full_name': cu.full_name or '', 'email': cu.email or ''} for cu in qs]
        return Response({'status': 'success', 'data': data})
    except Exception as e:
        logger.exception("list_workflow_company_users failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------- Advanced Analytics & Export ----------

def _compute_frontline_analytics_data(company_user, date_from_str=None, date_to_str=None):
    """Compute analytics data for the company user's tickets (same logic as frontline_analytics). Returns dict."""
    user = _get_or_create_user_for_company_user(company_user)
    qs = Ticket.objects.filter(created_by=user)
    if date_from_str:
        try:
            qs = qs.filter(created_at__date__gte=datetime.strptime(date_from_str, '%Y-%m-%d').date())
        except ValueError:
            pass
    if date_to_str:
        try:
            qs = qs.filter(created_at__date__lte=datetime.strptime(date_to_str, '%Y-%m-%d').date())
        except ValueError:
            pass
    tickets = list(qs)
    by_date = {}
    by_status = {}
    by_category = {}
    by_priority = {}
    resolution_times = []
    for t in tickets:
        d = t.created_at.date().isoformat()
        by_date[d] = by_date.get(d, 0) + 1
        by_status[t.status] = by_status.get(t.status, 0) + 1
        by_category[t.category] = by_category.get(t.category, 0) + 1
        by_priority[t.priority] = by_priority.get(t.priority, 0) + 1
        if t.resolved_at and t.created_at:
            delta = (t.resolved_at - t.created_at).total_seconds() / 3600
            resolution_times.append(delta)
    avg_resolution_hours = sum(resolution_times) / len(resolution_times) if resolution_times else None
    # Line/area charts need [{ label, value }]; bar/pie can use object { "Label": count }
    tickets_by_date_sorted = sorted(by_date.items())
    return {
        'tickets_by_date': [{'date': k, 'count': v} for k, v in tickets_by_date_sorted],
        'tickets_by_date_line': [{'label': k, 'value': v} for k, v in tickets_by_date_sorted],
        'tickets_by_status': [{'status': k, 'count': v} for k, v in by_status.items()],
        'tickets_by_status_obj': dict(by_status),
        'tickets_by_category': [{'category': k, 'count': v} for k, v in by_category.items()],
        'tickets_by_category_obj': dict(by_category),
        'tickets_by_priority': [{'priority': k, 'count': v} for k, v in by_priority.items()],
        'tickets_by_priority_obj': dict(by_priority),
        'total_tickets': len(tickets),
        'avg_resolution_hours': round(avg_resolution_hours, 2) if avg_resolution_hours is not None else None,
        'auto_resolved_count': sum(1 for t in tickets if t.auto_resolved),
    }


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def frontline_nl_analytics(request):
    """Natural language analytics: ask a question in plain language, get an answer + optional chart. Controlled (only precomputed data)."""
    try:
        company_user = request.user
        company = company_user.company
        data = json.loads(request.body) if request.body else {}
        question = (data.get('question') or '').strip()
        if not question:
            return Response(
                {'status': 'error', 'message': 'question is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        date_from_str = data.get('date_from') or request.GET.get('date_from')
        date_to_str = data.get('date_to') or request.GET.get('date_to')
        analytics_data = _compute_frontline_analytics_data(company_user, date_from_str, date_to_str)
        agent = FrontlineAgent(company_id=company.id)
        result = agent.answer_analytics_question(question, analytics_data)
        if not result.get('success'):
            return Response(
                {'status': 'error', 'message': result.get('error', 'Failed to answer')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        return Response({
            'status': 'success',
            'data': {
                'answer': result.get('answer'),
                'chart_type': result.get('chart_type'),
                'analytics_data': analytics_data,
            }
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("frontline_nl_analytics failed")
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def frontline_generate_graph(request):
    """AI Graph Maker: generate a chart from a natural language prompt (e.g. 'Show tickets by status as pie chart')."""
    try:
        company_user = request.user
        company = company_user.company
        data = json.loads(request.body) if request.body else {}
        prompt = (data.get('prompt') or '').strip()
        if not prompt:
            return Response(
                {'status': 'error', 'message': 'prompt is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        date_from_str = data.get('date_from')
        date_to_str = data.get('date_to')
        analytics_data = _compute_frontline_analytics_data(company_user, date_from_str, date_to_str)
        agent = FrontlineAgent(company_id=company.id)
        result = agent.generate_analytics_chart(prompt, analytics_data)
        return Response({
            'status': 'success',
            'data': {
                'chart': result.get('chart'),
                'insights': result.get('insights', ''),
            }
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("frontline_generate_graph failed")
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def frontline_graph_prompts_list(request):
    """Get all saved graph prompts for the current company user."""
    try:
        company_user = request.user
        prompts = SavedGraphPrompt.objects.filter(company_user=company_user)
        data = [{
            'id': p.id,
            'title': p.title,
            'prompt': p.prompt,
            'chart_type': p.chart_type,
            'tags': p.tags or [],
            'is_favorite': p.is_favorite,
            'created_at': p.created_at.isoformat(),
            'updated_at': p.updated_at.isoformat(),
        } for p in prompts]
        return Response({'status': 'success', 'data': data})
    except Exception as e:
        logger.exception("frontline_graph_prompts_list failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def frontline_graph_prompts_save(request):
    """Save a graph prompt. Body: title, prompt, tags (list), chart_type."""
    try:
        company_user = request.user
        data = request.data if isinstance(getattr(request, 'data', None), dict) else (json.loads(request.body) if request.body else {})
        title = (data.get('title') or '').strip()
        prompt = (data.get('prompt') or '').strip()
        tags = data.get('tags', [])
        chart_type = data.get('chart_type', 'bar')
        if not title:
            return Response({'status': 'error', 'message': 'Title is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not prompt:
            return Response({'status': 'error', 'message': 'Prompt is required.'}, status=status.HTTP_400_BAD_REQUEST)
        tags = list(tags) if isinstance(tags, list) else []
        saved = SavedGraphPrompt.objects.create(
            company_user=company_user,
            title=title,
            prompt=prompt,
            tags=tags,
            chart_type=chart_type,
        )
        return Response({
            'status': 'success',
            'message': 'Prompt saved.',
            'data': {
                'id': saved.id,
                'title': saved.title,
                'prompt': saved.prompt,
                'chart_type': saved.chart_type,
                'tags': saved.tags,
                'is_favorite': saved.is_favorite,
                'created_at': saved.created_at.isoformat(),
            }
        })
    except Exception as e:
        logger.exception("frontline_graph_prompts_save failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["DELETE"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def frontline_graph_prompts_delete(request, prompt_id):
    """Delete a saved graph prompt."""
    try:
        company_user = request.user
        prompt = SavedGraphPrompt.objects.filter(id=prompt_id, company_user=company_user).first()
        if not prompt:
            return Response({'status': 'error', 'message': 'Prompt not found.'}, status=status.HTTP_404_NOT_FOUND)
        prompt.delete()
        return Response({'status': 'success', 'message': 'Prompt deleted.'})
    except Exception as e:
        logger.exception("frontline_graph_prompts_delete failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["PATCH"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def frontline_graph_prompts_favorite(request, prompt_id):
    """Toggle favorite. Body: is_favorite (bool)."""
    try:
        company_user = request.user
        prompt = SavedGraphPrompt.objects.filter(id=prompt_id, company_user=company_user).first()
        if not prompt:
            return Response({'status': 'error', 'message': 'Prompt not found.'}, status=status.HTTP_404_NOT_FOUND)
        data = request.data if isinstance(getattr(request, 'data', None), dict) else (json.loads(request.body) if request.body else {})
        is_fav = data.get('is_favorite')
        if is_fav is not None:
            prompt.is_favorite = bool(is_fav)
            prompt.save(update_fields=['is_favorite', 'updated_at'])
        return Response({'status': 'success', 'data': {'id': prompt.id, 'is_favorite': prompt.is_favorite}})
    except Exception as e:
        logger.exception("frontline_graph_prompts_favorite failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def frontline_analytics(request):
    """Analytics: trends (tickets by day, by status, by category), resolution stats. Query params: date_from, date_to (YYYY-MM-DD)."""
    try:
        company_user = request.user
        company = company_user.company
        date_from_str = request.GET.get('date_from')
        date_to_str = request.GET.get('date_to')
        data = _compute_frontline_analytics_data(company_user, date_from_str, date_to_str)
        if request.GET.get('narrative') == '1':
            try:
                agent = FrontlineAgent(company_id=company.id)
                nar_result = agent.generate_analytics_narrative(data)
                if nar_result.get('success') and nar_result.get('narrative'):
                    data['narrative'] = nar_result['narrative']
            except Exception as nar_err:
                logger.warning("Analytics narrative generation failed: %s", nar_err)
        return Response({
            'status': 'success',
            'data': data,
        })
    except Exception as e:
        logger.exception("frontline_analytics failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def frontline_analytics_export(request):
    """Export analytics as CSV.

    Query params:
      - entity: tickets (default) | meetings
      - date_from / date_to: YYYY-MM-DD
      - status, priority, category (tickets only)
    Now correctly scoped to the caller's company instead of just their own tickets."""
    try:
        company = request.user.company
        entity = (request.GET.get('entity') or 'tickets').lower()
        date_from_str = request.GET.get('date_from')
        date_to_str = request.GET.get('date_to')

        def _apply_date_range(qs, field='created_at'):
            if date_from_str:
                try:
                    qs = qs.filter(**{f"{field}__date__gte": datetime.strptime(date_from_str, '%Y-%m-%d').date()})
                except ValueError:
                    pass
            if date_to_str:
                try:
                    qs = qs.filter(**{f"{field}__date__lte": datetime.strptime(date_to_str, '%Y-%m-%d').date()})
                except ValueError:
                    pass
            return qs

        response = HttpResponse(content_type='text/csv')
        writer = csv.writer(response)

        if entity == 'meetings':
            qs = FrontlineMeeting.objects.filter(company=company).order_by('-scheduled_at')
            qs = _apply_date_range(qs, field='scheduled_at')
            response['Content-Disposition'] = 'attachment; filename="frontline_meetings_export.csv"'
            writer.writerow(['id', 'title', 'scheduled_at', 'duration_minutes', 'status',
                             'organizer_id', 'participant_count', 'action_item_count',
                             'reminder_24h_sent_at', 'reminder_15m_sent_at', 'created_at'])
            for m in qs[:5000].iterator():
                writer.writerow([
                    m.id, m.title, m.scheduled_at.isoformat() if m.scheduled_at else '',
                    m.duration_minutes, m.status, m.organizer_id,
                    m.participants.count(),
                    len(m.action_items or []),
                    m.reminder_24h_sent_at.isoformat() if m.reminder_24h_sent_at else '',
                    m.reminder_15m_sent_at.isoformat() if m.reminder_15m_sent_at else '',
                    m.created_at.isoformat(),
                ])
            return response

        # Default: tickets — company-scoped
        qs = Ticket.objects.filter(company=company).order_by('-created_at')
        qs = _apply_date_range(qs, field='created_at')
        for f in ('status', 'priority', 'category'):
            v = request.GET.get(f)
            if v:
                qs = qs.filter(**{f: v})
        qs = qs[:5000]
        response['Content-Disposition'] = 'attachment; filename="frontline_tickets_export.csv"'
        writer.writerow([
            'id', 'title', 'description', 'status', 'priority', 'category',
            'auto_resolved', 'resolution_confidence', 'assigned_to_id',
            'created_by_id', 'intent', 'created_at', 'updated_at', 'resolved_at',
            'sla_due_at', 'notes_count',
        ])
        # Bulk-count notes in one query to avoid N+1.
        from django.db.models import Count as _Count
        ticket_ids = list(qs.values_list('id', flat=True))
        notes_map = dict(
            TicketNote.objects.filter(ticket_id__in=ticket_ids)
            .values_list('ticket_id')
            .annotate(c=_Count('id'))
            .values_list('ticket_id', 'c')
        ) if ticket_ids else {}
        for t in Ticket.objects.filter(id__in=ticket_ids).order_by('-created_at').iterator():
            writer.writerow([
                t.id, t.title, (t.description or '')[:500],
                t.status, t.priority, t.category,
                t.auto_resolved, t.resolution_confidence, t.assigned_to_id,
                t.created_by_id, t.intent or '',
                t.created_at.isoformat(), t.updated_at.isoformat(),
                t.resolved_at.isoformat() if t.resolved_at else '',
                t.sla_due_at.isoformat() if t.sla_due_at else '',
                notes_map.get(t.id, 0),
            ])
        return response
    except Exception as e:
        logger.exception("frontline_analytics_export failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def frontline_agent_performance(request):
    """Per-agent performance metrics for the company. Date range via date_from/date_to.

    Returns a list of agents with:
      - tickets_assigned, resolved, auto_resolved
      - avg_resolution_seconds (wall-clock between created_at and resolved_at)
      - resolution_rate (resolved / assigned)
      - sla_breached_count (resolved later than sla_due_at)
    """
    try:
        company = request.user.company
        date_from_str = request.GET.get('date_from')
        date_to_str = request.GET.get('date_to')

        qs = Ticket.objects.filter(company=company, assigned_to__isnull=False)
        if date_from_str:
            try:
                qs = qs.filter(created_at__date__gte=datetime.strptime(date_from_str, '%Y-%m-%d').date())
            except ValueError:
                pass
        if date_to_str:
            try:
                qs = qs.filter(created_at__date__lte=datetime.strptime(date_to_str, '%Y-%m-%d').date())
            except ValueError:
                pass

        resolved_statuses = {'resolved', 'closed', 'auto_resolved'}
        agents = {}  # assigned_to_id → counters
        for t in qs.only('id', 'assigned_to_id', 'status', 'auto_resolved',
                         'created_at', 'resolved_at', 'sla_due_at').iterator():
            aid = t.assigned_to_id
            a = agents.setdefault(aid, {
                'assigned_to_id': aid,
                'tickets_assigned': 0, 'resolved': 0, 'auto_resolved': 0,
                'resolution_seconds_sum': 0, 'resolution_count': 0,
                'sla_breached_count': 0,
            })
            a['tickets_assigned'] += 1
            if t.auto_resolved:
                a['auto_resolved'] += 1
            if t.status in resolved_statuses and t.resolved_at:
                a['resolved'] += 1
                delta = (t.resolved_at - t.created_at).total_seconds()
                if delta >= 0:
                    a['resolution_seconds_sum'] += delta
                    a['resolution_count'] += 1
                if t.sla_due_at and t.resolved_at > t.sla_due_at:
                    a['sla_breached_count'] += 1

        # Resolve user display names in one query.
        from django.contrib.auth.models import User as _User
        user_map = {u.id: (u.get_full_name() or u.username)
                    for u in _User.objects.filter(id__in=list(agents.keys()))}

        rows = []
        for aid, a in agents.items():
            avg = (a['resolution_seconds_sum'] / a['resolution_count']) if a['resolution_count'] else None
            rate = (a['resolved'] / a['tickets_assigned']) if a['tickets_assigned'] else 0.0
            rows.append({
                'assigned_to_id': aid,
                'assigned_to_name': user_map.get(aid),
                'tickets_assigned': a['tickets_assigned'],
                'resolved': a['resolved'],
                'auto_resolved': a['auto_resolved'],
                'resolution_rate': round(rate, 3),
                'avg_resolution_seconds': round(avg, 1) if avg is not None else None,
                'sla_breached_count': a['sla_breached_count'],
            })
        rows.sort(key=lambda r: r['tickets_assigned'], reverse=True)
        return Response({'status': 'success', 'data': rows})
    except Exception as e:
        logger.exception("frontline_agent_performance failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


"""
Frontline Agent API Views for Company Users
Similar structure to marketing_agent.py and recruitment_agent.py
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
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

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.models import CompanyUser, Company
from Frontline_agent.models import (
    Document, Ticket, KnowledgeBase, FrontlineQAChat, FrontlineQAChatMessage,
    NotificationTemplate, ScheduledNotification, FrontlineWorkflow, FrontlineWorkflowExecution,
)
from Frontline_agent.document_processor import DocumentProcessor
from core.Fronline_agent.frontline_agent import FrontlineAgent
from core.Fronline_agent.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


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
            delay_minutes = int(cfg.get('delay_minutes', 0))
            scheduled_at = timezone.now() + timedelta(minutes=delay_minutes)
            context = {
                'ticket_id': ticket.id,
                'ticket_title': ticket.title,
                'resolution': ticket.resolution or '',
                'customer_name': getattr(ticket.created_by, 'email', '') or '',
            }
            recipient_email = getattr(ticket.created_by, 'email', '') or ''
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
                    status='in_progress',
                    context_data=context_data,
                )
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
    """Get or create widget key and return embed URLs/snippet for chat widget and web form."""
    try:
        company_user = request.user
        company = company_user.company
        if not company.frontline_widget_key:
            company.frontline_widget_key = str(uuid.uuid4())
            company.save(update_fields=['frontline_widget_key'])
        key = company.frontline_widget_key
        # Frontend builds full embed URLs from its own origin (window.location.origin)
        return Response({
            'status': 'success',
            'data': {
                'widget_key': key,
            }
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("frontline_widget_config failed")
        return Response(
            {'status': 'error', 'message': 'Failed to load widget config', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


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
        
        # Create uploads directory if it doesn't exist
        upload_dir = Path(settings.MEDIA_ROOT) / 'frontline_documents' / str(company.id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        file_hash = hashlib.sha256(uploaded_file.read()).hexdigest()[:16]
        file_ext = Path(uploaded_file.name).suffix
        filename = f"{file_hash}_{uploaded_file.name}"
        file_path = upload_dir / filename
        
        # Check for duplicate
        existing_doc = Document.objects.filter(company=company, file_hash=hashlib.sha256(uploaded_file.read()).hexdigest()).first()
        if existing_doc:
            return Response({
                'status': 'error',
                'message': 'Document with same content already exists',
                'document_id': existing_doc.id
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Save file
        uploaded_file.seek(0)  # Reset file pointer
        with open(file_path, 'wb') as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)
        
        # Process document
        processor = DocumentProcessor()
        file_format = processor.get_file_format(uploaded_file.name)
        
        processing_result = processor.process_document(str(file_path), uploaded_file.name)
        
        if not processing_result['success']:
            # Delete file if processing failed
            if file_path.exists():
                file_path.unlink()
            return Response(
                {'status': 'error', 'message': f"Failed to process document: {processing_result.get('error')}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get extracted text (FULL content - no truncation for storage)
        extracted_text = processing_result.get('extracted_text', '')
        logger.info(f"Document extracted: {len(extracted_text)} characters from {title}")
        
        # Generate embedding for semantic search
        # NOTE: Embedding generation may truncate text for API limits, but full content is stored in document_content
        embedding = None
        embedding_model = None
        
        if extracted_text:
            try:
                embedding_service = EmbeddingService()
                if embedding_service.is_available():
                    # For embedding, use a representative sample if document is very large
                    # This ensures embedding captures key information while staying within API limits
                    # But we still store the FULL document_content in the database
                    searchable_text = f"{title}\n{description}\n{extracted_text}".strip()
                    
                    # If text is very long, use first part + last part for embedding (better representation)
                    # But always store FULL content
                    if len(searchable_text) > 50000:
                        # Use first 25000 chars + last 25000 chars for embedding (better coverage)
                        embedding_text = searchable_text[:25000] + "\n\n[... middle content ...]\n\n" + searchable_text[-25000:]
                        logger.info(f"Document is large ({len(searchable_text)} chars), using optimized text for embedding ({len(embedding_text)} chars)")
                    else:
                        embedding_text = searchable_text
                    
                    logger.info(f"Generating embedding for document: {title} (embedding text length: {len(embedding_text)} chars, full content: {len(extracted_text)} chars)")
                    embedding = embedding_service.generate_embedding(embedding_text)
                    embedding_model = embedding_service.embedding_model if embedding else None
                    
                    if embedding:
                        logger.info(f"✓ Embedding generated and will be stored in database (dimension: {len(embedding)}, model: {embedding_model})")
                        logger.info(f"✓ Full document content ({len(extracted_text)} chars) will be stored in document_content field")
                    else:
                        logger.warning(f"✗ Embedding generation failed for document: {title}. Will use keyword search only.")
                else:
                    logger.warning("Embedding service not available (OPENAI_API_KEY not set or invalid). Document will use keyword search only.")
            except Exception as e:
                # Only log unexpected errors (quota errors are handled in embedding_service)
                error_str = str(e)
                if '429' not in error_str and 'quota' not in error_str.lower():
                    logger.error(f"Unexpected error generating embedding: {e}", exc_info=True)
                # Continue without embedding - keyword search will still work
                logger.info(f"Continuing without embedding - full document content ({len(extracted_text)} chars) will still be stored")
        
        # Create document record
        document_data = {
            'title': title,
            'description': description,
            'document_type': document_type,
            'file_path': str(file_path.relative_to(settings.MEDIA_ROOT)),
            'file_size': uploaded_file.size,
            'mime_type': uploaded_file.content_type,
            'file_format': file_format,
            'uploaded_by': user,
            'company': company,
            'document_content': extracted_text,
            'is_indexed': True,  # Auto-index if processing succeeded
            'file_hash': processing_result.get('file_hash', ''),
            'processed': True,
            'processed_data': {
                'extraction_success': True,
                'file_format': file_format,
                'embedding_generated': embedding is not None,
            }
        }
        
        # Store embedding in database for semantic search
        # Embeddings are stored as TextField (JSON string) to support large embeddings (>65KB)
        if embedding is not None:
            import json
            embedding_dimension = len(embedding)
            # Serialize embedding to JSON string for storage in TextField
            embedding_json = json.dumps(embedding)
            embedding_json_length = len(embedding_json)
            
            logger.info(f"EMBEDDING DETAILS:")
            logger.info(f"  - Dimension (number of floats): {embedding_dimension}")
            logger.info(f"  - JSON serialized length: {embedding_json_length:,} characters")
            logger.info(f"  - Model: {embedding_model}")
            logger.info(f"  - Storing as NVARCHAR(MAX) (supports up to 2GB, current: {embedding_json_length:,} chars)")
            
            # Store as JSON string in TextField (no size limit issues)
            document_data['embedding'] = embedding_json
            logger.info(f"Embedding will be stored in database as JSON string for document: {title}")
        else:
            # Explicitly set to None if embedding generation failed
            document_data['embedding'] = None
            logger.info(f"No embedding stored for document: {title} (will use keyword search)")
        
        if embedding_model:
            document_data['embedding_model'] = embedding_model
        else:
            # Explicitly set to None if no model was used
            document_data['embedding_model'] = None
        
        # Log what's being stored BEFORE saving to database
        logger.info("=" * 80)
        logger.info("PREPARING TO STORE DOCUMENT IN DATABASE")
        logger.info("=" * 80)
        logger.info(f"Document Data to be stored:")
        logger.info(f"  - title: {document_data['title']}")
        logger.info(f"  - description: {len(document_data.get('description', ''))} chars")
        logger.info(f"  - document_type: {document_data['document_type']}")
        logger.info(f"  - file_format: {document_data['file_format']}")
        logger.info(f"  - file_size: {document_data['file_size']:,} bytes")
        logger.info(f"  - document_content length: {len(document_data['document_content']):,} characters")
        logger.info(f"  - embedding: {'Present' if document_data.get('embedding') else 'None'}")
        if document_data.get('embedding'):
            import json
            emb = document_data['embedding']
            emb_dimension = len(emb)
            emb_json = json.dumps(emb)
            emb_json_length = len(emb_json)
            logger.info(f"    - Embedding dimension: {emb_dimension} floats")
            logger.info(f"    - Embedding JSON length: {emb_json_length:,} characters")
            logger.info(f"    - Embedding size: {emb_json_length / 1024:.2f} KB")
        logger.info(f"  - embedding_model: {document_data.get('embedding_model') or 'None'}")
        logger.info(f"  - is_indexed: {document_data['is_indexed']}")
        logger.info(f"  - processed: {document_data['processed']}")
        logger.info(f"  - file_hash: {document_data.get('file_hash', '')[:16]}..." if document_data.get('file_hash') else "  - file_hash: None")
        logger.info("")
        logger.info(f"Content preview (first 300 chars of what will be stored):")
        logger.info("-" * 80)
        content_preview = document_data['document_content'][:300] if document_data['document_content'] else "(empty)"
        logger.info(content_preview)
        if len(document_data['document_content']) > 300:
            logger.info(f"... (showing first 300 of {len(document_data['document_content']):,} characters)")
        logger.info("-" * 80)
        logger.info("=" * 80)
        
        document = Document.objects.create(**document_data)
        
        # Verify full content was stored and log details
        stored_content_length = len(document.document_content) if document.document_content else 0
        logger.info("=" * 80)
        logger.info(f"DOCUMENT UPLOADED AND STORED IN DATABASE")
        logger.info("=" * 80)
        logger.info(f"Document ID: {document.id}")
        logger.info(f"Title: {document.title}")
        logger.info(f"Company ID: {company.id}")
        logger.info(f"File Format: {document.file_format}")
        logger.info(f"File Size: {uploaded_file.size:,} bytes ({uploaded_file.size / 1024 / 1024:.2f} MB)")
        logger.info(f"")
        logger.info(f"CONTENT STORAGE:")
        logger.info(f"  - Extracted Text Length: {len(extracted_text):,} characters")
        logger.info(f"  - Stored Content Length: {stored_content_length:,} characters")
        logger.info(f"  - Content Match: {'✓ YES' if stored_content_length == len(extracted_text) else '✗ NO - MISMATCH!'}")
        logger.info(f"")
        logger.info(f"CONTENT PREVIEW (first 500 chars):")
        logger.info("-" * 80)
        if document.document_content:
            preview = document.document_content[:500]
            logger.info(preview)
            if len(document.document_content) > 500:
                logger.info(f"... (showing first 500 of {stored_content_length:,} characters)")
        else:
            logger.info("(No content stored)")
        logger.info("-" * 80)
        logger.info(f"")
        logger.info(f"EMBEDDING:")
        logger.info(f"  - Embedding Generated: {'✓ YES' if embedding else '✗ NO'}")
        if embedding:
            import json
            emb_dimension = len(embedding)
            emb_json = json.dumps(embedding)
            emb_json_length = len(emb_json)
            logger.info(f"  - Embedding Dimension: {emb_dimension} floats")
            logger.info(f"  - Embedding JSON Length: {emb_json_length:,} characters")
            logger.info(f"  - Embedding Size: {emb_json_length / 1024:.2f} KB")
            logger.info(f"  - Embedding Model: {embedding_model}")
            logger.info(f"  - Storage: NVARCHAR(MAX) (supports up to 2GB)")
        logger.info(f"")
        logger.info(f"DATABASE FIELDS:")
        logger.info(f"  - document_content: {stored_content_length:,} chars")
        logger.info(f"  - embedding: {'Stored' if embedding else 'None'}")
        
        # Verify embedding was stored correctly
        if document.embedding:
            import json
            # Embedding is stored as JSON string in TextField, need to parse it
            try:
                if isinstance(document.embedding, str):
                    stored_emb = json.loads(document.embedding)
                    stored_emb_json = document.embedding
                else:
                    # Fallback for old format (list from JSONField)
                    stored_emb = document.embedding
                    stored_emb_json = json.dumps(stored_emb)
                
                stored_emb_dimension = len(stored_emb) if isinstance(stored_emb, list) else 0
                stored_emb_json_length = len(stored_emb_json)
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"  - embedding (stored): Error parsing - {e}")
                stored_emb = None
                stored_emb_json = ""
                stored_emb_json_length = 0
                stored_emb_dimension = 0
            
            logger.info(f"  - embedding (stored):")
            logger.info(f"    - Dimension: {stored_emb_dimension} floats")
            logger.info(f"    - JSON length: {stored_emb_json_length:,} characters")
            logger.info(f"    - Size: {stored_emb_json_length / 1024:.2f} KB")
            
            # Compare with what we tried to store
            if embedding:
                original_emb_json = json.dumps(embedding)
                original_emb_json_length = len(original_emb_json)
                if stored_emb_json_length != original_emb_json_length:
                    logger.warning(f"    ⚠ MISMATCH: Stored ({stored_emb_json_length:,}) != Original ({original_emb_json_length:,}) chars!")
                    logger.warning(f"    ⚠ Embedding may have been truncated by database!")
                else:
                    logger.info(f"    ✓ Embedding stored correctly ({stored_emb_json_length:,} chars)")
        else:
            logger.info(f"  - embedding (stored): None")
        
        logger.info(f"  - embedding_model: {embedding_model or 'None'}")
        logger.info(f"  - is_indexed: {document.is_indexed}")
        logger.info(f"  - processed: {document.processed}")
        logger.info(f"  - file_hash: {document.file_hash[:16]}..." if document.file_hash else "  - file_hash: None")
        logger.info("=" * 80)
        
        if stored_content_length < len(extracted_text):
            logger.warning(f"⚠ WARNING: Stored content ({stored_content_length:,} chars) is less than extracted text ({len(extracted_text):,} chars)!")
            logger.warning(f"⚠ This indicates content was truncated during storage!")
        
        if stored_content_length == 0:
            logger.error(f"✗ ERROR: No content was stored in database! Document may be empty or extraction failed.")
        
        return Response({
            'status': 'success',
            'data': {
                'document_id': document.id,
                'title': document.title,
                'file_format': document.file_format,
                'is_indexed': document.is_indexed,
                'processed': document.processed,
                'message': 'Document uploaded and processed successfully'
            }
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.exception("upload_document failed")
        return Response(
            {'status': 'error', 'message': 'Failed to upload document', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


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


def _get_company_by_widget_key(request):
    """Resolve company from widget_key in body (POST) or query/header. Returns (company, error_response) or (company, None)."""
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
    return company, None


@api_view(["POST"])
@permission_classes([])
@authentication_classes([])
def public_qa(request):
    """Public Knowledge Q&A for embedded chat/widget. No auth. Identify company by widget_key in body or X-Widget-Key header."""
    try:
        company, err = _get_company_by_widget_key(request)
        if err:
            return err
        data = json.loads(request.body) if request.body else {}
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
        agent = FrontlineAgent(company_id=company.id)
        result = agent.answer_question(
            question,
            company_id=company.id,
            scope_document_type=scope_document_type,
            scope_document_ids=scope_document_ids,
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
def public_submit(request):
    """Public web form submit (contact/support). Creates a ticket for the company. No auth. Body: widget_key, name, email, message."""
    try:
        company, err = _get_company_by_widget_key(request)
        if err:
            return err
        data = json.loads(request.body) if request.body else {}
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
        )
        _run_notification_triggers(company.id, 'ticket_created', ticket)
        _run_workflow_triggers(company.id, 'ticket_created', ticket, user)
        return Response({
            'status': 'success',
            'message': 'Submitted successfully. We will get back to you soon.',
            'data': {'ticket_id': ticket.id}
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
        
        # Initialize agent with company_id
        agent = FrontlineAgent(company_id=company.id)
        result = agent.answer_question(
            question,
            company_id=company.id,
            scope_document_type=scope_document_type,
            scope_document_ids=scope_document_ids,
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


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
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

        data = [
            {
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
            }
            for t in tickets
        ]
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


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
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
        related_ticket = None
        if ticket_id:
            user = _get_or_create_user_for_company_user(request.user)
            related_ticket = Ticket.objects.filter(id=ticket_id, created_by=user).first()
            if related_ticket:
                context.setdefault('ticket_id', related_ticket.id)
                context.setdefault('ticket_title', related_ticket.title)
                context.setdefault('resolution', related_ticket.resolution or '')
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


# ---------- Workflow / SOP Runner ----------

def _execute_workflow_steps(workflow, context_data, user):
    """Execute workflow steps in order. Returns (success, result_data, error_message)."""
    steps = workflow.steps or []
    result_data = {'steps_completed': 0, 'results': []}
    for i, step in enumerate(steps):
        step_type = (step.get('type') or '').lower()
        if step_type == 'send_email':
            template_id = step.get('template_id')
            raw_recipient = (step.get('recipient_email') or context_data.get('recipient_email') or '{{recipient_email}}').strip()
            recipient = _render_template_body(raw_recipient, context_data).strip()
            if template_id and recipient:
                template = NotificationTemplate.objects.filter(id=template_id).first()
                if template:
                    merged = {**context_data, **step.get('context', {})}
                    body = _render_template_body(template.body, merged)
                    personalized_body = _generate_llm_notification_body(template, merged, workflow.company_id)
                    if personalized_body:
                        body = personalized_body
                    subject = _render_template_body(template.subject, merged)
                    _send_notification_email(recipient, subject, body)
            result_data['results'].append({'step': i, 'type': step_type, 'done': True})
        elif step_type == 'update_ticket':
            ticket_id = context_data.get('ticket_id') or step.get('ticket_id')
            if ticket_id:
                ticket = Ticket.objects.filter(id=ticket_id).first()
                if ticket:
                    if 'status' in step:
                        ticket.status = step['status']
                    if 'resolution' in step:
                        ticket.resolution = step['resolution']
                    ticket.save()
            result_data['results'].append({'step': i, 'type': step_type, 'done': True})
        else:
            result_data['results'].append({'step': i, 'type': step_type, 'done': True})
        result_data['steps_completed'] = i + 1
    return True, result_data, None


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_workflows(request):
    """List workflows for the company."""
    try:
        company = request.user.company
        qs = FrontlineWorkflow.objects.filter(company=company).order_by('-updated_at')
        data = [{'id': w.id, 'name': w.name, 'description': w.description, 'trigger_conditions': w.trigger_conditions, 'steps': w.steps, 'is_active': w.is_active, 'created_at': w.created_at.isoformat(), 'updated_at': w.updated_at.isoformat()} for w in qs]
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
        return Response({'status': 'success', 'data': {'id': w.id, 'name': w.name, 'description': w.description, 'trigger_conditions': w.trigger_conditions, 'steps': w.steps, 'is_active': w.is_active}})
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["PATCH", "PUT"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_workflow(request, workflow_id):
    """Update a workflow."""
    try:
        company = request.user.company
        w = FrontlineWorkflow.objects.filter(company=company, id=workflow_id).first()
        if not w:
            return Response({'status': 'error', 'message': 'Workflow not found'}, status=status.HTTP_404_NOT_FOUND)
        data = request.data if isinstance(request.data, dict) else (json.loads(request.body or '{}'))
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
        w.save()
        return Response({'status': 'success', 'data': {'id': w.id, 'name': w.name}})
    except Exception as e:
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
    resolution_times = []
    for t in tickets:
        d = t.created_at.date().isoformat()
        by_date[d] = by_date.get(d, 0) + 1
        by_status[t.status] = by_status.get(t.status, 0) + 1
        by_category[t.category] = by_category.get(t.category, 0) + 1
        if t.resolved_at and t.created_at:
            delta = (t.resolved_at - t.created_at).total_seconds() / 3600
            resolution_times.append(delta)
    avg_resolution_hours = sum(resolution_times) / len(resolution_times) if resolution_times else None
    return {
        'tickets_by_date': [{'date': k, 'count': v} for k, v in sorted(by_date.items())],
        'tickets_by_status': [{'status': k, 'count': v} for k, v in by_status.items()],
        'tickets_by_category': [{'category': k, 'count': v} for k, v in by_category.items()],
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
    """Export analytics (tickets) as CSV. Query params: date_from, date_to."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        date_from_str = request.GET.get('date_from')
        date_to_str = request.GET.get('date_to')
        qs = Ticket.objects.filter(created_by=user).order_by('-created_at')
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
        qs = qs[:5000]
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="frontline_tickets_export.csv"'
        writer = csv.writer(response)
        writer.writerow(['id', 'title', 'description', 'status', 'priority', 'category', 'auto_resolved', 'created_at', 'updated_at', 'resolved_at'])
        for t in qs:
            writer.writerow([t.id, t.title, (t.description or '')[:500], t.status, t.priority, t.category, t.auto_resolved, t.created_at.isoformat(), t.updated_at.isoformat(), t.resolved_at.isoformat() if t.resolved_at else ''])
        return response
    except Exception as e:
        logger.exception("frontline_analytics_export failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


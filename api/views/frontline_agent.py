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
from datetime import timedelta
import json
import logging
import os
import hashlib
from pathlib import Path

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.models import CompanyUser, Company
from Frontline_agent.models import Document, Ticket, KnowledgeBase
from Frontline_agent.document_processor import DocumentProcessor
from core.Fronline_agent.frontline_agent import FrontlineAgent
from core.Fronline_agent.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


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
        
        # Validate file size (10MB max)
        if uploaded_file.size > 10 * 1024 * 1024:
            return Response(
                {'status': 'error', 'message': 'File size exceeds 10MB limit'},
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
        
        # Generate embedding for semantic search
        embedding = None
        embedding_model = None
        extracted_text = processing_result.get('extracted_text', '')
        
        if extracted_text:
            try:
                embedding_service = EmbeddingService()
                if embedding_service.is_available():
                    # Create searchable text: title + description + content
                    searchable_text = f"{title}\n{description}\n{extracted_text}".strip()
                    embedding = embedding_service.generate_embedding(searchable_text)
                    embedding_model = embedding_service.embedding_model if embedding else None
                    
                    if embedding:
                        logger.info(f"Generated embedding for document {title} (dimension: {len(embedding)})")
                    # Note: If embedding is None, it's already logged in embedding_service
                    # No need to log again here to avoid duplicate messages
                else:
                    logger.warning("Embedding service not available, skipping embedding generation")
            except Exception as e:
                # Only log unexpected errors (quota errors are handled in embedding_service)
                error_str = str(e)
                if '429' not in error_str and 'quota' not in error_str.lower():
                    logger.error(f"Unexpected error generating embedding: {e}", exc_info=True)
                # Continue without embedding - keyword search will still work
        
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
        
        # Only add embedding fields if embedding was generated
        if embedding is not None:
            document_data['embedding'] = embedding
        if embedding_model:
            document_data['embedding_model'] = embedding_model
        
        document = Document.objects.create(**document_data)
        
        logger.info(f"Document uploaded and processed: {document.id} by company {company.id} (embedding: {'yes' if embedding else 'no'})")
        
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


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def knowledge_qa(request):
    """Knowledge Q&A - Answer questions using knowledge base and uploaded documents"""
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
        
        # Initialize agent with company_id
        agent = FrontlineAgent(company_id=company.id)
        result = agent.answer_question(question, company_id=company.id)
        
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
        
        if not query:
            return Response(
                {'status': 'error', 'message': 'Query parameter (q) is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Initialize agent with company_id
        agent = FrontlineAgent(company_id=company.id)
        result = agent.search_knowledge(query, company_id=company.id)
        
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






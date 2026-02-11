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






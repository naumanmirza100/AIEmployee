"""
Operations Agent API Views
Document Processing, Summarization, Analytics, Knowledge Q&A, Authoring, Notifications
"""

import os
import hashlib
import logging
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from operations_agent.models import (
    OperationsDocument, OperationsDocumentChunk, OperationsDocumentSummary,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Document Processing Endpoints
# ──────────────────────────────────────────────

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def upload_document(request):
    """Upload and process a document (PDF, DOCX, XLSX, CSV, PPTX, TXT)."""
    try:
        company_user = request.user
        company = company_user.company

        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response({'status': 'error', 'message': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        title = request.data.get('title', '').strip()
        tags = request.data.get('tags', '').strip()

        # Validate size
        if uploaded_file.size > 50 * 1024 * 1024:
            return Response({'status': 'error', 'message': 'File too large. Maximum 50 MB.'}, status=status.HTTP_400_BAD_REQUEST)

        # Save to disk
        upload_dir = Path(settings.MEDIA_ROOT) / 'operations' / 'documents' / str(company.id)
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Hash for duplicate detection
        file_bytes = uploaded_file.read()
        file_hash = hashlib.sha256(file_bytes).hexdigest()[:16]
        uploaded_file.seek(0)

        safe_name = f"{file_hash}_{uploaded_file.name}"
        file_path = upload_dir / safe_name

        with open(file_path, 'wb') as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)

        # Check duplicate
        existing = OperationsDocument.objects.filter(
            company=company,
            original_filename=uploaded_file.name,
            file_size=uploaded_file.size,
        ).first()
        if existing:
            # Clean up saved file
            if file_path.exists():
                os.remove(file_path)
            return Response({
                'status': 'error',
                'message': f'Document "{uploaded_file.name}" already exists',
                'document_id': existing.id,
            }, status=status.HTTP_409_CONFLICT)

        # Process with agent
        from operations_agent.agents.document_processing_agent import DocumentProcessingAgent
        agent = DocumentProcessingAgent()
        result = agent.process(
            action='process_file',
            file_path=str(file_path),
            original_filename=uploaded_file.name,
            company_id=company.id,
            uploaded_by_id=company_user.id,
            title=title,
            tags=tags,
        )

        if not result.get('success'):
            # Clean up on failure
            if file_path.exists():
                os.remove(file_path)
            return Response({'status': 'error', 'message': result.get('error', 'Processing failed')}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'status': 'success',
            'message': 'Document uploaded and processed successfully',
            'document': result['document'],
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.error(f'Upload document error: {e}', exc_info=True)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_documents(request):
    """List all documents for the company with pagination and filters."""
    try:
        company = request.user.company
        docs = OperationsDocument.objects.filter(company=company).order_by('-created_at')

        # Filters
        doc_type = request.query_params.get('document_type')
        file_type = request.query_params.get('file_type')
        search = request.query_params.get('search', '').strip()
        is_processed = request.query_params.get('is_processed')

        if doc_type:
            docs = docs.filter(document_type=doc_type)
        if file_type:
            docs = docs.filter(file_type=file_type)
        if search:
            from django.db.models import Q
            docs = docs.filter(Q(title__icontains=search) | Q(original_filename__icontains=search))
        if is_processed is not None and is_processed != '':
            docs = docs.filter(is_processed=is_processed.lower() in ('true', '1'))

        # Pagination
        total = docs.count()
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 10))
        page = max(1, page)
        page_size = min(max(1, page_size), 50)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size
        docs_page = docs[start:end]

        data = []
        for doc in docs_page:
            data.append({
                'id': doc.id,
                'title': doc.title,
                'original_filename': doc.original_filename,
                'file_type': doc.file_type,
                'document_type': doc.document_type,
                'file_size': doc.file_size,
                'page_count': doc.page_count,
                'is_processed': doc.is_processed,
                'tags': doc.tags,
                'entities': doc.entities,
                'metadata': doc.metadata,
                'summary': doc.summary or '',
                'key_insights': doc.key_insights or [],
                'uploaded_by': doc.uploaded_by.full_name if doc.uploaded_by else None,
                'created_at': doc.created_at.isoformat(),
                'processed_at': doc.processed_at.isoformat() if doc.processed_at else None,
            })

        return Response({
            'status': 'success',
            'documents': data,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
        })

    except Exception as e:
        logger.error(f'List documents error: {e}', exc_info=True)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_document(request, document_id):
    """Get document detail with parsed content."""
    try:
        company = request.user.company
        doc = OperationsDocument.objects.filter(company=company, pk=document_id).first()
        if not doc:
            return Response({'status': 'error', 'message': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)

        chunks = OperationsDocumentChunk.objects.filter(document=doc).order_by('chunk_index')

        return Response({
            'status': 'success',
            'document': {
                'id': doc.id,
                'title': doc.title,
                'original_filename': doc.original_filename,
                'file_type': doc.file_type,
                'document_type': doc.document_type,
                'file_size': doc.file_size,
                'page_count': doc.page_count,
                'parsed_text': doc.parsed_text[:5000] if doc.parsed_text else '',
                'full_text_length': len(doc.parsed_text) if doc.parsed_text else 0,
                'summary': doc.summary or '',
                'key_insights': doc.key_insights or [],
                'metadata': doc.metadata,
                'entities': doc.entities,
                'tags': doc.tags,
                'is_processed': doc.is_processed,
                'chunks_count': chunks.count(),
                'uploaded_by': doc.uploaded_by.full_name if doc.uploaded_by else None,
                'created_at': doc.created_at.isoformat(),
                'processed_at': doc.processed_at.isoformat() if doc.processed_at else None,
            },
        })

    except Exception as e:
        logger.error(f'Get document error: {e}', exc_info=True)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_document(request, document_id):
    """Delete a document and its chunks."""
    try:
        company = request.user.company
        doc = OperationsDocument.objects.filter(company=company, pk=document_id).first()
        if not doc:
            return Response({'status': 'error', 'message': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)

        title = doc.title

        # Delete file from disk
        if doc.file and os.path.exists(str(doc.file)):
            try:
                os.remove(str(doc.file))
            except OSError:
                pass

        doc.delete()

        return Response({
            'status': 'success',
            'message': f'Document "{title}" deleted successfully',
        })

    except Exception as e:
        logger.error(f'Delete document error: {e}', exc_info=True)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ──────────────────────────────────────────────
# Summarization Endpoints
# ──────────────────────────────────────────────

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def upload_and_summarize(request):
    """Upload a document, extract text, generate rich summary, save summary only, delete file."""
    try:
        company_user = request.user
        company = company_user.company

        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response({'status': 'error', 'message': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        if uploaded_file.size > 50 * 1024 * 1024:
            return Response({'status': 'error', 'message': 'File too large. Maximum 50 MB.'}, status=status.HTTP_400_BAD_REQUEST)

        # Save to temp location
        upload_dir = Path(settings.MEDIA_ROOT) / 'operations' / 'summaries_tmp'
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_hash = hashlib.sha256(uploaded_file.read()).hexdigest()[:16]
        uploaded_file.seek(0)

        temp_path = upload_dir / f"{file_hash}_{uploaded_file.name}"
        with open(temp_path, 'wb') as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)

        # Process with summarization agent
        from operations_agent.agents.summarization_agent import DocumentSummarizationAgent
        agent = DocumentSummarizationAgent()
        result = agent.process(
            action='summarize_file',
            file_path=str(temp_path),
            original_filename=uploaded_file.name,
            company_id=company.id,
            uploaded_by_id=company_user.id,
        )

        # Agent deletes the file, but clean up just in case
        if temp_path.exists():
            try:
                os.remove(temp_path)
            except OSError:
                pass

        if not result.get('success'):
            return Response({'status': 'error', 'message': result.get('error', 'Summarization failed')}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'status': 'success',
            'message': 'Document summarized successfully',
            'summary': result['summary'],
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.error(f'Upload and summarize error: {e}', exc_info=True)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_summaries(request):
    """List all saved summaries for the company with pagination and filters."""
    try:
        company = request.user.company
        summaries = OperationsDocumentSummary.objects.filter(company=company).order_by('-created_at')

        # Filters
        search = request.query_params.get('search', '').strip()
        file_type = request.query_params.get('file_type')
        category = request.query_params.get('category')

        if search:
            summaries = summaries.filter(original_filename__icontains=search)
        if file_type:
            summaries = summaries.filter(file_type=file_type)
        if category:
            summaries = summaries.filter(document_category=category)

        # Pagination
        total = summaries.count()
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 10))
        page = max(1, page)
        page_size = min(max(1, page_size), 50)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size
        summaries_page = summaries[start:end]

        data = []
        for s in summaries_page:
            data.append({
                'id': s.id,
                'original_filename': s.original_filename,
                'file_type': s.file_type,
                'file_size': s.file_size,
                'page_count': s.page_count,
                'word_count': s.word_count,
                'rich_summary': s.rich_summary,
                'key_findings': s.key_findings or [],
                'action_items': s.action_items or [],
                # Insights
                'sentiment': s.sentiment or '',
                'sentiment_explanation': s.sentiment_explanation or '',
                'topics': s.topics or [],
                'importance_level': s.importance_level or '',
                'importance_reason': s.importance_reason or '',
                'entities': s.entities or {},
                'risks': s.risks or [],
                'opportunities': s.opportunities or [],
                'deadlines': s.deadlines or [],
                'document_category': s.document_category or '',
                'created_by': s.created_by.full_name if s.created_by else None,
                'created_at': s.created_at.isoformat(),
            })

        return Response({
            'status': 'success',
            'summaries': data,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
        })

    except Exception as e:
        logger.error(f'List summaries error: {e}', exc_info=True)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_summary(request, summary_id):
    """Get a single summary by ID."""
    try:
        company = request.user.company
        s = OperationsDocumentSummary.objects.filter(company=company, pk=summary_id).first()
        if not s:
            return Response({'status': 'error', 'message': 'Summary not found'}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            'status': 'success',
            'summary': {
                'id': s.id,
                'original_filename': s.original_filename,
                'file_type': s.file_type,
                'file_size': s.file_size,
                'page_count': s.page_count,
                'word_count': s.word_count,
                'rich_summary': s.rich_summary,
                'key_findings': s.key_findings or [],
                'action_items': s.action_items or [],
                # Insights
                'sentiment': s.sentiment or '',
                'sentiment_explanation': s.sentiment_explanation or '',
                'topics': s.topics or [],
                'importance_level': s.importance_level or '',
                'importance_reason': s.importance_reason or '',
                'entities': s.entities or {},
                'risks': s.risks or [],
                'opportunities': s.opportunities or [],
                'deadlines': s.deadlines or [],
                'document_category': s.document_category or '',
                'created_by': s.created_by.full_name if s.created_by else None,
                'created_at': s.created_at.isoformat(),
            },
        })

    except Exception as e:
        logger.error(f'Get summary error: {e}', exc_info=True)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_summary(request, summary_id):
    """Delete a summary."""
    try:
        company = request.user.company
        s = OperationsDocumentSummary.objects.filter(company=company, pk=summary_id).first()
        if not s:
            return Response({'status': 'error', 'message': 'Summary not found'}, status=status.HTTP_404_NOT_FOUND)

        filename = s.original_filename
        s.delete()

        return Response({
            'status': 'success',
            'message': f'Summary for "{filename}" deleted',
        })

    except Exception as e:
        logger.error(f'Delete summary error: {e}', exc_info=True)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ──────────────────────────────────────────────
# Dashboard Stats
# ──────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def dashboard_stats(request):
    """Get dashboard stats for operations agent."""
    try:
        company = request.user.company

        total_docs = OperationsDocument.objects.filter(company=company).count()
        processed_docs = OperationsDocument.objects.filter(company=company, is_processed=True).count()
        total_chunks = OperationsDocumentChunk.objects.filter(document__company=company).count()

        # Doc type breakdown
        from django.db.models import Count
        type_breakdown = dict(
            OperationsDocument.objects.filter(company=company)
            .order_by()
            .values_list('document_type')
            .annotate(count=Count('id'))
            .values_list('document_type', 'count')
        )

        # File type breakdown
        file_breakdown = dict(
            OperationsDocument.objects.filter(company=company)
            .order_by()
            .values_list('file_type')
            .annotate(count=Count('id'))
            .values_list('file_type', 'count')
        )

        return Response({
            'status': 'success',
            'stats': {
                'total_documents': total_docs,
                'processed_documents': processed_docs,
                'total_chunks': total_chunks,
                'document_types': type_breakdown,
                'file_types': file_breakdown,
            },
        })

    except Exception as e:
        logger.error(f'Dashboard stats error: {e}', exc_info=True)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

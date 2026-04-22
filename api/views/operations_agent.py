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
    OperationsChat, OperationsChatMessage, OperationsGeneratedDocument,
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


# ──────────────────────────────────────────────
# Knowledge Q&A Endpoints
# ──────────────────────────────────────────────

def _serialize_chat(chat, include_messages=False):
    data = {
        'id': chat.id,
        'title': chat.title,
        'created_at': chat.created_at.isoformat(),
        'updated_at': chat.updated_at.isoformat(),
    }
    if include_messages:
        msgs = chat.messages.all().order_by('created_at')
        data['messages'] = [
            {
                'id': m.id,
                'role': m.role,
                'content': m.content,
                'sources': m.sources or [],
                'created_at': m.created_at.isoformat(),
            }
            for m in msgs
        ]
    else:
        last = chat.messages.order_by('-created_at').first()
        data['last_message'] = (last.content[:140] if last else '')
        data['message_count'] = chat.messages.count()
    return data


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_qa_chats(request):
    """List all Knowledge Q&A chats for the current user."""
    try:
        user = request.user
        chats = OperationsChat.objects.filter(
            company=user.company, user=user
        ).order_by('-updated_at')
        return Response({
            'status': 'success',
            'chats': [_serialize_chat(c) for c in chats],
        })
    except Exception as e:
        logger.error(f'list_qa_chats error: {e}', exc_info=True)
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_qa_chat(request):
    """Create a new empty chat session."""
    try:
        user = request.user
        title = (request.data.get('title') or 'New chat').strip()[:255] or 'New chat'
        chat = OperationsChat.objects.create(
            company=user.company, user=user, title=title,
        )
        return Response(
            {'status': 'success', 'chat': _serialize_chat(chat, include_messages=True)},
            status=status.HTTP_201_CREATED,
        )
    except Exception as e:
        logger.error(f'create_qa_chat error: {e}', exc_info=True)
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_qa_chat(request, chat_id):
    """Get a chat with all its messages."""
    try:
        user = request.user
        chat = OperationsChat.objects.filter(
            company=user.company, user=user, pk=chat_id
        ).first()
        if not chat:
            return Response(
                {'status': 'error', 'message': 'Chat not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({
            'status': 'success',
            'chat': _serialize_chat(chat, include_messages=True),
        })
    except Exception as e:
        logger.error(f'get_qa_chat error: {e}', exc_info=True)
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def rename_qa_chat(request, chat_id):
    """Rename a chat."""
    try:
        user = request.user
        chat = OperationsChat.objects.filter(
            company=user.company, user=user, pk=chat_id
        ).first()
        if not chat:
            return Response(
                {'status': 'error', 'message': 'Chat not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        title = (request.data.get('title') or '').strip()[:255]
        if not title:
            return Response(
                {'status': 'error', 'message': 'Title cannot be empty'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        chat.title = title
        chat.save(update_fields=['title', 'updated_at'])
        return Response({'status': 'success', 'chat': _serialize_chat(chat)})
    except Exception as e:
        logger.error(f'rename_qa_chat error: {e}', exc_info=True)
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_qa_chat(request, chat_id):
    """Delete a chat and all its messages."""
    try:
        user = request.user
        chat = OperationsChat.objects.filter(
            company=user.company, user=user, pk=chat_id
        ).first()
        if not chat:
            return Response(
                {'status': 'error', 'message': 'Chat not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        chat.delete()
        return Response({'status': 'success', 'message': 'Chat deleted'})
    except Exception as e:
        logger.error(f'delete_qa_chat error: {e}', exc_info=True)
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def ask_qa_question(request):
    """Ask a question. Creates a chat if chat_id missing; persists both user+assistant messages."""
    try:
        user = request.user
        company = user.company

        question = (request.data.get('question') or '').strip()
        if not question:
            return Response(
                {'status': 'error', 'message': 'Question is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        chat_id = request.data.get('chat_id')
        document_ids = request.data.get('document_ids') or []
        if not isinstance(document_ids, list):
            document_ids = []
        # Normalise to ints, drop bad entries silently
        clean_doc_ids = []
        for d in document_ids:
            try:
                clean_doc_ids.append(int(d))
            except (TypeError, ValueError):
                continue

        # Resolve / create chat
        chat = None
        if chat_id:
            chat = OperationsChat.objects.filter(
                company=company, user=user, pk=chat_id
            ).first()
            if not chat:
                return Response(
                    {'status': 'error', 'message': 'Chat not found'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        if not chat:
            # New chat — temporary title, updated after answer
            chat = OperationsChat.objects.create(
                company=company, user=user, title=question[:60] or 'New chat',
            )

        # Build chat history from DB
        existing_msgs = list(
            chat.messages.order_by('created_at').values('role', 'content')
        )

        # Persist user message
        OperationsChatMessage.objects.create(
            chat=chat, role='user', content=question,
        )

        # Run agent
        from operations_agent.agents.knowledge_qa_agent import OperationsKnowledgeQAAgent
        agent = OperationsKnowledgeQAAgent()
        agent.company_id = company.id
        agent.agent_key_name = 'operations_agent'
        result = agent.answer(
            question=question,
            company_id=company.id,
            chat_history=existing_msgs,
            document_ids=clean_doc_ids or None,
        )

        answer_text = result.get('answer') or 'Sorry, I could not produce an answer.'
        sources = result.get('sources') or []

        # Persist assistant message even on soft errors so the user sees something
        assistant_msg = OperationsChatMessage.objects.create(
            chat=chat,
            role='assistant',
            content=answer_text,
            sources=sources,
            response_data={'success': bool(result.get('success'))},
        )

        # If this was a new chat and the first exchange, upgrade the title
        if chat.messages.count() <= 2 and result.get('suggested_title'):
            chat.title = result['suggested_title'][:255]
        chat.save(update_fields=['title', 'updated_at'])

        return Response({
            'status': 'success',
            'chat_id': chat.id,
            'chat_title': chat.title,
            'message': {
                'id': assistant_msg.id,
                'role': 'assistant',
                'content': answer_text,
                'sources': sources,
                'created_at': assistant_msg.created_at.isoformat(),
            },
            'success': bool(result.get('success')),
            'error': result.get('error'),
        })

    except Exception as e:
        logger.error(f'ask_qa_question error: {e}', exc_info=True)
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ──────────────────────────────────────────────
# Document Authoring Endpoints
# ──────────────────────────────────────────────

def _serialize_generated(doc, include_content=True):
    refs = [
        {'id': d.id, 'title': d.title or d.original_filename, 'file_type': d.file_type}
        for d in doc.reference_documents.all()
    ]
    data = {
        'id': doc.id,
        'title': doc.title,
        'template_type': doc.template_type,
        'tone': doc.tone,
        'prompt': doc.prompt,
        'version': doc.version,
        'edit_history': doc.edit_history or [],
        'reference_documents': refs,
        'generated_by': doc.generated_by.full_name if doc.generated_by else None,
        'created_at': doc.created_at.isoformat(),
        'updated_at': doc.updated_at.isoformat(),
        'word_count': len((doc.content or '').split()),
        'tokens_used': doc.tokens_used or {},
    }
    if include_content:
        data['content'] = doc.content
    else:
        preview = (doc.content or '').strip()
        if len(preview) > 220:
            preview = preview[:220] + '…'
        data['preview'] = preview
    return data


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def generate_document(request):
    """Generate a professional document using the authoring agent and persist it."""
    try:
        user = request.user
        company = user.company

        prompt = (request.data.get('prompt') or '').strip()
        if not prompt:
            return Response(
                {'status': 'error', 'message': 'Prompt is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        template_type = (request.data.get('template_type') or 'custom').strip()
        tone = (request.data.get('tone') or 'formal').strip()
        title = (request.data.get('title') or '').strip()

        ref_raw = request.data.get('reference_document_ids') or []
        if not isinstance(ref_raw, list):
            ref_raw = []
        ref_ids = []
        for r in ref_raw:
            try:
                ref_ids.append(int(r))
            except (TypeError, ValueError):
                continue

        # Validate refs belong to company
        valid_refs = list(
            OperationsDocument.objects.filter(
                company=company, id__in=ref_ids, is_processed=True,
            )
        )

        from operations_agent.agents.document_authoring_agent import DocumentAuthoringAgent
        agent = DocumentAuthoringAgent()
        result = agent.generate(
            company_id=company.id,
            prompt=prompt,
            template_type=template_type,
            tone=tone,
            title=title or None,
            reference_document_ids=[d.id for d in valid_refs] or None,
        )

        if not result.get('success'):
            return Response(
                {'status': 'error', 'message': result.get('error', 'Generation failed')},
                status=status.HTTP_400_BAD_REQUEST,
            )

        doc = OperationsGeneratedDocument.objects.create(
            company=company,
            generated_by=user,
            title=result['title'][:500],
            template_type=template_type if template_type in dict(
                OperationsGeneratedDocument.TEMPLATE_TYPE_CHOICES
            ) else 'custom',
            tone=tone if tone in dict(OperationsGeneratedDocument.TONE_CHOICES) else 'formal',
            prompt=prompt,
            content=result['content_markdown'],
            version=1,
            edit_history=[],
            tokens_used=result.get('tokens_used') or {},
        )
        if valid_refs:
            doc.reference_documents.set(valid_refs)

        return Response(
            {'status': 'success', 'document': _serialize_generated(doc, include_content=True)},
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        logger.error(f'generate_document error: {e}', exc_info=True)
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_generated_documents(request):
    """List all generated documents for the company."""
    try:
        company = request.user.company
        docs = OperationsGeneratedDocument.objects.filter(company=company).order_by('-updated_at')

        search = (request.query_params.get('search') or '').strip()
        template = request.query_params.get('template_type')
        if search:
            docs = docs.filter(title__icontains=search)
        if template:
            docs = docs.filter(template_type=template)

        total = docs.count()
        page = max(1, int(request.query_params.get('page', 1)))
        page_size = min(max(1, int(request.query_params.get('page_size', 20))), 100)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size
        page_docs = docs[start:end]

        return Response({
            'status': 'success',
            'documents': [_serialize_generated(d, include_content=False) for d in page_docs],
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
        })
    except Exception as e:
        logger.error(f'list_generated_documents error: {e}', exc_info=True)
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_generated_document(request, doc_id):
    """Get a generated document with full content."""
    try:
        company = request.user.company
        doc = OperationsGeneratedDocument.objects.filter(company=company, pk=doc_id).first()
        if not doc:
            return Response(
                {'status': 'error', 'message': 'Document not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({'status': 'success', 'document': _serialize_generated(doc)})
    except Exception as e:
        logger.error(f'get_generated_document error: {e}', exc_info=True)
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_generated_document(request, doc_id):
    """Update title / content of a generated document. Bumps version on content change."""
    try:
        user = request.user
        company = user.company
        doc = OperationsGeneratedDocument.objects.filter(company=company, pk=doc_id).first()
        if not doc:
            return Response(
                {'status': 'error', 'message': 'Document not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        changed = False
        new_title = request.data.get('title')
        new_content = request.data.get('content')

        if isinstance(new_title, str):
            new_title = new_title.strip()[:500]
            if new_title and new_title != doc.title:
                doc.title = new_title
                changed = True

        if isinstance(new_content, str) and new_content != doc.content:
            history = doc.edit_history or []
            history.append({
                'version': doc.version,
                'edited_at': timezone.now().isoformat(),
                'edited_by': user.full_name if hasattr(user, 'full_name') else None,
                'previous_length': len(doc.content or ''),
            })
            # Cap history to last 20 entries
            doc.edit_history = history[-20:]
            doc.content = new_content
            doc.version += 1
            changed = True

        if changed:
            doc.save()

        return Response({'status': 'success', 'document': _serialize_generated(doc)})
    except Exception as e:
        logger.error(f'update_generated_document error: {e}', exc_info=True)
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_generated_document(request, doc_id):
    """Delete a generated document."""
    try:
        company = request.user.company
        doc = OperationsGeneratedDocument.objects.filter(company=company, pk=doc_id).first()
        if not doc:
            return Response(
                {'status': 'error', 'message': 'Document not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        title = doc.title
        doc.delete()
        return Response({'status': 'success', 'message': f'Deleted "{title}"'})
    except Exception as e:
        logger.error(f'delete_generated_document error: {e}', exc_info=True)
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def regenerate_document(request, doc_id):
    """Regenerate a document using same prompt/template/refs but fresh AI output."""
    try:
        user = request.user
        company = user.company
        doc = OperationsGeneratedDocument.objects.filter(company=company, pk=doc_id).first()
        if not doc:
            return Response(
                {'status': 'error', 'message': 'Document not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Allow overriding prompt/tone/refs at regen time
        prompt = (request.data.get('prompt') or doc.prompt or '').strip()
        template_type = request.data.get('template_type') or doc.template_type
        tone = request.data.get('tone') or doc.tone
        ref_ids_raw = request.data.get('reference_document_ids')
        if ref_ids_raw is None:
            ref_ids = list(doc.reference_documents.values_list('id', flat=True))
        else:
            ref_ids = []
            if isinstance(ref_ids_raw, list):
                for r in ref_ids_raw:
                    try:
                        ref_ids.append(int(r))
                    except (TypeError, ValueError):
                        continue

        valid_refs = list(
            OperationsDocument.objects.filter(
                company=company, id__in=ref_ids, is_processed=True,
            )
        )

        from operations_agent.agents.document_authoring_agent import DocumentAuthoringAgent
        agent = DocumentAuthoringAgent()
        result = agent.generate(
            company_id=company.id,
            prompt=prompt,
            template_type=template_type,
            tone=tone,
            title=doc.title,
            reference_document_ids=[d.id for d in valid_refs] or None,
        )

        if not result.get('success'):
            return Response(
                {'status': 'error', 'message': result.get('error', 'Regeneration failed')},
                status=status.HTTP_400_BAD_REQUEST,
            )

        history = doc.edit_history or []
        history.append({
            'version': doc.version,
            'edited_at': timezone.now().isoformat(),
            'edited_by': user.full_name if hasattr(user, 'full_name') else None,
            'action': 'regenerate',
            'previous_length': len(doc.content or ''),
        })
        doc.edit_history = history[-20:]
        doc.prompt = prompt
        doc.template_type = template_type if template_type in dict(
            OperationsGeneratedDocument.TEMPLATE_TYPE_CHOICES
        ) else 'custom'
        doc.tone = tone if tone in dict(OperationsGeneratedDocument.TONE_CHOICES) else 'formal'
        doc.content = result['content_markdown']
        doc.version += 1
        doc.tokens_used = result.get('tokens_used') or {}
        doc.save()
        doc.reference_documents.set(valid_refs)

        return Response({'status': 'success', 'document': _serialize_generated(doc)})

    except Exception as e:
        logger.error(f'regenerate_document error: {e}', exc_info=True)
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def export_generated_document_pdf(request, doc_id):
    """Stream a generated document as a PDF file (direct download)."""
    from django.http import HttpResponse
    try:
        company = request.user.company
        doc = OperationsGeneratedDocument.objects.filter(company=company, pk=doc_id).first()
        if not doc:
            return Response(
                {'status': 'error', 'message': 'Document not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        from operations_agent.utils.pdf_exporter import render_document_pdf

        template_label = dict(OperationsGeneratedDocument.TEMPLATE_TYPE_CHOICES).get(doc.template_type, doc.template_type)
        tone_label = dict(OperationsGeneratedDocument.TONE_CHOICES).get(doc.tone, doc.tone)

        pdf_bytes = render_document_pdf(
            title=doc.title,
            content_markdown=doc.content or '',
            template_label=template_label,
            tone_label=tone_label,
            version=doc.version,
            word_count=len((doc.content or '').split()),
        )

        safe_name = ''.join(c if c.isalnum() or c in ('-', '_', ' ') else '_' for c in (doc.title or 'document'))[:80].strip() or 'document'

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{safe_name}.pdf"'
        response['Content-Length'] = str(len(pdf_bytes))
        return response

    except Exception as e:
        logger.error(f'export_generated_document_pdf error: {e}', exc_info=True)
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def stream_generate_document(request):
    """Stream a generated document using newline-delimited JSON (NDJSON).

    Each line is one event:
        {"type": "meta",  "title": "...", "references": [...]}
        {"type": "text",  "data": "chunk..."}
        {"type": "done",  "document": {...serialized...}}
        {"type": "error", "message": "..."}

    The client reads line-by-line with fetch().body.getReader().
    """
    import json
    from django.http import StreamingHttpResponse

    user = request.user
    company = user.company

    prompt = (request.data.get('prompt') or '').strip()
    if not prompt:
        return Response(
            {'status': 'error', 'message': 'Prompt is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    template_type = (request.data.get('template_type') or 'custom').strip()
    tone = (request.data.get('tone') or 'formal').strip()
    title = (request.data.get('title') or '').strip()

    ref_raw = request.data.get('reference_document_ids') or []
    if not isinstance(ref_raw, list):
        ref_raw = []
    ref_ids = []
    for r in ref_raw:
        try:
            ref_ids.append(int(r))
        except (TypeError, ValueError):
            continue

    valid_refs = list(
        OperationsDocument.objects.filter(
            company=company, id__in=ref_ids, is_processed=True,
        )
    )
    valid_ref_ids = [d.id for d in valid_refs]

    # Validate template/tone against model choices
    resolved_template = template_type if template_type in dict(
        OperationsGeneratedDocument.TEMPLATE_TYPE_CHOICES
    ) else 'custom'
    resolved_tone = tone if tone in dict(OperationsGeneratedDocument.TONE_CHOICES) else 'formal'

    def _emit(event_type: str, payload) -> str:
        if event_type == 'text':
            msg = {'type': 'text', 'data': payload}
        elif isinstance(payload, dict):
            msg = {'type': event_type, **payload}
        else:
            msg = {'type': event_type, 'data': payload}
        return json.dumps(msg, ensure_ascii=False) + '\n'

    def event_stream():
        try:
            from operations_agent.agents.document_authoring_agent import DocumentAuthoringAgent
            agent = DocumentAuthoringAgent()

            final_payload = None

            for event_type, payload in agent.generate_stream(
                company_id=company.id,
                prompt=prompt,
                template_type=resolved_template,
                tone=resolved_tone,
                title=title or None,
                reference_document_ids=valid_ref_ids or None,
            ):
                if event_type == 'done':
                    final_payload = payload
                    # Don't emit yet — save to DB first so the client gets the real id
                    break
                if event_type == 'error':
                    yield _emit('error', {'message': payload.get('message', 'Generation failed')})
                    return
                yield _emit(event_type, payload)

            if not final_payload:
                yield _emit('error', {'message': 'Stream ended without a result'})
                return

            # Persist to DB
            try:
                doc = OperationsGeneratedDocument.objects.create(
                    company=company,
                    generated_by=user,
                    title=final_payload['title'][:500],
                    template_type=resolved_template,
                    tone=resolved_tone,
                    prompt=prompt,
                    content=final_payload['content_markdown'],
                    version=1,
                    edit_history=[],
                    tokens_used=final_payload.get('tokens_used') or {},
                )
                if valid_refs:
                    doc.reference_documents.set(valid_refs)
            except Exception as db_err:
                logger.error(f'stream_generate_document DB save error: {db_err}', exc_info=True)
                yield _emit('error', {'message': f'Could not save document: {db_err}'})
                return

            yield _emit('done', {'document': _serialize_generated(doc, include_content=True)})

        except Exception as e:
            logger.error(f'stream_generate_document error: {e}', exc_info=True)
            yield _emit('error', {'message': str(e)})

    response = StreamingHttpResponse(event_stream(), content_type='application/x-ndjson')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # disable nginx buffering when deployed
    return response


# ──────────────────────────────────────────────
# Operations Analytics Endpoint
# ──────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def operations_analytics(request):
    """Aggregated analytics for the Operations module.

    Query params:
        range: '7d' | '30d' | '90d' | 'all'  (default '30d')

    Returns a big payload with KPIs + chart-ready series.
    """
    from collections import Counter
    from datetime import timedelta
    from django.db.models import Count, Sum

    try:
        company = request.user.company
        rng = (request.query_params.get('range') or '30d').lower()
        now = timezone.now()
        start = None
        if rng == '7d':
            start = now - timedelta(days=7)
        elif rng == '30d':
            start = now - timedelta(days=30)
        elif rng == '90d':
            start = now - timedelta(days=90)
        # 'all' leaves start as None

        # ── Base querysets ─────────────────────────
        docs_qs = OperationsDocument.objects.filter(company=company)
        summaries_qs = OperationsDocumentSummary.objects.filter(company=company)
        gen_qs = OperationsGeneratedDocument.objects.filter(company=company)
        chat_qs = OperationsChat.objects.filter(company=company)
        msg_qs = OperationsChatMessage.objects.filter(chat__company=company)

        if start:
            docs_qs = docs_qs.filter(created_at__gte=start)
            summaries_qs = summaries_qs.filter(created_at__gte=start)
            gen_qs = gen_qs.filter(created_at__gte=start)
            chat_qs = chat_qs.filter(created_at__gte=start)
            msg_qs = msg_qs.filter(created_at__gte=start)

        # ── KPIs ───────────────────────────────────
        total_docs = docs_qs.count()
        processed_docs = docs_qs.filter(is_processed=True).count()
        total_pages = docs_qs.aggregate(s=Sum('page_count'))['s'] or 0
        total_file_bytes = docs_qs.aggregate(s=Sum('file_size'))['s'] or 0
        total_summaries = summaries_qs.count()
        total_generated = gen_qs.count()
        total_chats = chat_qs.count()
        total_qa_messages = msg_qs.filter(role='user').count()

        # Tokens across generated docs (JSONField aggregation done in Python for portability)
        token_sum = 0
        token_by_template = {}
        for g in gen_qs.only('template_type', 'tokens_used'):
            tokens = (g.tokens_used or {}).get('total_tokens') or 0
            token_sum += tokens
            token_by_template.setdefault(g.template_type, {'count': 0, 'tokens': 0})
            token_by_template[g.template_type]['count'] += 1
            token_by_template[g.template_type]['tokens'] += tokens

        # ── Breakdowns ─────────────────────────────
        # `.order_by()` resets the model's default -created_at ordering which SQL Server
        # otherwise appends to the GROUP BY query and then rejects.
        doc_types = dict(
            docs_qs.order_by()
            .values_list('document_type')
            .annotate(c=Count('id'))
            .values_list('document_type', 'c')
        )
        file_types = dict(
            docs_qs.order_by()
            .values_list('file_type')
            .annotate(c=Count('id'))
            .values_list('file_type', 'c')
        )

        # ── Time series: uploads per day ───────────
        # Use last 30 buckets regardless of range (bucket size scales with range)
        bucket_days = 1
        lookback_days = 30
        if rng == '7d':
            lookback_days = 7
        elif rng == '30d':
            lookback_days = 30
        elif rng == '90d':
            lookback_days = 90
            bucket_days = 3  # 30 buckets × 3 days
        elif rng == 'all':
            oldest = OperationsDocument.objects.filter(company=company).order_by('created_at').first()
            if oldest:
                days_total = max(1, (now - oldest.created_at).days + 1)
                lookback_days = days_total
                bucket_days = max(1, days_total // 30)

        series_docs = []
        series_generated = []
        series_qa = []
        for i in range(lookback_days, 0, -bucket_days):
            bucket_end = now - timedelta(days=i - bucket_days)
            bucket_start = now - timedelta(days=i)
            label = bucket_start.strftime('%b %d')
            c_docs = OperationsDocument.objects.filter(
                company=company, created_at__gte=bucket_start, created_at__lt=bucket_end,
            ).count()
            c_gen = OperationsGeneratedDocument.objects.filter(
                company=company, created_at__gte=bucket_start, created_at__lt=bucket_end,
            ).count()
            c_qa = OperationsChatMessage.objects.filter(
                chat__company=company, role='user',
                created_at__gte=bucket_start, created_at__lt=bucket_end,
            ).count()
            series_docs.append({'label': label, 'value': c_docs})
            series_generated.append({'label': label, 'value': c_gen})
            series_qa.append({'label': label, 'value': c_qa})

        # ── Insights from summaries ────────────────
        sentiment_counts = Counter()
        importance_counts = Counter()
        topic_counts = Counter()
        category_counts = Counter()
        risks_total = 0
        opportunities_total = 0
        upcoming_deadlines = []
        entity_counter_orgs = Counter()
        entity_counter_people = Counter()

        for s in summaries_qs.only(
            'sentiment', 'importance_level', 'topics', 'document_category',
            'risks', 'opportunities', 'deadlines', 'entities', 'created_at',
        ):
            if s.sentiment:
                sentiment_counts[s.sentiment.lower()] += 1
            if s.importance_level:
                importance_counts[s.importance_level.lower()] += 1
            if s.document_category:
                category_counts[s.document_category] += 1
            for t in (s.topics or [])[:5]:
                if t:
                    topic_counts[str(t).strip()[:50]] += 1
            risks_total += len(s.risks or [])
            opportunities_total += len(s.opportunities or [])

            # Entities
            ents = s.entities or {}
            if isinstance(ents, dict):
                for org in (ents.get('organizations') or [])[:10]:
                    if org:
                        entity_counter_orgs[str(org).strip()[:60]] += 1
                for person in (ents.get('people') or [])[:10]:
                    if person:
                        entity_counter_people[str(person).strip()[:60]] += 1

            # Deadlines
            for d in (s.deadlines or [])[:10]:
                if isinstance(d, dict):
                    date = d.get('date') or d.get('deadline')
                    desc = d.get('description') or d.get('title') or d.get('text')
                    if date or desc:
                        upcoming_deadlines.append({
                            'date': str(date) if date else None,
                            'description': str(desc) if desc else '',
                            'source': s.original_filename,
                        })
                elif isinstance(d, str) and d.strip():
                    upcoming_deadlines.append({
                        'date': None,
                        'description': d.strip()[:200],
                        'source': s.original_filename,
                    })

        # Keep top deadlines (first 10, arbitrary order)
        upcoming_deadlines = upcoming_deadlines[:10]

        # ── Template breakdown (for generated docs) ─
        template_breakdown = []
        for template, data in token_by_template.items():
            template_breakdown.append({
                'template': template,
                'count': data['count'],
                'tokens': data['tokens'],
            })

        # ── Compose response ──────────────────────
        return Response({
            'status': 'success',
            'range': rng,
            'kpis': {
                'total_documents': total_docs,
                'processed_documents': processed_docs,
                'total_pages': total_pages,
                'total_file_bytes': int(total_file_bytes),
                'total_summaries': total_summaries,
                'total_generated': total_generated,
                'total_chats': total_chats,
                'total_qa_messages': total_qa_messages,
                'total_tokens_used': token_sum,
            },
            'document_types': [
                {'name': k, 'value': v} for k, v in sorted(doc_types.items(), key=lambda x: -x[1])
            ],
            'file_types': [
                {'name': k, 'value': v} for k, v in sorted(file_types.items(), key=lambda x: -x[1])
            ],
            'timeseries': {
                'documents': series_docs,
                'generated': series_generated,
                'qa': series_qa,
            },
            'sentiment': [
                {'name': k, 'value': v} for k, v in sentiment_counts.most_common()
            ],
            'importance': [
                {'name': k, 'value': v}
                for k, v in sorted(importance_counts.items(), key=lambda x: -x[1])
            ],
            'topics': [
                {'name': k, 'value': v} for k, v in topic_counts.most_common(10)
            ],
            'categories': [
                {'name': k, 'value': v} for k, v in category_counts.most_common(8)
            ],
            'risks_vs_opportunities': {
                'risks': risks_total,
                'opportunities': opportunities_total,
            },
            'top_organizations': [
                {'name': k, 'value': v} for k, v in entity_counter_orgs.most_common(8)
            ],
            'top_people': [
                {'name': k, 'value': v} for k, v in entity_counter_people.most_common(8)
            ],
            'upcoming_deadlines': upcoming_deadlines,
            'template_usage': template_breakdown,
        })

    except Exception as e:
        logger.error(f'operations_analytics error: {e}', exc_info=True)
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

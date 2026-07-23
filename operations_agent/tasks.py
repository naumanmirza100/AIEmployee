"""Background processing for Operations documents.

Operations' document pipeline runs LLM classification / entity / summary steps
that require the *per-company* API key resolved from the request. A plain Celery
worker has no request context to resolve that key, so — unlike HR/Frontline,
whose tasks only extract+chunk+embed — the heavy pipeline here runs in a
background **thread** started from the upload view, with the resolved agent
passed in. The HTTP request returns 202 immediately; the thread does the work
and stamps `processing_status`.

The Celery `reindex_operations_document` task below only re-chunks + re-embeds
an already-parsed document (no LLM, no per-company key), so it is safe to run in
a worker and is used by the reindex management command.
"""
import logging
import threading

logger = logging.getLogger(__name__)


def process_document_in_background(agent, file_path, original_filename,
                                   company_id, uploaded_by_id, existing_doc_id,
                                   title='', tags=''):
    """Run the full (LLM + chunk + embed) pipeline in a daemon thread.

    `agent` must be a `DocumentProcessingAgent` already configured with
    `company_id` + `agent_key_name` so its per-company LLM key is resolvable.
    `existing_doc_id` is the placeholder row the endpoint pre-created so the
    client can poll status immediately. Returns the started `threading.Thread`.
    """
    def _run():
        from django.db import close_old_connections
        close_old_connections()
        try:
            agent.process(
                action='process_file',
                file_path=file_path,
                original_filename=original_filename,
                company_id=company_id,
                uploaded_by_id=uploaded_by_id,
                title=title,
                tags=tags,
                existing_doc_id=existing_doc_id,
            )
        except Exception as exc:
            logger.exception("Operations background processing failed for %s", original_filename)
            # Ensure the placeholder doesn't hang in 'processing' forever.
            try:
                from operations_agent.models import OperationsDocument
                OperationsDocument.objects.filter(id=existing_doc_id).update(
                    processing_status='failed', processing_error=str(exc)[:2000],
                )
            except Exception:
                pass
        finally:
            close_old_connections()

    t = threading.Thread(target=_run, name='ops-doc-process', daemon=True)
    t.start()
    return t


try:
    from celery import shared_task
except Exception:  # pragma: no cover - celery optional in some envs
    shared_task = None


def _reindex_impl(document_id):
    """Re-chunk + re-embed an already-parsed OperationsDocument from its stored
    `parsed_text`. No LLM calls, so no per-company key needed."""
    from operations_agent.models import OperationsDocument, OperationsDocumentChunk
    from operations_agent.agents.document_processing_agent import (
        DocumentProcessingAgent, _invalidate_operations_indexes,
    )

    doc = OperationsDocument.objects.filter(id=document_id).first()
    if not doc:
        return {'status': 'not_found', 'document_id': document_id}
    if not (doc.parsed_text or '').strip():
        return {'status': 'no_text', 'document_id': document_id}

    doc.processing_status = 'processing'
    doc.save(update_fields=['processing_status', 'updated_at'])
    OperationsDocumentChunk.objects.filter(document=doc).delete()

    agent = DocumentProcessingAgent()
    count, embedded, model = agent._chunk_embed_and_store(
        doc, doc.parsed_text, doc.page_count or 1, doc.document_type or 'other',
    )
    doc.chunks_total = count
    doc.chunks_processed = count
    doc.is_indexed = embedded
    doc.embedding_model = model or ''
    doc.processing_status = 'ready'
    doc.save(update_fields=[
        'chunks_total', 'chunks_processed', 'is_indexed',
        'embedding_model', 'processing_status', 'updated_at',
    ])
    _invalidate_operations_indexes(doc.company_id, embedded)
    return {'status': 'ready', 'document_id': document_id, 'chunks': count, 'embedded': embedded}


if shared_task is not None:
    @shared_task(name='operations_agent.tasks.reindex_operations_document',
                 bind=True, max_retries=1, default_retry_delay=30)
    def reindex_operations_document(self, document_id):
        return _reindex_impl(document_id)
else:  # pragma: no cover
    def reindex_operations_document(document_id):
        return _reindex_impl(document_id)

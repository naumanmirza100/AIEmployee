"""Background processing for Operations documents.

Operations' document pipeline runs LLM classification / entity / summary steps
that require the *per-company* API key resolved from the request. A plain Celery
worker has no request context to resolve that key, so — unlike HR/Frontline,
whose tasks only extract+chunk+embed — the heavy pipeline here runs in a
background **thread** started from the upload view, with the resolved agent
passed in. The HTTP request returns 202 immediately; the thread does the work
and stamps `processing_status`.

The Celery `reindex_operations_document` task below only re-chunks + re-embeds
an already-parsed document (no LLM), so it is safe to run in a worker and is
used by the reindex management command. Embedding resolves the company key from
the database rather than the request — so it still needs no request context —
and failing to resolve one is never fatal: the chunks are just stored without
vectors.
"""
import logging
import threading

logger = logging.getLogger(__name__)


def _fail_if_still_running(model, row_id, result):
    """Stamp an entry failed with the agent's own error when the work did not succeed and the entry is still pending
    or processing.

    The agent hands most errors back as a result instead of raising them, and that result was never read: an error
    while saving left the entry on 'processing' until the sweep marked it 'The server may have restarted', 30
    minutes later (two hours for a summary), and the file could not be summarised again meanwhile (CO-178). Saved
    with its fields named, so the 'could not process' alert and the uploader's bell still follow. A failure that
    already wrote its own message, and an entry deleted meanwhile, are left alone."""
    if (result or {}).get('success') or (result or {}).get('deleted'):
        return
    row = model.objects.filter(id=row_id, processing_status__in=('pending', 'processing')).first()
    if row is None:
        return
    row.processing_status = 'failed'
    row.processing_error = str((result or {}).get('error') or 'Processing failed.')[:2000]
    fields = ['processing_status', 'processing_error']
    if any(f.name == 'updated_at' for f in model._meta.fields):
        fields.append('updated_at')
    row.save(update_fields=fields)


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
            result = agent.process(
                action='process_file',
                file_path=file_path,
                original_filename=original_filename,
                company_id=company_id,
                uploaded_by_id=uploaded_by_id,
                title=title,
                tags=tags,
                existing_doc_id=existing_doc_id,
            )
            from operations_agent.models import OperationsDocument
            _fail_if_still_running(OperationsDocument, existing_doc_id, result)
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


def summarize_document_in_background(agent, file_path, original_filename,
                                     company_id, uploaded_by_id, existing_summary_id):
    """Run summarisation (extract → LLM summary → insights → chunk/embed) in a
    daemon thread so the upload request returns immediately.

    Same rationale as `process_document_in_background`: the pipeline needs the
    per-company LLM key resolved from the request, which a Celery worker has no
    context for.
    """
    def _run():
        from django.db import close_old_connections
        close_old_connections()
        try:
            result = agent.process(
                action='summarize_file',
                file_path=file_path,
                original_filename=original_filename,
                company_id=company_id,
                uploaded_by_id=uploaded_by_id,
                existing_summary_id=existing_summary_id,
            )
            from operations_agent.models import OperationsDocumentSummary
            _fail_if_still_running(OperationsDocumentSummary, existing_summary_id, result)
        except Exception as exc:
            logger.exception("Operations background summarisation failed for %s", original_filename)
            try:
                from operations_agent.models import OperationsDocumentSummary
                OperationsDocumentSummary.objects.filter(id=existing_summary_id).update(
                    processing_status='failed', processing_error=str(exc)[:2000],
                )
            except Exception:
                pass
        finally:
            close_old_connections()

    t = threading.Thread(target=_run, name='ops-doc-summarize', daemon=True)
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

    from django.db import transaction

    doc.processing_status = 'processing'
    doc.processing_error = ''
    doc.save(update_fields=['processing_status', 'processing_error', 'updated_at'])

    # Re-chunk + re-embed + stamp ready in one transaction so a failure can't
    # leave the doc chunk-less-but-ready or stuck mid-way.
    agent = DocumentProcessingAgent()
    # A document whose passages had vectors keeps them when the new run gets none (the embedding provider was down):
    # re-indexing replaced good vectors with none and still reported success, for every document of every company
    # when run without filters (CO-266).
    had_vectors = OperationsDocumentChunk.objects.filter(document=doc, embedding__isnull=False).exists()
    try:
        with transaction.atomic():
            OperationsDocumentChunk.objects.filter(document=doc).delete()
            count, embedded, model = agent._chunk_embed_and_store(
                doc, doc.parsed_text, doc.page_count or 1, doc.document_type or 'other',
            )
            if had_vectors and not embedded:
                raise _NoVectors()
            doc.chunks_total = count
            doc.chunks_processed = count
            doc.is_indexed = embedded
            doc.embedding_model = model or ''
            doc.processing_status = 'ready'
            doc.is_processed = True
            doc.save(update_fields=[
                'chunks_total', 'chunks_processed', 'is_indexed',
                'embedding_model', 'processing_status', 'is_processed', 'updated_at',
            ])
    except _NoVectors:
        OperationsDocument.objects.filter(pk=doc.pk).update(processing_status='ready', processing_error='')
        return {'status': 'not_embedded', 'document_id': document_id}
    _invalidate_operations_indexes(doc.company_id, embedded)
    return {'status': 'ready', 'document_id': document_id, 'chunks': count, 'embedded': embedded}


class _NoVectors(Exception):
    """The new run made no vectors for a document that had them: undo it, keep the old passages."""


def reindex_document_in_background(document_id):
    """Run `_reindex_impl` in a daemon thread (used by the reprocess endpoint so
    the request returns immediately). Stamps 'failed' if it dies."""
    def _run():
        from django.db import close_old_connections
        close_old_connections()
        try:
            _reindex_impl(document_id)
        except Exception as exc:
            logger.exception("Operations reprocess failed for doc %s", document_id)
            try:
                from operations_agent.models import OperationsDocument
                OperationsDocument.objects.filter(id=document_id).update(
                    processing_status='failed', processing_error=str(exc)[:2000],
                )
            except Exception:
                pass
        finally:
            close_old_connections()

    t = threading.Thread(target=_run, name='ops-doc-reindex', daemon=True)
    t.start()
    return t


def _reindex_summary_impl(summary_id):
    """Re-chunk + re-embed a summarised file from its stored `parsed_text`.
    No LLM. Embedding may resolve the company's own key (see
    `_chunk_embed_and_store`), but never blocks: a quota/key failure just
    stores the chunks without vectors. Used by the reindex command's
    --summaries mode and to backfill embeddings once a provider key is added."""
    from django.db import transaction
    from operations_agent.models import OperationsDocumentSummary, OperationsDocumentChunk
    from operations_agent.agents.document_processing_agent import (
        DocumentProcessingAgent, _invalidate_operations_indexes,
    )

    s = OperationsDocumentSummary.objects.filter(id=summary_id).first()
    if not s:
        return {'status': 'not_found', 'summary_id': summary_id}
    if not (s.parsed_text or '').strip():
        return {'status': 'no_text', 'summary_id': summary_id}

    s.processing_status = 'processing'
    s.save(update_fields=['processing_status'])

    agent = DocumentProcessingAgent()
    had_vectors = OperationsDocumentChunk.objects.filter(summary=s, embedding__isnull=False).exists()
    try:
        with transaction.atomic():
            OperationsDocumentChunk.objects.filter(summary=s).delete()
            count, embedded, model = agent._chunk_embed_and_store(
                s, s.parsed_text, s.page_count or 1, s.document_category or 'other',
                owner_kind='summary',
            )
            if had_vectors and not embedded:
                raise _NoVectors()      # keep the old vectors (CO-266)
            s.is_indexed = embedded
            s.embedding_model = model or ''
            s.processing_status = 'ready'
            s.save(update_fields=['is_indexed', 'embedding_model', 'processing_status'])
    except _NoVectors:
        OperationsDocumentSummary.objects.filter(pk=s.pk).update(processing_status='ready')
        return {'status': 'not_embedded', 'summary_id': summary_id}
    _invalidate_operations_indexes(s.company_id, embedded)
    return {'status': 'ready', 'summary_id': summary_id, 'chunks': count, 'embedded': embedded}


if shared_task is not None:
    @shared_task(name='operations_agent.tasks.reindex_operations_document',
                 bind=True, max_retries=1, default_retry_delay=30)
    def reindex_operations_document(self, document_id):
        return _reindex_impl(document_id)
else:  # pragma: no cover
    def reindex_operations_document(document_id):
        return _reindex_impl(document_id)


def _alert_deadlines_impl(today=None):
    """Every morning: deadlines in ready summaries that have come within a week get their alert.

    Summaries are read without their full text, and only those that list deadlines are looked at."""
    from datetime import timedelta
    from django.utils import timezone
    from .models import OperationsDocumentSummary
    from .signals import alert_upcoming_deadlines
    today = today or timezone.now().date()
    summaries = (OperationsDocumentSummary.objects
                 .filter(processing_status='ready', created_at__gte=timezone.now() - timedelta(days=400))
                 .exclude(deadlines=[])
                 .select_related('company')
                 .defer('rich_summary', 'parsed_text', 'entities', 'key_findings'))
    alerts = 0
    for summary in summaries.iterator(chunk_size=200):
        if summary.deadlines and alert_upcoming_deadlines(summary, today):
            alerts += 1
    return alerts


if shared_task is not None:
    @shared_task(name='operations_agent.tasks.alert_operations_deadlines')
    def alert_operations_deadlines():
        return _alert_deadlines_impl()
else:  # pragma: no cover
    def alert_operations_deadlines():
        return _alert_deadlines_impl()

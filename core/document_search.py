"""Whether a company's document search finds answers by meaning or only by matching words (CO-70).

HR and Frontline share one embedding engine (core/Frontline_agent/embedding_service.py). When it has no provider, or
a batch call fails, chunks are stored without vectors and the document is still marked ready, so search quietly falls
back to keyword matching and the upload pop-up still said "N chunk(s) embedded". These helpers say which it is, and
fill the missing vectors once a provider works. Operations has its own banner (api/views/operations_agent.py).
"""
import json
import logging

from django.core.cache import cache
from django.db.models import Q

logger = logging.getLogger(__name__)

_CACHE_SECONDS = 600

# agent -> (chunk model, its company lookup, document model)
AGENTS = {
    'hr_agent': ('hr_agent.HRDocumentChunk', 'document__company_id', 'hr_agent.HRDocument'),
    'frontline_agent': ('Frontline_agent.DocumentChunk', 'document__company_id', 'Frontline_agent.Document'),
}


def _models(agent):
    from django.apps import apps
    chunk, lookup, document = AGENTS[agent]
    return apps.get_model(chunk), lookup, apps.get_model(document)


def _cache_key(company_id, agent):
    return f'embedding-provider:{agent}:{company_id}'


def provider_available(company_id, agent):
    """Whether an embedding provider works for this company and agent. Building the service loads the local model,
    so the answer is kept for ten minutes."""
    hit = cache.get(_cache_key(company_id, agent))
    if hit is not None:
        return hit
    try:
        from core.Frontline_agent.embedding_service import EmbeddingService
        ok = EmbeddingService(company_id=company_id, agent_key_name=agent).is_available()
    except Exception:
        logger.exception('document_search: could not build the embedding service')
        ok = False
    cache.set(_cache_key(company_id, agent), ok, _CACHE_SECONDS)
    return ok


def _without_vectors(chunks):
    return chunks.filter(Q(embedding__isnull=True) | Q(embedding=''))


def status(company_id, agent):
    """{'mode': 'meaning' | 'partly' | 'words', 'provider_available', 'chunks', 'chunks_without_vectors'}."""
    chunk_model, lookup, _ = _models(agent)
    chunks = chunk_model.objects.filter(**{lookup: company_id})
    total = chunks.count()
    missing = _without_vectors(chunks).count() if total else 0
    available = provider_available(company_id, agent)
    mode = 'words' if not available else ('partly' if missing else 'meaning')
    return {'mode': mode, 'provider_available': available, 'chunks': total, 'chunks_without_vectors': missing}


def vectors_in(document):
    """How many of one document's chunks have a vector (for the upload pop-up)."""
    return document.chunks.exclude(Q(embedding__isnull=True) | Q(embedding='')).count()


def fill_missing_vectors(company_id, agent):
    """Give every chunk of the company's documents that has no vector one. Returns how many got one."""
    from core.Frontline_agent.embedding_service import EmbeddingService
    chunk_model, lookup, document_model = _models(agent)
    service = EmbeddingService(company_id=company_id, agent_key_name=agent)
    cache.set(_cache_key(company_id, agent), service.is_available(), _CACHE_SECONDS)
    if not service.is_available():
        return 0
    ids = list(_without_vectors(chunk_model.objects.filter(**{lookup: company_id}))
               .order_by('pk').values_list('pk', flat=True))
    batch, done, documents = service.recommended_batch_size, 0, set()
    for start in range(0, len(ids), batch):
        rows = list(chunk_model.objects.filter(pk__in=ids[start:start + batch]))
        vectors = service.generate_embeddings_batch([row.chunk_text for row in rows])
        changed = []
        for row, vector in zip(rows, vectors):
            if vector:
                row.embedding = json.dumps(vector)
                changed.append(row)
                documents.add(row.document_id)
        chunk_model.objects.bulk_update(changed, ['embedding'])
        done += len(changed)
    if documents:
        (document_model.objects.filter(pk__in=documents)
         .filter(Q(embedding_model='') | Q(embedding_model__isnull=True))
         .update(embedding_model=service.embedding_model))
        if agent == 'hr_agent':
            from hr_agent.vector_store import mark_index_dirty
            from core.HR_agent.hr_agent import invalidate_answer_cache_for_company
        else:
            from Frontline_agent.vector_store import mark_index_dirty
            from core.Frontline_agent.frontline_agent import invalidate_answer_cache_for_company
        mark_index_dirty(company_id)
        invalidate_answer_cache_for_company(company_id)
    logger.info('document_search: %s vectors filled for company %s (%s)', done, company_id, agent)
    return done

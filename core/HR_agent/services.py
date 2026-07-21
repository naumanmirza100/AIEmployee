"""HR Support Agent — knowledge retrieval + employee context.

`HRKnowledgeService` runs RAG over `HRDocument` + `HRDocumentChunk`. It uses
the same `EmbeddingService` and `vector_store` as Frontline so we don't fork
the embedding stack. The HR-specific bits are:

  * **Confidentiality gate.** Documents tagged `manager` / `hr_only` are
    filtered out for ICs. Personal docs (with `employee` FK set) are visible
    only to that employee + HR.
  * **Employee context injection.** Given the asker's `Employee`, we can
    stitch their leave balances / manager into the prompt — turns "how many
    PTO days do I have?" from "I don't know who you are" into a real answer.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
from typing import List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

try:
    import numpy as _np  # type: ignore
    _HAS_NUMPY = True
except Exception:  # pragma: no cover - numpy is standard on servers but fall back gracefully
    _np = None
    _HAS_NUMPY = False


# ---------------------------------------------------------------------------
# In-process caches. Cheap wins that dominate query latency for large docs:
#   * `_CHUNK_EMBEDDING_CACHE` — parsed numpy vectors keyed by chunk_id so we
#     stop paying `json.loads` on every retrieval call.
#   * `_QUERY_EMBEDDING_CACHE` — most-recent question embeddings, since a user
#     often re-asks or refines the same question multiple times.
#   * `_CHUNK_JUNK_CACHE` — flags chunks that look like TOC/index rows so we
#     skip them at retrieval time even for docs indexed before the chunker fix.
# All bounded by `_CACHE_MAX` to avoid memory bloat.
# ---------------------------------------------------------------------------
_CACHE_LOCK = threading.Lock()
_CHUNK_EMBEDDING_CACHE: dict = {}    # chunk_id -> vector (numpy array or list)
_CHUNK_JUNK_CACHE: dict = {}         # chunk_id -> bool
_QUERY_EMBEDDING_CACHE: dict = {}    # sha256(query) -> vector
_CACHE_MAX = 20_000                  # cap total chunk-embedding entries


def _parse_embedding(raw):
    """Return a vector suitable for cosine math, or None. Uses numpy when
    available. Called from `_semantic_score`; results are cached per chunk."""
    if raw is None:
        return None
    try:
        vec = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return None
    if not vec:
        return None
    if _HAS_NUMPY:
        try:
            arr = _np.asarray(vec, dtype=_np.float32)
            if arr.size == 0:
                return None
            return arr
        except Exception:
            return vec
    return vec


def _cache_get_chunk_vec(chunk_id: int, raw):
    """Fetch a chunk's parsed embedding vector, using the module-level cache."""
    with _CACHE_LOCK:
        hit = _CHUNK_EMBEDDING_CACHE.get(chunk_id)
        if hit is not None:
            return hit
    vec = _parse_embedding(raw)
    if vec is None:
        return None
    with _CACHE_LOCK:
        if len(_CHUNK_EMBEDDING_CACHE) >= _CACHE_MAX:
            # Cheapest eviction: drop half the cache. Prevents unbounded growth.
            for k in list(_CHUNK_EMBEDDING_CACHE.keys())[: _CACHE_MAX // 2]:
                _CHUNK_EMBEDDING_CACHE.pop(k, None)
        _CHUNK_EMBEDDING_CACHE[chunk_id] = vec
    return vec


def _cache_get_query_vec(query: str, embedding_service):
    """Fetch (and cache) an embedding vector for a query string."""
    key = hashlib.sha256((query or '').strip().lower().encode('utf-8')).hexdigest()
    with _CACHE_LOCK:
        hit = _QUERY_EMBEDDING_CACHE.get(key)
        if hit is not None:
            return hit
    raw = embedding_service.generate_embedding(query)
    if not raw:
        return None
    vec = _parse_embedding(raw)
    if vec is None:
        return None
    with _CACHE_LOCK:
        if len(_QUERY_EMBEDDING_CACHE) > 512:
            for k in list(_QUERY_EMBEDDING_CACHE.keys())[:256]:
                _QUERY_EMBEDDING_CACHE.pop(k, None)
        _QUERY_EMBEDDING_CACHE[key] = vec
    return vec


def _semantic_score(qvec, cvec):
    """Cosine similarity, using numpy when available."""
    if qvec is None or cvec is None:
        return None
    if _HAS_NUMPY and isinstance(qvec, _np.ndarray) and isinstance(cvec, _np.ndarray):
        if qvec.shape != cvec.shape:
            return None
        denom = float(_np.linalg.norm(qvec)) * float(_np.linalg.norm(cvec))
        if denom == 0.0:
            return None
        return float(_np.dot(qvec, cvec) / denom)
    return _cosine(qvec, cvec)


def _is_junk_chunk(chunk_id, text) -> bool:
    """Cached wrapper around the chunker's TOC/index heuristic."""
    with _CACHE_LOCK:
        hit = _CHUNK_JUNK_CACHE.get(chunk_id)
        if hit is not None:
            return hit
    try:
        from hr_agent.chunking import _looks_like_toc_or_index
        verdict = _looks_like_toc_or_index(text or '')
    except Exception:
        verdict = False
    with _CACHE_LOCK:
        if len(_CHUNK_JUNK_CACHE) >= _CACHE_MAX:
            for k in list(_CHUNK_JUNK_CACHE.keys())[: _CACHE_MAX // 2]:
                _CHUNK_JUNK_CACHE.pop(k, None)
        _CHUNK_JUNK_CACHE[chunk_id] = verdict
    return verdict


HR_RANKED_CONFIDENTIALITY = ['public', 'employee', 'manager', 'hr_only']


def _allowed_confidentialities(role: str) -> list[str]:
    """Map an asker role to the list of confidentiality levels they can see.

    ``role`` is one of ``'employee'``, ``'manager'``, ``'hr'``, ``'public'``.
    """
    if role == 'public':
        return ['public']
    if role == 'employee':
        return ['public', 'employee']
    if role == 'manager':
        return ['public', 'employee', 'manager']
    if role == 'hr':
        return HR_RANKED_CONFIDENTIALITY
    return ['public']


class HRKnowledgeService:
    """RAG over HR documents, gated by confidentiality + per-employee scope."""

    def __init__(self, company_id: Optional[int] = None):
        self.company_id = company_id
        # Lazy-imported to avoid a hard dependency at scaffold time.
        from core.Frontline_agent.embedding_service import EmbeddingService
        self.embedding_service = EmbeddingService()
        # Per-call sub-phase timing so the UI + logs can pinpoint which step
        # is slow (query_embed / json_scan / keyword / chunk_fetch / …).
        # Mirrors the Frontline `KnowledgeService` shape.
        self.last_retrieval_timing: dict = {}
        self.last_retrieval_path: str = ''

    def get_answer(self, question: str, *, asker_role: str = 'employee',
                   asker_employee_id: Optional[int] = None,
                   max_results: int = 5) -> dict:
        """Retrieve top chunks and return the same shape Frontline uses
        (`answer`, `has_verified_info`, `confidence`, `citations`,
        `best_score`, `threshold`)."""
        results = self.search_knowledge(
            question, asker_role=asker_role,
            asker_employee_id=asker_employee_id, max_results=max_results,
        )
        if not results:
            return {
                'success': True, 'answer': None, 'has_verified_info': False,
                'confidence': 'none', 'citations': [],
                'message': 'No verified HR knowledge found for this question.',
            }
        threshold = float(getattr(settings, 'HR_RAG_MIN_CONFIDENCE',
                                  getattr(settings, 'FRONTLINE_RAG_MIN_CONFIDENCE', 0.3)))
        best = results[0]
        sem = best.get('semantic_score')
        if sem is not None and float(sem) < threshold:
            return {
                'success': True, 'answer': None, 'has_verified_info': False,
                'confidence': 'low', 'best_score': float(sem),
                'threshold': threshold, 'citations': [],
                'message': 'No sufficiently confident HR match found.',
            }
        # Aggregate top chunks into a single context block
        content = "\n\n".join(
            f"--- Source: {r.get('title','Unknown')} ---\n{r.get('content','')}"
            for r in results
        )
        citations = [{
            'type': 'hr_document',
            'title': r.get('title'),
            'section_heading': r.get('section_heading') or '',
            'document_id': r.get('document_id'),
            'chunk_id': r.get('chunk_id'),
            'score': round(float(r['semantic_score']), 3) if r.get('semantic_score') is not None else None,
            'snippet': (r.get('content') or '')[:200],
        } for r in results]
        return {
            'success': True,
            'answer': content,
            'has_verified_info': True,
            'confidence': 'high' if sem and sem >= max(threshold + 0.2, 0.5) else 'medium',
            'best_score': sem,
            'threshold': threshold,
            'citations': citations,
        }

    def search_knowledge(self, query: str, *, asker_role: str = 'employee',
                         asker_employee_id: Optional[int] = None,
                         max_results: int = 5) -> List[dict]:
        """Hybrid retrieval (semantic + keyword) over the company's HR docs.

        Returns a flat list of result dicts with `chunk_id`, `document_id`,
        `title`, `content`, `semantic_score`. Mirrors the Frontline service's
        output shape so views can render citations identically.
        """
        import time as _time
        from hr_agent.models import HRDocument, HRDocumentChunk

        # Reset per-call timing counters.
        _t0 = _time.time()
        self.last_retrieval_timing = {}
        self.last_retrieval_path = ''

        _t = _time.time()
        docs = HRDocument.objects.filter(
            company_id=self.company_id,
            is_indexed=True,
            processing_status='ready',
            superseded_by__isnull=True,  # never retrieve old revisions
            is_outdated=False,            # D-F2 — skip soft-deprecated docs too
        )
        # Confidentiality gate
        allowed_levels = _allowed_confidentialities(asker_role)
        docs = docs.filter(confidentiality__in=allowed_levels)
        # Personal-doc gate: an employee sees only their own personal docs
        # (or no employee filter at all if HR is asking).
        if asker_role != 'hr':
            from django.db.models import Q
            personal_ok = Q(employee__isnull=True)
            if asker_employee_id:
                personal_ok |= Q(employee_id=asker_employee_id)
            docs = docs.filter(personal_ok)

        doc_ids = list(docs.values_list('id', flat=True))
        self.last_retrieval_timing['doc_filter'] = int((_time.time() - _t) * 1000)
        if not doc_ids:
            return []

        # Pull only the columns we actually need for scoring. `select_related`
        # is dropped — we only need `document.title` for the small subset that
        # ranks; we re-fetch those with `document_id__in` at the very end.
        chunks_qs = HRDocumentChunk.objects.filter(
            document_id__in=doc_ids,
        ).only('id', 'document_id', 'embedding', 'chunk_text',
               'section_heading', 'page_number', 'chunk_index')

        # Semantic via embedding service if available
        semantic_hits: list[tuple[int, float]] = []
        if self.embedding_service.is_available():
            _t = _time.time()
            qvec = _cache_get_query_vec(query, self.embedding_service)
            self.last_retrieval_timing['query_embed'] = int((_time.time() - _t) * 1000)
            if qvec is not None:
                # -------- FAISS path (O(log N)) --------
                # Try FAISS first — for a company with 1000+ chunks this is
                # ~10ms vs 200 seconds for the Python scan.
                used_faiss = False
                try:
                    from hr_agent import vector_store as _vs
                    if _vs.FAISS_AVAILABLE:
                        _t_faiss = _time.time()
                        store = _vs.get_store(self.company_id)
                        store_ready_ms = int((_time.time() - _t_faiss) * 1000)
                        if store is not None:
                            self.last_retrieval_path += f'faiss(store_ready={store_ready_ms}ms)|'
                            # Candidate set = chunk IDs surviving the confidentiality
                            # + personal-doc gates from the DB query above.
                            _t = _time.time()
                            candidate_ids = set(chunks_qs.values_list('id', flat=True))
                            self.last_retrieval_timing['faiss_candidates'] = int((_time.time() - _t) * 1000)
                            _t = _time.time()
                            hits = store.search(qvec, k=50, candidate_chunk_ids=candidate_ids)
                            self.last_retrieval_timing['faiss_search'] = int((_time.time() - _t) * 1000)
                            if hits:
                                used_faiss = True
                                semantic_hits = [(cid, float(score)) for cid, score in hits]
                                self.last_retrieval_path += f'hits={len(hits)}|'
                            else:
                                self.last_retrieval_path += 'faiss_empty|'
                        else:
                            # Store couldn't be built — no chunks yet or FAISS
                            # failed. Fall through to Python scan.
                            self.last_retrieval_path += 'faiss_no_store|'
                    else:
                        self.last_retrieval_path += 'faiss_unavailable|'
                except Exception as exc:
                    logger.warning("HR FAISS retrieval failed: %s — falling back", exc)
                    self.last_retrieval_path += 'faiss_error|'

                # -------- Python-scan fallback --------
                # Only runs when FAISS didn't return usable hits (no library,
                # no built store yet, or dim mismatch). Slower but correct.
                if not used_faiss:
                    _t = _time.time()
                    scanned = 0
                    skipped_junk = 0
                    for c in chunks_qs.iterator(chunk_size=500):
                        scanned += 1
                        if not c.embedding:
                            continue
                        if _is_junk_chunk(c.id, c.chunk_text):
                            skipped_junk += 1
                            continue
                        cvec = _cache_get_chunk_vec(c.id, c.embedding)
                        if cvec is None:
                            continue
                        score = _semantic_score(qvec, cvec)
                        if score is not None:
                            semantic_hits.append((c.id, score))
                    semantic_hits.sort(key=lambda x: x[1], reverse=True)
                    semantic_hits = semantic_hits[:50]
                    self.last_retrieval_timing['json_scan'] = int((_time.time() - _t) * 1000)
                    self.last_retrieval_timing['json_scan_chunks'] = scanned
                    self.last_retrieval_path += f'json_scan|scanned={scanned},junk={skipped_junk}|'
        else:
            self.last_retrieval_path += 'no_embeddings|'

        # Keyword fallback (cheap) — searches both body text AND the section
        # heading so queries like "LEAVE POLICY" or "Article 4" hit chunks
        # whose heading matches even if the body text doesn't.
        _t = _time.time()
        from django.db.models import Q as _Q
        keyword_hits: list[int] = list(
            chunks_qs.filter(
                _Q(chunk_text__icontains=query[:80])
                | _Q(section_heading__icontains=query[:80])
            ).values_list('id', flat=True)[:50]
        )
        self.last_retrieval_timing['keyword'] = int((_time.time() - _t) * 1000)

        # Cheap RRF merge (k=60)
        rrf: dict[int, float] = {}
        sem_score: dict[int, float] = {}
        for rank, (cid, s) in enumerate(semantic_hits):
            rrf[cid] = rrf.get(cid, 0) + 1 / (60 + rank + 1)
            sem_score[cid] = float(s)
        for rank, cid in enumerate(keyword_hits):
            rrf[cid] = rrf.get(cid, 0) + 1 / (60 + rank + 1)

        ordered = sorted(rrf.items(), key=lambda kv: kv[1], reverse=True)[: max_results * 2]
        if not ordered:
            return []

        # Re-fetch only the small ranked subset with document title joined in.
        # `.only(...)` + fresh queryset from `HRDocumentChunk.objects` avoids
        # the MSSQL query-plan issue that hit Frontline (chaining
        # `.filter()` on top of a queryset with `select_related` triggered a
        # pathological plan on MSSQL that cost >170s for 50 rows).
        _t = _time.time()
        top_ids = [cid for cid, _ in ordered]
        chunk_map = {c.id: c for c in HRDocumentChunk.objects
                     .filter(id__in=top_ids)
                     .select_related('document')
                     .only('id', 'document_id', 'chunk_text', 'chunk_index',
                           'section_heading', 'page_number',
                           'document__title')}
        self.last_retrieval_timing['chunk_fetch'] = int((_time.time() - _t) * 1000)

        _t = _time.time()
        out: list[dict] = []
        dropped_junk = 0
        for cid, _ in ordered:
            c = chunk_map.get(cid)
            if not c:
                continue
            # Defense-in-depth: keyword branch can surface junk chunks that
            # the semantic branch already rejected.
            if _is_junk_chunk(c.id, c.chunk_text):
                dropped_junk += 1
                continue
            heading = getattr(c, 'section_heading', '') or ''
            page = getattr(c, 'page_number', None)
            page_label = f" p.{page}" if page else ""
            out.append({
                'chunk_id': c.id,
                'document_id': c.document_id,
                'title': (f"{c.document.title} — {heading}{page_label}" if heading
                          else f"{c.document.title} (Chunk {c.chunk_index}{page_label})"),
                'section_heading': heading,
                'page_number': page,
                'content': c.chunk_text,
                'semantic_score': sem_score.get(cid),
            })
        self.last_retrieval_timing['output_build'] = int((_time.time() - _t) * 1000)
        self.last_retrieval_timing['search_total'] = int((_time.time() - _t0) * 1000)
        self.last_retrieval_path += f'kept={len(out)},dropped_junk={dropped_junk}|'
        logger.info(
            "HR retrieval breakdown (ms): %s path=%s",
            self.last_retrieval_timing, self.last_retrieval_path,
        )
        return out[:max_results]


def _cosine(a, b):
    if not a or not b:
        return None
    if len(a) != len(b):
        return None
    try:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return None
        return dot / (na * nb)
    except Exception:
        return None


def build_employee_context(employee) -> dict:
    """Build the personalisation payload that gets injected into Knowledge Q&A
    prompts. Pulls the bits we know are useful (manager, leave balances) and
    skips anything sensitive like salary."""
    if not employee:
        return {}
    ctx: dict = {
        'full_name': employee.full_name,
        'job_title': employee.job_title,
        'department': employee.department,
    }
    if employee.manager_id:
        ctx['manager_name'] = employee.manager.full_name if employee.manager else None
    balances = []
    for b in employee.leave_balances.all():
        balances.append({
            'leave_type': b.leave_type,
            'remaining': b.remaining,
        })
    if balances:
        ctx['leave_balances'] = balances
    return ctx

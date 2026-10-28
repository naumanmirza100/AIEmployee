"""Per-company FAISS vector index for Operations knowledge retrieval.

Mirrors ``hr_agent.vector_store`` / ``Frontline_agent.vector_store`` — see those
modules for the design rationale. Differences here:

* Reads from ``OperationsDocumentChunk`` (``embedding`` is a JSONField, so it
  may arrive as a native list rather than a JSON string).
* Filters by ``document__company_id`` (same relation shape as HR/Frontline).
* On-disk indexes live under
  ``MEDIA_ROOT/operations_vector_indexes/company_<id>.{faiss,meta.json}`` so the
  agents don't collide.

Rebuild triggers: ``mark_index_dirty(company_id)`` is called from the Operations
document processing task after each successful embed. Next query loads the
index; if dirty, it's rebuilt from scratch.

Falls back to the legacy JSON scan when FAISS isn't importable.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import List, Optional, Tuple

from django.conf import settings

logger = logging.getLogger(__name__)


try:
    import faiss  # type: ignore
    import numpy as np
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    faiss = None  # type: ignore
    np = None  # type: ignore

# Startup visibility — one log line per process. If a deployment requires
# FAISS (``OPERATIONS_REQUIRE_FAISS=True``), fail loud at import time rather
# than silently serve slow queries in prod.
if FAISS_AVAILABLE:
    logger.info("Operations vector store: FAISS active (O(log N) retrieval).")
else:
    _msg = (
        "Operations vector store: FAISS NOT INSTALLED — falling back to "
        "keyword retrieval (fine for small corpora, no semantic match)."
    )
    if getattr(settings, 'OPERATIONS_REQUIRE_FAISS', False):
        logger.error(_msg)
        raise RuntimeError(
            "OPERATIONS_REQUIRE_FAISS=True but faiss is not importable. "
            "Install faiss-cpu (or set OPERATIONS_REQUIRE_FAISS=False)."
        )
    logger.warning(_msg)


# In-process cache — avoid re-loading the index file on every query.
_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()


def _index_dir() -> Path:
    # Pin under LOCAL_STORAGE_ROOT — MEDIA_ROOT is '' when S3 is on, which would
    # otherwise drop the index files into the project root.
    root = getattr(settings, 'LOCAL_STORAGE_ROOT', None) or getattr(settings, 'MEDIA_ROOT', '.') or '.'
    base = Path(root) / 'operations_vector_indexes'
    base.mkdir(parents=True, exist_ok=True)
    return base


def _paths(company_id: int) -> tuple:
    d = _index_dir()
    return (
        d / f'company_{company_id}.faiss',
        d / f'company_{company_id}.meta.json',
        d / f'company_{company_id}.dirty',
    )


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def get_store(company_id: int) -> Optional['OperationsFaissVectorStore']:
    """Return a ready-to-search store for ``company_id`` or None if FAISS is
    unavailable or the company has no indexable chunks yet."""
    if not FAISS_AVAILABLE:
        return None
    if not company_id:
        return None
    with _CACHE_LOCK:
        store = _CACHE.get(company_id)
        if store is not None and not store.needs_rebuild():
            return store
        store = OperationsFaissVectorStore(company_id)
        if not store.ensure_ready():
            return None
        _CACHE[company_id] = store
        return store


def mark_index_dirty(company_id: int) -> None:
    """Signal that the index for a company should be rebuilt on next query."""
    if not company_id:
        return
    _faiss_path, _meta_path, dirty_path = _paths(company_id)
    try:
        dirty_path.touch()
    except OSError as exc:
        logger.warning("Operations mark_index_dirty(%s) failed: %s", company_id, exc)
    with _CACHE_LOCK:
        _CACHE.pop(company_id, None)


def evict(company_id: int) -> None:
    """Drop the in-process cache entry for a company."""
    with _CACHE_LOCK:
        _CACHE.pop(company_id, None)


# --------------------------------------------------------------------------
# OperationsFaissVectorStore
# --------------------------------------------------------------------------

class OperationsFaissVectorStore:
    """FAISS ``IndexFlatIP`` + chunk-id mapping for one company's Operations
    docs. Build path: read every ``OperationsDocumentChunk`` with an embedding
    for this company, normalize, add to the index. Meta file holds the row → id
    mapping and embedding dim.
    """

    def __init__(self, company_id: int):
        self.company_id = company_id
        self.faiss_path, self.meta_path, self.dirty_path = _paths(company_id)
        self.index = None
        self.chunk_ids: List[int] = []
        self.dim: int = 0

    # ---- lifecycle -----------------------------------------------------

    def needs_rebuild(self) -> bool:
        if not self.faiss_path.exists() or not self.meta_path.exists():
            return True
        if self.dirty_path.exists():
            return True
        return False

    def ensure_ready(self) -> bool:
        if self.needs_rebuild():
            built = self._build_from_db()
            if not built:
                return False
            self._clear_dirty()
            return True
        return self._load_from_disk()

    # ---- public search -------------------------------------------------

    def search(self, query_vec, k: int = 25,
               candidate_chunk_ids: Optional[set] = None) -> List[Tuple[int, float]]:
        """Return up to ``k`` ``(chunk_id, score)`` tuples ordered by score desc.

        Scores are cosine similarities in [-1, 1]. When ``candidate_chunk_ids``
        is provided, results are filtered to only those ids — used by the caller
        to scope to the company's processed documents (or a document filter).
        """
        if self.index is None or not self.chunk_ids:
            return []
        q = np.asarray(query_vec, dtype='float32').reshape(1, -1)
        if q.shape[1] != self.dim:
            logger.warning("Operations FAISS query dim mismatch: query=%d index=%d (company=%s)",
                           q.shape[1], self.dim, self.company_id)
            return []
        _normalize_inplace(q)
        fetch = k if not candidate_chunk_ids else min(k * 4, len(self.chunk_ids))
        scores, idx_rows = self.index.search(q, fetch)
        out: List[Tuple[int, float]] = []
        for score, row in zip(scores[0].tolist(), idx_rows[0].tolist()):
            if row < 0 or row >= len(self.chunk_ids):
                continue
            cid = self.chunk_ids[row]
            if candidate_chunk_ids is not None and cid not in candidate_chunk_ids:
                continue
            out.append((cid, float(score)))
            if len(out) >= k:
                break
        return out

    # ---- internals -----------------------------------------------------

    def _build_from_db(self) -> bool:
        """Read the company's OperationsDocumentChunks and build the FAISS index
        from scratch. Returns False when nothing indexable exists."""
        from django.db.models import Q
        from operations_agent.models import OperationsDocumentChunk

        # Chunks belong to either a document or a summary — index both. The vectors of the model now in use, on
        # purpose: the first vector found set the index's size and every vector of another model was skipped, so
        # documents embedded with an earlier model dropped out of meaning-based search while still marked indexed
        # (CO-279). Those are re-embedded with the current model in the background.
        current = _current_embedding_model(self.company_id)
        qs = (OperationsDocumentChunk.objects
              .filter(Q(document__company_id=self.company_id)
                      | Q(summary__company_id=self.company_id))
              .exclude(embedding__isnull=True)
              .values_list('id', 'embedding', 'document__embedding_model', 'summary__embedding_model')
              .iterator(chunk_size=2000))

        vecs: List[List[float]] = []
        ids: List[int] = []
        dim = 0
        for chunk_id, embedding, doc_model, summary_model in qs:
            model = doc_model or summary_model or ''
            if current and model and model != current:
                continue
            try:
                # JSONField may hand back a native list; older/string payloads
                # are JSON-decoded.
                emb = json.loads(embedding) if isinstance(embedding, str) else embedding
                if not emb or not isinstance(emb, list):
                    continue
                if dim == 0:
                    dim = len(emb)
                elif len(emb) != dim:
                    continue
                vecs.append(emb)
                ids.append(chunk_id)
            except Exception:
                continue
        if current:
            _reembed_other_models(self.company_id, current)

        if not vecs:
            logger.info("Operations FAISS build skipped for company %s: no embeddings found",
                        self.company_id)
            return False

        mat = np.asarray(vecs, dtype='float32')
        _normalize_inplace(mat)
        index = faiss.IndexFlatIP(dim)
        index.add(mat)
        self.index = index
        self.chunk_ids = ids
        self.dim = dim
        self._save_to_disk()
        logger.info("Operations FAISS index built for company %s: %d chunks, dim=%d",
                    self.company_id, len(ids), dim)
        return True

    def _save_to_disk(self) -> None:
        try:
            faiss.write_index(self.index, str(self.faiss_path))
            with open(self.meta_path, 'w', encoding='utf-8') as fh:
                json.dump({'chunk_ids': self.chunk_ids, 'dim': self.dim,
                           'count': len(self.chunk_ids)}, fh)
        except Exception as exc:
            logger.exception("Operations FAISS save failed for company %s: %s", self.company_id, exc)

    def _load_from_disk(self) -> bool:
        try:
            self.index = faiss.read_index(str(self.faiss_path))
            with open(self.meta_path, 'r', encoding='utf-8') as fh:
                meta = json.load(fh)
            self.chunk_ids = list(meta.get('chunk_ids') or [])
            self.dim = int(meta.get('dim') or 0)
            return bool(self.chunk_ids and self.dim)
        except Exception as exc:
            logger.warning("Operations FAISS load failed for company %s: %s — rebuilding",
                           self.company_id, exc)
            return self._build_from_db()

    def _clear_dirty(self) -> None:
        try:
            if self.dirty_path.exists():
                os.remove(self.dirty_path)
        except OSError:
            pass


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _current_embedding_model(company_id) -> str:
    """The embedding model the company's search uses now, or '' when no provider answers."""
    try:
        from operations_agent.agents.document_processing_agent import build_embedding_service
        svc = build_embedding_service(company_id)
        if svc is not None and svc.is_available():
            return getattr(svc, 'embedding_model', '') or ''
    except Exception:
        logger.debug("Operations: no current embedding model for company %s", company_id)
    return ''


_REEMBED_QUEUED: set = set()


def _reembed_other_models(company_id, current: str) -> None:
    """Re-embed, in one background thread, the company's indexed documents and summaries whose vectors came from
    another model, at most 20 a time and each once per process (CO-279)."""
    from django.db.models import Q
    from operations_agent.models import OperationsDocument, OperationsDocumentSummary
    other = Q(is_indexed=True) & ~Q(embedding_model='') & ~Q(embedding_model=current)
    docs = [('d', i) for i in OperationsDocument.objects.filter(other, company_id=company_id)
            .values_list('id', flat=True)[:20]]
    sums = [('s', i) for i in OperationsDocumentSummary.objects.filter(other, company_id=company_id)
            .values_list('id', flat=True)[:20]]
    todo = [key for key in docs + sums if key not in _REEMBED_QUEUED][:20]
    if not todo:
        return
    _REEMBED_QUEUED.update(todo)
    logger.info("Operations: re-embedding %d entries of company %s with %s", len(todo), company_id, current)

    def _run():
        from django.db import close_old_connections
        from operations_agent.tasks import _reindex_impl, _reindex_summary_impl
        close_old_connections()
        try:
            for kind, row_id in todo:
                try:
                    (_reindex_impl if kind == 'd' else _reindex_summary_impl)(row_id)
                except Exception:
                    logger.exception("Operations: re-embedding %s %s failed", kind, row_id)
        finally:
            close_old_connections()

    threading.Thread(target=_run, name='ops-reembed', daemon=True).start()


def _normalize_inplace(mat) -> None:
    """L2-normalize a 2-D numpy array in place. Zero-norm rows left as zero."""
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    mat /= norms

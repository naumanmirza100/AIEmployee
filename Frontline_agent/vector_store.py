"""Per-company FAISS vector index for Frontline knowledge retrieval.

Why: chunk embeddings sit as JSON strings in MSSQL. Scanning every row to
compute cosine against a query is O(N) in Python; it breaks beyond ~10k
chunks per tenant.

What: one ``IndexFlatIP`` per company persisted under
``MEDIA_ROOT/frontline_vector_indexes/company_<id>.{faiss,meta.json}``. Inner
product on L2-normalized vectors is mathematically cosine, so we normalize
once on build and never again. The ``.meta.json`` sidecar stores the row ↔
``DocumentChunk.id`` mapping plus the embedding dim so reload doesn't need
the DB.

Rebuild triggers: ``mark_index_dirty(company_id)`` — called from the
document-processing task. The next query loads the index; if dirty, it's
rebuilt from scratch. Incremental upserts are not worth the complexity
until we hit memory pressure rebuilding from scratch takes seconds, and the
pipeline already processes docs in a Celery worker.

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


# In-process cache — avoid re-loading the index file on every query.
# Keyed by company_id. Guarded by a lock so concurrent threads don't race.
_CACHE: dict[int, 'FaissVectorStore'] = {}
_CACHE_LOCK = threading.Lock()


def _index_dir() -> Path:
    base = Path(getattr(settings, 'MEDIA_ROOT', '.')) / 'frontline_vector_indexes'
    base.mkdir(parents=True, exist_ok=True)
    return base


def _paths(company_id: int) -> tuple[Path, Path, Path]:
    d = _index_dir()
    return (
        d / f'company_{company_id}.faiss',
        d / f'company_{company_id}.meta.json',
        d / f'company_{company_id}.dirty',
    )


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def get_store(company_id: int) -> Optional['FaissVectorStore']:
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
        store = FaissVectorStore(company_id)
        if not store.ensure_ready():
            return None
        _CACHE[company_id] = store
        return store


def mark_index_dirty(company_id: int) -> None:
    """Signal that the index for a company should be rebuilt on next query.
    Cheap — just touches a sidecar file. Safe to call from any process."""
    if not company_id:
        return
    _faiss_path, _meta_path, dirty_path = _paths(company_id)
    try:
        dirty_path.touch()
    except OSError as exc:
        logger.warning("mark_index_dirty(%s) failed: %s", company_id, exc)
    with _CACHE_LOCK:
        _CACHE.pop(company_id, None)


def evict(company_id: int) -> None:
    """Drop the in-process cache entry for a company. Used by tests and by
    hot-reload flows — does NOT delete the on-disk index."""
    with _CACHE_LOCK:
        _CACHE.pop(company_id, None)


# --------------------------------------------------------------------------
# FaissVectorStore
# --------------------------------------------------------------------------

class FaissVectorStore:
    """Thin wrapper around a FAISS ``IndexFlatIP`` + chunk-id mapping.

    Build path: read every ``DocumentChunk`` with an embedding for this
    company, normalize, add to the index. Meta file holds the row→id mapping
    and embedding dim.
    """

    def __init__(self, company_id: int):
        self.company_id = company_id
        self.faiss_path, self.meta_path, self.dirty_path = _paths(company_id)
        self.index = None       # faiss.IndexFlatIP
        self.chunk_ids: List[int] = []  # row i → DocumentChunk.id
        self.dim: int = 0

    # ---- lifecycle -----------------------------------------------------

    def needs_rebuild(self) -> bool:
        """True if either the on-disk index is missing or the dirty flag is set."""
        if not self.faiss_path.exists() or not self.meta_path.exists():
            return True
        if self.dirty_path.exists():
            return True
        return False

    def ensure_ready(self) -> bool:
        """Load-or-build the index. Returns False when no indexable chunks exist."""
        if self.needs_rebuild():
            built = self._build_from_db()
            if not built:
                return False
            self._clear_dirty()
            return True
        return self._load_from_disk()

    # ---- public search -------------------------------------------------

    def search(self, query_vec: List[float], k: int = 25,
               candidate_chunk_ids: Optional[set] = None) -> List[Tuple[int, float]]:
        """Return up to ``k`` ``(chunk_id, score)`` tuples ordered by score desc.

        Scores are cosine similarities in [-1, 1]. When ``candidate_chunk_ids``
        is provided, results are filtered to only those ids — used by the caller
        to apply multi-tenant + visibility + scope filters from the DB.
        """
        if self.index is None or not self.chunk_ids:
            return []
        q = np.asarray(query_vec, dtype='float32').reshape(1, -1)
        if q.shape[1] != self.dim:
            logger.warning("FAISS query dim mismatch: query=%d index=%d (company=%s)",
                           q.shape[1], self.dim, self.company_id)
            return []
        _normalize_inplace(q)
        # Over-fetch when filtering so post-filter has enough candidates to return k.
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
        """Read the company's DocumentChunks and build the FAISS index from
        scratch. Returns False when nothing indexable exists (caller should
        fall back to the JSON-scan path)."""
        from Frontline_agent.models import DocumentChunk

        qs = (DocumentChunk.objects
              .filter(document__company_id=self.company_id)
              .exclude(embedding__isnull=True)
              .exclude(embedding='')
              .values_list('id', 'embedding')
              .iterator(chunk_size=2000))

        vecs: List[List[float]] = []
        ids: List[int] = []
        dim = 0
        for chunk_id, embedding in qs:
            try:
                emb = json.loads(embedding) if isinstance(embedding, str) else embedding
                if not emb or not isinstance(emb, list):
                    continue
                if dim == 0:
                    dim = len(emb)
                elif len(emb) != dim:
                    # Skip dim-mismatched rows (model upgrade mid-flight) rather than crash.
                    continue
                vecs.append(emb)
                ids.append(chunk_id)
            except Exception:
                continue

        if not vecs:
            logger.info("FAISS build skipped for company %s: no embeddings found",
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
        logger.info("FAISS index built for company %s: %d chunks, dim=%d",
                    self.company_id, len(ids), dim)
        return True

    def _save_to_disk(self) -> None:
        try:
            faiss.write_index(self.index, str(self.faiss_path))
            with open(self.meta_path, 'w', encoding='utf-8') as fh:
                json.dump({'chunk_ids': self.chunk_ids, 'dim': self.dim,
                           'count': len(self.chunk_ids)}, fh)
        except Exception as exc:
            logger.exception("FAISS save failed for company %s: %s", self.company_id, exc)

    def _load_from_disk(self) -> bool:
        try:
            self.index = faiss.read_index(str(self.faiss_path))
            with open(self.meta_path, 'r', encoding='utf-8') as fh:
                meta = json.load(fh)
            self.chunk_ids = list(meta.get('chunk_ids') or [])
            self.dim = int(meta.get('dim') or 0)
            return bool(self.chunk_ids and self.dim)
        except Exception as exc:
            logger.warning("FAISS load failed for company %s: %s — rebuilding",
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

def _normalize_inplace(mat) -> None:
    """L2-normalize a 2-D numpy array in place. Zero-norm rows are left as zero
    (FAISS returns 0 similarity — equivalent to excluding the row)."""
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    mat /= norms

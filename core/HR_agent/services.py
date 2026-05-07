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

import json
import logging
import math
from typing import List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


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
        from hr_agent.models import HRDocument, HRDocumentChunk

        docs = HRDocument.objects.filter(
            company_id=self.company_id,
            is_indexed=True,
            processing_status='ready',
            superseded_by__isnull=True,  # never retrieve old revisions
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
        if not doc_ids:
            return []

        chunks = HRDocumentChunk.objects.filter(document_id__in=doc_ids).select_related('document')

        # Semantic via embedding service if available
        semantic_hits: list[tuple[int, float]] = []
        if self.embedding_service.is_available():
            qvec = self.embedding_service.generate_embedding(query)
            if qvec:
                # Walk chunks once — fine at scaffold scale; swap in FAISS later
                # mirroring `Frontline_agent.vector_store`.
                for c in chunks:
                    if not c.embedding:
                        continue
                    try:
                        vec = json.loads(c.embedding) if isinstance(c.embedding, str) else c.embedding
                    except Exception:
                        continue
                    score = _cosine(qvec, vec)
                    if score is not None:
                        semantic_hits.append((c.id, score))
                semantic_hits.sort(key=lambda x: x[1], reverse=True)
                semantic_hits = semantic_hits[:50]

        # Keyword fallback (cheap)
        keyword_hits: list[int] = list(
            chunks.filter(chunk_text__icontains=query[:80])
            .values_list('id', flat=True)[:50]
        )

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

        chunk_map = {c.id: c for c in chunks.filter(id__in=[cid for cid, _ in ordered])}
        out: list[dict] = []
        for cid, _ in ordered:
            c = chunk_map.get(cid)
            if not c:
                continue
            out.append({
                'chunk_id': c.id,
                'document_id': c.document_id,
                'title': f"{c.document.title} (Chunk {c.chunk_index})",
                'content': c.chunk_text,
                'semantic_score': sem_score.get(cid),
            })
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

"""HRAgent — main agent class. Mirrors Frontline's pattern:
extends ``BaseAgent`` so per-tenant key resolution + LLM cost tracking work,
and exposes high-level methods for each sub-agent (``answer_question``,
``summarize_document``, ``extract_meeting_action_items``, ...).
"""
from __future__ import annotations

import hashlib
import json as _json_top
import logging
import threading
import time
from typing import Optional

from django.conf import settings

from project_manager_agent.ai_agents.base_agent import BaseAgent
from .services import HRKnowledgeService, build_employee_context
from .prompts import HR_SYSTEM_PROMPT, get_knowledge_prompt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-process answer cache — mirrors the Frontline agent's cache. Repeat HR
# questions on the same doc corpus replay in sub-second time instead of
# incurring another LLM round-trip. TTL 5 minutes by default (override via
# `HR_ANSWER_CACHE_TTL_SECONDS`). Bounded to `_ANSWER_CACHE_MAX` entries.
# Only caches queries with no employee-specific personalisation, since those
# answers are per-employee.
# ---------------------------------------------------------------------------
_ANSWER_CACHE_LOCK = threading.Lock()
_ANSWER_CACHE: dict = {}
_ANSWER_CACHE_MAX = 2000


def _answer_cache_key(company_id, asker_role, question) -> str:
    payload = {
        'c': int(company_id or 0),
        'r': (asker_role or '').lower(),
        'q': (question or '').strip().lower(),
    }
    return hashlib.sha256(_json_top.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()


def _answer_cache_get(key: str, ttl_seconds: int):
    with _ANSWER_CACHE_LOCK:
        hit = _ANSWER_CACHE.get(key)
        if hit is None:
            return None
        ts, resp = hit
        if (time.time() - ts) > ttl_seconds:
            _ANSWER_CACHE.pop(key, None)
            return None
        return resp


def _answer_cache_put(key: str, resp: dict):
    with _ANSWER_CACHE_LOCK:
        if len(_ANSWER_CACHE) >= _ANSWER_CACHE_MAX:
            for k in list(_ANSWER_CACHE.keys())[: _ANSWER_CACHE_MAX // 2]:
                _ANSWER_CACHE.pop(k, None)
        _ANSWER_CACHE[key] = (time.time(), resp)


def invalidate_answer_cache_for_company(company_id):
    """Drop the whole HR answer cache when new content is indexed. A more
    granular cache would keep payloads alongside keys; since doc-change events
    are rare, a global clear is acceptable."""
    if not company_id:
        return
    with _ANSWER_CACHE_LOCK:
        _ANSWER_CACHE.clear()


class HRAgent(BaseAgent):
    """HR Support AI Agent — knowledge-grounded, employee-aware, PII-careful."""

    def __init__(self, company_id: Optional[int] = None):
        super().__init__()
        self.company_id = company_id
        # Per-tenant API key routing knows this agent by name.
        self.agent_key_name = 'hr_agent'
        self.knowledge_service = HRKnowledgeService(company_id=company_id)
        self.system_prompt = HR_SYSTEM_PROMPT
        logger.info("HRAgent initialized (company_id=%s)", company_id)

    # ---- Knowledge Q&A ----------------------------------------------------

    def answer_question(self, question: str, *, asker_role: str = 'employee',
                        asker_employee=None, max_results: int = 3) -> dict:
        """Q&A entry point. ``asker_role`` controls what the retriever is
        allowed to see; ``asker_employee`` (Employee instance, optional)
        unlocks personalised answers (their leave balance, manager etc.)."""
        # Per-phase timing so the UI + logs can pinpoint which step is slow.
        _t_overall = time.time()
        timing_ms: dict = {}

        # Answer cache: only for generic (non-personalised) queries. Employee-
        # specific answers (leave balance etc.) are not cached to avoid cross-
        # employee leaks and stale personal data.
        cache_ttl = int(getattr(settings, 'HR_ANSWER_CACHE_TTL_SECONDS', 300))
        cache_key = None
        if cache_ttl > 0 and asker_employee is None:
            cache_key = _answer_cache_key(self.company_id, asker_role, question)
            cached = _answer_cache_get(cache_key, cache_ttl)
            if cached is not None:
                logger.info("HR answer cache hit for company=%s q=%r",
                            self.company_id, question[:60])
                out = dict(cached)
                out['cache_hit'] = True
                out['timing_ms'] = {'total': int((time.time() - _t_overall) * 1000), 'cache': True}
                return out

        _t_retr = time.time()
        knowledge_result = self.knowledge_service.get_answer(
            question,
            asker_role=asker_role,
            asker_employee_id=getattr(asker_employee, 'id', None),
            max_results=max_results,
        )
        timing_ms['retrieval'] = int((time.time() - _t_retr) * 1000)
        # Sub-phase breakdown from the retrieval layer.
        try:
            timing_ms['retrieval_breakdown'] = dict(
                getattr(self.knowledge_service, 'last_retrieval_timing', {}) or {}
            )
            timing_ms['retrieval_path'] = getattr(self.knowledge_service, 'last_retrieval_path', '') or ''
        except Exception:
            pass

        if not knowledge_result.get('has_verified_info'):
            timing_ms['total'] = int((time.time() - _t_overall) * 1000)
            return {
                'success': True,
                'answer': "I don't have verified information on this in our HR knowledge base. "
                          "I'll route this to the HR team to follow up.",
                'has_verified_info': False,
                'confidence': knowledge_result.get('confidence', 'none'),
                'best_score': knowledge_result.get('best_score'),
                'threshold': knowledge_result.get('threshold'),
                'citations': [],
                'timing_ms': timing_ms,
            }

        # Format with the LLM, grounded in the retrieved excerpts + (optional) employee context.
        try:
            employee_context = build_employee_context(asker_employee) if asker_employee else None
            prompt = get_knowledge_prompt(question, [knowledge_result], employee_context=employee_context)
            _t_llm = time.time()
            # HR answers legitimately need more room than Frontline (policy
            # detail, leave-balance breakdowns, benefit tiers). Default 400
            # but tunable via `HR_QA_MAX_TOKENS` for tenants that want tighter
            # answers.
            formatted = self._call_llm(
                prompt=prompt,
                system_prompt=self.system_prompt,
                temperature=0.3,
                max_tokens=int(getattr(settings, 'HR_QA_MAX_TOKENS', 400)),
            )
            timing_ms['llm'] = int((time.time() - _t_llm) * 1000)
            timing_ms['total'] = int((time.time() - _t_overall) * 1000)
            logger.info("HR answer timing (ms): %s", timing_ms)
            response = {
                'success': True,
                'answer': formatted or knowledge_result.get('answer'),
                'has_verified_info': True,
                'confidence': knowledge_result.get('confidence'),
                'best_score': knowledge_result.get('best_score'),
                'threshold': knowledge_result.get('threshold'),
                'citations': knowledge_result.get('citations', []),
                'timing_ms': timing_ms,
            }
            if cache_key:
                _answer_cache_put(cache_key, response)
            return response
        except Exception as exc:
            from core.api_key_service import KeyServiceError
            if isinstance(exc, KeyServiceError):
                raise
            logger.exception("HRAgent.answer_question LLM formatting failed: %s", exc)
            return {
                'success': True,
                'answer': knowledge_result.get('answer'),
                'has_verified_info': True,
                'confidence': knowledge_result.get('confidence'),
                'citations': knowledge_result.get('citations', []),
            }

    # ---- Document summarisation / extraction ------------------------------

    def summarize_document(self, content: str, *, max_sentences: Optional[int] = None) -> dict:
        """Cheap LLM summary of an HR document's extracted text. Stub keeps
        the API surface predictable; tighten the prompt for HR docs later."""
        if not content or not content.strip():
            return {'success': False, 'error': 'No content to summarize.'}
        n = int(max_sentences or 5)
        prompt = (
            f"Summarize the HR document below in {n} concise sentences. "
            "Focus on policy scope, eligibility, and any deadlines or numeric thresholds. "
            "Do NOT add interpretation beyond the document.\n\n"
            f"<document>\n{content[:12000]}\n</document>"
        )
        try:
            summary = self._call_llm(
                prompt=prompt, system_prompt=self.system_prompt,
                temperature=0.2, max_tokens=400,
            )
            return {'success': True, 'summary': (summary or '').strip()}
        except Exception as exc:
            from core.api_key_service import KeyServiceError
            if isinstance(exc, KeyServiceError):
                raise
            logger.exception("HRAgent.summarize_document failed")
            return {'success': False, 'error': str(exc)}

    def extract_from_document(self, content: str, *, schema: Optional[list] = None) -> dict:
        """Extract structured fields from an HR document.

        Default schema covers the most common case (offer letter / contract).
        Pass `schema=[...]` to override.
        """
        if not content.strip():
            return {'success': False, 'error': 'No content to extract from.'}
        schema = schema or [
            'employee_name', 'job_title', 'department',
            'start_date', 'end_date',
            'compensation', 'currency',
            'reporting_manager', 'work_location',
            'probation_period_months',
        ]
        prompt = (
            "From the HR document below, extract these fields strictly as a JSON "
            "object with exactly these keys (use null when a field is not present):\n"
            f"  Keys: {', '.join(schema)}\n\n"
            "Output ONLY the JSON object, no commentary.\n\n"
            f"<document>\n{content[:12000]}\n</document>"
        )
        try:
            raw = self._call_llm(
                prompt=prompt, system_prompt=self.system_prompt,
                temperature=0.0, max_tokens=400,
            )
            import json
            s = (raw or '').strip()
            if s.startswith('```'):
                s = s.split('```', 2)[1]
                if s.startswith('json'):
                    s = s[4:]
                s = s.strip('` \n')
            try:
                data = json.loads(s)
            except Exception:
                return {'success': False, 'error': 'LLM did not return valid JSON', 'raw': s[:500]}
            return {'success': True, 'data': data}
        except Exception as exc:
            from core.api_key_service import KeyServiceError
            if isinstance(exc, KeyServiceError):
                raise
            logger.exception("HRAgent.extract_from_document failed")
            return {'success': False, 'error': str(exc)}

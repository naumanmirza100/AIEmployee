"""HRAgent — main agent class. Mirrors Frontline's pattern:
extends ``BaseAgent`` so per-tenant key resolution + LLM cost tracking work,
and exposes high-level methods for each sub-agent (``answer_question``,
``summarize_document``, ``extract_meeting_action_items``, ...).
"""
from __future__ import annotations

import logging
from typing import Optional

from project_manager_agent.ai_agents.base_agent import BaseAgent
from .services import HRKnowledgeService, build_employee_context
from .prompts import HR_SYSTEM_PROMPT, get_knowledge_prompt

logger = logging.getLogger(__name__)


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
                        asker_employee=None, max_results: int = 5) -> dict:
        """Q&A entry point. ``asker_role`` controls what the retriever is
        allowed to see; ``asker_employee`` (Employee instance, optional)
        unlocks personalised answers (their leave balance, manager etc.)."""
        knowledge_result = self.knowledge_service.get_answer(
            question,
            asker_role=asker_role,
            asker_employee_id=getattr(asker_employee, 'id', None),
            max_results=max_results,
        )
        if not knowledge_result.get('has_verified_info'):
            return {
                'success': True,
                'answer': "I don't have verified information on this in our HR knowledge base. "
                          "I'll route this to the HR team to follow up.",
                'has_verified_info': False,
                'confidence': knowledge_result.get('confidence', 'none'),
                'best_score': knowledge_result.get('best_score'),
                'threshold': knowledge_result.get('threshold'),
                'citations': [],
            }

        # Format with the LLM, grounded in the retrieved excerpts + (optional) employee context.
        try:
            employee_context = build_employee_context(asker_employee) if asker_employee else None
            prompt = get_knowledge_prompt(question, [knowledge_result], employee_context=employee_context)
            formatted = self._call_llm(
                prompt=prompt,
                system_prompt=self.system_prompt,
                temperature=0.3,
                max_tokens=500,
            )
            return {
                'success': True,
                'answer': formatted or knowledge_result.get('answer'),
                'has_verified_info': True,
                'confidence': knowledge_result.get('confidence'),
                'best_score': knowledge_result.get('best_score'),
                'threshold': knowledge_result.get('threshold'),
                'citations': knowledge_result.get('citations', []),
            }
        except Exception as exc:
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
            logger.exception("HRAgent.extract_from_document failed")
            return {'success': False, 'error': str(exc)}

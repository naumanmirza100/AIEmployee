"""
Task & Prioritization Agent — AI Executive Meeting Assistant
Handles: AI-driven task prioritization, bottleneck detection, deadline suggestions,
workload analysis, and executive task management.
"""

import json
import re
import logging
from typing import Optional

from project_manager_agent.ai_agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Task & Prioritization Agent for an AI Executive Meeting Assistant.
You help executives manage and prioritize their tasks intelligently.

Your capabilities:
- Prioritize tasks based on urgency, importance, deadlines, and dependencies
- Detect bottlenecks and blocked tasks
- Suggest realistic deadlines based on estimated effort
- Analyze workload and flag overload risks
- Recommend task delegation opportunities

Always return valid JSON when asked to analyze or prioritize.
Be practical, concise, and executive-focused.
"""


class TaskPrioritizationAgent(BaseAgent):

    def __init__(self, company_id: Optional[int] = None):
        super().__init__()
        self.company_id = company_id
        self.agent_key_name = 'exec_meeting_agent'
        self.system_prompt = SYSTEM_PROMPT

    def prioritize_tasks(self, tasks: list, context: str = '') -> list:
        """Re-prioritize a list of tasks using AI reasoning."""
        self.log_action("prioritize_tasks", {"task_count": len(tasks)})
        tasks_text = json.dumps(tasks[:30], indent=2)
        prompt = f"""Prioritize these executive tasks. Consider deadlines, urgency, and business impact.

Context: {context or 'General executive task management'}

Tasks:
{tasks_text}

Return ONLY a JSON array with the same tasks, each with updated fields:
[
  {{
    "id": <original id or index>,
    "title": "task title",
    "priority": "low|medium|high|critical",
    "ai_reasoning": "brief explanation for this priority",
    "suggested_due_date": "YYYY-MM-DD or null",
    "delegate_suggestion": "name or null"
  }}
]

Return ONLY the JSON array."""
        raw = self._call_llm(prompt, self.system_prompt, temperature=0.2, max_tokens=1200)
        return self._extract_json_array(raw)

    def detect_bottlenecks(self, tasks: list) -> list:
        """Identify bottleneck or blocked tasks from the task list."""
        self.log_action("detect_bottlenecks")
        tasks_text = json.dumps(tasks[:30], indent=2)
        prompt = f"""Analyze these tasks and identify bottlenecks or risks.

Tasks:
{tasks_text}

Return ONLY a JSON array of bottleneck findings:
[
  {{
    "task_id": <id or index>,
    "task_title": "title",
    "issue": "description of bottleneck or risk",
    "severity": "low|medium|high|critical",
    "recommendation": "what to do about it"
  }}
]

Return ONLY the JSON array. Empty array if no bottlenecks found."""
        raw = self._call_llm(prompt, self.system_prompt, temperature=0.2, max_tokens=800)
        return self._extract_json_array(raw)

    def suggest_deadlines(self, tasks: list) -> list:
        """Suggest realistic deadlines for tasks without due dates."""
        self.log_action("suggest_deadlines")
        from django.utils import timezone
        today = timezone.now().strftime('%Y-%m-%d')
        tasks_without_dates = [t for t in tasks if not t.get('due_date')][:20]
        if not tasks_without_dates:
            return []
        prompt = f"""Suggest realistic deadlines for these tasks. Today is {today}.

Tasks without deadlines:
{json.dumps(tasks_without_dates, indent=2)}

Return ONLY a JSON array:
[
  {{
    "id": <original id>,
    "title": "task title",
    "suggested_due_date": "YYYY-MM-DD",
    "reasoning": "why this deadline makes sense"
  }}
]

Return ONLY the JSON array."""
        raw = self._call_llm(prompt, self.system_prompt, temperature=0.2, max_tokens=600)
        return self._extract_json_array(raw)

    def analyze_workload(self, tasks: list, company_user_name: str = '') -> dict:
        """Analyze workload and return a summary with risk flags."""
        self.log_action("analyze_workload")
        from django.utils import timezone
        today = timezone.now().strftime('%Y-%m-%d')
        prompt = f"""Analyze the workload for {company_user_name or 'this executive'}. Today is {today}.

Tasks:
{json.dumps(tasks[:30], indent=2)}

Return ONLY a JSON object:
{{
  "total_tasks": <number>,
  "overdue_count": <number>,
  "critical_count": <number>,
  "workload_level": "light|moderate|heavy|overloaded",
  "risk_flags": ["flag 1", "flag 2"],
  "top_recommendations": ["recommendation 1", "recommendation 2", "recommendation 3"],
  "summary": "2-3 sentence executive summary"
}}

Return ONLY the JSON object."""
        raw = self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=500)
        return self._extract_json(raw)

    def generate_description(self, title: str, points: str) -> dict:
        """
        Expand a task title + a few free-form points into a proper task
        description — the user reviews/edits before saving.
        """
        self.log_action("generate_description", {"title": title})
        prompt = f"""Write a task description for the following. Output ONLY valid JSON:

{{
  "description": "a clear, actionable 2-4 sentence task description"
}}

Task title: {title or 'Untitled task'}
Points to cover (from the assigner, may be rough notes): {points or 'Not provided'}

Rules:
- The description should read as a clear, actionable summary of what needs to be done — not a copy of the raw points.
- If points are too sparse, infer a reasonable description from the title.
- Return ONLY the JSON object, no explanation, no markdown fences."""

        raw = self._call_llm(prompt, self.system_prompt, temperature=0.5, max_tokens=300)
        parsed = self._extract_json(raw)
        return {'description': parsed.get('description', '') or ''}

    def process(self, action: str = 'prioritize', **kwargs) -> dict:
        try:
            if action == 'prioritize':
                return {
                    'success': True,
                    'tasks': self.prioritize_tasks(kwargs['tasks'], kwargs.get('context', '')),
                }
            if action == 'bottlenecks':
                return {
                    'success': True,
                    'bottlenecks': self.detect_bottlenecks(kwargs['tasks']),
                }
            if action == 'suggest_deadlines':
                return {
                    'success': True,
                    'suggestions': self.suggest_deadlines(kwargs['tasks']),
                }
            if action == 'workload':
                return {
                    'success': True,
                    'analysis': self.analyze_workload(kwargs['tasks'], kwargs.get('company_user_name', '')),
                }
            if action == 'generate_description':
                return {
                    'success': True,
                    'data': self.generate_description(kwargs.get('title', ''), kwargs.get('points', '')),
                }
            return {'success': False, 'error': f"Unknown action: {action}"}
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            logger.error("TaskPrioritizationAgent.process error: %s", e)
            return {'success': False, 'error': str(e)}

    @staticmethod
    def _extract_json(text: str) -> dict:
        text = text.strip()
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```$', '', text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return {}

    @staticmethod
    def _extract_json_array(text: str) -> list:
        text = text.strip()
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```$', '', text)
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass
        return []

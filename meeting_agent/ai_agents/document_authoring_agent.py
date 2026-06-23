"""
Document Authoring Agent — AI Executive Meeting Assistant
Handles: agenda drafting, meeting minutes, executive briefings, reports,
and professional document generation for meetings.
"""

import json
import re
import logging
from typing import Optional

from project_manager_agent.ai_agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Document Authoring Agent for an AI Executive Meeting Assistant.
You produce polished, professional documents for executives.

Your capabilities:
- Draft detailed meeting agendas
- Write comprehensive meeting minutes
- Create executive briefing documents
- Generate status reports
- Produce professional correspondence

Write in clear, professional language suitable for executive audiences.
Be structured, concise, and action-oriented.
"""


class DocumentAuthoringAgent(BaseAgent):

    def __init__(self, company_id: Optional[int] = None):
        super().__init__()
        self.company_id = company_id
        self.agent_key_name = 'exec_document_authoring'
        self.system_prompt = SYSTEM_PROMPT

    def draft_agenda(self, meeting_title: str, duration_minutes: int, topics: list, attendees: list = None, context: str = '') -> str:
        """Draft a structured meeting agenda."""
        self.log_action("draft_agenda")
        attendees_text = ', '.join(attendees) if attendees else 'TBD'
        topics_text = '\n'.join([f"- {t}" for t in topics]) if topics else 'General discussion'
        prompt = f"""Draft a professional meeting agenda.

Meeting: {meeting_title}
Duration: {duration_minutes} minutes
Attendees: {attendees_text}
Context: {context or 'Executive meeting'}

Topics to cover:
{topics_text}

Create a structured agenda with time allocations, objectives for each item,
and a clear format. Include: Welcome/Introductions, main agenda items with
time slots, Action Items Review, and Next Steps/Closing.

Format it as clean markdown."""
        return self._call_llm(prompt, self.system_prompt, temperature=0.4, max_tokens=700)

    def write_minutes(self, meeting_title: str, date: str, attendees: list, summary: str, action_items: list, decisions: list) -> str:
        """Write formal meeting minutes."""
        self.log_action("write_minutes")
        action_text = '\n'.join([
            f"- {a.get('title', '')} | Owner: {a.get('assignee_hint', 'TBD')} | Due: {a.get('due_date', 'TBD')}"
            for a in action_items[:15]
        ])
        decisions_text = '\n'.join([f"- {d}" for d in decisions[:15]])
        prompt = f"""Write formal meeting minutes.

Meeting: {meeting_title}
Date: {date}
Attendees: {', '.join(attendees) if attendees else 'TBD'}

Discussion Summary:
{summary}

Action Items:
{action_text or 'None'}

Key Decisions:
{decisions_text or 'None'}

Format as professional meeting minutes in markdown. Include: header with meeting details,
attendees list, discussion summary, decisions made, action items table, and next meeting info."""
        return self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=900)

    def create_briefing(self, topic: str, context: str, key_points: list = None, audience: str = 'Executive Team') -> str:
        """Create an executive briefing document."""
        self.log_action("create_briefing")
        points_text = '\n'.join([f"- {p}" for p in (key_points or [])[:10]])
        prompt = f"""Create a concise executive briefing document.

Topic: {topic}
Audience: {audience}
Context: {context}

Key Points to Cover:
{points_text or 'Provide comprehensive coverage of the topic'}

Format as a professional executive briefing in markdown:
- Executive Summary (2-3 sentences)
- Background/Context
- Key Points / Analysis
- Implications
- Recommended Actions
- Conclusion

Keep it concise — executives are busy. Under 400 words."""
        return self._call_llm(prompt, self.system_prompt, temperature=0.4, max_tokens=700)

    def draft_report(self, report_type: str, data: dict, period: str = '') -> str:
        """Generate a status or progress report."""
        self.log_action("draft_report")
        prompt = f"""Generate a professional {report_type} report.

Period: {period or 'Current'}
Data:
{json.dumps(data, indent=2)[:2000]}

Format as a professional report in markdown with:
- Report header (type, period, date)
- Executive Summary
- Key Metrics / Highlights
- Details / Analysis
- Issues & Risks
- Next Steps

Be concise and data-driven."""
        return self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=800)

    def process(self, action: str = 'agenda', **kwargs) -> dict:
        try:
            if action == 'agenda':
                return {
                    'success': True,
                    'document': self.draft_agenda(
                        kwargs.get('meeting_title', 'Meeting'),
                        kwargs.get('duration_minutes', 60),
                        kwargs.get('topics', []),
                        kwargs.get('attendees'),
                        kwargs.get('context', ''),
                    ),
                    'doc_type': 'agenda',
                }
            if action == 'minutes':
                return {
                    'success': True,
                    'document': self.write_minutes(
                        kwargs.get('meeting_title', 'Meeting'),
                        kwargs.get('date', ''),
                        kwargs.get('attendees', []),
                        kwargs.get('summary', ''),
                        kwargs.get('action_items', []),
                        kwargs.get('decisions', []),
                    ),
                    'doc_type': 'minutes',
                }
            if action == 'briefing':
                return {
                    'success': True,
                    'document': self.create_briefing(
                        kwargs['topic'],
                        kwargs.get('context', ''),
                        kwargs.get('key_points'),
                        kwargs.get('audience', 'Executive Team'),
                    ),
                    'doc_type': 'briefing',
                }
            if action == 'report':
                return {
                    'success': True,
                    'document': self.draft_report(
                        kwargs.get('report_type', 'Status'),
                        kwargs.get('data', {}),
                        kwargs.get('period', ''),
                    ),
                    'doc_type': 'report',
                }
            return {'success': False, 'error': f"Unknown action: {action}"}
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            logger.error("DocumentAuthoringAgent.process error: %s", e)
            return {'success': False, 'error': str(e)}

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
        self.agent_key_name = 'exec_meeting_agent'
        self.system_prompt = SYSTEM_PROMPT

    def draft_agenda(self, meeting_title: str, duration_minutes: int, topics: list, attendees: list = None, context: str = '', scheduled_at: str = '') -> str:
        """Draft a structured meeting agenda."""
        self.log_action("draft_agenda")
        has_topics = bool(topics)
        has_attendees = bool(attendees)
        topics_text = '\n'.join([f"- {t}" for t in topics]) if has_topics else ''
        attendees_text = ', '.join(attendees) if has_attendees else ''

        # Parse scheduled_at (handles ISO "2026-07-16T09:00:00+00:00" or "2026-07-16 09:00")
        start_hour, start_min = 9, 0
        display_datetime = ''
        if scheduled_at:
            try:
                # Normalise ISO to a plain datetime string
                clean = scheduled_at.replace('Z', '').replace('T', ' ')
                # Strip timezone offset (+05:00 etc)
                import re as _re
                clean = _re.sub(r'[+-]\d{2}:\d{2}$', '', clean).strip()
                date_part, time_part = clean[:10], clean[11:16]
                h, m = time_part.split(':')
                start_hour, start_min = int(h), int(m)
                # Format nicely for the AI: "16 Jul 2026 at 09:00"
                from datetime import datetime as _dt
                parsed = _dt.strptime(date_part, '%Y-%m-%d')
                display_datetime = parsed.strftime('%d %b %Y') + f' at {time_part}'
            except Exception:
                display_datetime = scheduled_at

        def fmt_time(offset_minutes):
            total = start_hour * 60 + start_min + offset_minutes
            return f"{total // 60:02d}:{total % 60:02d}"

        if has_topics or has_attendees:
            slot_guide = f"Meeting starts at {fmt_time(0)}. Time slots must use real clock times (HH:MM format) starting from {fmt_time(0)} and ending at {fmt_time(duration_minutes)}."
            prompt = f"""Create a professional meeting agenda in markdown.

Meeting: {meeting_title}
Date/Time: {display_datetime or '[date TBD]'}
Duration: {duration_minutes} minutes
{f'Attendees: {attendees_text}' if has_attendees else ''}
{f'Topics: {topics_text}' if has_topics else ''}
{f'Context: {context}' if context else ''}

{slot_guide}

Rules:
- Use ONLY markdown headings (##, ###), bullet points (- item), and bold (**text**). Do NOT use === or --- underline-style headings or dividers.
- Time slots must be in HH:MM – HH:MM format (e.g. 09:00 – 09:10), NOT 0:00 – 0:05.
- Include: Welcome/Introductions, each topic as its own timed section, Action Items Review, Next Steps/Closing.
- Use only the topics provided — do not invent extras.

Return clean markdown only."""
        else:
            slot_guide = f"Meeting starts at {fmt_time(0)}. All time slots must use real clock times starting from {fmt_time(0)}."
            prompt = f"""Generate a professional meeting agenda TEMPLATE in markdown for: "{meeting_title}"

Date/Time: {display_datetime or '[date TBD]'}
Duration: {duration_minutes} minutes

{slot_guide}

IMPORTANT:
- Use ONLY markdown headings (##, ###) and bullet points. Do NOT use === or --- underline-style dividers.
- Time slots must be HH:MM – HH:MM format (e.g. 09:00 – 09:10), NOT 0:00 style.
- This is a TEMPLATE — use [square-bracket placeholders] for all specific content.
- Do NOT invent discussion points, attendees, or outcomes.

Sections required:
1. ## Meeting Details — Date: {display_datetime or '[DD MMM YYYY HH:MM]'}, Duration: {duration_minutes} min, Attendees: [Name, Role]
2. ## Objectives — [State 1-2 goals]
3. ## Agenda — timed items from {fmt_time(0)} to {fmt_time(duration_minutes)}, each as ### HH:MM – HH:MM: Topic Name
4. ## Action Items Review
5. ## Next Steps & Closing

Durations must add up to {duration_minutes} minutes. Return clean markdown only."""

        return self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=800)

    def write_minutes(self, meeting_title: str, date: str, attendees: list, summary: str, action_items: list, decisions: list) -> str:
        """Write formal meeting minutes."""
        self.log_action("write_minutes")
        has_summary = bool(summary and summary.strip())
        has_actions = bool(action_items)
        has_decisions = bool(decisions)
        action_text = '\n'.join([
            f"- {a.get('title', '')} | Owner: {a.get('assignee_hint', 'TBD')} | Due: {a.get('due_date', 'TBD')}"
            for a in action_items[:15]
        ])
        decisions_text = '\n'.join([f"- {d}" for d in decisions[:15]])

        if has_summary or has_actions or has_decisions:
            prompt = f"""Write formal meeting minutes in markdown.

Meeting: {meeting_title}
Date: {date}
Attendees: {', '.join(attendees) if attendees else '[List attendees]'}

Discussion Summary:
{summary if has_summary else '[No summary provided]'}

Action Items:
{action_text or 'None recorded'}

Key Decisions:
{decisions_text or 'None recorded'}

Rules:
- Use ONLY markdown headings (##, ###) and bullet points (- item). Do NOT use === or --- underline-style headings or dividers.
- Do not invent any details not present in the summary, action items, or decisions.
- Format: ## header, ## Attendees, ## Discussion Summary, ## Key Decisions, ## Action Items, ## Next Steps.

Return clean markdown only."""
        else:
            prompt = f"""Generate a professional meeting minutes TEMPLATE in markdown for: "{meeting_title}"

Rules:
- Use ONLY markdown headings (##, ###) and bullet points. Do NOT use === or --- underline-style dividers.
- This is a TEMPLATE — use [square-bracket placeholders] for all specific content.
- Do NOT invent discussion points, decisions, or outcomes.

Sections required:
1. ## Meeting Details — Meeting name, Date: [DD/MM/YYYY], Time: [HH:MM], Location: [Board Room / Zoom]
2. ## Attendees — table: Name | Role | Present
3. ## Apologies / Absent
4. ## Discussion — ### [Agenda Item 1], notes: [what was discussed], Decision: [outcome]
5. ## Key Decisions — bullet list with placeholders
6. ## Action Items — table: # | Action | Owner | Due Date | Status
7. ## Next Meeting — Date: [TBD], Items to carry forward: [list]
8. ## Sign-off — Minutes by: [Name] | Approved by: [Name]

Make placeholders descriptive. Return clean markdown only."""

        return self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=1000)

    def create_briefing(self, topic: str, context: str, key_points: list = None, audience: str = 'Executive Team') -> str:
        """Create an executive briefing document."""
        self.log_action("create_briefing")
        has_context = bool(context and context.strip())
        has_points = bool(key_points)
        points_text = '\n'.join([f"- {p}" for p in (key_points or [])[:10]])

        if has_context or has_points:
            prompt = f"""Create a concise executive briefing document in markdown.

Topic: {topic}
Audience: {audience}
{f'Context: {context}' if has_context else ''}
{f'Key Points: {points_text}' if has_points else ''}

Rules:
- Use ONLY markdown headings (##, ###) and bullet points. Do NOT use === or --- underline-style dividers.
- Write only from the context and key points provided — do not invent facts or statistics.
- Keep it under 400 words.

Sections: # {topic} — Executive Briefing, ## Executive Summary, ## Background, ## Key Points, ## Implications, ## Recommended Actions, ## Conclusion.
Return clean markdown only."""
        else:
            prompt = f"""Generate a professional executive briefing TEMPLATE in markdown for topic: "{topic}"

Rules:
- Use ONLY markdown headings (##, ###) and bullet points. Do NOT use === or --- underline-style dividers.
- This is a TEMPLATE — use [square-bracket placeholders] for all specific content.
- Do NOT invent facts, statistics, or analysis.

Sections required:
1. # {topic} — Executive Briefing (header line: Prepared for: {audience} | Date: [DD/MM/YYYY] | By: [Name])
2. ## Executive Summary — [2-3 sentences: key message and recommendation]
3. ## Background / Context — [situation, problem, or opportunity]
4. ## Key Points — bullet list: [finding 1], [finding 2], [finding 3]
5. ## Implications — [what this means for the business/team]
6. ## Recommended Actions — 1. [Action — Owner — Due date]
7. ## Conclusion — [1-2 sentence wrap-up]

Make placeholders descriptive. Return clean markdown only."""

        return self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=800)

    def draft_report(self, report_type: str, data: dict, period: str = '') -> str:
        """Generate a status or progress report."""
        self.log_action("draft_report")
        has_data = bool(data)
        prompt = f"""Generate a professional {report_type} report TEMPLATE in markdown.
{f'Period: {period}' if period else ''}
{f'Data: {json.dumps(data, indent=2)[:800]}' if has_data else ''}

Rules:
- Use ONLY markdown headings (##, ###), bullet points, and tables. Do NOT use === or --- underline-style dividers.
- This is a TEMPLATE — use [square-bracket placeholders] for all specific content.
- Do NOT invent metrics or outcomes.

Sections required:
1. # {report_type} Report (sub-line: Period: {period or '[Q / Week]'} | Date: [DD/MM/YYYY] | By: [Name/Team])
2. ## Executive Summary — [2-3 sentences: overall status]
3. ## Key Metrics — table: Metric | Target | Actual | Status
4. ## Progress Update — bullet per workstream: [Workstream]: [status]
5. ## Issues & Risks — table: Issue | Severity | Owner | Mitigation
6. ## Decisions Required — [list decisions the reader must make]
7. ## Next Steps — 1. [Action — Owner — Due Date]
8. ## Next Report Date: [DD/MM/YYYY]

Make placeholders descriptive. Return clean markdown only."""

        return self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=900)

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

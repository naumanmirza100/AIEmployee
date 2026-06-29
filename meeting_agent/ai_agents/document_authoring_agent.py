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

    def draft_agenda(self, meeting_title: str, duration_minutes: int, topics: list, attendees: list = None, context: str = '') -> str:
        """Draft a structured meeting agenda."""
        self.log_action("draft_agenda")
        has_topics = bool(topics)
        has_attendees = bool(attendees)
        topics_text = '\n'.join([f"- {t}" for t in topics]) if has_topics else ''
        attendees_text = ', '.join(attendees) if has_attendees else ''

        if has_topics or has_attendees:
            prompt = f"""Create a professional meeting agenda in markdown.

Meeting: {meeting_title}
Duration: {duration_minutes} minutes
{f'Attendees: {attendees_text}' if has_attendees else ''}
{f'Topics: {topics_text}' if has_topics else ''}
{f'Context: {context}' if context else ''}

Build a structured agenda with realistic time slots for each topic.
Include: Welcome/Introductions, each topic as its own timed agenda item, Action Items Review, Next Steps/Closing.
Use the actual topic names provided — do not invent additional topics.
Format as clean markdown."""
        else:
            prompt = f"""Generate a professional meeting agenda TEMPLATE in markdown for: "{meeting_title}"

IMPORTANT: This is a TEMPLATE — use square-bracket placeholders for all specific details.
Do NOT invent or assume any discussion points, decisions, or attendee names.

The template must have these sections with example placeholder text in brackets:
1. Meeting header (title, date, time, location, duration)
2. Attendees (e.g. [Name, Role], [Name, Role])
3. Objectives (e.g. [State the 1-2 goals of this meeting])
4. Agenda items with time slots — each item should show:
   - Time slot (e.g. 00:00 – 00:10)
   - Agenda item name (e.g. [Topic 1: e.g. Q3 Revenue Review])
   - Owner (e.g. [Presenter Name])
   - Brief description (e.g. [What will be covered / decided])
5. Action Items Review
6. Next Steps & Closing

Use realistic slot durations that add up to {duration_minutes} minutes.
Make the placeholders descriptive enough that the user understands exactly what to fill in."""

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

Write professional meeting minutes using the information above.
Do not invent any details not present in the summary, action items, or decisions.
Format: header with meeting details, attendees list, discussion summary, decisions made, action items table, next steps."""
        else:
            prompt = f"""Generate a professional meeting minutes TEMPLATE in markdown for: "{meeting_title}"

IMPORTANT: This is a TEMPLATE — use square-bracket placeholders for all specific content.
Do NOT invent discussion points, decisions, or outcomes.

The template must include these sections with descriptive placeholder text:
1. Meeting header (Meeting name, Date: [DD/MM/YYYY], Time: [HH:MM], Location: [e.g. Board Room / Zoom])
2. Attendees table (columns: Name | Role | Present)
3. Apologies / Absent
4. Agenda items discussed — for each item show:
   - Item heading (e.g. [Agenda Item 1: e.g. Budget Review])
   - Discussion notes (e.g. [Summarise what was discussed])
   - Decision reached (e.g. [State the decision, or "No decision — deferred to next meeting"])
5. Key Decisions (bulleted list with placeholders)
6. Action Items table (columns: # | Action | Owner | Due Date | Status)
7. Next Meeting (Date: [TBD], Agenda items to carry forward: [List])
8. Minutes prepared by: [Name] | Approved by: [Name]

Make placeholders descriptive so the user knows exactly what to fill in."""

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

Write the briefing using only the context and key points provided above.
Do not invent facts, statistics, or outcomes not mentioned in the context.
Format:
- # [Topic] — Executive Briefing
- **Executive Summary** (2-3 sentences based on provided context)
- **Background / Context**
- **Key Points / Analysis**
- **Implications**
- **Recommended Actions**
- **Conclusion**

Keep it concise — under 400 words."""
        else:
            prompt = f"""Generate a professional executive briefing TEMPLATE in markdown for topic: "{topic}"

IMPORTANT: This is a TEMPLATE — use square-bracket placeholders for all specific content.
Do NOT invent facts, statistics, outcomes, or analysis.

The template must include these sections with descriptive placeholder text:
1. Document header (Topic, Prepared for: {audience}, Date: [DD/MM/YYYY], Prepared by: [Name/Department])
2. **Executive Summary** — e.g. [2-3 sentences: What is this briefing about and what is the key message or recommendation?]
3. **Background / Context** — e.g. [Describe the situation, problem, or opportunity. What led to this briefing?]
4. **Key Points / Analysis** — bullet list, e.g.:
   - [Key finding or point 1 — e.g. Current state of X]
   - [Key finding or point 2 — e.g. Risk or opportunity identified]
   - [Key finding or point 3 — e.g. Relevant data or comparison]
5. **Implications** — e.g. [What does this mean for the business / team / decision-makers?]
6. **Recommended Actions** — numbered list, e.g.:
   1. [Action 1 — e.g. Approve budget for X by [date]]
   2. [Action 2 — e.g. Assign owner for Y initiative]
7. **Conclusion** — e.g. [1-2 sentence wrap-up and call to action]

Make every placeholder descriptive so the user understands exactly what to write there."""

        return self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=800)

    def draft_report(self, report_type: str, data: dict, period: str = '') -> str:
        """Generate a status or progress report."""
        self.log_action("draft_report")
        has_data = bool(data)
        prompt = f"""Generate a professional {report_type} report TEMPLATE in markdown.
{f'Period: {period}' if period else ''}

IMPORTANT: This is a TEMPLATE — use square-bracket placeholders for all specific content.
Do NOT invent metrics, figures, or outcomes.

The template must include these sections with descriptive placeholder text:
1. Report header (Report Type: {report_type} Report, Period: {period or '[e.g. Q3 2026 / Week of DD/MM]'}, Date: [DD/MM/YYYY], Prepared by: [Name/Team])
2. **Executive Summary** — e.g. [2-3 sentences: Overall status and headline message for this period]
3. **Key Metrics / Highlights** — table with columns: Metric | Target | Actual | Status (e.g. [Revenue] | [£X] | [£Y] | [On Track / At Risk])
4. **Progress Update** — bullet list per workstream/project:
   - [Workstream 1 — e.g. Product Launch]: [Brief status update]
   - [Workstream 2 — e.g. Hiring]: [Brief status update]
5. **Issues & Risks** — table: Issue | Severity | Owner | Mitigation
6. **Decisions Required** — e.g. [List any decisions the reader needs to make based on this report]
7. **Next Steps** — numbered list:
   1. [Action — Owner — Due Date]
8. **Next Report Date**: [DD/MM/YYYY]
{f'Use the following data to pre-fill relevant placeholders: {json.dumps(data, indent=2)[:1000]}' if has_data else ''}

Make every placeholder descriptive so the user knows exactly what to fill in."""

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

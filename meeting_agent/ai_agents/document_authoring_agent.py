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

        attendees_for_prompt = attendees_text if has_attendees else '[Name, Role]'

        # No topics and no attendees — return static template, skip AI
        if not has_topics and not has_attendees:
            return f"""# {meeting_title} — Meeting Agenda

**Date:** {display_datetime or '[DD MMM YYYY at HH:MM]'}
**Duration:** {duration_minutes} minutes
**Attendees:** [Name, Role]

---

## Objectives

- [State Goal 1 — what should be achieved by end of this meeting]
- [State Goal 2 — what decision or outcome is needed]

---

## Agenda

### {fmt_time(0)} – {fmt_time(5)}: Welcome & Introductions
- [Welcome attendees and review meeting objectives]

### {fmt_time(5)} – {fmt_time(5 + duration_minutes // 3)}: [Topic 1 — e.g. Quarterly Review]
- [Describe what will be discussed or decided]

### {fmt_time(5 + duration_minutes // 3)} – {fmt_time(5 + 2 * duration_minutes // 3)}: [Topic 2 — e.g. Budget Update]
- [Describe what will be discussed or decided]

### {fmt_time(5 + 2 * duration_minutes // 3)} – {fmt_time(duration_minutes - 5)}: [Topic 3 — e.g. Next Quarter Planning]
- [Describe what will be discussed or decided]

### {fmt_time(duration_minutes - 5)} – {fmt_time(duration_minutes)}: Next Steps & Closing
- [Recap key decisions and confirm action items]

---

## Action Items Review

- [Review outstanding action items from previous meetings]
- [Assign new action items with owners and due dates]

---

## Next Steps & Closing

- [Recap key decisions]
- [Confirm next steps and deadlines]
- [Adjourn at {fmt_time(duration_minutes)}]
"""

        topics_for_prompt = topics_text if has_topics else '- [Topic 1]\n- [Topic 2]\n- [Topic 3]'

        prompt = f"""Write a meeting agenda in markdown. Follow the EXACT structure below — no deviations.

---
# {meeting_title} — Meeting Agenda

**Date:** {display_datetime or '[DD MMM YYYY at HH:MM]'}
**Duration:** {duration_minutes} minutes
**Attendees:** {attendees_for_prompt}

---

## Objectives

{'- ' + chr(10).join(f'[Goal {i+1}]' for i in range(2)) if not has_topics else '- [State the 1-2 goals of this meeting]'}

---

## Agenda

{f"Each item below is one of the provided topics. Time slots start at {fmt_time(0)} and end at {fmt_time(duration_minutes)}." if has_topics else f"Time slots start at {fmt_time(0)} and end at {fmt_time(duration_minutes)}."}

Topics to cover:
{topics_for_prompt}

For EACH topic write exactly this format:
### HH:MM – HH:MM: [Topic Name]
- [What will be discussed or decided]

Also include a Welcome/Introductions item at {fmt_time(0)} (5 min) before the topics.
{'Use the exact topic names provided. Do not invent or rename them.' if has_topics else 'Replace [Topic Name] with descriptive placeholder text.'}
No breaks unless duration > 120 minutes.

---

## Action Items Review

- [Review outstanding action items from previous meetings]
- [Assign new action items with owners and due dates]

---

## Next Steps & Closing

- [Recap key decisions]
- [Confirm next steps and deadlines]
- [Adjourn at {fmt_time(duration_minutes)}]

---

Rules (STRICT):
- Output the EXACT sections above in the EXACT order: Objectives, Agenda, Action Items Review, Next Steps & Closing.
- Use only ##, ### for headings. No === or --- as underlines. No plain text headers.
- All time slots: HH:MM – HH:MM format. Durations must add up to exactly {duration_minutes} minutes.
- Do not add extra sections or change section names.
- Return markdown only, no explanation."""

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

        attendees_for_prompt = ', '.join(attendees) if attendees else '[Name, Role]'

        # If no real data at all — return a static template directly (no AI call)
        if not has_summary and not has_actions and not has_decisions:
            return f"""# {meeting_title} — Meeting Minutes

**Date:** {date}
**Attendees:** {attendees_for_prompt}

---

## Discussion Summary

[Summarise what was discussed in the meeting — key topics, points raised, and any background context.]

---

## Key Decisions

- [Decision 1 — describe the decision that was made]
- [Decision 2 — describe the decision that was made]

---

## Action Items

| # | Action | Owner | Due Date | Status |
|---|--------|-------|----------|--------|
| 1 | [Action to be taken] | [Owner Name] | [DD MMM YYYY] | Pending |
| 2 | [Action to be taken] | [Owner Name] | [DD MMM YYYY] | Pending |

---

## Next Steps

- [Follow-up step 1 — owner and deadline]
- [Follow-up step 2 — owner and deadline]

---

## Sign-off

- **Minutes prepared by:** [Name]
- **Approved by:** [Name]
"""

        summary_for_prompt = summary if has_summary else '[No summary provided]'
        decisions_for_prompt = decisions_text if has_decisions else '- [No decisions recorded]'
        action_for_prompt = action_text if has_actions else '- [No action items recorded]'

        prompt = f"""Write formal meeting minutes in markdown using ONLY the data provided below. Follow the EXACT structure.

# {meeting_title} — Meeting Minutes

**Date:** {date}
**Attendees:** {attendees_for_prompt}

---

## Discussion Summary

{summary_for_prompt}

---

## Key Decisions

{decisions_for_prompt}

---

## Action Items

{action_for_prompt}

---

## Next Steps

- [Outline follow-up steps based on the above]

---

## Sign-off

- **Minutes prepared by:** [Name]
- **Approved by:** [Name]

---

Rules (STRICT):
- Copy the structure above exactly. Output these sections in this order only.
- Use only ## for headings. No === or --- as underlines.
- Do NOT invent names, figures, dates, or discussion points not present in the data above.
- Return markdown only, no explanation."""

        return self._call_llm(prompt, self.system_prompt, temperature=0.1, max_tokens=1000)

    def extract_decisions_and_actions(self, summary: str) -> dict:
        """Extract key decisions and action items from a meeting summary."""
        self.log_action("extract_decisions_and_actions")
        prompt = f"""Read the following meeting summary and extract:
1. Key decisions — any choices made, approvals given, or conclusions reached.
2. Action items — any specific tasks, follow-ups, or things someone needs to do.

If something is clearly a task or follow-up, include it as an action item even if no owner or due date is mentioned.
If no real decisions or action items exist, return empty lists — do NOT invent any.

Summary:
{summary}

Return ONLY this JSON (no markdown):
{{
  "decisions": ["decision 1", "decision 2"],
  "action_items": [
    {{"title": "task description", "assignee_hint": "person name or null", "due_date": null}},
    {{"title": "task description", "assignee_hint": null, "due_date": null}}
  ]
}}"""
        import json as _json
        import re as _re
        raw = self._call_llm(prompt, self.system_prompt, temperature=0.1, max_tokens=400)
        raw = raw.strip()
        raw = _re.sub(r'^```(?:json)?\s*', '', raw, flags=_re.IGNORECASE)
        raw = _re.sub(r'\s*```$', '', raw)
        try:
            result = _json.loads(raw)
            if isinstance(result, dict):
                return {
                    'decisions': result.get('decisions') or [],
                    'action_items': result.get('action_items') or [],
                }
        except Exception:
            pass
        return {'decisions': [], 'action_items': []}

    def create_briefing(self, topic: str, context: str, key_points: list = None, audience: str = 'Executive Team') -> str:
        """Create an executive briefing document."""
        self.log_action("create_briefing")
        has_context = bool(context and context.strip())
        has_points = bool(key_points)
        points_text = '\n'.join([f"- {p}" for p in (key_points or [])[:10]])

        # No context and no key points — return static template, skip AI
        if not has_context and not has_points:
            return f"""# {topic} — Executive Briefing

**Prepared for:** {audience}
**Date:** [DD MMM YYYY]
**Prepared by:** [Name / Department]

---

## Executive Summary

[2-3 sentences: What is this briefing about and what is the key message or recommendation?]

---

## Background / Context

[Describe the situation, problem, or opportunity that led to this briefing. What has happened and why does it matter?]

---

## Key Points

- [Key finding or point 1 — e.g. Current state of X]
- [Key finding or point 2 — e.g. Risk or opportunity identified]
- [Key finding or point 3 — e.g. Relevant data or comparison]

---

## Implications

[What does this mean for the business, team, or decision-makers? What happens if no action is taken?]

---

## Recommended Actions

1. [Action 1 — Owner — Due date]
2. [Action 2 — Owner — Due date]

---

## Conclusion

[1-2 sentence wrap-up and call to action.]
"""

        context_for_prompt = context if has_context else '[No context provided]'
        points_for_prompt = points_text if has_points else ''

        prompt = f"""Write an executive briefing document in markdown using ONLY the data provided below. Follow the EXACT structure.

---
# {topic} — Executive Briefing

**Prepared for:** {audience}
**Date:** [DD MMM YYYY]
**Prepared by:** [Name / Department]

---

## Executive Summary

{'Write 2-3 sentences summarising the key message and recommendation based on the context provided.' if has_context else '[2-3 sentences: What is this briefing about and what is the key recommendation?]'}

---

## Background / Context

{context_for_prompt}

---

## Key Points

{points_for_prompt}

---

## Implications

{'Based on the above, summarise what this means for the business or team.' if has_context else '[What does this mean for the business, team, or decision-makers?]'}

---

## Recommended Actions

1. [Action 1 — Owner — Due date]
2. [Action 2 — Owner — Due date]

---

## Conclusion

[1-2 sentence wrap-up and call to action]

---

Rules (STRICT):
- Output the EXACT sections above in the EXACT order.
- Use only # and ## for headings. No === or --- as underlines. No plain text headers.
- {'Write only from the context and key points provided — do not invent facts or statistics.' if (has_context or has_points) else 'Keep [square-bracket placeholders] for all specific content.'}
- Keep it concise — under 400 words total.
- Return markdown only, no explanation."""

        return self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=800)

    def draft_report(self, report_type: str, data: dict, period: str = '') -> str:
        """Generate a status or progress report."""
        self.log_action("draft_report")
        has_data = bool(data)
        data_snippet = f'\nData provided:\n{json.dumps(data, indent=2)[:800]}' if has_data else ''

        prompt = f"""Write a {report_type} status report in markdown. Follow the EXACT structure below.

---
# {report_type} Report

**Period:** {period or '[e.g. Q3 2026 / Week of DD MMM]'}
**Date:** [DD MMM YYYY]
**Prepared by:** [Name / Team]

---

## Executive Summary

[2-3 sentences: overall status and headline message for this period]

---

## Key Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| [Metric 1] | [Target] | [Actual] | [On Track / At Risk] |
| [Metric 2] | [Target] | [Actual] | [On Track / At Risk] |

---

## Progress Update

- **[Workstream 1]:** [Brief status update]
- **[Workstream 2]:** [Brief status update]

---

## Issues & Risks

| Issue | Severity | Owner | Mitigation |
|-------|----------|-------|------------|
| [Issue 1] | [High/Med/Low] | [Name] | [Action] |

---

## Decisions Required

- [Decision 1 that the reader needs to make]
- [Decision 2]

---

## Next Steps

1. [Action — Owner — Due Date]
2. [Action — Owner — Due Date]

---

**Next Report Date:** [DD MMM YYYY]

---

Rules (STRICT):
- Output the EXACT sections above in the EXACT order.
- Use only # and ## for headings. No === or --- as underlines. No plain text headers.
- {'Use the provided data to fill in relevant fields. Do not invent figures not in the data.' if has_data else 'Keep [square-bracket placeholders] for all specific content — do not invent metrics or figures.'}
- Return markdown only, no explanation.{data_snippet}"""

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

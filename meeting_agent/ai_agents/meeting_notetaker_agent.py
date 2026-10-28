"""
Meeting Notetaker Agent — AI Executive Meeting Assistant
Handles: transcript processing, AI summary generation, action item extraction,
key decisions capture, and follow-up email drafting.
"""

import json
import re
import logging
from typing import Optional

from project_manager_agent.ai_agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Meeting Notetaker Agent for an AI Executive Meeting Assistant.
You process meeting transcripts and produce structured, actionable notes.

Your capabilities:
- Generate concise meeting summaries
- Extract action items with assignees, deadlines, and priorities
- Identify key decisions made during the meeting
- Draft professional follow-up emails
- Structure unstructured meeting notes

Always return valid JSON when asked to extract structured data.
Be accurate, concise, and professional.
"""


#: A transcript is read in pieces of this many characters (about 3,000 tokens), one call each (CO-164).
PIECE_CHARS = 12000
#: At most this many pieces, about 96,000 characters: two hours of talk. Past it, the reply says how much was read.
MAX_PIECES = 8


class MeetingNotetakerAgent(BaseAgent):

    def __init__(self, company_id: Optional[int] = None):
        super().__init__()
        self.company_id = company_id
        self.agent_key_name = 'exec_meeting_agent'
        self.system_prompt = SYSTEM_PROMPT

    def generate_summary(self, transcript: str) -> str:
        """Generate a concise AI summary from a meeting transcript."""
        self.log_action("generate_summary", {"transcript_len": len(transcript)})
        prompt = f"""Summarize this meeting transcript in 3-5 bullet points. Be concise and professional.

Transcript:
{transcript[:PIECE_CHARS]}

Return a clean bullet-point summary. Focus on what was discussed, decided, and agreed upon."""
        return self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=500)

    @staticmethod
    def _dates_hint(held_on) -> str:
        """The day the meeting was held, for working out the due dates said in it.

        Told nothing, the AI turned "by Friday" into a Friday in 2023."""
        if not held_on:
            return ''
        return (f"The meeting was held on {held_on:%A}, {held_on.isoformat()}. Work out every due date from that "
                "day: 'Friday' is the first Friday after it, 'next week' is the week after it, 'end of the month' is "
                "the last day of its month. No due date is before that day. If no date was said, use null.")

    def extract_action_items(self, transcript: str, participant_names: list = None, held_on=None) -> list:
        """Extract action items from transcript as structured JSON list."""
        self.log_action("extract_action_items")
        participants_hint = f"Known participants: {', '.join(participant_names)}" if participant_names else ""
        prompt = f"""Extract all action items from this meeting transcript.
{participants_hint}
{self._dates_hint(held_on)}

Transcript:
{transcript[:PIECE_CHARS]}

Return ONLY a JSON array:
[
  {{
    "title": "action item description",
    "assignee_hint": "person's name or null",
    "due_date": "YYYY-MM-DD or null",
    "priority": "low|medium|high|critical",
    "description": "additional context"
  }}
]

Return ONLY the JSON array, no explanation."""
        raw = self._call_llm(prompt, self.system_prompt, temperature=0.1, max_tokens=800)
        return self._extract_json_array(raw)

    def extract_key_decisions(self, transcript: str) -> list:
        """Extract key decisions from transcript as a JSON list of strings."""
        self.log_action("extract_key_decisions")
        prompt = f"""Extract all key decisions made in this meeting transcript.

Transcript:
{transcript[:PIECE_CHARS]}

Return ONLY a JSON array of decision strings:
["decision 1", "decision 2", ...]

Return ONLY the JSON array, no explanation."""
        raw = self._call_llm(prompt, self.system_prompt, temperature=0.1, max_tokens=400)
        return self._extract_json_array(raw)

    def draft_followup_email(self, meeting_title: str, summary: str, action_items: list, decisions: list) -> str:
        """Draft a follow-up email after the meeting."""
        self.log_action("draft_followup_email")
        action_text = '\n'.join([f"- {a.get('title', '')} (Assignee: {a.get('assignee_hint', 'TBD')}, Due: {a.get('due_date', 'TBD')})" for a in action_items[:10]])
        decisions_text = '\n'.join([f"- {d}" for d in decisions[:10]])
        prompt = f"""Write a professional follow-up email for this meeting.

Meeting: {meeting_title}

Summary:
{summary}

Action Items:
{action_text or 'None'}

Key Decisions:
{decisions_text or 'None'}

Write a professional email body (no subject line). Keep it under 200 words. Be clear and actionable."""
        return self._call_llm(prompt, self.system_prompt, temperature=0.4, max_tokens=400)

    def _read_piece(self, piece: str, number: int, total: int, participant_names: list = None, held_on=None) -> dict:
        """One piece of a long transcript, read in one call: its points, action items and decisions."""
        participants_hint = f"Known participants: {', '.join(participant_names)}" if participant_names else ""
        prompt = f"""This is part {number} of {total} of a meeting transcript.
{participants_hint}
{self._dates_hint(held_on)}

Transcript, part {number}:
{piece}

Return ONLY JSON:
{{"points": ["what was discussed, decided or agreed in this part, 2-4 short bullets"],
  "action_items": [{{"title": "...", "assignee_hint": "name or null", "due_date": "YYYY-MM-DD or null",
                    "priority": "low|medium|high|critical", "description": "..."}}],
  "decisions": ["decision", "..."]}}"""
        raw = self._call_llm(prompt, self.system_prompt, temperature=0.1, max_tokens=1200)
        try:
            data = json.loads(re.sub(r'^```(?:json)?|```$', '', (raw or '').strip(), flags=re.M).strip())
        except (TypeError, ValueError):
            match = re.search(r'\{.*\}', raw or '', re.S)
            try:
                data = json.loads(match.group(0)) if match else {}
            except ValueError:
                data = {}
        return data if isinstance(data, dict) else {}

    def process_full_transcript(self, transcript: str, meeting_title: str = '', participant_names: list = None,
                                held_on=None) -> dict:
        """Summary, action items and decisions from the whole transcript.

        Only its first 4,000 characters were read, a few minutes of talk, and the screen said the meeting was
        summarised (CO-164). A short transcript is read whole; a long one in pieces of PIECE_CHARS, one call each,
        and the pieces' points combined. Past MAX_PIECES the rest is not read, and `chars_read` says so."""
        self.log_action("process_full_transcript", {"transcript_len": len(transcript)})
        total = len(transcript)
        if total <= PIECE_CHARS:
            return {
                'summary': self.generate_summary(transcript),
                'action_items': self.extract_action_items(transcript, participant_names, held_on),
                'key_decisions': self.extract_key_decisions(transcript),
                'chars_read': total, 'chars_total': total,
            }
        pieces = [transcript[i:i + PIECE_CHARS] for i in range(0, total, PIECE_CHARS)][:MAX_PIECES]
        points, items, decisions, seen_items, seen_decisions = [], [], [], set(), set()
        for number, piece in enumerate(pieces, 1):
            part = self._read_piece(piece, number, len(pieces), participant_names, held_on)
            points += [str(p) for p in part.get('points') or [] if p]
            for item in part.get('action_items') or []:
                key = str((item or {}).get('title', '')).strip().lower() if isinstance(item, dict) else ''
                if key and key not in seen_items:
                    seen_items.add(key)
                    items.append(item)
            for decision in part.get('decisions') or []:
                key = ' '.join(str(decision).split()).lower()
                if key and key not in seen_decisions:
                    seen_decisions.add(key)
                    decisions.append(str(decision))
        summary = self._call_llm(
            "These are the points of a meeting, part by part, in order:\n" + '\n'.join(f'- {p}' for p in points)
            + "\n\nSummarize the whole meeting in 3-6 bullet points. Be concise and professional.",
            self.system_prompt, temperature=0.3, max_tokens=500) if points else ''
        return {
            'summary': summary,
            'action_items': items,
            'key_decisions': decisions,
            'chars_read': sum(len(p) for p in pieces), 'chars_total': total,
        }

    def process(self, action: str = 'full', **kwargs) -> dict:
        try:
            if action == 'full':
                return {
                    'success': True,
                    'data': self.process_full_transcript(
                        kwargs['transcript'],
                        kwargs.get('meeting_title', ''),
                        kwargs.get('participant_names'),
                        kwargs.get('held_on'),
                    ),
                }
            if action == 'summary':
                return {'success': True, 'summary': self.generate_summary(kwargs['transcript'])}
            if action == 'action_items':
                return {'success': True, 'action_items': self.extract_action_items(kwargs['transcript'], kwargs.get('participant_names'), kwargs.get('held_on'))}
            if action == 'decisions':
                return {'success': True, 'decisions': self.extract_key_decisions(kwargs['transcript'])}
            if action == 'followup_email':
                return {'success': True, 'email': self.draft_followup_email(
                    kwargs.get('meeting_title', ''),
                    kwargs.get('summary', ''),
                    kwargs.get('action_items', []),
                    kwargs.get('decisions', []),
                )}
            return {'success': False, 'error': f"Unknown action: {action}"}
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            logger.error("MeetingNotetakerAgent.process error: %s", e)
            return {'success': False, 'error': str(e)}

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

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
{transcript[:4000]}

Return a clean bullet-point summary. Focus on what was discussed, decided, and agreed upon."""
        return self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=500)

    def extract_action_items(self, transcript: str, participant_names: list = None) -> list:
        """Extract action items from transcript as structured JSON list."""
        self.log_action("extract_action_items")
        participants_hint = f"Known participants: {', '.join(participant_names)}" if participant_names else ""
        prompt = f"""Extract all action items from this meeting transcript.
{participants_hint}

Transcript:
{transcript[:4000]}

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
{transcript[:4000]}

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

    def process_full_transcript(self, transcript: str, meeting_title: str = '', participant_names: list = None) -> dict:
        """Run full notetaker pipeline: summary + action items + decisions."""
        self.log_action("process_full_transcript")
        summary = self.generate_summary(transcript)
        action_items = self.extract_action_items(transcript, participant_names)
        decisions = self.extract_key_decisions(transcript)
        followup = self.draft_followup_email(meeting_title, summary, action_items, decisions)
        return {
            'summary': summary,
            'action_items': action_items,
            'key_decisions': decisions,
            'followup_email': followup,
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
                    ),
                }
            if action == 'summary':
                return {'success': True, 'summary': self.generate_summary(kwargs['transcript'])}
            if action == 'action_items':
                return {'success': True, 'action_items': self.extract_action_items(kwargs['transcript'], kwargs.get('participant_names'))}
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

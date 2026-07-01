"""
Meeting Scheduling Agent — AI Executive Meeting Assistant
Handles: natural-language scheduling, conflict detection, slot suggestions,
participant matching, recurrence, and counter-proposal workflow.
"""

import json
import re
import logging
from datetime import datetime, timedelta
from typing import Optional

from django.utils import timezone

from project_manager_agent.ai_agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Meeting Scheduling Agent for an AI Executive Meeting Assistant.
You help executives schedule, reschedule, and manage meetings with precision.

Your capabilities:
- Parse natural language meeting requests into structured data
- Detect scheduling conflicts
- Suggest available time slots
- Handle meeting recurrence (daily, weekly, biweekly, monthly)
- Manage participant invitations and responses

Always respond with valid JSON when asked to parse or suggest.
Be concise, professional, and timezone-aware.
"""


class MeetingSchedulingAgent(BaseAgent):

    def __init__(self, company_id: Optional[int] = None):
        super().__init__()
        self.company_id = company_id
        self.agent_key_name = 'exec_meeting_agent'
        self.system_prompt = SYSTEM_PROMPT

    def parse_meeting_request(self, message: str, company_user_id: int) -> dict:
        """Parse a natural-language meeting request into structured JSON."""
        self.log_action("parse_meeting_request", {"message_len": len(message)})
        prompt = f"""Parse this meeting request and return ONLY valid JSON:

Request: "{message}"

Return JSON with these fields:
{{
  "title": "meeting title",
  "scheduled_at": "YYYY-MM-DDTHH:MM:SS",
  "duration_minutes": 60,
  "timezone_name": "UTC",
  "description": "optional description",
  "agenda": ["item 1", "item 2"],
  "recurrence": "none|daily|weekly|biweekly|monthly",
  "recurrence_end_date": "YYYY-MM-DD or null",
  "participant_hints": ["name or email hints"],
  "location": "",
  "meeting_link": ""
}}

Use today's date as reference: {timezone.now().strftime('%Y-%m-%d')}.
If any field is unclear, use sensible defaults. Return ONLY JSON, no explanation."""

        raw = self._call_llm(prompt, self.system_prompt, temperature=0.1, max_tokens=600)
        return self._extract_json(raw)

    def check_conflicts(self, company_user_id: int, scheduled_at: datetime, duration_minutes: int, exclude_meeting_id: int = None) -> list:
        """Return list of conflicting meeting dicts for a given user + time window."""
        self.log_action("check_conflicts")
        from meeting_agent.models import ExecutiveMeeting, ExecutiveMeetingParticipant
        end_time = scheduled_at + timedelta(minutes=duration_minutes)

        organizer_qs = ExecutiveMeeting.objects.filter(
            organizer_id=company_user_id,
            status__in=['scheduled', 'in_progress', 'pending_confirmation'],
            scheduled_at__lt=end_time,
        ).exclude(status='cancelled')

        participant_qs = ExecutiveMeeting.objects.filter(
            participants__company_user_id=company_user_id,
            participants__response__in=['accepted', 'tentative', 'pending'],
            status__in=['scheduled', 'in_progress', 'pending_confirmation'],
            scheduled_at__lt=end_time,
        ).exclude(status='cancelled')

        conflicts = []
        for meeting in (list(organizer_qs) + list(participant_qs)):
            if exclude_meeting_id and meeting.id == exclude_meeting_id:
                continue
            meeting_end = meeting.scheduled_at + timedelta(minutes=meeting.duration_minutes)
            if meeting_end > scheduled_at:
                conflicts.append({
                    'id': meeting.id,
                    'title': meeting.title,
                    'scheduled_at': meeting.scheduled_at.isoformat(),
                    'duration_minutes': meeting.duration_minutes,
                })
        # deduplicate by id
        seen = set()
        unique = []
        for c in conflicts:
            if c['id'] not in seen:
                seen.add(c['id'])
                unique.append(c)
        return unique

    def suggest_available_slots(self, company_user_id: int, preferred_date: str, duration_minutes: int = 60, num_slots: int = 5) -> list:
        """Suggest free time slots on a given date (9 AM – 6 PM window, 30-min step)."""
        self.log_action("suggest_available_slots")
        try:
            base = datetime.strptime(preferred_date, '%Y-%m-%d')
        except ValueError:
            base = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

        slots = []
        candidate = base.replace(hour=9, minute=0, second=0, microsecond=0)
        end_of_day = base.replace(hour=18, minute=0, second=0, microsecond=0)

        while candidate + timedelta(minutes=duration_minutes) <= end_of_day and len(slots) < num_slots:
            aware_candidate = timezone.make_aware(candidate) if timezone.is_naive(candidate) else candidate
            conflicts = self.check_conflicts(company_user_id, aware_candidate, duration_minutes)
            if not conflicts:
                slots.append({
                    'start': candidate.strftime('%Y-%m-%dT%H:%M:%S'),
                    'end': (candidate + timedelta(minutes=duration_minutes)).strftime('%Y-%m-%dT%H:%M:%S'),
                })
            candidate += timedelta(minutes=30)

        return slots

    def generate_recurrence_dates(self, start_date: datetime, recurrence: str, end_date) -> list:
        """Generate occurrence datetimes for a recurring meeting."""
        if recurrence == 'none' or not end_date:
            return []
        dates = []
        current = start_date
        if isinstance(end_date, str):
            from datetime import date
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        delta_map = {
            'daily': timedelta(days=1),
            'weekly': timedelta(weeks=1),
            'biweekly': timedelta(weeks=2),
            'monthly': None,
        }
        delta = delta_map.get(recurrence)
        while True:
            if recurrence == 'monthly':
                month = current.month + 1
                year = current.year + (month - 1) // 12
                month = ((month - 1) % 12) + 1
                try:
                    current = current.replace(year=year, month=month)
                except ValueError:
                    break
            else:
                current = current + delta
            if current.date() > end_date:
                break
            dates.append(current)
        return dates

    def draft_invite_message(self, meeting_data: dict) -> str:
        """Generate a professional meeting invitation message."""
        self.log_action("draft_invite_message")
        prompt = f"""Write a professional meeting invitation email for:

Title: {meeting_data.get('title', 'Meeting')}
Date/Time: {meeting_data.get('scheduled_at', 'TBD')}
Duration: {meeting_data.get('duration_minutes', 60)} minutes
Location/Link: {meeting_data.get('location') or meeting_data.get('meeting_link') or 'TBD'}
Agenda: {json.dumps(meeting_data.get('agenda', []))}
Description: {meeting_data.get('description', '')}

Write a concise, professional email body (no subject line). Keep it under 150 words."""
        return self._call_llm(prompt, self.system_prompt, temperature=0.4, max_tokens=300)

    def process(self, action: str = 'parse', **kwargs) -> dict:
        try:
            if action == 'parse':
                return {
                    'success': True,
                    'data': self.parse_meeting_request(kwargs['message'], kwargs['company_user_id']),
                }
            if action == 'conflicts':
                return {
                    'success': True,
                    'conflicts': self.check_conflicts(
                        kwargs['company_user_id'],
                        kwargs['scheduled_at'],
                        kwargs.get('duration_minutes', 60),
                        kwargs.get('exclude_meeting_id'),
                    ),
                }
            if action == 'suggest_slots':
                return {
                    'success': True,
                    'slots': self.suggest_available_slots(
                        kwargs['company_user_id'],
                        kwargs['preferred_date'],
                        kwargs.get('duration_minutes', 60),
                        kwargs.get('num_slots', 5),
                    ),
                }
            if action == 'draft_invite':
                return {
                    'success': True,
                    'message': self.draft_invite_message(kwargs['meeting_data']),
                }
            return {'success': False, 'error': f"Unknown action: {action}"}
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            logger.error("MeetingSchedulingAgent.process error: %s", e)
            return {'success': False, 'error': str(e)}

    @staticmethod
    def _extract_json(text: str) -> dict:
        text = text.strip()
        # strip markdown fences
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

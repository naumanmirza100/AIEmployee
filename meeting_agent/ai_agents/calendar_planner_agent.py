"""
Calendar Auto-planner Agent — AI Executive Meeting Assistant
Handles: weekly/daily calendar planning, auto-scheduling tasks into free slots,
conflict resolution, focus time blocking, and smart rescheduling suggestions.
"""

import json
import re
import logging
from datetime import datetime, timedelta
from typing import Optional

from django.utils import timezone

from project_manager_agent.ai_agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Calendar Auto-planner Agent for an AI Executive Meeting Assistant.
You help executives manage their time intelligently by optimizing their calendar.

Your capabilities:
- Plan the executive's week by slotting tasks and meetings efficiently
- Auto-schedule unscheduled tasks into available time slots
- Detect and resolve calendar conflicts
- Recommend focus-time blocks for deep work
- Suggest optimal meeting times based on energy and priorities

Always return valid JSON when asked to plan or suggest.
Be time-aware, practical, and executive-focused.
"""


class CalendarPlannerAgent(BaseAgent):

    def __init__(self, company_id: Optional[int] = None):
        super().__init__()
        self.company_id = company_id
        self.agent_key_name = 'exec_calendar_planner'
        self.system_prompt = SYSTEM_PROMPT

    def plan_week(self, meetings: list, tasks: list, week_start: str = None) -> dict:
        """Generate an optimized weekly plan given meetings and tasks."""
        self.log_action("plan_week", {"meetings": len(meetings), "tasks": len(tasks)})
        if not week_start:
            week_start = timezone.now().strftime('%Y-%m-%d')
        prompt = f"""Create an optimized weekly calendar plan for an executive.
Week starting: {week_start}

Scheduled Meetings:
{json.dumps(meetings[:20], indent=2)}

Pending Tasks:
{json.dumps(tasks[:20], indent=2)}

Return ONLY a JSON object:
{{
  "week_start": "{week_start}",
  "daily_plans": [
    {{
      "date": "YYYY-MM-DD",
      "day_name": "Monday",
      "scheduled_meetings": [<meeting titles>],
      "suggested_task_slots": [
        {{"time": "HH:MM", "task": "task title", "duration_minutes": 60}}
      ],
      "focus_blocks": [
        {{"start": "HH:MM", "end": "HH:MM", "label": "Deep Work"}}
      ],
      "workload_level": "light|moderate|heavy"
    }}
  ],
  "weekly_summary": "brief summary",
  "conflicts_detected": ["conflict description"],
  "recommendations": ["recommendation 1"]
}}

Return ONLY the JSON object."""
        raw = self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=1500)
        return self._extract_json(raw)

    def auto_schedule_tasks(self, tasks: list, available_slots: list) -> list:
        """Assign unscheduled tasks to available calendar slots."""
        self.log_action("auto_schedule_tasks")
        prompt = f"""Assign these tasks to available time slots. Match task duration to slot size.

Unscheduled Tasks:
{json.dumps(tasks[:15], indent=2)}

Available Slots:
{json.dumps(available_slots[:20], indent=2)}

Return ONLY a JSON array:
[
  {{
    "task_id": <id>,
    "task_title": "title",
    "assigned_slot_start": "YYYY-MM-DDTHH:MM:SS",
    "assigned_slot_end": "YYYY-MM-DDTHH:MM:SS",
    "reasoning": "why this slot was chosen"
  }}
]

Return ONLY the JSON array."""
        raw = self._call_llm(prompt, self.system_prompt, temperature=0.2, max_tokens=800)
        return self._extract_json_array(raw)

    def resolve_conflicts(self, conflicts: list, meetings: list) -> list:
        """Suggest resolutions for detected calendar conflicts."""
        self.log_action("resolve_conflicts")
        prompt = f"""Suggest resolutions for these calendar conflicts.

Conflicts:
{json.dumps(conflicts[:10], indent=2)}

All Meetings:
{json.dumps(meetings[:20], indent=2)}

Return ONLY a JSON array:
[
  {{
    "conflict_description": "what conflicts",
    "resolution": "what to do",
    "affected_meeting_id": <id or null>,
    "suggested_new_time": "YYYY-MM-DDTHH:MM:SS or null",
    "priority": "which meeting to keep"
  }}
]

Return ONLY the JSON array."""
        raw = self._call_llm(prompt, self.system_prompt, temperature=0.2, max_tokens=600)
        return self._extract_json_array(raw)

    def get_free_slots(self, company_user_id: int, date_str: str, duration_minutes: int = 60) -> list:
        """Query DB for free slots on a given date for a user."""
        self.log_action("get_free_slots")
        from meeting_agent.models import ExecutiveMeeting, ExecutiveMeetingParticipant
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            date = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

        day_start = timezone.make_aware(date.replace(hour=9, minute=0, second=0, microsecond=0))
        day_end = timezone.make_aware(date.replace(hour=18, minute=0, second=0, microsecond=0))

        # Get all meetings for this user on this day
        busy = []
        for m in ExecutiveMeeting.objects.filter(
            organizer_id=company_user_id,
            scheduled_at__date=date.date(),
            status__in=['scheduled', 'in_progress', 'pending_confirmation'],
        ):
            busy.append((m.scheduled_at, m.scheduled_at + timedelta(minutes=m.duration_minutes)))

        for p in ExecutiveMeetingParticipant.objects.filter(
            company_user_id=company_user_id,
            response__in=['accepted', 'tentative', 'pending'],
            meeting__scheduled_at__date=date.date(),
            meeting__status__in=['scheduled', 'in_progress', 'pending_confirmation'],
        ).select_related('meeting'):
            m = p.meeting
            busy.append((m.scheduled_at, m.scheduled_at + timedelta(minutes=m.duration_minutes)))

        # Find free slots
        free_slots = []
        candidate = day_start
        while candidate + timedelta(minutes=duration_minutes) <= day_end:
            slot_end = candidate + timedelta(minutes=duration_minutes)
            is_free = all(not (candidate < bend and slot_end > bstart) for bstart, bend in busy)
            if is_free:
                free_slots.append({
                    'start': candidate.isoformat(),
                    'end': slot_end.isoformat(),
                })
            candidate += timedelta(minutes=30)
        return free_slots

    def process(self, action: str = 'plan_week', **kwargs) -> dict:
        try:
            if action == 'plan_week':
                return {
                    'success': True,
                    'plan': self.plan_week(
                        kwargs.get('meetings', []),
                        kwargs.get('tasks', []),
                        kwargs.get('week_start'),
                    ),
                }
            if action == 'auto_schedule':
                return {
                    'success': True,
                    'assignments': self.auto_schedule_tasks(kwargs['tasks'], kwargs['available_slots']),
                }
            if action == 'resolve_conflicts':
                return {
                    'success': True,
                    'resolutions': self.resolve_conflicts(kwargs['conflicts'], kwargs.get('meetings', [])),
                }
            if action == 'free_slots':
                return {
                    'success': True,
                    'slots': self.get_free_slots(
                        kwargs['company_user_id'],
                        kwargs['date'],
                        kwargs.get('duration_minutes', 60),
                    ),
                }
            return {'success': False, 'error': f"Unknown action: {action}"}
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            logger.error("CalendarPlannerAgent.process error: %s", e)
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

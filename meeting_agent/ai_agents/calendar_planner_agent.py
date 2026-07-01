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
        self.agent_key_name = 'exec_meeting_agent'
        self.system_prompt = SYSTEM_PROMPT

    def plan_week(self, meetings: list, tasks: list, week_start: str = None) -> dict:
        """Generate an optimized weekly plan given meetings and tasks."""
        self.log_action("plan_week", {"meetings": len(meetings), "tasks": len(tasks)})
        if not week_start:
            week_start = timezone.now().strftime('%Y-%m-%d')

        # Pre-compute exact 7 dates so AI cannot invent dates
        try:
            base = datetime.strptime(week_start, '%Y-%m-%d')
        except ValueError:
            base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        week_dates = [
            {'date': (base + timedelta(days=i)).strftime('%Y-%m-%d'),
             'day_name': day_names[(base + timedelta(days=i)).weekday()]}
            for i in range(7)
        ]

        # Group meetings by their actual date (Python — never trust AI for this)
        meetings_by_date = {}
        for m in meetings:
            d = m['scheduled_at'][:10]
            time_str = m['scheduled_at'][11:16] if len(m['scheduled_at']) > 10 else ''
            meetings_by_date.setdefault(d, []).append({
                'title': m['title'],
                'time': time_str,
                'duration_minutes': m.get('duration_minutes', 0),
            })

        # Distribute tasks across days with fewest meetings (Python logic, no AI)
        work_days = [d for d in week_dates if day_names[datetime.strptime(d['date'], '%Y-%m-%d').weekday()] not in ('Saturday', 'Sunday')]
        # Sort work days by meeting load ascending so lighter days get tasks first
        work_days_sorted = sorted(work_days, key=lambda d: len(meetings_by_date.get(d['date'], [])))
        tasks_by_date = {d['date']: [] for d in week_dates}
        slot_times = ['09:00', '10:00', '11:00', '13:00', '14:00', '15:00', '16:00']
        week_date_set = {d['date'] for d in week_dates}
        task_queue = list(tasks[:20])
        for task in task_queue:
            # Prefer day matching due_date only if it falls within this week
            due = (task.get('due_date') or '')[:10]
            placed = False
            if due and due in week_date_set:
                tasks_by_date[due].append(task)
                placed = True
            if not placed:
                # Pick lightest day that still has free slots
                for d in work_days_sorted:
                    used = len(tasks_by_date[d['date']]) + len(meetings_by_date.get(d['date'], []))
                    if used < len(slot_times):
                        tasks_by_date[d['date']].append(task)
                        # Re-sort after adding
                        work_days_sorted = sorted(work_days, key=lambda x: len(tasks_by_date[x['date']]) + len(meetings_by_date.get(x['date'], [])))
                        break

        # Ask AI only for summary, recommendations, focus blocks per day
        days_summary = '\n'.join(
            f"  {d['date']} ({d['day_name']}): meetings={[m['title'] for m in meetings_by_date.get(d['date'], [])]}, tasks={[t.get('title') for t in tasks_by_date.get(d['date'], [])]}"
            for d in week_dates
        )
        prompt = f"""You are a calendar assistant. Given this weekly schedule, provide a brief summary and practical recommendations only.

Schedule:
{days_summary}

Return ONLY this JSON (no markdown):
{{
  "weekly_summary": "...",
  "conflicts_detected": [],
  "recommendations": ["tip 1", "tip 2"]
}}"""
        raw = self._call_llm(prompt, self.system_prompt, temperature=0.1, max_tokens=800)
        ai = self._extract_json(raw) or {}

        # Build final plan entirely in Python
        fixed_days = []
        for d in week_dates:
            date = d['date']
            is_weekend = d['day_name'] in ('Saturday', 'Sunday')
            day_meetings = meetings_by_date.get(date, [])
            day_tasks = tasks_by_date.get(date, [])

            # Assign slot times to tasks
            used_slots = set()
            task_slots = []
            slot_idx = 0
            for task in day_tasks:
                while slot_idx < len(slot_times) and slot_times[slot_idx] in used_slots:
                    slot_idx += 1
                if slot_idx < len(slot_times):
                    task_slots.append({
                        'time': slot_times[slot_idx],
                        'task': task.get('title', ''),
                        'duration_minutes': 60,
                    })
                    used_slots.add(slot_times[slot_idx])
                    slot_idx += 1

            # Compute focus block in Python — pick first 2-hour gap after all tasks+meetings
            if not is_weekend:
                # Collect all occupied hour blocks
                occupied = set()
                for ts in task_slots:
                    h = int(ts['time'].split(':')[0])
                    occupied.add(h)
                for mt in day_meetings:
                    if mt.get('time'):
                        h = int(mt['time'].split(':')[0])
                        dur_hours = max(1, (mt.get('duration_minutes') or 60) // 60)
                        for i in range(dur_hours):
                            occupied.add(h + i)
                # Find first 2-hour consecutive free slot between 9-18
                focus_start = None
                for h in range(9, 17):
                    if h not in occupied and (h + 1) not in occupied:
                        focus_start = h
                        break
                if focus_start:
                    focus_blocks = [{'start': f'{focus_start:02d}:00', 'end': f'{focus_start+2:02d}:00', 'label': 'Deep Work'}]
                else:
                    focus_blocks = []
            else:
                focus_blocks = []

            total_load = len(day_meetings) + len(day_tasks)
            workload = 'heavy' if total_load >= 4 else ('moderate' if total_load >= 2 else 'light')

            fixed_days.append({
                'date': date,
                'day_name': d['day_name'],
                'scheduled_meetings': day_meetings,
                'suggested_task_slots': task_slots,
                'focus_blocks': focus_blocks,
                'workload_level': workload,
            })

        return {
            'week_start': week_start,
            'daily_plans': fixed_days,
            'weekly_summary': ai.get('weekly_summary') or '',
            'conflicts_detected': ai.get('conflicts_detected') or [],
            'recommendations': ai.get('recommendations') or [],
        }

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

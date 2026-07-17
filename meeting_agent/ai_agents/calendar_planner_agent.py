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

    def plan_week(self, meetings: list, tasks: list, week_start: str = None,
                  work_start_hour: int = 9, work_end_hour: int = 17) -> dict:
        """Generate an optimized weekly plan given meetings and tasks.

        Task slots are hourly within [work_start_hour, work_end_hour), skipping a
        12:00 lunch hour if it falls in the window.
        """
        self.log_action("plan_week", {"meetings": len(meetings), "tasks": len(tasks),
                                       "hours": f"{work_start_hour}-{work_end_hour}"})
        if not week_start:
            week_start = timezone.now().strftime('%Y-%m-%d')
        try:
            work_start_hour = max(0, min(23, int(work_start_hour)))
            work_end_hour = max(work_start_hour + 1, min(24, int(work_end_hour)))
        except (ValueError, TypeError):
            work_start_hour, work_end_hour = 9, 17

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

        # Detect meeting-vs-meeting time overlaps in Python (a task never
        # conflicts with a meeting — tasks are scheduled AROUND meetings). For
        # each clash, suggest moving the later meeting to start right after the
        # earlier one ends. This replaces the unreliable AI-guessed conflicts.
        def _mins(t):
            try:
                return int(t.split(':')[0]) * 60 + int(t.split(':')[1])
            except (ValueError, IndexError, AttributeError):
                return None

        meeting_conflicts = []
        for date in sorted(meetings_by_date.keys()):
            day_ms = [mt for mt in meetings_by_date[date] if _mins(mt.get('time'))
                      is not None]
            day_ms.sort(key=lambda mt: _mins(mt['time']))
            for i in range(len(day_ms)):
                for j in range(i + 1, len(day_ms)):
                    a, b = day_ms[i], day_ms[j]
                    a_start = _mins(a['time'])
                    a_end = a_start + (a.get('duration_minutes') or 60)
                    b_start = _mins(b['time'])
                    if b_start < a_end:  # b starts before a ends -> overlap
                        new_start = a_end
                        nh, nm = new_start // 60, new_start % 60
                        meeting_conflicts.append(
                            f"{date}: “{a['title']}” and “{b['title']}” overlap — "
                            f"move “{b['title']}” to {nh:02d}:{nm:02d} (after “{a['title']}” ends)."
                        )

        # Hourly task slots within the user's work window, skipping a 12:00
        # lunch hour if it falls inside it.
        slot_hours = [h for h in range(work_start_hour, work_end_hour) if h != 12]
        slot_times = [f'{h:02d}:00' for h in slot_hours]

        # Hours occupied by meetings on each date — used so task slots and focus
        # blocks never land on top of a meeting. A meeting blocks every hour it
        # touches: from its start hour through the hour its (start + duration)
        # falls in. So a 10:00 meeting for 90 min (ends 11:30) blocks hours 10
        # AND 11, not just 10.
        def _meeting_occupied_hours(date):
            occ = set()
            for mt in meetings_by_date.get(date, []):
                t = mt.get('time') or ''
                if not t or ':' not in t:
                    continue
                try:
                    sh, sm = int(t.split(':')[0]), int(t.split(':')[1])
                except (ValueError, IndexError):
                    continue
                dur = mt.get('duration_minutes') or 60
                end_minutes = sh * 60 + sm + dur
                end_hour = (end_minutes - 1) // 60  # last hour the meeting still touches
                for h in range(sh, end_hour + 1):
                    occ.add(h)
            return occ

        # Free task-slot count for a day = slot_times not blocked by a meeting
        # and not already used by another task placed there.
        def _free_slot_count(date):
            occ = _meeting_occupied_hours(date)
            used_by_tasks = len(tasks_by_date.get(date, []))
            free = sum(1 for h in slot_hours if h not in occ)
            return max(0, free - used_by_tasks)

        # Distribute tasks across days with the most free capacity (Python, no AI)
        work_days = [d for d in week_dates if day_names[datetime.strptime(d['date'], '%Y-%m-%d').weekday()] not in ('Saturday', 'Sunday')]
        tasks_by_date = {d['date']: [] for d in week_dates}
        unscheduled_tasks = []  # tasks that couldn't fit any day's free slots
        week_date_set = {d['date'] for d in week_dates}
        task_queue = list(tasks[:20])
        for task in task_queue:
            due = (task.get('due_date') or '')[:10]
            placed = False
            # Prefer the due-date day, but only if it actually has a free slot.
            if due and due in week_date_set and _free_slot_count(due) > 0:
                tasks_by_date[due].append(task)
                placed = True
            if not placed:
                # Otherwise pick the weekday with the most free capacity.
                candidates = sorted(work_days, key=lambda x: _free_slot_count(x['date']), reverse=True)
                for d in candidates:
                    if _free_slot_count(d['date']) > 0:
                        tasks_by_date[d['date']].append(task)
                        placed = True
                        break
            if not placed:
                unscheduled_tasks.append(task.get('title', ''))

        # Ask AI only for summary, recommendations, focus blocks per day
        days_summary = '\n'.join(
            f"  {d['date']} ({d['day_name']}): meetings={[m['title'] for m in meetings_by_date.get(d['date'], [])]}, tasks={[t.get('title') for t in tasks_by_date.get(d['date'], [])]}"
            for d in week_dates
        )
        prompt = f"""You are a calendar assistant. Given this weekly schedule, write a brief summary and 2-3 practical recommendations.

Schedule:
{days_summary}

Do NOT list time conflicts — those are computed separately. Tasks are always scheduled around meetings, so a task and a meeting are never in conflict.

Return ONLY this JSON (no markdown):
{{
  "weekly_summary": "...",
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

            # Assign slot times to tasks — skip any slot whose hour is taken by a
            # meeting, so a suggested task never overlaps a real meeting.
            meeting_hours = _meeting_occupied_hours(date)
            task_slots = []
            available_slots = [s for s, h in zip(slot_times, slot_hours) if h not in meeting_hours]
            for i, task in enumerate(day_tasks):
                if i >= len(available_slots):
                    break  # no free slot left; task stays visible via unscheduled_tasks
                # If this task's own due date isn't this day, it was moved here
                # because its due-date day was already full — flag that for the UI.
                task_due = (task.get('due_date') or '')[:10]
                task_slots.append({
                    'time': available_slots[i],
                    'task': task.get('title', ''),
                    'duration_minutes': 60,
                    'adjusted': bool(task_due) and task_due != date,
                    'due_date': task_due or None,
                })

            # Focus block — first 2-hour gap free of BOTH meetings and task slots.
            if not is_weekend:
                occupied = set(meeting_hours)
                for ts in task_slots:
                    occupied.add(int(ts['time'].split(':')[0]))
                focus_start = None
                # Look for a 2-hour gap within the work window (leave room for
                # the 2nd hour, so stop at work_end_hour - 2).
                for h in range(work_start_hour, max(work_start_hour, work_end_hour - 1)):
                    if h not in occupied and (h + 1) not in occupied:
                        focus_start = h
                        break
                focus_blocks = (
                    [{'start': f'{focus_start:02d}:00', 'end': f'{focus_start+2:02d}:00', 'label': 'Deep Work'}]
                    if focus_start is not None else []
                )
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
            # Python-computed meeting-vs-meeting conflicts (not AI-guessed).
            'conflicts_detected': meeting_conflicts,
            'recommendations': ai.get('recommendations') or [],
            # Tasks that couldn't fit any day's free slots this week — surfaced so
            # they aren't silently dropped from the plan.
            'unscheduled_tasks': unscheduled_tasks,
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

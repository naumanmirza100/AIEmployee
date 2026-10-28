"""
Proactive Notification Agent — AI Executive Meeting Assistant
Handles: scanning for upcoming meetings/overdue tasks, sending smart reminders,
escalating critical items, and generating notification messages.
"""

import json
import re
import logging
from datetime import timedelta
from typing import Optional

from django.db import models
from django.utils import timezone

from project_manager_agent.ai_agents.base_agent import BaseAgent

# Where the bell's Executive Meeting alerts open.
AGENT_TASKS = '/exec-meeting/dashboard?tab=tasks'
AGENT_MEETINGS = '/exec-meeting/dashboard?tab=meetings'

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Proactive Notification Agent for an AI Executive Meeting Assistant.
You proactively alert executives about important upcoming events and overdue items.

Your capabilities:
- Generate smart, contextual reminder messages
- Prioritize notifications by urgency and importance
- Draft escalation messages for critical overdue items
- Summarize what needs attention right now
- Create concise, actionable notification text

Write notification messages that are brief, clear, and immediately actionable.
"""


class ProactiveNotificationAgent(BaseAgent):

    def __init__(self, company_id: Optional[int] = None):
        super().__init__()
        self.company_id = company_id
        self.agent_key_name = 'exec_meeting_agent'
        self.system_prompt = SYSTEM_PROMPT

    def scan_and_create_notifications(self, company_user_id: int) -> list:
        """
        Scan meetings and tasks for notification-worthy events and create
        ExecNotification records. Returns list of created notification dicts.
        """
        self.log_action("scan_and_create_notifications")
        from meeting_agent.models import (
            ExecutiveMeeting, ExecutiveMeetingParticipant,
            ExecutiveTask, MeetingActionItem, ExecNotification,
        )
        from core.models import CompanyUser
        from meeting_agent import clock
        from meeting_agent.bell import ring, task_people
        owner = CompanyUser.objects.select_related('company').filter(id=company_user_id).first()
        if owner is None:
            return []
        # Today on the company's clock, not the server's (CO-210).
        today = clock.today(owner.company)
        created = []

        # Meeting reminders are the five-minute job's (meeting_agent.tasks.send_meeting_reminders). This scan raised
        # the organiser's too, and when it ran first the job skipped the people invited (CO-259).

        # Each alert is raised once per due date: it came twice a day for as long as the task stayed open, and a
        # deleted one came back within fifteen minutes (CO-169). It reaches the owner and the people it is assigned
        # to, in the bell as well as on this agent's page.
        # --- Overdue tasks ---
        overdue_tasks = (ExecutiveTask.objects.filter(company_user_id=company_user_id,
                                                      status__in=['todo', 'in_progress', 'review'],
                                                      due_date__lt=today)
                         .exclude(overdue_alerted_for=models.F('due_date'))
                         .prefetch_related('assignees'))
        for task in overdue_tasks[:50]:
            notif = ExecNotification.objects.create(
                company_user_id=company_user_id,
                notification_type='task_overdue',
                severity='critical',
                title=f"Overdue task: {task.title}"[:255],
                message=f"Task '{task.title}' was due on {task.due_date:%d %b %Y} and is still {task.get_status_display()}.",
                data={'task_id': task.id, 'due_date': str(task.due_date), 'priority': task.priority},
            )
            ring(task_people(task), title=notif.title, message=notif.message, kind='exec_task_overdue',
                 link=f'{AGENT_TASKS}', employee_link='/me/tasks', severity='critical',
                 data={'task_id': task.id})
            ExecutiveTask.objects.filter(id=task.id).update(overdue_alerted_for=task.due_date)
            created.append({'id': notif.id, 'type': 'task_overdue', 'title': notif.title})

        # --- Overdue action items ---
        overdue_actions = (MeetingActionItem.objects.filter(meeting__organizer_id=company_user_id,
                                                            status__in=['open', 'in_progress'],
                                                            due_date__lt=today)
                           .exclude(overdue_alerted_for=models.F('due_date'))
                           .select_related('meeting', 'assignee'))
        for item in overdue_actions[:50]:
            notif = ExecNotification.objects.create(
                company_user_id=company_user_id,
                notification_type='action_item_overdue',
                severity='warning',
                title=f"Overdue action item: {item.title}"[:255],
                message=f"Action item '{item.title}' from meeting '{item.meeting.title}' was due on {item.due_date:%d %b %Y}.",
                meeting=item.meeting,
                data={'action_item_id': item.id, 'meeting_id': item.meeting_id, 'due_date': str(item.due_date)},
            )
            ring([owner, item.assignee], title=notif.title, message=notif.message, kind='exec_action_item_overdue',
                 link=f'{AGENT_MEETINGS}', severity='warning', data={'action_item_id': item.id})
            MeetingActionItem.objects.filter(id=item.id).update(overdue_alerted_for=item.due_date)
            created.append({'id': notif.id, 'type': 'action_item_overdue', 'title': notif.title})

        # --- Tasks due today ---
        due_today = (ExecutiveTask.objects.filter(company_user_id=company_user_id,
                                                  status__in=['todo', 'in_progress'], due_date=today)
                     .exclude(due_today_alerted_for=models.F('due_date'))
                     .prefetch_related('assignees'))
        for task in due_today[:50]:
            notif = ExecNotification.objects.create(
                company_user_id=company_user_id,
                notification_type='task_due',
                severity='info',
                title=f"Task due today: {task.title}"[:255],
                message=f"Task '{task.title}' [{task.get_priority_display()}] is due today.",
                data={'task_id': task.id, 'priority': task.priority},
            )
            ring(task_people(task), title=notif.title, message=notif.message, kind='exec_task_due',
                 link=f'{AGENT_TASKS}', employee_link='/me/tasks', data={'task_id': task.id})
            ExecutiveTask.objects.filter(id=task.id).update(due_today_alerted_for=task.due_date)
            created.append({'id': notif.id, 'type': 'task_due', 'title': notif.title})

        return created

    def generate_smart_message(self, notification_type: str, context: dict) -> str:
        """Generate a smart, contextual notification message using AI."""
        self.log_action("generate_smart_message")
        prompt = f"""Generate a brief, professional notification message for an executive.

Notification type: {notification_type}
Context: {json.dumps(context, indent=2)}

Write a single, clear notification message (1-2 sentences max).
Be direct and actionable. No fluff."""
        return self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=100)

    def generate_daily_digest(self, company_user_id: int, company_user_name: str = '') -> dict:
        """Generate an AI daily digest summarizing what needs attention."""
        self.log_action("generate_daily_digest")
        from core.models import CompanyUser
        from meeting_agent import clock
        from meeting_agent.models import ExecutiveMeeting, ExecutiveTask, MeetingActionItem
        now = timezone.now()
        # Today on the company's clock; the typed times of today's meetings carry today's date (CO-210).
        owner = CompanyUser.objects.select_related('company').filter(id=company_user_id).first()
        today = clock.today(owner.company) if owner else now.date()

        # The time as typed, which is the company's own clock. Sent as a stored datetime ("03:25:00+00:00") it was
        # read as UTC, and the digest said "at 03:25 UTC" of a meeting at 03:25 in Karachi (film, 29 Oct 2026).
        todays_meetings = [
            {'title': m['title'], 'time': f"{m['scheduled_at']:%H:%M}", 'duration_minutes': m['duration_minutes']}
            for m in ExecutiveMeeting.objects.filter(
                organizer_id=company_user_id,
                scheduled_at__date=today,
                status__in=['scheduled', 'in_progress'],
            ).order_by('scheduled_at').values('title', 'scheduled_at', 'duration_minutes')[:10]
        ]

        overdue_tasks = ExecutiveTask.objects.filter(
            company_user_id=company_user_id,
            status__in=['todo', 'in_progress'],
            due_date__lt=today,
        ).count()

        due_today_count = ExecutiveTask.objects.filter(
            company_user_id=company_user_id,
            status__in=['todo', 'in_progress'],
            due_date=today,
        ).count()

        pending_action_qs = MeetingActionItem.objects.filter(
            meeting__organizer_id=company_user_id,
            status__in=['open', 'in_progress'],
        ).select_related('meeting')[:10]
        pending_actions_list = [
            {
                'title': a.title,
                'meeting': a.meeting.title if a.meeting else '',
                'due_date': str(a.due_date) if a.due_date else None,
                'priority': a.priority,
            }
            for a in pending_action_qs
        ]
        pending_actions_count = len(pending_action_qs)

        # Also get executive tasks due today or overdue
        due_tasks_list = list(ExecutiveTask.objects.filter(
            company_user_id=company_user_id,
            status__in=['todo', 'in_progress'],
            due_date__lte=today,
        ).values('title', 'priority', 'due_date', 'status')[:10])

        prompt = f"""Generate a brief executive daily digest.

Executive: {company_user_name or 'Executive'}
Today: {today}

Today's meetings: {len(todays_meetings)} scheduled (times are the company's own clock: write them as given, with no time zone)
{json.dumps(todays_meetings, indent=2, default=str)}

Overdue tasks: {overdue_tasks}
Tasks due today: {due_today_count}
Pending action items ({pending_actions_count}):
{json.dumps(pending_actions_list, indent=2, default=str)}

Due/overdue executive tasks:
{json.dumps(due_tasks_list, indent=2, default=str)}

Return ONLY a JSON object:
{{
  "greeting": "Good morning, [name]!",
  "summary": "2-3 sentence overview of the day",
  "top_priorities": ["priority 1", "priority 2", "priority 3"],
  "alerts": ["alert if anything critical"],
  "focus_recommendation": "what to focus on first"
}}

Return ONLY the JSON."""
        raw = self._call_llm(prompt, self.system_prompt, temperature=0.4, max_tokens=500)
        result = self._extract_json(raw)
        result['stats'] = {
            'meetings_today': len(todays_meetings),
            'overdue_tasks': overdue_tasks,
            'due_today': due_today_count,
            'pending_actions': pending_actions_count,
        }
        result['pending_action_items'] = pending_actions_list
        result['due_tasks'] = due_tasks_list
        return result

    def process(self, action: str = 'scan', **kwargs) -> dict:
        try:
            if action == 'scan':
                return {
                    'success': True,
                    'created': self.scan_and_create_notifications(kwargs['company_user_id']),
                }
            if action == 'smart_message':
                return {
                    'success': True,
                    'message': self.generate_smart_message(kwargs['notification_type'], kwargs.get('context', {})),
                }
            if action == 'daily_digest':
                return {
                    'success': True,
                    'digest': self.generate_daily_digest(
                        kwargs['company_user_id'],
                        kwargs.get('company_user_name', ''),
                    ),
                }
            return {'success': False, 'error': f"Unknown action: {action}"}
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            logger.error("ProactiveNotificationAgent.process error: %s", e)
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

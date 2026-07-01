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

from django.utils import timezone

from project_manager_agent.ai_agents.base_agent import BaseAgent

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
        self.agent_key_name = 'exec_proactive_notification'
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
        now = timezone.now()
        created = []

        # --- Meeting reminders: meetings in next 15 minutes ---
        upcoming = ExecutiveMeeting.objects.filter(
            organizer_id=company_user_id,
            status='scheduled',
            scheduled_at__gte=now,
            scheduled_at__lte=now + timedelta(minutes=15),
        )
        for meeting in upcoming:
            exists = ExecNotification.objects.filter(
                company_user_id=company_user_id,
                notification_type='meeting_reminder',
                meeting=meeting,
                created_at__gte=now - timedelta(minutes=20),
            ).exists()
            if not exists:
                notif = ExecNotification.objects.create(
                    company_user_id=company_user_id,
                    notification_type='meeting_reminder',
                    severity='warning',
                    title=f"Meeting starting soon: {meeting.title}",
                    message=f"Your meeting '{meeting.title}' starts in less than 15 minutes.",
                    meeting=meeting,
                    data={'meeting_id': meeting.id, 'scheduled_at': meeting.scheduled_at.isoformat()},
                )
                created.append({'id': notif.id, 'type': 'meeting_reminder', 'title': notif.title})

        # --- Overdue tasks ---
        overdue_tasks = ExecutiveTask.objects.filter(
            company_user_id=company_user_id,
            status__in=['todo', 'in_progress', 'review'],
            due_date__lt=now.date(),
        )
        for task in overdue_tasks[:10]:
            exists = ExecNotification.objects.filter(
                company_user_id=company_user_id,
                notification_type='task_overdue',
                data__task_id=task.id,
                created_at__gte=now - timedelta(hours=12),
            ).exists()
            if not exists:
                notif = ExecNotification.objects.create(
                    company_user_id=company_user_id,
                    notification_type='task_overdue',
                    severity='critical',
                    title=f"Overdue task: {task.title}",
                    message=f"Task '{task.title}' was due on {task.due_date} and is still {task.get_status_display()}.",
                    data={'task_id': task.id, 'due_date': str(task.due_date), 'priority': task.priority},
                )
                created.append({'id': notif.id, 'type': 'task_overdue', 'title': notif.title})

        # --- Overdue action items ---
        overdue_actions = MeetingActionItem.objects.filter(
            meeting__organizer_id=company_user_id,
            status__in=['open', 'in_progress'],
            due_date__lt=now.date(),
        )
        for item in overdue_actions[:10]:
            exists = ExecNotification.objects.filter(
                company_user_id=company_user_id,
                notification_type='action_item_overdue',
                data__action_item_id=item.id,
                created_at__gte=now - timedelta(hours=12),
            ).exists()
            if not exists:
                notif = ExecNotification.objects.create(
                    company_user_id=company_user_id,
                    notification_type='action_item_overdue',
                    severity='warning',
                    title=f"Overdue action item: {item.title}",
                    message=f"Action item '{item.title}' from meeting '{item.meeting.title}' is overdue.",
                    meeting=item.meeting,
                    data={'action_item_id': item.id, 'meeting_id': item.meeting_id, 'due_date': str(item.due_date)},
                )
                created.append({'id': notif.id, 'type': 'action_item_overdue', 'title': notif.title})

        # --- Tasks due today ---
        due_today = ExecutiveTask.objects.filter(
            company_user_id=company_user_id,
            status__in=['todo', 'in_progress'],
            due_date=now.date(),
        )
        for task in due_today[:5]:
            exists = ExecNotification.objects.filter(
                company_user_id=company_user_id,
                notification_type='task_due',
                data__task_id=task.id,
                created_at__gte=now.replace(hour=0, minute=0, second=0, microsecond=0),
            ).exists()
            if not exists:
                notif = ExecNotification.objects.create(
                    company_user_id=company_user_id,
                    notification_type='task_due',
                    severity='info',
                    title=f"Task due today: {task.title}",
                    message=f"Task '{task.title}' [{task.get_priority_display()}] is due today.",
                    data={'task_id': task.id, 'priority': task.priority},
                )
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
        from meeting_agent.models import ExecutiveMeeting, ExecutiveTask, MeetingActionItem
        now = timezone.now()
        today = now.date()

        todays_meetings = list(ExecutiveMeeting.objects.filter(
            organizer_id=company_user_id,
            scheduled_at__date=today,
            status__in=['scheduled', 'in_progress'],
        ).values('id', 'title', 'scheduled_at', 'duration_minutes')[:10])

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

        pending_actions = MeetingActionItem.objects.filter(
            meeting__organizer_id=company_user_id,
            status__in=['open', 'in_progress'],
        ).count()

        prompt = f"""Generate a brief executive daily digest.

Executive: {company_user_name or 'Executive'}
Today: {today}

Today's meetings: {len(todays_meetings)} scheduled
{json.dumps(todays_meetings, indent=2, default=str)}

Overdue tasks: {overdue_tasks}
Tasks due today: {due_today_count}
Pending action items: {pending_actions}

Return ONLY a JSON object:
{{
  "greeting": "Good morning, [name]!",
  "summary": "2-3 sentence overview of the day",
  "top_priorities": ["priority 1", "priority 2", "priority 3"],
  "alerts": ["alert if anything critical"],
  "focus_recommendation": "what to focus on first"
}}

Return ONLY the JSON."""
        raw = self._call_llm(prompt, self.system_prompt, temperature=0.4, max_tokens=400)
        result = self._extract_json(raw)
        result['stats'] = {
            'meetings_today': len(todays_meetings),
            'overdue_tasks': overdue_tasks,
            'due_today': due_today_count,
            'pending_actions': pending_actions,
        }
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

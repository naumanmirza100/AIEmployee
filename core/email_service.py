"""
Email Service for Project Manager Agent
Handles sending emails for task assignments, reminders, and notifications.
"""

from typing import Dict, Optional, Any
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from django.template import Template, Context
from django.utils.html import strip_tags
from django.utils import timezone

from .models import EmailTemplate, EmailLog, UserProfile


class EmailService:
    """Service for sending emails using templates"""
    
    def __init__(self):
        self.from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')
    
    def _render_template(self, template_string: str, context: Dict[str, Any]) -> str:
        """
        Render a template string with context variables.
        
        Args:
            template_string: Template string with variables like {{ variable_name }}
            context: Dictionary of variables to substitute
            
        Returns:
            Rendered template string
        """
        try:
            template = Template(template_string)
            return template.render(Context(context))
        except Exception as e:
            # If template rendering fails, return original string
            return template_string
    
    def _log_email(
        self,
        recipient: str,
        subject: str,
        status: str,
        template: Optional[EmailTemplate] = None,
        error_message: Optional[str] = None,
        related_object_type: Optional[str] = None,
        related_object_id: Optional[int] = None,
    ) -> EmailLog:
        """
        Log email sending attempt to database.
        
        Args:
            recipient: Email recipient
            subject: Email subject
            status: 'sent', 'failed', or 'pending'
            template: EmailTemplate used (optional)
            error_message: Error message if failed (optional)
            related_object_type: Type of related object (optional)
            related_object_id: ID of related object (optional)
            
        Returns:
            EmailLog instance
        """
        return EmailLog.objects.create(
            recipient=recipient,
            subject=subject,
            template=template,
            status=status,
            error_message=error_message,
            related_object_type=related_object_type,
            related_object_id=related_object_id,
        )
    
    def _check_email_preferences(self, user, notification_type: str) -> bool:
        """
        Check if user has email notifications enabled for the given notification type.
        
        Args:
            user: User instance
            notification_type: Type of notification
            
        Returns:
            True if email should be sent, False otherwise
        """
        try:
            profile = user.profile
            if not profile.email_notifications_enabled:
                return False
            # Someone who is also a dashboard login of the same company may have
            # paused all emails, or turned task emails off, on the notification
            # settings page. Until this asked, a paused person still got these.
            if notification_type == 'task_assigned':
                from core.notification_settings import address_wants_email
                if not address_wants_email(profile.company_id, user.email, 'tasks_assigned'):
                    return False
            
            # Check notification preferences if they exist
            from .models import NotificationPreference
            try:
                pref = NotificationPreference.objects.get(
                    user=user,
                    notification_type=notification_type
                )
                return pref.email_enabled
            except NotificationPreference.DoesNotExist:
                # Default to enabled if no preference exists
                return True
        except UserProfile.DoesNotExist:
            # Default to enabled if no profile exists
            return True
    
    def send_email(
        self,
        recipient: str,
        subject: str,
        message_text: str,
        message_html: Optional[str] = None,
        template: Optional[EmailTemplate] = None,
        context: Optional[Dict[str, Any]] = None,
        related_object_type: Optional[str] = None,
        related_object_id: Optional[int] = None,
    ) -> bool:
        """
        Send an email to a recipient.
        
        Args:
            recipient: Email recipient address
            subject: Email subject
            message_text: Plain text message body
            message_html: HTML message body (optional)
            template: EmailTemplate used (optional, for logging)
            context: Context variables used in template (optional)
            related_object_type: Type of related object (optional)
            related_object_id: ID of related object (optional)
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        # Render templates if provided
        if template:
            if template.subject_template:
                subject = self._render_template(template.subject_template, context or {})
            if template.body_text_template:
                message_text = self._render_template(template.body_text_template, context or {})
            if template.body_html_template:
                message_html = self._render_template(template.body_html_template, context or {})
        
        try:
            # Send email
            if message_html:
                # Send HTML email with text fallback
                email = EmailMultiAlternatives(
                    subject=subject,
                    body=message_text,
                    from_email=self.from_email,
                    to=[recipient],
                )
                email.attach_alternative(message_html, "text/html")
                email.send()
            else:
                # Send plain text email
                send_mail(
                    subject=subject,
                    message=message_text,
                    from_email=self.from_email,
                    recipient_list=[recipient],
                    fail_silently=False,
                )
            
            # Log successful send
            self._log_email(
                recipient=recipient,
                subject=subject,
                status='sent',
                template=template,
                related_object_type=related_object_type,
                related_object_id=related_object_id,
            )
            return True
            
        except Exception as e:
            # Log failed send
            self._log_email(
                recipient=recipient,
                subject=subject,
                status='failed',
                template=template,
                error_message=str(e),
                related_object_type=related_object_type,
                related_object_id=related_object_id,
            )
            return False
    
    def send_task_assignment_email(self, task, assignee) -> bool:
        """
        Send email notification when a task is assigned to a user.
        
        Args:
            task: Task instance
            assignee: User instance who is assigned the task
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        # Check if user wants email notifications
        if not self._check_email_preferences(assignee, 'task_assigned'):
            return False
        
        # Try to get template, otherwise use default
        try:
            template = EmailTemplate.objects.get(
                template_type='task_assigned',
                is_active=True
            )
            context = {
                'task_title': task.title,
                'task_description': task.description,
                'task_priority': task.get_priority_display(),
                'task_due_date': task.due_date.strftime('%Y-%m-%d %H:%M') if task.due_date else 'Not set',
                'project_name': task.project.name,
                'assignee_name': assignee.get_full_name() or assignee.username,
                'task_url': self._get_task_url(task),
                'task_reasoning': task.ai_reasoning or 'No implementation suggestions provided.',
            }
            return self.send_email(
                recipient=assignee.email,
                subject="",  # Will be set from template
                message_text="",  # Will be set from template
                template=template,
                context=context,
                related_object_type='Task',
                related_object_id=task.id,
            )
        except EmailTemplate.DoesNotExist:
            # Use default email if no template found
            subject = f"New Task Assigned: {task.title}"
            reasoning_section = ""
            if task.ai_reasoning:
                reasoning_section = f"""

AI Reasoning & Implementation Suggestions:
{task.ai_reasoning}

"""
            message_text = f"""
Hello {assignee.get_full_name() or assignee.username},

You have been assigned a new task:

Task: {task.title}
Project: {task.project.name}
Priority: {task.get_priority_display()}
Due Date: {task.due_date.strftime('%Y-%m-%d %H:%M') if task.due_date else 'Not set'}

Description:
{task.description or 'No description provided.'}
{reasoning_section}Please review and start working on this task.

Task URL: {self._get_task_url(task)}
"""
            return self.send_email(
                recipient=assignee.email,
                subject=subject,
                message_text=message_text.strip(),
                related_object_type='Task',
                related_object_id=task.id,
            )
    
    def _get_task_url(self, task=None) -> str:
        """Where the assignee sees their tasks: My Space, on the website.

        This used to be built from the API server's address and pointed at
        /projects/<id>/tasks/<id>/, a page that does not exist."""
        base = (getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
        return f'{base}/me/tasks' if base else '/me/tasks'

    def send_tasks_assigned_summary(self, assignee, tasks, reason: str = '') -> bool:
        """One email for several tasks given to one person at once (a hand-over).

        Takes the place of one "New Task Assigned" email per task. Obeys the same
        switches as that email."""
        tasks = list(tasks)
        if not tasks or not getattr(assignee, 'email', ''):
            return False
        if len(tasks) == 1:
            return self.send_task_assignment_email(tasks[0], assignee)
        if not self._check_email_preferences(assignee, 'task_assigned'):
            return False
        lines = []
        for task in tasks:
            due = task.due_date.strftime('%Y-%m-%d') if task.due_date else 'no due date'
            lines.append(f"- {task.title} ({task.project.name}; {task.get_priority_display()}; {due})")
        message_text = (
            f"Hello {assignee.get_full_name() or assignee.username},\n\n"
            f"{len(tasks)} tasks have been assigned to you."
            + (f" {reason}" if reason else '') + "\n\n"
            + "\n".join(lines)
            + f"\n\nSee them all: {self._get_task_url()}"
        )
        return self.send_email(
            recipient=assignee.email,
            subject=f"{len(tasks)} tasks assigned to you",
            message_text=message_text,
            related_object_type='Task',
            related_object_id=tasks[0].id,
        )
    
    def send_task_due_reminder(self, task, recipient, days_until_due: int = 1) -> bool:
        """
        Send email reminder for upcoming task due date.
        
        Args:
            task: Task instance
            recipient: User instance to send reminder to
            days_until_due: Number of days until due date (for context)
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        if not task.due_date:
            return False
        
        # Check if user wants email notifications
        if not self._check_email_preferences(recipient, 'deadline_approaching'):
            return False
        
        # Try to get template
        try:
            template = EmailTemplate.objects.get(
                template_type='task_reminder',
                is_active=True
            )
            context = {
                'task_title': task.title,
                'task_description': task.description,
                'task_priority': task.get_priority_display(),
                'task_due_date': task.due_date.strftime('%Y-%m-%d %H:%M'),
                'days_until_due': days_until_due,
                'project_name': task.project.name,
                'recipient_name': recipient.get_full_name() or recipient.username,
                'task_url': self._get_task_url(task),
            }
            return self.send_email(
                recipient=recipient.email,
                subject="",
                message_text="",
                template=template,
                context=context,
                related_object_type='Task',
                related_object_id=task.id,
            )
        except EmailTemplate.DoesNotExist:
            # Default reminder email
            subject = f"Reminder: Task Due Soon - {task.title}"
            due_date_str = task.due_date.strftime('%B %d, %Y at %I:%M %p')
            
            if days_until_due == 0:
                urgency = "TODAY"
            elif days_until_due == 1:
                urgency = "TOMORROW"
            else:
                urgency = f"in {days_until_due} days"
            
            message_text = f"""
Hello {recipient.get_full_name() or recipient.username},

This is a reminder that you have a task due {urgency}:

Task: {task.title}
Project: {task.project.name}
Priority: {task.get_priority_display()}
Due Date: {due_date_str}

Description:
{task.description or 'No description provided.'}

Please ensure this task is completed on time.

Task URL: {self._get_task_url(task)}
"""
            return self.send_email(
                recipient=recipient.email,
                subject=subject,
                message_text=message_text.strip(),
                related_object_type='Task',
                related_object_id=task.id,
            )
    
    def send_task_overdue_notification(self, task, recipient) -> bool:
        """
        Send email notification for overdue task.
        
        Args:
            task: Task instance
            recipient: User instance to send notification to
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        if not task.due_date:
            return False
        
        # Check if user wants email notifications
        if not self._check_email_preferences(recipient, 'deadline_approaching'):
            return False
        
        # Calculate days overdue
        from django.utils import timezone
        now = timezone.now()
        if task.due_date.tzinfo is None:
            # If task.due_date is naive, make it timezone-aware
            task_due = timezone.make_aware(task.due_date)
        else:
            task_due = task.due_date
        
        days_overdue = (now - task_due).days
        
        # Try to get template
        try:
            template = EmailTemplate.objects.get(
                template_type='task_overdue',
                is_active=True
            )
            context = {
                'task_title': task.title,
                'task_description': task.description,
                'task_priority': task.get_priority_display(),
                'task_due_date': task.due_date.strftime('%Y-%m-%d %H:%M'),
                'days_overdue': days_overdue,
                'project_name': task.project.name,
                'recipient_name': recipient.get_full_name() or recipient.username,
                'task_url': self._get_task_url(task),
            }
            return self.send_email(
                recipient=recipient.email,
                subject="",
                message_text="",
                template=template,
                context=context,
                related_object_type='Task',
                related_object_id=task.id,
            )
        except EmailTemplate.DoesNotExist:
            # Default overdue email
            subject = f"URGENT: Overdue Task - {task.title}"
            due_date_str = task.due_date.strftime('%B %d, %Y at %I:%M %p')
            
            message_text = f"""
Hello {recipient.get_full_name() or recipient.username},

This task is OVERDUE by {days_overdue} day{'s' if days_overdue != 1 else ''}:

Task: {task.title}
Project: {task.project.name}
Priority: {task.get_priority_display()}
Original Due Date: {due_date_str}
Days Overdue: {days_overdue}

Description:
{task.description or 'No description provided.'}

Please complete this task as soon as possible.

Task URL: {self._get_task_url(task)}
"""
            return self.send_email(
                recipient=recipient.email,
                subject=subject,
                message_text=message_text.strip(),
                related_object_type='Task',
                related_object_id=task.id,
            )
    
    def send_milestone_reminder(self, milestone, recipient, days_until_due: int = 1) -> bool:
        """
        Send email reminder for upcoming milestone due date.
        
        Args:
            milestone: ProjectMilestone instance
            recipient: User instance to send reminder to
            days_until_due: Number of days until due date
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        # Check if user wants email notifications
        if not self._check_email_preferences(recipient, 'deadline_approaching'):
            return False
        
        # Try to get template
        try:
            template = EmailTemplate.objects.get(
                template_type='milestone_reminder',
                is_active=True
            )
            context = {
                'milestone_title': milestone.title,
                'milestone_description': milestone.description or '',
                'milestone_due_date': milestone.due_date.strftime('%Y-%m-%d'),
                'days_until_due': days_until_due,
                'project_name': milestone.project.name,
                'recipient_name': recipient.get_full_name() or recipient.username,
            }
            return self.send_email(
                recipient=recipient.email,
                subject="",
                message_text="",
                template=template,
                context=context,
                related_object_type='ProjectMilestone',
                related_object_id=milestone.id,
            )
        except EmailTemplate.DoesNotExist:
            # Default milestone reminder
            subject = f"Milestone Reminder: {milestone.title}"
            due_date_str = milestone.due_date.strftime('%B %d, %Y')
            
            if days_until_due == 0:
                urgency = "TODAY"
            elif days_until_due == 1:
                urgency = "TOMORROW"
            else:
                urgency = f"in {days_until_due} days"
            
            message_text = f"""
Hello {recipient.get_full_name() or recipient.username},

This is a reminder about an upcoming project milestone due {urgency}:

Milestone: {milestone.title}
Project: {milestone.project.name}
Due Date: {due_date_str}

Description:
{milestone.description or 'No description provided.'}

Please ensure all related tasks are on track to meet this milestone.
"""
            return self.send_email(
                recipient=recipient.email,
                subject=subject,
                message_text=message_text.strip(),
                related_object_type='ProjectMilestone',
                related_object_id=milestone.id,
            )
    
    def send_meeting_reminder(self, meeting, recipient, hours_before: int = 1) -> bool:
        """
        Send email reminder for upcoming meeting.
        
        Args:
            meeting: Meeting instance
            recipient: User instance to send reminder to
            hours_before: Number of hours before meeting (for context)
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        # Check if user wants email notifications
        # Using 'deadline_approaching' as meeting reminder preference
        if not self._check_email_preferences(recipient, 'deadline_approaching'):
            return False
        
        # Try to get template
        try:
            template = EmailTemplate.objects.get(
                template_type='meeting_upcoming',
                is_active=True
            )
            
            # Get participant names
            participants = [p.get_full_name() or p.username for p in meeting.participants.all()]
            
            context = {
                'meeting_title': meeting.title,
                'meeting_description': meeting.description or '',
                'meeting_date': meeting.scheduled_at.strftime('%Y-%m-%d %H:%M'),
                'meeting_duration': meeting.duration_minutes,
                'hours_before': hours_before,
                'organizer_name': meeting.organizer.get_full_name() or meeting.organizer.username,
                'participants': ', '.join(participants) if participants else 'None',
                'recipient_name': recipient.get_full_name() or recipient.username,
            }
            return self.send_email(
                recipient=recipient.email,
                subject="",
                message_text="",
                template=template,
                context=context,
                related_object_type='Meeting',
                related_object_id=meeting.id,
            )
        except EmailTemplate.DoesNotExist:
            # Default meeting reminder
            subject = f"Meeting Reminder: {meeting.title}"
            meeting_date_str = meeting.scheduled_at.strftime('%B %d, %Y at %I:%M %p')
            
            participants = [p.get_full_name() or p.username for p in meeting.participants.all()]
            
            message_text = f"""
Hello {recipient.get_full_name() or recipient.username},

This is a reminder about an upcoming meeting in {hours_before} hour{'s' if hours_before != 1 else ''}:

Meeting: {meeting.title}
Date & Time: {meeting_date_str}
Duration: {meeting.duration_minutes} minutes
Organizer: {meeting.organizer.get_full_name() or meeting.organizer.username}

Participants:
{', '.join(participants) if participants else 'None'}

Description:
{meeting.description or 'No description provided.'}

Please join on time.
"""
            return self.send_email(
                recipient=recipient.email,
                subject=subject,
                message_text=message_text.strip(),
                related_object_type='Meeting',
                related_object_id=meeting.id,
            )


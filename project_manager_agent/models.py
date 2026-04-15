from django.db import models
from django.utils import timezone


class PMKnowledgeQAChat(models.Model):
    """Knowledge Q&A chat sessions for project manager. Each chat contains multiple messages."""
    company_user = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='pm_knowledge_qa_chats',
        help_text='Company user who owns this chat',
    )
    title = models.CharField(max_length=255, default='Chat', help_text='Chat title (e.g. first question snippet)')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'project_manager_agent'
        ordering = ['-updated_at']
        verbose_name = 'PM Knowledge QA Chat'
        verbose_name_plural = 'PM Knowledge QA Chats'
        indexes = [models.Index(fields=['company_user', '-updated_at'])]

    def __str__(self):
        return f"PM QA Chat: {self.title[:40]}... ({self.id})"


class PMKnowledgeQAChatMessage(models.Model):
    """Individual messages in a PM Knowledge QA chat."""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]
    chat = models.ForeignKey(
        PMKnowledgeQAChat,
        on_delete=models.CASCADE,
        related_name='messages',
        help_text='Chat this message belongs to',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField(help_text='Message content')
    response_data = models.JSONField(
        null=True,
        blank=True,
        help_text='For assistant: { answer, project_id, project_title }',
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'project_manager_agent'
        ordering = ['created_at']
        verbose_name = 'PM Knowledge QA Chat Message'
        verbose_name_plural = 'PM Knowledge QA Chat Messages'

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."


class PMProjectPilotChat(models.Model):
    """Project Pilot chat sessions for project manager. Each chat contains multiple messages."""
    company_user = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='pm_project_pilot_chats',
        help_text='Company user who owns this chat',
    )
    title = models.CharField(max_length=255, default='Chat', help_text='Chat title (e.g. first request snippet)')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'project_manager_agent'
        ordering = ['-updated_at']
        verbose_name = 'PM Project Pilot Chat'
        verbose_name_plural = 'PM Project Pilot Chats'
        indexes = [models.Index(fields=['company_user', '-updated_at'])]

    def __str__(self):
        return f"PM Pilot Chat: {self.title[:40]}... ({self.id})"


class PMProjectPilotChatMessage(models.Model):
    """Individual messages in a PM Project Pilot chat."""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]
    chat = models.ForeignKey(
        PMProjectPilotChat,
        on_delete=models.CASCADE,
        related_name='messages',
        help_text='Chat this message belongs to',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField(help_text='Message content (user request or assistant answer)')
    response_data = models.JSONField(
        null=True,
        blank=True,
        help_text='For assistant: { answer, action_results, cannot_do, project_id, project_title, from_file, file_name }',
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'project_manager_agent'
        ordering = ['created_at']
        verbose_name = 'PM Project Pilot Chat Message'
        verbose_name_plural = 'PM Project Pilot Chat Messages'

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."


class PMMeetingSchedulerChat(models.Model):
    """Meeting Scheduler chat sessions."""
    company_user = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='pm_meeting_scheduler_chats',
    )
    title = models.CharField(max_length=255, default='Chat')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'project_manager_agent'
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['company_user', '-updated_at'])]

    def __str__(self):
        return f"Meeting Chat: {self.title[:40]}... ({self.id})"


class PMMeetingSchedulerChatMessage(models.Model):
    ROLE_CHOICES = [('user', 'User'), ('assistant', 'Assistant')]
    chat = models.ForeignKey(PMMeetingSchedulerChat, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    response_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'project_manager_agent'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."


class PMNotification(models.Model):
    """Smart notifications generated by the AI agent system."""
    SEVERITY_CHOICES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]
    TYPE_CHOICES = [
        ('overdue_task', 'Overdue Task'),
        ('blocked_task', 'Blocked Task'),
        ('unassigned_high_priority', 'Unassigned High Priority'),
        ('deadline_approaching', 'Deadline Approaching'),
        ('workload_imbalance', 'Workload Imbalance'),
        ('project_at_risk', 'Project At Risk'),
        ('member_inactive', 'Member Inactive'),
        ('milestone_due', 'Milestone Due'),
        ('sprint_overloaded', 'Sprint Overloaded'),
        ('custom', 'Custom'),
    ]
    company_user = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='pm_notifications',
    )
    project = models.ForeignKey(
        'core.Project',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='pm_notifications',
    )
    notification_type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='info')
    title = models.CharField(max_length=255)
    message = models.TextField()
    data = models.JSONField(null=True, blank=True, help_text='Extra data (task IDs, user IDs, etc.)')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'project_manager_agent'
        ordering = ['-created_at']
        verbose_name = 'PM Notification'
        verbose_name_plural = 'PM Notifications'
        indexes = [models.Index(fields=['company_user', 'is_read', '-created_at'])]

    def __str__(self):
        return f"[{self.severity}] {self.title}"


class PMAuditLog(models.Model):
    """Audit trail for tracking all actions in the PM agent system."""
    ACTION_CHOICES = [
        ('project_created', 'Project Created'),
        ('project_updated', 'Project Updated'),
        ('project_deleted', 'Project Deleted'),
        ('task_created', 'Task Created'),
        ('task_updated', 'Task Updated'),
        ('task_deleted', 'Task Deleted'),
        ('task_assigned', 'Task Assigned'),
        ('meeting_scheduled', 'Meeting Scheduled'),
        ('meeting_accepted', 'Meeting Accepted'),
        ('meeting_rejected', 'Meeting Rejected'),
        ('meeting_withdrawn', 'Meeting Withdrawn'),
        ('meeting_rescheduled', 'Meeting Rescheduled'),
        ('subtasks_generated', 'Subtasks Generated'),
        ('priority_updated', 'Priority Updated'),
    ]

    company_user = models.ForeignKey(
        'core.CompanyUser', on_delete=models.CASCADE, related_name='pm_audit_logs',
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=50, help_text='e.g., Project, Task, ScheduledMeeting')
    object_id = models.IntegerField(null=True, blank=True)
    object_title = models.CharField(max_length=255, blank=True, default='')
    details = models.JSONField(null=True, blank=True, help_text='Additional context')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'project_manager_agent'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['company_user', '-created_at'])]

    def __str__(self):
        return f"[{self.action}] {self.object_title} by {self.company_user_id}"


class ScheduledMeeting(models.Model):
    """
    Meeting scheduling between a CompanyUser (organizer) and one or more project Users (participants).
    The organizer is the logged-in company user. Participants are project team members
    (Django Users) that belong to the organizer's company.
    Overall status is derived from participant statuses.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('partially_accepted', 'Partially Accepted'),
        ('rejected', 'Rejected'),
        ('counter_proposed', 'Counter Proposed'),
        ('withdrawn', 'Withdrawn'),
    ]
    RECURRENCE_CHOICES = [
        ('none', 'None'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('weekly_weekdays', 'Weekdays (Mon-Fri)'),
        ('biweekly', 'Every 2 Weeks'),
        ('monthly', 'Monthly'),
    ]

    organizer = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='organized_scheduled_meetings',
        help_text='Company user who scheduled the meeting',
    )
    # Keep invitee for backward compat with existing single-invitee meetings
    invitee = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='invited_scheduled_meetings',
        help_text='Primary invitee (legacy). Use participants for multi-user meetings.',
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    agenda = models.JSONField(null=True, blank=True, help_text='Structured agenda items: [{"item": "...", "done": false}]')
    proposed_time = models.DateTimeField(help_text='Currently proposed meeting time')
    duration_minutes = models.IntegerField(default=30)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    # Recurrence fields
    recurrence = models.CharField(max_length=20, choices=RECURRENCE_CHOICES, default='none')
    recurrence_end_date = models.DateField(null=True, blank=True, help_text='Stop recurring after this date')
    parent_meeting = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='occurrences',
        help_text='Parent meeting for recurring series. Null = standalone or parent itself.',
    )
    actual_duration_minutes = models.IntegerField(null=True, blank=True, help_text='Actual meeting duration (filled after meeting ends)')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'project_manager_agent'
        ordering = ['-created_at']
        verbose_name = 'Scheduled Meeting'
        verbose_name_plural = 'Scheduled Meetings'
        indexes = [
            models.Index(fields=['organizer', '-created_at']),
            models.Index(fields=['status', 'proposed_time']),
        ]

    def __str__(self):
        participant_count = self.participants.count()
        if participant_count == 1:
            p = self.participants.first()
            name = p.user.get_full_name() or p.user.username if p else 'Unknown'
        elif participant_count > 1:
            name = f"{participant_count} participants"
        elif self.invitee:
            name = self.invitee.get_full_name() or self.invitee.username
        else:
            name = 'No participants'
        return f"{self.title} ({self.organizer.full_name} → {name}) [{self.status}]"

    def update_overall_status(self):
        """Recalculate meeting status based on all participant statuses."""
        participants = self.participants.all()
        if not participants.exists():
            return
        statuses = list(participants.values_list('status', flat=True))
        if all(s == 'accepted' for s in statuses):
            self.status = 'accepted'
        elif any(s == 'counter_proposed' for s in statuses):
            self.status = 'counter_proposed'
        elif all(s == 'rejected' for s in statuses):
            self.status = 'rejected'
        elif any(s == 'accepted' for s in statuses) and any(s == 'pending' for s in statuses):
            self.status = 'partially_accepted'
        else:
            self.status = 'pending'
        self.save(update_fields=['status', 'updated_at'])


class MeetingParticipant(models.Model):
    """Individual participant in a meeting with their own accept/reject status."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('counter_proposed', 'Counter Proposed'),
    ]

    meeting = models.ForeignKey(
        ScheduledMeeting,
        on_delete=models.CASCADE,
        related_name='participants',
    )
    user = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='meeting_participations',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reason = models.TextField(blank=True, default='', help_text='Reason for rejection or counter-proposal')
    counter_proposed_time = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'project_manager_agent'
        unique_together = ['meeting', 'user']
        ordering = ['created_at']

    def __str__(self):
        name = self.user.get_full_name() or self.user.username
        return f"{name} → {self.status} ({self.meeting.title})"


class MeetingResponse(models.Model):
    """
    Each response in the meeting negotiation chain.
    responded_by indicates who responded: 'organizer' (CompanyUser) or 'invitee' (project User).
    """
    ACTION_CHOICES = [
        ('proposed', 'Proposed'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('counter_proposed', 'Counter Proposed'),
        ('withdrawn', 'Withdrawn'),
    ]
    RESPONDED_BY_CHOICES = [
        ('organizer', 'Organizer'),
        ('invitee', 'Invitee'),
    ]

    meeting = models.ForeignKey(
        ScheduledMeeting,
        on_delete=models.CASCADE,
        related_name='responses',
    )
    responded_by = models.CharField(
        max_length=20,
        choices=RESPONDED_BY_CHOICES,
        default='organizer',
        help_text='Who responded: organizer (CompanyUser) or invitee (project User)',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    proposed_time = models.DateTimeField(
        null=True, blank=True,
        help_text='New proposed time (for counter-proposals)',
    )
    reason = models.TextField(blank=True, default='', help_text='Reason for rejection or counter-proposal')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'project_manager_agent'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.responded_by} → {self.action} ({self.meeting.title})"

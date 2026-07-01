from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Executive Meeting
# ---------------------------------------------------------------------------

class ExecutiveMeeting(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('pending_confirmation', 'Pending Confirmation'),
    ]
    RECURRENCE_CHOICES = [
        ('none', 'None'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('biweekly', 'Bi-Weekly'),
        ('monthly', 'Monthly'),
    ]

    organizer = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='exec_organized_meetings',
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    agenda = models.JSONField(default=list, blank=True, help_text='List of agenda items')
    location = models.CharField(max_length=255, blank=True, default='')
    meeting_link = models.URLField(blank=True, default='')

    scheduled_at = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=60)
    timezone_name = models.CharField(max_length=64, default='UTC')

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='scheduled', db_index=True)

    recurrence = models.CharField(max_length=20, choices=RECURRENCE_CHOICES, default='none')
    recurrence_end_date = models.DateField(null=True, blank=True)
    parent_meeting = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='occurrences',
    )

    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'meeting_agent'
        ordering = ['-scheduled_at']
        indexes = [
            models.Index(fields=['organizer', '-scheduled_at']),
            models.Index(fields=['status', 'scheduled_at']),
        ]

    def __str__(self):
        return f"{self.title} — {self.scheduled_at:%Y-%m-%d %H:%M}"


class ExecutiveMeetingParticipant(models.Model):
    RESPONSE_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('counter_proposed', 'Counter Proposed'),
        ('tentative', 'Tentative'),
    ]

    meeting = models.ForeignKey(
        ExecutiveMeeting,
        on_delete=models.CASCADE,
        related_name='participants',
    )
    company_user = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='exec_meeting_participations',
    )
    response = models.CharField(max_length=20, choices=RESPONSE_CHOICES, default='pending', db_index=True)
    counter_proposed_time = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(blank=True, default='')
    responded_at = models.DateTimeField(null=True, blank=True)
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = 'meeting_agent'
        unique_together = [('meeting', 'company_user')]

    def __str__(self):
        return f"{self.company_user} — {self.meeting.title} ({self.response})"


# ---------------------------------------------------------------------------
# Meeting Notes & Action Items
# ---------------------------------------------------------------------------

class MeetingNote(models.Model):
    meeting = models.OneToOneField(
        ExecutiveMeeting,
        on_delete=models.CASCADE,
        related_name='note',
    )
    raw_transcript = models.TextField(blank=True, default='', help_text='Raw transcript submitted by user')
    ai_summary = models.TextField(blank=True, default='', help_text='AI-generated meeting summary')
    key_decisions = models.JSONField(default=list, blank=True, help_text='List of key decisions made')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'meeting_agent'

    def __str__(self):
        return f"Notes: {self.meeting.title}"


class MeetingActionItem(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    meeting = models.ForeignKey(
        ExecutiveMeeting,
        on_delete=models.CASCADE,
        related_name='action_items',
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    assignee = models.ForeignKey(
        'core.CompanyUser',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='exec_action_items',
    )
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open', db_index=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    ai_extracted = models.BooleanField(default=False, help_text='True if extracted by AI from transcript')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'meeting_agent'
        ordering = ['-priority', 'due_date']

    def __str__(self):
        return f"{self.title} ({self.status})"


# ---------------------------------------------------------------------------
# Executive Tasks
# ---------------------------------------------------------------------------

class ExecutiveTask(models.Model):
    STATUS_CHOICES = [
        ('todo', 'To Do'),
        ('in_progress', 'In Progress'),
        ('review', 'Review'),
        ('done', 'Done'),
        ('blocked', 'Blocked'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    company_user = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='exec_tasks',
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='todo', db_index=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium', db_index=True)
    due_date = models.DateField(null=True, blank=True)
    estimated_hours = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    ai_reasoning = models.TextField(blank=True, default='', help_text='AI explanation for priority assignment')
    assignees = models.ManyToManyField(
        'core.CompanyUser',
        blank=True,
        related_name='exec_assigned_tasks',
    )
    linked_meeting = models.ForeignKey(
        ExecutiveMeeting,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='linked_tasks',
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'meeting_agent'
        ordering = ['-priority', 'due_date']
        indexes = [
            models.Index(fields=['company_user', 'status']),
            models.Index(fields=['company_user', '-priority']),
        ]

    def __str__(self):
        return f"{self.title} [{self.priority}] ({self.status})"


# ---------------------------------------------------------------------------
# Meeting Documents
# ---------------------------------------------------------------------------

class MeetingDocument(models.Model):
    DOC_TYPE_CHOICES = [
        ('agenda', 'Agenda'),
        ('minutes', 'Minutes'),
        ('briefing', 'Briefing'),
        ('report', 'Report'),
        ('other', 'Other'),
    ]

    meeting = models.ForeignKey(
        ExecutiveMeeting,
        on_delete=models.CASCADE,
        related_name='documents',
    )
    created_by = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='exec_meeting_documents',
    )
    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES, default='other')
    title = models.CharField(max_length=255)
    content = models.TextField(help_text='Document body (markdown)')
    ai_generated = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'meeting_agent'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_doc_type_display()}: {self.title}"


# ---------------------------------------------------------------------------
# Standalone AI Documents (not tied to a specific meeting)
# ---------------------------------------------------------------------------

class ExecStandaloneDocument(models.Model):
    DOC_TYPE_CHOICES = [
        ('agenda', 'Agenda'),
        ('minutes', 'Minutes'),
        ('briefing', 'Briefing'),
        ('report', 'Report'),
        ('other', 'Other'),
    ]

    company_user = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='exec_standalone_documents',
    )
    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES, default='other')
    title = models.CharField(max_length=255)
    content = models.TextField(help_text='Document body (markdown)')
    ai_generated = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'meeting_agent'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_doc_type_display()}: {self.title}"


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

class ExecNotification(models.Model):
    TYPE_CHOICES = [
        ('meeting_reminder', 'Meeting Reminder'),
        ('meeting_invite', 'Meeting Invite'),
        ('meeting_update', 'Meeting Update'),
        ('meeting_cancelled', 'Meeting Cancelled'),
        ('action_item_due', 'Action Item Due'),
        ('action_item_overdue', 'Action Item Overdue'),
        ('task_due', 'Task Due'),
        ('task_overdue', 'Task Overdue'),
        ('calendar_conflict', 'Calendar Conflict'),
        ('participant_response', 'Participant Response'),
        ('document_ready', 'Document Ready'),
    ]
    SEVERITY_CHOICES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]

    company_user = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='exec_notifications',
    )
    notification_type = models.CharField(max_length=40, choices=TYPE_CHOICES, db_index=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='info')
    title = models.CharField(max_length=255)
    message = models.TextField()
    data = models.JSONField(default=dict, blank=True, help_text='Extra context — meeting_id, task_id, etc.')
    is_read = models.BooleanField(default=False, db_index=True)
    meeting = models.ForeignKey(
        ExecutiveMeeting,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='notifications',
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'meeting_agent'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company_user', 'is_read', '-created_at']),
        ]

    def __str__(self):
        return f"[{self.severity}] {self.title}"


class ExecNotificationChannel(models.Model):
    CHANNEL_CHOICES = [
        ('email', 'Email'),
        ('slack', 'Slack'),
        ('teams', 'Microsoft Teams'),
    ]

    company_user = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='exec_notification_channels',
    )
    channel_type = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    target = models.CharField(max_length=512, help_text='Email address or webhook URL')
    is_active = models.BooleanField(default=True)
    severities = models.CharField(
        max_length=50, blank=True, default='',
        help_text='Comma-separated severities to send. Empty = all.',
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'meeting_agent'
        unique_together = [('company_user', 'channel_type', 'target')]

    def __str__(self):
        return f"{self.company_user} — {self.channel_type}: {self.target}"


# ---------------------------------------------------------------------------
# Chat models — one pair per sub-agent
# ---------------------------------------------------------------------------

class ExecMeetingSchedulingChat(models.Model):
    company_user = models.ForeignKey(
        'core.CompanyUser', on_delete=models.CASCADE,
        related_name='exec_scheduling_chats',
    )
    title = models.CharField(max_length=255, default='Chat')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'meeting_agent'
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['company_user', '-updated_at'])]

    def __str__(self):
        return f"Scheduling Chat: {self.title[:40]} ({self.id})"


class ExecMeetingSchedulingChatMessage(models.Model):
    ROLE_CHOICES = [('user', 'User'), ('assistant', 'Assistant')]
    chat = models.ForeignKey(ExecMeetingSchedulingChat, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    response_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'meeting_agent'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class ExecNotetakerChat(models.Model):
    company_user = models.ForeignKey(
        'core.CompanyUser', on_delete=models.CASCADE,
        related_name='exec_notetaker_chats',
    )
    title = models.CharField(max_length=255, default='Chat')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'meeting_agent'
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['company_user', '-updated_at'])]

    def __str__(self):
        return f"Notetaker Chat: {self.title[:40]} ({self.id})"


class ExecNotetakerChatMessage(models.Model):
    ROLE_CHOICES = [('user', 'User'), ('assistant', 'Assistant')]
    chat = models.ForeignKey(ExecNotetakerChat, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    response_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'meeting_agent'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class ExecTaskChat(models.Model):
    company_user = models.ForeignKey(
        'core.CompanyUser', on_delete=models.CASCADE,
        related_name='exec_task_chats',
    )
    title = models.CharField(max_length=255, default='Chat')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'meeting_agent'
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['company_user', '-updated_at'])]

    def __str__(self):
        return f"Task Chat: {self.title[:40]} ({self.id})"


class ExecTaskChatMessage(models.Model):
    ROLE_CHOICES = [('user', 'User'), ('assistant', 'Assistant')]
    chat = models.ForeignKey(ExecTaskChat, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    response_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'meeting_agent'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class ExecCalendarChat(models.Model):
    company_user = models.ForeignKey(
        'core.CompanyUser', on_delete=models.CASCADE,
        related_name='exec_calendar_chats',
    )
    title = models.CharField(max_length=255, default='Chat')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'meeting_agent'
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['company_user', '-updated_at'])]

    def __str__(self):
        return f"Calendar Chat: {self.title[:40]} ({self.id})"


class ExecCalendarChatMessage(models.Model):
    ROLE_CHOICES = [('user', 'User'), ('assistant', 'Assistant')]
    chat = models.ForeignKey(ExecCalendarChat, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    response_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'meeting_agent'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class ExecDocumentChat(models.Model):
    company_user = models.ForeignKey(
        'core.CompanyUser', on_delete=models.CASCADE,
        related_name='exec_document_chats',
    )
    title = models.CharField(max_length=255, default='Chat')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'meeting_agent'
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['company_user', '-updated_at'])]

    def __str__(self):
        return f"Document Chat: {self.title[:40]} ({self.id})"


class ExecDocumentChatMessage(models.Model):
    ROLE_CHOICES = [('user', 'User'), ('assistant', 'Assistant')]
    chat = models.ForeignKey(ExecDocumentChat, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    response_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'meeting_agent'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class ExecNotificationChat(models.Model):
    company_user = models.ForeignKey(
        'core.CompanyUser', on_delete=models.CASCADE,
        related_name='exec_notification_chats',
    )
    title = models.CharField(max_length=255, default='Chat')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'meeting_agent'
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['company_user', '-updated_at'])]

    def __str__(self):
        return f"Notification Chat: {self.title[:40]} ({self.id})"


class ExecNotificationChatMessage(models.Model):
    ROLE_CHOICES = [('user', 'User'), ('assistant', 'Assistant')]
    chat = models.ForeignKey(ExecNotificationChat, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    response_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'meeting_agent'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"

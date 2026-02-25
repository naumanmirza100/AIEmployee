from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Ticket(models.Model):
    """Support ticket model for ticket triage and auto-resolution"""
    STATUS_CHOICES = [
        ('new', 'New'),
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
        ('auto_resolved', 'Auto Resolved'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    CATEGORY_CHOICES = [
        ('technical', 'Technical'),
        ('billing', 'Billing'),
        ('account', 'Account'),
        ('feature_request', 'Feature Request'),
        ('bug', 'Bug'),
        ('knowledge_gap', 'Knowledge gap (add to KB)'),
        ('other', 'Other'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, null=True, blank=True, related_name='frontline_tickets')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_tickets')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tickets')
    resolution = models.TextField(blank=True, null=True)
    auto_resolved = models.BooleanField(default=False)
    resolution_confidence = models.FloatField(null=True, blank=True, help_text="AI confidence score for auto-resolution")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.get_status_display()}"


class KnowledgeBase(models.Model):
    """Knowledge base articles for Q&A agent"""
    CATEGORY_CHOICES = [
        ('faq', 'FAQ'),
        ('documentation', 'Documentation'),
        ('troubleshooting', 'Troubleshooting'),
        ('policies', 'Policies'),
        ('procedures', 'Procedures'),
        ('other', 'Other'),
    ]
    
    title = models.CharField(max_length=200)
    content = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    tags = models.CharField(max_length=500, blank=True, help_text="Comma-separated tags")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='knowledge_articles')
    views_count = models.IntegerField(default=0)
    helpful_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['category']),
            models.Index(fields=['title']),
        ]
    
    def __str__(self):
        return self.title
    
    def get_tags_list(self):
        """Return tags as a list"""
        return [tag.strip() for tag in self.tags.split(',') if tag.strip()]


class Notification(models.Model):
    """Proactive notifications and follow-ups"""
    TYPE_CHOICES = [
        ('ticket_update', 'Ticket Update'),
        ('ticket_assigned', 'Ticket Assigned'),
        ('follow_up', 'Follow-up'),
        ('reminder', 'Reminder'),
        ('alert', 'Alert'),
        ('system', 'System'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='frontline_notifications')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='system')
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    related_ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications')
    action_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.user.username}"


class NotificationTemplate(models.Model):
    """Reusable templates for proactive notifications (email/SMS/in-app)."""
    CHANNEL_CHOICES = [
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('in_app', 'In-App'),
    ]
    TYPE_CHOICES = [
        ('ticket_update', 'Ticket Update'),
        ('ticket_assigned', 'Ticket Assigned'),
        ('follow_up', 'Follow-up'),
        ('reminder', 'Reminder'),
        ('alert', 'Alert'),
        ('system', 'System'),
    ]
    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='frontline_notification_templates', null=True, blank=True)
    name = models.CharField(max_length=200)
    subject = models.CharField(max_length=300, blank=True, help_text='Email subject')
    body = models.TextField(help_text='Body text. Use {{ticket_id}}, {{ticket_title}}, {{customer_name}}, {{resolution}} for placeholders.')
    notification_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default='ticket_update')
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='email')
    trigger_config = models.JSONField(default=dict, blank=True, help_text='Optional: {"on": "ticket_created"|"ticket_updated", "delay_minutes": 0}. When set, notifications are auto-created on that event.')
    use_llm_personalization = models.BooleanField(default=False, help_text='When enabled, the email body is generated by LLM from context (ticket, customer) for a personalized message; fallback to template body on failure.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.name} ({self.channel})"


class ScheduledNotification(models.Model):
    """Scheduled or sent notifications (history + pending)."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='frontline_scheduled_notifications', null=True, blank=True)
    template = models.ForeignKey(NotificationTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name='scheduled_notifications')
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    recipient_email = models.EmailField(blank=True)
    recipient_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='frontline_scheduled_notifications_received')
    related_ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, null=True, blank=True, related_name='scheduled_notifications')
    context = models.JSONField(default=dict, blank=True, help_text='Placeholder values for template')
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-scheduled_at']
        indexes = [
            models.Index(fields=['status', 'scheduled_at']),
            models.Index(fields=['company']),
        ]

    def __str__(self):
        return f"ScheduledNotification {self.id} ({self.status}) @ {self.scheduled_at}"


class FrontlineWorkflow(models.Model):
    """Workflow/SOP definition for Frontline Agent."""
    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='frontline_workflows', null=True, blank=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    trigger_conditions = models.JSONField(default=dict, blank=True, help_text='e.g. {"on": "ticket_created", "category": "billing"}')
    steps = models.JSONField(default=list, help_text='List of steps: [{"type": "send_email", "template_id": 1}, {"type": "update_ticket", "status": "open"}]')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-updated_at']

    def __str__(self):
        return self.name


class FrontlineWorkflowExecution(models.Model):
    """Workflow/SOP execution tracking for Frontline Agent"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    workflow = models.ForeignKey(FrontlineWorkflow, on_delete=models.SET_NULL, null=True, blank=True, related_name='executions')
    workflow_name = models.CharField(max_length=200)
    workflow_description = models.TextField(blank=True)
    executed_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='frontline_workflow_executions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    context_data = models.JSONField(default=dict, blank=True)
    result_data = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['status', 'started_at']),
            models.Index(fields=['executed_by']),
        ]

    def __str__(self):
        return f"{self.workflow_name} - {self.executed_by.username} ({self.status})"


class FrontlineMeeting(models.Model):
    """Meeting scheduling for Frontline Agent"""
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('rescheduled', 'Rescheduled'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    organizer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='frontline_organized_meetings')
    participants = models.ManyToManyField(User, related_name='frontline_meetings', blank=True)
    scheduled_at = models.DateTimeField()
    duration_minutes = models.IntegerField(default=60)
    meeting_link = models.URLField(blank=True, null=True)
    location = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    notes = models.TextField(blank=True)
    transcript = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-scheduled_at']
        indexes = [
            models.Index(fields=['status', 'scheduled_at']),
            models.Index(fields=['organizer']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.scheduled_at}"


class Document(models.Model):
    """Document processing for Frontline Agent"""
    DOCUMENT_TYPE_CHOICES = [
        ('ticket_attachment', 'Ticket Attachment'),
        ('knowledge_base', 'Knowledge Base'),
        ('policy', 'Policy'),
        ('procedure', 'Procedure'),
        ('report', 'Report'),
        ('other', 'Other'),
    ]
    
    FILE_FORMAT_CHOICES = [
        ('pdf', 'PDF'),
        ('docx', 'DOCX'),
        ('doc', 'DOC'),
        ('txt', 'TXT'),
        ('md', 'Markdown'),
        ('html', 'HTML'),
        ('other', 'Other'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPE_CHOICES, default='knowledge_base')
    file_path = models.CharField(max_length=1000, help_text="Path to stored document file")
    file_size = models.IntegerField(null=True, blank=True, help_text="File size in bytes")
    mime_type = models.CharField(max_length=100, blank=True)
    file_format = models.CharField(max_length=10, choices=FILE_FORMAT_CHOICES, default='other', help_text="File format/extension")
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='frontline_documents')
    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, null=True, blank=True, related_name='frontline_documents', help_text="Company that owns this document")
    document_content = models.TextField(blank=True, help_text="Extracted text content from document")
    is_indexed = models.BooleanField(default=False, help_text="Whether document content is indexed for search")
    file_hash = models.CharField(max_length=64, blank=True, help_text="SHA256 hash for duplicate detection")
    processed = models.BooleanField(default=False)
    processed_data = models.JSONField(default=dict, blank=True, help_text="Extracted/processed content from document")
    embedding = models.TextField(null=True, blank=True, help_text="Vector embedding for semantic search (stored as JSON string to support large embeddings)")
    embedding_model = models.CharField(max_length=100, blank=True, null=True, help_text="Model used to generate embedding (e.g., text-embedding-3-large)")
    related_ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    related_knowledge = models.ForeignKey(KnowledgeBase, on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['document_type', 'processed']),
            models.Index(fields=['created_at']),
            models.Index(fields=['company', 'is_indexed']),
            models.Index(fields=['file_hash']),
        ]
    
    def __str__(self):
        return self.title


class FrontlineAnalytics(models.Model):
    """Analytics and dashboard data for Frontline Agent"""
    metric_name = models.CharField(max_length=100)
    metric_value = models.FloatField()
    metric_data = models.JSONField(default=dict, blank=True)
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)
    calculated_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-calculated_at']
        indexes = [
            models.Index(fields=['metric_name', 'calculated_at']),
        ]
    
    def __str__(self):
        return f"{self.metric_name} - {self.metric_value}"


class FrontlineQAChat(models.Model):
    """Knowledge Q&A chat sessions for frontline. Each chat contains multiple messages."""
    company_user = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='frontline_qa_chats',
        help_text='Company user who owns this chat',
    )
    title = models.CharField(max_length=255, default='Chat', help_text='Chat title (e.g. first question snippet)')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-updated_at']
        verbose_name = 'Frontline QA Chat'
        verbose_name_plural = 'Frontline QA Chats'

    def __str__(self):
        return f"QA Chat: {self.title[:40]}... ({self.id})"


class FrontlineQAChatMessage(models.Model):
    """Individual messages in a Frontline QA chat."""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]
    chat = models.ForeignKey(
        FrontlineQAChat,
        on_delete=models.CASCADE,
        related_name='messages',
        help_text='Chat this message belongs to',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField(help_text='Message content')
    response_data = models.JSONField(
        null=True,
        blank=True,
        help_text='For assistant: full API response { answer, has_verified_info, source, type }',
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['created_at']
        verbose_name = 'Frontline QA Chat Message'
        verbose_name_plural = 'Frontline QA Chat Messages'

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."


class SavedGraphPrompt(models.Model):
    """Saved AI graph prompts for Frontline analytics. Users can save, favorite, and reuse prompts."""
    CHART_TYPE_CHOICES = [
        ('bar', 'Bar Chart'),
        ('pie', 'Pie Chart'),
        ('line', 'Line Chart'),
        ('area', 'Area Chart'),
    ]
    company_user = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='frontline_saved_graph_prompts',
    )
    title = models.CharField(max_length=255)
    prompt = models.TextField()
    chart_type = models.CharField(max_length=20, choices=CHART_TYPE_CHOICES, default='bar')
    tags = models.JSONField(default=list, blank=True)
    is_favorite = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-is_favorite', '-updated_at']
        verbose_name = 'Saved Graph Prompt'
        verbose_name_plural = 'Saved Graph Prompts'

    def __str__(self):
        return f"{self.title} ({self.chart_type})"


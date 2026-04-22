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
    sla_due_at = models.DateTimeField(null=True, blank=True, help_text='Target response time for SLA; used for aging alerts')

    # Snooze: when set in the future, the ticket is dormant; Celery wakes it when the time passes.
    snoozed_until = models.DateTimeField(null=True, blank=True, db_index=True,
                                         help_text='If set and in the future, ticket is snoozed and hidden from queues.')

    # SLA pause: sla_paused_at is the moment we stopped the clock (e.g. waiting on customer).
    # sla_paused_accumulated_seconds tracks total paused time across multiple pause/resume cycles.
    sla_paused_at = models.DateTimeField(null=True, blank=True,
                                         help_text='If set, the SLA clock is currently paused since this time.')
    sla_paused_accumulated_seconds = models.IntegerField(default=0,
                                                         help_text='Total accumulated paused seconds across all pause/resume cycles.')

    # Triage bookkeeping: track when the ticket was last re-triaged.
    last_triaged_at = models.DateTimeField(null=True, blank=True,
                                           help_text='When triage was last run (create or re-triage on update).')

    # Internal entities for analytics/workflow
    intent = models.CharField(max_length=100, blank=True, null=True, help_text='Extracted intention of the user')
    entities = models.JSONField(default=dict, blank=True, help_text='Extracted entities like user_id, product, etc.')

    # The customer this ticket is about (first-class Contact record, scoped to company).
    # Nullable so older tickets and internally-raised tickets stay valid.
    contact = models.ForeignKey('Frontline_agent.Contact', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='tickets',
                                help_text='First-class customer record for this ticket.')

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['created_at']),
            models.Index(fields=['sla_due_at']),
            models.Index(fields=['snoozed_until']),
            models.Index(fields=['contact', 'created_at']),
        ]

    def __str__(self):
        return f"{self.title} - {self.get_status_display()}"

    def is_snoozed(self):
        """True if the ticket is currently within its snooze window."""
        return bool(self.snoozed_until and self.snoozed_until > timezone.now())


class TicketNote(models.Model):
    """Internal / private note on a ticket. Agents use these to discuss with
    each other without the customer seeing. `is_internal=False` is reserved
    for a future customer-visible comment type."""
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='frontline_ticket_notes')
    body = models.TextField()
    is_internal = models.BooleanField(default=True, help_text='True = private agent note. Reserved False for future customer-visible comments.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['ticket', 'created_at']),
        ]

    def __str__(self):
        return f"Note on ticket #{self.ticket_id} by {self.author_id}"


class TicketMessage(models.Model):
    """A single message on a ticket thread — inbound from customer or outbound
    from agent. Stores the raw email metadata for threading (RFC 5322
    Message-ID / In-Reply-To / References) and both text + sanitized HTML
    bodies. `direction` indicates who sent it; `channel` lets future channels
    (widget chat, SMS, WhatsApp) slot into the same thread."""

    DIRECTION_CHOICES = [
        ('inbound', 'Inbound (from customer)'),
        ('outbound', 'Outbound (from agent / system)'),
    ]
    CHANNEL_CHOICES = [
        ('email', 'Email'),
        ('widget', 'Web widget'),
        ('api', 'API'),
        ('sms', 'SMS'),
        ('whatsapp', 'WhatsApp'),
        ('manual', 'Manual entry'),
    ]

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='messages')
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='email')

    from_address = models.CharField(max_length=320, blank=True, help_text='Email address / handle of sender.')
    from_name = models.CharField(max_length=255, blank=True)
    to_addresses = models.JSONField(default=list, blank=True, help_text='List of recipient addresses.')
    cc_addresses = models.JSONField(default=list, blank=True)

    subject = models.CharField(max_length=998, blank=True)
    body_text = models.TextField(blank=True, help_text='Plain-text body (reply-stripped when possible).')
    body_html = models.TextField(blank=True, help_text='Sanitized HTML body (bleach-stripped).')

    message_id = models.CharField(max_length=998, blank=True, db_index=True,
                                  help_text='RFC 5322 Message-ID header. Used for reply threading.')
    in_reply_to = models.CharField(max_length=998, blank=True, db_index=True,
                                   help_text='In-Reply-To header from the incoming email.')
    references = models.JSONField(default=list, blank=True,
                                  help_text='Ordered list of Message-IDs from the References header.')

    raw_payload = models.JSONField(default=dict, blank=True,
                                   help_text='Provider-normalized payload for debugging / re-processing.')

    author_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='frontline_ticket_messages_sent',
                                    help_text='Django user that sent this message (outbound).')
    author_company_user = models.ForeignKey('core.CompanyUser', on_delete=models.SET_NULL, null=True, blank=True,
                                            related_name='frontline_ticket_messages_sent',
                                            help_text='Company user that sent this message (outbound).')

    is_auto_reply = models.BooleanField(default=False,
                                        help_text='True if this was generated by an auto-response (e.g. bounce, vacation).')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['ticket', 'created_at']),
            models.Index(fields=['direction', 'channel']),
            models.Index(fields=['message_id']),
            models.Index(fields=['in_reply_to']),
        ]

    def __str__(self):
        return f"{self.direction} msg on ticket #{self.ticket_id} ({self.channel})"


class TicketAttachment(models.Model):
    """File attachment on a ticket message. Stored on local disk under
    media/frontline_ticket_attachments/<company>/<ticket>/<hash>.<ext>."""

    ticket_message = models.ForeignKey(TicketMessage, on_delete=models.CASCADE,
                                       related_name='attachments')
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.IntegerField(default=0)
    storage_path = models.CharField(max_length=1000, help_text='Path on disk under MEDIA_ROOT.')
    sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['ticket_message', 'created_at']),
        ]

    def __str__(self):
        return f"Attachment {self.filename} ({self.size_bytes}B) on msg #{self.ticket_message_id}"


class Contact(models.Model):
    """First-class customer record per tenant. One row per unique customer
    email within a company. Email is case-insensitive: always store lower.

    `total_tickets_count`, `first_seen_at`, `last_seen_at` are denormalized
    so Customer-360 panels render in one query instead of a subquery per row.
    `external_id` / `external_source` are reserved for future CRM sync
    (HubSpot / Salesforce) — non-null → the row is mirrored externally.
    """
    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='contacts')
    email = models.EmailField(help_text='Stored lowercased. Unique within a company.')
    name = models.CharField(max_length=255, blank=True, default='')
    phone = models.CharField(max_length=40, blank=True, default='')

    tags = models.JSONField(default=list, blank=True, help_text='List of free-form tag strings.')
    custom_fields = models.JSONField(default=dict, blank=True,
                                     help_text='Tenant-defined attributes: {key: value}.')

    first_seen_at = models.DateTimeField(null=True, blank=True,
                                         help_text='First time we saw this email (inbound msg or manual create).')
    last_seen_at = models.DateTimeField(null=True, blank=True,
                                        help_text='Most recent inbound message from this email.')
    total_tickets_count = models.IntegerField(default=0,
                                              help_text='Denormalized count of tickets linked to this contact.')

    # External-system mirror (e.g. HubSpot contactId). Null = local only.
    external_id = models.CharField(max_length=128, blank=True, default='', db_index=True)
    external_source = models.CharField(max_length=40, blank=True, default='',
                                       help_text="e.g. 'hubspot', 'salesforce'.")
    external_synced_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-last_seen_at', '-created_at']
        unique_together = [('company', 'email')]
        indexes = [
            models.Index(fields=['company', 'last_seen_at']),
            models.Index(fields=['company', 'email']),
            models.Index(fields=['external_source', 'external_id']),
        ]

    def __str__(self):
        return f"{self.name or self.email} ({self.company_id})"


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
        ('dead_lettered', 'Dead-lettered'),
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

    # Retry + DLQ bookkeeping
    attempts = models.IntegerField(default=0, help_text='Number of send attempts made so far.')
    max_attempts = models.IntegerField(default=3, help_text='Upper bound on retry attempts before dead-lettering.')
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True,
                                         help_text='Earliest time the Celery worker may attempt the next retry.')
    last_error = models.TextField(blank=True, null=True, help_text='Error message from the most recent failed attempt.')
    dead_lettered_at = models.DateTimeField(null=True, blank=True, db_index=True,
                                            help_text='When this notification exhausted retries and was dead-lettered.')
    deferred_reason = models.CharField(max_length=50, blank=True, default='',
                                       help_text="If non-empty, send was deferred (e.g. 'quiet_hours').")

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-scheduled_at']
        indexes = [
            models.Index(fields=['status', 'scheduled_at']),
            models.Index(fields=['company']),
            models.Index(fields=['status', 'next_retry_at']),
            models.Index(fields=['dead_lettered_at']),
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
    requires_approval = models.BooleanField(default=False, help_text='If True, execution halts until approved by admin')
    is_active = models.BooleanField(default=True)
    # Workflow-level budget: if execution exceeds this many seconds, the run is aborted.
    # 0 or null means "no timeout" (existing behaviour).
    timeout_seconds = models.IntegerField(default=0, help_text='Max wall-clock seconds for one run. 0 = unlimited.')
    # Incremented on every edit; paired with FrontlineWorkflowVersion snapshots.
    version = models.IntegerField(default=1, help_text='Incremented when the workflow definition is changed.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-updated_at']

    def __str__(self):
        return self.name


class FrontlineWorkflowVersion(models.Model):
    """Immutable snapshot of a FrontlineWorkflow at a point in time.
    Created whenever the workflow is updated; supports rollback."""
    workflow = models.ForeignKey(FrontlineWorkflow, on_delete=models.CASCADE, related_name='versions')
    version = models.IntegerField(help_text='Matches FrontlineWorkflow.version at the time of snapshot.')
    snapshot = models.JSONField(help_text='Frozen copy of name/description/trigger_conditions/steps/requires_approval/is_active/timeout_seconds.')
    saved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='frontline_workflow_versions_saved')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-version']
        indexes = [models.Index(fields=['workflow', 'version'])]
        unique_together = [('workflow', 'version')]

    def __str__(self):
        return f"{self.workflow_id} v{self.version}"


class FrontlineWorkflowExecution(models.Model):
    """Workflow/SOP execution tracking for Frontline Agent"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('awaiting_approval', 'Awaiting Approval'),
        ('rejected', 'Rejected'),
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
    company = models.ForeignKey('core.Company', on_delete=models.CASCADE,
                                null=True, blank=True,
                                related_name='frontline_meetings',
                                help_text='Tenant that owns this meeting.')
    organizer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='frontline_organized_meetings')
    participants = models.ManyToManyField(User, related_name='frontline_meetings', blank=True)
    scheduled_at = models.DateTimeField()
    duration_minutes = models.IntegerField(default=60)
    timezone_name = models.CharField(max_length=64, default='UTC',
                                     help_text='IANA tz name for display; scheduled_at is always UTC in DB.')
    meeting_link = models.URLField(blank=True, null=True)
    location = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    notes = models.TextField(blank=True)
    transcript = models.TextField(blank=True)

    # Reminder bookkeeping — populated by the Celery task so we send each reminder once.
    reminder_24h_sent_at = models.DateTimeField(null=True, blank=True)
    reminder_15m_sent_at = models.DateTimeField(null=True, blank=True)

    # LLM-extracted action items. Each entry: {text, owner_user_id?, due_date?, ticket_id?}.
    action_items = models.JSONField(default=list, blank=True,
                                    help_text='Action items extracted from transcript.')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-scheduled_at']
        indexes = [
            models.Index(fields=['status', 'scheduled_at']),
            models.Index(fields=['organizer']),
            models.Index(fields=['company', 'scheduled_at']),
            models.Index(fields=['scheduled_at', 'reminder_24h_sent_at']),
            models.Index(fields=['scheduled_at', 'reminder_15m_sent_at']),
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
    
    PROCESSING_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]

    VISIBILITY_CHOICES = [
        ('company', 'Company (all users in the company)'),
        ('private', 'Private (allowed_users only)'),
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

    # Background-processing state. `processed` stays for back-compat; `processing_status`
    # is the source of truth for the async pipeline.
    processing_status = models.CharField(max_length=20, choices=PROCESSING_STATUS_CHOICES, default='ready',
                                         db_index=True,
                                         help_text="Async processing state. Defaults 'ready' for back-compat.")
    processing_error = models.TextField(blank=True, default='', help_text="Last error from background processing.")
    chunks_processed = models.IntegerField(default=0, help_text="Chunks indexed so far (for progress display).")
    chunks_total = models.IntegerField(default=0, help_text="Total chunks to index (for progress display).")

    # Versioning: uploading a new revision supersedes the old one in retrieval.
    version = models.IntegerField(default=1)
    parent_document = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='revisions',
                                        help_text="Original document if this is a newer revision.")
    superseded_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='superseded_revisions', db_index=True,
                                      help_text="Points to the newer revision. Set → excluded from retrieval.")

    # Per-doc access control.
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='company')
    allowed_users = models.ManyToManyField('core.CompanyUser', blank=True, related_name='frontline_accessible_documents',
                                           help_text="When visibility='private', only these users can retrieve the doc.")

    # Retention (days). 0 or null = keep forever. Prune job deletes expired docs.
    retention_days = models.IntegerField(null=True, blank=True,
                                         help_text="Delete this document after N days from created_at. Blank/0 = keep forever.")

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
            models.Index(fields=['processing_status']),
            models.Index(fields=['superseded_by']),
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


class KBFeedback(models.Model):
    """User feedback on knowledge-base answers (helpful / not helpful) to improve docs and RAG."""
    company_user = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='frontline_kb_feedbacks',
    )
    question = models.TextField(help_text='Question that was answered')
    helpful = models.BooleanField(help_text='True = helpful, False = not helpful')
    document = models.ForeignKey(
        Document,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kb_feedbacks',
        help_text='Document that was used for the answer (if any)',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company_user', 'created_at']),
            models.Index(fields=['document', 'helpful']),
        ]

    def __str__(self):
        return f"KB feedback: {'helpful' if self.helpful else 'not helpful'} ({self.question[:40]}...)"


class FrontlineNotificationPreferences(models.Model):
    """Per-company-user notification preferences. Respect user choice, less spam."""
    company_user = models.OneToOneField(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='frontline_notification_preferences',
    )
    # Master toggles
    email_enabled = models.BooleanField(default=True, help_text='Receive notification emails')
    in_app_enabled = models.BooleanField(default=True, help_text='Show in-app notifications')
    # Per-event email toggles (only apply when email_enabled is True)
    ticket_created_email = models.BooleanField(default=True, help_text='Email when a ticket is created (e.g. trigger or workflow)')
    ticket_updated_email = models.BooleanField(default=True, help_text='Email when a ticket is updated')
    ticket_assigned_email = models.BooleanField(default=True, help_text='Email when a ticket is assigned to you')
    # Workflow / template emails (e.g. send_email step or template trigger)
    workflow_email_enabled = models.BooleanField(default=True, help_text='Receive emails from workflow steps and template triggers')

    # Quiet hours — sends during the window are deferred to the next allowed slot.
    timezone_name = models.CharField(max_length=64, default='UTC',
                                     help_text="IANA timezone name for quiet-hour calculations (e.g. 'America/New_York').")
    quiet_hours_enabled = models.BooleanField(default=False)
    quiet_hours_start = models.CharField(max_length=5, default='22:00', help_text='HH:MM 24h, local to timezone_name.')
    quiet_hours_end = models.CharField(max_length=5, default='08:00', help_text='HH:MM 24h. If end < start the window wraps past midnight.')

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'Frontline_agent'
        verbose_name = 'Frontline notification preferences'
        verbose_name_plural = 'Frontline notification preferences'

    def __str__(self):
        return f"Preferences for {self.company_user.email}"


class DocumentChunk(models.Model):
    """Chunked document content and embedding for intelligent retrieval (RAG)"""
    document = models.ForeignKey(
        Document, 
        on_delete=models.CASCADE, 
        related_name='chunks',
        help_text='Parent document this chunk belongs to'
    )
    chunk_index = models.IntegerField(help_text='Sequential index of this chunk within the document')
    chunk_text = models.TextField(help_text='Text content of this specific chunk')
    embedding = models.TextField(null=True, blank=True, help_text='Vector embedding for this chunk (JSON string)')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['document', 'chunk_index']
        indexes = [
            models.Index(fields=['document', 'chunk_index']),
        ]

    def __str__(self):
        return f"Chunk {self.chunk_index} of {self.document.title}"


class LLMUsage(models.Model):
    """Per-call LLM usage log for cost tracking and per-tenant caps.

    One row per successful or failed LLM call made by any agent that opts in
    (by setting self.company_id on the BaseAgent). estimated_cost_usd is a
    rough approximation from a hardcoded price map — tune as models change.
    """
    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='llm_usage')
    agent_name = models.CharField(max_length=100, db_index=True)
    model = models.CharField(max_length=100, db_index=True)
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    duration_ms = models.IntegerField(default=0)
    success = models.BooleanField(default=True)
    estimated_cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = 'Frontline_agent'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'created_at']),
            models.Index(fields=['company', 'agent_name', 'created_at']),
        ]

    def __str__(self):
        return f"{self.agent_name}/{self.model} · {self.total_tokens}tok · ${self.estimated_cost_usd}"

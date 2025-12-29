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
        ('other', 'Other'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_tickets')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tickets')
    resolution = models.TextField(blank=True, null=True)
    auto_resolved = models.BooleanField(default=False)
    resolution_confidence = models.FloatField(null=True, blank=True, help_text="AI confidence score for auto-resolution")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
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
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.user.username}"


class FrontlineWorkflowExecution(models.Model):
    """Workflow/SOP execution tracking for Frontline Agent"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
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
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPE_CHOICES, default='other')
    file_path = models.CharField(max_length=1000, help_text="Path to stored document file")
    file_size = models.IntegerField(null=True, blank=True, help_text="File size in bytes")
    mime_type = models.CharField(max_length=100, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='frontline_documents')
    processed = models.BooleanField(default=False)
    processed_data = models.JSONField(default=dict, blank=True, help_text="Extracted/processed content from document")
    related_ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    related_knowledge = models.ForeignKey(KnowledgeBase, on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['document_type', 'processed']),
            models.Index(fields=['created_at']),
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
        ordering = ['-calculated_at']
        indexes = [
            models.Index(fields=['metric_name', 'calculated_at']),
        ]
    
    def __str__(self):
        return f"{self.metric_name} - {self.metric_value}"


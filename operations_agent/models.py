from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class OperationsDocument(models.Model):
    """Uploaded documents for operations analysis (PDF, DOCX, Excel, PPT, CSV)"""
    DOCUMENT_TYPE_CHOICES = [
        ('report', 'Report'),
        ('invoice', 'Invoice'),
        ('contract', 'Contract'),
        ('memo', 'Memo'),
        ('spreadsheet', 'Spreadsheet'),
        ('presentation', 'Presentation'),
        ('policy', 'Policy'),
        ('manual', 'Manual'),
        ('other', 'Other'),
    ]

    FILE_TYPE_CHOICES = [
        ('pdf', 'PDF'),
        ('docx', 'Word Document'),
        ('xlsx', 'Excel Spreadsheet'),
        ('csv', 'CSV'),
        ('pptx', 'PowerPoint'),
        ('txt', 'Text File'),
        ('other', 'Other'),
    ]

    company = models.ForeignKey(
        'core.Company', on_delete=models.CASCADE,
        related_name='operations_documents',
    )
    uploaded_by = models.ForeignKey(
        'core.CompanyUser', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='uploaded_operations_documents',
    )
    title = models.CharField(max_length=500)
    original_filename = models.CharField(max_length=500)
    file = models.FileField(upload_to='operations/documents/%Y/%m/', max_length=1000)
    file_type = models.CharField(max_length=20, choices=FILE_TYPE_CHOICES, default='other')
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPE_CHOICES, default='other')
    file_size = models.PositiveIntegerField(default=0)
    page_count = models.PositiveIntegerField(default=0)
    parsed_text = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    entities = models.JSONField(default=dict, blank=True)
    tags = models.CharField(max_length=500, blank=True)
    is_processed = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'operations_agent'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.file_type})"


class OperationsDocumentChunk(models.Model):
    """Chunked text from documents for RAG/embedding-based retrieval"""
    document = models.ForeignKey(
        OperationsDocument, on_delete=models.CASCADE, related_name='chunks',
    )
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    page_number = models.PositiveIntegerField(null=True, blank=True)
    embedding = models.JSONField(null=True, blank=True)
    token_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'operations_agent'
        ordering = ['document', 'chunk_index']
        unique_together = ['document', 'chunk_index']

    def __str__(self):
        return f"Chunk {self.chunk_index} of {self.document.title}"


class OperationsAnalyticsSnapshot(models.Model):
    """Periodic metric snapshots aggregated from documents"""
    company = models.ForeignKey(
        'core.Company', on_delete=models.CASCADE,
        related_name='operations_analytics_snapshots',
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    source = models.CharField(max_length=20, default='document')
    snapshot_type = models.CharField(max_length=20, default='custom')
    data = models.JSONField(default=dict)
    chart_config = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        'core.CompanyUser', on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'operations_agent'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class OperationsChat(models.Model):
    """Chat sessions for the Knowledge Q&A agent"""
    company = models.ForeignKey(
        'core.Company', on_delete=models.CASCADE, related_name='operations_chats',
    )
    user = models.ForeignKey(
        'core.CompanyUser', on_delete=models.CASCADE, related_name='operations_chats',
    )
    title = models.CharField(max_length=255, default='Chat')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'operations_agent'
        ordering = ['-updated_at']

    def __str__(self):
        return f"Ops Chat: {self.title[:40]}..."


class OperationsChatMessage(models.Model):
    """Individual messages in an Operations Q&A chat"""
    ROLE_CHOICES = [('user', 'User'), ('assistant', 'Assistant')]

    chat = models.ForeignKey(OperationsChat, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    response_data = models.JSONField(null=True, blank=True)
    sources = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'operations_agent'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."


class OperationsNotification(models.Model):
    """Proactive alerts from the notification agent"""
    NOTIFICATION_TYPE_CHOICES = [
        ('anomaly_detected', 'Anomaly Detected'),
        ('threshold_breach', 'Threshold Breach'),
        ('report_ready', 'Report Ready'),
        ('document_update', 'Document Update'),
        ('metric_change', 'Metric Change'),
        ('digest_ready', 'Digest Ready'),
    ]
    SEVERITY_CHOICES = [('info', 'Info'), ('warning', 'Warning'), ('critical', 'Critical')]

    company = models.ForeignKey(
        'core.Company', on_delete=models.CASCADE, related_name='operations_notifications',
    )
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='info')
    title = models.CharField(max_length=255)
    message = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'operations_agent'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.severity}] {self.title}"


class OperationsGeneratedDocument(models.Model):
    """AI-authored documents (reports, summaries, memos)"""
    TEMPLATE_TYPE_CHOICES = [
        ('weekly_report', 'Weekly Report'),
        ('monthly_analysis', 'Monthly Analysis'),
        ('executive_summary', 'Executive Summary'),
        ('memo', 'Memo'),
        ('proposal', 'Proposal'),
        ('custom', 'Custom'),
    ]
    TONE_CHOICES = [
        ('formal', 'Formal'), ('concise', 'Concise'),
        ('detailed', 'Detailed'), ('technical', 'Technical'),
    ]

    company = models.ForeignKey(
        'core.Company', on_delete=models.CASCADE,
        related_name='operations_generated_documents',
    )
    generated_by = models.ForeignKey(
        'core.CompanyUser', on_delete=models.SET_NULL, null=True, blank=True,
    )
    title = models.CharField(max_length=500)
    template_type = models.CharField(max_length=30, choices=TEMPLATE_TYPE_CHOICES, default='custom')
    tone = models.CharField(max_length=20, choices=TONE_CHOICES, default='formal')
    prompt = models.TextField()
    content = models.TextField()
    reference_documents = models.ManyToManyField(
        OperationsDocument, blank=True, related_name='referenced_in_generated',
    )
    version = models.PositiveIntegerField(default=1)
    edit_history = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'operations_agent'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} (v{self.version})"

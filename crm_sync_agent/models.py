from django.db import models
from django.utils import timezone


class CRMIntegration(models.Model):
    """Per-company CRM integration configuration."""

    PROVIDER_HUBSPOT = 'hubspot'
    PROVIDER_SALESFORCE = 'salesforce'
    PROVIDER_PIPEDRIVE = 'pipedrive'
    PROVIDERS = [
        (PROVIDER_HUBSPOT, 'HubSpot'),
        (PROVIDER_SALESFORCE, 'Salesforce'),
        (PROVIDER_PIPEDRIVE, 'Pipedrive'),
    ]

    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        related_name='crm_integrations',
    )
    provider = models.CharField(max_length=20, choices=PROVIDERS)

    # Credentials stored as JSON — provider-specific keys documented per connector.
    # HubSpot:    {"access_token": "pat-..."}
    # Salesforce: {"client_id": "...", "client_secret": "...", "username": "...",
    #              "password": "...", "security_token": "...", "domain": "login"}
    # Pipedrive:  {"api_token": "..."}
    credentials = models.JSONField(default=dict)

    # Optional per-integration field mappings: {"internal_field": "crm_field_name"}
    field_mappings = models.JSONField(default=dict)

    sync_contacts = models.BooleanField(default=True)
    sync_emails = models.BooleanField(default=True)
    sync_meetings = models.BooleanField(default=True)
    sync_notes = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    last_ping_at = models.DateTimeField(null=True, blank=True)
    last_ping_ok = models.BooleanField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'crm_integration'
        unique_together = ('company', 'provider')
        ordering = ['provider']

    def __str__(self):
        return f'{self.company_id} / {self.provider}'


class CRMContactMapping(models.Model):
    """Maps an internal lead/contact to its CRM counterpart per integration."""

    SOURCE_SDR_LEAD = 'sdr_lead'
    SOURCE_FRONTLINE = 'frontline_contact'
    SOURCE_TYPES = [
        (SOURCE_SDR_LEAD, 'SDR Lead'),
        (SOURCE_FRONTLINE, 'Frontline Contact'),
    ]

    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        related_name='crm_contact_mappings',
    )
    integration = models.ForeignKey(
        CRMIntegration,
        on_delete=models.CASCADE,
        related_name='contact_mappings',
    )
    source_type = models.CharField(max_length=30, choices=SOURCE_TYPES)
    source_id = models.PositiveBigIntegerField()
    crm_contact_id = models.CharField(max_length=255)
    # Optional: deal / opportunity ID created alongside the contact
    crm_deal_id = models.CharField(max_length=255, blank=True)
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'crm_contact_mapping'
        unique_together = ('integration', 'source_type', 'source_id')
        indexes = [
            models.Index(fields=['integration', 'source_type', 'source_id']),
        ]

    def __str__(self):
        return f'{self.source_type}:{self.source_id} → {self.integration.provider}:{self.crm_contact_id}'


class CRMSyncLog(models.Model):
    """Immutable audit trail for every CRM sync operation."""

    TYPE_CONTACT = 'contact'
    TYPE_EMAIL = 'email_activity'
    TYPE_MEETING = 'meeting'
    TYPE_NOTE = 'note'
    OBJECT_TYPES = [
        (TYPE_CONTACT, 'Contact'),
        (TYPE_EMAIL, 'Email Activity'),
        (TYPE_MEETING, 'Meeting'),
        (TYPE_NOTE, 'Note'),
    ]

    OP_CREATE = 'create'
    OP_UPDATE = 'update'
    OPERATIONS = [
        (OP_CREATE, 'Create'),
        (OP_UPDATE, 'Update'),
    ]

    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_SKIPPED = 'skipped'
    STATUSES = [
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_SKIPPED, 'Skipped'),
    ]

    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        related_name='crm_sync_logs',
    )
    integration = models.ForeignKey(
        CRMIntegration,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sync_logs',
    )
    object_type = models.CharField(max_length=30, choices=OBJECT_TYPES)
    # Internal source identifier (e.g., "sdr_lead:42")
    object_id = models.CharField(max_length=200, blank=True)
    # ID returned by the CRM after sync
    crm_object_id = models.CharField(max_length=255, blank=True)
    operation = models.CharField(max_length=20, choices=OPERATIONS)
    status = models.CharField(max_length=20, choices=STATUSES)
    error_message = models.TextField(blank=True)
    payload = models.JSONField(default=dict)
    response = models.JSONField(default=dict)
    attempted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'crm_sync_log'
        ordering = ['-attempted_at']
        indexes = [
            models.Index(fields=['company', 'attempted_at']),
            models.Index(fields=['integration', 'status']),
        ]

    def __str__(self):
        return f'{self.object_type} {self.operation} [{self.status}] @ {self.attempted_at:%Y-%m-%d %H:%M}'


class CRMSyncQueue(models.Model):
    """
    Work queue for outbound CRM syncs.

    Items are enqueued by Django signals and processed by the
    `process_crm_sync_queue` Celery task. Failed items are retried
    up to `max_attempts` with exponential back-off.
    """

    TYPE_CONTACT = 'contact'
    TYPE_EMAIL = 'email_activity'
    TYPE_MEETING = 'meeting'
    TYPE_NOTE = 'note'
    OBJECT_TYPES = [
        (TYPE_CONTACT, 'Contact'),
        (TYPE_EMAIL, 'Email Activity'),
        (TYPE_MEETING, 'Meeting'),
        (TYPE_NOTE, 'Note'),
    ]

    OP_CREATE = 'create'
    OP_UPDATE = 'update'
    OPERATIONS = [
        (OP_CREATE, 'Create'),
        (OP_UPDATE, 'Update'),
    ]

    SOURCE_SDR_LEAD = 'sdr_lead'
    SOURCE_SDR_EMAIL = 'sdr_email'
    SOURCE_SDR_MEETING = 'sdr_meeting'
    SOURCE_SDR_NOTE = 'sdr_note'
    SOURCE_FRONTLINE = 'frontline_contact'
    SOURCE_TYPES = [
        (SOURCE_SDR_LEAD, 'SDR Lead'),
        (SOURCE_SDR_EMAIL, 'SDR Email'),
        (SOURCE_SDR_MEETING, 'SDR Meeting'),
        (SOURCE_SDR_NOTE, 'SDR Note'),
        (SOURCE_FRONTLINE, 'Frontline Contact'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_DONE = 'done'
    STATUS_FAILED = 'failed'
    STATUSES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_DONE, 'Done'),
        (STATUS_FAILED, 'Failed'),
    ]

    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        related_name='crm_sync_queue',
    )
    integration = models.ForeignKey(
        CRMIntegration,
        on_delete=models.CASCADE,
        related_name='sync_queue',
    )
    object_type = models.CharField(max_length=30, choices=OBJECT_TYPES)
    operation = models.CharField(max_length=20, choices=OPERATIONS, default=OP_CREATE)
    source_type = models.CharField(max_length=30, choices=SOURCE_TYPES)
    source_id = models.PositiveBigIntegerField()

    # 1 = highest priority, 10 = lowest; contacts default to 3, activities to 5
    priority = models.SmallIntegerField(default=5)

    # Denormalized snapshot of data to push — survives source deletion
    payload = models.JSONField(default=dict)

    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    last_attempted_at = models.DateTimeField(null=True, blank=True)
    # Allow scheduling items in the future (e.g. after a delay)
    scheduled_at = models.DateTimeField(default=timezone.now)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'crm_sync_queue'
        ordering = ['priority', 'scheduled_at']
        indexes = [
            models.Index(fields=['status', 'priority', 'scheduled_at']),
            models.Index(fields=['company', 'status']),
            models.Index(fields=['integration', 'status']),
        ]

    def __str__(self):
        return f'[{self.status}] {self.object_type} {self.source_type}:{self.source_id}'

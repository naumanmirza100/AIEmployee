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
    # Stored encrypted: {"enc": "<Fernet token of the JSON>"}. Read and written
    # through get_credentials() / set_credentials(), never directly. Rows saved
    # before encryption hold the plain values and are still read.
    credentials = models.JSONField(default=dict)

    # Optional per-integration field mappings: {"internal_field": "crm_field_name"}
    field_mappings = models.JSONField(default=dict)

    #: Credential fields that say where to sign in, not how; shown as they are.
    NOT_SECRET = ('domain', 'username')

    def get_credentials(self) -> dict:
        """The saved credentials, readable. They used to be kept in clear text
        and sent whole to the browser of any login in the company."""
        import json
        from core.crypto_utils import decrypt_secret
        stored = self.credentials or {}
        if set(stored) != {'enc'}:
            return dict(stored)             # saved before encryption
        try:
            return json.loads(decrypt_secret(stored['enc']) or '{}')
        except Exception:
            import logging
            logging.getLogger(__name__).error(
                'CRM integration %s: the saved credentials cannot be read with the keys this server has. '
                'Check FIELD_ENCRYPTION_KEY, or connect the CRM again.', self.pk)
            return {}

    def set_credentials(self, credentials: dict) -> None:
        import json
        from core.crypto_utils import encrypt_secret
        self.credentials = {'enc': encrypt_secret(json.dumps(credentials or {}))}

    #: Secrets of which nothing at all is shown: a person's password is not a key.
    SHOWN_AS_DOTS = ('password', 'client_secret', 'security_token')
    MASK = '********'

    def credentials_preview(self) -> dict:
        """What may be shown on screen: a password as `********`, a key as `********abcd` (its last four).

        It kept the first and last four characters of everything, so a Salesforce password 'Summer2026!' showed as
        'Summ********026!' (CO-160). The edit form sends the preview back, and anything containing `********` is
        taken as unchanged (api/views/crm_sync_agent.py, _merged_credentials)."""
        out = {}
        for key, value in self.get_credentials().items():
            text = str(value or '')
            if key in self.NOT_SECRET:
                out[key] = value
            elif not text:
                out[key] = ''
            elif key in self.SHOWN_AS_DOTS or len(text) < 20:
                out[key] = self.MASK
            else:
                out[key] = self.MASK + text[-4:]
        return out

    sync_contacts = models.BooleanField(default=True)
    sync_emails = models.BooleanField(default=True)
    sync_meetings = models.BooleanField(default=True)
    sync_notes = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    last_ping_at = models.DateTimeField(null=True, blank=True)
    last_ping_ok = models.BooleanField(null=True, blank=True)

    # Set True when the provider rejects writes because the account is over its
    # object/record limit (e.g. HubSpot free-tier 1000-contact cap). While True
    # the sync poller keeps deferring items; cleared automatically on the next
    # successful write. Surfaced in the UI so the user knows sync is paused.
    limit_reached = models.BooleanField(default=False)
    limit_message = models.TextField(blank=True)
    limit_reached_at = models.DateTimeField(null=True, blank=True)

    # When the CRM refused the saved key. Entries wait (STATUS_WAITING) instead of using up their attempts, and
    # go out again once a test of the connection succeeds or the key is changed (CO-159).
    key_refused_at = models.DateTimeField(null=True, blank=True)
    # What the CRM would not take for lack of a permission, said on the card: such entries are recorded as
    # skipped. They used to be recorded as sent (CO-162).
    missing_permission = models.TextField(blank=True)

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
    # The Inbox Manager's part of the client's list: mail from customers and leads, and the replies sent.
    SOURCE_INBOX_EMAIL = 'inbox_email'
    SOURCE_INBOX_REPLY = 'inbox_reply'
    SOURCE_TYPES = [
        (SOURCE_SDR_LEAD, 'SDR Lead'),
        (SOURCE_SDR_EMAIL, 'SDR Email'),
        (SOURCE_SDR_MEETING, 'SDR Meeting'),
        (SOURCE_SDR_NOTE, 'SDR Note'),
        (SOURCE_FRONTLINE, 'Frontline Contact'),
        (SOURCE_INBOX_EMAIL, 'Reply Draft: email received'),
        (SOURCE_INBOX_REPLY, 'Reply Draft: reply sent'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_DONE = 'done'
    STATUS_FAILED = 'failed'
    # Held until the CRM takes the key again (CO-159).
    STATUS_WAITING = 'waiting'
    # Not sent: the CRM refused it for lack of a permission (CO-162).
    STATUS_SKIPPED = 'skipped'
    STATUSES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_DONE, 'Done'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_WAITING, 'Waiting for the CRM key'),
        (STATUS_SKIPPED, 'Skipped'),
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


class CRMActivityMapping(models.Model):
    """The CRM's own id for something we sent it that can change later: a sales call that is moved or cancelled.

    The id was not kept, so a call moved or cancelled after it reached the CRM stayed there as it was (CO-275)."""

    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='crm_activity_mappings')
    integration = models.ForeignKey(CRMIntegration, on_delete=models.CASCADE, related_name='activity_mappings')
    source_type = models.CharField(max_length=30)
    source_id = models.PositiveBigIntegerField()
    crm_object_id = models.CharField(max_length=255)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'crm_activity_mapping'
        unique_together = ('integration', 'source_type', 'source_id')

    def __str__(self):
        return f'{self.source_type}:{self.source_id} → {self.crm_object_id}'

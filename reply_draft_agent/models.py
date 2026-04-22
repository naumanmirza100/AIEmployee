from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

from marketing_agent.models import Reply, Lead, EmailAccount, EmailSendHistory


INTEREST_LEVEL_CHOICES = [
    ('positive', 'Positive/Interested'),
    ('negative', 'Negative/Not Interested'),
    ('neutral', 'Neutral'),
    ('requested_info', 'Requested More Information'),
    ('objection', 'Has Objection/Concern'),
    ('unsubscribe', 'Unsubscribe Request'),
    ('not_analyzed', 'Not Analyzed'),
]


class InboxEmail(models.Model):
    """Generic inbound email stored for the Reply Draft Agent.

    Populated by the IMAP sync task for every message in the mailbox that
    is NOT a reply to a campaign-sent email (those go into marketing_agent.Reply).
    One row per (email_account, message_id).
    """
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='inbox_emails')
    email_account = models.ForeignKey(
        EmailAccount, on_delete=models.CASCADE, related_name='inbox_emails',
        help_text='Mailbox this message arrived in'
    )

    message_id = models.CharField(max_length=500, db_index=True,
                                  help_text='RFC Message-ID header (dedupe key)')
    in_reply_to = models.CharField(max_length=500, blank=True)
    references = models.TextField(blank=True)

    from_email = models.EmailField(db_index=True)
    from_name = models.CharField(max_length=255, blank=True)
    subject = models.CharField(max_length=500, blank=True)
    body = models.TextField(blank=True)

    received_at = models.DateTimeField(db_index=True, default=timezone.now,
                                       help_text='Date header from the message, or sync time as fallback')

    # AI analysis (populated lazily when a draft is generated)
    interest_level = models.CharField(max_length=20, choices=INTEREST_LEVEL_CHOICES, default='not_analyzed')
    analysis = models.TextField(blank=True)

    synced_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ppp_replydraftagent_inboxemail'
        ordering = ['-received_at']
        unique_together = [('email_account', 'message_id')]
        indexes = [
            models.Index(fields=['owner', '-received_at']),
            models.Index(fields=['email_account', '-received_at']),
            models.Index(fields=['from_email']),
        ]

    def __str__(self):
        return f"InboxEmail from {self.from_email} at {self.received_at:%Y-%m-%d %H:%M}"


class ReplyDraft(models.Model):
    """AI-generated draft reply to an incoming email, pending user review."""

    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('sent', 'Sent'),
        ('rejected', 'Rejected'),
        ('failed', 'Send Failed'),
    ]

    TONE_CHOICES = [
        ('professional', 'Professional'),
        ('friendly', 'Friendly'),
        ('formal', 'Formal'),
        ('casual', 'Casual'),
        ('apologetic', 'Apologetic'),
        ('confident', 'Confident'),
        ('empathetic', 'Empathetic'),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reply_drafts')

    original_email = models.ForeignKey(
        Reply, on_delete=models.CASCADE, related_name='drafts',
        null=True, blank=True,
        help_text='The campaign reply this draft is replying to (exactly one of original_email / inbox_email is set)'
    )
    inbox_email = models.ForeignKey(
        InboxEmail, on_delete=models.CASCADE, related_name='drafts',
        null=True, blank=True,
        help_text='The generic inbox email this draft is replying to'
    )
    lead = models.ForeignKey(Lead, on_delete=models.SET_NULL, null=True, blank=True, related_name='reply_drafts')
    email_account = models.ForeignKey(
        EmailAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='reply_drafts',
        help_text='Which account to send from. Defaults to the user default.'
    )

    draft_subject = models.CharField(max_length=500, help_text='AI-generated subject')
    draft_body = models.TextField(help_text='AI-generated body')

    edited_subject = models.CharField(max_length=500, blank=True, help_text='User-edited subject (overrides draft)')
    edited_body = models.TextField(blank=True, help_text='User-edited body (overrides draft)')

    tone = models.CharField(max_length=20, choices=TONE_CHOICES, default='professional')
    ai_notes = models.TextField(blank=True, help_text='AI reasoning / notes about the draft')
    generation_prompt = models.TextField(blank=True, help_text='Extra instructions the user provided')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    sent_at = models.DateTimeField(null=True, blank=True)
    sent_email = models.ForeignKey(
        EmailSendHistory, on_delete=models.SET_NULL, null=True, blank=True, related_name='reply_drafts'
    )
    send_error = models.TextField(blank=True)

    regeneration_count = models.IntegerField(default=0)
    parent_draft = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='regenerations',
        help_text='The previous draft this one replaced (when regenerated)'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ppp_replydraftagent_replydraft'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner', 'status', '-created_at']),
            models.Index(fields=['original_email', '-created_at']),
        ]

    def __str__(self):
        target = self.get_recipient_email() or 'unknown'
        return f"Draft to {target} ({self.get_status_display()})"

    # --- source abstraction (campaign Reply vs generic InboxEmail) ---

    @property
    def source_kind(self):
        if self.original_email_id:
            return 'reply'
        if self.inbox_email_id:
            return 'inbox'
        return 'unknown'

    def get_recipient_email(self):
        """Where this draft will be sent. Prefers lead (set by Reply source)."""
        if self.lead_id and self.lead and self.lead.email:
            return self.lead.email
        if self.inbox_email_id and self.inbox_email:
            return self.inbox_email.from_email
        return ''

    def get_recipient_name(self):
        if self.lead_id and self.lead:
            full = ' '.join(filter(None, [self.lead.first_name, self.lead.last_name])).strip()
            if full:
                return full
        if self.inbox_email_id and self.inbox_email:
            return self.inbox_email.from_name or ''
        return ''

    def get_original_subject(self):
        if self.original_email_id and self.original_email:
            return self.original_email.reply_subject or ''
        if self.inbox_email_id and self.inbox_email:
            return self.inbox_email.subject or ''
        return ''

    def get_original_body(self):
        if self.original_email_id and self.original_email:
            return self.original_email.reply_content or ''
        if self.inbox_email_id and self.inbox_email:
            return self.inbox_email.body or ''
        return ''

    def get_original_analysis(self):
        if self.original_email_id and self.original_email:
            return self.original_email.analysis or ''
        if self.inbox_email_id and self.inbox_email:
            return self.inbox_email.analysis or ''
        return ''

    def get_original_interest_level(self):
        if self.original_email_id and self.original_email:
            return self.original_email.interest_level or ''
        if self.inbox_email_id and self.inbox_email:
            return self.inbox_email.interest_level or ''
        return ''

    def get_final_subject(self):
        return (self.edited_subject or self.draft_subject or '').strip()

    def get_final_body(self):
        return self.edited_body or self.draft_body or ''

    def mark_sent(self, send_history):
        self.status = 'sent'
        self.sent_at = timezone.now()
        self.sent_email = send_history
        self.send_error = ''
        self.save(update_fields=['status', 'sent_at', 'sent_email', 'send_error', 'updated_at'])

    def mark_failed(self, error):
        self.status = 'failed'
        self.send_error = str(error)[:2000]
        self.save(update_fields=['status', 'send_error', 'updated_at'])

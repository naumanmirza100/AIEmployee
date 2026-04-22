from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

from marketing_agent.models import Reply, Lead, EmailAccount, EmailSendHistory


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
        help_text='The incoming email that this draft is replying to'
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
        target = self.lead.email if self.lead_id else 'unknown'
        return f"Draft to {target} ({self.get_status_display()})"

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

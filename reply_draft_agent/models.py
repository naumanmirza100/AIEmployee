import re

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
    body = models.TextField(blank=True, default='',
                            help_text='Plain-text body. Used for AI analysis and search; preferred over HTML when both are present in the source.')
    # Nullable + empty default so any caller path (including older-stamp
    # workers that haven't picked up the new field, and the campaign-reply
    # branch that constructs InboxEmail in different shapes) can insert
    # without violating a NOT NULL constraint. Frontend treats NULL the
    # same as empty string.
    body_html = models.TextField(blank=True, null=True, default='',
                                 help_text='Original HTML body if the source carried one. Rendered in the UI for fidelity (links, images, layout); plain `body` is used as fallback when this is empty.')

    received_at = models.DateTimeField(db_index=True, default=timezone.now,
                                       help_text='Date header from the message, or sync time as fallback')

    # AI analysis (populated lazily when a draft is generated)
    interest_level = models.CharField(max_length=20, choices=INTEREST_LEVEL_CHOICES, default='not_analyzed')
    analysis = models.TextField(blank=True)

    # Recipient + direction. Mirrors columns added by migration
    # 0003_inboxemail_direction_to_email — kept in the model so inserts
    # don't violate the NOT NULL constraint on those columns.
    to_email = models.EmailField(blank=True, default='',
                                 help_text='Mailbox the message was delivered to (the EmailAccount address)')
    direction = models.CharField(max_length=4, default='in',
                                 help_text="'in' for received mail, 'out' for sent")

    # Conversation grouping key. Derived from the RFC References chain
    # (root message-id) when present; falls back to a normalized
    # subject + canonical participant pair so plain "Re:" exchanges that
    # don't carry References still group. Populated at sync time —
    # nullable + indexed so existing rows stay valid until backfill.
    thread_key = models.CharField(max_length=120, blank=True, default='', db_index=True,
                                  help_text='Stable key shared by every message in the same conversation.')

    # Lazy-attachment flag. The IMAP sync intentionally skips attachment
    # extraction — pulling RFC822 bodies + writing files inline was the
    # dominant cost of a fresh sync (a 2000-message backfill spent more
    # time on attachments than on everything else combined). Sync stamps
    # this False; the per-email lazy-fetch endpoint flips it True after
    # downloading the attachments on first open. UI uses the flag to know
    # whether it must call the lazy endpoint before rendering files.
    attachments_fetched = models.BooleanField(
        default=False,
        help_text='True once attachments have been downloaded from IMAP. '
                  'False means sync stored only headers/body; call the '
                  'fetch-attachments endpoint when the user opens the email.',
    )

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
            models.Index(fields=['email_account', 'thread_key']),
        ]

    def __str__(self):
        return f"InboxEmail from {self.from_email} at {self.received_at:%Y-%m-%d %H:%M}"

    @staticmethod
    def compute_thread_key(*, references, in_reply_to, subject, from_email, to_email, max_len=120):
        """Derive a stable per-thread key from RFC headers + subject.

        Preference order:
          1. Root message-id from the References chain (most reliable —
             every reply in a thread keeps the same first References entry).
          2. The In-Reply-To header (one-step-back parent).
          3. Hash of normalized subject + sorted participant pair (works
             when the sender's client doesn't set References, as some
             webmail clients still don't).

        The result is truncated to `max_len` chars so it fits the column.
        """
        import hashlib

        refs = (references or '').strip()
        if refs:
            # References can be space- or newline-separated; the first
            # token is the root of the thread.
            first = refs.split()[0].strip().lstrip('<').rstrip('>')
            if first:
                return ('root:' + first)[:max_len]

        irt = (in_reply_to or '').strip().lstrip('<').rstrip('>')
        if irt:
            return ('irt:' + irt)[:max_len]

        # Subject-based fallback. Strip the standard reply prefixes and
        # collapse whitespace so "Re: Re: Foo" and "Foo" land together.
        subj = (subject or '').strip()
        subj = re.sub(r'^(?:\s*(?:re|fwd?|aw)\s*:\s*)+', '', subj, flags=re.IGNORECASE)
        subj = re.sub(r'\s+', ' ', subj).strip().lower()

        # Canonical participant pair: sort the two addresses so an exchange
        # in either direction shares the same key.
        pair = sorted(filter(None, [(from_email or '').strip().lower(), (to_email or '').strip().lower()]))
        seed = (subj + '|' + '|'.join(pair)).encode('utf-8', 'ignore')
        digest = hashlib.sha1(seed).hexdigest()[:24]
        return ('subj:' + digest)[:max_len]


def _inbox_attachment_upload_path(instance, original_filename):
    """Where Django stores the file under ``default_storage``.

    Path layout: ``inbox_attachments/<account_id>/<email_id>/<sha8>-<filename>``.
    Bucketing by account + email keeps directories small enough for fast
    listing on local disk and yields stable S3 prefixes when the storage
    backend is later swapped to S3 (just flip ``DEFAULT_FILE_STORAGE``;
    this code stays unchanged).
    """
    # `instance.sha256` is set before .save(); fall back to '' if a caller
    # forgot, in which case Django will append its own uniquifier on collision.
    sha_prefix = (instance.sha256 or '')[:8]
    safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', original_filename)[:120] or 'attachment.bin'
    return (
        f'inbox_attachments/'
        f'{instance.inbox_email.email_account_id}/'
        f'{instance.inbox_email_id}/'
        f'{sha_prefix}-{safe_name}'
    )


class InboxAttachment(models.Model):
    """File attachment on an InboxEmail.

    Uses Django's ``FileField`` against ``default_storage``, so the file
    lives wherever ``DEFAULT_FILE_STORAGE`` points: on local disk today
    (``MEDIA_ROOT``), on S3 the day someone flips one settings line. DB
    row holds only metadata so SQL Server isn't loaded down with blobs.
    """

    inbox_email = models.ForeignKey(
        InboxEmail, on_delete=models.CASCADE, related_name='attachments',
        help_text='Email this attachment was extracted from. CASCADE keeps the table consistent '
                  'when emails are pruned; the actual file is removed by the post_delete signal '
                  'wired up in apps.py.',
    )
    filename = models.CharField(max_length=255, help_text='Original filename from the message part.')
    content_type = models.CharField(max_length=120, blank=True, default='')
    size_bytes = models.BigIntegerField(default=0)
    file = models.FileField(upload_to=_inbox_attachment_upload_path, max_length=1000,
                            help_text='Stored via default_storage (local FS now, S3 later).')
    sha256 = models.CharField(max_length=64, blank=True, default='', db_index=True,
                              help_text='Content hash. Lets us dedupe identical files across emails.')
    # Inline-image content-id (e.g. "<image001@01D8...@laskon.com>") so the
    # frontend can later swap `cid:` references in body_html for download URLs.
    content_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    is_inline = models.BooleanField(default=False,
                                    help_text='True for cid: parts referenced inside body_html (e.g. inline images).')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ppp_replydraftagent_inboxattachment'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['inbox_email', 'created_at']),
        ]

    def __str__(self):
        return f"InboxAttachment {self.filename} ({self.size_bytes}B) on email #{self.inbox_email_id}"


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

    # Recipient for fresh-compose drafts (the Gmail-style "+ Compose" flow,
    # not a reply to anything). Reply drafts leave this blank and resolve
    # the recipient through `lead.email` or `inbox_email.from_email`.
    compose_to_email = models.EmailField(blank=True, default='',
                                         help_text='Recipient address for fresh-compose drafts (no source email)')

    # Whether `draft_body` / `edited_body` should be treated as plain text
    # or as HTML. AI-generated reply drafts are always 'text' (the model
    # outputs plain text), so this defaults to 'text' for backwards
    # compatibility. Compose drafts written in HTML mode flip this to
    # 'html', which makes send_approved use the body as-is for the HTML
    # MIME alternative instead of running it through the plain→HTML
    # converter.
    BODY_FORMAT_CHOICES = [
        ('text', 'Plain text'),
        ('html', 'HTML'),
    ]
    body_format = models.CharField(max_length=4, choices=BODY_FORMAT_CHOICES, default='text')

    tone = models.CharField(max_length=20, choices=TONE_CHOICES, default='professional')
    ai_notes = models.TextField(blank=True, help_text='AI reasoning / notes about the draft')
    generation_prompt = models.TextField(blank=True, help_text='Extra instructions the user provided')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    sent_at = models.DateTimeField(null=True, blank=True)
    sent_email = models.ForeignKey(
        EmailSendHistory, on_delete=models.SET_NULL, null=True, blank=True, related_name='reply_drafts'
    )
    send_error = models.TextField(blank=True)

    # Newline-separated list of every RFC Message-ID this draft has used
    # in an SMTP attempt. Saved BEFORE each email.send() so we have a
    # record even when the provider rejects the message (e.g. Gmail's 552
    # security block). The Sent tab uses this to suppress IMAP-synced
    # Sent-folder copies of failed sends — Gmail retains a copy of a
    # 552-rejected message in the user's Sent folder, which would
    # otherwise look like a successful send in our app.
    #
    # APPENDED, never overwritten — a draft retried 3 times has 3 IDs to
    # filter, not 1. The earlier singular `attempted_message_id` (kept
    # below for back-compat with rows the data migration ran on) only
    # tracked the latest, so prior failed attempts leaked into Sent.
    attempted_message_ids = models.TextField(blank=True, default='')

    # Legacy singular field — retained on the model so existing migrations
    # that referenced it (and the dual-read in list_pending_replies)
    # continue to resolve. Always mirrors the LATEST entry written to
    # `attempted_message_ids`. Removed from primary write paths but kept
    # readable; do not rely on this field alone for new logic.
    attempted_message_id = models.CharField(max_length=500, blank=True, default='', db_index=True)

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
        if self.compose_to_email:
            return 'compose'
        return 'unknown'

    def get_recipient_email(self):
        """Where this draft will be sent. Prefers lead (set by Reply source)."""
        if self.lead_id and self.lead and self.lead.email:
            return self.lead.email
        if self.inbox_email_id and self.inbox_email:
            return self.inbox_email.from_email
        # Fresh-compose draft: the user typed the recipient directly into
        # the To: field; no lead or source email is involved.
        if self.compose_to_email:
            return self.compose_to_email
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

    def get_original_body_html(self):
        """HTML version of the source message body, when the source carried one.

        Used by the draft view's "thread context" pane so an HTML email
        (e.g. transactional / newsletter style messages with `body_html`
        populated by the IMAP sync) renders the same as it does in the
        Inbox tab. Without this the pane falls back to plain `body`,
        which for many marketing emails is the raw HTML source dumped as
        text — not what the user expects.
        """
        if self.inbox_email_id and self.inbox_email:
            return self.inbox_email.body_html or ''
        # Reply (campaign-thread) sources don't store HTML separately.
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


def _reply_draft_attachment_upload_path(instance, original_filename):
    """Where Django stores the uploaded file under ``default_storage``.

    Layout: ``reply_draft_attachments/<owner_id>/<draft_id>/<sha8>-<filename>``.
    Bucketing by owner + draft mirrors the inbox-attachment layout so the
    later S3 swap is a one-line setting flip with no path rewrites.
    """
    sha_prefix = (instance.sha256 or '')[:8]
    safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', original_filename)[:120] or 'attachment.bin'
    owner_id = getattr(instance.draft, 'owner_id', 0) if instance.draft_id else 0
    return (
        f'reply_draft_attachments/'
        f'{owner_id}/'
        f'{instance.draft_id}/'
        f'{sha_prefix}-{safe_name}'
    )


class ReplyDraftAttachment(models.Model):
    """User-uploaded attachment for an outgoing ReplyDraft.

    Stored via ``default_storage`` (local disk today, S3 later) so the DB
    holds metadata only. Wired into ``ReplyDraftAgent.send_approved`` —
    every row tied to the draft is attached to the outbound SMTP message
    when the user clicks Send.
    """

    draft = models.ForeignKey(
        ReplyDraft, on_delete=models.CASCADE, related_name='attachments',
        help_text='Draft this file is attached to. CASCADE drops the row when the draft is deleted; '
                  'the underlying file is removed by the post_delete signal wired up in apps.py.',
    )
    filename = models.CharField(max_length=255, help_text='Original filename uploaded by the user.')
    content_type = models.CharField(max_length=120, blank=True, default='')
    size_bytes = models.BigIntegerField(default=0)
    file = models.FileField(
        upload_to=_reply_draft_attachment_upload_path, max_length=1000,
        help_text='Stored via default_storage (local FS now, S3 later).',
    )
    sha256 = models.CharField(max_length=64, blank=True, default='', db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ppp_replydraftagent_replydraftattachment'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['draft', 'created_at']),
        ]

    def __str__(self):
        return f"ReplyDraftAttachment {self.filename} ({self.size_bytes}B) on draft #{self.draft_id}"

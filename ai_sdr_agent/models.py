import logging
import uuid
from datetime import date as _date, timedelta as _timedelta

from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

from ai_sdr_agent.fields import EncryptedCharField


class SDRIcpProfile(models.Model):
    """Ideal Customer Profile — defines who to target for outreach."""
    company_user = models.ForeignKey(
        'core.CompanyUser', on_delete=models.CASCADE, related_name='sdr_icp_profiles'
    )
    name = models.CharField(max_length=255, default='Default ICP')

    # Targeting criteria
    industries = models.JSONField(default=list)       # ["SaaS", "FinTech"]
    job_titles = models.JSONField(default=list)        # ["VP Sales", "Head of Marketing"]
    locations = models.JSONField(default=list)         # ["United States", "UK"]
    keywords = models.JSONField(default=list)          # ["AI", "automation"]
    company_size_min = models.IntegerField(null=True, blank=True)
    company_size_max = models.IntegerField(null=True, blank=True)

    # Scoring thresholds
    hot_threshold = models.IntegerField(default=75)   # score >= hot_threshold → Hot
    warm_threshold = models.IntegerField(default=60)  # score >= warm_threshold → Warm

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sdr_icp_profile'

    def __str__(self):
        return f"{self.company_user} — {self.name}"


class SDRLeadManager(models.Manager):
    """Default manager that hides soft-deleted leads.

    Every list, stats, CRM-sync and analytics query goes through ``objects``,
    so filtering here means a deleted lead disappears everywhere at once without
    having to remember ``is_deleted=False`` at each of the ~27 call sites. Use
    ``SDRLead.all_objects`` when you genuinely need deleted rows too (e.g. the
    restore endpoint).
    """

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class SDRLead(models.Model):
    """Individual sales lead with enrichment and AI qualification data."""

    STATUS_CHOICES = [
        ('new', 'New'),
        ('qualified', 'Qualified'),
        ('contacted', 'Contacted'),
        ('replied', 'Replied'),
        ('meeting_scheduled', 'Meeting Scheduled'),
        ('converted', 'Converted'),
        ('disqualified', 'Disqualified'),
    ]
    TEMPERATURE_CHOICES = [
        ('hot', 'Hot'),
        ('warm', 'Warm'),
        ('cold', 'Cold'),
    ]
    SOURCE_CHOICES = [
        ('apollo', 'Apollo.io'),
        ('apify', 'Apify'),
        ('manual', 'Manual'),
        ('csv_import', 'CSV Import'),
        ('ai_generated', 'AI Generated'),
    ]

    company_user = models.ForeignKey(
        'core.CompanyUser', on_delete=models.CASCADE, related_name='sdr_leads'
    )
    icp_profile = models.ForeignKey(
        'SDRIcpProfile', on_delete=models.SET_NULL, null=True, blank=True
    )

    # Identity
    first_name = models.CharField(max_length=255, blank=True)
    last_name = models.CharField(max_length=255, blank=True)
    full_name = models.CharField(max_length=255, blank=True)
    email = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=100, blank=True)

    # Professional
    job_title = models.CharField(max_length=255, blank=True)
    seniority_level = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)

    # Company
    company_name = models.CharField(max_length=255, blank=True)
    company_domain = models.CharField(max_length=255, blank=True)
    company_industry = models.CharField(max_length=255, blank=True)
    company_size = models.IntegerField(null=True, blank=True)
    company_size_range = models.CharField(max_length=100, blank=True)
    company_location = models.CharField(max_length=255, blank=True)
    company_technologies = models.JSONField(default=list)

    # Online presence
    linkedin_url = models.CharField(max_length=500, blank=True)
    company_linkedin_url = models.CharField(max_length=500, blank=True)
    company_website = models.CharField(max_length=500, blank=True)

    # Enrichment signals
    recent_news = models.JSONField(default=list)      # [{title, date, summary}]
    buying_signals = models.JSONField(default=list)   # ["Just raised Series A", ...]

    # Apollo.io raw data
    apollo_id = models.CharField(max_length=255, blank=True)
    raw_data = models.JSONField(default=dict)

    # AI Qualification
    score = models.IntegerField(null=True, blank=True)           # 0–100
    temperature = models.CharField(max_length=10, choices=TEMPERATURE_CHOICES, blank=True)
    score_breakdown = models.JSONField(default=dict)             # {company_quality:22, contact_quality:18, ...}
    qualification_reasoning = models.TextField(blank=True)
    key_strengths = models.JSONField(default=list, blank=True)
    concerns = models.JSONField(default=list, blank=True)
    outreach_strategy = models.TextField(blank=True)
    confidence_score = models.IntegerField(null=True, blank=True, help_text="Data accuracy confidence 0-100")
    data_quality_flags = models.JSONField(default=list, blank=True)

    # Background qualification queue. Instead of scoring every new lead
    # synchronously (which exhausts AI tokens in one burst), leads are queued and
    # a scheduler processes them in small batches, retrying failures.
    QUALIFICATION_STATUS_CHOICES = [
        ('none',       'Not queued'),     # legacy / manual, not in the queue
        ('pending',    'Queued'),         # waiting to be qualified
        ('processing', 'Processing'),     # currently being qualified
        ('done',       'Qualified'),      # scored successfully
        ('failed',     'Failed'),         # errored — retried until attempts run out
    ]
    qualification_status = models.CharField(
        max_length=12, choices=QUALIFICATION_STATUS_CHOICES, default='none', db_index=True,
    )
    qualification_attempts = models.IntegerField(default=0)
    qualification_error = models.TextField(blank=True)
    qualification_queued_at = models.DateTimeField(null=True, blank=True)

    # Workflow
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='new')
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default='manual')


    # Email validity — set to True when a hard bounce is detected
    email_bounced        = models.BooleanField(default=False)
    email_bounced_at     = models.DateTimeField(null=True, blank=True)
    email_bounce_reason  = models.CharField(max_length=500, blank=True)

    qualified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # Soft delete — a deleted lead is hidden by the default manager but kept in
    # the table so it can be restored (the "Undo" after a delete).
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SDRLeadManager()      # hides soft-deleted rows (the default everywhere)
    all_objects = models.Manager()  # includes soft-deleted rows (for restore)

    class Meta:
        db_table = 'sdr_lead'
        ordering = ['-score', '-created_at']
        # Django uses the base manager for related-object lookups and
        # serialization; point it at the unfiltered manager so those internals
        # never silently drop a soft-deleted row they legitimately need.
        base_manager_name = 'all_objects'

    def __str__(self):
        return f"{self.display_name} — {self.company_name} ({self.temperature or 'unscored'})"

    def soft_delete(self):
        """Mark as deleted without removing the row, so it can be restored."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

    def restore(self):
        """Undo a soft delete."""
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

    @property
    def display_name(self):
        return (
            self.full_name
            or f"{self.first_name} {self.last_name}".strip()
            or self.email
            or "Unknown"
        )


class SDRCampaign(models.Model):
    """An outreach campaign that sequences emails and LinkedIn touches to SDR leads."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
    ]

    company_user = models.ForeignKey(
        'core.CompanyUser', on_delete=models.CASCADE, related_name='sdr_campaigns'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    # Why the product itself paused this campaign (its mailbox refused to send, or
    # its owner's login was switched off). Shown on the campaign; cleared when it
    # is switched back on. Blank when a person paused it.
    paused_reason = models.CharField(max_length=500, blank=True, default='')

    # Sender identity (used for email personalisation)
    sender_name = models.CharField(max_length=255, blank=True)
    sender_title = models.CharField(max_length=255, blank=True)
    sender_company = models.CharField(max_length=255, blank=True)
    # Physical mailing address printed in the email footer (CAN-SPAM requirement).
    postal_address = models.CharField(max_length=500, blank=True, default='')

    # SMTP settings (per-campaign, self-contained)
    from_email = models.CharField(max_length=255, blank=True)
    smtp_host = models.CharField(max_length=255, blank=True)
    smtp_port = models.IntegerField(default=587)
    smtp_username = models.CharField(max_length=255, blank=True)
    smtp_password = EncryptedCharField(max_length=1000, blank=True)   # Fernet-encrypted at rest
    smtp_use_tls = models.BooleanField(default=True)

    # IMAP settings for reply detection. The login is the SMTP one above; with none set,
    # replies are not checked (never the platform's own mailbox login).
    imap_host = models.CharField(max_length=255, blank=True)
    imap_port = models.IntegerField(default=993)

    # Scheduling / handoff
    calendar_link = models.CharField(max_length=500, blank=True)  # Calendly / calendar URL

    # Auto-run scheduling (Celery)
    start_date = models.DateField(null=True, blank=True)        # auto-activates when reached
    end_date = models.DateField(null=True, blank=True)          # informational; auto-derived
    auto_check_replies = models.BooleanField(default=True)       # poll IMAP every 5 min
    # A lead who writes back asking for more gets an answer written by the AI. On:
    # the answer waits as a draft for the campaign's owner to read and send
    # (ai_sdr_agent/reply_answers.py). Off: it is sent at once, as it always was.
    # On for new campaigns; campaigns that existed before the switch keep sending.
    review_ai_replies = models.BooleanField(default=True)
    last_replies_checked_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)

    # Stats (denormalised for quick reads)
    total_leads = models.IntegerField(default=0)
    emails_sent = models.IntegerField(default=0)
    replies_received = models.IntegerField(default=0)
    meetings_booked = models.IntegerField(default=0)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sdr_campaign'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.status})"

    def derive_end_date(self):
        """End date = start_date + max delay_days across all steps (defaults 10)."""
        if not self.start_date:
            return None
        # start_date may be a raw string when called right after objects.create()
        # before Django does a DB-fetch roundtrip — coerce it to a date object.
        start = self.start_date
        if isinstance(start, str):
            start = _date.fromisoformat(start)
        max_delay = self.steps.aggregate(m=models.Max('delay_days'))['m'] or 10
        return start + _timedelta(days=max_delay)

    def _coerce_start_date(self):
        """Return start_date as a date object regardless of whether it's a str or date."""
        if not self.start_date:
            return None
        if isinstance(self.start_date, str):
            return _date.fromisoformat(self.start_date)
        return self.start_date

    # The mailbox settings are typed or pasted in, and a space around one names a server that does not exist:
    # 'srv1983265.hstgr.cloud ' passed the check (validate_mail_server strips before it looks) and was saved as it
    # was, so the campaign sent nothing ("Name or service not known") and read no replies.
    _TRIMMED_FIELDS = ('from_email', 'smtp_host', 'smtp_username', 'imap_host')

    def save(self, *args, **kwargs):
        for name in self._TRIMMED_FIELDS:
            value = getattr(self, name)
            if isinstance(value, str):
                setattr(self, name, value.strip())
        # Auto-derive end_date from start_date + longest step delay
        if self.start_date and self.pk:
            self.end_date = self.derive_end_date()
        # Auto-activate scheduled campaigns when start_date arrives
        start = self._coerce_start_date()
        if (
            self.status == 'scheduled'
            and start
            and start <= timezone.now().date()
            and self.steps.filter(is_active=True).exists() if self.pk else False
        ):
            self.status = 'active'
            self.activated_at = timezone.now()
        super().save(*args, **kwargs)


class SDRCampaignStep(models.Model):
    """One step in an outreach campaign (email or LinkedIn touch)."""

    STEP_TYPE_CHOICES = [
        ('email', 'Email'),
        ('linkedin', 'LinkedIn Request'),
    ]

    campaign = models.ForeignKey(SDRCampaign, on_delete=models.CASCADE, related_name='steps')
    step_order = models.IntegerField(default=1)
    step_type = models.CharField(max_length=30, choices=STEP_TYPE_CHOICES, default='email')
    delay_days = models.IntegerField(default=1)   # days from enrollment start (cumulative)
    name = models.CharField(max_length=255, blank=True)
    subject_template = models.CharField(max_length=500, blank=True)
    body_template = models.TextField(blank=True)
    ai_personalize = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'sdr_campaign_step'
        ordering = ['step_order']

    def __str__(self):
        return f"Step {self.step_order} — Day {self.delay_days} ({self.step_type})"


class SDRCampaignEnrollment(models.Model):
    """Tracks a single lead's progress through a campaign."""

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('replied', 'Replied'),
        ('completed', 'Completed'),
        ('unsubscribed', 'Unsubscribed'),
        ('bounced', 'Bounced'),
    ]

    campaign = models.ForeignKey(SDRCampaign, on_delete=models.CASCADE, related_name='enrollments')
    lead = models.ForeignKey(SDRLead, on_delete=models.CASCADE, related_name='campaign_enrollments')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    current_step = models.IntegerField(default=0)   # index of next step to execute
    next_action_at = models.DateTimeField(null=True, blank=True)

    replied_at = models.DateTimeField(null=True, blank=True)
    reply_content = models.TextField(blank=True)
    reply_sentiment = models.CharField(max_length=20, blank=True)  # positive/negative/neutral
    # Message-ID (or a hash of sender/date/subject) of the last reply we acted on.
    # Claimed atomically so the same inbox message is never processed twice.
    last_reply_message_id = models.CharField(max_length=255, blank=True, default='')

    enrolled_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sdr_campaign_enrollment'
        unique_together = ['campaign', 'lead']
        ordering = ['-enrolled_at']

    def __str__(self):
        return f"{self.lead.display_name} → {self.campaign.name} ({self.status})"


class SDRRemovedEnrollment(models.Model):
    """Who an unsubscribe link belongs to, kept after its enrolment is deleted.

    Emails sent before 10 October 2026 carry an unsubscribe link that names only
    the enrolment. Deleting a campaign or clearing its leads deletes the
    enrolment, and the link then had nobody to unsubscribe. This keeps the two
    facts such a link needs: the company and the address. Links made since
    carry both themselves and do not need it.
    """
    enrollment_id = models.BigIntegerField(unique=True)
    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='+')
    email = models.CharField(max_length=254)
    removed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'sdr_removed_enrollment'

    def __str__(self):
        return f"enrolment {self.enrollment_id}: {self.email}"


@receiver(pre_delete, sender=SDRCampaignEnrollment)
def remember_who_the_unsubscribe_link_was_for(sender, instance, **kwargs):
    """Runs for a single delete, a bulk delete and a delete that follows from
    its campaign or lead being deleted. Never stops the delete."""
    try:
        email = (instance.lead.email or '').strip()
        company_id = instance.campaign.company_user.company_id
        if email and company_id:
            SDRRemovedEnrollment.objects.update_or_create(
                enrollment_id=instance.pk, defaults={'company_id': company_id, 'email': email})
    except Exception:
        logging.getLogger(__name__).warning(
            'Could not keep the unsubscribe details of enrolment %s', instance.pk, exc_info=True)


class SDRReplyDraft(models.Model):
    """An answer the AI wrote to a lead's reply, kept for a person to check.

    Made when the campaign has 'Check the AI's answers before they are sent' on.
    'sending' is held only for the moment the email is going out, so that two
    people pressing Send together send one email."""

    STATUS_CHOICES = [
        ('pending', 'Waiting to be checked'),
        ('sending', 'Being sent'),
        ('sent', 'Sent'),
        ('discarded', 'Discarded'),
    ]

    enrollment = models.ForeignKey(SDRCampaignEnrollment, on_delete=models.CASCADE, related_name='reply_drafts')
    lead_reply = models.TextField(blank=True)          # what the lead wrote
    subject = models.CharField(max_length=500, blank=True)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey('core.CompanyUser', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')

    class Meta:
        db_table = 'sdr_reply_draft'
        ordering = ['-created_at']

    def __str__(self):
        return f"Answer to enrolment {self.enrollment_id} ({self.status})"


class SDROutreachLog(models.Model):
    """Audit log of every outreach action (email sent, LinkedIn noted, etc.)."""

    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]

    enrollment = models.ForeignKey(
        SDRCampaignEnrollment, on_delete=models.CASCADE, related_name='logs'
    )
    step = models.ForeignKey(SDRCampaignStep, on_delete=models.SET_NULL, null=True, blank=True)
    step_order = models.IntegerField(default=1)
    action_type = models.CharField(max_length=30)   # 'email' | 'linkedin'
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='sent')
    subject_sent = models.CharField(max_length=500, blank=True)
    body_sent = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'sdr_outreach_log'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action_type} — {self.status} ({self.enrollment})"


class SDRMeeting(models.Model):
    """Meeting booked with a lead after a positive reply — scheduling agent output."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('awaiting_approval', 'Awaiting Approval'),
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ]

    company_user = models.ForeignKey(
        'core.CompanyUser', on_delete=models.CASCADE, related_name='sdr_meetings'
    )
    lead = models.ForeignKey(SDRLead, on_delete=models.CASCADE, related_name='meetings')
    enrollment = models.ForeignKey(
        SDRCampaignEnrollment, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='meetings'
    )

    title = models.CharField(max_length=255, default='Discovery Call')
    notes = models.TextField(blank=True)
    reply_snippet = models.TextField(blank=True)   # the reply that triggered this
    scheduled_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(default=30)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    calendar_link = models.CharField(max_length=500, blank=True)

    # The Google Calendar event made for this call, and the time that event
    # stands at. core.google_calendar.follow moves or removes the event when
    # the call moves or is called off. Empty: no event (Google not connected).
    google_event_id = models.CharField(max_length=255, blank=True, default='')
    google_event_state = models.CharField(max_length=64, blank=True, default='')

    # Scheduling agent fields
    prep_notes = models.JSONField(default=dict, blank=True)          # AI-generated prep notes
    scheduling_email_sent_at = models.DateTimeField(null=True, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    # Timezone — IANA name of the lead's local timezone (e.g. "America/New_York")
    # Used to display scheduled_at in the lead's local time in emails and UI.
    lead_timezone = models.CharField(max_length=100, default='UTC', blank=True)

    # True for meetings a user created by hand (they have no enrollment).
    is_manual = models.BooleanField(default=False)

    # Public booking link — shared with the lead so they can self-schedule
    booking_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    # Lead approval flow — token used in yes/suggest-time links emailed to the lead
    approval_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    approval_proposed_at = models.DateTimeField(null=True, blank=True)  # when approval email was sent

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sdr_meeting'
        ordering = ['-created_at']

    def __str__(self):
        return f"Meeting with {self.lead.display_name} ({self.status})"


class SDRJobLock(models.Model):
    """Cross-process lock for scheduler jobs.

    Every web worker starts its own scheduler, so without this each job runs once
    per worker (duplicate reply handling, double token spend, the daily email
    re-sent on every restart). A job runs only if it can claim its row.
    """
    name = models.CharField(max_length=64, unique=True)
    locked_until = models.DateTimeField(default=timezone.now)
    last_run_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sdr_job_lock'

    def __str__(self):
        return f"{self.name} (last run {self.last_run_at})"


class SDRAgentSettings(models.Model):
    """Per-company-user API credentials for the SDR agent (Apollo, Apify, etc.)."""
    company_user = models.OneToOneField(
        'core.CompanyUser', on_delete=models.CASCADE, related_name='sdr_settings'
    )
    apollo_api_key = models.CharField(max_length=500, blank=True)
    apify_api_token = models.CharField(max_length=500, blank=True)
    apify_actor_id = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sdr_agent_settings'

    def __str__(self):
        return f"SDR settings for {self.company_user}"


class SDRLeadResearchJob(models.Model):
    """Tracks async lead-research jobs (Apollo search or AI generation)."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    company_user = models.ForeignKey('core.CompanyUser', on_delete=models.CASCADE)
    icp_profile = models.ForeignKey(
        'SDRIcpProfile', on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    source = models.CharField(max_length=20, default='ai_generated')  # 'apollo' | 'ai_generated'
    search_params = models.JSONField(default=dict)
    total_found = models.IntegerField(default=0)
    leads_created = models.IntegerField(default=0)
    leads_qualified = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'sdr_lead_research_job'
        ordering = ['-created_at']

    def __str__(self):
        return f"ResearchJob #{self.id} — {self.status} ({self.leads_created} leads)"

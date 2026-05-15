import uuid
from datetime import date as _date, timedelta as _timedelta

from django.db import models
from django.utils import timezone


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
    hot_threshold = models.IntegerField(default=70)   # score >= hot_threshold → Hot
    warm_threshold = models.IntegerField(default=40)  # score >= warm_threshold → Warm

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sdr_icp_profile'

    def __str__(self):
        return f"{self.company_user} — {self.name}"


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
    score_breakdown = models.JSONField(default=dict)             # {industry:28, job_title:30, ...}
    qualification_reasoning = models.TextField(blank=True)

    # Workflow
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='new')
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default='manual')

    qualified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sdr_lead'
        ordering = ['-score', '-created_at']

    def __str__(self):
        return f"{self.display_name} — {self.company_name} ({self.temperature or 'unscored'})"

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

    # Sender identity (used for email personalisation)
    sender_name = models.CharField(max_length=255, blank=True)
    sender_title = models.CharField(max_length=255, blank=True)
    sender_company = models.CharField(max_length=255, blank=True)

    # SMTP settings (per-campaign, self-contained)
    from_email = models.CharField(max_length=255, blank=True)
    smtp_host = models.CharField(max_length=255, blank=True)
    smtp_port = models.IntegerField(default=587)
    smtp_username = models.CharField(max_length=255, blank=True)
    smtp_password = models.CharField(max_length=500, blank=True)
    smtp_use_tls = models.BooleanField(default=True)

    # IMAP settings for reply detection (falls back to env EMAIL_HOST_USER/PASSWORD)
    imap_host = models.CharField(max_length=255, blank=True)
    imap_port = models.IntegerField(default=993)

    # Scheduling / handoff
    calendar_link = models.CharField(max_length=500, blank=True)  # Calendly / calendar URL

    # Auto-run scheduling (Celery)
    start_date = models.DateField(null=True, blank=True)        # auto-activates when reached
    end_date = models.DateField(null=True, blank=True)          # informational; auto-derived
    auto_check_replies = models.BooleanField(default=True)       # poll IMAP every 5 min
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

    def save(self, *args, **kwargs):
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

    enrolled_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sdr_campaign_enrollment'
        unique_together = ['campaign', 'lead']
        ordering = ['-enrolled_at']

    def __str__(self):
        return f"{self.lead.display_name} → {self.campaign.name} ({self.status})"


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

    # Scheduling agent fields
    prep_notes = models.JSONField(default=dict, blank=True)          # AI-generated prep notes
    scheduling_email_sent_at = models.DateTimeField(null=True, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    # Public booking link — shared with the lead so they can self-schedule
    booking_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sdr_meeting'
        ordering = ['-created_at']

    def __str__(self):
        return f"Meeting with {self.lead.display_name} ({self.status})"


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

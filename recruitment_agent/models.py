import re as _re

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


def _cv_upload_to(instance, filename):
    """S3 path: cvs/{company_id}/{job_id}/{safe_filename}"""
    safe = _re.sub(r'[^A-Za-z0-9._-]+', '_', filename)
    try:
        company_id = instance.job.company_id or 'unknown'
        job_id = instance.job_id or 'unknown'
    except Exception:
        company_id = 'unknown'
        job_id = 'unknown'
    return f'cvs/{company_id}/{job_id}/{safe}'


class RecruiterEmailSettings(models.Model):
    """
    Recruiter email timing preferences.
    Each recruiter can set their own preferences for follow-up and reminder emails.
    """
    recruiter = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name='recruiter_email_settings')
    company_user = models.OneToOneField('core.CompanyUser', on_delete=models.CASCADE, null=True, blank=True, related_name='recruiter_email_settings_company')
    
    # Follow-up email settings for PENDING interviews
    followup_delay_hours = models.FloatField(
        default=48,
        help_text="Hours to wait before sending first follow-up email (e.g., 0.1 = 6 minutes, 1 = 1 hour)"
    )
    min_hours_between_followups = models.FloatField(
        default=24,
        help_text="Minimum hours between follow-up emails (e.g., 0.1 = 6 minutes, 1 = 1 hour)"
    )
    max_followup_emails = models.IntegerField(
        default=3,
        help_text="Maximum number of follow-up emails to send"
    )
    
    # Reminder email settings for SCHEDULED interviews
    reminder_hours_before = models.FloatField(
        default=24,
        help_text="Hours before scheduled interview to send reminder (e.g., 0.5 = 30 minutes, 1 = 1 hour)"
    )
    
    # Additional settings
    auto_send_followups = models.BooleanField(
        default=True,
        help_text="Automatically send follow-up emails (if False, emails must be sent manually)"
    )
    auto_send_reminders = models.BooleanField(
        default=True,
        help_text="Automatically send pre-interview reminders (if False, reminders must be sent manually)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'ppp_recruitment_agent_recruiteremailsettings'
        verbose_name = 'Recruiter Email Settings'
        verbose_name_plural = 'Recruiter Email Settings'
    
    def __str__(self):
        return f"Email Settings for {self.recruiter.username}"


class RecruiterQualificationSettings(models.Model):
    """
    Recruiter qualification/decision threshold settings.
    Each company can set custom thresholds for INTERVIEW/HOLD/REJECT decisions.
    """
    recruiter = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name='recruiter_qualification_settings')
    company_user = models.OneToOneField('core.CompanyUser', on_delete=models.CASCADE, null=True, blank=True, related_name='recruiter_qualification_settings_company')
    
    # Decision thresholds (0-100)
    interview_threshold = models.IntegerField(
        default=65,
        help_text="Minimum confidence score (0-100) to mark candidate as INTERVIEW. Default: 65"
    )
    hold_threshold = models.IntegerField(
        default=45,
        help_text="Minimum confidence score (0-100) to mark candidate as HOLD. Default: 45. Scores below this are REJECTED."
    )
    
    # Use custom thresholds flag
    use_custom_thresholds = models.BooleanField(
        default=False,
        help_text="If True, use custom thresholds. If False, use default values (65 for INTERVIEW, 45 for HOLD)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'ppp_recruitment_agent_recruiterqualificationsettings'
        verbose_name = 'Recruiter Qualification Settings'
        verbose_name_plural = 'Recruiter Qualification Settings'
    
    def __str__(self):
        return f"Qualification Settings for {self.recruiter.username if self.recruiter else 'Company User'}"


class RecruiterInterviewSettings(models.Model):
    """
    Recruiter interview scheduling preferences.
    Each job can have its own interview scheduling settings:
    - Date range for scheduling interviews (from date to date)
    - Time range for daily interview hours (start time to end time)
    - Interview time gap (minutes between slots)
    - Separate time slots for each job
    """
    recruiter = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='recruiter_interview_settings')
    company_user = models.ForeignKey('core.CompanyUser', on_delete=models.CASCADE, null=True, blank=True, related_name='recruiter_interview_settings_company')
    job = models.ForeignKey('JobDescription', on_delete=models.CASCADE, null=True, blank=True, related_name='interview_settings', help_text='Job description this setting belongs to. If null, applies to all jobs (backward compatibility)')
    
    # Date range for scheduling interviews
    schedule_from_date = models.DateField(
        null=True,
        blank=True,
        help_text="Start date from which interviews can be scheduled (leave empty to start from today)"
    )
    schedule_to_date = models.DateField(
        null=True,
        blank=True,
        help_text="End date until which interviews can be scheduled (leave empty for no end date)"
    )
    
    # Time range for daily interview hours
    start_time = models.TimeField(
        default='09:00',
        help_text="Start time of day for interviews (e.g., 09:00 for 9 AM)"
    )
    end_time = models.TimeField(
        default='17:00',
        help_text="End time of day for interviews (e.g., 17:00 for 5 PM)"
    )
    
    # Interview time gap
    interview_time_gap = models.IntegerField(
        default=30,
        validators=[MinValueValidator(15), MaxValueValidator(480)],
        help_text="Time gap between interview slots in minutes (15–480)"
    )
    
    # Default interview type for this job (candidates get this in invitation email)
    default_interview_type = models.CharField(
        max_length=10,
        choices=[('ONLINE', 'Online'), ('ONSITE', 'Onsite')],
        default='ONLINE',
        help_text='Interview type for this job. Sent to candidates in invitation email.'
    )
    
    # Generated time slots stored as JSON
    time_slots_json = models.JSONField(
        default=list,
        blank=True,
        help_text="Generated time slots stored as JSON array. Format: [{'date': 'YYYY-MM-DD', 'time': 'HH:MM', 'datetime': 'YYYY-MM-DDTHH:MM'}, ...]"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'ppp_recruitment_agent_recruiterinterviewsettings'
        verbose_name = 'Recruiter Interview Settings'
        verbose_name_plural = 'Recruiter Interview Settings'
        constraints = [
            models.UniqueConstraint(fields=['company_user', 'job'], name='unique_company_user_job_settings', condition=models.Q(job__isnull=False)),
            models.UniqueConstraint(fields=['company_user'], name='unique_company_user_no_job_settings', condition=models.Q(job__isnull=True)),
            models.UniqueConstraint(fields=['recruiter', 'job'], name='unique_recruiter_job_settings', condition=models.Q(job__isnull=False)),
        ]
        indexes = [
            models.Index(fields=['company_user', 'job']),
            models.Index(fields=['recruiter', 'job']),
        ]

    def clean(self):
        errors = {}
        if self.schedule_from_date and self.schedule_to_date:
            if self.schedule_from_date > self.schedule_to_date:
                errors['schedule_to_date'] = 'End date must be after start date.'
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                errors['end_time'] = 'End time must be after start time.'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        if self.job:
            return f"Interview Settings for {self.job.title}"
        return f"Interview Settings for {self.recruiter.username if self.recruiter else 'Company User'}"


class JobDescription(models.Model):
    """
    Model to store job descriptions for recruitment positions.
    Recruiters can manage multiple job descriptions for different positions.
    """
    TYPE_CHOICES = [
        ('Full-time', 'Full-time'),
        ('Part-time', 'Part-time'),
        ('Contract', 'Contract'),
        ('Internship', 'Internship'),
    ]
    
    title = models.CharField(max_length=255, help_text="Job title/position name")
    description = models.TextField(help_text="Full job description text")
    keywords_json = models.TextField(null=True, blank=True, help_text="Parsed keywords and requirements from JobDescriptionParserAgent (JSON)")
    
    # Additional fields from payPerProject
    location = models.CharField(max_length=255, blank=True, null=True)
    department = models.CharField(max_length=255, blank=True, null=True)
    type = models.CharField(max_length=50, choices=TYPE_CHOICES, default='Full-time')
    requirements = models.TextField(blank=True, null=True, help_text="Job requirements")
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_job_descriptions')
    company = models.ForeignKey('core.Company', on_delete=models.SET_NULL, null=True, blank=True, related_name='job_positions')
    company_user = models.ForeignKey('core.CompanyUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_jobs', help_text='Company user who created this job')
    is_active = models.BooleanField(default=True, help_text="Whether this job description is currently active/being used")
    application_open_date = models.DateField(null=True, blank=True, help_text="Date from which applications are accepted")
    application_close_date = models.DateField(null=True, blank=True, help_text="Deadline date after which applications are no longer accepted")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ppp_recruitment_agent_jobdescription'
        ordering = ['-created_at']
        verbose_name = 'Job Description'
        verbose_name_plural = 'Job Descriptions'
        indexes = [
            models.Index(fields=['is_active', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} (ID: {self.id})"


class CVRecord(models.Model):
    """
    Django model for parsed CV data and processing results.
    Table: dbo.ppp_recruitment_agent_cvrecord (aligned with ppp_ prefix).
    """
    file_name = models.CharField(max_length=512)
    s3_key = models.CharField(max_length=1024, null=True, blank=True, help_text="S3 object key for the original CV file (cvs/{company_id}/{job_id}/{filename})")
    parsed_json = models.TextField(help_text="Structured CV data from CVParserAgent")
    insights_json = models.TextField(null=True, blank=True, help_text="Summarization results from SummarizationAgent")
    role_fit_score = models.IntegerField(null=True, blank=True, help_text="Role fit score 0-100")
    rank = models.IntegerField(null=True, blank=True, help_text="Final ranking position")
    enriched_json = models.TextField(null=True, blank=True, help_text="Enrichment results from LeadResearchEnrichmentAgent")
    qualification_json = models.TextField(null=True, blank=True, help_text="Qualification results from LeadQualificationAgent")
    qualification_decision = models.CharField(max_length=32, null=True, blank=True, help_text="INTERVIEW/HOLD/REJECT")
    qualification_confidence = models.IntegerField(null=True, blank=True, help_text="Confidence score 0-100")
    qualification_priority = models.CharField(max_length=16, null=True, blank=True, help_text="HIGH/MEDIUM/LOW")
    
    # Link to job description (optional)
    job_description = models.ForeignKey(JobDescription, on_delete=models.SET_NULL, null=True, blank=True, related_name='cv_records', db_index=True)

    # Link to the public JobApplication this CV came from (null for manually uploaded CVs)
    job_application = models.OneToOneField(
        'JobApplication',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cv_record',
    )

    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'ppp_recruitment_agent_cvrecord'
        ordering = ['-created_at']
        verbose_name = 'CV Record'
        verbose_name_plural = 'CV Records'
        indexes = [
            models.Index(fields=['qualification_decision', '-created_at']),
            models.Index(fields=['job_description', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.file_name} (ID: {self.id})"


class JobApplication(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('reviewed', 'Reviewed'),
        ('shortlisted', 'Shortlisted'),
        ('rejected', 'Rejected'),
    ]

    job = models.ForeignKey(JobDescription, on_delete=models.CASCADE, related_name='applications')
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    current_location = models.CharField(max_length=255, blank=True, null=True)
    salary_expectation = models.CharField(max_length=100, blank=True, null=True)
    education = models.TextField(blank=True, null=True)
    previous_company = models.CharField(max_length=255, blank=True, null=True)
    previous_salary = models.CharField(max_length=100, blank=True, null=True)
    linkedin_url = models.URLField(max_length=500, blank=True, null=True)
    github_url = models.URLField(max_length=500, blank=True, null=True)
    other_links = models.TextField(blank=True, null=True)
    cover_letter = models.TextField(blank=True, null=True)
    cv_file = models.FileField(upload_to=_cv_upload_to, null=True, blank=True)
    cv_file_name = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    applied_at = models.DateTimeField(auto_now_add=True)
    access_token = models.CharField(max_length=64, unique=True, blank=True, null=True)

    class Meta:
        db_table = 'ppp_recruitment_job_applications'
        constraints = [
            models.UniqueConstraint(fields=['job', 'email'], name='unique_job_app_email'),
            models.UniqueConstraint(fields=['job', 'phone'], name='unique_job_app_phone'),
        ]
        ordering = ['-applied_at']

    def __str__(self):
        return f"{self.first_name} {self.last_name} → {self.job.title}"


class Interview(models.Model):
    """
    Model to store interview scheduling information.
    Created after a candidate is approved for interview.
    """
    INTERVIEW_STATUS_CHOICES = [
        ('PENDING', 'Pending - Awaiting candidate response'),
        ('SCHEDULED', 'Scheduled - Interview confirmed'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
        ('RESCHEDULED', 'Rescheduled'),
    ]
    
    INTERVIEW_TYPE_CHOICES = [
        ('ONLINE', 'Online'),
        ('ONSITE', 'Onsite'),
    ]
    
    # Candidate information
    candidate_name = models.CharField(max_length=255)
    candidate_email = models.EmailField()
    candidate_phone = models.CharField(max_length=50, null=True, blank=True)
    
    # Job information
    job_role = models.CharField(max_length=255)
    interview_type = models.CharField(max_length=10, choices=INTERVIEW_TYPE_CHOICES, default='ONLINE')
    
    # Interview details
    status = models.CharField(max_length=20, choices=INTERVIEW_STATUS_CHOICES, default='PENDING')
    outcome = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        help_text='Decision after interview (when status is COMPLETED)',
        choices=[
            ('', 'Not set'),
            ('ONSITE_INTERVIEW', 'Onsite Interview'),
            ('HIRED', 'Hired'),
            ('PASSED', 'Passed'),
            ('REJECTED', 'Rejected'),
        ],
    )
    scheduled_datetime = models.DateTimeField(null=True, blank=True)
    selected_slot = models.CharField(max_length=255, null=True, blank=True, help_text="The time slot selected by candidate")
    
    # Available slots (stored as JSON)
    available_slots_json = models.TextField(help_text="JSON array of available time slots offered to candidate")
    
    # Unique token for candidate to access slot selection page
    confirmation_token = models.CharField(max_length=64, unique=True, null=True, blank=True, help_text="Unique token for candidate slot selection")

    # Google Meet link auto-generated at slot confirmation
    meeting_link = models.URLField(max_length=500, null=True, blank=True, help_text="Google Meet link generated when candidate confirms their slot")
    
    # Related CV record (optional)
    cv_record = models.ForeignKey(CVRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name='interviews')
    
    # Recruiter information
    recruiter = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='scheduled_interviews')
    company_user = models.ForeignKey('core.CompanyUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='scheduled_interviews_company')
    
    # Recruiter Email Timing Preferences (configurable per interview, defaults from RecruiterEmailSettings)
    followup_delay_hours = models.FloatField(default=48, help_text="Hours to wait before sending first follow-up email (e.g., 0.1 = 6 minutes)")
    reminder_hours_before = models.FloatField(default=24, help_text="Hours before scheduled interview to send reminder (e.g., 0.5 = 30 minutes)")
    max_followup_emails = models.IntegerField(default=3, help_text="Maximum number of follow-up emails to send")
    min_hours_between_followups = models.FloatField(default=24, help_text="Minimum hours between follow-up emails (e.g., 0.1 = 6 minutes)")
    
    # Timestamps
    invitation_sent_at = models.DateTimeField(null=True, blank=True)
    confirmation_sent_at = models.DateTimeField(null=True, blank=True)
    last_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    last_followup_sent_at = models.DateTimeField(null=True, blank=True, help_text="Last time a follow-up email was sent for unconfirmed interview")
    pre_interview_reminder_sent_at = models.DateTimeField(null=True, blank=True, help_text="When the pre-interview reminder was sent")
    followup_count = models.IntegerField(default=0, help_text="Number of follow-up emails sent for unconfirmed interview")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Additional notes
    notes = models.TextField(null=True, blank=True)

    # Post-interview feedback
    feedback_rating = models.IntegerField(null=True, blank=True, help_text="Interviewer rating 1-5")
    feedback_notes = models.TextField(null=True, blank=True, help_text="General feedback notes")
    feedback_strengths = models.TextField(null=True, blank=True, help_text="Candidate strengths observed")
    feedback_improvements = models.TextField(null=True, blank=True, help_text="Areas for improvement")
    feedback_submitted_at = models.DateTimeField(null=True, blank=True, help_text="When interviewer submitted feedback")

    class Meta:
        db_table = 'ppp_recruitment_agent_interview'
        ordering = ['-created_at']
        verbose_name = 'Interview'
        verbose_name_plural = 'Interviews'
        indexes = [
            models.Index(fields=['status', 'scheduled_datetime']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['candidate_email', 'status']),
            models.Index(fields=['company_user', 'status']),
        ]
    
    def __str__(self):
        return f"Interview: {self.candidate_name} - {self.job_role} ({self.status})"
    
    def get_recruiter_settings(self):
        """Get recruiter email settings, with defaults if not set"""
        if self.recruiter:
            try:
                return self.recruiter.recruiter_email_settings
            except RecruiterEmailSettings.DoesNotExist:
                # Return default settings object
                return RecruiterEmailSettings(
                    recruiter=self.recruiter,
                    followup_delay_hours=48,
                    reminder_hours_before=24,
                    max_followup_emails=3,
                    min_hours_between_followups=24
                )
        # Return default settings if no recruiter
        return RecruiterEmailSettings(
            followup_delay_hours=48,
            reminder_hours_before=24,
            max_followup_emails=3,
            min_hours_between_followups=24
        )
    
    def get_followup_delay_hours(self):
        """Get follow-up delay hours from recruiter settings or interview-specific setting"""
        if self.followup_delay_hours != 48:  # If custom value set
            return self.followup_delay_hours
        settings = self.get_recruiter_settings()
        return settings.followup_delay_hours
    
    def get_reminder_hours_before(self):
        """Get reminder hours before from recruiter settings or interview-specific setting"""
        if self.reminder_hours_before != 24:  # If custom value set
            return self.reminder_hours_before
        settings = self.get_recruiter_settings()
        return settings.reminder_hours_before
    
    def get_max_followup_emails(self):
        """Get max follow-up emails from recruiter settings or interview-specific setting"""
        if self.max_followup_emails != 3:  # If custom value set
            return self.max_followup_emails
        settings = self.get_recruiter_settings()
        return settings.max_followup_emails
    
    def get_min_hours_between_followups(self):
        """Get min hours between follow-ups from recruiter settings or interview-specific setting"""
        if self.min_hours_between_followups != 24:  # If custom value set
            return self.min_hours_between_followups
        settings = self.get_recruiter_settings()
        return settings.min_hours_between_followups

    def is_job_schedule_expired(self):
        """Check if the job's interview scheduling date range has passed.
        Returns True if schedule_to_date is set and today is past that date.
        """
        from datetime import date
        job = None
        try:
            if self.cv_record_id and self.cv_record and self.cv_record.job_description_id:
                job = self.cv_record.job_description
        except CVRecord.DoesNotExist:
            pass

        if not job:
            return False

        # Check job-specific settings first, then fallback to general settings
        settings = None
        if self.company_user:
            settings = RecruiterInterviewSettings.objects.filter(
                company_user=self.company_user, job=job
            ).first()
            if not settings:
                settings = RecruiterInterviewSettings.objects.filter(
                    company_user=self.company_user, job__isnull=True
                ).first()

        if not settings and self.recruiter:
            settings = RecruiterInterviewSettings.objects.filter(
                recruiter=self.recruiter, job=job
            ).first()
            if not settings:
                settings = RecruiterInterviewSettings.objects.filter(
                    recruiter=self.recruiter, job__isnull=True
                ).first()

        if settings and settings.schedule_to_date:
            return date.today() > settings.schedule_to_date

        return False


class RecruitmentQAChat(models.Model):
    """Knowledge Q&A chat sessions for recruiters. Each chat contains multiple messages."""
    company_user = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='recruitment_qa_chats',
        help_text='Company user who owns this chat',
    )
    title = models.CharField(max_length=255, default='Chat', help_text='Chat title (e.g. first question snippet)')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ppp_recruitment_agent_recruitmentqachat'
        ordering = ['-updated_at']
        verbose_name = 'Recruitment QA Chat'
        verbose_name_plural = 'Recruitment QA Chats'

    def __str__(self):
        return f"QA Chat: {self.title[:40]}... ({self.id})"


class RecruitmentQAChatMessage(models.Model):
    """Individual messages in a Recruitment QA chat."""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]
    chat = models.ForeignKey(
        RecruitmentQAChat,
        on_delete=models.CASCADE,
        related_name='messages',
        help_text='Chat this message belongs to',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField(help_text='Message content')
    response_data = models.JSONField(
        null=True,
        blank=True,
        help_text='For assistant: full API response { answer, insights }',
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'ppp_recruitment_agent_recruitmentqachatmessage'
        ordering = ['created_at']
        verbose_name = 'Recruitment QA Chat Message'
        verbose_name_plural = 'Recruitment QA Chat Messages'

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."


class SavedGraphPrompt(models.Model):
    """
    Model to store saved AI graph generation prompts.
    Users can save, favorite, and reuse prompts for generating visualizations.
    """
    CHART_TYPE_CHOICES = [
        ('bar', 'Bar Chart'),
        ('pie', 'Pie Chart'),
        ('line', 'Line Chart'),
        ('area', 'Area Chart'),
        ('scatter', 'Scatter Plot'),
        ('heatmap', 'Heat Map'),
    ]
    
    company_user = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='saved_graph_prompts',
        help_text='Company user who saved this prompt',
    )
    title = models.CharField(max_length=255, help_text='User-friendly title for the prompt')
    prompt = models.TextField(help_text='The natural language prompt for graph generation')
    chart_type = models.CharField(
        max_length=20,
        choices=CHART_TYPE_CHOICES,
        default='bar',
        help_text='Type of chart this prompt generates'
    )
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text='Tags for categorizing and searching prompts'
    )
    is_favorite = models.BooleanField(
        default=False,
        help_text='Whether this prompt is marked as favorite'
    )
    run_count = models.IntegerField(
        default=0,
        help_text='Number of times this prompt has been run'
    )
    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Last time this prompt was executed'
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'ppp_recruitment_agent_savedgraphprompt'
        ordering = ['-is_favorite', '-updated_at']
        verbose_name = 'Saved Graph Prompt'
        verbose_name_plural = 'Saved Graph Prompts'
        indexes = [
            models.Index(fields=['company_user', 'is_favorite']),
            models.Index(fields=['company_user', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.chart_type})"


class CVRecordDecisionLog(models.Model):
    """Audit trail of every decision change on a CV record."""
    SOURCE_CHOICES = [
        ('AI', 'AI Processing'),
        ('Manual', 'Manual Override'),
    ]
    cv_record = models.ForeignKey(CVRecord, on_delete=models.CASCADE, related_name='decision_logs')
    from_decision = models.CharField(max_length=32, null=True, blank=True)
    to_decision = models.CharField(max_length=32)
    changed_by = models.CharField(max_length=255, null=True, blank=True, help_text='Email/name of the user who made the change')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='Manual')
    changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'ppp_recruitment_agent_cvrecorddecisionlog'
        ordering = ['changed_at']
        verbose_name = 'CV Record Decision Log'
        verbose_name_plural = 'CV Record Decision Logs'

    def __str__(self):
        return f"CVRecord#{self.cv_record_id}: {self.from_decision} → {self.to_decision}"


class CareerApplication(models.Model):
    """Job applications - maps to ppp_career_applications"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('reviewing', 'Reviewing'),
        ('interview', 'Interview'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]
    
    position_title = models.CharField(max_length=255)
    applicant_name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True, null=True)
    resume_path = models.CharField(max_length=500, blank=True, null=True)
    cover_letter = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    position = models.ForeignKey(JobDescription, on_delete=models.SET_NULL, null=True, blank=True, related_name='career_applications')
    application_token = models.CharField(max_length=255, unique=True, blank=True, null=True)
    company = models.ForeignKey('core.Company', on_delete=models.SET_NULL, null=True, blank=True, related_name='career_applications')
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'ppp_recruitment_agent_careerapplication'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.applicant_name} - {self.position_title}"
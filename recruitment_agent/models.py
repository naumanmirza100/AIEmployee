from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class RecruiterEmailSettings(models.Model):
    """
    Recruiter email timing preferences.
    Each recruiter can set their own preferences for follow-up and reminder emails.
    """
    recruiter = models.OneToOneField(User, on_delete=models.CASCADE, related_name='recruiter_email_settings')
    
    # Follow-up email settings for PENDING interviews
    followup_delay_hours = models.IntegerField(
        default=48,
        help_text="Hours to wait before sending first follow-up email for unconfirmed interviews"
    )
    min_hours_between_followups = models.IntegerField(
        default=24,
        help_text="Minimum hours between follow-up emails"
    )
    max_followup_emails = models.IntegerField(
        default=3,
        help_text="Maximum number of follow-up emails to send"
    )
    
    # Reminder email settings for SCHEDULED interviews
    reminder_hours_before = models.IntegerField(
        default=24,
        help_text="Hours before scheduled interview to send reminder email"
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
        verbose_name = 'Recruiter Email Settings'
        verbose_name_plural = 'Recruiter Email Settings'
    
    def __str__(self):
        return f"Email Settings for {self.recruiter.username}"


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
    is_active = models.BooleanField(default=True, help_text="Whether this job description is currently active/being used")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
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
    Django model equivalent to dbo.ppp_cv_records table from RecruitmentAI.
    Stores parsed CV data and all processing results.
    """
    file_name = models.CharField(max_length=512)
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
    job_description = models.ForeignKey(JobDescription, on_delete=models.SET_NULL, null=True, blank=True, related_name='cv_records')
    
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'ppp_cv_records'  # Use same table name as original
        ordering = ['-created_at']
        verbose_name = 'CV Record'
        verbose_name_plural = 'CV Records'
    
    def __str__(self):
        return f"{self.file_name} (ID: {self.id})"


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
    scheduled_datetime = models.DateTimeField(null=True, blank=True)
    selected_slot = models.CharField(max_length=255, null=True, blank=True, help_text="The time slot selected by candidate")
    
    # Available slots (stored as JSON)
    available_slots_json = models.TextField(help_text="JSON array of available time slots offered to candidate")
    
    # Unique token for candidate to access slot selection page
    confirmation_token = models.CharField(max_length=64, unique=True, null=True, blank=True, help_text="Unique token for candidate slot selection")
    
    # Related CV record (optional)
    cv_record = models.ForeignKey(CVRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name='interviews')
    
    # Recruiter information
    recruiter = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='scheduled_interviews')
    
    # Recruiter Email Timing Preferences (configurable per interview, defaults from RecruiterEmailSettings)
    followup_delay_hours = models.IntegerField(default=48, help_text="Hours to wait before sending first follow-up email for PENDING interviews")
    reminder_hours_before = models.IntegerField(default=24, help_text="Hours before scheduled interview to send reminder email")
    max_followup_emails = models.IntegerField(default=3, help_text="Maximum number of follow-up emails to send")
    min_hours_between_followups = models.IntegerField(default=24, help_text="Minimum hours between follow-up emails")
    
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
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Interview'
        verbose_name_plural = 'Interviews'
        indexes = [
            models.Index(fields=['status', 'scheduled_datetime']),
            models.Index(fields=['candidate_email']),
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
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.applicant_name} - {self.position_title}"

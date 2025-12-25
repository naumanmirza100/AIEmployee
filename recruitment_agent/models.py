from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class JobDescription(models.Model):
    """
    Model to store job descriptions for recruitment positions.
    Recruiters can manage multiple job descriptions for different positions.
    """
    title = models.CharField(max_length=255, help_text="Job title/position name")
    description = models.TextField(help_text="Full job description text")
    keywords_json = models.TextField(null=True, blank=True, help_text="Parsed keywords and requirements from JobDescriptionParserAgent (JSON)")
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_job_descriptions')
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
    
    # Timestamps
    invitation_sent_at = models.DateTimeField(null=True, blank=True)
    confirmation_sent_at = models.DateTimeField(null=True, blank=True)
    last_reminder_sent_at = models.DateTimeField(null=True, blank=True)
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

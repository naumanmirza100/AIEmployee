from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import m2m_changed, pre_save
from django.dispatch import receiver
import json
import logging

logger = logging.getLogger(__name__)


class Lead(models.Model):
    """Lead Model for Marketing Campaigns"""
    STATUS_CHOICES = [
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('qualified', 'Qualified'),
        ('converted', 'Converted'),
        ('lost', 'Lost'),
    ]
    
    email = models.EmailField()
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    company = models.CharField(max_length=200, blank=True)
    job_title = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    notes = models.TextField(blank=True)
    source = models.CharField(max_length=100, blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='marketing_leads')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = [('email', 'owner')]
    
    def __str__(self):
        return f"{self.email} - {self.get_status_display()}"


class Campaign(models.Model):
    """Marketing Campaign Model - Email Only"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    campaign_type = models.CharField(max_length=20, default='email')  # Email only
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    actual_spend = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # User-friendly fields instead of JSON
    # Goals fields
    target_revenue = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Target revenue in dollars")
    target_leads = models.IntegerField(null=True, blank=True, help_text="Target number of leads to achieve (goal - you need to upload leads via CSV)")
    target_conversions = models.IntegerField(null=True, blank=True, help_text="Target number of conversions")
    
    # Target Audience fields
    age_range = models.CharField(max_length=50, blank=True, help_text="e.g., 25-45")
    interests = models.CharField(max_length=500, blank=True, help_text="Comma-separated interests")
    location = models.CharField(max_length=200, blank=True, help_text="Target location/region")
    industry = models.CharField(max_length=200, blank=True, help_text="Target industry (e.g., Technology, Healthcare)")
    company_size = models.CharField(max_length=100, blank=True, help_text="Target company size (e.g., 1-50, 51-200, 201-1000)")
    language = models.CharField(max_length=100, blank=True, help_text="Target language (e.g., English, Spanish)")
    
    # Keep JSON fields for backward compatibility and flexible data
    target_audience = models.JSONField(default=dict, blank=True)
    goals = models.JSONField(default=dict, blank=True)
    channels = models.JSONField(default=list, blank=True)
    
    # Leads relationship
    leads = models.ManyToManyField('Lead', blank=True, related_name='campaigns')
    
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='marketing_campaigns')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name
    
    def get_roi(self):
        """Calculate ROI if revenue data is available"""
        if self.target_revenue and self.actual_spend > 0:
            return ((float(self.target_revenue) - float(self.actual_spend)) / float(self.actual_spend)) * 100
        elif 'revenue' in self.goals and self.actual_spend > 0:
            revenue = float(self.goals.get('revenue', 0))
            return ((revenue - float(self.actual_spend)) / float(self.actual_spend)) * 100
        return None
    
    def save(self, *args, **kwargs):
        """Override save to automatically activate sequences when campaign becomes active"""
        is_new = self.pk is None
        old_status = None
        
        # Check if status is being changed to 'active' (for existing campaigns)
        if not is_new:
            try:
                old_campaign = Campaign.objects.get(pk=self.pk)
                old_status = old_campaign.status
            except Campaign.DoesNotExist:
                pass  # Shouldn't happen, but handle gracefully
        
        # Call parent save first (so self.pk exists and relationships work)
        super().save(*args, **kwargs)
        
        # If status is 'active' (either new campaign or status changed to active), activate all sequences
        if self.status == 'active':
            if is_new or (old_status and old_status != 'active'):
                sequences_updated = self.email_sequences.update(is_active=True)
                if sequences_updated > 0:
                    if is_new:
                        logger.info(f"New campaign '{self.name}' created as active. {sequences_updated} sequence(s) automatically activated.")
                    else:
                        logger.info(f"Campaign '{self.name}' status changed to active. {sequences_updated} sequence(s) automatically activated.")


class MarketResearch(models.Model):
    """Market Research Findings Model"""
    RESEARCH_TYPE_CHOICES = [
        ('market_trend', 'Market Trend'),
        ('competitor', 'Competitor Analysis'),
        ('customer_behavior', 'Customer Behavior'),
        ('opportunity', 'Opportunity Analysis'),
        ('threat', 'Threat Analysis'),
    ]
    
    research_type = models.CharField(max_length=30, choices=RESEARCH_TYPE_CHOICES)
    topic = models.CharField(max_length=200)
    findings = models.JSONField(default=dict, blank=True)  # Structured findings
    insights = models.TextField(blank=True)  # AI-generated insights
    source_urls = models.JSONField(default=list, blank=True)  # List of source URLs
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='market_research')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_research_type_display()}: {self.topic}"


class CampaignPerformance(models.Model):
    """Campaign Performance Metrics Model"""
    METRIC_TYPE_CHOICES = [
        ('impressions', 'Impressions'),
        ('clicks', 'Clicks'),
        ('conversions', 'Conversions'),
        ('engagement', 'Engagement Rate'),
        ('roi', 'ROI'),
        ('cac', 'Customer Acquisition Cost'),
        ('ltv', 'Lifetime Value'),
        ('revenue', 'Revenue'),
        ('open_rate', 'Open Rate'),
        ('click_through_rate', 'Click-Through Rate'),
    ]
    
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='performance_metrics')
    metric_name = models.CharField(max_length=30, choices=METRIC_TYPE_CHOICES)
    metric_value = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.now)
    channel = models.CharField(max_length=50, blank=True)  # email, social, paid, etc.
    target_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    actual_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date', '-created_at']
        unique_together = ['campaign', 'metric_name', 'date', 'channel']
    
    def __str__(self):
        return f"{self.campaign.name} - {self.get_metric_name_display()} ({self.date})"


class MarketingDocument(models.Model):
    """Marketing Document Model"""
    DOCUMENT_TYPE_CHOICES = [
        ('strategy', 'Marketing Strategy'),
        ('proposal', 'Campaign Proposal'),
        ('report', 'Performance Report'),
        ('brief', 'Campaign Brief'),
        ('presentation', 'Presentation'),
        ('analysis', 'Market Analysis'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ]
    
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    content = models.TextField()  # Markdown or structured content
    file_path = models.CharField(max_length=500, blank=True)  # Optional file path
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    campaign = models.ForeignKey(Campaign, on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='marketing_documents')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_document_type_display()}: {self.title}"


class NotificationRule(models.Model):
    """Proactive Notification Rules Model"""
    RULE_TYPE_CHOICES = [
        ('performance_alert', 'Performance Alert'),
        ('opportunity', 'Opportunity Alert'),
        ('anomaly', 'Anomaly Detection'),
        ('milestone', 'Milestone Reached'),
        ('budget', 'Budget Alert'),
    ]
    
    rule_type = models.CharField(max_length=20, choices=RULE_TYPE_CHOICES)
    name = models.CharField(max_length=200)
    trigger_condition = models.JSONField(default=dict)  # Flexible condition structure
    threshold_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notification_message = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, null=True, blank=True, related_name='notification_rules')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notification_rules', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_triggered = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_rule_type_display()}: {self.name}"


class MarketingNotification(models.Model):
    """Marketing Proactive Notifications Model"""
    NOTIFICATION_TYPE_CHOICES = [
        ('performance_alert', 'Performance Alert'),
        ('opportunity', 'Opportunity Alert'),
        ('anomaly', 'Anomaly Detection'),
        ('milestone', 'Milestone Reached'),
        ('budget', 'Budget Alert'),
        ('campaign_status', 'Campaign Status Change'),
        ('email_delivery', 'Email Delivery Issue'),
        ('engagement', 'Engagement Alert'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='marketing_notifications')
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications')
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPE_CHOICES)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    title = models.CharField(max_length=200)
    message = models.TextField()
    action_required = models.BooleanField(default=False)
    action_url = models.CharField(max_length=500, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)  # Store additional data (metrics, thresholds, etc.)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['campaign', 'notification_type']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.user.username}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        from django.utils import timezone
        self.is_read = True
        self.read_at = timezone.now()
        self.save()


class EmailTemplate(models.Model):
    """Email Template for Campaigns"""
    EMAIL_TYPE_CHOICES = [
        ('initial', 'Initial Campaign Email'),
        ('followup', 'Follow-up Email'),
        ('test', 'Test Email'),
    ]
    
    AB_TEST_VARIANT_CHOICES = [
        ('A', 'Variant A'),
        ('B', 'Variant B'),
    ]
    
    name = models.CharField(max_length=200)
    email_type = models.CharField(max_length=20, choices=EMAIL_TYPE_CHOICES, default='initial')
    subject = models.CharField(max_length=300)
    html_content = models.TextField(help_text='HTML email content')
    text_content = models.TextField(blank=True, help_text='Plain text version')
    
    # A/B Testing
    is_ab_test = models.BooleanField(default=False, help_text='Is this part of an A/B test?')
    ab_test_variant = models.CharField(max_length=1, choices=AB_TEST_VARIANT_CHOICES, blank=True, 
                                      help_text='A or B variant for A/B testing')
    
    # Sequence Management
    followup_sequence_number = models.IntegerField(default=0, 
                                                   help_text='Sequence number for follow-up emails (0 = initial, 1 = first follow-up, etc.)')
    followup_delay_days = models.IntegerField(default=3, 
                                             help_text='Days to wait before sending this follow-up')
    
    # Spam Prevention
    spam_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                                    help_text='Spam score (0-100, lower is better)')
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Relationships
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='email_templates')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['campaign', 'followup_sequence_number', 'created_at']
    
    def __str__(self):
        return f"{self.name} - {self.get_email_type_display()} ({self.campaign.name})"


class EmailSequence(models.Model):
    """Email Sequence - manages sequence of templates for a campaign"""
    name = models.CharField(max_length=200, help_text='Name of the sequence (e.g., "Welcome Series", "Product Launch")')
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='email_sequences')
    email_account = models.ForeignKey('EmailAccount', on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='sequences', help_text='Email account to use for sending sequence emails')
    is_active = models.BooleanField(default=True)
    
    # Sub-sequence support: link to parent sequence (null = main sequence, not null = sub-sequence)
    parent_sequence = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True,
                                        related_name='sub_sequences', 
                                        help_text='Parent sequence (if this is a sub-sequence triggered by replies)')
    is_sub_sequence = models.BooleanField(default=False, help_text='Is this a sub-sequence (triggered by replies)?')
    
    # Interest level routing for sub-sequences
    INTEREST_LEVEL_CHOICES = [
        ('any', 'Any Reply (Default)'),
        ('positive', 'Interested / Positive'),
        ('negative', 'Not Interested / Negative'),
        ('neutral', 'Neutral / Acknowledgment'),
        ('requested_info', 'Requested More Information'),
        ('objection', 'Has Objection / Concern'),
        ('unsubscribe', 'Unsubscribe Request'),
    ]
    interest_level = models.CharField(
        max_length=20,
        choices=INTEREST_LEVEL_CHOICES,
        default='any',
        help_text='Interest level this sub-sequence handles (only for sub-sequences)'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        sequence_type = "Sub-Sequence" if self.is_sub_sequence else "Sequence"
        return f"{sequence_type}: {self.name} - {self.campaign.name}"


class EmailSequenceStep(models.Model):
    """Individual step in an email sequence"""
    sequence = models.ForeignKey(EmailSequence, on_delete=models.CASCADE, related_name='steps')
    template = models.ForeignKey(EmailTemplate, on_delete=models.CASCADE, related_name='sequence_steps')
    step_order = models.IntegerField(help_text='Order in sequence (1, 2, 3...)')
    delay_days = models.IntegerField(default=0, help_text='Days to wait after previous step before sending this')
    delay_hours = models.IntegerField(default=0, help_text='Hours to wait after previous step before sending this')
    delay_minutes = models.IntegerField(default=0, help_text='Minutes to wait after previous step before sending this')
    
    class Meta:
        ordering = ['sequence', 'step_order']
        unique_together = ['sequence', 'step_order']
    
    def __str__(self):
        return f"Step {self.step_order} - {self.template.name}"


class EmailSendHistory(models.Model):
    """History of emails sent to leads"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('opened', 'Opened'),
        ('clicked', 'Clicked'),
        ('bounced', 'Bounced'),
        ('failed', 'Failed'),
        ('unsubscribed', 'Unsubscribed'),
    ]
    
    # Email Details
    subject = models.CharField(max_length=300)
    recipient_email = models.EmailField()
    
    # Status Tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    
    # Error Handling
    bounce_reason = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    
    # A/B Testing
    is_ab_test = models.BooleanField(default=False)
    ab_test_variant = models.CharField(max_length=1, blank=True)
    
    # Sequence Info
    is_followup = models.BooleanField(default=False)
    followup_sequence_number = models.IntegerField(default=0)
    
    # Tracking
    tracking_token = models.CharField(max_length=64, unique=True, null=True, blank=True,
                                     help_text='Unique token for email tracking (opens/clicks)')
    
    # Relationships
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='email_sends')
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='email_history')
    email_template = models.ForeignKey(EmailTemplate, on_delete=models.SET_NULL, null=True, blank=True, 
                                      related_name='sends')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def generate_tracking_token(self):
        """Generate a unique tracking token for this email"""
        import hashlib
        import secrets
        from django.conf import settings
        from django.utils import timezone
        # Use ID (if available), email, timestamp, secret salt + random for uniqueness
        salt = getattr(settings, 'SECRET_KEY', 'default-secret')
        obj_id = self.id if self.id else 0
        timestamp = timezone.now().isoformat()
        unique_str = f"{obj_id}-{self.recipient_email}-{timestamp}-{salt}-{secrets.token_hex(8)}"
        token = hashlib.sha256(unique_str.encode()).hexdigest()[:32]
        return token
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['campaign', 'status']),
            models.Index(fields=['lead', 'campaign']),
        ]
    
    def __str__(self):
        return f"{self.subject} to {self.recipient_email} ({self.status})"


class EmailAccount(models.Model):
    """Email Account Configuration for Sending Campaign Emails"""
    ACCOUNT_TYPE_CHOICES = [
        ('gmail', 'Gmail'),
        ('smtp', 'SMTP Server'),
        ('hostinger', 'Hostinger'),
        ('outlook', 'Outlook'),
        ('custom', 'Custom SMTP'),
    ]
    
    name = models.CharField(max_length=200, help_text='Friendly name for this account (e.g., "Main Gmail Account")')
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES, default='smtp')
    email = models.EmailField(help_text='Email address used for sending')
    
    # SMTP Settings
    smtp_host = models.CharField(max_length=255, help_text='SMTP server host (e.g., smtp.gmail.com)')
    smtp_port = models.IntegerField(default=587, help_text='SMTP server port (587 for TLS, 465 for SSL)')
    smtp_username = models.CharField(max_length=255, help_text='SMTP username (usually same as email)')
    smtp_password = models.CharField(max_length=500, help_text='SMTP password or app password')
    use_tls = models.BooleanField(default=True, help_text='Use TLS encryption')
    use_ssl = models.BooleanField(default=False, help_text='Use SSL encryption')
    
    # Gmail-specific (OAuth or App Password)
    is_gmail_app_password = models.BooleanField(default=False, help_text='Is this using Gmail App Password?')
    
    # Status
    is_active = models.BooleanField(default=True, help_text='Is this account active and ready to use?')
    is_default = models.BooleanField(default=False, help_text='Use this as default account for sending')
    
    # Test/Verification
    last_tested_at = models.DateTimeField(null=True, blank=True, help_text='Last time account was tested')
    test_status = models.CharField(max_length=20, choices=[('success', 'Success'), ('failed', 'Failed'), ('not_tested', 'Not Tested')], default='not_tested')
    test_error = models.TextField(blank=True, help_text='Error message from last test')
    
    # Relationship
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_accounts')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_default', '-is_active', '-created_at']
        unique_together = [('email', 'owner')]
    
    def __str__(self):
        return f"{self.name} ({self.email})"
    
    def save(self, *args, **kwargs):
        # Ensure only one default account per user
        if self.is_default:
            EmailAccount.objects.filter(owner=self.owner, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class CampaignContact(models.Model):
    """
    Tracks where each lead is in the email sequence for a campaign.
    This is the core of automation - tracks state for each contact.
    """
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='campaign_contacts')
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='campaign_contacts')
    sequence = models.ForeignKey('EmailSequence', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='contacts', help_text='Main sequence this contact is in')
    
    # Sub-sequence support
    sub_sequence = models.ForeignKey('EmailSequence', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='sub_sequence_contacts',
                                    help_text='Sub-sequence this contact is in (triggered by reply)')
    sub_sequence_step = models.IntegerField(default=0, help_text='Current step in sub-sequence (0 = not started)')
    sub_sequence_last_sent_at = models.DateTimeField(null=True, blank=True, help_text='When the last sub-sequence email was sent')
    
    # Sequence Progress Tracking
    current_step = models.IntegerField(default=0, help_text='Current step number in sequence (0 = not started, 1 = first step, etc.)')
    last_sent_at = models.DateTimeField(null=True, blank=True, help_text='When the last email in sequence was sent')
    
    # Status Flags
    replied = models.BooleanField(default=False, help_text='Has this contact replied? (stops main sequence, starts sub-sequence)')
    completed = models.BooleanField(default=False, help_text='Has this contact completed the sequence?')
    sub_sequence_completed = models.BooleanField(default=False, help_text='Has this contact completed the sub-sequence?')
    
    # Reply Tracking
    replied_at = models.DateTimeField(null=True, blank=True, help_text='When the contact replied')
    reply_subject = models.CharField(max_length=500, blank=True, help_text='Subject of the reply email')
    reply_content = models.TextField(blank=True, help_text='Full content of the reply email')
    
    # AI Analysis of Reply
    reply_interest_level = models.CharField(
        max_length=20,
        choices=[
            ('positive', 'Positive/Interested'),
            ('negative', 'Negative/Not Interested'),
            ('neutral', 'Neutral'),
            ('not_analyzed', 'Not Analyzed'),
        ],
        default='not_analyzed',
        help_text='AI-determined interest level based on reply content'
    )
    reply_analysis = models.TextField(blank=True, help_text='AI analysis of the reply sentiment and interest')
    
    # Metadata
    started_at = models.DateTimeField(null=True, blank=True, help_text='When sequence started for this contact')
    completed_at = models.DateTimeField(null=True, blank=True, help_text='When sequence completed')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        # Note: Removed unique_together since a contact can be in main sequence and sub-sequence
        indexes = [
            models.Index(fields=['campaign', 'completed', 'replied']),
            models.Index(fields=['campaign', 'sequence', 'current_step']),
            models.Index(fields=['campaign', 'sub_sequence', 'sub_sequence_step']),
            models.Index(fields=['last_sent_at']),
            models.Index(fields=['sub_sequence_last_sent_at']),
        ]
    
    def __str__(self):
        status = 'Completed' if self.completed else ('Replied' if self.replied else f'Step {self.current_step}')
        return f"{self.lead.email} - {self.campaign.name} ({status})"
    
    def mark_replied(self, reply_subject='', reply_content='', reply_at=None, interest_level='not_analyzed', analysis='', sub_sequence=None):
        """
        Mark this contact as having replied - stops main sequence automation and starts sub-sequence if available
        
        Args:
            reply_subject: Subject of the reply
            reply_content: Content of the reply
            reply_at: When the reply was received
            interest_level: AI-determined interest level
            analysis: AI analysis of the reply
            sub_sequence: Optional EmailSequence to use as sub-sequence (if None, looks for sub-sequences of main sequence)
        """
        self.replied = True
        self.replied_at = reply_at or timezone.now()
        if reply_subject:
            self.reply_subject = reply_subject
        if reply_content:
            self.reply_content = reply_content
        if interest_level:
            self.reply_interest_level = interest_level
        if analysis:
            self.reply_analysis = analysis
        
        # Start sub-sequence ONLY if:
        # 1. We're NOT already in a sub-sequence (don't replace existing sub-sequence)
        # 2. sub_sequence parameter is provided (explicitly passed from views.py)
        # 3. This is a reply to MAIN sequence email (not sub-sequence email)
        
        # If already in sub-sequence, don't change it (just record the reply)
        if self.sub_sequence:
            logger.info(f"Contact {self.lead.email} already in sub-sequence '{self.sub_sequence.name}'. Reply recorded, sub-sequence continues.")
        elif sub_sequence is not None and self.sequence:
            # sub_sequence was explicitly passed from views.py (only happens for main sequence replies)
            self.sub_sequence = sub_sequence
            self.sub_sequence_step = 0  # Start from step 0 (will be incremented to 1 when first email is sent)
            self.sub_sequence_last_sent_at = None
            self.sub_sequence_completed = False
            logger.info(f"Started sub-sequence '{sub_sequence.name}' for contact {self.lead.email} after main sequence reply")
        elif sub_sequence is None and not self.sub_sequence and self.sequence:
            # No sub_sequence passed, but we should try to find one (fallback for backward compatibility)
            # This should rarely happen now since views.py handles sub-sequence finding
            detected_interest = interest_level if interest_level and interest_level != 'not_analyzed' else 'neutral'
            
            # Map AI interest levels to sub-sequence interest levels
            interest_mapping = {
                'positive': 'positive',
                'negative': 'negative',
                'neutral': 'neutral',
                'not_analyzed': 'any'
            }
            target_interest = interest_mapping.get(detected_interest, 'any')
            
            # Look for sub-sequences matching the interest level
            sub_sequences = EmailSequence.objects.filter(
                parent_sequence=self.sequence,
                is_sub_sequence=True,
                is_active=True,
                interest_level=target_interest
            )
            
            # If no exact match, try 'any'
            if not sub_sequences.exists() and target_interest != 'any':
                sub_sequences = EmailSequence.objects.filter(
                    parent_sequence=self.sequence,
                    is_sub_sequence=True,
                    is_active=True,
                    interest_level='any'
                )
            
            # If still no match, get any active sub-sequence as fallback
            if not sub_sequences.exists():
                sub_sequences = EmailSequence.objects.filter(
                    parent_sequence=self.sequence,
                    is_sub_sequence=True,
                    is_active=True
                ).order_by('created_at')
            
            if sub_sequences.exists():
                found_sub_sequence = sub_sequences.first()
                self.sub_sequence = found_sub_sequence
                self.sub_sequence_step = 0
                self.sub_sequence_last_sent_at = None
                self.sub_sequence_completed = False
                logger.info(
                    f"Found sub-sequence '{found_sub_sequence.name}' (interest: {found_sub_sequence.interest_level}) "
                    f"for contact {self.lead.email} (detected interest: {detected_interest})"
                )
        
        self.save()
    
    def mark_completed(self):
        """Mark this contact as having completed the sequence"""
        self.completed = True
        self.completed_at = timezone.now()
        self.save()
    
    def advance_step(self, sent_at=None):
        """Advance to next step in sequence"""
        self.current_step += 1
        self.last_sent_at = sent_at or timezone.now()
        if not self.started_at:
            self.started_at = self.last_sent_at
        self.save()


class Reply(models.Model):
    """Stores multiple replies from a contact - allows reply history"""
    INTEREST_LEVEL_CHOICES = [
        ('positive', 'Positive/Interested'),
        ('negative', 'Negative/Not Interested'),
        ('neutral', 'Neutral'),
        ('requested_info', 'Requested More Information'),
        ('objection', 'Has Objection/Concern'),
        ('unsubscribe', 'Unsubscribe Request'),
        ('not_analyzed', 'Not Analyzed'),
    ]
    
    contact = models.ForeignKey(CampaignContact, on_delete=models.CASCADE, related_name='replies')
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='replies')
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='replies')
    
    # Link to sequence - which sequence email triggered this reply
    sequence = models.ForeignKey('EmailSequence', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='replies',
                                help_text='The sequence that the replied-to email belongs to')
    sub_sequence = models.ForeignKey('EmailSequence', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='sub_sequence_replies',
                                    help_text='The sub-sequence that the replied-to email belongs to (if any)')
    
    # Reply Details
    reply_subject = models.CharField(max_length=500, blank=True)
    reply_content = models.TextField(blank=True)
    replied_at = models.DateTimeField(default=timezone.now)
    
    # AI Analysis
    interest_level = models.CharField(max_length=20, choices=INTEREST_LEVEL_CHOICES, default='not_analyzed')
    analysis = models.TextField(blank=True)
    
    # Which email triggered this reply (optional)
    triggering_email = models.ForeignKey('EmailSendHistory', on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='triggered_replies',
                                        help_text='The email that this reply was responding to')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-replied_at']
        indexes = [
            models.Index(fields=['contact', '-replied_at']),
            models.Index(fields=['campaign', '-replied_at']),
            models.Index(fields=['lead', '-replied_at']),
            models.Index(fields=['sequence', '-replied_at']),
            models.Index(fields=['campaign', 'sequence', '-replied_at']),
        ]
    
    def __str__(self):
        return f"Reply from {self.lead.email} on {self.replied_at.strftime('%Y-%m-%d %H:%M')} ({self.get_interest_level_display()})"


# Signal to automatically create CampaignContact when leads are added to campaigns
# @receiver(m2m_changed, sender=Campaign.leads.through)
# def create_campaign_contact(sender, instance, action, pk_set, **kwargs):
#     """Automatically create CampaignContact when leads are added to a campaign"""
#     if action == 'post_add':
#         from marketing_agent.models import CampaignContact, EmailSequence
#         for lead_id in pk_set:
#             lead = Lead.objects.get(pk=lead_id)
#             # Get or create CampaignContact
#             contact, created = CampaignContact.objects.get_or_create(
#                 campaign=instance,
#                 lead=lead,
#                 defaults={
#                     'sequence': instance.email_sequences.filter(is_active=True).first(),
#                     'current_step': 0,
#                 }
#             )
#             if created:
#                 logger = logging.getLogger(__name__)
#                 logger.info(f'Created CampaignContact for {lead.email} in campaign {instance.name}')

@receiver(m2m_changed, sender=Campaign.leads.through)
def create_campaign_contact(sender, instance, action, pk_set, **kwargs):
    """Automatically create CampaignContact when leads are added to a campaign"""
    if action == 'post_add':
        active_sequences = list(instance.email_sequences.filter(is_active=True))
        if not active_sequences:
            return

        for lead_id in pk_set:
            lead = Lead.objects.get(pk=lead_id)
            for seq in active_sequences:
                CampaignContact.objects.get_or_create(
                    campaign=instance,
                    lead=lead,
                    sequence=seq,
                    defaults={'current_step': 0},
                )


@receiver(pre_save, sender=Campaign)
def sync_sequence_status_with_campaign(sender, instance, **kwargs):
    """Sync email sequence status with campaign status"""
    # Only process if this is an update (has pk) and status is changing
    if instance.pk:
        try:
            old_campaign = Campaign.objects.get(pk=instance.pk)
            # If campaign status changed, sync all sequences
            if old_campaign.status != instance.status:
                campaign_is_active = instance.status == 'active'
                # Update all sequences for this campaign
                # Only sequences that were previously active should be affected
                sequences = EmailSequence.objects.filter(campaign=instance)
                for sequence in sequences:
                    # If campaign becomes inactive, deactivate sequences
                    # If campaign becomes active, restore sequences that were previously active
                    if not campaign_is_active:
                        # Campaign is not active, so sequence should be inactive
                        sequence.is_active = False
                    else:
                        # Campaign is active, but we don't auto-activate sequences
                        # They keep their current is_active value
                        # This allows users to manually control sequence activation
                        pass
                    sequence.save()
                logger.info(
                    f'Synced {sequences.count()} sequence(s) status with campaign "{instance.name}" '
                    f'(status changed from {old_campaign.status} to {instance.status})'
                )
        except Campaign.DoesNotExist:
            # New campaign, no need to sync
            pass
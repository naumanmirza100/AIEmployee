from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import json


class Campaign(models.Model):
    """Marketing Campaign Model"""
    CAMPAIGN_TYPE_CHOICES = [
        ('email', 'Email'),
        ('social', 'Social Media'),
        ('paid', 'Paid Advertising'),
        ('partnership', 'Partnership'),
        ('integrated', 'Integrated'),
    ]
    
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
    campaign_type = models.CharField(max_length=20, choices=CAMPAIGN_TYPE_CHOICES, default='integrated')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    actual_spend = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # JSON fields for flexible data
    target_audience = models.JSONField(default=dict, blank=True)
    goals = models.JSONField(default=dict, blank=True)
    channels = models.JSONField(default=list, blank=True)  # List of channels used
    
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='marketing_campaigns')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name
    
    def get_roi(self):
        """Calculate ROI if revenue data is available"""
        if 'revenue' in self.goals and self.actual_spend > 0:
            revenue = float(self.goals.get('revenue', 0))
            return ((revenue - float(self.actual_spend)) / float(self.actual_spend)) * 100
        return None


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

from django.contrib import admin
from .models import Campaign, MarketResearch, CampaignPerformance, MarketingDocument, NotificationRule


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ['name', 'campaign_type', 'status', 'owner', 'budget', 'actual_spend', 'start_date', 'created_at']
    list_filter = ['campaign_type', 'status', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'campaign_type', 'status', 'owner')
        }),
        ('Dates & Budget', {
            'fields': ('start_date', 'end_date', 'budget', 'actual_spend')
        }),
        ('Configuration', {
            'fields': ('target_audience', 'goals', 'channels')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(MarketResearch)
class MarketResearchAdmin(admin.ModelAdmin):
    list_display = ['topic', 'research_type', 'created_by', 'created_at']
    list_filter = ['research_type', 'created_at']
    search_fields = ['topic', 'insights']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Research Information', {
            'fields': ('research_type', 'topic', 'created_by')
        }),
        ('Findings', {
            'fields': ('findings', 'insights', 'source_urls')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(CampaignPerformance)
class CampaignPerformanceAdmin(admin.ModelAdmin):
    list_display = ['campaign', 'metric_name', 'metric_value', 'date', 'channel', 'created_at']
    list_filter = ['metric_name', 'channel', 'date', 'created_at']
    search_fields = ['campaign__name']
    readonly_fields = ['created_at']
    date_hierarchy = 'date'


@admin.register(MarketingDocument)
class MarketingDocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'document_type', 'status', 'campaign', 'created_by', 'created_at']
    list_filter = ['document_type', 'status', 'created_at']
    search_fields = ['title', 'content']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(NotificationRule)
class NotificationRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'rule_type', 'is_active', 'campaign', 'created_by', 'last_triggered']
    list_filter = ['rule_type', 'is_active', 'created_at']
    search_fields = ['name', 'notification_message']
    readonly_fields = ['created_at', 'last_triggered']

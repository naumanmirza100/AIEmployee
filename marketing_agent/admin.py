from django.contrib import admin
from .models import Campaign, MarketResearch, CampaignPerformance, MarketingDocument, NotificationRule, Lead, CampaignContact


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ['name', 'campaign_type', 'status', 'owner', 'start_date', 'created_at']
    list_filter = ['campaign_type', 'status', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'campaign_type', 'status', 'owner')
        }),
        ('Dates', {
            'fields': ('start_date', 'end_date')
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


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ['email', 'first_name', 'last_name', 'company', 'status', 'owner', 'created_at']
    list_filter = ['status', 'source', 'created_at']
    search_fields = ['email', 'first_name', 'last_name', 'company', 'phone']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Contact Information', {
            'fields': ('email', 'first_name', 'last_name', 'phone', 'owner')
        }),
        ('Company Information', {
            'fields': ('company', 'job_title', 'source')
        }),
        ('Status & Notes', {
            'fields': ('status', 'notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(CampaignContact)
class CampaignContactAdmin(admin.ModelAdmin):
    list_display = ['lead', 'campaign', 'sequence', 'current_step', 'replied', 'completed', 'last_sent_at', 'created_at']
    list_filter = ['replied', 'completed', 'campaign', 'sequence', 'created_at']
    search_fields = ['lead__email', 'lead__first_name', 'lead__last_name', 'campaign__name']
    readonly_fields = ['created_at', 'updated_at', 'started_at', 'completed_at', 'replied_at']
    fieldsets = (
        ('Contact & Campaign', {
            'fields': ('campaign', 'lead', 'sequence')
        }),
        ('Sequence Progress', {
            'fields': ('current_step', 'last_sent_at', 'started_at')
        }),
        ('Status', {
            'fields': ('replied', 'replied_at', 'reply_subject', 'completed', 'completed_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    actions = ['mark_as_replied', 'mark_as_completed', 'reset_sequence']
    
    def mark_as_replied(self, request, queryset):
        """Mark selected contacts as replied"""
        count = 0
        for contact in queryset:
            if not contact.replied:
                contact.mark_replied()
                count += 1
        self.message_user(request, f'{count} contact(s) marked as replied.')
    mark_as_replied.short_description = 'Mark as replied (stops automation)'
    
    def mark_as_completed(self, request, queryset):
        """Mark selected contacts as completed"""
        count = 0
        for contact in queryset:
            if not contact.completed:
                contact.mark_completed()
                count += 1
        self.message_user(request, f'{count} contact(s) marked as completed.')
    mark_as_completed.short_description = 'Mark as completed'
    
    def reset_sequence(self, request, queryset):
        """Reset sequence progress for selected contacts"""
        count = queryset.update(current_step=0, last_sent_at=None, started_at=None, completed=False)
        self.message_user(request, f'{count} contact(s) sequence reset.')
    reset_sequence.short_description = 'Reset sequence progress'

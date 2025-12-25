from django.contrib import admin
from .models import CVRecord, Interview, JobDescription


@admin.register(JobDescription)
class JobDescriptionAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'is_active', 'created_by', 'created_at', 'updated_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['title', 'description']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'is_active')
        }),
        ('Parsed Data', {
            'fields': ('keywords_json',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at')
        }),
    )


@admin.register(CVRecord)
class CVRecordAdmin(admin.ModelAdmin):
    list_display = ['id', 'file_name', 'role_fit_score', 'rank', 'qualification_decision', 'qualification_confidence', 'qualification_priority', 'created_at']
    list_filter = ['qualification_decision', 'qualification_priority', 'created_at']
    search_fields = ['file_name']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('file_name', 'created_at')
        }),
        ('Parsed Data', {
            'fields': ('parsed_json',)
        }),
        ('Insights', {
            'fields': ('insights_json', 'role_fit_score', 'rank')
        }),
        ('Enrichment', {
            'fields': ('enriched_json',)
        }),
        ('Qualification', {
            'fields': ('qualification_json', 'qualification_decision', 'qualification_confidence', 'qualification_priority')
        }),
        ('Relations', {
            'fields': ('job_description',)
        }),
    )


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ['id', 'candidate_name', 'candidate_email', 'job_role', 'interview_type', 'status', 'scheduled_datetime', 'created_at']
    list_filter = ['status', 'interview_type', 'created_at']
    search_fields = ['candidate_name', 'candidate_email', 'job_role']
    readonly_fields = ['created_at', 'updated_at', 'invitation_sent_at', 'confirmation_sent_at', 'last_reminder_sent_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Candidate Information', {
            'fields': ('candidate_name', 'candidate_email', 'candidate_phone')
        }),
        ('Job Information', {
            'fields': ('job_role', 'interview_type')
        }),
        ('Interview Details', {
            'fields': ('status', 'scheduled_datetime', 'selected_slot', 'available_slots_json')
        }),
        ('Relations', {
            'fields': ('cv_record', 'recruiter')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'invitation_sent_at', 'confirmation_sent_at', 'last_reminder_sent_at')
        }),
        ('Additional', {
            'fields': ('notes',)
        }),
    )

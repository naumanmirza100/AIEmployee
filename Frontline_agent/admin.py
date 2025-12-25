from django.contrib import admin
from .models import (
    Ticket, KnowledgeBase, Notification, FrontlineWorkflowExecution,
    FrontlineMeeting, Document, FrontlineAnalytics
)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'status', 'priority', 'created_by', 'assigned_to', 'created_at']
    list_filter = ['status', 'priority', 'created_at']
    search_fields = ['title', 'description', 'created_by__username']
    date_hierarchy = 'created_at'


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'category', 'created_by', 'created_at', 'updated_at']
    list_filter = ['category', 'created_at']
    search_fields = ['title', 'content', 'tags']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'type', 'title', 'is_read', 'created_at']
    list_filter = ['type', 'is_read', 'created_at']
    search_fields = ['title', 'message', 'user__username']


@admin.register(FrontlineWorkflowExecution)
class FrontlineWorkflowExecutionAdmin(admin.ModelAdmin):
    list_display = ['id', 'workflow_name', 'executed_by', 'status', 'started_at', 'completed_at']
    list_filter = ['status', 'started_at']
    search_fields = ['workflow_name', 'executed_by__username']


@admin.register(FrontlineMeeting)
class FrontlineMeetingAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'organizer', 'scheduled_at', 'status', 'created_at']
    list_filter = ['status', 'scheduled_at']
    search_fields = ['title', 'organizer__username']


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'document_type', 'uploaded_by', 'created_at']
    list_filter = ['document_type', 'created_at']
    search_fields = ['title', 'description']


@admin.register(FrontlineAnalytics)
class FrontlineAnalyticsAdmin(admin.ModelAdmin):
    list_display = ['id', 'metric_name', 'metric_value', 'calculated_at']
    list_filter = ['metric_name', 'calculated_at']
    search_fields = ['metric_name']


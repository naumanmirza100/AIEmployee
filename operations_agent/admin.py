from django.contrib import admin
from .models import (
    OperationsDocument, OperationsDocumentChunk, OperationsAnalyticsSnapshot,
    OperationsChat, OperationsChatMessage, OperationsNotification,
    OperationsGeneratedDocument,
)


@admin.register(OperationsDocument)
class OperationsDocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'document_type', 'file_type', 'company', 'is_processed', 'created_at']
    list_filter = ['document_type', 'file_type', 'is_processed', 'company']
    search_fields = ['title', 'original_filename']


@admin.register(OperationsDocumentChunk)
class OperationsDocumentChunkAdmin(admin.ModelAdmin):
    list_display = ['document', 'chunk_index', 'page_number', 'created_at']


@admin.register(OperationsAnalyticsSnapshot)
class OperationsAnalyticsSnapshotAdmin(admin.ModelAdmin):
    list_display = ['name', 'source', 'snapshot_type', 'company', 'created_at']


@admin.register(OperationsChat)
class OperationsChatAdmin(admin.ModelAdmin):
    list_display = ['title', 'company', 'user', 'created_at']


@admin.register(OperationsChatMessage)
class OperationsChatMessageAdmin(admin.ModelAdmin):
    list_display = ['chat', 'role', 'created_at']


@admin.register(OperationsNotification)
class OperationsNotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'notification_type', 'severity', 'company', 'is_read', 'created_at']
    list_filter = ['notification_type', 'severity', 'is_read']


@admin.register(OperationsGeneratedDocument)
class OperationsGeneratedDocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'template_type', 'tone', 'company', 'created_at']

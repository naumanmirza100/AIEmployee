from django.contrib import admin
from .models import CRMIntegration, CRMContactMapping, CRMSyncLog, CRMSyncQueue


@admin.register(CRMIntegration)
class CRMIntegrationAdmin(admin.ModelAdmin):
    list_display = ('company', 'provider', 'is_active', 'last_ping_ok', 'last_ping_at', 'updated_at')
    list_filter = ('provider', 'is_active', 'last_ping_ok')
    search_fields = ('company__name',)
    readonly_fields = ('last_ping_at', 'last_ping_ok', 'created_at', 'updated_at')


@admin.register(CRMContactMapping)
class CRMContactMappingAdmin(admin.ModelAdmin):
    list_display = ('integration', 'source_type', 'source_id', 'crm_contact_id', 'last_synced_at')
    list_filter = ('source_type', 'integration__provider')
    search_fields = ('crm_contact_id',)
    readonly_fields = ('last_synced_at',)


@admin.register(CRMSyncLog)
class CRMSyncLogAdmin(admin.ModelAdmin):
    list_display = ('company', 'object_type', 'operation', 'status', 'crm_object_id', 'attempted_at')
    list_filter = ('status', 'object_type', 'operation')
    search_fields = ('object_id', 'crm_object_id', 'error_message')
    readonly_fields = ('attempted_at',)


@admin.register(CRMSyncQueue)
class CRMSyncQueueAdmin(admin.ModelAdmin):
    list_display = ('integration', 'object_type', 'source_type', 'source_id', 'status', 'attempts', 'priority', 'scheduled_at')
    list_filter = ('status', 'object_type', 'source_type')
    search_fields = ('source_id', 'error_message')
    readonly_fields = ('created_at', 'last_attempted_at')
    actions = ['requeue_selected']

    @admin.action(description='Re-queue selected items (reset to pending)')
    def requeue_selected(self, request, queryset):
        from django.utils import timezone
        count = queryset.update(
            status=CRMSyncQueue.STATUS_PENDING,
            attempts=0,
            error_message='',
            scheduled_at=timezone.now(),
        )
        self.message_user(request, f'{count} item(s) re-queued.')

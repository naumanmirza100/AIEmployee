from django.contrib import admin
from .models import (
    ExecutiveMeeting,
    ExecutiveMeetingParticipant,
    MeetingNote,
    MeetingActionItem,
    ExecutiveTask,
    MeetingDocument,
    ExecNotification,
    ExecNotificationChannel,
    ExecMeetingSchedulingChat, ExecMeetingSchedulingChatMessage,
    ExecNotetakerChat, ExecNotetakerChatMessage,
    ExecTaskChat, ExecTaskChatMessage,
    ExecCalendarChat, ExecCalendarChatMessage,
    ExecDocumentChat, ExecDocumentChatMessage,
    ExecNotificationChat, ExecNotificationChatMessage,
)


class ParticipantInline(admin.TabularInline):
    model = ExecutiveMeetingParticipant
    extra = 0
    readonly_fields = ('responded_at', 'notified_at')
    fields = ('company_user', 'response', 'counter_proposed_time', 'reason', 'responded_at')


class ActionItemInline(admin.TabularInline):
    model = MeetingActionItem
    extra = 0
    readonly_fields = ('ai_extracted', 'created_at')
    fields = ('title', 'assignee', 'due_date', 'status', 'priority', 'ai_extracted')


class MeetingNoteInline(admin.StackedInline):
    model = MeetingNote
    extra = 0
    readonly_fields = ('created_at', 'updated_at')


class MeetingDocumentInline(admin.TabularInline):
    model = MeetingDocument
    extra = 0
    readonly_fields = ('ai_generated', 'created_at')
    fields = ('doc_type', 'title', 'ai_generated', 'created_at')


@admin.register(ExecutiveMeeting)
class ExecutiveMeetingAdmin(admin.ModelAdmin):
    list_display = ('title', 'organizer', 'scheduled_at', 'duration_minutes', 'status', 'recurrence', 'created_at')
    list_filter = ('status', 'recurrence', 'scheduled_at')
    search_fields = ('title', 'description', 'organizer__full_name', 'organizer__email')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-scheduled_at',)
    inlines = [ParticipantInline, ActionItemInline, MeetingNoteInline, MeetingDocumentInline]
    fieldsets = (
        ('Meeting Info', {
            'fields': ('title', 'description', 'organizer', 'status'),
        }),
        ('Schedule', {
            'fields': ('scheduled_at', 'duration_minutes', 'timezone_name', 'actual_start', 'actual_end'),
        }),
        ('Meeting Link', {
            'fields': ('meeting_link',),
        }),
        ('Recurrence', {
            'fields': ('recurrence', 'recurrence_end_date', 'parent_meeting'),
            'classes': ('collapse',),
        }),
        ('Agenda', {
            'fields': ('agenda',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(ExecutiveMeetingParticipant)
class ExecutiveMeetingParticipantAdmin(admin.ModelAdmin):
    list_display = ('meeting', 'company_user', 'response', 'responded_at')
    list_filter = ('response',)
    search_fields = ('meeting__title', 'company_user__full_name', 'company_user__email')
    readonly_fields = ('responded_at', 'notified_at')


@admin.register(MeetingActionItem)
class MeetingActionItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'meeting', 'assignee', 'due_date', 'status', 'priority', 'ai_extracted')
    list_filter = ('status', 'priority', 'ai_extracted')
    search_fields = ('title', 'meeting__title', 'assignee__full_name')
    readonly_fields = ('ai_extracted', 'created_at', 'updated_at')
    ordering = ('-priority', 'due_date')


@admin.register(ExecutiveTask)
class ExecutiveTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'company_user', 'status', 'priority', 'due_date', 'estimated_hours', 'created_at')
    list_filter = ('status', 'priority', 'due_date')
    search_fields = ('title', 'description', 'company_user__full_name', 'company_user__email')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-priority', 'due_date')
    fieldsets = (
        ('Task Info', {
            'fields': ('company_user', 'title', 'description', 'status', 'priority'),
        }),
        ('Schedule', {
            'fields': ('due_date', 'estimated_hours', 'linked_meeting'),
        }),
        ('AI', {
            'fields': ('ai_reasoning',),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(MeetingDocument)
class MeetingDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'doc_type', 'meeting', 'created_by', 'ai_generated', 'created_at')
    list_filter = ('doc_type', 'ai_generated')
    search_fields = ('title', 'meeting__title', 'created_by__full_name')
    readonly_fields = ('ai_generated', 'created_at', 'updated_at')


@admin.register(ExecNotification)
class ExecNotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'company_user', 'notification_type', 'severity', 'is_read', 'created_at')
    list_filter = ('notification_type', 'severity', 'is_read')
    search_fields = ('title', 'message', 'company_user__full_name', 'company_user__email')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
    actions = ['mark_as_read']

    @admin.action(description='Mark selected notifications as read')
    def mark_as_read(self, request, queryset):
        queryset.update(is_read=True)


@admin.register(ExecNotificationChannel)
class ExecNotificationChannelAdmin(admin.ModelAdmin):
    list_display = ('company_user', 'channel_type', 'target', 'is_active', 'created_at')
    list_filter = ('channel_type', 'is_active')
    search_fields = ('company_user__full_name', 'target')


# ---------------------------------------------------------------------------
# Chat models — read-only in admin
# ---------------------------------------------------------------------------

class BaseChatMessageInline(admin.TabularInline):
    extra = 0
    readonly_fields = ('role', 'content', 'created_at')
    fields = ('role', 'content', 'created_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class SchedulingMessageInline(BaseChatMessageInline):
    model = ExecMeetingSchedulingChatMessage


class NotetakerMessageInline(BaseChatMessageInline):
    model = ExecNotetakerChatMessage


class TaskChatMessageInline(BaseChatMessageInline):
    model = ExecTaskChatMessage


class CalendarChatMessageInline(BaseChatMessageInline):
    model = ExecCalendarChatMessage


class DocumentChatMessageInline(BaseChatMessageInline):
    model = ExecDocumentChatMessage


class NotificationChatMessageInline(BaseChatMessageInline):
    model = ExecNotificationChatMessage


def _make_chat_admin(message_inline_cls):
    class ChatAdmin(admin.ModelAdmin):
        list_display = ('title', 'company_user', 'created_at', 'updated_at')
        list_filter = ('created_at',)
        search_fields = ('title', 'company_user__full_name', 'company_user__email')
        readonly_fields = ('created_at', 'updated_at')
        inlines = [message_inline_cls]

        def has_add_permission(self, request):
            return False

    return ChatAdmin


admin.site.register(ExecMeetingSchedulingChat, _make_chat_admin(SchedulingMessageInline))
admin.site.register(ExecNotetakerChat, _make_chat_admin(NotetakerMessageInline))
admin.site.register(ExecTaskChat, _make_chat_admin(TaskChatMessageInline))
admin.site.register(ExecCalendarChat, _make_chat_admin(CalendarChatMessageInline))
admin.site.register(ExecDocumentChat, _make_chat_admin(DocumentChatMessageInline))
admin.site.register(ExecNotificationChat, _make_chat_admin(NotificationChatMessageInline))

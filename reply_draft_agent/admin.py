from django.contrib import admin
from .models import ReplyDraft


@admin.register(ReplyDraft)
class ReplyDraftAdmin(admin.ModelAdmin):
    list_display = ('id', 'owner', 'lead', 'status', 'tone', 'regeneration_count', 'created_at', 'sent_at')
    list_filter = ('status', 'tone', 'created_at')
    search_fields = ('lead__email', 'draft_subject', 'edited_subject')
    readonly_fields = ('created_at', 'updated_at', 'sent_at', 'sent_email', 'regeneration_count', 'parent_draft')
    raw_id_fields = ('original_email', 'lead', 'email_account', 'owner')

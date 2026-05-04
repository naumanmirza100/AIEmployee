from django.apps import AppConfig
from django.db.models.signals import post_delete
from django.dispatch import receiver


class ReplyDraftAgentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'reply_draft_agent'

    def ready(self):
        """Register the reply draft agent with the shared registry."""
        try:
            from project_manager_agent.ai_agents.agents_registry import AgentRegistry
            from .agents.reply_draft_agent import ReplyDraftAgent
            AgentRegistry.register("reply_draft", ReplyDraftAgent)
        except ImportError:
            pass

        # Delete the underlying file when an InboxAttachment row is removed.
        # Django's FileField doesn't auto-delete files on row delete (intentional —
        # it's safer to opt in), so wire it here. CASCADE from InboxEmail also
        # fires this signal for each attachment row, keeping local disk clean
        # whenever an email is pruned or an account is disconnected.
        from .models import InboxAttachment, ReplyDraftAttachment

        def _file_is_shared(file_name, *, exclude_inbox_id=None, exclude_draft_att_id=None):
            """Return True if any other attachment row still references this path.

            The Reply-Draft Agent's send-mirror flow has an InboxAttachment
            row and a ReplyDraftAttachment row pointing at the SAME file on
            disk (we share the source file instead of re-writing bytes).
            That means a naive post_delete unlink — fired by either side —
            would leave the other row's download endpoint serving a dead
            path. Before unlinking, we check both tables for any sibling
            still referencing the same `file` value.
            """
            if not file_name:
                return False
            inbox_qs = InboxAttachment.objects.filter(file=file_name)
            if exclude_inbox_id is not None:
                inbox_qs = inbox_qs.exclude(id=exclude_inbox_id)
            if inbox_qs.exists():
                return True
            draft_qs = ReplyDraftAttachment.objects.filter(file=file_name)
            if exclude_draft_att_id is not None:
                draft_qs = draft_qs.exclude(id=exclude_draft_att_id)
            return draft_qs.exists()

        @receiver(post_delete, sender=InboxAttachment, dispatch_uid='inbox_attachment_file_cleanup')
        def _delete_attachment_file(sender, instance, **_kwargs):
            f = getattr(instance, 'file', None)
            if not f or not f.name:
                return
            # Skip the unlink when another row still references this path
            # (the sent-mirror shares its file with the source draft).
            if _file_is_shared(f.name, exclude_inbox_id=instance.id):
                return
            try:
                f.delete(save=False)
            except Exception:
                # Storage backend not reachable / file already gone —
                # fail quietly so the row deletion still succeeds.
                pass

        # Same cleanup pattern for outgoing draft attachments. Without it,
        # discarded drafts and re-uploaded files would pile up on disk
        # (or S3) even after their DB row is gone.
        @receiver(post_delete, sender=ReplyDraftAttachment, dispatch_uid='reply_draft_attachment_file_cleanup')
        def _delete_reply_draft_attachment_file(sender, instance, **_kwargs):
            f = getattr(instance, 'file', None)
            if not f or not f.name:
                return
            if _file_is_shared(f.name, exclude_draft_att_id=instance.id):
                return
            try:
                f.delete(save=False)
            except Exception:
                pass

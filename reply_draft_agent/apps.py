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
        from .models import InboxAttachment

        @receiver(post_delete, sender=InboxAttachment, dispatch_uid='inbox_attachment_file_cleanup')
        def _delete_attachment_file(sender, instance, **_kwargs):
            f = getattr(instance, 'file', None)
            if f and f.name:
                try:
                    f.delete(save=False)
                except Exception:
                    # Storage backend not reachable / file already gone —
                    # fail quietly so the row deletion still succeeds.
                    pass

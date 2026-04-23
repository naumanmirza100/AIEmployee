from django.apps import AppConfig


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

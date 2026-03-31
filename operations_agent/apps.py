from django.apps import AppConfig


class OperationsAgentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'operations_agent'
    verbose_name = 'Operations Agent'

    def ready(self):
        """Register operations agents when app is ready"""
        from project_manager_agent.ai_agents.agents_registry import AgentRegistry

        try:
            from .agents.document_processing_agent import DocumentProcessingAgent
            AgentRegistry.register("document_processing", DocumentProcessingAgent)
        except ImportError:
            pass

        try:
            from .agents.summarization_insight_agent import SummarizationInsightAgent
            AgentRegistry.register("summarization_insight", SummarizationInsightAgent)
        except ImportError:
            pass

        try:
            from .agents.analytics_dashboard_agent import AnalyticsDashboardAgent
            AgentRegistry.register("analytics_dashboard", AnalyticsDashboardAgent)
        except ImportError:
            pass

        try:
            from .agents.knowledge_qa_agent import KnowledgeQAAgent
            AgentRegistry.register("operations_knowledge_qa", KnowledgeQAAgent)
        except ImportError:
            pass

        try:
            from .agents.document_authoring_agent import DocumentAuthoringAgent
            AgentRegistry.register("operations_document_authoring", DocumentAuthoringAgent)
        except ImportError:
            pass

        try:
            from .agents.proactive_notification_agent import ProactiveNotificationAgent
            AgentRegistry.register("operations_proactive_notification", ProactiveNotificationAgent)
        except ImportError:
            pass

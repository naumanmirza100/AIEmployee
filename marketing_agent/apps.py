from django.apps import AppConfig


class MarketingAgentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'marketing_agent'
    
    def ready(self):
        """Register marketing agents when app is ready"""
        from project_manager_agent.ai_agents.agents_registry import AgentRegistry
        
        try:
            from .agents.marketing_qa_agent import MarketingQAAgent
            AgentRegistry.register("marketing_qa", MarketingQAAgent)
        except ImportError:
            pass  # Agent not implemented yet
        
        try:
            from .agents.market_research_agent import MarketResearchAgent
            AgentRegistry.register("market_research", MarketResearchAgent)
        except ImportError:
            pass  # Agent not implemented yet
        
        try:
            from .agents.outreach_campaign_agent import OutreachCampaignAgent
            AgentRegistry.register("outreach_campaign", OutreachCampaignAgent)
        except ImportError:
            pass  # Agent not implemented yet
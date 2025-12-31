from django.apps import AppConfig


class RecruitmentAgentConfig(AppConfig):
    name = 'recruitment_agent'
    
    def ready(self):
        """Register signals when app is ready"""
        import recruitment_agent.signals  # noqa
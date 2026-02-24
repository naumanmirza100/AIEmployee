from django.apps import AppConfig


class FrontlineAgentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Frontline_agent'
    verbose_name = 'Frontline Agent'

    def ready(self):
        import Frontline_agent.signals  # noqa: F401 - connect post_save workflow triggers


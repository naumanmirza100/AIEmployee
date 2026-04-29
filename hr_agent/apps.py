from django.apps import AppConfig


class HRAgentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hr_agent'
    verbose_name = 'HR Support Agent'

    def ready(self):
        # Connect post_save / time-based signals once they're added.
        try:
            import hr_agent.signals  # noqa: F401
        except ImportError:
            pass

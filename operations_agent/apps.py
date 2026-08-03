from django.apps import AppConfig


class OperationsAgentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'operations_agent'
    verbose_name = 'Operations Agent'

    def ready(self):
        # Connect signal handlers that auto-generate notifications.
        try:
            from . import signals  # noqa: F401
        except ImportError:
            pass
        # NOTE: Operations agents are used by direct import in api/views, not
        # via AgentRegistry, so no registrations happen here. (The previous
        # registrations referenced non-existent classes/modules and silently
        # failed — removed to avoid dead code.)

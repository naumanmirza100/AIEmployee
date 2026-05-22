from django.apps import AppConfig


class CRMSyncAgentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'crm_sync_agent'
    verbose_name = 'CRM & System Sync Agent'

    def ready(self):
        import crm_sync_agent.signals  # noqa: F401

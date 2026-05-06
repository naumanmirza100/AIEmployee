import os
import sys

from django.apps import AppConfig


class AiSdrAgentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ai_sdr_agent'
    verbose_name = 'AI SDR Agent'

    def ready(self):
        # Don't start background threads during management commands
        # (migrate, makemigrations, collectstatic, shell, test…)
        managed_cmds = {'migrate', 'makemigrations', 'collectstatic', 'test', 'shell', 'check'}
        if len(sys.argv) > 1 and sys.argv[1] in managed_cmds:
            return

        # Django's autoreloader runs two processes: the outer watcher and the
        # inner worker (RUN_MAIN=true). Only start the scheduler in the worker
        # so we don't spin up duplicate threads.
        if (os.environ.get('RUN_MAIN') == 'true'
                or '--noreload' in sys.argv
                or 'runserver' not in sys.argv):
            try:
                from ai_sdr_agent.scheduler import start_scheduler
                start_scheduler()
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "SDR scheduler failed to start — emails will not send automatically"
                )

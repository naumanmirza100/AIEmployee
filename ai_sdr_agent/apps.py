import os
import sys

from django.apps import AppConfig


class AiSdrAgentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ai_sdr_agent'
    verbose_name = 'AI SDR Agent'

    def ready(self):
        # ── Skip during management commands ──────────────────────────────────
        # We never want background threads during migrate, makemigrations,
        # collectstatic, shell, test, check — they don't serve requests.
        _SKIP_CMDS = {
            'migrate', 'makemigrations', 'collectstatic',
            'test', 'shell', 'check', 'showmigrations',
            'sqlmigrate', 'dbshell', 'createsuperuser',
        }
        if len(sys.argv) > 1 and sys.argv[1] in _SKIP_CMDS:
            return

        # ── Guard against duplicate processes (dev auto-reloader) ────────────
        # Django's dev server (runserver) spawns two processes:
        #   - outer watcher  →  RUN_MAIN is unset
        #   - inner worker   →  RUN_MAIN=true  (this is the one that handles requests)
        # We start the scheduler only in the inner worker (or in production where
        # runserver isn't used at all).
        is_inner_worker  = os.environ.get('RUN_MAIN') == 'true'
        is_noreload      = '--noreload' in sys.argv
        is_not_devserver = 'runserver' not in sys.argv   # gunicorn / waitress / etc.

        if not (is_inner_worker or is_noreload or is_not_devserver):
            return  # outer watcher process — skip

        # ── Start the scheduler ──────────────────────────────────────────────
        try:
            from ai_sdr_agent.scheduler import start_scheduler
            start_scheduler()
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "SDR scheduler failed to start — emails will not send automatically"
            )

        # ── Wire shutdown signal for clean stop ──────────────────────────────
        # Django sends `setting_changed` on test teardown and raises SystemExit
        # on Ctrl-C, both of which trigger atexit handlers registered inside
        # start_scheduler().  For gunicorn SIGTERM we add an explicit receiver.
        try:
            import signal
            from ai_sdr_agent.scheduler import stop_scheduler

            _original_sigterm = signal.getsignal(signal.SIGTERM)

            def _sigterm_handler(signum, frame):
                stop_scheduler()
                # Re-raise so gunicorn / the OS can finish its own cleanup.
                if callable(_original_sigterm):
                    _original_sigterm(signum, frame)

            signal.signal(signal.SIGTERM, _sigterm_handler)
        except Exception:
            pass  # SIGTERM wiring is best-effort

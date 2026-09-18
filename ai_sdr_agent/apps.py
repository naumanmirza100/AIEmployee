import os
import sys

from django.apps import AppConfig


_FALSE = {'0', 'false', 'no', 'off'}
_TRUE = {'1', 'true', 'yes', 'on'}

# Management commands that serve requests. Every other command (migrate, shell,
# check, test, sync_stripe_plans, rebuild_calendar_blocks, …) is a short job
# that must not start background threads.
_SERVER_COMMANDS = {'runserver', 'runserver_with_celery', 'runserver_plus'}


def _is_celery_process(argv):
    """`celery -A … worker|beat` and `python -m celery …`."""
    for arg in argv[:2]:
        name = os.path.basename(str(arg)).lower()
        if name in ('celery', 'celery.exe') or 'celery' in os.path.normpath(str(arg)).lower().split(os.sep):
            return True
    return False


def should_start_scheduler(argv=None, environ=None):
    """Whether this process should run the SDR scheduler.

    Exactly one copy should run per deployment: in the web server process.
    Every copy runs every job, and each run costs database connections, which
    the database user may only open 500 times an hour. Before this check the
    Celery worker, Celery Beat and any standalone script each started their
    own copy as well, because the only test was "not runserver".

    ``SDR_SCHEDULER_ENABLED`` overrides the detection: ``false`` never starts
    it (e.g. a developer not working on SDR), ``true`` starts it in any
    process that isn't Celery or a one-off management command (e.g. a
    dedicated scheduler process, or a WSGI host the detection doesn't know).
    """
    argv = list(sys.argv if argv is None else argv)
    environ = os.environ if environ is None else environ
    flag = str(environ.get('SDR_SCHEDULER_ENABLED', '')).strip().lower()
    if flag in _FALSE:
        return False
    if _is_celery_process(argv):
        return False

    program = os.path.basename(str(argv[0])).lower() if argv else ''
    if program in ('manage.py', 'manage', 'django-admin', 'django-admin.py'):
        command = argv[1] if len(argv) > 1 else ''
        if command not in _SERVER_COMMANDS:
            return False
        # The dev server runs two processes: the autoreload watcher (RUN_MAIN
        # unset) and the worker that serves requests (RUN_MAIN=true).
        return environ.get('RUN_MAIN') == 'true' or '--noreload' in argv

    if flag in _TRUE:
        return True
    # A WSGI/ASGI server (gunicorn, uvicorn, waitress, Passenger, mod_wsgi …)
    # imports Django without a manage.py command. Scripts, `python -c`, stdin,
    # the interactive interpreter and test runners are not servers.
    if program in ('passenger_wsgi.py', 'wsgi.py', 'asgi.py'):
        return True
    if program in ('', '-', '-c', 'ipython', 'pytest', 'py.test') or program.endswith('.py'):
        return False
    return not program.startswith(('jupyter', 'ipykernel'))


class AiSdrAgentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ai_sdr_agent'
    verbose_name = 'AI SDR Agent'

    def ready(self):
        if not should_start_scheduler():
            return

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

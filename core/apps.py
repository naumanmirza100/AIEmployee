import atexit
import os
import subprocess
import sys

from django.apps import AppConfig

# Module-level references so atexit can clean them up
_celery_worker_proc = None
_celery_beat_proc = None


def _cleanup_celery():
    """Terminate Celery worker and beat on exit."""
    global _celery_worker_proc, _celery_beat_proc
    for proc in (_celery_worker_proc, _celery_beat_proc):
        if proc and proc.poll() is None:
            proc.terminate()


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        """Import signals when app is ready"""
        import core.signals  # noqa

        # Auto-start Celery when running the dev server
        self._auto_start_celery()

    def _auto_start_celery(self):
        global _celery_worker_proc, _celery_beat_proc

        # Only start Celery for runserver (not migrate, collectstatic, shell, etc.)
        if not self._is_runserver():
            return

        # Skip if runserver_with_celery already handles Celery
        if os.environ.get('CELERY_AUTO_STARTED'):
            return

        # Django reloader runs ready() twice: once in the main process, once in
        # the child (which has RUN_MAIN=true). Start Celery only in the main
        # process (before the reloader fork) so restarts don't spawn duplicates.
        if os.environ.get('RUN_MAIN') == 'true':
            return

        os.environ['CELERY_AUTO_STARTED'] = '1'

        creation_flags = 0
        if sys.platform == 'win32':
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

        # Log Celery output to files instead of cluttering the terminal
        logs_dir = os.path.join(os.getcwd(), 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        worker_log = open(os.path.join(logs_dir, 'celery_worker.log'), 'a')
        beat_log = open(os.path.join(logs_dir, 'celery_beat.log'), 'a')

        try:
            # threads pool with concurrency=4 lets the on-connect inbox sync
            # run alongside the periodic 5-min beat instead of waiting in
            # queue. Was --pool=solo previously, which serialized everything
            # behind whatever long-running task happened to be active.
            _celery_worker_proc = subprocess.Popen(
                [sys.executable, '-m', 'celery', '-A', 'project_manager_ai', 'worker', '-l', 'info', '--pool=threads', '--concurrency=4'],
                stdout=worker_log,
                stderr=worker_log,
                creationflags=creation_flags,
                cwd=os.getcwd(),
                env=os.environ.copy(),
            )
            print('[AUTO] Celery worker started (PID %s) -> logs/celery_worker.log' % _celery_worker_proc.pid)
        except Exception as e:
            print('[AUTO] Failed to start Celery worker: %s' % e)

        try:
            _celery_beat_proc = subprocess.Popen(
                [sys.executable, '-m', 'celery', '-A', 'project_manager_ai', 'beat', '-l', 'info'],
                stdout=beat_log,
                stderr=beat_log,
                creationflags=creation_flags,
                cwd=os.getcwd(),
                env=os.environ.copy(),
            )
            print('[AUTO] Celery beat started (PID %s) -> logs/celery_beat.log' % _celery_beat_proc.pid)
        except Exception as e:
            print('[AUTO] Failed to start Celery beat: %s' % e)

        atexit.register(_cleanup_celery)

    @staticmethod
    def _is_runserver():
        """Check if the current command is runserver or runserver_with_celery."""
        argv = sys.argv
        for arg in argv:
            if arg in ('runserver', 'runserver_with_celery'):
                return True
        return False
"""
Run Django development server with Celery worker and beat in the background.
Single command: server + Celery run together. Stop with Ctrl+C stops all.

Usage:
    python manage.py runserver_with_celery
    python manage.py runserver_with_celery 0.0.0.0:8000
"""
import subprocess
import sys
import time
import signal
import os

from django.core.management.base import BaseCommand
from django.core.management import execute_from_command_line


class Command(BaseCommand):
    help = 'Run runserver with Celery worker and beat in the background (single command)'

    def add_arguments(self, parser):
        parser.add_argument(
            'addrport',
            nargs='?',
            default='127.0.0.1:8000',
            help='Optional port number, or ip:port (default 127.0.0.1:8000)',
        )
        parser.add_argument(
            '--noreload',
            action='store_true',
            help='Disable auto-reloader',
        )

    def handle(self, *args, **options):
        addrport = options.get('addrport', '127.0.0.1:8000')
        noreload = options.get('noreload', False)

        worker_proc = None
        beat_proc = None

        def cleanup():
            if worker_proc and worker_proc.poll() is None:
                worker_proc.terminate()
                self.stdout.write('Stopped Celery worker.')
            if beat_proc and beat_proc.poll() is None:
                beat_proc.terminate()
                self.stdout.write('Stopped Celery beat.')

        def signal_handler(signum, frame):
            cleanup()
            sys.exit(0)

        # Start Celery worker in background
        self.stdout.write('Starting Celery worker in background...')
        worker_cmd = [sys.executable, '-m', 'celery', '-A', 'project_manager_ai', 'worker', '-l', 'info']
        try:
            worker_proc = subprocess.Popen(
                worker_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
                cwd=os.getcwd(),
                env=os.environ.copy(),
            )
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Failed to start Celery worker: {e}'))
            return
        self.stdout.write(self.style.SUCCESS('Celery worker started.'))

        # Start Celery beat in background
        self.stdout.write('Starting Celery beat in background...')
        beat_cmd = [sys.executable, '-m', 'celery', '-A', 'project_manager_ai', 'beat', '-l', 'info']
        try:
            beat_proc = subprocess.Popen(
                beat_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
                cwd=os.getcwd(),
                env=os.environ.copy(),
            )
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Failed to start Celery beat: {e}'))
            cleanup()
            return
        self.stdout.write(self.style.SUCCESS('Celery beat started.'))

        time.sleep(1)

        # Run server (blocking); Ctrl+C will raise KeyboardInterrupt
        runserver_args = ['runserver', addrport]
        if noreload:
            runserver_args.append('--noreload')
        self.stdout.write(self.style.SUCCESS(f'Starting Django server at http://{addrport}/'))
        self.stdout.write('Press Ctrl+C to stop server and Celery.\n')

        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        except (AttributeError, ValueError):
            pass  # Windows may not support all signals

        try:
            execute_from_command_line([sys.argv[0]] + runserver_args)
        except KeyboardInterrupt:
            pass
        finally:
            cleanup()

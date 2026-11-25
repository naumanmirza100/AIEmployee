"""The nightly backup: `python manage.py make_backup --keep 7` (core.backups.make_nightly_backup).

scripts/ppp-full-backup.sh runs it on the web container from cron, then encrypts the zip and sends it to Backblaze
B2. It prints the zip's file name, alone on the last line, for the script; it is in BACKUP_ROOT and on Admin → Backups.
"""
from django.core.management.base import BaseCommand, CommandError

from core import backups


class Command(BaseCommand):
    help = 'Make a whole-system backup now (as Admin → Backups does) and keep only the newest nightly ones.'

    def add_arguments(self, parser):
        parser.add_argument('--keep', type=int, default=7,
                            help='How many nightly backups the server keeps (default 7). Ones made with the button '
                                 'are never deleted.')

    def handle(self, *args, **options):
        try:
            backup = backups.make_nightly_backup(keep=options['keep'])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if backup.status != 'done':
            raise CommandError(f'The backup failed: {backup.error}')
        summary = backup.summary or {}
        self.stderr.write(f"{summary.get('records')} records, {summary.get('files')} uploaded files, "
                          f"{backup.size_bytes:,} bytes.")
        self.stdout.write(backup.file_name)

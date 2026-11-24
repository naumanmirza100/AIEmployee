"""Put a backup from Admin → Backups back, on a new server: `python manage.py restore_backup backup-....zip`.

Run it after `migrate`, on a database with no logins and no companies (it refuses any other). It loads the whole
database with the app's save hooks off and puts the uploaded files back (core.backups.restore).
"""
from django.core.management.base import BaseCommand, CommandError

from core import backups


class Command(BaseCommand):
    help = 'Restore a backup made on Admin → Backups into this new, empty database, with its uploaded files.'

    def add_arguments(self, parser):
        parser.add_argument('zip', help='The backup zip, as downloaded from Admin → Backups.')
        parser.add_argument('--no-media', action='store_true', help='Load the database only, not the uploaded files.')

    def handle(self, *args, **options):
        try:
            result = backups.restore(options['zip'], media=not options['no_media'])
        except backups.RestoreError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"Restored {result['records']} records and {result['files']} uploaded files."))
        self.stdout.write('Stored API keys and mailbox passwords only decrypt with the same FIELD_ENCRYPTION_KEY '
                          '(or SECRET_KEY) as the server the backup came from.')

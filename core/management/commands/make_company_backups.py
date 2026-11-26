"""Each company's nightly backup: `python manage.py make_company_backups --keep 7`
(core.backups.make_nightly_company_backups).

scripts/ppp-full-backup.sh runs it on the web container from cron, after the whole-system backup, then encrypts each
zip and sends it to Backblaze B2 (companies/<company id>/). It prints one line per finished backup on stdout, its path
under BACKUP_ROOT: companies/<company id>/<file name>. Companies whose backup failed are on stderr, and then the
command exits with an error once the others are done, so the script reports it.
"""
from django.core.management.base import BaseCommand, CommandError

from core import backups


class Command(BaseCommand):
    help = "Make each active company's backup now (as its dashboard's Backups page does) and keep only its newest nightly ones."

    def add_arguments(self, parser):
        parser.add_argument('--keep', type=int, default=7,
                            help="How many nightly backups the server keeps for each company (default 7). Ones made "
                                 "with the button are never deleted.")

    def handle(self, *args, **options):
        failed = 0
        for company, backup, error in backups.make_nightly_company_backups(keep=options['keep']):
            if error or backup is None:
                failed += 1
                self.stderr.write(f'Company {company.pk} ({company.name}): the backup failed: {error}')
                continue
            self.stdout.write(f'companies/{company.pk}/{backup.file_name}')
        if failed:
            raise CommandError(f'{failed} company backup(s) failed.')

"""Recompute the shared busy-time table from the PM, HR and Frontline meeting
tables.

    python manage.py rebuild_calendar_blocks                 # meetings that haven't ended
    python manage.py rebuild_calendar_blocks --company 12
    python manage.py rebuild_calendar_blocks --since 2026-01-01

Safe to run at any time: every meeting's rows are rewritten from its source
row, so running it twice gives the same result. The same rebuild runs nightly
through Celery Beat (`core.tasks.rebuild_calendar_blocks`).
"""
from datetime import datetime, timezone as dt_timezone

from django.core.management.base import BaseCommand, CommandError

from core.scheduling.sync import rebuild


class Command(BaseCommand):
    help = 'Rebuild CalendarBlock rows (shared busy time) from the meeting tables.'

    def add_arguments(self, parser):
        parser.add_argument('--company', type=int, help='Only this company id.')
        parser.add_argument('--since', help='ISO date; rebuild meetings from this date on '
                                            '(default: now). Use an early date to include past meetings.')

    def handle(self, *args, **opts):
        since = None
        if opts.get('since'):
            try:
                since = datetime.fromisoformat(opts['since'])
            except ValueError:
                raise CommandError('--since must be an ISO date, e.g. 2026-01-01')
            if since.tzinfo is None:
                since = since.replace(tzinfo=dt_timezone.utc)
        stats = rebuild(company_id=opts.get('company'), since=since, log=self.stdout.write)
        total = sum(s['blocks'] for s in stats.values())
        self.stdout.write(self.style.SUCCESS(f'Done: {total} busy blocks written.'))

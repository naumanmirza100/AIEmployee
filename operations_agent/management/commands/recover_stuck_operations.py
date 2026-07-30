"""Recover Operations documents / summaries stuck mid-processing.

Processing runs in a background thread. If the worker restarts, is redeployed,
or is OOM-killed mid-run, the thread dies silently and the row is stranded in
`pending`/`processing` forever — the only failure path that stamps `failed` is a
caught Python exception, which process death bypasses.

This command marks such rows `failed` once they've sat in a non-terminal state
longer than `--minutes` (default 30). Run it periodically (cron / celery-beat).

Usage:
    python manage.py recover_stuck_operations                 # 30-min threshold
    python manage.py recover_stuck_operations --minutes 15
    python manage.py recover_stuck_operations --dry-run       # report only
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = "Mark Operations documents/summaries stuck in processing as failed."

    def add_arguments(self, parser):
        parser.add_argument('--minutes', type=int, default=30,
                            help='Age (minutes) past which a non-terminal row is considered stuck.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would be marked failed without changing anything.')

    def handle(self, *args, **opts):
        from operations_agent.models import OperationsDocument, OperationsDocumentSummary

        cutoff = timezone.now() - timedelta(minutes=opts['minutes'])
        dry = opts['dry_run']
        stuck_statuses = ('pending', 'processing')
        msg = f'Processing exceeded {opts["minutes"]} min without completing (auto-recovered).'

        total = 0
        # OperationsDocument tracks updated_at; the summary model only has
        # created_at — use whichever timestamp each model exposes.
        for model, label, ts_field in (
            (OperationsDocument, 'document', 'updated_at'),
            (OperationsDocumentSummary, 'summary', 'created_at'),
        ):
            qs = model.objects.filter(
                processing_status__in=stuck_statuses,
                **{f'{ts_field}__lt': cutoff},
            )
            n = qs.count()
            total += n
            for row in qs.only('id')[:500]:
                name = getattr(row, 'title', None) or getattr(row, 'original_filename', '?')
                self.stdout.write(f'  {"[dry] " if dry else ""}stuck {label} {row.id} — {name}')
            if not dry and n:
                qs.update(processing_status='failed', processing_error=msg)

        if total == 0:
            self.stdout.write('No stuck rows found.')
        else:
            verb = 'Would mark' if dry else 'Marked'
            self.stdout.write(self.style.SUCCESS(f'{verb} {total} stuck row(s) as failed.'))

"""Delete old StripeWebhookEvent rows.

The table is a dedup ledger, not a log: one row per event id, claimed before the
handler runs so a redelivery cannot process twice. It only has to outlive Stripe's
retry window (~3 days), but nothing ever deleted from it, so it grew for the life of
the deployment.

Default retention is 30 days — an order of magnitude past the retry window, which
leaves plenty of room to investigate a recent incident while still bounding the
table.

    python manage.py prune_stripe_events                 # dry run
    python manage.py prune_stripe_events --commit
    python manage.py prune_stripe_events --days 90 --commit
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import StripeWebhookEvent

# Stripe retries a failed delivery for about three days. Deleting a row inside that
# window would let a retry be processed as if it were new.
MIN_SAFE_DAYS = 7


class Command(BaseCommand):
    help = 'Delete StripeWebhookEvent rows older than the retention window.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=30,
            help='Retention window in days (default 30, minimum 7).',
        )
        parser.add_argument(
            '--commit', action='store_true',
            help='Apply the deletion. Without this the command only reports.',
        )

    def handle(self, *args, **opts):
        days = opts['days']
        commit = opts['commit']

        if days < MIN_SAFE_DAYS:
            self.stdout.write(self.style.ERROR(
                f'--days must be at least {MIN_SAFE_DAYS}. Stripe retries failed '
                'deliveries for about three days, and deleting a dedup row inside '
                'that window would let a retry be processed twice.'
            ))
            return

        cutoff = timezone.now() - timedelta(days=days)
        old = StripeWebhookEvent.objects.filter(received_at__lt=cutoff)
        total = StripeWebhookEvent.objects.count()
        count = old.count()

        # A row that was claimed but never marked processed is a handler that died
        # mid-flight. Worth seeing before it is swept away.
        unprocessed = old.filter(processed_at=None).count()

        self.stdout.write(f'Total events   : {total}')
        self.stdout.write(f'Older than {days:>3}d : {count}')
        if unprocessed:
            self.stdout.write(self.style.WARNING(
                f'  of which {unprocessed} never completed processing '
                '(handler crashed; these were never retried successfully)'
            ))

        if not commit:
            self.stdout.write(self.style.WARNING(
                f'\nDRY RUN — {count} row(s) would be deleted. Re-run with --commit.'
            ))
            return

        deleted, _ = old.delete()
        self.stdout.write(self.style.SUCCESS(
            f'\nDeleted {deleted} row(s). {total - count} retained.'
        ))

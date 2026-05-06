"""Reset stuck sync_inbox state for one or all accounts.

Used when a previous sync acquired the Redis lock and crashed before
releasing it (worker restart, OOM, network blip, etc.). The lock has a
30-minute TTL by default, so without this command the user has to wait
out the TTL before a fresh sync can run.

Resets two pieces of state:
  - The Redis lock at sync_inbox_lock:account:<id>
  - The EmailAccount.sync_in_progress flag (so the UI banner stops
    pretending a sync is still running)

Usage:
    # Reset one account
    python manage.py reset_sync_lock --account-id=57

    # Reset every account that's flagged sync_in_progress=True
    python manage.py reset_sync_lock --all-stuck
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from marketing_agent.models import EmailAccount
from marketing_agent.management.commands.sync_inbox import (
    _LOCK_KEY_PREFIX,
    _get_redis_client,
)


class Command(BaseCommand):
    help = 'Clear stuck sync_inbox Redis locks + sync_in_progress flags'

    def add_arguments(self, parser):
        parser.add_argument(
            '--account-id', type=int, default=None,
            help='Specific EmailAccount ID to reset.',
        )
        parser.add_argument(
            '--all-stuck', action='store_true',
            help='Reset every account currently flagged sync_in_progress=True.',
        )
        parser.add_argument(
            '--trigger-sync', action='store_true',
            help='Queue an immediate sync_inbox_task for the reset accounts.',
        )

    def handle(self, *args, **options):
        account_id = options.get('account_id')
        all_stuck = options.get('all_stuck')
        trigger = options.get('trigger_sync')

        if not account_id and not all_stuck:
            self.stdout.write(self.style.ERROR(
                'Pass --account-id=<id> or --all-stuck'
            ))
            return

        if all_stuck:
            accounts = EmailAccount.objects.filter(sync_in_progress=True)
        else:
            accounts = EmailAccount.objects.filter(pk=account_id)

        client = _get_redis_client()
        reset_count = 0
        for account in accounts:
            self.stdout.write(f'Resetting account {account.id} ({account.email})...')

            # 1) Clear the Redis lock so the next sync tick can acquire it.
            if client is not None:
                key = f'{_LOCK_KEY_PREFIX}{account.id}'
                try:
                    deleted = client.delete(key)
                    if deleted:
                        self.stdout.write(f'  Cleared Redis lock {key!r}')
                    else:
                        self.stdout.write(f'  No Redis lock at {key!r}')
                except Exception as e:
                    self.stdout.write(self.style.WARNING(
                        f'  Could not delete Redis lock: {e}'
                    ))

            # 2) Clear the sync_in_progress flag so the UI stops showing
            # the "Syncing…" banner. last_sync_stage stays where it was —
            # if a stage had committed, that progress is real.
            EmailAccount.objects.filter(pk=account.pk).update(
                sync_in_progress=False, updated_at=timezone.now(),
            )
            self.stdout.write('  Cleared sync_in_progress flag')

            # 3) Optionally kick off a fresh sync now.
            if trigger:
                try:
                    from marketing_agent.tasks import sync_inbox_task
                    sync_inbox_task.delay(account_id=account.id)
                    self.stdout.write('  Queued sync_inbox_task')
                except Exception as e:
                    self.stdout.write(self.style.WARNING(
                        f'  Could not queue sync: {e}'
                    ))
            reset_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nReset {reset_count} account(s).'
        ))

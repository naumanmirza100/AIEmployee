"""Clear test-mode Stripe IDs before switching to live Stripe keys.

Stripe test mode and live mode are entirely separate object spaces: a `cus_...`,
`sub_...` or `price_...` created with `sk_test_` keys does NOT exist once you
point the app at `sk_live_`. Left in place, those stale ids mean

  - `_ensure_stripe_customer` silently creates duplicate Customers,
  - checkout fails on a `stripe_price_id` that live mode has never heard of,
  - webhook handlers can never match a row by `stripe_subscription_id`.

So this must be run ONCE, after switching keys, before taking real payments.

    python manage.py clear_test_stripe_ids            # dry run — shows counts only
    python manage.py clear_test_stripe_ids --commit   # actually clear

Only rows whose ids look test-mode are touched. Live ids are left alone, so
running it against a live database after go-live is a no-op rather than damage.
After running, `python manage.py sync_stripe_plans` recreates the Products and
Prices in live mode.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import AgentPlan, Company, CompanyModulePurchase

# Stripe stamps test-mode objects with a `_test_` infix (cus_test_..., price_test_...).
# Keys are what carry the plain `sk_test_` prefix, not the object ids, so match the
# infix and treat anything else as live and leave it untouched.
TEST_MARKER = '_test_'


def _is_test_id(value):
    return bool(value) and TEST_MARKER in value


class Command(BaseCommand):
    help = 'Null out test-mode Stripe IDs so live-mode objects can be created cleanly.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--commit', action='store_true',
            help='Apply the changes. Without this the command only reports.',
        )
        parser.add_argument(
            '--all', action='store_true',
            help='Clear EVERY Stripe id regardless of whether it looks test-mode. '
                 'Use only if you know the whole dataset came from test mode.',
        )

    def handle(self, *args, **options):
        commit = options['commit']
        clear_all = options['all']

        def targets(qs, field):
            rows = [r for r in qs if getattr(r, field)]
            if not clear_all:
                rows = [r for r in rows if _is_test_id(getattr(r, field))]
            return rows

        companies = targets(Company.objects.exclude(stripe_customer_id=None), 'stripe_customer_id')
        purchases = targets(
            CompanyModulePurchase.objects.exclude(stripe_subscription_id=None),
            'stripe_subscription_id',
        )
        plans = targets(AgentPlan.objects.exclude(stripe_price_id=None), 'stripe_price_id')

        self.stdout.write(f'Company.stripe_customer_id          : {len(companies)} row(s)')
        self.stdout.write(f'CompanyModulePurchase.stripe_sub_id : {len(purchases)} row(s)')
        self.stdout.write(f'AgentPlan.stripe_price_id           : {len(plans)} row(s)')

        if not commit:
            self.stdout.write(self.style.WARNING(
                '\nDry run — nothing changed. Re-run with --commit to apply.'
            ))
            return

        with transaction.atomic():
            Company.objects.filter(id__in=[c.id for c in companies]).update(stripe_customer_id=None)
            CompanyModulePurchase.objects.filter(id__in=[p.id for p in purchases]).update(
                stripe_subscription_id=None,
                current_period_start=None,
                current_period_end=None,
                cancel_at_period_end=False,
            )
            AgentPlan.objects.filter(id__in=[p.id for p in plans]).update(
                stripe_price_id=None, stripe_product_id=None,
            )

        self.stdout.write(self.style.SUCCESS('\nCleared.'))
        self.stdout.write(
            'Next: run `python manage.py sync_stripe_plans` to recreate Products '
            'and Prices in live mode.'
        )
        if purchases:
            self.stdout.write(self.style.WARNING(
                f'{len(purchases)} purchase(s) lost their subscription link and are now '
                'treated as legacy rows. Check whether any should be re-subscribed.'
            ))

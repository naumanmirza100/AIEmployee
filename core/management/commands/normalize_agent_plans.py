"""Collapse each agent's plans down to one monthly and one yearly.

Plans predate the move to Stripe subscriptions, when an agent could have several
plans that differed by `duration_days` (30 / 90 / 365 days of one-time access).
Stripe bills on the interval and runs until cancelled, so those extra rows are now
the same monthly subscription at different prices, wearing labels that misdescribe
the charge — a "3 months / $7870" plan bills $7870 EVERY month.

This picks one plan per (agent, interval) and DEACTIVATES the rest. It deliberately
does not delete them: a losing row may still own the Stripe Price that a live
subscription is billing against, and deleting it would orphan that subscription.
is_active=False hides it from customers while leaving the billing intact.

Which one wins, in order:
  1. a plan an active subscription is actually using (never strand a payer)
  2. otherwise the cheapest — the junk rows in practice are the absurd ones
     ($9000/mo, $7870/mo), and undercharging beats overcharging if we guess wrong

Free ($0) plans are always deactivated: a $0 recurring price renews forever without
charging, which is indistinguishable from a paying customer until you read the books.

Dry run by default. Pass --commit to apply.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Count

from core.models import AgentPlan, CompanyModulePurchase


class Command(BaseCommand):
    help = 'Collapse each agent to one monthly + one yearly plan (deactivates the rest).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--commit', action='store_true',
            help='Apply the changes. Without this the command only reports.',
        )

    def _live_price_ids(self):
        """Price ids that a real Stripe subscription is billing against.

        Ask Stripe, not the local rows. The previous version inferred this from
        AgentPlan by taking an arbitrary `.first()` for the agent with no interval
        filter — but `stripe_price_id` is overwritten every time a price changes,
        so after any edit the genuinely-live price id is no longer stored on any
        plan row. The "never strand a payer" guarantee silently stopped holding at
        exactly the moment it mattered.
        """
        from django.conf import settings
        import stripe

        secret = getattr(settings, 'STRIPE_SECRET_KEY', None)
        if not secret or secret == 'sk_test_placeholder':
            self.stdout.write(self.style.WARNING(
                'Stripe is not configured — cannot confirm which prices are in use. '
                'Falling back to local data; review the plan carefully before --commit.'
            ))
            return {
                p.stripe_price_id
                for p in AgentPlan.objects.exclude(stripe_price_id=None)
            }, False

        stripe.api_key = secret
        live = set()
        try:
            for sub in stripe.Subscription.list(status='all', limit=100).auto_paging_iter():
                if sub.get('status') not in ('active', 'trialing', 'past_due', 'unpaid'):
                    continue
                for item in (sub.get('items') or {}).get('data') or []:
                    price_id = (item.get('price') or {}).get('id')
                    if price_id:
                        live.add(price_id)
        except stripe.error.StripeError as exc:
            self.stdout.write(self.style.ERROR(
                f'Could not read subscriptions from Stripe: {exc}\n'
                'Refusing to guess which plans are safe to deactivate.'
            ))
            return set(), False
        return live, True

    def handle(self, *args, **opts):
        commit = opts['commit']

        live_price_ids, live_is_authoritative = self._live_price_ids()
        if commit and not live_is_authoritative:
            self.stdout.write(self.style.ERROR(
                '\nRefusing to --commit without an authoritative view of which prices '
                'are in use, since that risks deactivating a plan a customer is paying '
                'for. Fix Stripe access and re-run.'
            ))
            return

        # Any plan row whose price a live subscription uses, plus a report of live
        # prices no plan row owns any more (orphaned by a past price edit).
        owned = {p.stripe_price_id for p in AgentPlan.objects.exclude(stripe_price_id=None)}
        stranded = live_price_ids - owned

        agents = (
            AgentPlan.objects.filter(is_active=True)
            .values('agent_name').annotate(n=Count('id')).order_by('agent_name')
        )

        to_deactivate = []
        keeping = []

        for row in agents:
            agent = row['agent_name']
            for interval in ('month', 'year'):
                plans = list(
                    AgentPlan.objects.filter(
                        agent_name=agent, billing_interval=interval, is_active=True,
                    )
                )
                if not plans:
                    continue

                paid = [p for p in plans if Decimal(p.price_usd) > 0]
                free = [p for p in plans if Decimal(p.price_usd) <= 0]
                to_deactivate.extend(free)  # $0 recurring is never a real plan

                if not paid:
                    continue

                in_use = [p for p in paid if p.stripe_price_id in live_price_ids]
                winner = in_use[0] if in_use else min(paid, key=lambda p: Decimal(p.price_usd))
                keeping.append(winner)
                to_deactivate.extend([p for p in paid if p.id != winner.id])

        self.stdout.write(self.style.MIGRATE_HEADING('\nKEEPING:'))
        for p in sorted(keeping, key=lambda x: (x.agent_name, x.billing_interval)):
            flag = '  (in use by a live subscription)' if p.stripe_price_id in live_price_ids else ''
            self.stdout.write(f'  {p.agent_name:<24} {p.billing_interval:<6} ${p.price_usd}{flag}')

        self.stdout.write(self.style.MIGRATE_HEADING('\nDEACTIVATING:'))
        if not to_deactivate:
            self.stdout.write('  (nothing — plans are already normalized)')
        for p in sorted(to_deactivate, key=lambda x: (x.agent_name, x.billing_interval)):
            why = 'free plan' if Decimal(p.price_usd) <= 0 else 'duplicate interval'
            label = p.label or f'{p.duration_days}d'
            self.stdout.write(
                f'  {p.agent_name:<24} {p.billing_interval:<6} ${p.price_usd:<10} '
                f'[{label}] — {why}'
            )

        # Subscriptions billing against a Price that no plan row owns any more.
        # These are invisible to every other tool: the customer is being charged,
        # but nothing local can name the price they are on.
        if stranded:
            self.stdout.write(self.style.MIGRATE_HEADING('\nLIVE PRICES NOT OWNED BY ANY PLAN:'))
            for price_id in sorted(stranded):
                self.stdout.write(
                    f'  {price_id} — a subscription is billing against this, but no '
                    'AgentPlan row references it (superseded by a price edit).'
                )
            self.stdout.write(
                '  These keep billing correctly; they are listed so you know they exist. '
                'Nothing here is changed by this command.'
            )

        if not commit:
            self.stdout.write(self.style.WARNING(
                f'\nDRY RUN — {len(to_deactivate)} plan(s) would be deactivated. '
                'Re-run with --commit to apply.'
            ))
            return

        ids = [p.id for p in to_deactivate]
        AgentPlan.objects.filter(id__in=ids).update(is_active=False)
        self.stdout.write(self.style.SUCCESS(
            f'\nDeactivated {len(ids)} plan(s). Rows and Stripe Prices are preserved, '
            'so any live subscription keeps billing normally.'
        ))

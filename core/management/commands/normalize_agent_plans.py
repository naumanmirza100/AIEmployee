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

    def handle(self, *args, **opts):
        commit = opts['commit']

        # Price ids that a real subscription is billing against — never deactivate
        # the row that owns one if we can help it.
        live_price_ids = set()
        for pur in CompanyModulePurchase.objects.exclude(stripe_subscription_id=None):
            plan = AgentPlan.objects.filter(
                agent_name=pur.module_name, stripe_price_id__isnull=False,
            ).first()
            if plan and plan.stripe_price_id:
                live_price_ids.add(plan.stripe_price_id)

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

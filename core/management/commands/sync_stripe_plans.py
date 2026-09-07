"""Sync AgentPlans to Stripe Products/Prices.

Run after seeding or editing plans outside the admin UI, or once after deploying:

    python manage.py sync_stripe_plans
    python manage.py sync_stripe_plans --agent recruitment_agent
    python manage.py sync_stripe_plans --dry-run

Safe to run repeatedly — it only creates a Stripe Price when a plan's amount or
interval no longer matches, and archives (never deletes) the superseded one.
"""
from django.core.management.base import BaseCommand

from core.models import AgentPlan


class Command(BaseCommand):
    help = 'Create/update Stripe Products and Prices for active AgentPlans.'

    def add_arguments(self, parser):
        parser.add_argument('--agent', help='Only sync this agent slug.')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would be synced without calling Stripe.',
        )

    def handle(self, *args, **options):
        from core.stripe_sync import sync_agent_plans_to_stripe, sync_stripe_products_and_prices

        agent = options.get('agent')

        if options.get('dry_run'):
            qs = AgentPlan.objects.filter(is_active=True)
            if agent:
                qs = qs.filter(agent_name=agent)
            for plan in qs.order_by('agent_name', 'sort_order'):
                state = 'linked' if plan.stripe_price_id else 'NOT LINKED'
                self.stdout.write(
                    f'  {plan.agent_name:<24} {plan.display_label:<12} '
                    f'${plan.price_usd}/{plan.billing_interval}  [{state}]'
                )
            self.stdout.write(self.style.WARNING('Dry run — nothing sent to Stripe.'))
            return

        count = sync_agent_plans_to_stripe(agent) if agent else sync_stripe_products_and_prices()
        self.stdout.write(self.style.SUCCESS(f'Synced {count} plan(s) to Stripe.'))

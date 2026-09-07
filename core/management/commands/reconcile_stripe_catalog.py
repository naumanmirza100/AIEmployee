"""Compare the Stripe catalogue against AgentPlan and report drift.

Webhooks are a fast path, never a guarantee: a delivery can fail for three days and
then be dropped, the endpoint can be misconfigured, or a change can predate the
handlers existing at all. This is the backstop — it asks Stripe what is actually
there and reports everything that does not line up.

It reports far more than it fixes, on purpose. `--commit` adopts only the one case
whose intent is unambiguous (exactly one active plan, exactly one active matching
Price in Stripe, amounts differ); everything else is printed for a human, because
guessing at a price is guessing at what customers get charged.

    python manage.py reconcile_stripe_catalog            # dry run
    python manage.py reconcile_stripe_catalog --commit
"""
from django.conf import settings
from django.core.management.base import BaseCommand

import stripe

from core.models import AgentPlan


class Command(BaseCommand):
    help = 'Report (and optionally adopt) differences between Stripe and AgentPlan.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--commit', action='store_true',
            help='Adopt unambiguous drift into AgentPlan. Without this, report only.',
        )

    def handle(self, *args, **opts):
        commit = opts['commit']

        secret = getattr(settings, 'STRIPE_SECRET_KEY', None)
        if not secret or secret == 'sk_test_placeholder':
            self.stdout.write(self.style.ERROR('Stripe is not configured.'))
            return
        stripe.api_key = secret

        from core.stripe_sync import adopt_stripe_price

        drift, ambiguous, unlinked, broken = [], [], [], []

        plans = AgentPlan.objects.filter(is_active=True).order_by('agent_name', 'billing_interval')
        for plan in plans:
            if not plan.stripe_price_id:
                unlinked.append(plan)
                continue

            # Does the linked Price still exist and still say what we think?
            try:
                price = stripe.Price.retrieve(plan.stripe_price_id)
            except stripe.error.InvalidRequestError:
                broken.append((plan, 'linked Price no longer exists in Stripe'))
                continue
            except stripe.error.StripeError as exc:
                broken.append((plan, f'could not read Price: {exc}'))
                continue

            local_cents = int(round(float(plan.price_usd) * 100))
            if not price.get('active'):
                broken.append((plan, f'linked Price {price.get("id")} is archived in Stripe'))
            elif price.get('unit_amount') != local_cents:
                drift.append((plan, price))

            # More than one active Price on this Product for this interval means a
            # human added one in the dashboard alongside ours.
            if plan.stripe_product_id:
                try:
                    others = [
                        p for p in stripe.Price.list(
                            product=plan.stripe_product_id, active=True, limit=100,
                        ).auto_paging_iter()
                        if (p.get('recurring') or {}).get('interval') == plan.billing_interval
                    ]
                except stripe.error.StripeError:
                    others = []
                if len(others) > 1:
                    ambiguous.append((plan, others))

        # ---- report -------------------------------------------------------
        def head(text):
            self.stdout.write(self.style.MIGRATE_HEADING(f'\n{text}'))

        if drift:
            head('PRICE DIFFERS BETWEEN STRIPE AND US:')
            for plan, price in drift:
                self.stdout.write(
                    f'  {plan.agent_name:<24} {plan.billing_interval:<6} '
                    f'local ${plan.price_usd}  ->  Stripe ${(price.get("unit_amount") or 0) / 100}'
                )

        if ambiguous:
            head('MORE THAN ONE ACTIVE PRICE (needs a human):')
            for plan, others in ambiguous:
                ids = ', '.join(
                    f'{p.get("id")} (${(p.get("unit_amount") or 0) / 100})' for p in others
                )
                self.stdout.write(f'  {plan.agent_name:<24} {plan.billing_interval:<6} {ids}')
            self.stdout.write(
                '  Not adopted — with two candidates there is no way to know which '
                'price you meant. Archive the wrong one in Stripe, then re-run.'
            )

        if broken:
            head('BROKEN LINKS:')
            for plan, why in broken:
                self.stdout.write(f'  {plan.agent_name:<24} {plan.billing_interval:<6} {why}')
            self.stdout.write(
                '  Run `python manage.py sync_stripe_plans` to mint a replacement Price.'
            )

        if unlinked:
            head('PLANS WITH NO STRIPE PRICE (not buyable):')
            for plan in unlinked:
                self.stdout.write(
                    f'  {plan.agent_name:<24} {plan.billing_interval:<6} ${plan.price_usd}'
                )
            self.stdout.write('  Run `python manage.py sync_stripe_plans` to create them.')

        if not (drift or ambiguous or broken or unlinked):
            self.stdout.write(self.style.SUCCESS('\nIn sync — nothing to report.'))
            return

        if not commit:
            self.stdout.write(self.style.WARNING(
                f'\nDRY RUN — {len(drift)} price(s) would be adopted from Stripe. '
                f'{len(ambiguous) + len(broken) + len(unlinked)} item(s) need a human either way. '
                'Re-run with --commit to adopt.'
            ))
            return

        adopted = 0
        for plan, price in drift:
            # notify=False: this command already prints everything it refused, and a
            # single run can hit the same refusal for many plans — sending an admin
            # notification per row would bury the alerts the webhook path raises.
            result = adopt_stripe_price(price, notify=False)
            self.stdout.write(f'  {plan.agent_name} {plan.billing_interval}: {result}')
            if result == 'adopted':
                adopted += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nAdopted {adopted} price(s). Existing subscribers move at their next '
            'renewal and have been notified.'
        ))

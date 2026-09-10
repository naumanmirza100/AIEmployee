"""Stripe Product/Price synchronisation for AgentPlans.

One Stripe Product per agent, one Stripe Price per plan.

The important constraint: **Stripe Prices are immutable.** You cannot edit an
amount or interval. Changing what a plan costs therefore means minting a NEW
Price and archiving the old one — existing subscribers stay on the Price they
signed up at, which is the grandfathering behaviour you want, and new checkouts
use the new one.

This is invoked explicitly — from `save_agent_plans` after an admin edit, and
from the `sync_stripe_plans` management command — deliberately NOT from
AppConfig.ready(). Startup is the wrong place: `ready()` fires in every gunicorn
worker, every celery worker and every `manage.py` invocation, so concurrent
workers race to create duplicate Products, and it fires during `migrate` before
the columns it reads even exist.
"""
import logging

import stripe
from django.conf import settings

logger = logging.getLogger(__name__)


def _stripe_ready():
    """True when a usable Stripe secret key is configured."""
    secret_key = getattr(settings, 'STRIPE_SECRET_KEY', None)
    if not secret_key or secret_key == 'sk_test_placeholder':
        logger.info('Stripe not configured; skipping product/price sync.')
        return False
    stripe.api_key = secret_key
    return True


def _price_matches(price, plan):
    """True when an existing Stripe Price still represents this plan's terms.

    Compared in integer cents — never floats — so 0.1 + 0.2 style drift can't
    make an identical price look changed and mint a needless new Price.
    """
    if not price:
        return False
    want_cents = int(round(float(plan.price_usd) * 100))
    recurring = price.get('recurring') or {}
    return (
        price.get('unit_amount') == want_cents
        and price.get('currency') == 'usd'
        and recurring.get('interval') == (plan.billing_interval or 'month')
        and price.get('active')
    )


def _archive_price(price_id):
    """Deactivate a Stripe Price. Never delete — subscriptions still reference it."""
    if not price_id:
        return
    try:
        stripe.Price.modify(price_id, active=False)
        logger.info('Archived Stripe Price %s', price_id)
    except stripe.error.InvalidRequestError:
        logger.info('Stripe Price %s already gone; nothing to archive.', price_id)
    except stripe.error.StripeError as exc:
        logger.warning('Could not archive Stripe Price %s: %s', price_id, exc)


def _ensure_product(agent_name, existing_product_id=None):
    """Find-or-create the Stripe Product for one agent. Returns its id or None."""
    from core.models import MODULE_DISPLAY_NAMES

    display_name = MODULE_DISPLAY_NAMES.get(agent_name, agent_name)

    if existing_product_id:
        try:
            product = stripe.Product.retrieve(existing_product_id)
            if product.get('active'):
                return existing_product_id
        except stripe.error.InvalidRequestError:
            pass  # deleted in the dashboard; fall through and recreate

    # Reuse a Product previously created for this agent rather than making a
    # duplicate — this is what makes a concurrent second caller converge on the
    # same Product instead of creating its own.
    try:
        found = stripe.Product.search(query=f"metadata['agent_name']:'{agent_name}' AND active:'true'", limit=1)
        if found and found.get('data'):
            return found['data'][0]['id']
    except stripe.error.StripeError as exc:
        logger.debug('Product search unavailable for %s (%s); creating.', agent_name, exc)

    try:
        product = stripe.Product.create(
            name=display_name,
            description=f'{display_name} — AI Agent subscription',
            metadata={'agent_name': agent_name},
        )
        logger.info('Created Stripe Product %s for %s', product.id, agent_name)
        return product.id
    except stripe.error.StripeError as exc:
        logger.error('Failed to create Stripe Product for %s: %s', agent_name, exc)
        return None


def sync_agent_plans_to_stripe(agent_name, archive_prices_for=None):
    """Reconcile one agent's active AgentPlans with Stripe.

    `archive_prices_for` is an iterable of AgentPlan rows the caller has already
    deleted locally; their Stripe Prices get archived so they can't be checked
    out against. Returns the number of plans synced.
    """
    from core.models import AgentPlan

    if not _stripe_ready():
        return 0

    for dead in (archive_prices_for or []):
        _archive_price(getattr(dead, 'stripe_price_id', None))

    plans = list(
        AgentPlan.objects.filter(agent_name=agent_name, is_active=True)
        .order_by('sort_order', 'duration_days')
    )
    if not plans:
        return 0

    seed_product = next((p.stripe_product_id for p in plans if p.stripe_product_id), None)
    product_id = _ensure_product(agent_name, seed_product)
    if not product_id:
        return 0

    synced = 0
    for plan in plans:
        existing_price = None
        if plan.stripe_price_id:
            try:
                existing_price = stripe.Price.retrieve(plan.stripe_price_id)
            except stripe.error.InvalidRequestError:
                existing_price = None
            except stripe.error.StripeError as exc:
                logger.warning('Could not read Stripe Price %s: %s', plan.stripe_price_id, exc)
                continue

        # Still correct and on the right Product? Nothing to do.
        if _price_matches(existing_price, plan) and plan.stripe_product_id == product_id:
            synced += 1
            continue

        try:
            price = stripe.Price.create(
                product=product_id,
                unit_amount=int(round(float(plan.price_usd) * 100)),
                currency='usd',
                recurring={'interval': plan.billing_interval or 'month'},
                metadata={'agent_name': agent_name, 'plan_id': str(plan.id)},
            )
        except stripe.error.StripeError as exc:
            logger.error('Failed to create Stripe Price for plan %s: %s', plan.id, exc)
            continue

        # Archive the superseded Price only after the replacement exists, so a
        # failure above can never leave the plan with no usable price at all.
        if existing_price and existing_price.get('id') != price.id:
            _archive_price(existing_price['id'])

        plan.stripe_product_id = product_id
        plan.stripe_price_id = price.id
        plan.save(update_fields=['stripe_product_id', 'stripe_price_id', 'updated_at'])
        synced += 1
        logger.info('Synced plan %s → Stripe Price %s (%s $%s)',
                    plan.id, price.id, plan.billing_interval, plan.price_usd)

    return synced


def sync_stripe_products_and_prices():
    """Reconcile every agent's active plans with Stripe. Returns total synced."""
    from core.models import AgentPlan

    if not _stripe_ready():
        return 0

    agent_names = (
        AgentPlan.objects.filter(is_active=True)
        .values_list('agent_name', flat=True).distinct()
    )
    total = 0
    for agent_name in agent_names:
        total += sync_agent_plans_to_stripe(agent_name)
    logger.info('Stripe sync complete: %d plan(s) synced.', total)
    return total

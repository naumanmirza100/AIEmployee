"""Stripe Product/Price synchronisation for AgentPlans.

One Stripe Product per agent, one Stripe Price per plan.

The important constraint: **Stripe Prices are immutable.** You cannot edit an
amount or interval. Changing what a plan costs therefore means minting a NEW
Price and archiving the old one.

Existing subscribers are then MIGRATED onto the new Price, taking effect at their
next renewal — next month for a monthly plan, next year for a yearly one — with
no mid-cycle proration. (This replaces the earlier grandfathering behaviour, where
a subscriber kept their original price indefinitely and the admin's edit applied
only to new customers. That produced cohorts paying different amounts for the same
agent, and a price shown in the admin UI that nobody was actually being charged.)
Affected companies are notified in-app; see `_notify_price_change`.

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


def _find_existing_price(product_id, plan):
    """An existing ACTIVE Price on this Product matching the plan's terms, or None.

    Without this the sync churns. `_price_matches` requires `active`, so the moment
    a plan's linked Price is archived — by a previous sync, or by hand in the
    dashboard — the match fails and a brand-new Price is minted. Repeat that on
    every save and one agent ends up with a stack of near-identical Prices (this is
    how Recruitment Agent reached seven).

    Find-or-create makes the sync converge instead, the same discipline
    `_ensure_product` already applies to Products.
    """
    try:
        for price in stripe.Price.list(product=product_id, active=True, limit=100).auto_paging_iter():
            if _price_matches(price, plan):
                return price
    except stripe.error.StripeError as exc:
        logger.warning('Could not list Prices for product %s: %s', product_id, exc)
    return None


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


def _notify_price_change(subscription, agent_name, old_cents, new_cents):
    """Tell a company its agent price changed, and when it takes effect.

    Mirrors the failed-payment notification in module_purchase.py. severity is
    'warning', not 'critical' — critical is reserved for things that break access.
    """
    # datetime.timezone.utc, not django.utils.timezone.utc — the Django alias is
    # deprecated in 4.2 and removed in 5.0, and this whole function is wrapped in a
    # try/except that only logs, so on upgrade the price migration would keep
    # succeeding while every customer notification silently vanished.
    from datetime import datetime, timezone as dt_timezone
    from core.models import Company, CompanyUser, MODULE_DISPLAY_NAMES

    display = MODULE_DISPLAY_NAMES.get(agent_name, agent_name)
    customer_id = subscription.get('customer')
    company = Company.objects.filter(stripe_customer_id=customer_id).first()
    if not company:
        logger.warning('Price change: no company for Stripe customer %s', customer_id)
        return

    # The effective date is per-subscriber — it is their own renewal, not a date
    # shared across the account — so read it off this subscription.
    period_end = subscription.get('current_period_end')
    if not period_end:
        items = (subscription.get('items') or {}).get('data') or [{}]
        period_end = items[0].get('current_period_end')
    effective = (
        datetime.fromtimestamp(int(period_end), tz=dt_timezone.utc)
        if period_end else None
    )
    when = effective.strftime('%d %b %Y') if effective else 'your next renewal'

    old_amount = f'${old_cents / 100:.2f}'
    new_amount = f'${new_cents / 100:.2f}'
    direction = 'increase' if new_cents > old_cents else 'decrease'

    try:
        from project_manager_agent.models import PMNotification
        for cu in CompanyUser.objects.filter(company=company, is_active=True):
            PMNotification.objects.create(
                company_user=cu,
                notification_type='custom',
                severity='warning',
                title=f'Price change — {display}',
                message=(
                    f'The subscription price for {display} will {direction} from '
                    f'{old_amount} to {new_amount}. This takes effect on {when}, at '
                    f'your next renewal — you will not be charged anything extra before then.'
                ),
                data={
                    'module_name': agent_name,
                    'old_price': old_cents / 100,
                    'new_price': new_cents / 100,
                    'effective_at': effective.isoformat() if effective else None,
                },
            )
    except Exception as exc:
        logger.warning('Could not notify company %s of price change: %s', company.id, exc)


def _migrate_subscriptions_to_price(old_price_id, new_price, agent_name):
    """Move live subscriptions from a superseded Price onto the new one.

    `proration_behavior='none'` is the whole point: the new amount is picked up by
    the NEXT invoice rather than generating an immediate prorated charge or credit.
    A monthly subscriber changes next month, a yearly one next year, and nobody is
    billed a surprise amount today.

    Called after the replacement Price exists and before the old one is archived.
    """
    if not old_price_id:
        return 0

    # Dict access throughout: this is called both with a StripeObject (from our own
    # Price.create) and with raw webhook event data, and only dict access works for
    # both.
    new_price_id = new_price.get('id')
    new_unit_amount = new_price.get('unit_amount') or 0

    migrated = 0
    try:
        subs = stripe.Subscription.list(price=old_price_id, status='all', limit=100)
        for sub in subs.auto_paging_iter():
            if sub.get('status') not in ('active', 'trialing', 'past_due', 'unpaid'):
                continue
            item = next(
                (i for i in ((sub.get('items') or {}).get('data') or [])
                 if (i.get('price') or {}).get('id') == old_price_id),
                None,
            )
            if not item:
                continue
            old_cents = (item.get('price') or {}).get('unit_amount') or 0
            try:
                stripe.Subscription.modify(
                    sub['id'],
                    items=[{'id': item['id'], 'price': new_price_id}],
                    proration_behavior='none',
                    billing_cycle_anchor='unchanged',
                )
            except stripe.error.StripeError as exc:
                logger.error('Could not migrate subscription %s to price %s: %s',
                             sub.get('id'), new_price_id, exc)
                continue

            migrated += 1
            logger.info('Migrated subscription %s from %s to %s (effective next renewal)',
                        sub.get('id'), old_price_id, new_price_id)
            _notify_price_change(sub, agent_name, old_cents, new_unit_amount)
    except stripe.error.StripeError as exc:
        logger.error('Could not list subscriptions on price %s: %s', old_price_id, exc)

    return migrated


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

        # Adopt an equivalent Price already on this Product before minting another.
        price = _find_existing_price(product_id, plan)
        if price is None:
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

        # Move existing subscribers onto the new Price, effective at their next
        # renewal. Done BEFORE archiving the old Price: Stripe will not accept a
        # subscription update that points at an inactive price.
        if existing_price and existing_price.get('id') != price.id:
            moved = _migrate_subscriptions_to_price(existing_price['id'], price, agent_name)
            if moved:
                logger.info('Price change for %s (%s): %d subscription(s) move at next renewal',
                            agent_name, plan.billing_interval, moved)

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


# ---------------------------------------------------------------------------
# Stripe → app: adopt catalogue edits made in the dashboard
# ---------------------------------------------------------------------------
#
# The catalogue is owned by AgentPlan and pushed to Stripe, but a human can still
# edit a Price in the dashboard, and until now that change never came back — the
# admin UI would show one amount while Stripe charged another.
#
# This adopts such a change ONLY when its intent is unambiguous. It is deliberately
# not a general two-way sync: Stripe Prices are immutable, so a dashboard "edit" is
# really a new object, and with two candidates there is no way to know which one the
# admin meant.

def _agent_for_product(product_id):
    """The agent a Stripe Product belongs to, from its metadata. None if not ours."""
    try:
        product = stripe.Product.retrieve(product_id)
    except stripe.error.StripeError as exc:
        logger.warning('Could not retrieve Stripe Product %s: %s', product_id, exc)
        return None
    return (product.get('metadata') or {}).get('agent_name') or None


def _alert_admins_unadopted(title, message):
    """Tell staff about a dashboard price edit we refused to act on.

    Without this the refusal is a log line nobody reads, and the admin who made the
    edit in Stripe is left believing it took effect. notify_admins swallows its own
    exceptions, so this can never fail the webhook handler or roll back its
    transaction.
    """
    try:
        from core.notification_utils import notify_admins
        notify_admins(
            title=title,
            message=message,
            action_url='/admin/agent-plans',
            notification_type='admin_action',
        )
    except Exception as exc:  # import-time failure only
        logger.warning('Could not alert admins about unadopted price: %s', exc)


def adopt_stripe_price(price, notify=True):
    """Adopt a dashboard-made Price into AgentPlan. Returns a short status string.

    The echo-loop breaker is `metadata.plan_id`: every Price this app mints carries
    one, a hand-made Price does not. So our own writes coming back as webhooks are
    recognised and ignored, and only genuine external edits are considered.

    Adoption is also idempotent — writing a value that already matches is a no-op —
    so a replayed event cannot cause drift.

    `notify=False` suppresses the admin alerts raised when adoption is refused. The
    reconcile command passes it: that command already prints a full report, and it
    can hit the same refusal for every plan in a single run, which would bury real
    alerts under its own output.
    """
    from core.models import AgentPlan, MODULE_DISPLAY_NAMES

    price_id = price.get('id')
    metadata = price.get('metadata') or {}

    if metadata.get('plan_id'):
        return 'ours'  # our own sync, echoed back

    if not price.get('active'):
        return 'inactive'

    recurring = price.get('recurring') or {}
    interval = recurring.get('interval')
    if interval not in ('month', 'year'):
        return 'not_recurring'

    if price.get('currency') != 'usd':
        currency = (price.get('currency') or '?').upper()
        logger.warning('Ignoring Stripe Price %s: currency %s is not supported.',
                       price_id, currency)
        if notify:
            _alert_admins_unadopted(
                title='Stripe price ignored — unsupported currency',
                message=(
                    f'A {currency} price ({price_id}) was created in Stripe, but this '
                    'platform bills in USD only, so it was not applied. Nothing has '
                    'changed. Create the price in USD if it was intended.'
                ),
            )
        return 'wrong_currency'

    product_id = price.get('product')
    if isinstance(product_id, dict):
        product_id = product_id.get('id')
    agent_name = _agent_for_product(product_id) if product_id else None
    if not agent_name:
        return 'not_ours'  # a Product we did not create

    plans = list(AgentPlan.objects.filter(
        agent_name=agent_name, billing_interval=interval, is_active=True,
    ))
    if len(plans) != 1:
        # 0 -> no plan to attach it to; >1 should be impossible now that the
        # uniqueness constraint exists, but refuse rather than pick one.
        logger.warning(
            'Not adopting Stripe Price %s: found %d active %s plan(s) for %s. '
            'Resolve this in the admin UI or run reconcile_stripe_catalog.',
            price_id, len(plans), interval, agent_name,
        )
        if notify:
            display = MODULE_DISPLAY_NAMES.get(agent_name, agent_name)
            amount = (price.get('unit_amount') or 0) / 100
            period = 'yearly' if interval == 'year' else 'monthly'
            if not plans:
                detail = (
                    f'there is no active {period} plan for {display} to apply it to. '
                    f'Create one in Agent Plans, or archive the price in Stripe.'
                )
            else:
                detail = (
                    f'{display} has {len(plans)} active {period} plans, so there is no '
                    'way to tell which one you meant. Resolve the duplicates first.'
                )
            _alert_admins_unadopted(
                title=f'Stripe price change not applied — {display}',
                message=(
                    f'A ${amount:.2f}/{interval} price ({price_id}) was set in the '
                    f'Stripe dashboard but was NOT applied, because {detail} '
                    'Customers are still being charged the existing price.'
                ),
            )
        return 'ambiguous'

    plan = plans[0]
    amount = (price.get('unit_amount') or 0) / 100

    if plan.stripe_price_id == price_id and float(plan.price_usd) == amount:
        return 'unchanged'  # idempotent replay

    old_price_id = plan.stripe_price_id
    old_amount = float(plan.price_usd)
    plan.stripe_price_id = price_id
    plan.price_usd = amount
    if product_id:
        plan.stripe_product_id = product_id
    plan.save(update_fields=['stripe_price_id', 'price_usd', 'stripe_product_id', 'updated_at'])

    logger.info('Adopted Stripe Price %s for %s (%s): $%s -> $%s',
                price_id, agent_name, interval, old_amount, amount)

    # Same treatment a price change made in our own admin gets: move existing
    # subscribers at their next renewal and tell them. Skipped when the plan had no
    # price yet — there is nobody on it to move.
    if old_price_id and old_price_id != price_id:
        _migrate_subscriptions_to_price(old_price_id, price, agent_name)
        _archive_price(old_price_id)

    return 'adopted'

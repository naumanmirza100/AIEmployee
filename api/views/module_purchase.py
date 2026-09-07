"""
Module Purchase API Views — Stripe Recurring Subscription Flow

Subscription lifecycle:
  User subscribes → Stripe creates recurring subscription →
  Stripe automatically charges every billing cycle →
  subscription remains active → access continues →
  user can cancel → subscription cancelled at period end →
  access removed after billing period ends.

Stripe is the source of truth for billing state.  Local DB stores/synchronizes
relevant Stripe information via webhooks.
"""
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

import stripe

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.models import (
    CompanyUser, CompanyModulePurchase, Company, AgentPlan,
    MODULE_DISPLAY_NAMES,
)

logger = logging.getLogger(__name__)

stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', None)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_plan(p):
    """Shape one AgentPlan for the buy flow."""
    return {
        'id': p.id,
        'duration_days': p.duration_days,
        'price_usd': float(p.price_usd),
        'label': p.display_label,
        'billing_interval': p.billing_interval,
        'stripe_price_id': p.stripe_price_id,
    }


def _active_plans_for(module_name):
    """Active AgentPlans for a module, cheapest/shortest first."""
    return list(
        AgentPlan.objects.filter(agent_name=module_name, is_active=True)
        .order_by('sort_order', 'duration_days')
    )


def _format_duration(delta):
    """Render a timedelta down to the minute, e.g. '29d 10h 45m', '10h 45m', '45m'."""
    total_minutes = int(delta.total_seconds() // 60)
    days, rem_minutes = divmod(total_minutes, 1440)
    hours, minutes = divmod(rem_minutes, 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{max(minutes, 1)}m"


# Module pricing configuration (USD) — kept for backward compat / display
MODULE_PRICES = {
    'recruitment_agent': 99,
    'marketing_agent': 149,
    'project_manager_agent': 199,
    'frontline_agent': 149,
    'operations_agent': 179,
    'reply_draft_agent': 79,
    'hr_agent': 129,
    'ai_sdr_agent': 199,
    'crm_sync_agent': 99,
    'exec_meeting_agent': 179,
}


def _ensure_stripe_customer(company):
    """Find or create a Stripe Customer for the company.  Stores the ID on the Company."""
    if company.stripe_customer_id:
        try:
            stripe.Customer.retrieve(company.stripe_customer_id)
            return company.stripe_customer_id
        except stripe.error.InvalidRequestError:
            pass  # deleted in dashboard; recreate

    customer = stripe.Customer.create(
        name=company.name,
        email=getattr(company, 'email', None) or '',
        metadata={'company_id': str(company.id), 'source': 'platform'},
    )
    company.stripe_customer_id = customer.id
    company.save(update_fields=['stripe_customer_id'])
    logger.info('Created Stripe Customer %s for company %s (%s)', customer.id, company.name, company.id)
    return customer.id


def _ts_to_dt(ts):
    """Stripe epoch seconds → aware UTC datetime, or None."""
    if not ts:
        return None
    return datetime.fromtimestamp(int(ts), tz=dt_timezone.utc)


def _extract_period(subscription):
    """Read (current_period_start, current_period_end) off a Stripe Subscription.

    Stripe MOVED these fields between API versions: up to 2024 they sit on the
    subscription itself, and from the 2025 versions they sit on each subscription
    *item* instead.  Which one we get depends on two independent things — the
    version pinned by the `stripe` library (used for our own `.retrieve()` calls)
    and the version configured on the webhook endpoint in the dashboard — so they
    can legitimately disagree within one deployment.

    Reading top-level first with an item-level fallback works on every version and
    survives both a library upgrade and a dashboard endpoint change.  Returning
    (None, None) here is what previously left `current_period_end` NULL, which made
    `is_active()` return True forever.
    """
    if not subscription:
        return None, None

    start = _ts_to_dt(subscription.get('current_period_start'))
    end = _ts_to_dt(subscription.get('current_period_end'))
    if start and end:
        return start, end

    items = (subscription.get('items') or {}).get('data') or []
    if items:
        start = start or _ts_to_dt(items[0].get('current_period_start'))
        end = end or _ts_to_dt(items[0].get('current_period_end'))

    if not end:
        logger.warning(
            'Stripe subscription %s: no current_period_end on the subscription or its '
            'items. Access expiry cannot be enforced for this row.',
            subscription.get('id'),
        )
    return start, end


def _extract_interval(subscription):
    """Read the recurring interval ('month'/'year') off a Stripe Subscription.

    A subscription item's `plan` exposes `interval` directly; only a `price`
    object nests it under `recurring`. Check both so either shape resolves.
    """
    items = ((subscription or {}).get('items') or {}).get('data') or []
    if not items:
        return None
    item = items[0]
    interval = (
        (item.get('plan') or {}).get('interval')
        or ((item.get('price') or {}).get('recurring') or {}).get('interval')
    )
    if not interval:
        return None
    return 'year' if interval == 'year' else 'month'


def _serialize_purchase(purchase, now):
    """Serialize a CompanyModulePurchase for the API response."""
    is_subscription = bool(purchase.stripe_subscription_id)

    # Determine effective status
    effective_status = purchase.status
    is_expired = purchase.status == 'expired'

    # Determine the reference date for time calculations
    ref_date = purchase.current_period_end if (is_subscription and purchase.current_period_end) else purchase.expires_at

    # Compute time remaining or time since expired
    time_remaining = None
    time_ended_ago = None
    if ref_date:
        if effective_status == 'active':
            diff = ref_date - now
            if diff.total_seconds() > 0:
                time_remaining = f"{_format_duration(diff)} remaining"
            else:
                is_expired = True
                effective_status = 'expired'
        if effective_status in ('expired',):
            ended = now - ref_date
            if ended.total_seconds() > 0:
                time_ended_ago = f"Ended {_format_duration(ended)} ago"

    # Active duration
    if effective_status == 'active':
        delta = now - purchase.purchased_at
        days_val = delta.days
    elif ref_date and is_expired:
        delta = ref_date - purchase.purchased_at
        days_val = delta.days
    elif purchase.cancelled_at:
        delta = purchase.cancelled_at - purchase.purchased_at
        days_val = delta.days
    else:
        delta = now - purchase.purchased_at
        days_val = delta.days

    if days_val > 365:
        active_duration = f"{days_val // 365}y {(days_val % 365) // 30}m"
    elif days_val > 30:
        active_duration = f"{days_val // 30}m {days_val % 30}d"
    else:
        active_duration = f"{days_val}d"

    if effective_status == 'active':
        active_label = f"Active since: {active_duration}"
    else:
        active_label = f"Was active for {active_duration}"

    return {
        'id': purchase.id,
        'module_name': purchase.module_name,
        'module_display_name': purchase.get_module_name_display(),
        'status': effective_status,
        'subscription_status_label': purchase.subscription_status_label,
        'purchased_at': purchase.purchased_at.isoformat(),
        'expires_at': purchase.expires_at.isoformat() if purchase.expires_at else None,
        'cancelled_at': purchase.cancelled_at.isoformat() if purchase.cancelled_at else None,
        'cancelled_reason': purchase.cancelled_reason,
        'history_kept': purchase.history_kept,
        'price_paid': float(purchase.price_paid) if purchase.price_paid else None,
        'purchased_by_name': purchase.purchased_by.full_name if purchase.purchased_by else None,
        'is_expired': is_expired,
        'deactivated_by_admin': purchase.cancelled_reason == 'admin_deactivated',
        'time_remaining': time_remaining,
        'time_ended_ago': time_ended_ago,
        'active_label': active_label,
        # Stripe subscription fields
        'is_subscription': is_subscription,
        'billing_interval': purchase.billing_interval,
        'current_period_start': purchase.current_period_start.isoformat() if purchase.current_period_start else None,
        'current_period_end': purchase.current_period_end.isoformat() if purchase.current_period_end else None,
        'cancel_at_period_end': purchase.cancel_at_period_end,
        'is_complimentary': purchase.is_complimentary,
        'next_billing_date': purchase.current_period_end.isoformat() if (is_subscription and purchase.current_period_end and purchase.status == 'active') else None,
    }


# ---------------------------------------------------------------------------
# Fulfillment — called from webhook and verify_session
# ---------------------------------------------------------------------------

def _fulfill_purchase_from_metadata(metadata, subscription=None):
    """Create or update CompanyModulePurchase from Stripe metadata.

    When `subscription` is provided (from Stripe webhook), stores the
    subscription IDs and billing period.  Idempotent.
    """
    company_id = metadata.get('company_id')
    company_user_id = metadata.get('company_user_id')
    module_name = metadata.get('module_name')
    if not company_id or not module_name:
        return False, 'invalid_metadata'
    if module_name not in MODULE_PRICES:
        return False, 'invalid_module'

    try:
        company = Company.objects.get(pk=int(company_id))
    except (Company.DoesNotExist, ValueError, TypeError):
        return False, 'company_not_found'

    purchased_by = None
    if company_user_id:
        try:
            purchased_by = CompanyUser.objects.get(pk=int(company_user_id), company=company)
        except (CompanyUser.DoesNotExist, ValueError, TypeError):
            pass

    # Price from the admin-defined AgentPlan
    price = MODULE_PRICES[module_name]
    billing_interval = None
    plan_id = metadata.get('plan_id')
    if plan_id:
        try:
            plan = AgentPlan.objects.get(pk=int(plan_id), agent_name=module_name)
            price = float(plan.price_usd)
            billing_interval = plan.billing_interval
        except (AgentPlan.DoesNotExist, ValueError, TypeError):
            logger.warning('Fulfill: plan_id %s not found for %s; using legacy price', plan_id, module_name)

    # Subscription data from Stripe
    stripe_sub_id = None
    period_start = None
    period_end = None
    if subscription:
        stripe_sub_id = subscription.get('id')
        period_start, period_end = _extract_period(subscription)
        # Derive billing_interval from Stripe if the plan didn't give us one
        if not billing_interval:
            billing_interval = _extract_interval(subscription)

    # For legacy one-time purchases (no subscription), keep expires_at
    expires_at = None
    if not stripe_sub_id:
        duration_days = metadata.get('duration_days') or 30
        try:
            duration_days = int(duration_days)
        except (ValueError, TypeError):
            duration_days = 30
        expires_at = timezone.now() + timedelta(days=duration_days)

    existing = CompanyModulePurchase.objects.filter(company=company, module_name=module_name).first()
    if existing:
        # Update existing record
        update_fields = ['status', 'price_paid', 'updated_at']
        existing.status = 'active'
        existing.price_paid = price
        existing.cancelled_at = None
        existing.cancelled_reason = None
        existing.history_kept = None

        if stripe_sub_id:
            # Stripe subscription — update subscription fields
            existing.stripe_subscription_id = stripe_sub_id
            existing.current_period_start = period_start
            existing.current_period_end = period_end
            existing.cancel_at_period_end = False
            existing.billing_interval = billing_interval
            update_fields += [
                'stripe_subscription_id', 'current_period_start', 'current_period_end',
                'cancel_at_period_end', 'billing_interval',
            ]
        else:
            # Legacy one-time purchase
            existing.expires_at = expires_at
            existing.stripe_subscription_id = None
            existing.current_period_start = None
            existing.current_period_end = None
            existing.cancel_at_period_end = False
            existing.billing_interval = None
            update_fields += [
                'expires_at', 'stripe_subscription_id', 'current_period_start',
                'current_period_end', 'cancel_at_period_end', 'billing_interval',
            ]

        if purchased_by:
            existing.purchased_by = purchased_by
            update_fields.append('purchased_by')

        existing.save(update_fields=update_fields)
        logger.info('Module %s updated for company %s (ID: %s) — sub=%s',
                     module_name, company.name, company.id, bool(stripe_sub_id))
    else:
        purchase = CompanyModulePurchase.objects.create(
            company=company,
            module_name=module_name,
            status='active',
            price_paid=price,
            purchased_by=purchased_by,
            expires_at=expires_at,
            stripe_subscription_id=stripe_sub_id,
            current_period_start=period_start,
            current_period_end=period_end,
            billing_interval=billing_interval,
        )
        logger.info('Module %s created for company %s (ID: %s) — sub=%s',
                     module_name, company.name, company.id, bool(stripe_sub_id))

    # Ensure quota exists — create only if missing, never overwrite existing
    _ensure_quota(company, module_name)

    return True, module_name


def _ensure_quota(company, module_name):
    """Create AgentTokenQuota if missing. Idempotent."""
    from core.models import AgentTokenQuota, AdminPricingConfig, DEFAULT_FREE_TOKENS
    try:
        cfg = AdminPricingConfig.objects.get(agent_name=module_name)
        free_tokens = cfg.free_tokens_on_purchase
    except AdminPricingConfig.DoesNotExist:
        free_tokens = DEFAULT_FREE_TOKENS

    _, created = AgentTokenQuota.objects.get_or_create(
        company=company,
        agent_name=module_name,
        defaults={'included_tokens': free_tokens},
    )
    if created:
        logger.info('Fresh quota created for %s company %s', module_name, company.name)


# ---------------------------------------------------------------------------
# API Views — Purchased modules & access checks
# ---------------------------------------------------------------------------

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_purchased_modules(request):
    """Get list of modules purchased by the company."""
    try:
        company = request.user.company
        now = timezone.now()

        # For legacy purchases (no Stripe subscription), auto-expire if past expires_at
        # Locally-owned expiry only: legacy one-time purchases and admin-granted
        # complimentary access. Live Stripe subscriptions expire via webhooks.
        CompanyModulePurchase.objects.filter(
            Q(stripe_subscription_id__isnull=True) | Q(is_complimentary=True),
            company=company, status='active',
            expires_at__isnull=False, expires_at__lt=now,
        ).update(status='expired')

        all_purchases = CompanyModulePurchase.objects.filter(
            company=company,
        ).select_related('purchased_by').order_by('-purchased_at')

        active_purchases = []
        all_purchases_data = []

        for purchase in all_purchases:
            purchase_data = _serialize_purchase(purchase, now)
            all_purchases_data.append(purchase_data)
            if purchase.is_active():
                active_purchases.append(purchase_data)

        return Response({
            'status': 'success',
            'purchased_modules': active_purchases,
            'all_purchases': all_purchases_data,
            'module_names': [p['module_name'] for p in active_purchases],
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error('Error getting purchased modules: %s', str(e), exc_info=True)
        return Response({
            'status': 'error',
            'message': f'Failed to get purchased modules: {str(e)}',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def check_module_access(request, module_name):
    """Check if company has access to a specific module."""
    try:
        company = request.user.company

        try:
            purchase = CompanyModulePurchase.objects.get(
                company=company, module_name=module_name,
            )
            has_access = purchase.is_active()

            return Response({
                'status': 'success',
                'has_access': has_access,
                'module_name': module_name,
                'module_display_name': purchase.get_module_name_display(),
                'purchase_status': purchase.status,
                'subscription_status_label': purchase.subscription_status_label,
                'expires_at': purchase.expires_at.isoformat() if purchase.expires_at else None,
                'current_period_end': purchase.current_period_end.isoformat() if purchase.current_period_end else None,
                'cancel_at_period_end': purchase.cancel_at_period_end,
                'is_complimentary': purchase.is_complimentary,
                'is_subscription': bool(purchase.stripe_subscription_id),
                'billing_interval': purchase.billing_interval,
            }, status=status.HTTP_200_OK)

        except CompanyModulePurchase.DoesNotExist:
            return Response({
                'status': 'success',
                'has_access': False,
                'module_name': module_name,
                'module_display_name': MODULE_DISPLAY_NAMES.get(module_name, module_name),
            }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error('Error checking module access: %s', str(e), exc_info=True)
        return Response({
            'status': 'error',
            'message': f'Failed to check module access: {str(e)}',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------------------------------------------------------------------------
# Checkout — Stripe Subscription mode
# ---------------------------------------------------------------------------

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_checkout_session(request):
    """Create a Stripe Checkout Session for a recurring subscription.

    Uses mode='subscription' so Stripe handles recurring billing.
    Creates/retrieves a Stripe Customer for the company.
    """
    try:
        if not stripe.api_key or stripe.api_key == 'sk_test_placeholder':
            return Response({
                'status': 'error',
                'message': 'Stripe is not configured. Set STRIPE_SECRET_KEY in .env.',
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        company_user = request.user
        company = company_user.company
        module_name = request.data.get('module_name')
        if not module_name:
            return Response({
                'status': 'error',
                'message': 'module_name is required',
            }, status=status.HTTP_400_BAD_REQUEST)
        if module_name not in MODULE_PRICES:
            return Response({
                'status': 'error',
                'message': f'Invalid module name. Valid: {", ".join(MODULE_PRICES.keys())}',
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check for existing active subscription
        existing = CompanyModulePurchase.objects.filter(
            company=company, module_name=module_name,
        ).first()
        if existing and existing.is_active():
            return Response({
                'status': 'error',
                'message': f'{MODULE_DISPLAY_NAMES[module_name]} is already active.',
            }, status=status.HTTP_400_BAD_REQUEST)

        # A past_due row is NOT active, but its subscription is still live at
        # Stripe and being retried. Checking out again would open a SECOND
        # subscription and bill the company twice for one agent — send them to
        # the billing portal to fix the card instead.
        if existing and existing.stripe_subscription_id and existing.status == 'past_due':
            return Response({
                'status': 'error',
                'error': 'payment_required',
                'message': (
                    f'{MODULE_DISPLAY_NAMES[module_name]} already has a subscription with a '
                    'failed payment. Please update your payment method instead of subscribing again.'
                ),
            }, status=status.HTTP_409_CONFLICT)

        # A plan is REQUIRED
        plans = _active_plans_for(module_name)
        if not plans:
            return Response({
                'status': 'error',
                'message': f'{MODULE_DISPLAY_NAMES[module_name]} has no plans available yet.',
            }, status=status.HTTP_400_BAD_REQUEST)

        plan_id = request.data.get('plan_id')
        plan = next((p for p in plans if str(p.id) == str(plan_id)), None) if plan_id else None
        if plan is None:
            return Response({
                'status': 'error',
                'message': 'Please choose a plan before subscribing.',
            }, status=status.HTTP_400_BAD_REQUEST)

        if not plan.stripe_price_id:
            return Response({
                'status': 'error',
                'message': 'This plan is not yet configured for Stripe billing. Please try again later.',
            }, status=status.HTTP_400_BAD_REQUEST)

        # Ensure Stripe Customer exists
        customer_id = _ensure_stripe_customer(company)

        frontend_url = (getattr(settings, 'FRONTEND_URL', None) or '').rstrip('/')

        # Create Checkout Session in subscription mode
        session = stripe.checkout.Session.create(
            mode='subscription',
            customer=customer_id,
            line_items=[{
                'price': plan.stripe_price_id,
                'quantity': 1,
            }],
            metadata={
                'company_id': str(company.id),
                'company_user_id': str(company_user.id),
                'module_name': module_name,
                'plan_id': str(plan.id),
                'type': 'module_subscription',
            },
            success_url=f'{frontend_url}/module-purchase-success?session_id={{CHECKOUT_SESSION_ID}}',
            cancel_url=f'{frontend_url}/',
        )

        return Response({
            'status': 'success',
            'url': session.url,
            'session_id': session.id,
        }, status=status.HTTP_200_OK)

    except stripe.error.StripeError as e:
        logger.error('Stripe error creating checkout session: %s', str(e), exc_info=True)
        return Response({
            'status': 'error',
            'message': str(e.user_message) if getattr(e, 'user_message', None) else 'Payment setup failed.',
        }, status=status.HTTP_502_BAD_GATEWAY)
    except Exception as e:
        logger.error('Error creating checkout session: %s', str(e), exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Failed to create checkout session.',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



# ---------------------------------------------------------------------------
# Stripe Webhooks — full subscription lifecycle
# ---------------------------------------------------------------------------

def _invoice_subscription_id(invoice):
    """Read the subscription id off a Stripe Invoice, across API versions.

    Older versions put it at `invoice.subscription`; the 2025 versions moved it to
    `invoice.parent.subscription_details.subscription`. Same reasoning as
    `_extract_period` — check both so the handler works whichever version the
    webhook endpoint is pinned to.
    """
    sub = invoice.get('subscription')
    if sub:
        return sub if isinstance(sub, str) else sub.get('id')
    details = ((invoice.get('parent') or {}).get('subscription_details') or {})
    sub = details.get('subscription')
    if sub:
        return sub if isinstance(sub, str) else sub.get('id')
    return None


def _stripe_map_status(stripe_status):
    """Map a Stripe subscription status to our local status.

    `incomplete` means the first payment has NOT cleared yet (e.g. the card is
    still in 3-D Secure, or it failed). It must not grant access — Stripe sends a
    follow-up event once it resolves to active or incomplete_expired.

    Unknown/new Stripe statuses deliberately fall through to 'past_due' rather
    than 'active': if we don't understand the state, withhold access instead of
    granting it for free.
    """
    mapping = {
        'active': 'active',
        'trialing': 'active',
        'past_due': 'past_due',
        'paused': 'past_due',
        'incomplete': 'past_due',     # first payment not settled — no access yet
        'unpaid': 'expired',
        'incomplete_expired': 'expired',
        'canceled': 'cancelled',
    }
    return mapping.get(stripe_status, 'past_due')


def _handle_checkout_completed(session):
    """Handle checkout.session.completed for module subscriptions."""
    metadata = session.get('metadata') or {}

    if metadata.get('type') == 'key_request':
        _handle_key_request_payment(metadata)
        return

    # Module subscription — retrieve the subscription object
    subscription_id = session.get('subscription')
    subscription = None
    if subscription_id:
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
        except stripe.error.StripeError as exc:
            logger.warning('Could not retrieve subscription %s: %s', subscription_id, exc)

    ok, _ = _fulfill_purchase_from_metadata(metadata, subscription=subscription)
    if not ok:
        logger.warning('Checkout fulfilled failed for metadata: %s', metadata)


def _handle_key_request_payment(metadata):
    """Handle key request payment from checkout.session.completed."""
    try:
        from core.models import KeyRequest
        request_id = metadata.get('request_id')
        req = KeyRequest.objects.get(pk=int(request_id), status='payment_pending')
        total = float((req.key_cost_snapshot or 0) + (req.service_charge_snapshot or 0))
        req.status = 'payment_received'
        req.amount_paid = total
        req.paid_at = timezone.now()
        req.save()
        from core.notification_utils import notify_admins
        notify_admins(
            title=f"Payment received — {req.company.name} / {req.get_agent_name_display()}",
            message=f"{req.company.name} paid ${total:.2f} via Stripe. Please assign the managed key.",
            action_url='/admin/api-keys',
            notification_type='key_request_new',
        )
    except Exception as exc:
        logger.error('Webhook: failed to fulfill key request payment: %s', exc)


def _handle_subscription_updated(subscription):
    """Handle customer.subscription.updated — sync state to local DB."""
    stripe_sub_id = subscription.get('id')
    stripe_status = subscription.get('status')
    cancel_at_period_end = subscription.get('cancel_at_period_end', False)

    purchase = CompanyModulePurchase.objects.filter(
        stripe_subscription_id=stripe_sub_id,
    ).first()
    if not purchase:
        logger.warning('Webhook subscription.updated: no local purchase for sub %s', stripe_sub_id)
        return

    # A comped row can still carry the id of the subscription it used to have.
    # Stripe events about that dead subscription must not drive a row that is no
    # longer billed through it.
    if purchase.is_complimentary:
        logger.info('Ignoring %s event for complimentary purchase %s.', stripe_sub_id, purchase.id)
        return

    period_start, period_end = _extract_period(subscription)

    update_fields = ['updated_at']
    new_status = _stripe_map_status(stripe_status)

    # Never let a Stripe event resurrect access an admin deliberately revoked.
    # Stripe keeps reporting 'active' until the subscription is actually cancelled
    # there, so without this guard the next routine event silently undoes the
    # admin's decision. The billing side is cancelled separately by the admin view.
    if purchase.cancelled_reason == 'admin_deactivated' and new_status == 'active':
        logger.info(
            'Subscription %s reports active but purchase %s was deactivated by an '
            'admin — leaving local status cancelled.', stripe_sub_id, purchase.id,
        )
        new_status = purchase.status

    # Only update status if it's a meaningful change
    if purchase.status != new_status:
        purchase.status = new_status
        update_fields.append('status')

    if purchase.cancel_at_period_end != cancel_at_period_end:
        purchase.cancel_at_period_end = cancel_at_period_end
        update_fields.append('cancel_at_period_end')

    if period_start and purchase.current_period_start != period_start:
        purchase.current_period_start = period_start
        update_fields.append('current_period_start')

    if period_end and purchase.current_period_end != period_end:
        purchase.current_period_end = period_end
        update_fields.append('current_period_end')

    # If subscription was deleted/canceled, record cancellation
    if stripe_status == 'canceled' and not purchase.cancelled_at:
        purchase.cancelled_at = timezone.now()
        purchase.cancelled_reason = 'user_cancelled'
        update_fields += ['cancelled_at', 'cancelled_reason']

    if len(update_fields) > 1:  # more than just 'updated_at'
        purchase.save(update_fields=update_fields)
        logger.info('Subscription %s updated: status=%s cancel_at_period_end=%s period_end=%s',
                     stripe_sub_id, purchase.status, purchase.cancel_at_period_end, purchase.current_period_end)


def _handle_subscription_deleted(subscription):
    """Handle customer.subscription.deleted — subscription has fully ended."""
    stripe_sub_id = subscription.get('id')

    purchase = CompanyModulePurchase.objects.filter(
        stripe_subscription_id=stripe_sub_id,
    ).first()
    if not purchase:
        logger.warning('Webhook subscription.deleted: no local purchase for sub %s', stripe_sub_id)
        return

    # See _handle_subscription_updated: a comped row keeps its old subscription id,
    # and the deletion of that dead subscription must not revoke granted access.
    if purchase.is_complimentary:
        logger.info('Ignoring deletion of %s for complimentary purchase %s.', stripe_sub_id, purchase.id)
        return

    purchase.status = 'cancelled'
    purchase.cancelled_at = timezone.now()
    purchase.cancelled_reason = 'user_cancelled'
    purchase.cancel_at_period_end = False
    purchase.save(update_fields=[
        'status', 'cancelled_at', 'cancelled_reason', 'cancel_at_period_end', 'updated_at',
    ])
    logger.info('Subscription %s deleted — purchase %s marked cancelled', stripe_sub_id, purchase.id)


def _handle_invoice_paid(invoice):
    """Handle invoice.paid — successful recurring payment. Extend access."""
    stripe_sub_id = _invoice_subscription_id(invoice)
    if not stripe_sub_id:
        return  # one-time invoice, not subscription-related

    purchase = CompanyModulePurchase.objects.filter(
        stripe_subscription_id=stripe_sub_id,
    ).first()
    if not purchase:
        return

    # Update billing period from the invoice
    update_fields = ['updated_at']

    ps = _ts_to_dt(invoice.get('period_start'))
    pe = _ts_to_dt(invoice.get('period_end'))
    if ps:
        purchase.current_period_start = ps
        update_fields.append('current_period_start')
    if pe:
        purchase.current_period_end = pe
        update_fields.append('current_period_end')

    # If was past_due, reactivate
    if purchase.status == 'past_due':
        purchase.status = 'active'
        update_fields.append('status')

    if len(update_fields) > 1:
        purchase.save(update_fields=update_fields)
        logger.info('Invoice paid for sub %s — period extended to %s', stripe_sub_id, purchase.current_period_end)


def _handle_invoice_payment_failed(invoice):
    """Handle invoice.payment_failed — Stripe retry/dunning in progress."""
    stripe_sub_id = _invoice_subscription_id(invoice)
    if not stripe_sub_id:
        return

    purchase = CompanyModulePurchase.objects.filter(
        stripe_subscription_id=stripe_sub_id,
    ).first()
    if not purchase:
        return

    if purchase.status == 'active':
        purchase.status = 'past_due'
        purchase.save(update_fields=['status', 'updated_at'])
        logger.warning('Payment failed for sub %s — marked past_due', stripe_sub_id)

        # Notify company users
        try:
            from core.models import CompanyUser
            from project_manager_agent.models import PMNotification
            for cu in CompanyUser.objects.filter(company=purchase.company, is_active=True):
                PMNotification.objects.create(
                    company_user=cu,
                    notification_type='custom',
                    severity='critical',
                    title=f'Payment failed — {purchase.get_module_name_display()}',
                    message=(
                        f'Your recurring payment for {purchase.get_module_name_display()} could not be processed. '
                        f'Please update your payment method to avoid interruption.'
                    ),
                )
        except Exception as exc:
            logger.warning('Failed to send payment failure notification: %s', exc)


@csrf_exempt
@require_http_methods(['POST'])
def stripe_webhook(request):
    """Handle Stripe webhooks.  Processes the full subscription lifecycle."""
    from django.db import IntegrityError
    from core.models import StripeWebhookEvent

    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', None) or ''
    if not webhook_secret or webhook_secret == 'whsec_placeholder':
        # Loud, not a debug aside: with no secret every event is rejected, so
        # renewals, cancellations and failed payments never reach the database
        # and every subscriber silently keeps access forever.
        logger.error(
            'STRIPE_WEBHOOK_SECRET is not set — rejecting Stripe webhook. Subscription '
            'renewals, cancellations and payment failures are NOT being synced. Set '
            'STRIPE_WEBHOOK_SECRET in .env and register the endpoint in Stripe.'
        )
        return JsonResponse({'error': 'Webhook not configured'}, status=503)

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError as e:
        logger.warning('Stripe webhook invalid payload: %s', e)
        return JsonResponse({'error': 'Invalid payload'}, status=400)
    except stripe.error.SignatureVerificationError as e:
        logger.warning('Stripe webhook signature verification failed: %s', e)
        return JsonResponse({'error': 'Invalid signature'}, status=400)

    event_id = event.get('id')
    event_type = event['type']
    event_data = event['data']['object']

    # Idempotency gate. Stripe retries for up to three days, so the same event id
    # arrives repeatedly; the unique insert is the lock. Claim it BEFORE running
    # the handler so two concurrent deliveries can't both process.
    try:
        log_row = StripeWebhookEvent.objects.create(event_id=event_id, event_type=event_type)
    except IntegrityError:
        logger.info('Stripe event %s (%s) already seen — skipping replay.', event_id, event_type)
        return JsonResponse({'received': True, 'duplicate': True}, status=200)

    try:
        if event_type == 'checkout.session.completed':
            _handle_checkout_completed(event_data)
        elif event_type in ('customer.subscription.created', 'customer.subscription.updated'):
            _handle_subscription_updated(event_data)
        elif event_type == 'customer.subscription.deleted':
            _handle_subscription_deleted(event_data)
        elif event_type == 'invoice.paid':
            _handle_invoice_paid(event_data)
        elif event_type == 'invoice.payment_failed':
            _handle_invoice_payment_failed(event_data)
        else:
            logger.debug('Unhandled Stripe event: %s', event_type)
        log_row.processed_at = timezone.now()
        log_row.save(update_fields=['processed_at'])
    except Exception as exc:
        # Drop the claim so Stripe's retry can have another go — otherwise a
        # transient failure would be permanently deduped away as "handled".
        log_row.delete()
        logger.error('Error processing webhook event %s (%s): %s',
                     event_type, event_id, exc, exc_info=True)
        return JsonResponse({'error': 'Handler failed'}, status=500)

    return JsonResponse({'received': True}, status=200)


# ---------------------------------------------------------------------------
# Verify session (fallback fulfillment after Stripe redirect)
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([AllowAny])
def verify_session(request):
    """Verify Stripe Checkout session and fulfill module purchase.

    Public endpoint called from the success page after Stripe redirect.
    For subscriptions, retrieves the subscription object.
    """
    session_id = (request.data or {}).get('session_id')
    if not session_id:
        return Response(
            {'status': 'error', 'message': 'session_id is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not stripe.api_key or stripe.api_key == 'sk_test_placeholder':
        return Response(
            {'status': 'error', 'message': 'Stripe is not configured.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.InvalidRequestError as e:
        logger.warning('Verify session invalid request: %s', e)
        return Response(
            {'status': 'error', 'message': 'Invalid session.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except stripe.error.StripeError as e:
        logger.error('Verify session Stripe error: %s', e, exc_info=True)
        return Response(
            {'status': 'error', 'message': 'Could not verify payment.'},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if session.payment_status != 'paid':
        return Response(
            {'status': 'error', 'message': 'Payment not completed.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    raw = getattr(session, 'metadata', None) or {}
    metadata = dict(raw) if raw else {}

    # For subscription checkouts, retrieve the subscription
    subscription = None
    subscription_id = session.get('subscription')
    if subscription_id:
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
        except stripe.error.StripeError as exc:
            logger.warning('Verify session: could not retrieve subscription %s: %s', subscription_id, exc)

    ok, mod = _fulfill_purchase_from_metadata(metadata, subscription=subscription)
    if not ok:
        logger.warning('Verify session fulfill failed for session %s metadata: %s', session_id, metadata)
        return Response(
            {'status': 'error', 'message': 'Could not activate module.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(
        {'status': 'success', 'message': 'Module activated.', 'module_name': mod},
        status=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# Subscription management — cancel, reactivate, billing portal
# ---------------------------------------------------------------------------

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def cancel_subscription(request, module_name):
    """Cancel a Stripe subscription at the end of the current billing period.

    The user keeps access until the period ends.  Stripe does not renew.
    """
    try:
        company = request.user.company

        if module_name not in MODULE_PRICES:
            return Response({
                'status': 'error',
                'message': 'Invalid module name.',
            }, status=status.HTTP_400_BAD_REQUEST)

        purchase = CompanyModulePurchase.objects.filter(
            company=company, module_name=module_name,
        ).first()
        # Deliberately NOT gated on is_active(): a past_due customer (card
        # declined, Stripe still retrying) is exactly who most needs to cancel,
        # and is_active() is False for them. Gate on the subscription being live
        # at Stripe instead.
        if not purchase or purchase.status not in ('active', 'past_due'):
            return Response({
                'status': 'error',
                'message': f'No active subscription found for {MODULE_DISPLAY_NAMES.get(module_name, module_name)}.',
            }, status=status.HTTP_404_NOT_FOUND)

        if not purchase.stripe_subscription_id:
            return Response({
                'status': 'error',
                'message': 'This is not a Stripe subscription. Cannot cancel via this endpoint.',
            }, status=status.HTTP_400_BAD_REQUEST)

        if purchase.cancel_at_period_end:
            return Response({
                'status': 'error',
                'message': 'Subscription is already scheduled for cancellation.',
            }, status=status.HTTP_400_BAD_REQUEST)

        # Tell Stripe to cancel at period end
        stripe.Subscription.modify(
            purchase.stripe_subscription_id,
            cancel_at_period_end=True,
        )
        purchase.cancel_at_period_end = True
        purchase.save(update_fields=['cancel_at_period_end', 'updated_at'])

        return Response({
            'status': 'success',
            'message': f'Subscription will be cancelled at the end of the current billing period.',
            'current_period_end': purchase.current_period_end.isoformat() if purchase.current_period_end else None,
        }, status=status.HTTP_200_OK)

    except stripe.error.StripeError as e:
        logger.error('Stripe error cancelling subscription: %s', str(e), exc_info=True)
        return Response({
            'status': 'error',
            'message': str(e.user_message) if getattr(e, 'user_message', None) else 'Failed to cancel subscription.',
        }, status=status.HTTP_502_BAD_GATEWAY)
    except Exception as e:
        logger.error('Error cancelling subscription: %s', str(e), exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Failed to cancel subscription.',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def reactivate_subscription(request, module_name):
    """Reactivate a subscription that was scheduled for cancellation.

    Reverses cancel_at_period_end so Stripe will renew at period end.
    """
    try:
        company = request.user.company

        if module_name not in MODULE_PRICES:
            return Response({
                'status': 'error',
                'message': 'Invalid module name.',
            }, status=status.HTTP_400_BAD_REQUEST)

        purchase = CompanyModulePurchase.objects.filter(
            company=company, module_name=module_name,
        ).first()
        # Same reasoning as cancel_subscription: allow past_due through so a
        # customer who fixed their card can undo a pending cancellation.
        if not purchase or purchase.status not in ('active', 'past_due'):
            return Response({
                'status': 'error',
                'message': 'No active subscription found.',
            }, status=status.HTTP_404_NOT_FOUND)

        if not purchase.stripe_subscription_id:
            return Response({
                'status': 'error',
                'message': 'This is not a Stripe subscription.',
            }, status=status.HTTP_400_BAD_REQUEST)

        if not purchase.cancel_at_period_end:
            return Response({
                'status': 'error',
                'message': 'Subscription is not scheduled for cancellation.',
            }, status=status.HTTP_400_BAD_REQUEST)

        stripe.Subscription.modify(
            purchase.stripe_subscription_id,
            cancel_at_period_end=False,
        )
        purchase.cancel_at_period_end = False
        purchase.save(update_fields=['cancel_at_period_end', 'updated_at'])

        return Response({
            'status': 'success',
            'message': 'Subscription reactivated. It will renew at the end of the billing period.',
        }, status=status.HTTP_200_OK)

    except stripe.error.StripeError as e:
        logger.error('Stripe error reactivating subscription: %s', str(e), exc_info=True)
        return Response({
            'status': 'error',
            'message': str(e.user_message) if getattr(e, 'user_message', None) else 'Failed to reactivate.',
        }, status=status.HTTP_502_BAD_GATEWAY)
    except Exception as e:
        logger.error('Error reactivating subscription: %s', str(e), exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Failed to reactivate subscription.',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def billing_overview(request):
    """Everything the in-app billing screen needs, read live from Stripe.

    Deliberately does NOT serve subscription state from the local DB. The DB is a
    webhook-fed mirror, so it is stale for exactly as long as an event takes to
    arrive — and silently wrong for good if one is ever missed. A billing screen
    showing a customer the wrong renewal date or a card they have already replaced
    is worse than one that is briefly slow, so this reads Stripe directly and falls
    back to the mirror only when Stripe is unreachable.

    Card entry is handled in-app by Stripe Elements, not by the hosted portal.
    Elements renders the card field in an iframe served from Stripe's own origin,
    so the PAN never reaches our DOM or our servers and the integration stays PCI
    SAQ A — the same tier as redirecting out. See `create_setup_intent` and
    `set_default_payment_method` below. The portal is kept only for what we do not
    reimplement: billing address, tax IDs and the full receipt archive.

    `publishable_key` rides along in the response rather than being baked into the
    frontend build, so it can never drift out of test/live sync with
    STRIPE_SECRET_KEY (see the clear_test_stripe_ids management command, which
    exists to support exactly that cutover).
    """
    try:
        company = request.user.company

        publishable_key = getattr(settings, 'STRIPE_PUBLISHABLE_KEY', None) or None

        if not company.stripe_customer_id:
            # No customer yet, but the card dialog still needs the key: a company
            # can save a card before its first purchase (create_setup_intent calls
            # _ensure_stripe_customer, which the portal flow cannot do).
            return Response({
                'status': 'success',
                'has_billing': False,
                'subscriptions': [], 'invoices': [], 'payment_method': None,
                'publishable_key': publishable_key,
            }, status=status.HTTP_200_OK)

        purchases = {
            p.stripe_subscription_id: p
            for p in CompanyModulePurchase.objects
                .filter(company=company).exclude(stripe_subscription_id=None)
        }

        subscriptions, invoices, payment_method = [], [], None
        stripe_ok = True

        try:
            for sub in stripe.Subscription.list(
                customer=company.stripe_customer_id, status='all', limit=100,
            ).auto_paging_iter():
                purchase = purchases.get(sub.get('id'))
                start, end = _extract_period(sub)
                item = ((sub.get('items') or {}).get('data') or [{}])[0]
                price = item.get('price') or {}
                subscriptions.append({
                    'stripe_subscription_id': sub.get('id'),
                    'module_name': purchase.module_name if purchase else None,
                    'module_display_name': (
                        purchase.get_module_name_display() if purchase else 'Unknown agent'
                    ),
                    'stripe_status': sub.get('status'),
                    'cancel_at_period_end': bool(sub.get('cancel_at_period_end')),
                    'current_period_start': start.isoformat() if start else None,
                    'current_period_end': end.isoformat() if end else None,
                    'amount': (price.get('unit_amount') or 0) / 100,
                    'currency': (price.get('currency') or 'usd').upper(),
                    'billing_interval': _extract_interval(sub),
                })

            for inv in stripe.Invoice.list(
                customer=company.stripe_customer_id, limit=24,
            ).auto_paging_iter():
                invoices.append({
                    'id': inv.get('id'),
                    'number': inv.get('number'),
                    'status': inv.get('status'),
                    'amount_paid': (inv.get('amount_paid') or 0) / 100,
                    'amount_due': (inv.get('amount_due') or 0) / 100,
                    'currency': (inv.get('currency') or 'usd').upper(),
                    'created': _ts_to_dt(inv.get('created')).isoformat() if inv.get('created') else None,
                    # Stripe-hosted links: no PDF is generated or stored by us.
                    'hosted_invoice_url': inv.get('hosted_invoice_url'),
                    'invoice_pdf': inv.get('invoice_pdf'),
                })

            customer = stripe.Customer.retrieve(company.stripe_customer_id)
            default_pm = (customer.get('invoice_settings') or {}).get('default_payment_method')
            pm = None
            if default_pm:
                pm = stripe.PaymentMethod.retrieve(default_pm)
            else:
                cards = stripe.PaymentMethod.list(
                    customer=company.stripe_customer_id, type='card', limit=1,
                )
                pm = cards.data[0] if cards.data else None
            if pm:
                card = pm.get('card') or {}
                payment_method = {
                    'brand': (card.get('brand') or '').title(),
                    'last4': card.get('last4'),
                    'exp_month': card.get('exp_month'),
                    'exp_year': card.get('exp_year'),
                }

        except stripe.error.StripeError as exc:
            # Degrade to the mirror rather than showing a blank billing page.
            stripe_ok = False
            logger.error('Billing overview: Stripe read failed for company %s: %s',
                         company.id, exc, exc_info=True)
            for sub_id, p in purchases.items():
                subscriptions.append({
                    'stripe_subscription_id': sub_id,
                    'module_name': p.module_name,
                    'module_display_name': p.get_module_name_display(),
                    'stripe_status': p.status,
                    'cancel_at_period_end': p.cancel_at_period_end,
                    'current_period_start': (
                        p.current_period_start.isoformat() if p.current_period_start else None
                    ),
                    'current_period_end': (
                        p.current_period_end.isoformat() if p.current_period_end else None
                    ),
                    'amount': float(p.price_paid) if p.price_paid else None,
                    'currency': 'USD',
                    'billing_interval': p.billing_interval,
                })

        return Response({
            'status': 'success',
            'has_billing': True,
            'live': stripe_ok,       # false = figures are from the local mirror
            'subscriptions': subscriptions,
            'invoices': invoices,
            'payment_method': payment_method,
            'publishable_key': publishable_key,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error('Error building billing overview: %s', e, exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Failed to load billing information.',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_billing_portal(request):
    """Create a Stripe Billing Portal session for the company.

    Secondary escape hatch only. Subscriptions, invoices and the saved card are all
    handled natively now (billing_overview + set_default_payment_method), so this is
    reached from one link in the Billing tab for the things we do not reimplement:
    billing address, tax IDs and the full receipt archive.
    """
    try:
        company = request.user.company

        if not company.stripe_customer_id:
            return Response({
                'status': 'error',
                'message': 'No Stripe customer found. Subscribe to a plan first.',
            }, status=status.HTTP_400_BAD_REQUEST)

        frontend_url = (getattr(settings, 'FRONTEND_URL', None) or '').rstrip('/')

        session = stripe.billing_portal.Session.create(
            customer=company.stripe_customer_id,
            return_url=f'{frontend_url}/company/dashboard/billing',
        )

        return Response({
            'status': 'success',
            'url': session.url,
        }, status=status.HTTP_200_OK)

    except stripe.error.InvalidRequestError as e:
        # The portal must be configured once per Stripe account (Settings →
        # Billing → Customer portal) before any session can be created. Until
        # that is saved, every call fails here — surface the actual cause rather
        # than a generic failure, because it is a dashboard step, not a code bug.
        msg = str(e)
        if 'configuration' in msg.lower():
            logger.error(
                'Stripe Billing Portal is not configured for this account. Save the '
                'customer portal settings in the Stripe dashboard (Settings → Billing '
                '→ Customer portal) to enable it. Stripe said: %s', msg,
            )
            return Response({
                'status': 'error',
                'message': 'Billing portal is not set up yet. Please contact support.',
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        logger.error('Stripe error creating billing portal: %s', msg, exc_info=True)
        return Response({
            'status': 'error',
            'message': str(e.user_message) if getattr(e, 'user_message', None) else 'Failed to open billing portal.',
        }, status=status.HTTP_502_BAD_GATEWAY)
    except stripe.error.StripeError as e:
        logger.error('Stripe error creating billing portal: %s', str(e), exc_info=True)
        return Response({
            'status': 'error',
            'message': str(e.user_message) if getattr(e, 'user_message', None) else 'Failed to open billing portal.',
        }, status=status.HTTP_502_BAD_GATEWAY)
    except Exception as e:
        logger.error('Error creating billing portal: %s', str(e), exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Failed to open billing portal.',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------------------------------------------------------------------------
# In-app card management (Stripe Elements)
# ---------------------------------------------------------------------------

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_setup_intent(request):
    """Start an in-app card save. Returns a SetupIntent client_secret for Elements.

    `usage='off_session'` because the saved card is charged unattended on every
    renewal — omitting it makes Stripe collect weaker authentication up front and
    the first renewal is then far more likely to be declined for missing SCA.

    Uses _ensure_stripe_customer, so this also works for a company that has not
    bought anything yet. The portal cannot do that: create_billing_portal 400s when
    stripe_customer_id is null.
    """
    try:
        company = request.user.company
        customer_id = _ensure_stripe_customer(company)

        intent = stripe.SetupIntent.create(
            customer=customer_id,
            payment_method_types=['card'],
            usage='off_session',
            metadata={'company_id': str(company.id), 'source': 'billing_tab'},
        )

        return Response({
            'status': 'success',
            'client_secret': intent.client_secret,
        }, status=status.HTTP_200_OK)

    except stripe.error.StripeError as e:
        logger.error('Stripe error creating setup intent for company %s: %s',
                     getattr(request.user, 'company_id', None), e, exc_info=True)
        return Response({
            'status': 'error',
            'message': str(e.user_message) if getattr(e, 'user_message', None) else 'Failed to start card setup.',
        }, status=status.HTTP_502_BAD_GATEWAY)
    except Exception as e:
        logger.error('Error creating setup intent: %s', e, exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Failed to start card setup.',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def set_default_payment_method(request):
    """Promote a just-saved card to the default for this company.

    Writing customer.invoice_settings alone is NOT enough, and the failure is
    silent. Checkout in subscription mode stamps default_payment_method onto every
    subscription it creates, and a subscription-level default overrides the
    customer-level one. Skip step 3 below and the billing screen would show the new
    card while every renewal kept charging the old one until it expired. The hosted
    portal does this internally; doing it here is the price of owning the flow.
    """
    try:
        company = request.user.company
        payment_method_id = (request.data.get('payment_method_id') or '').strip()

        if not payment_method_id:
            return Response({
                'status': 'error',
                'message': 'payment_method_id is required.',
            }, status=status.HTTP_400_BAD_REQUEST)

        if not company.stripe_customer_id:
            return Response({
                'status': 'error',
                'message': 'No Stripe customer found for this company.',
            }, status=status.HTTP_400_BAD_REQUEST)

        # The id arrives from the browser, so confirm Stripe actually attached it to
        # THIS customer before pointing any subscription at it.
        pm = stripe.PaymentMethod.retrieve(payment_method_id)
        if pm.get('customer') != company.stripe_customer_id:
            logger.warning(
                'Company %s tried to set payment method %s owned by customer %s',
                company.id, payment_method_id, pm.get('customer'),
            )
            return Response({
                'status': 'error',
                'message': 'That payment method does not belong to this account.',
            }, status=status.HTTP_403_FORBIDDEN)

        # 1. Customer-level default — future subscriptions and one-off invoices.
        stripe.Customer.modify(
            company.stripe_customer_id,
            invoice_settings={'default_payment_method': payment_method_id},
        )

        # 2. Subscription-level default — everything already running.
        billable = {'active', 'trialing', 'past_due', 'unpaid'}
        updated = 0
        for sub in stripe.Subscription.list(
            customer=company.stripe_customer_id, status='all', limit=100,
        ).auto_paging_iter():
            if sub.get('status') in billable:
                stripe.Subscription.modify(sub['id'], default_payment_method=payment_method_id)
                updated += 1

        logger.info('Company %s set default payment method %s on %d subscription(s)',
                    company.id, payment_method_id, updated)

        card = pm.get('card') or {}
        return Response({
            'status': 'success',
            'subscriptions_updated': updated,
            'payment_method': {
                'brand': (card.get('brand') or '').title(),
                'last4': card.get('last4'),
                'exp_month': card.get('exp_month'),
                'exp_year': card.get('exp_year'),
            },
        }, status=status.HTTP_200_OK)

    except stripe.error.StripeError as e:
        logger.error('Stripe error setting default payment method: %s', e, exc_info=True)
        return Response({
            'status': 'error',
            'message': str(e.user_message) if getattr(e, 'user_message', None) else 'Failed to save the card.',
        }, status=status.HTTP_502_BAD_GATEWAY)
    except Exception as e:
        logger.error('Error setting default payment method: %s', e, exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Failed to save the card.',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------------------------------------------------------------------------
# Pricing / plan endpoints (public)
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([AllowAny])
def get_module_prices(request):
    """Get pricing information for all modules (public endpoint)."""
    try:
        plans_by_agent = {}
        for p in AgentPlan.objects.filter(is_active=True).order_by('sort_order', 'duration_days'):
            plans_by_agent.setdefault(p.agent_name, []).append(_serialize_plan(p))

        prices = []
        for module_name, price in MODULE_PRICES.items():
            plans = plans_by_agent.get(module_name, [])
            prices.append({
                'module_name': module_name,
                'module_display_name': MODULE_DISPLAY_NAMES[module_name],
                'price': price,
                'price_period': 'month',
                'plans': plans,
                'has_plans': bool(plans),
            })

        return Response({
            'status': 'success',
            'modules': prices,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error('Error getting module prices: %s', str(e), exc_info=True)
        return Response({
            'status': 'error',
            'message': f'Failed to get module prices: {str(e)}',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def get_module_plans(request, module_name):
    """Active plans for a single module (public endpoint), used by the buy card."""
    try:
        if module_name not in MODULE_PRICES:
            return Response({
                'status': 'error',
                'message': 'Invalid module name.',
            }, status=status.HTTP_400_BAD_REQUEST)
        plans = [_serialize_plan(p) for p in _active_plans_for(module_name)]
        return Response({
            'status': 'success',
            'module_name': module_name,
            'module_display_name': MODULE_DISPLAY_NAMES[module_name],
            'plans': plans,
            'has_plans': bool(plans),
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error('Error getting module plans for %s: %s', module_name, e, exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Failed to get module plans.',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

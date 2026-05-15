"""Company-user facing API for per-agent LLM keys + key requests.

Scope:
  - List the company's purchased agents with current key state + quota.
  - Let the user register / update / revoke their own BYOK key.
  - Let the user raise a KeyRequest asking admin to provision a managed key.

A user NEVER sees a plaintext key — only the masked display (`sk-12********wxyz`).
Managed keys are assigned by a superadmin via the admin API; this view is
strictly user-side.
"""
import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.models import (
    AGENT_CHOICES,
    AGENT_DEFAULT_PROVIDER,
    PROVIDER_CHOICES,
    AgentTokenQuota,
    CompanyAPIKey,
    CompanyModulePurchase,
    KeyRequest,
)


logger = logging.getLogger(__name__)

VALID_AGENTS = {name for name, _ in AGENT_CHOICES}
VALID_PROVIDERS = {name for name, _ in PROVIDER_CHOICES}


def _serialize_key(key: CompanyAPIKey):
    return {
        'id': key.id,
        'mode': key.mode,
        'provider': key.provider,
        'masked': key.masked_display,
        'status': key.status,
        'assigned_by': key.assigned_by.username if key.assigned_by else None,
        'updated_at': key.updated_at.isoformat(),
    }


def _serialize_quota(quota: AgentTokenQuota, agent_name: str = None):
    if not quota:
        return None
    provider_breakdown = {
        row.provider: row.used_tokens
        for row in quota.provider_usage.all()
    }
    default_provider = AGENT_DEFAULT_PROVIDER.get(agent_name or quota.agent_name, 'openai')
    if not provider_breakdown and quota.used_tokens > 0:
        provider_breakdown = {default_provider: quota.used_tokens}
    else:
        # Attribute any untracked tokens (usage before per-provider logging existed)
        # to the default provider so the breakdown sum matches the total.
        untracked = quota.used_tokens - sum(provider_breakdown.values())
        if untracked > 0:
            provider_breakdown[default_provider] = provider_breakdown.get(default_provider, 0) + untracked
    return {
        'included_tokens': quota.included_tokens,
        'used_tokens': quota.used_tokens,
        'remaining': quota.remaining,
        'is_exhausted': quota.is_exhausted,
        'byok_tokens_info': quota.byok_tokens_info,
        'managed_included_tokens': quota.managed_included_tokens,
        'managed_used_tokens': quota.managed_used_tokens,
        'managed_is_exhausted': quota.managed_included_tokens > 0 and quota.managed_used_tokens >= quota.managed_included_tokens,
        'preferred_pool': quota.preferred_pool,
        'byok_token_limit': quota.byok_token_limit,
        'provider_breakdown': provider_breakdown,
        'default_provider': default_provider,
    }


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_agent_keys(request):
    """Return one row per purchased agent with its key + quota state.

    Frontend uses this to render the "API Keys" settings tab. Agents the
    company has NOT purchased are omitted — they can't configure a key until
    they buy the agent.
    """
    company = request.user.company

    purchases = (
        CompanyModulePurchase.objects
        .filter(company=company, status='active')
        .values_list('module_name', flat=True)
    )
    purchased = set(purchases)

    keys_by_agent = {}
    # Active keys first — these always win
    for k in CompanyAPIKey.objects.filter(company=company, status='active'):
        keys_by_agent.setdefault(k.agent_name, {})[k.mode] = k
    # Show the most-recently revoked managed key only when no active managed key exists,
    # so the company can see "revoked by admin" instead of a blank slot.
    for k in CompanyAPIKey.objects.filter(company=company, mode='managed', status='revoked').order_by('-updated_at'):
        if 'managed' not in keys_by_agent.get(k.agent_name, {}):
            keys_by_agent.setdefault(k.agent_name, {})['managed'] = k

    quotas_by_agent = {
        q.agent_name: q
        for q in AgentTokenQuota.objects.filter(company=company).prefetch_related('provider_usage')
    }

    rows = []
    for agent_name, agent_label in AGENT_CHOICES:
        if agent_name not in purchased:
            continue
        agent_keys = keys_by_agent.get(agent_name, {})
        rows.append({
            'agent_name': agent_name,
            'agent_label': agent_label,
            'byok': _serialize_key(agent_keys['byok']) if 'byok' in agent_keys else None,
            'managed': _serialize_key(agent_keys['managed']) if 'managed' in agent_keys else None,
            'quota': _serialize_quota(quotas_by_agent.get(agent_name), agent_name),
            'default_provider': AGENT_DEFAULT_PROVIDER.get(agent_name, 'openai'),
        })

    return Response({
        'status': 'success',
        'providers': [{'value': v, 'label': l} for v, l in PROVIDER_CHOICES],
        'agents': rows,
    })


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def upsert_byok_key(request):
    """Create or replace the company's BYOK key for one agent.

    Body: { agent_name, provider, api_key }
    Requires the company to have an active purchase for the agent.
    """
    company = request.user.company
    agent_name = (request.data.get('agent_name') or '').strip()
    provider = (request.data.get('provider') or 'openai').strip()
    api_key = (request.data.get('api_key') or '').strip()

    if agent_name not in VALID_AGENTS:
        return Response({'status': 'error', 'message': 'Invalid agent_name'},
                        status=status.HTTP_400_BAD_REQUEST)
    if provider not in VALID_PROVIDERS:
        return Response({'status': 'error', 'message': 'Invalid provider'},
                        status=status.HTTP_400_BAD_REQUEST)
    if len(api_key) < 10:
        return Response({'status': 'error', 'message': 'API key looks too short to be valid'},
                        status=status.HTTP_400_BAD_REQUEST)

    has_purchase = CompanyModulePurchase.objects.filter(
        company=company, module_name=agent_name, status='active'
    ).exists()
    if not has_purchase:
        return Response(
            {'status': 'error', 'message': 'You must purchase this agent before adding a BYOK key.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    key, created = CompanyAPIKey.objects.get_or_create(
        company=company, agent_name=agent_name, mode='byok',
        defaults={'provider': provider, 'encrypted_key': ''},
    )
    key.provider = provider
    key.status = 'active'
    key.set_plaintext_key(api_key)
    key.save()

    # In-app notification to the user who added/updated the key
    try:
        from project_manager_agent.models import PMNotification
        agent_label = dict(AGENT_CHOICES).get(agent_name, agent_name)
        action = 'added' if created else 'updated'
        PMNotification.objects.create(
            company_user=request.user,
            notification_type='custom',
            severity='info',
            title=f'API key {action} — {agent_label}',
            message=(
                f'Your {provider.upper()} API key for {agent_label} has been {action} successfully. '
                f'Calls for this agent will now use your own key.'
            ),
        )
    except Exception:
        pass

    return Response({'status': 'success', 'key': _serialize_key(key), 'created': created})


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def revoke_byok_key(request, agent_name):
    """Delete the company's BYOK key for one agent.

    Managed keys can NOT be revoked via this endpoint — only by a superadmin.
    """
    company = request.user.company
    deleted, _ = CompanyAPIKey.objects.filter(
        company=company, agent_name=agent_name, mode='byok',
    ).delete()
    return Response({'status': 'success', 'deleted': deleted})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def set_token_pool(request):
    """Set the preferred token pool for an agent.

    Body: { agent_name, preferred_pool }  — preferred_pool: 'free' | 'managed'
    Only relevant when the company has both free tokens remaining and an active
    managed key. The chosen pool is used for subsequent LLM calls.
    """
    company = request.user.company
    agent_name = (request.data.get('agent_name') or '').strip()
    preferred_pool = (request.data.get('preferred_pool') or '').strip()

    if agent_name not in {name for name, _ in AGENT_CHOICES}:
        return Response({'status': 'error', 'message': 'Invalid agent_name'},
                        status=status.HTTP_400_BAD_REQUEST)
    if preferred_pool not in ('free', 'managed'):
        return Response({'status': 'error', 'message': "preferred_pool must be 'free' or 'managed'"},
                        status=status.HTTP_400_BAD_REQUEST)

    quota, _ = AgentTokenQuota.objects.get_or_create(
        company=company, agent_name=agent_name,
        defaults={'included_tokens': 0},
    )
    quota.preferred_pool = preferred_pool
    quota.save(update_fields=['preferred_pool'])
    return Response({'status': 'success', 'preferred_pool': preferred_pool})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def set_byok_limit(request):
    """Set or clear the user's self-imposed BYOK spending cap.

    Body: { agent_name, limit }  — limit: integer tokens, 0 = no limit (clear).
    This is a soft cap: calls are never blocked, but the UI shows a progress bar
    and warns when usage approaches/exceeds the cap.
    """
    company = request.user.company
    agent_name = (request.data.get('agent_name') or '').strip()
    try:
        limit = max(0, int(request.data.get('limit', 0)))
    except (TypeError, ValueError):
        return Response({'status': 'error', 'message': 'limit must be an integer'},
                        status=status.HTTP_400_BAD_REQUEST)

    if agent_name not in {name for name, _ in AGENT_CHOICES}:
        return Response({'status': 'error', 'message': 'Invalid agent_name'},
                        status=status.HTTP_400_BAD_REQUEST)

    quota, _ = AgentTokenQuota.objects.get_or_create(
        company=company, agent_name=agent_name,
        defaults={'included_tokens': 0},
    )
    quota.byok_token_limit = limit
    quota.save(update_fields=['byok_token_limit'])
    return Response({'status': 'success', 'byok_token_limit': limit})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_key_requests(request):
    """List this company's KeyRequests (all statuses)."""
    company = request.user.company
    reqs = KeyRequest.objects.filter(company=company).select_related('requested_by', 'resolved_by').order_by('-created_at')

    # Agents whose managed key is currently revoked — used to override 'approved'
    # requests that predate the revocation (handles existing DB rows).
    revoked_agents = set(
        CompanyAPIKey.objects.filter(company=company, mode='managed', status='revoked')
        .values_list('agent_name', flat=True)
    )

    data = []
    for r in reqs:
        status = r.status
        if status == 'approved' and r.agent_name in revoked_agents:
            status = 'revoked'
        data.append({
            'id': r.id,
            'agent_name': r.agent_name,
            'agent_label': r.get_agent_name_display(),
            'provider': r.provider,
            'note': r.note,
            'status': status,
            'admin_note': r.admin_note,
            'requested_by': r.requested_by.email if r.requested_by else None,
            'resolved_by': r.resolved_by.username if r.resolved_by else None,
            'created_at': r.created_at.isoformat(),
            'resolved_at': r.resolved_at.isoformat() if r.resolved_at else None,
            'key_cost_snapshot': float(r.key_cost_snapshot) if r.key_cost_snapshot is not None else None,
            'service_charge_snapshot': float(r.service_charge_snapshot) if r.service_charge_snapshot is not None else None,
            'amount_paid': float(r.amount_paid) if r.amount_paid is not None else None,
            'paid_at': r.paid_at.isoformat() if r.paid_at else None,
        })
    return Response({'status': 'success', 'requests': data})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_key_request(request):
    """Raise a KeyRequest: user asks admin to assign a managed key.

    Body: { agent_name, provider?, note? }
    Only one pending request per (company, agent) — if one exists, we return it.
    """
    company = request.user.company
    agent_name = (request.data.get('agent_name') or '').strip()
    provider = (request.data.get('provider') or 'openai').strip()
    note = (request.data.get('note') or '').strip()

    if agent_name not in VALID_AGENTS:
        return Response({'status': 'error', 'message': 'Invalid agent_name'},
                        status=status.HTTP_400_BAD_REQUEST)
    if provider not in VALID_PROVIDERS:
        return Response({'status': 'error', 'message': 'Invalid provider'},
                        status=status.HTTP_400_BAD_REQUEST)

    has_purchase = CompanyModulePurchase.objects.filter(
        company=company, module_name=agent_name, status='active'
    ).exists()
    if not has_purchase:
        return Response(
            {'status': 'error', 'message': 'Purchase this agent before requesting a key.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    existing = KeyRequest.objects.filter(
        company=company, agent_name=agent_name, status='pending'
    ).first()
    if existing:
        return Response({
            'status': 'success',
            'already_pending': True,
            'request_id': existing.id,
        })

    req = KeyRequest.objects.create(
        company=company,
        requested_by=request.user,
        agent_name=agent_name,
        provider=provider,
        note=note,
    )

    # Broadcast to admins so they see it without polling the dashboard
    from core.notification_utils import notify_admins
    notify_admins(
        title=f"New managed-key request — {company.name}",
        message=f"{company.name} is requesting a managed {provider.upper()} key for {req.get_agent_name_display()}.",
        action_url='/admin/api-keys',
        notification_type='key_request_new',
    )

    return Response({'status': 'success', 'request_id': req.id})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_key_checkout_session(request, request_id):
    """Create a Stripe Checkout Session for a payment_pending key request."""
    import stripe
    from django.conf import settings
    company = request.user.company
    try:
        req = KeyRequest.objects.select_related('company').get(pk=request_id, company=company)
    except KeyRequest.DoesNotExist:
        return Response({'status': 'error', 'message': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if req.status != 'payment_pending':
        return Response({'status': 'error', 'message': f'Request is {req.status}, expected payment_pending'},
                        status=status.HTTP_400_BAD_REQUEST)

    stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', None)
    if not stripe.api_key or stripe.api_key == 'sk_test_placeholder':
        return Response({'status': 'error', 'message': 'Stripe is not configured.'},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE)

    total = float((req.key_cost_snapshot or 0) + (req.service_charge_snapshot or 0))
    if total <= 0:
        return Response({'status': 'error', 'message': 'No charge due for this request.'},
                        status=status.HTTP_400_BAD_REQUEST)

    frontend_url = (getattr(settings, 'FRONTEND_URL', None) or '').rstrip('/')
    agent_label = req.get_agent_name_display()

    try:
        session = stripe.checkout.Session.create(
            mode='payment',
            payment_method_types=['card'],
            line_items=[
                {
                    'price_data': {
                        'currency': 'usd',
                        'unit_amount': int(round(float(req.key_cost_snapshot or 0) * 100)),
                        'product_data': {'name': f'{agent_label} — Managed API Key'},
                    },
                    'quantity': 1,
                },
                {
                    'price_data': {
                        'currency': 'usd',
                        'unit_amount': int(round(float(req.service_charge_snapshot or 0) * 100)),
                        'product_data': {'name': f'{agent_label} — Service Charge'},
                    },
                    'quantity': 1,
                },
            ],
            metadata={
                'type': 'key_request',
                'request_id': str(req.id),
                'company_id': str(company.id),
                'company_user_id': str(request.user.id),
            },
            success_url=f'{frontend_url}/company/settings/api-keys?key_session={{CHECKOUT_SESSION_ID}}',
            cancel_url=f'{frontend_url}/company/settings/api-keys',
        )
        req.stripe_session_id = session.id
        req.save(update_fields=['stripe_session_id'])
        return Response({'status': 'success', 'url': session.url, 'session_id': session.id})
    except stripe.error.StripeError as exc:
        logger.error('Stripe error for key request %s: %s', request_id, exc)
        return Response({'status': 'error', 'message': getattr(exc, 'user_message', None) or 'Payment setup failed.'},
                        status=status.HTTP_502_BAD_GATEWAY)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def verify_key_session(request, session_id):
    """Verify a Stripe session for a key request and mark payment_received."""
    import stripe
    from django.conf import settings
    from django.utils import timezone
    company = request.user.company

    stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', None)
    if not stripe.api_key:
        return Response({'status': 'error', 'message': 'Stripe not configured.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as exc:
        return Response({'status': 'error', 'message': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    if session.payment_status != 'paid':
        return Response({'status': 'pending', 'payment_status': session.payment_status})

    req = KeyRequest.objects.filter(stripe_session_id=session_id, company=company).first()
    if not req:
        return Response({'status': 'error', 'message': 'Request not found.'}, status=status.HTTP_404_NOT_FOUND)

    if req.status == 'payment_received':
        return Response({'status': 'success', 'already_confirmed': True, 'agent_label': req.get_agent_name_display()})

    if req.status != 'payment_pending':
        return Response({'status': 'error', 'message': f'Request is {req.status}.'}, status=status.HTTP_400_BAD_REQUEST)

    total = float((req.key_cost_snapshot or 0) + (req.service_charge_snapshot or 0))
    req.status = 'payment_received'
    req.amount_paid = total
    req.paid_at = timezone.now()
    req.save()

    from core.notification_utils import notify_admins
    notify_admins(
        title=f"Payment received — {req.company.name} / {req.get_agent_name_display()}",
        message=(
            f"{req.company.name} paid ${total:.2f} for a managed {req.provider.upper()} key "
            f"for {req.get_agent_name_display()} via Stripe. Please assign the key."
        ),
        action_url='/admin/api-keys',
        notification_type='key_request_new',
    )
    return Response({'status': 'success', 'agent_label': req.get_agent_name_display(), 'amount_paid': total})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def pay_for_key_request(request, request_id):
    """Company confirms payment for an approved key request.

    Marks the request as payment_received and notifies admins.
    No real payment gateway yet — company confirms they've paid manually.
    """
    from django.utils import timezone
    company = request.user.company
    try:
        req = KeyRequest.objects.select_related('company').get(pk=request_id, company=company)
    except KeyRequest.DoesNotExist:
        return Response({'status': 'error', 'message': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if req.status != 'payment_pending':
        return Response({'status': 'error', 'message': f'Request is {req.status}, not awaiting payment'}, status=status.HTTP_400_BAD_REQUEST)

    total = (req.key_cost_snapshot or 0) + (req.service_charge_snapshot or 0)
    req.status = 'payment_received'
    req.amount_paid = total
    req.paid_at = timezone.now()
    req.save()

    # Notify admins so they can assign the key
    from core.notification_utils import notify_admins
    notify_admins(
        title=f"Payment received — {req.company.name} / {req.get_agent_name_display()}",
        message=(
            f"{req.company.name} has confirmed payment of ${float(total):.2f} for a managed "
            f"{req.provider.upper()} key for {req.get_agent_name_display()}. Please assign the key."
        ),
        action_url='/admin/api-keys',
        notification_type='key_request_new',
    )

    return Response({
        'status': 'success',
        'amount_paid': float(total),
        'new_status': 'payment_received',
    })

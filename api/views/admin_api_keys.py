"""Super-admin API for company API keys, pricing, quotas, and key requests.

All endpoints require IsAuthenticated + IsAdmin (staff/superuser). This is the
control panel backend for the Super Admin Dashboard.
"""
import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.permissions import IsAdmin
from core.models import (
    AGENT_CHOICES,
    AGENT_DEFAULT_PROVIDER,
    PROVIDER_CHOICES,
    AdminPricingConfig,
    AgentProviderUsage,
    AgentTokenQuota,
    Company,
    CompanyAPIKey,
    CompanyModulePurchase,
    KeyRequest,
    PlatformAPIKey,
)

logger = logging.getLogger(__name__)

VALID_AGENTS = {name for name, _ in AGENT_CHOICES}
VALID_PROVIDERS = {name for name, _ in PROVIDER_CHOICES}


# ----------------------------------------------------------------------------
# Keys — assign / revoke managed keys + view BYOK (masked)
# ----------------------------------------------------------------------------

def _serialize_admin_key(key: CompanyAPIKey):
    return {
        'id': key.id,
        'company_id': key.company_id,
        'company_name': key.company.name,
        'agent_name': key.agent_name,
        'agent_label': key.get_agent_name_display(),
        'provider': key.provider,
        'mode': key.mode,
        'masked': key.masked_display,
        'status': key.status,
        'assigned_by': key.assigned_by.username if key.assigned_by else None,
        'created_at': key.created_at.isoformat(),
        'updated_at': key.updated_at.isoformat(),
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def list_all_keys(request):
    """List every CompanyAPIKey across all companies (paginated).

    Query params:
      - company_id, agent_name, mode, status, provider, search (company name)
    """
    qs = CompanyAPIKey.objects.select_related('company', 'assigned_by').order_by('-updated_at')

    company_id = request.GET.get('company_id')
    if company_id:
        qs = qs.filter(company_id=company_id)
    for field in ('agent_name', 'mode', 'status', 'provider'):
        val = request.GET.get(field)
        if val:
            qs = qs.filter(**{field: val})
    search = request.GET.get('search')
    if search:
        qs = qs.filter(company__name__icontains=search)

    page = int(request.GET.get('page', 1))
    limit = min(int(request.GET.get('limit', 20)), 100)
    total = qs.count()
    start = (page - 1) * limit
    items = qs[start:start + limit]

    return Response({
        'status': 'success',
        'total': total,
        'page': page,
        'limit': limit,
        'keys': [_serialize_admin_key(k) for k in items],
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdmin])
def assign_managed_key(request):
    """Assign (or replace) a managed key for a (company, agent).

    Body: { company_id, agent_name, provider, api_key, request_id? }
    If `request_id` is passed, the matching KeyRequest is marked approved.
    """
    company_id = request.data.get('company_id')
    agent_name = (request.data.get('agent_name') or '').strip()
    provider = (request.data.get('provider') or 'openai').strip()
    api_key = (request.data.get('api_key') or '').strip()
    request_id = request.data.get('request_id')

    if not company_id or agent_name not in VALID_AGENTS or provider not in VALID_PROVIDERS:
        return Response({'status': 'error', 'message': 'Missing or invalid fields'},
                        status=status.HTTP_400_BAD_REQUEST)
    if len(api_key) < 10:
        return Response({'status': 'error', 'message': 'API key looks too short'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        company = Company.objects.get(pk=company_id)
    except Company.DoesNotExist:
        return Response({'status': 'error', 'message': 'Company not found'},
                        status=status.HTTP_404_NOT_FOUND)

    with transaction.atomic():
        key, _ = CompanyAPIKey.objects.get_or_create(
            company=company, agent_name=agent_name, mode='managed',
            defaults={'provider': provider, 'encrypted_key': ''},
        )
        key.provider = provider
        key.status = 'active'
        key.set_plaintext_key(api_key)
        key.assigned_by = request.user
        key.save()

        approved_req = None
        if request_id:
            try:
                req = KeyRequest.objects.get(pk=request_id, company=company, agent_name=agent_name)
                req.status = 'approved'
                req.resolved_by = request.user
                req.resolved_at = timezone.now()
                req.save()
                approved_req = req
            except KeyRequest.DoesNotExist:
                pass

    # Notify the requester — outside the transaction so a notification failure
    # can never roll back the key assignment.
    if approved_req and approved_req.requested_by:
        from core.notification_utils import notify_company_user
        notify_company_user(
            approved_req.requested_by,
            title=f"Managed key approved — {key.get_agent_name_display()}",
            message=(
                f"Admin has assigned a managed {key.get_provider_display()} key for "
                f"{key.get_agent_name_display()}. It is now active on your account."
            ),
            action_url='/company/settings/api-keys',
            notification_type='key_request_approved',
        )

    return Response({'status': 'success', 'key': _serialize_admin_key(key)})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdmin])
def revoke_key(request, key_id):
    """Revoke (soft) any key — managed or BYOK. Sets status='revoked'."""
    try:
        key = CompanyAPIKey.objects.get(pk=key_id)
    except CompanyAPIKey.DoesNotExist:
        return Response({'status': 'error', 'message': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    key.status = 'revoked'
    key.save(update_fields=['status', 'updated_at'])
    return Response({'status': 'success'})


# ----------------------------------------------------------------------------
# Pricing
# ----------------------------------------------------------------------------

def _serialize_pricing(p: AdminPricingConfig):
    return {
        'agent_name': p.agent_name,
        'agent_label': p.get_agent_name_display(),
        'monthly_flat_usd': str(p.monthly_flat_usd),
        'service_charge_usd': str(p.service_charge_usd),
        'free_tokens_on_purchase': p.free_tokens_on_purchase,
        'updated_by': p.updated_by.username if p.updated_by else None,
        'updated_at': p.updated_at.isoformat(),
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def list_pricing(request):
    """Return pricing for every agent. Auto-creates missing rows so the UI
    always has one row per agent to edit."""
    rows = []
    for agent_name, _ in AGENT_CHOICES:
        p, _ = AdminPricingConfig.objects.get_or_create(agent_name=agent_name)
        rows.append(_serialize_pricing(p))
    return Response({'status': 'success', 'pricing': rows})


@api_view(['PUT'])
@permission_classes([IsAuthenticated, IsAdmin])
def update_pricing(request, agent_name):
    if agent_name not in VALID_AGENTS:
        return Response({'status': 'error', 'message': 'Invalid agent'}, status=status.HTTP_400_BAD_REQUEST)
    p, _ = AdminPricingConfig.objects.get_or_create(agent_name=agent_name)
    try:
        if 'monthly_flat_usd' in request.data:
            p.monthly_flat_usd = request.data['monthly_flat_usd']
        if 'service_charge_usd' in request.data:
            p.service_charge_usd = request.data['service_charge_usd']
        if 'free_tokens_on_purchase' in request.data:
            p.free_tokens_on_purchase = int(request.data['free_tokens_on_purchase'])
    except (TypeError, ValueError):
        return Response({'status': 'error', 'message': 'Bad numeric value'},
                        status=status.HTTP_400_BAD_REQUEST)
    p.updated_by = request.user
    p.save()
    return Response({'status': 'success', 'pricing': _serialize_pricing(p)})


# ----------------------------------------------------------------------------
# Quotas
# ----------------------------------------------------------------------------

def _serialize_quota_admin(q: AgentTokenQuota):
    provider_breakdown = {
        row.provider: row.used_tokens
        for row in q.provider_usage.all()
    }
    # For historical usage before AgentProviderUsage existed, fall back to
    # default_provider so admin can still see which model this agent uses.
    default_provider = AGENT_DEFAULT_PROVIDER.get(q.agent_name, 'openai')
    if not provider_breakdown and q.used_tokens > 0:
        provider_breakdown = {default_provider: q.used_tokens}
    return {
        'id': q.id,
        'company_id': q.company_id,
        'company_name': q.company.name,
        'agent_name': q.agent_name,
        'agent_label': q.get_agent_name_display(),
        'included_tokens': q.included_tokens,
        'used_tokens': q.used_tokens,
        'remaining': q.remaining,
        'is_exhausted': q.is_exhausted,
        'byok_tokens_info': q.byok_tokens_info,
        'provider_breakdown': provider_breakdown,
        'default_provider': default_provider,
        'updated_at': q.updated_at.isoformat(),
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def list_quotas(request):
    qs = AgentTokenQuota.objects.select_related('company').prefetch_related('provider_usage').order_by('-updated_at')
    search = request.GET.get('search')
    if search:
        qs = qs.filter(company__name__icontains=search)
    agent = request.GET.get('agent_name')
    if agent:
        qs = qs.filter(agent_name=agent)

    page = int(request.GET.get('page', 1))
    limit = min(int(request.GET.get('limit', 50)), 200)
    total = qs.count()
    start = (page - 1) * limit
    items = qs[start:start + limit]

    return Response({
        'status': 'success',
        'total': total,
        'page': page,
        'limit': limit,
        'quotas': [_serialize_quota_admin(q) for q in items],
    })


@api_view(['PATCH'])
@permission_classes([IsAuthenticated, IsAdmin])
def adjust_quota(request, quota_id):
    """Manually adjust a quota. Supports:
      - action='reset' → used_tokens=0
      - action='set_included' → included_tokens=value
      - action='add_tokens' → included_tokens += value
    """
    try:
        q = AgentTokenQuota.objects.get(pk=quota_id)
    except AgentTokenQuota.DoesNotExist:
        return Response({'status': 'error', 'message': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    action = (request.data.get('action') or '').strip()
    try:
        if action == 'reset':
            q.used_tokens = 0
        elif action == 'set_included':
            q.included_tokens = int(request.data.get('value'))
        elif action == 'add_tokens':
            q.included_tokens = max(0, q.included_tokens + int(request.data.get('value')))
        else:
            return Response({'status': 'error', 'message': 'Invalid action'},
                            status=status.HTTP_400_BAD_REQUEST)
    except (TypeError, ValueError):
        return Response({'status': 'error', 'message': 'Bad numeric value'},
                        status=status.HTTP_400_BAD_REQUEST)
    q.save()
    return Response({'status': 'success', 'quota': _serialize_quota_admin(q)})


# ----------------------------------------------------------------------------
# Key Requests
# ----------------------------------------------------------------------------

def _serialize_request_admin(r: KeyRequest):
    return {
        'id': r.id,
        'company_id': r.company_id,
        'company_name': r.company.name,
        'agent_name': r.agent_name,
        'agent_label': r.get_agent_name_display(),
        'provider': r.provider,
        'status': r.status,
        'note': r.note,
        'admin_note': r.admin_note,
        'requested_by': r.requested_by.email if r.requested_by else None,
        'resolved_by': r.resolved_by.username if r.resolved_by else None,
        'created_at': r.created_at.isoformat(),
        'resolved_at': r.resolved_at.isoformat() if r.resolved_at else None,
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def list_requests(request):
    qs = KeyRequest.objects.select_related('company', 'requested_by', 'resolved_by').order_by('-created_at')
    status_filter = request.GET.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)
    search = request.GET.get('search')
    if search:
        qs = qs.filter(company__name__icontains=search)

    page = int(request.GET.get('page', 1))
    limit = min(int(request.GET.get('limit', 50)), 200)
    total = qs.count()
    start = (page - 1) * limit
    items = qs[start:start + limit]
    return Response({
        'status': 'success',
        'total': total,
        'page': page,
        'limit': limit,
        'requests': [_serialize_request_admin(r) for r in items],
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdmin])
def reject_request(request, request_id):
    try:
        req = KeyRequest.objects.get(pk=request_id)
    except KeyRequest.DoesNotExist:
        return Response({'status': 'error', 'message': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    req.status = 'rejected'
    req.resolved_by = request.user
    req.resolved_at = timezone.now()
    req.admin_note = (request.data.get('admin_note') or '').strip()
    req.save()

    if req.requested_by:
        from core.notification_utils import notify_company_user
        notify_company_user(
            req.requested_by,
            title=f"Managed key request rejected — {req.get_agent_name_display()}",
            message=(
                (req.admin_note or 'Your request was rejected by the admin. '
                 'You can still add your own BYOK key to continue using this agent.')
            ),
            action_url='/company/settings/api-keys',
            notification_type='key_request_rejected',
        )

    return Response({'status': 'success', 'request': _serialize_request_admin(req)})


# ----------------------------------------------------------------------------
# Overview — single call that feeds the whole dashboard
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# Platform keys (the shared "free tokens" keys)
# ----------------------------------------------------------------------------

def _serialize_platform(p: PlatformAPIKey):
    return {
        'id': p.id,
        'provider': p.provider,
        'provider_label': p.get_provider_display(),
        'masked': p.masked_display,
        'status': p.status,
        'updated_by': p.updated_by.username if p.updated_by else None,
        'updated_at': p.updated_at.isoformat(),
        'configured': bool(p.encrypted_key),
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def list_platform_keys(request):
    """Return one row per provider (auto-creates stubs so UI always has
    all providers to configure)."""
    rows = []
    for provider, _ in PROVIDER_CHOICES:
        p = PlatformAPIKey.objects.filter(provider=provider).first()
        if not p:
            rows.append({
                'id': None, 'provider': provider,
                'provider_label': dict(PROVIDER_CHOICES)[provider],
                'masked': '', 'status': 'active',
                'updated_by': None, 'updated_at': None, 'configured': False,
            })
        else:
            rows.append(_serialize_platform(p))
    return Response({'status': 'success', 'platform_keys': rows})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdmin])
def upsert_platform_key(request):
    """Set/replace the platform key for one provider. Body: { provider, api_key }."""
    provider = (request.data.get('provider') or '').strip()
    api_key = (request.data.get('api_key') or '').strip()
    if provider not in VALID_PROVIDERS:
        return Response({'status': 'error', 'message': 'Invalid provider'},
                        status=status.HTTP_400_BAD_REQUEST)
    if len(api_key) < 10:
        return Response({'status': 'error', 'message': 'API key looks too short'},
                        status=status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        p, _ = PlatformAPIKey.objects.get_or_create(provider=provider)
        p.set_plaintext_key(api_key)
        p.status = 'active'
        p.updated_by = request.user
        p.save()
    return Response({'status': 'success', 'platform_key': _serialize_platform(p)})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdmin])
def revoke_platform_key(request, provider):
    try:
        p = PlatformAPIKey.objects.get(provider=provider)
    except PlatformAPIKey.DoesNotExist:
        return Response({'status': 'error', 'message': 'Not found'},
                        status=status.HTTP_404_NOT_FOUND)
    p.status = 'revoked'
    p.save(update_fields=['status', 'updated_at'])
    return Response({'status': 'success'})


# ----------------------------------------------------------------------------
# Company picker (for admin key-assign modal)
# ----------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def list_companies_simple(request):
    """Lightweight company picker for the admin UI. Optional ?search=."""
    qs = Company.objects.order_by('name')
    search = request.GET.get('search')
    if search:
        qs = qs.filter(name__icontains=search)
    rows = [{'id': c.id, 'name': c.name, 'email': c.email} for c in qs[:100]]
    return Response({'status': 'success', 'companies': rows})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def admin_overview(request):
    """Top-level stats for the admin dashboard landing."""
    from django.db.models import F, Sum
    agg = AgentTokenQuota.objects.aggregate(
        total_included=Sum('included_tokens'),
        total_used=Sum('used_tokens'),
        total_byok_info=Sum('byok_tokens_info'),
    )
    # Per-provider aggregate across all companies
    provider_totals = {
        row['provider']: row['total']
        for row in AgentProviderUsage.objects.values('provider').annotate(total=Sum('used_tokens'))
    }
    stats = {
        'total_companies': Company.objects.count(),
        'total_purchases': CompanyModulePurchase.objects.filter(status='active').count(),
        'total_keys': CompanyAPIKey.objects.filter(status='active').count(),
        'managed_keys': CompanyAPIKey.objects.filter(status='active', mode='managed').count(),
        'byok_keys': CompanyAPIKey.objects.filter(status='active', mode='byok').count(),
        'platform_keys_configured': PlatformAPIKey.objects.filter(status='active').exclude(encrypted_key='').count(),
        'pending_requests': KeyRequest.objects.filter(status='pending').count(),
        'exhausted_quotas': AgentTokenQuota.objects.filter(used_tokens__gte=F('included_tokens')).count(),
        'total_included_tokens': agg['total_included'] or 0,
        'total_used_tokens': agg['total_used'] or 0,
        'total_byok_info_tokens': agg['total_byok_info'] or 0,
        'provider_totals': provider_totals,
    }
    return Response({'status': 'success', 'stats': stats})

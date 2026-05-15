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
    for k in CompanyAPIKey.objects.filter(company=company, status='active'):
        keys_by_agent.setdefault(k.agent_name, {})[k.mode] = k

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

    key, _ = CompanyAPIKey.objects.get_or_create(
        company=company, agent_name=agent_name, mode='byok',
        defaults={'provider': provider, 'encrypted_key': ''},
    )
    key.provider = provider
    key.status = 'active'
    key.set_plaintext_key(api_key)
    key.save()

    return Response({'status': 'success', 'key': _serialize_key(key)})


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


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_key_requests(request):
    """List this company's KeyRequests (all statuses)."""
    company = request.user.company
    reqs = KeyRequest.objects.filter(company=company).select_related('requested_by', 'resolved_by')
    data = [{
        'id': r.id,
        'agent_name': r.agent_name,
        'agent_label': r.get_agent_name_display(),
        'provider': r.provider,
        'note': r.note,
        'status': r.status,
        'admin_note': r.admin_note,
        'requested_by': r.requested_by.email if r.requested_by else None,
        'resolved_by': r.resolved_by.username if r.resolved_by else None,
        'created_at': r.created_at.isoformat(),
        'resolved_at': r.resolved_at.isoformat() if r.resolved_at else None,
    } for r in reqs]
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

"""Agent catalogue endpoint.

Single source of truth for "which AI agents exist" across the whole frontend.
Every admin dropdown/filter reads from here instead of a hardcoded list, so
adding an Agent row makes it appear everywhere without a code change.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core.models import Agent, AdminPricingConfig


@api_view(['GET'])
@permission_classes([AllowAny])
def list_agents(request):
    """List agents for dropdowns, filters and pricing cards.

    Query params:
      - `all=1`          include inactive/retired agents (admin screens that need
                         to render historical rows).
      - `purchasable=1`  only agents currently on sale.

    AllowAny because the public pricing/module cards render from this too; the
    payload is catalogue metadata only — no company or key data.
    """
    try:
        qs = Agent.objects.all()
        if request.query_params.get('all') != '1':
            qs = qs.filter(is_active=True)
        if request.query_params.get('purchasable') == '1':
            qs = qs.filter(is_purchasable=True)

        # Pricing lives in AdminPricingConfig, keyed by slug. Fetch in one query
        # rather than per-agent to keep this endpoint cheap — it's called on
        # nearly every admin page load.
        pricing = {
            p.agent_name: p
            for p in AdminPricingConfig.objects.filter(
                agent_name__in=list(qs.values_list('slug', flat=True))
            )
        }

        data = []
        for agent in qs:
            cfg = pricing.get(agent.slug)
            data.append({
                # `value`/`label` mirror the shape the existing frontend Select
                # options already use, so dropdowns can consume this as-is.
                'value': agent.slug,
                'label': agent.name,
                'slug': agent.slug,
                'name': agent.name,
                'description': agent.description,
                'features': agent.features or [],
                'default_provider': agent.default_provider,
                'is_active': agent.is_active,
                'is_purchasable': agent.is_purchasable,
                'sort_order': agent.sort_order,
                'monthly_price': float(cfg.monthly_flat_usd) if cfg else None,
            })

        return Response({'status': 'success', 'data': data}, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch agents',
            'error': str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

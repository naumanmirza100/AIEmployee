"""Module-access guard for reply_draft_agent views.

Matches the pattern in api/views/module_purchase.py: a purchase is tied to
Company, and we resolve the logged-in user to a Company before checking.
Falls open when no Company is attached (dev/single-tenant mode) so the guard
doesn't break setups that predate the purchase system.
"""
from functools import wraps
from django.http import JsonResponse
from django.utils import timezone

from core.models import CompanyModulePurchase, CompanyUser


MODULE_NAME = 'reply_draft_agent'


def _resolve_company(user):
    """Best-effort resolution from Django User → Company.

    The codebase uses two user types: Django's contrib.auth User and CompanyUser.
    CompanyUser is the one with a Company FK. We try a few heuristics.
    Returns Company or None.
    """
    if not user or not user.is_authenticated:
        return None

    company = getattr(user, 'company', None)
    if company is not None:
        return company

    email = getattr(user, 'email', None)
    if email:
        cu = CompanyUser.objects.filter(email=email, is_active=True).select_related('company').first()
        if cu:
            return cu.company

    return None


def company_has_module(company):
    if company is None:
        return False
    purchase = CompanyModulePurchase.objects.filter(
        company=company, module_name=MODULE_NAME
    ).first()
    if not purchase:
        return False
    if purchase.status == 'active' and purchase.expires_at and timezone.now() > purchase.expires_at:
        purchase.status = 'expired'
        purchase.save(update_fields=['status'])
    return purchase.is_active()


def requires_reply_draft_module(view):
    """Block the view if the caller's company hasn't purchased reply_draft_agent.

    Falls open if no Company can be resolved (preserves dev/test workflows).
    """
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        company = _resolve_company(getattr(request, 'user', None))
        if company is not None and not company_has_module(company):
            return JsonResponse({
                'success': False,
                'error': 'Reply Draft Agent is not active for your company. Purchase required.',
                'module_name': MODULE_NAME,
            }, status=403)
        return view(request, *args, **kwargs)
    return wrapper

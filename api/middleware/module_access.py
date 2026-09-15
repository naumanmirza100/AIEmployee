"""Server-side enforcement of agent module subscriptions.

Until now only `reply_draft_agent` checked a purchase on the server; every other
agent relied on the React app hiding its pages. That is not enforcement — a
cancelled or expired customer keeps full API access by calling the endpoints
directly, so cancellation never actually stopped anyone using the product.

Why middleware rather than a decorator: there are ~500 `@api_view` functions
across the ten agent modules. Decorating each one is a guarantee that somebody
adding endpoint 501 forgets, and the hole silently reopens. The URL prefixes map
cleanly onto agents, so a single prefix check covers everything written so far
and everything added later, by construction.

Fails OPEN when no company can be resolved (anonymous, staff, or non-agent
routes) — those paths are already gated by their own auth, and this layer only
answers "has this company paid for this agent".
"""
import logging
import re

from django.http import JsonResponse

logger = logging.getLogger(__name__)

# URL prefix (first path segment under /api/) → Agent slug.
# Keep in step with api/urls.py; a prefix that isn't listed is simply not gated.
PREFIX_TO_MODULE = {
    'recruitment': 'recruitment_agent',
    'marketing': 'marketing_agent',
    'project-manager': 'project_manager_agent',
    'frontline': 'frontline_agent',
    'operations': 'operations_agent',
    'reply-draft': 'reply_draft_agent',
    'hr': 'hr_agent',
    'sdr': 'ai_sdr_agent',
    'crm-sync': 'crm_sync_agent',
    'exec-meeting': 'exec_meeting_agent',
}

# Agent endpoints that live under a SHARED parent prefix, matched against the
# path after `/api/`.
#
# `company/` and `user/` can't go in PREFIX_TO_MODULE: they also host login,
# signup, password reset, API-key management and several agents side by side,
# so gating the whole prefix would lock unsubscribed companies out of logging
# in. Before this map existed, PM endpoints under these parents weren't gated at
# all — a company whose project_manager_agent subscription had lapsed was
# blocked from `/api/project-manager/...` but could still create and update
# projects and tasks through `/api/user/project-manager/...` and
# `/api/company/tasks/...`.
#
# Deliberately NOT gated:
#   company/projects   (exact) — CompanyDashboardPage loads this for every
#                      company as its landing view. Gating it would 403 the home
#                      page for anyone who bought only, say, Frontline.
#   user/tasks, user/projects — team members viewing and updating work already
#                      assigned to them.
NESTED_PATTERNS_TO_MODULE = (
    (re.compile(r'^user/project-manager(/|$)'), 'project_manager_agent'),
    (re.compile(r'^company/projects/list/?$'), 'project_manager_agent'),
    (re.compile(r'^company/projects/\d+/'), 'project_manager_agent'),
    (re.compile(r'^company/tasks(/|$)'), 'project_manager_agent'),
)

# Sub-paths that must stay reachable without the module, so a company that has
# not subscribed (or has lapsed) can still see pricing and buy their way back in.
EXEMPT_SUFFIXES = ('/access', '/plans', '/prices')


class ModuleAccessMiddleware:
    """Reject agent API calls from companies without an active subscription."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        module_name = self._module_for(request.path)
        if module_name:
            company = self._resolve_company(request)
            if company is not None and not self._has_module(company, module_name):
                logger.info(
                    'Blocked %s for company %s — no active %s subscription.',
                    request.path, company.id, module_name,
                )
                return JsonResponse({
                    'success': False,
                    'status': 'error',
                    'error': 'subscription_required',
                    'module_name': module_name,
                    'message': (
                        'Your subscription for this agent is not active. '
                        'Please subscribe or renew to continue.'
                    ),
                }, status=403)
        return self.get_response(request)

    @staticmethod
    def _module_for(path):
        """Map a request path to an agent slug, or None if it isn't gated."""
        if not path.startswith('/api/'):
            return None
        rest = path[len('/api/'):]
        prefix = rest.split('/', 1)[0]
        module_name = PREFIX_TO_MODULE.get(prefix)
        if not module_name:
            for pattern, nested_module in NESTED_PATTERNS_TO_MODULE:
                if pattern.match(rest):
                    module_name = nested_module
                    break
        if not module_name:
            return None
        if path.rstrip('/').endswith(EXEMPT_SUFFIXES):
            return None
        return module_name

    @staticmethod
    def _resolve_company(request):
        """Resolve the caller to a Company, or None to fall open.

        Middleware runs BEFORE DRF authenticates, so `request.user` is not yet the
        CompanyUser — the token has to be read directly here. Staff/superusers are
        deliberately exempt so admin tooling keeps working.
        """
        from core.models import CompanyUser, CompanyUserToken

        django_user = getattr(request, 'user', None)
        if django_user is not None and getattr(django_user, 'is_authenticated', False):
            if getattr(django_user, 'is_staff', False) or getattr(django_user, 'is_superuser', False):
                return None

        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        token_key = None
        for keyword in ('Token ', 'Bearer '):
            if auth_header.startswith(keyword):
                token_key = auth_header[len(keyword):].strip()
                break

        if token_key:
            try:
                token = (
                    CompanyUserToken.objects
                    .select_related('company_user__company')
                    .get(key=token_key)
                )
            except CompanyUserToken.DoesNotExist:
                token = None
            except Exception as exc:
                logger.warning('ModuleAccessMiddleware: token lookup failed: %s', exc)
                return None

            if token is not None:
                company_user = token.company_user
                if not isinstance(company_user, CompanyUser) or not company_user.is_active:
                    return None
                return company_user.company

            # Not a CompanyUser token. The `user/...` routes authenticate end
            # users (auth.User) with DRF's own authtoken.Token — without this
            # branch every such request fell open, so gating those routes would
            # have been a no-op for exactly the callers it targets.
            return ModuleAccessMiddleware._company_for_auth_user_token(token_key)

        # No bearer token: a session-authenticated end user. AuthenticationMiddleware
        # runs before this one, so `request.user` is already populated.
        if django_user is not None and getattr(django_user, 'is_authenticated', False):
            return ModuleAccessMiddleware._company_for_django_user(django_user)
        return None

    @staticmethod
    def _company_for_auth_user_token(token_key):
        try:
            from rest_framework.authtoken.models import Token
            token = Token.objects.select_related('user').get(key=token_key)
        except Exception:
            return None      # invalid token — let DRF produce the 401
        return ModuleAccessMiddleware._company_for_django_user(token.user)

    @staticmethod
    def _company_for_django_user(user):
        """End users belong to a company through their UserProfile — directly,
        or via the CompanyUser who created them."""
        if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
            return None
        try:
            from core.models import UserProfile
            profile = (UserProfile.objects
                       .select_related('company', 'created_by_company_user__company')
                       .filter(user=user).first())
        except Exception as exc:
            logger.warning('ModuleAccessMiddleware: profile lookup failed: %s', exc)
            return None
        if profile is None:
            return None
        if profile.company_id:
            return profile.company
        if profile.created_by_company_user_id:
            return profile.created_by_company_user.company
        return None

    @staticmethod
    def _has_module(company, module_name):
        from core.models import CompanyModulePurchase

        purchase = CompanyModulePurchase.objects.filter(
            company=company, module_name=module_name,
        ).first()
        return bool(purchase and purchase.is_active())

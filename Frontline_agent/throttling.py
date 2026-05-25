"""
Throttle classes for Frontline Agent endpoints.

Rates live in settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].
Public throttles key by IP (AnonRateThrottle base); authenticated
throttles key by user (UserRateThrottle base).
"""
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class FrontlinePublicThrottle(AnonRateThrottle):
    scope = 'frontline_public'


class FrontlineLLMThrottle(UserRateThrottle):
    scope = 'frontline_llm'


class FrontlineUploadThrottle(UserRateThrottle):
    scope = 'frontline_upload'


class FrontlineCRUDThrottle(UserRateThrottle):
    scope = 'frontline_crud'


class FrontlineWidgetKeyThrottle(AnonRateThrottle):
    """Throttle public widget calls by widget_key, not just IP.

    The default ``FrontlinePublicThrottle`` keys on IP, which has two failure
    modes: (a) two abusive visitors on different IPs each pass under the limit
    and together still flood; (b) every visitor behind a corporate NAT shares
    one IP and one slow user can DoS the rest. Keying by widget_key fixes both
    — each tenant has its own budget regardless of caller spread.

    Combine with the per-IP throttle (apply BOTH) so a single IP still can't
    flood: ``@throttle_classes([FrontlinePublicThrottle, FrontlineWidgetKeyThrottle])``.
    """
    scope = 'frontline_widget_key'

    def get_ident(self, request):  # noqa: D401 — DRF hook
        # widget_key may arrive in the body, query string, or header.
        key = (
            (request.data or {}).get('widget_key')
            if hasattr(request, 'data') and isinstance(request.data, dict) else None
        ) or request.GET.get('widget_key') or request.headers.get('X-Widget-Key')
        if key:
            # Prefix so the cache key never collides with a stray IP that
            # happens to look like a UUID.
            return f"wk:{key}"
        # No widget_key in this request: fall back to IP so the throttle still
        # counts something. Equivalent to the base AnonRateThrottle behaviour.
        return super().get_ident(request)

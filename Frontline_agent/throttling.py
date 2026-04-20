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

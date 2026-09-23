"""Throttle classes for HR Support Agent endpoints. Mirrors Frontline's
pattern (scope per endpoint type), but with HR-specific scope names so the
two agents don't share a rate budget. Rates live in
``settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']``.
"""
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class HRPublicThrottle(AnonRateThrottle):
    """Public/widget-style endpoints (no auth)."""
    scope = 'hr_public'


class HRStreamThrottle(UserRateThrottle):
    """Tighter budget for streamed answers.

    A stream holds a worker for the whole generation, not just for a
    request/response round trip, so unlimited concurrent streams are an
    availability problem as well as a cost one (HR-GAP-2).
    """
    scope = 'hr_stream'


class HRLLMThrottle(UserRateThrottle):
    """LLM-backed endpoints — Knowledge Q&A, summaries, draft replies."""
    scope = 'hr_llm'


class HRUploadThrottle(UserRateThrottle):
    """Document upload endpoints — bound CPU + storage cost per tenant."""
    scope = 'hr_upload'


class HRCRUDThrottle(UserRateThrottle):
    """Routine CRUD on HR objects (employees, leave requests, meetings)."""
    scope = 'hr_crud'

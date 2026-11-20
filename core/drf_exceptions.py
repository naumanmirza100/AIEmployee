"""Global DRF exception handler.

Catches `KeyServiceError` subclasses (QuotaExhausted, NoKeyAvailable, ...) raised
deep inside agent code and converts them into clean 402/403 JSON responses so
the frontend can show the hard-block UI without each view catching explicitly.
An AI provider that is out of credit or can't be reached (AIServiceUnavailable)
is a 503 with its own message.
"""
from rest_framework.response import Response
from rest_framework.views import exception_handler

from core.api_key_service import (
    AIServiceUnavailable, ByokCapReached, KeyServiceError, ManagedQuotaExhausted, NoKeyAvailable, NotSubscribed,
    QuotaExhausted,
)


def key_error_status(exc):
    """The HTTP status for a KeyServiceError."""
    if isinstance(exc, AIServiceUnavailable):
        return 503                      # the provider, not the company: out of credit or unreachable (19 Nov 2026)
    if isinstance(exc, (QuotaExhausted, ManagedQuotaExhausted, ByokCapReached)):
        return 402
    if isinstance(exc, (NoKeyAvailable, NotSubscribed)):
        return 403
    return 400                          # BadAPIKey and the rest


def key_service_exception_handler(exc, context):
    if isinstance(exc, KeyServiceError):
        return Response({
            'status': 'error',
            'code': exc.reason,
            'message': exc.user_message,
            'hard_block': True,
        }, status=key_error_status(exc))

    return exception_handler(exc, context)

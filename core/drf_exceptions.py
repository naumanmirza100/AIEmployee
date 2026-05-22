"""Global DRF exception handler.

Catches `KeyServiceError` subclasses (QuotaExhausted, NoKeyAvailable, ...) raised
deep inside agent code and converts them into clean 402/403 JSON responses so
the frontend can show the hard-block UI without each view catching explicitly.
"""
from rest_framework.response import Response
from rest_framework.views import exception_handler

from core.api_key_service import BadAPIKey, ByokCapReached, KeyServiceError, ManagedQuotaExhausted, NoKeyAvailable, QuotaExhausted


def key_service_exception_handler(exc, context):
    if isinstance(exc, KeyServiceError):
        if isinstance(exc, (QuotaExhausted, ManagedQuotaExhausted, ByokCapReached)):
            http_status = 402
        elif isinstance(exc, NoKeyAvailable):
            http_status = 403
        elif isinstance(exc, BadAPIKey):
            http_status = 400
        else:
            http_status = 400
        return Response({
            'status': 'error',
            'code': exc.reason,
            'message': exc.user_message,
            'hard_block': True,
        }, status=http_status)

    return exception_handler(exc, context)

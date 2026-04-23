"""Global DRF exception handler.

Catches `KeyServiceError` subclasses (QuotaExhausted, NoKeyAvailable, ...) raised
deep inside agent code and converts them into clean 402/403 JSON responses so
the frontend can show the hard-block UI without each view catching explicitly.
"""
from rest_framework.response import Response
from rest_framework.views import exception_handler

from core.api_key_service import KeyServiceError, QuotaExhausted, NoKeyAvailable


def key_service_exception_handler(exc, context):
    if isinstance(exc, KeyServiceError):
        http_status = 402 if isinstance(exc, QuotaExhausted) else 403 if isinstance(exc, NoKeyAvailable) else 400
        return Response({
            'status': 'error',
            'code': exc.reason,
            'message': exc.user_message,
            'hard_block': True,
        }, status=http_status)

    return exception_handler(exc, context)

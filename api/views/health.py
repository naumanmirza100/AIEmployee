import logging

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db import connection
from django.utils import timezone


@api_view(['GET'])
@permission_classes([AllowAny])
def ping(request):
    """Bare liveness check — no DB, no auth. Confirms only that the
    backend process is up and serving requests."""
    return Response({'status': 'ok', 'message': 'pong'}, status=200)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def version(request):
    """This server's API level (core/version.py), for the screens to compare
    with the level they were built against. A logged-in screen that needs more
    than this server has (`?needs=N`) is reported to the people who run the
    site: someone uploaded a frontend the backend isn't ready for."""
    from api.middleware.module_access import ModuleAccessMiddleware
    from core.version import API_LEVEL

    needs = request.query_params.get('needs', '')
    if needs.isdigit() and int(needs) > API_LEVEL and ModuleAccessMiddleware._resolve_company(request._request):
        logging.getLogger('alerts').error(
            'The screens people are using need API level %s; this server is at %s. The frontend '
            'was uploaded before the backend it needs: deploy the latest main.',
            needs, API_LEVEL, extra={'alert_key': 'api-level-behind'})
    return Response({'api_level': API_LEVEL}, status=200)


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Health check endpoint"""
    try:
        # Test database connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        
        return Response({
            'status': 'ok',
            'message': 'Server is running',
            'database': 'connected',
            'timestamp': timezone.now().isoformat(),
        }, status=200)
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Server error',
            'database': 'disconnected',
            'error': str(e),
        }, status=500)


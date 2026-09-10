from rest_framework.decorators import api_view, permission_classes
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


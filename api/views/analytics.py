from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.utils import timezone

from core.models import AnalyticsEvent, PageView
from api.serializers.analytics import AnalyticsEventSerializer, PageViewSerializer


@api_view(['POST'])
@permission_classes([AllowAny])  # Allow anonymous tracking
def log_analytics_event(request):
    """Log analytics event"""
    try:
        data = request.data
        
        event_data = {
            'event_type': data.get('eventType') or data.get('event_type', ''),
            'event_name': data.get('eventName') or data.get('event_name', ''),
            'properties': data.get('properties') or data.get('eventData') or data.get('event_data', {}),
            'ip_address': request.META.get('REMOTE_ADDR'),
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
        }
        
        # Add user if authenticated
        if request.user.is_authenticated:
            event_data['user'] = request.user
        
        # Handle properties field - convert dict to JSON string
        properties = event_data.get('properties', {})
        if isinstance(properties, dict):
            import json
            event_data['properties'] = json.dumps(properties)
        elif not isinstance(properties, str):
            event_data['properties'] = ''
        
        serializer = AnalyticsEventSerializer(data=event_data)
        
        if serializer.is_valid():
            event = serializer.save()
            
            return Response({
                'status': 'success',
                'message': 'Event logged successfully',
                'data': {'id': event.id}
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'status': 'error',
            'message': 'Validation error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to log event',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])  # Allow anonymous tracking
def log_page_view(request):
    """Log page view"""
    try:
        data = request.data
        
        page_view_data = {
            'page_path': data.get('pagePath') or data.get('page_path', ''),
            'page_title': data.get('pageTitle') or data.get('page_title', ''),
            'referrer': data.get('referrer', ''),
            'ip_address': request.META.get('REMOTE_ADDR'),
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            'session_id': data.get('sessionId') or data.get('session_id'),
            'duration': data.get('duration'),
        }
        
        # Add user if authenticated
        if request.user.is_authenticated:
            page_view_data['user'] = request.user
        
        serializer = PageViewSerializer(data=page_view_data)
        
        if serializer.is_valid():
            page_view = serializer.save()
            
            return Response({
                'status': 'success',
                'message': 'Page view logged successfully',
                'data': {'id': page_view.id}
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'status': 'error',
            'message': 'Validation error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to log page view',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


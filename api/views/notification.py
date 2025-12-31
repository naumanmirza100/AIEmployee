from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone

from core.models import Notification


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_notifications(request):
    """Get user notifications"""
    try:
        user = request.user
        
        # Get unread notifications first, then read
        unread = Notification.objects.filter(user=user, is_read=False).order_by('-created_at')
        read = Notification.objects.filter(user=user, is_read=True).order_by('-created_at')[:50]  # Limit read notifications
        
        # Serialize notifications
        notifications_data = []
        for notif in unread:
            notifications_data.append({
                'id': notif.id,
                'title': notif.title,
                'message': notif.message,
                'type': notif.type,
                'link': notif.link,
                'is_read': notif.is_read,
                'created_at': notif.created_at.isoformat() if notif.created_at else None
            })
        
        for notif in read:
            notifications_data.append({
                'id': notif.id,
                'title': notif.title,
                'message': notif.message,
                'type': notif.type,
                'link': notif.link,
                'is_read': notif.is_read,
                'created_at': notif.created_at.isoformat() if notif.created_at else None
            })
        
        return Response({
            'status': 'success',
            'data': notifications_data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch notifications',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def mark_notification_read(request, id):
    """Mark notification as read"""
    try:
        notification = get_object_or_404(Notification, id=id, user=request.user)
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save()
        
        return Response({
            'status': 'success',
            'message': 'Notification marked as read'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to update notification',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def mark_all_notifications_read(request):
    """Mark all notifications as read"""
    try:
        now = timezone.now()
        updated_count = Notification.objects.filter(user=request.user, is_read=False).update(
            is_read=True,
            read_at=now
        )
        
        return Response({
            'status': 'success',
            'message': f'{updated_count} notifications marked as read'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to update notifications',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


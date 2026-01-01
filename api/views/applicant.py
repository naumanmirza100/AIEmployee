from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404

from recruitment_agent.models import CareerApplication
from api.serializers.career import CareerApplicationSerializer


@api_view(['GET'])
@permission_classes([AllowAny])
def get_application_status(request):
    """Get application status by token (Public)"""
    try:
        token = request.GET.get('token')
        
        if not token:
            return Response({
                'status': 'error',
                'message': 'Token is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            application = CareerApplication.objects.get(application_token=token)
        except CareerApplication.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Invalid token'
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = CareerApplicationSerializer(application)
        
        return Response({
            'status': 'success',
            'data': {
                'application': serializer.data,
                'status': application.status,
                'statusMessage': f'Your application is currently {application.status}'
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch application status',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


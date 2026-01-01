from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone

from core.models import Consultation
from api.serializers.consultation import ConsultationSerializer
from api.permissions import IsAdmin


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_consultation(request):
    """Create consultation request"""
    try:
        data = request.data.copy()
        
        consultation_data = {
            'name': data.get('name', ''),
            'email': data.get('email', ''),
            'phone': data.get('phone'),
            'company': data.get('company'),
            'industry': data.get('industry'),
            'project_type': data.get('projectType') or data.get('project_type'),
            'project_description': data.get('projectDescription') or data.get('project_description', ''),
            'budget_range': data.get('budgetRange') or data.get('budget_range'),
            'timeline': data.get('timeline'),
            'status': 'pending'
        }
        
        serializer = ConsultationSerializer(data=consultation_data)
        
        if serializer.is_valid():
            consultation = serializer.save()
            
            return Response({
                'status': 'success',
                'message': 'Consultation request submitted successfully',
                'data': ConsultationSerializer(consultation).data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'status': 'error',
            'message': 'Validation error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to create consultation request',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_consultations(request):
    """Get consultations (protected - user's own or admin sees all)"""
    try:
        user = request.user
        
        if user.is_staff:
            # Admin sees all
            query = Consultation.objects.all()
        else:
            # Regular users see their own
            query = Consultation.objects.filter(email=user.email)
        
        # Filter by status
        status_filter = request.GET.get('status')
        if status_filter:
            query = query.filter(status=status_filter)
        
        query = query.order_by('-created_at')
        
        serializer = ConsultationSerializer(query, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch consultations',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_consultation(request, id):
    """Get consultation by ID"""
    try:
        consultation = get_object_or_404(Consultation, id=id)
        
        # Check permissions
        if not request.user.is_staff and consultation.email != request.user.email:
            return Response({
                'status': 'error',
                'message': 'You do not have permission to view this consultation'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = ConsultationSerializer(consultation)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch consultation',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


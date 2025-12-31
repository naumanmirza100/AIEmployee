from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.shortcuts import get_object_or_404

from core.models import Industry, IndustryChallenge
from api.serializers.industry import IndustrySerializer, IndustryChallengeSerializer
from api.permissions import IsAdmin


@api_view(['GET'])
@permission_classes([AllowAny])
def list_industries(request):
    """List all industries"""
    try:
        industries = Industry.objects.all().order_by('name')
        serializer = IndustrySerializer(industries, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch industries',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_industry_by_slug(request, slug):
    """Get industry by slug"""
    try:
        industry = get_object_or_404(Industry, slug=slug)
        serializer = IndustrySerializer(industry)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch industry',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_industry_challenges(request, slug):
    """Get challenges for an industry"""
    try:
        # Verify industry exists
        industry = get_object_or_404(Industry, slug=slug)
        
        challenges = IndustryChallenge.objects.filter(industry_slug=slug).order_by('created_at')
        serializer = IndustryChallengeSerializer(challenges, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch challenges',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404

from core.models import WhiteLabelProduct
from api.serializers.white_label import WhiteLabelProductSerializer
import logging

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([AllowAny])
def list_white_label_products(request):
    """List white label products"""
    try:
        products = WhiteLabelProduct.objects.filter(status='active').order_by('-created_at')
        
        # Filter by category if provided
        category = request.GET.get('category')
        if category:
            products = products.filter(category=category)
        
        # Filter by featured if provided
        featured_only = request.GET.get('featured', '').lower() == 'true'
        if featured_only:
            products = products.filter(featured=True)
        
        serializer = WhiteLabelProductSerializer(products, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.exception('list_white_label_products failed')
        return Response({
            'status': 'error',
            'message': 'Failed to fetch products',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_white_label_product(request, id):
    """Get white label product by ID"""
    try:
        product = get_object_or_404(WhiteLabelProduct, id=id)
        serializer = WhiteLabelProductSerializer(product)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.exception('get_white_label_product failed')
        return Response({
            'status': 'error',
            'message': 'Failed to fetch product',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_white_label_categories(request):
    """Get white label product categories"""
    try:
        # Get distinct categories from active products
        categories = WhiteLabelProduct.objects.filter(status='active').values_list('category', flat=True).distinct()
        
        return Response({
            'status': 'success',
            'data': list(categories)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.exception('get_white_label_categories failed')
        return Response({
            'status': 'error',
            'message': 'Failed to fetch categories',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


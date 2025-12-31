from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db.models import Avg, Count

from core.models import Review
from api.serializers.review import ReviewSerializer


@api_view(['GET'])
@permission_classes([AllowAny])
def list_reviews(request):
    """List all reviews"""
    try:
        # Filter by featured if requested
        featured_only = request.GET.get('featured', '').lower() == 'true'
        query = Review.objects.all()
        
        if featured_only:
            query = query.filter(featured=True)
        
        # Order by display_order and created_at
        query = query.order_by('display_order', '-created_at')
        
        serializer = ReviewSerializer(query, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch reviews',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_reviews_summary(request):
    """Get reviews summary (average rating, total count)"""
    try:
        reviews = Review.objects.all()
        
        # Calculate average rating
        avg_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0
        
        # Get total count
        total_count = reviews.count()
        
        # Get count by rating
        rating_counts = reviews.values('rating').annotate(count=Count('id')).order_by('-rating')
        
        return Response({
            'status': 'success',
            'data': {
                'averageRating': round(float(avg_rating), 1),
                'totalReviews': total_count,
                'ratingDistribution': [
                    {'rating': item['rating'], 'count': item['count']} 
                    for item in rating_counts
                ]
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch reviews summary',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify

from core.models import BlogPost, BlogTag, BlogPostTag
from api.serializers.blog import BlogPostSerializer, BlogPostListSerializer, BlogTagSerializer
from api.permissions import IsAdmin


@api_view(['GET'])
@permission_classes([AllowAny])
def list_blog_posts(request):
    """List all published blog posts"""
    try:
        # Only show published posts for non-authenticated or non-admin users
        query = BlogPost.objects.filter(status='published')
        
        # Admin can see all posts
        if request.user.is_authenticated and request.user.is_staff:
            status_filter = request.GET.get('status')
            if status_filter:
                query = BlogPost.objects.filter(status=status_filter)
            else:
                query = BlogPost.objects.all()
        
        # Filter by category
        category = request.GET.get('category')
        if category:
            query = query.filter(category=category)
        
        # Filter by tag
        tag_slug = request.GET.get('tag')
        if tag_slug:
            try:
                tag = BlogTag.objects.get(slug=tag_slug)
                query = query.filter(tags=tag)
            except BlogTag.DoesNotExist:
                pass
        
        # Order by published_at or created_at
        query = query.order_by('-published_at', '-created_at')
        
        serializer = BlogPostListSerializer(query, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch blog posts',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_blog_post_by_slug(request, slug):
    """Get blog post by slug"""
    try:
        post = get_object_or_404(BlogPost, slug=slug)
        
        # Check if user can view unpublished posts
        if post.status != 'published' and (not request.user.is_authenticated or not request.user.is_staff):
            return Response({
                'status': 'error',
                'message': 'Blog post not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Increment views count
        post.views_count += 1
        post.save(update_fields=['views_count'])
        
        serializer = BlogPostSerializer(post)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch blog post',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_blog_categories(request):
    """Get blog categories"""
    try:
        # Get distinct categories from published posts
        categories = BlogPost.objects.filter(status='published').values_list('category', flat=True).distinct()
        
        return Response({
            'status': 'success',
            'data': list(categories)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch categories',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def list_blog_tags(request):
    """Get blog tags"""
    try:
        tags = BlogTag.objects.all().order_by('name')
        serializer = BlogTagSerializer(tags, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch tags',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


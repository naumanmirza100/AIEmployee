from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from core.models import UserProfile, Project, ProjectApplication, TeamMember, Credit
from django.db.models import Count, Q

from api.serializers.auth import UserSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_profile(request):
    """Get user profile"""
    try:
        user = request.user
        serializer = UserSerializer(user)
        
        # Get profile data
        profile_data = serializer.data
        if hasattr(user, 'profile'):
            profile = user.profile
            profile_data['profile'] = {
                'companyName': profile.company_name,
                'bio': profile.bio,
                'avatarUrl': profile.avatar_url,
                'location': profile.location,
                'timezone': profile.timezone,
                'website': profile.website,
                'linkedin': profile.linkedin,
                'github': profile.github,
            }
        
        return Response({
            'status': 'success',
            'data': profile_data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch profile',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    """Update user profile"""
    try:
        user = request.user
        data = request.data
        
        # Update user fields
        if 'first_name' in data:
            user.first_name = data['first_name']
        if 'last_name' in data:
            user.last_name = data['last_name']
        # Note: phone is not in Django User model, skip for now
        user.save()
        
        # Update or create profile
        profile, created = UserProfile.objects.get_or_create(user=user)
        
        if 'company_name' in data:
            profile.company_name = data['company_name']
        if 'bio' in data:
            profile.bio = data['bio']
        if 'avatar_url' in data:
            profile.avatar_url = data['avatar_url']
        if 'location' in data:
            profile.location = data['location']
        if 'timezone' in data:
            profile.timezone = data['timezone']
        if 'website' in data:
            profile.website = data['website']
        if 'linkedin' in data:
            profile.linkedin = data['linkedin']
        if 'github' in data:
            profile.github = data['github']
        
        profile.save()
        
        # Get updated data
        serializer = UserSerializer(user)
        
        return Response({
            'status': 'success',
            'message': 'Profile updated successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to update profile',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_dashboard_stats(request):
    """Get dashboard statistics"""
    try:
        user = request.user
        stats = {}
        
        # Determine user type
        user_type = 'client'
        if hasattr(user, 'profile'):
            role = user.profile.role
            if role == 'developer':
                user_type = 'freelancer'
            elif user.is_staff:
                user_type = 'admin'
        
        if user_type == 'client':
            # Client stats - use owner field (mapped from client_id in PayPerProject)
            projects = Project.objects.filter(owner=user)
            stats = {
                'total_projects': projects.count(),
                'posted': projects.filter(status='posted').count(),
                'in_progress': projects.filter(status='in_progress').count(),
                'completed': projects.filter(status='completed').count(),
            }
            
            # Get total applications for user's projects
            total_applications = ProjectApplication.objects.filter(
                project__owner=user
            ).count()
            stats['totalApplications'] = total_applications
            
        elif user_type == 'freelancer':
            # Freelancer stats
            applications = ProjectApplication.objects.filter(freelancer=user)
            stats = {
                'total_applications': applications.count(),
                'pending': applications.filter(status='pending').count(),
                'accepted': applications.filter(status='accepted').count(),
                'rejected': applications.filter(status='rejected').count(),
            }
            
            # Get active projects (where user is team member)
            active_projects = TeamMember.objects.filter(
                user=user,
                removed_at__isnull=True,
                project__status__in=['in_progress', 'review']
            ).count()
            stats['activeProjects'] = active_projects
        
        # Get credit balance
        try:
            credit = Credit.objects.get(user=user)
            stats['creditBalance'] = float(credit.balance)
        except Credit.DoesNotExist:
            stats['creditBalance'] = 0
        
        return Response({
            'status': 'success',
            'data': stats
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch dashboard stats',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q

from core.models import Project, ProjectApplication, Industry
from api.serializers.project import ProjectSerializer, ProjectListSerializer, ProjectApplicationSerializer
from api.permissions import IsOwnerOrAdmin


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_projects(request):
    """List projects with filtering"""
    try:
        user = request.user
        query = Project.objects.all()
        
        # Filter by status
        status_filter = request.GET.get('status')
        if status_filter:
            query = query.filter(status=status_filter)
        
        # Filter by user's projects (if not admin)
        if not user.is_staff:
            query = query.filter(Q(owner=user) | Q(project_manager=user))
        
        # Filter by industry
        industry_id = request.GET.get('industry_id')
        if industry_id:
            query = query.filter(industry_id=industry_id)
        
        # Filter by project type
        project_type = request.GET.get('project_type')
        if project_type:
            query = query.filter(project_type=project_type)
        
        # Order by created_at desc
        query = query.order_by('-created_at')
        
        serializer = ProjectListSerializer(query, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch projects',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_project(request, id):
    """Get project by ID"""
    try:
        project = get_object_or_404(Project, id=id)
        
        # Check permissions
        if not request.user.is_staff and project.owner != request.user and project.project_manager != request.user:
            return Response({
                'status': 'error',
                'message': 'You do not have permission to view this project'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = ProjectSerializer(project)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch project',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_project(request):
    """Create a new project"""
    try:
        data = request.data.copy()
        
        # Map title to name for Django model
        if 'title' in data and 'name' not in data:
            data['name'] = data['title']
        
        # Map industry_id to industry
        if 'industry_id' in data:
            industry_id = data.pop('industry_id')
            if industry_id:
                try:
                    industry = Industry.objects.get(id=industry_id)
                    data['industry'] = industry.id
                except Industry.DoesNotExist:
                    return Response({
                        'status': 'error',
                        'message': 'Invalid industry_id'
                    }, status=status.HTTP_400_BAD_REQUEST)
        
        # Map project_manager_id to project_manager
        if 'project_manager_id' in data:
            pm_id = data.pop('project_manager_id')
            if pm_id:
                try:
                    from django.contrib.auth.models import User
                    pm = User.objects.get(id=pm_id)
                    data['project_manager'] = pm.id
                except User.DoesNotExist:
                    return Response({
                        'status': 'error',
                        'message': 'Invalid project_manager_id'
                    }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = ProjectSerializer(data=data, context={'request': request})
        
        if serializer.is_valid():
            project = serializer.save()
            
            # Return with title field
            response_data = serializer.data
            response_data['title'] = project.name
            
            return Response({
                'status': 'success',
                'message': 'Project created successfully',
                'data': response_data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'status': 'error',
            'message': 'Validation error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to create project',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_project(request, id):
    """Update a project"""
    try:
        project = get_object_or_404(Project, id=id)
        
        # Check permissions
        is_owner = project.owner == request.user
        is_manager = project.project_manager == request.user
        is_admin = request.user.is_staff
        
        if not is_owner and not is_manager and not is_admin:
            return Response({
                'status': 'error',
                'message': 'You do not have permission to update this project'
            }, status=status.HTTP_403_FORBIDDEN)
        
        data = request.data.copy()
        
        # Map title to name
        if 'title' in data and 'name' not in data:
            data['name'] = data['title']
        
        # Handle industry_id
        if 'industry_id' in data:
            industry_id = data.pop('industry_id')
            if industry_id:
                try:
                    industry = Industry.objects.get(id=industry_id)
                    data['industry'] = industry.id
                except Industry.DoesNotExist:
                    return Response({
                        'status': 'error',
                        'message': 'Invalid industry_id'
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                data['industry'] = None
        
        # Handle project_manager_id
        if 'project_manager_id' in data:
            pm_id = data.pop('project_manager_id')
            if pm_id:
                try:
                    from django.contrib.auth.models import User
                    pm = User.objects.get(id=pm_id)
                    data['project_manager'] = pm.id
                except User.DoesNotExist:
                    return Response({
                        'status': 'error',
                        'message': 'Invalid project_manager_id'
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                data['project_manager'] = None
        
        serializer = ProjectSerializer(project, data=data, partial=True, context={'request': request})
        
        if serializer.is_valid():
            project = serializer.save()
            response_data = serializer.data
            response_data['title'] = project.name
            
            return Response({
                'status': 'success',
                'message': 'Project updated successfully',
                'data': response_data
            }, status=status.HTTP_200_OK)
        
        return Response({
            'status': 'error',
            'message': 'Validation error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to update project',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_project(request, id):
    """Delete a project"""
    try:
        project = get_object_or_404(Project, id=id)
        
        # Check permissions (only owner or admin)
        is_owner = project.owner == request.user
        is_admin = request.user.is_staff
        
        if not is_owner and not is_admin:
            return Response({
                'status': 'error',
                'message': 'You do not have permission to delete this project'
            }, status=status.HTTP_403_FORBIDDEN)
        
        project.delete()
        
        return Response({
            'status': 'success',
            'message': 'Project deleted successfully'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to delete project',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def apply_to_project(request, id):
    """Apply to a project"""
    try:
        project = get_object_or_404(Project, id=id)
        user = request.user
        
        # Check if user is a freelancer
        is_freelancer = hasattr(user, 'profile') and user.profile.role == 'developer'
        if not is_freelancer:
            return Response({
                'status': 'error',
                'message': 'Only freelancers can apply to projects'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if already applied
        existing_application = ProjectApplication.objects.filter(
            project=project,
            freelancer=user
        ).first()
        
        if existing_application:
            return Response({
                'status': 'error',
                'message': 'You have already applied to this project'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        data = request.data.copy()
        data['project'] = project.id
        data['freelancer'] = user.id
        data['status'] = 'pending'
        
        serializer = ProjectApplicationSerializer(data=data)
        
        if serializer.is_valid():
            application = serializer.save(project=project, freelancer=user)
            
            return Response({
                'status': 'success',
                'message': 'Application submitted successfully',
                'data': ProjectApplicationSerializer(application).data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'status': 'error',
            'message': 'Validation error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to submit application',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_project_applications(request, id):
    """Get applications for a project"""
    try:
        project = get_object_or_404(Project, id=id)
        
        # Check permissions
        is_owner = project.owner == request.user
        is_manager = project.project_manager == request.user
        is_admin = request.user.is_staff
        
        if not is_owner and not is_manager and not is_admin:
            return Response({
                'status': 'error',
                'message': 'You do not have permission to view applications'
            }, status=status.HTTP_403_FORBIDDEN)
        
        applications = ProjectApplication.objects.filter(project=project).order_by('-applied_at')
        serializer = ProjectApplicationSerializer(applications, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch applications',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


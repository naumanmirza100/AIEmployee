from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q

from core.models import Project
from api.serializers.project import ProjectSerializer, ProjectListSerializer

# Only reading is left here. The old marketplace's create, edit, delete, apply and applications
# addresses are gone (CO-269): no screen used them, and any login could write to the table
# Project Manager keeps its projects in. Projects are made and changed through Project Manager.


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_projects(request):
    """List the caller's own projects (staff: all), with filtering.

    This was AllowAny "temporarily for testing", and a request with no login got
    every project of every company. Project Manager keeps its projects in this
    same table.
    """
    try:
        user = request.user
        query = Project.objects.all()
        
        # Filter by status
        status_filter = request.GET.get('status')
        if status_filter:
            query = query.filter(status=status_filter)
        
        # Everyone but platform staff sees only projects they own or manage.
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



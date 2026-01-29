"""
Company Projects and Tasks Management API Views
For company users to edit projects and tasks
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User
import logging

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.models import Project, Task, UserProfile

logger = logging.getLogger(__name__)


@api_view(['PUT', 'PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_company_project(request, project_id):
    """
    Update a project created by the company user
    PUT/PATCH /api/company/projects/{project_id}/update
    """
    try:
        company_user = request.user
        
        # Get project and verify it was created by this company user
        project = get_object_or_404(
            Project, 
            id=project_id,
            created_by_company_user=company_user
        )
        
        data = request.data.copy()
        
        # Update allowed fields
        if 'name' in data:
            project.name = data['name']
        if 'description' in data:
            project.description = data.get('description', '')
        if 'status' in data:
            # Validate status
            valid_statuses = [choice[0] for choice in Project.STATUS_CHOICES]
            if data['status'] in valid_statuses:
                project.status = data['status']
        if 'priority' in data:
            # Validate priority
            valid_priorities = [choice[0] for choice in Project.PRIORITY_CHOICES]
            if data['priority'] in valid_priorities:
                project.priority = data['priority']
        if 'project_type' in data:
            # Validate project_type
            valid_types = [choice[0] for choice in Project.PROJECT_TYPE_CHOICES]
            if data['project_type'] in valid_types:
                project.project_type = data['project_type']
        if 'deadline' in data:
            project.deadline = data['deadline'] if data['deadline'] else None
        if 'start_date' in data:
            project.start_date = data['start_date'] if data['start_date'] else None
        if 'end_date' in data:
            project.end_date = data['end_date'] if data['end_date'] else None
        
        project.save()
        
        return Response({
            'status': 'success',
            'message': 'Project updated successfully',
            'data': {
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'status': project.status,
                'priority': project.priority,
                'project_type': project.project_type,
                'deadline': project.deadline.isoformat() if project.deadline else None,
                'start_date': project.start_date.isoformat() if project.start_date else None,
                'end_date': project.end_date.isoformat() if project.end_date else None,
            }
        }, status=status.HTTP_200_OK)
    
    except Project.DoesNotExist:
        return Response({
            'status': 'error',
            'message': 'Project not found or you do not have permission to update it'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Error updating project: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to update project',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_company_task(request, task_id):
    """
    Update a task in a project created by the company user
    PUT/PATCH /api/company/tasks/{task_id}/update
    """
    try:
        company_user = request.user
        
        # Get task and verify it belongs to a project created by this company user
        task = get_object_or_404(
            Task,
            id=task_id,
            project__created_by_company_user=company_user
        )
        
        data = request.data.copy()
        
        # Update allowed fields
        if 'title' in data:
            task.title = data['title']
        if 'description' in data:
            task.description = data.get('description', '')
        if 'priority' in data:
            # Validate priority
            valid_priorities = [choice[0] for choice in Task.PRIORITY_CHOICES]
            if data['priority'] in valid_priorities:
                task.priority = data['priority']
        if 'status' in data:
            # Validate status
            valid_statuses = [choice[0] for choice in Task.STATUS_CHOICES]
            if data['status'] in valid_statuses:
                task.status = data['status']
        if 'assignee_id' in data:
            # Update assignee - must be a user created by this company user
            assignee_id = data.get('assignee_id')
            if assignee_id:
                try:
                    # Verify the assignee is a user created by this company user
                    assignee_profile = UserProfile.objects.get(
                        user_id=assignee_id,
                        created_by_company_user=company_user
                    )
                    task.assignee = assignee_profile.user
                except UserProfile.DoesNotExist:
                    return Response({
                        'status': 'error',
                        'message': 'Invalid assignee. User must be created by your company.'
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                task.assignee = None
        if 'due_date' in data:
            task.due_date = data['due_date'] if data['due_date'] else None
        
        task.save()
        
        return Response({
            'status': 'success',
            'message': 'Task updated successfully',
            'data': {
                'id': task.id,
                'title': task.title,
                'description': task.description,
                'priority': task.priority,
                'status': task.status,
                'assignee_id': task.assignee.id if task.assignee else None,
                'assignee_name': task.assignee.get_full_name() if task.assignee else None,
                'assignee_email': task.assignee.email if task.assignee else None,
                'due_date': task.due_date.isoformat() if task.due_date else None,
            }
        }, status=status.HTTP_200_OK)
    
    except Task.DoesNotExist:
        return Response({
            'status': 'error',
            'message': 'Task not found or you do not have permission to update it'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Error updating task: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to update task',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_company_users_for_assignment(request):
    """
    Get list of users created by the company user (for task assignment)
    GET /api/company/users/for-assignment
    """
    try:
        company_user = request.user
        
        # Get all users created by this company user
        user_profiles = UserProfile.objects.filter(
            created_by_company_user=company_user
        ).select_related('user')
        
        users_data = []
        for profile in user_profiles:
            users_data.append({
                'id': profile.user.id,
                'email': profile.user.email,
                'username': profile.user.username,
                'full_name': profile.user.get_full_name() or profile.user.username,
                'role': profile.role,
            })
        
        return Response({
            'status': 'success',
            'data': users_data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.exception(f"Error fetching users for assignment: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to fetch users',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


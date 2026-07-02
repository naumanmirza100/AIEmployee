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
        # `end_date` is the legacy alias for `deadline`. Accept either, mirror
        # writes to both DB columns, drop end_date from the response.
        if 'deadline' in data or 'end_date' in data:
            new_deadline = data.get('deadline')
            if new_deadline is None:
                new_deadline = data.get('end_date')
            project.deadline = new_deadline if new_deadline else None
            project.end_date = new_deadline if new_deadline else None
        if 'start_date' in data:
            project.start_date = data['start_date'] if data['start_date'] else None

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
                'deadline': (project.deadline or project.end_date).isoformat() if (project.deadline or project.end_date) else None,
                'start_date': project.start_date.isoformat() if project.start_date else None,
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
        company = getattr(company_user, 'company', None)

        # Get task and verify it belongs to a project at the SAME company.
        # Previously this filtered by `project__created_by_company_user=company_user`,
        # which 404'd whenever a colleague at the same company had created the
        # project the task lives in. Scoping by company keeps the security
        # boundary (other tenants are still locked out) but lets every
        # CompanyUser in a company edit their colleagues' tasks.
        task_qs_kwargs = {'id': task_id}
        if company is not None:
            task_qs_kwargs['project__company'] = company
        else:
            task_qs_kwargs['project__created_by_company_user'] = company_user
        task = get_object_or_404(Task, **task_qs_kwargs)

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
            # Update assignee — same widening: any UserProfile inside the same
            # company is OK, not just users this specific CompanyUser created.
            # Also require the user to be active (deactivated users shouldn't
            # be assignable; we already filter them out of the dropdown).
            assignee_id = data.get('assignee_id')
            if assignee_id:
                try:
                    profile_qs = UserProfile.objects.filter(
                        user_id=assignee_id, user__is_active=True,
                    )
                    if company is not None:
                        profile_qs = profile_qs.filter(
                            created_by_company_user__company=company,
                        )
                    else:
                        profile_qs = profile_qs.filter(
                            created_by_company_user=company_user,
                        )
                    assignee_profile = profile_qs.get()
                    task.assignee = assignee_profile.user
                except UserProfile.DoesNotExist:
                    return Response({
                        'status': 'error',
                        'message': 'Invalid assignee. User must belong to your company and be active.'
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                task.assignee = None
        if 'due_date' in data:
            # Parse explicitly so an unparseable string (e.g. "07/02/2026 05:00 AM")
            # returns a clear 400 instead of bubbling into a generic 500.
            raw_due = data['due_date']
            if not raw_due:
                task.due_date = None
            else:
                from django.utils.dateparse import parse_datetime, parse_date
                parsed = parse_datetime(raw_due) or parse_date(raw_due)
                if parsed is None:
                    return Response({
                        'status': 'error',
                        'message': (
                            'Invalid due date format. Send an ISO 8601 datetime '
                            '(e.g. "2026-07-02T05:00:00Z") or a date (YYYY-MM-DD).'
                        ),
                    }, status=status.HTTP_400_BAD_REQUEST)
                task.due_date = parsed

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


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_company_task(request, task_id):
    """Delete a task that belongs to one of this company's projects.

    DELETE /api/company/tasks/{task_id}/delete

    Same company-scope policy as `update_company_task` — any CompanyUser in
    the same company can delete any task in the company's projects. Subtasks
    cascade via the FK on_delete=CASCADE.
    """
    try:
        company_user = request.user
        company = getattr(company_user, 'company', None)

        task_qs_kwargs = {'id': task_id}
        if company is not None:
            task_qs_kwargs['project__company'] = company
        else:
            task_qs_kwargs['project__created_by_company_user'] = company_user
        task = get_object_or_404(Task, **task_qs_kwargs)

        task_title = task.title
        task.delete()

        return Response({
            'status': 'success',
            'message': 'Task deleted successfully',
            'data': {'id': task_id, 'title': task_title},
        }, status=status.HTTP_200_OK)

    except Task.DoesNotExist:
        return Response({
            'status': 'error',
            'message': 'Task not found or you do not have permission to delete it.',
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Error deleting task: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to delete task',
            'error': str(e),
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
        company = getattr(company_user, 'company', None)

        # Get all ACTIVE users in the same company (not just users this
        # specific CompanyUser created). Previously this filtered by
        # `created_by_company_user=company_user`, so the Assign-To dropdown
        # was missing colleagues' users — and an attempt to assign them
        # then failed in `update_company_task` with "Invalid assignee".
        # Same security boundary: only users from this company, never
        # another tenant's.
        profile_qs = UserProfile.objects.filter(user__is_active=True)
        if company is not None:
            profile_qs = profile_qs.filter(created_by_company_user__company=company)
        else:
            profile_qs = profile_qs.filter(created_by_company_user=company_user)
        user_profiles = profile_qs.select_related('user')

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


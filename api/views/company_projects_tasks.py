"""
Company Projects and Tasks Management API Views
For company users to edit projects and tasks
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
import logging

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.tenancy import members_of
from project_manager_agent import services as pm_services
from api.pagination import paginate

logger = logging.getLogger(__name__)


@api_view(['PUT', 'PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_company_project(request, project_id):
    """
    Update a project of the caller's company.
    PUT/PATCH /api/company/projects/{project_id}/update
    Rules (validation, scope, audit): project_manager_agent.services.
    """
    try:
        project, _ = pm_services.update_project(
            pm_services.DashboardActor.from_request(request), project_id, request.data)
    except pm_services.ServiceError as exc:
        return exc.response()
    except Exception as e:
        logger.exception(f"Error updating project: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to update project',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
            'industry_id': project.industry_id,
            'budget_min': float(project.budget_min) if project.budget_min is not None else None,
            'budget_max': float(project.budget_max) if project.budget_max is not None else None,
            'deadline': project.effective_deadline.isoformat() if project.effective_deadline else None,
            'start_date': project.start_date.isoformat() if project.start_date else None,
        }
    }, status=status.HTTP_200_OK)


@api_view(['PUT', 'PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_company_task(request, task_id):
    """
    Update a task in one of the caller's company's projects.
    PUT/PATCH /api/company/tasks/{task_id}/update
    Rules (validation, dependencies, due-date bounds, audit): project_manager_agent.services.
    """
    try:
        task, _ = pm_services.update_task(
            pm_services.DashboardActor.from_request(request), task_id, request.data)
    except pm_services.ServiceError as exc:
        return exc.response()
    except Exception as e:
        logger.exception(f"Error updating task: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to update task',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({
        'status': 'success',
        'message': 'Task updated successfully',
        'data': {
            'id': task.id,
            'title': task.title,
            'description': task.description,
            'priority': task.priority,
            'status': task.status,
            'assignee_id': task.assignee_id,
            'assignee_name': task.assignee.get_full_name() if task.assignee else None,
            'assignee_email': task.assignee.email if task.assignee else None,
            'due_date': task.due_date.isoformat() if task.due_date else None,
        }
    }, status=status.HTTP_200_OK)


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_company_task(request, task_id):
    """Delete a task that belongs to one of this company's projects.

    DELETE /api/company/tasks/{task_id}/delete

    Delegates to api.views.pm_deletes, shared with
    /api/project-manager/tasks/<id>/delete. The previous body caught
    Task.DoesNotExist around get_object_or_404 (which raises Http404), so a
    missing or foreign task fell through to `except Exception` and returned 500
    instead of 404. It also wrote no audit entry.
    """
    from api.views.pm_deletes import delete_task_as_company_user
    return delete_task_as_company_user(request, task_id)

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_company_users_for_assignment(request):
    """
    Users a task in this company can be assigned to
    GET /api/company/users/for-assignment
    """
    try:
        company_user = request.user
        company = getattr(company_user, 'company', None)

        # Exactly the people assignment accepts (core.tenancy.members_of):
        # active users of this company through either profile link. This used
        # to match only the "created by a dashboard login" link, so employees
        # whose profile names the company directly were missing from the list.
        members, pagination = paginate(
            request,
            members_of(company, company_user=company_user).select_related('profile').order_by('id'),
            default_limit=500, max_limit=1000,
        )

        users_data = []
        for member in members:
            users_data.append({
                'id': member.id,
                'email': member.email,
                'username': member.username,
                'full_name': member.get_full_name() or member.username,
                'role': getattr(getattr(member, 'profile', None), 'role', None),
            })
        
        return Response({
            'status': 'success',
            'data': users_data,
            'pagination': pagination,
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.exception(f"Error fetching users for assignment: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to fetch users',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


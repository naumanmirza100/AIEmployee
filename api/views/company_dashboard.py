"""
Company Dashboard API Views
"""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from django.db.models import Q, Count
import logging

from core.models import Project, Task, CompanyUser, Subtask
from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly

logger = logging.getLogger(__name__)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def project_manager_dashboard(request):
    """
    Get project manager dashboard data - Only accessible to company users with project_manager role
    """
    try:
        company_user = request.user
        
        # Check if user can access project manager features (project_manager or company_user role)
        if not hasattr(company_user, 'can_access_project_manager_features'):
            logger.error(f"CompanyUser {company_user.id} does not have can_access_project_manager_features method")
            return Response(
                {
                    'status': 'error',
                    'message': 'Invalid user type. Please contact support.'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        if not company_user.can_access_project_manager_features():
            return Response(
                {
                    'status': 'error',
                    'message': 'Access denied. Project manager or company user role required.'
                },
                status=status.HTTP_403_FORBIDDEN
            )
        
        company = company_user.company
        if not company:
            logger.error(f"CompanyUser {company_user.id} does not have an associated company")
            return Response(
                {
                    'status': 'error',
                    'message': 'User is not associated with a company. Please contact support.'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Get projects created by this company user
        projects = Project.objects.filter(created_by_company_user=company_user)
        tasks = Task.objects.filter(project__created_by_company_user=company_user)
        
        # Calculate statistics
        stats = {
            'total_projects': projects.count(),
            'active_projects': projects.filter(status='active').count(),
            'completed_projects': projects.filter(status='completed').count(),
            'total_tasks': tasks.count(),
            'completed_tasks': tasks.filter(status='done').count(),
            'in_progress_tasks': tasks.filter(status='in_progress').count(),
            'todo_tasks': tasks.filter(status='todo').count(),
        }
        
        # Get recent projects with tasks and subtasks
        recent_projects = projects.order_by('-created_at')[:10]
        projects_data = []
        for p in recent_projects:
            # Get all tasks for this project
            project_tasks = Task.objects.filter(project=p)
            tasks_data = []
            for task in project_tasks:
                # Get all subtasks for this task
                subtasks = task.subtasks.all()
                tasks_data.append({
                    'id': task.id,
                    'title': task.title,
                    'description': task.description,
                    'status': task.status,
                    'priority': task.priority,
                    'due_date': task.due_date.isoformat() if task.due_date else None,
                    'subtasks': [
                        {
                            'id': st.id,
                            'title': st.title,
                            'description': st.description,
                            'status': st.status,
                            'order': st.order,
                            'created_at': st.created_at.isoformat() if st.created_at else None,
                        }
                        for st in subtasks
                    ],
                })
            
            projects_data.append({
                'id': p.id,
                'name': p.name,
                'description': p.description,
                'status': p.status,
                'priority': p.priority,
                'tasks_count': project_tasks.count(),
                'tasks': tasks_data,
                'created_at': p.created_at.isoformat() if p.created_at else None,
            })
        
        return Response({
            'status': 'success',
            'data': {
                'stats': stats,
                'projects': projects_data,
                'user': {
                    'id': company_user.id,
                    'email': company_user.email,
                    'fullName': company_user.full_name,
                    'role': company_user.role,
                    'companyId': company.id,
                    'companyName': company.name,
                }
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.exception(f"Error in project_manager_dashboard: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return Response({
            'status': 'error',
            'message': 'Failed to fetch dashboard data',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_company_user_projects(request):
    """
    Get all projects created by the logged-in company user with tasks and subtasks
    """
    try:
        company_user = request.user
        
        # Get projects created by this company user
        projects = Project.objects.filter(created_by_company_user=company_user).order_by('-created_at')
        
        projects_data = []
        for p in projects:
            # Get all tasks for this project
            project_tasks = Task.objects.filter(project=p)
            tasks_data = []
            for task in project_tasks:
                # Get all subtasks for this task
                subtasks = task.subtasks.all()
                tasks_data.append({
                    'id': task.id,
                    'title': task.title,
                    'description': task.description,
                    'status': task.status,
                    'priority': task.priority,
                    'due_date': task.due_date.isoformat() if task.due_date else None,
                    'created_at': task.created_at.isoformat() if task.created_at else None,
                    'assignee_id': task.assignee.id if task.assignee else None,
                    'assignee_name': task.assignee.get_full_name() if task.assignee and (task.assignee.first_name or task.assignee.last_name) else (task.assignee.username if task.assignee else None),
                    'assignee_email': task.assignee.email if task.assignee else None,
                    'subtasks': [
                        {
                            'id': st.id,
                            'title': st.title,
                            'description': st.description,
                            'status': st.status,
                            'order': st.order,
                            'created_at': st.created_at.isoformat() if st.created_at else None,
                        }
                        for st in subtasks
                    ],
                })
            
            projects_data.append({
                'id': p.id,
                'name': p.name,
                'description': p.description,
                'status': p.status,
                'priority': p.priority,
                'project_type': p.project_type,
                'tasks_count': project_tasks.count(),
                'tasks': tasks_data,
                'created_at': p.created_at.isoformat() if p.created_at else None,
                'updated_at': p.updated_at.isoformat() if p.updated_at else None,
            })
        
        return Response({
            'status': 'success',
            'data': projects_data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.exception(f"Error in get_company_user_projects: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return Response({
            'status': 'error',
            'message': 'Failed to fetch projects',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


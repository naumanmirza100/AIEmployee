"""
Company Dashboard API Views
"""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from django.db.models import Q, Count, Prefetch, prefetch_related_objects
import logging

from core.models import Project, Task, CompanyUser, Subtask
from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from api.pagination import paginate


def _with_tasks_and_subtasks(projects_qs):
    """Prefetch each project's tasks (with assignee) and their subtasks.

    Both dashboard views used to loop projects -> tasks -> subtasks issuing a
    query at every level, plus one per task for `task.assignee` and a repeat
    `.count()` per project. Measured against the Hostinger database with 8
    projects x 6 tasks x 3 subtasks, /api/company/projects took 106 queries
    and 30.6 s. This collapses the tree to a constant three queries.

    Ordering is unchanged: the prefetch querysets inherit Task and Subtask
    Meta.ordering, exactly as the per-row queries did.
    """
    return projects_qs.prefetch_related(_task_tree_prefetch())


def _task_tree_prefetch():
    # Built fresh per call rather than shared at module level.
    return Prefetch('tasks', queryset=Task.objects.select_related('assignee')
                                         .prefetch_related('subtasks'))

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
        
        # Calculate statistics.
        # Note: dashboard tiles read these counts directly (BUG-03 fix) —
        # `projects_data` below is capped at 10 for the "recent projects"
        # panel, and using its length for the tiles caused the counter
        # to freeze at 10.
        # Two aggregate queries instead of eight separate COUNTs.
        p_agg = projects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status__in=['active', 'in_progress'])),
            planning=Count('id', filter=Q(status='planning')),
            completed=Count('id', filter=Q(status='completed')),
        )
        t_agg = tasks.aggregate(
            total=Count('id'),
            done=Count('id', filter=Q(status='done')),
            in_progress=Count('id', filter=Q(status='in_progress')),
            todo=Count('id', filter=Q(status='todo')),
        )
        stats = {
            'total_projects': p_agg['total'],
            'active_projects': p_agg['active'],
            'planning_projects': p_agg['planning'],
            'completed_projects': p_agg['completed'],
            'total_tasks': t_agg['total'],
            'completed_tasks': t_agg['done'],
            'in_progress_tasks': t_agg['in_progress'],
            'todo_tasks': t_agg['todo'],
        }
        
        # Get recent projects with tasks and subtasks
        recent_projects = _with_tasks_and_subtasks(projects.order_by('-created_at')[:10])
        projects_data = []
        for p in recent_projects:
            project_tasks = list(p.tasks.all())  # prefetched
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
                'tasks_count': len(project_tasks),
                'tasks': tasks_data,
                'created_at': p.created_at.isoformat() if p.created_at else None,
                # BUG-06: expose project timeline so the task-creation form can
                # constrain the due-date picker to the project's window.
                'start_date': p.start_date.isoformat() if p.start_date else None,
                'deadline': (p.effective_deadline.isoformat()
                             if p.effective_deadline else None),
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
def get_company_user_projects_list(request):
    """
    Lightweight endpoint: returns only id, name, status for combo boxes / dropdowns.
    No nested tasks or subtasks — single query, fast response.
    """
    try:
        company_user = request.user
        projects, pagination = paginate(
            request,
            Project.objects.filter(created_by_company_user=company_user)
                   .order_by('-created_at').values('id', 'name', 'status'),
            default_limit=500, max_limit=1000,
        )

        return Response({
            'status': 'success',
            'data': projects,
            'pagination': pagination,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception(f"Error in get_company_user_projects_list: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to fetch projects list',
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
        # Page first, then prefetch just that page's tasks/subtasks. Each item
        # carries its full task tree, so this is the heaviest list endpoint.
        page, pagination = paginate(
            request,
            Project.objects.filter(created_by_company_user=company_user).order_by('-created_at'),
            default_limit=200, max_limit=500,
        )
        prefetch_related_objects(page, _task_tree_prefetch())  # onto the loaded page — no re-query
        
        projects_data = []
        for p in page:
            project_tasks = list(p.tasks.all())  # prefetched, assignee joined
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
                'tasks_count': len(project_tasks),
                'tasks': tasks_data,
                'created_at': p.created_at.isoformat() if p.created_at else None,
                'updated_at': p.updated_at.isoformat() if p.updated_at else None,
            })
        
        return Response({
            'status': 'success',
            'data': projects_data,
            'pagination': pagination,
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


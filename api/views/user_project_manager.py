"""
User Project Manager API Views
For users with project_manager role to manage projects and tasks
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import models
from datetime import datetime
import logging

from core.models import Project, Task, UserProfile, Company, TaskRecurrence

logger = logging.getLogger(__name__)


def _serialize_task_brief(task):
    return {
        'id': task.id,
        'title': task.title,
        'status': task.status,
    }


def _get_blockers(task, dep_ids=None):
    """
    Return the list of dependency tasks that block this one
    (i.e. depends_on entries whose status != 'done').
    `dep_ids` lets the caller pass a candidate set instead of using task.depends_on.all().
    """
    if dep_ids is None:
        deps = task.depends_on.all()
    else:
        deps = Task.objects.filter(id__in=list(dep_ids))
    return [d for d in deps if d.status != 'done']


def _dependency_creates_cycle(task_id, candidate_dep_ids):
    """
    Return True if marking `task_id` as depending on every id in
    `candidate_dep_ids` would introduce a cycle. We walk
    depends_on transitively from each candidate and see if we ever reach task_id.
    Empty input is safe.
    """
    if not candidate_dep_ids:
        return False
    target = int(task_id)
    visited = set()
    stack = [int(c) for c in candidate_dep_ids if int(c) != target]
    # Direct self-loop check
    if any(int(c) == target for c in candidate_dep_ids):
        return True
    # Pre-fetch the dependency graph as a dict to avoid N queries per node
    edges = {}
    for tid, dep_id in Task.depends_on.through.objects.values_list('from_task_id', 'to_task_id'):
        edges.setdefault(tid, set()).add(dep_id)
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        if node == target:
            return True
        for next_node in edges.get(node, ()):
            if next_node not in visited:
                stack.append(next_node)
    return False


def _validate_dependency_change(task, raw_dep_ids):
    """
    Validate a proposed full-replace dependency list for `task`.
    Returns (cleaned_dep_ids: list[int], error: Response|None).
    """
    if not isinstance(raw_dep_ids, list):
        return None, Response({
            'status': 'error',
            'message': 'depends_on_ids must be a list of task IDs.'
        }, status=status.HTTP_400_BAD_REQUEST)

    cleaned = []
    seen = set()
    for raw in raw_dep_ids:
        try:
            tid = int(raw)
        except (TypeError, ValueError):
            return None, Response({
                'status': 'error',
                'message': f'Invalid task id in depends_on_ids: {raw!r}'
            }, status=status.HTTP_400_BAD_REQUEST)
        if tid == task.id:
            return None, Response({
                'status': 'error',
                'message': 'A task cannot depend on itself.'
            }, status=status.HTTP_400_BAD_REQUEST)
        if tid in seen:
            continue
        seen.add(tid)
        cleaned.append(tid)

    if cleaned:
        found = list(Task.objects.filter(id__in=cleaned).values_list('id', 'project_id'))
        found_ids = {tid for tid, _ in found}
        missing = [t for t in cleaned if t not in found_ids]
        if missing:
            return None, Response({
                'status': 'error',
                'message': f'Dependency tasks not found: {missing}'
            }, status=status.HTTP_400_BAD_REQUEST)
        # Dependencies must live in the same project
        out_of_project = [tid for tid, pid in found if pid != task.project_id]
        if out_of_project:
            return None, Response({
                'status': 'error',
                'message': f'Dependencies must be in the same project. Offending task IDs: {out_of_project}'
            }, status=status.HTTP_400_BAD_REQUEST)
        # Cycle check
        if _dependency_creates_cycle(task.id, cleaned):
            return None, Response({
                'status': 'error',
                'message': 'These dependencies would create a cycle.'
            }, status=status.HTTP_400_BAD_REQUEST)

    return cleaned, None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_project_manager_projects_tasks(request):
    """
    Get all tasks from projects where the project manager has at least one task assigned
    GET /api/user/project-manager/projects-tasks
    """
    try:
        user = request.user
        
        # Check if user is a project manager
        if not hasattr(user, 'profile') or user.profile.role != 'project_manager':
            return Response({
                'status': 'error',
                'message': 'Access denied. Project manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get all projects where this user has at least one task assigned OR is the project manager/owner
        projects_with_tasks = Project.objects.filter(
            models.Q(tasks__assignee=user) | models.Q(project_manager=user) | models.Q(owner=user)
        ).distinct()
        
        projects_data = []
        for project in projects_with_tasks:
            # Get ALL tasks for this project (not just user's tasks)
            all_project_tasks = Task.objects.filter(project=project).select_related('assignee', 'project', 'recurrence').prefetch_related('depends_on')

            tasks_data = []
            for task in all_project_tasks:
                deps = list(task.depends_on.all())
                blocked_by = [_serialize_task_brief(d) for d in deps if d.status != 'done']
                rec = getattr(task, 'recurrence', None)
                tasks_data.append({
                    'id': task.id,
                    'title': task.title,
                    'description': task.description,
                    'status': task.status,
                    'priority': task.priority,
                    'due_date': task.due_date.isoformat() if task.due_date else None,
                    'progress_percentage': task.progress_percentage,
                    'assignee_id': task.assignee.id if task.assignee else None,
                    'assignee_name': task.assignee.get_full_name() if task.assignee and (task.assignee.first_name or task.assignee.last_name) else (task.assignee.username if task.assignee else None),
                    'assignee_email': task.assignee.email if task.assignee else None,
                    'created_at': task.created_at.isoformat() if task.created_at else None,
                    'depends_on_ids': [d.id for d in deps],
                    'depends_on': [_serialize_task_brief(d) for d in deps],
                    'blocked_by': blocked_by,
                    'is_blocked': bool(blocked_by),
                    'recurrence': _serialize_recurrence(rec) if rec else None,
                })
            
            projects_data.append({
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'status': project.status,
                'priority': project.priority,
                'project_type': project.project_type,
                'start_date': project.start_date.isoformat() if project.start_date else None,
                'deadline': (project.deadline or project.end_date).isoformat() if (project.deadline or project.end_date) else None,
                'tasks': tasks_data,
                'tasks_count': len(tasks_data),
            })
        
        return Response({
            'status': 'success',
            'data': projects_data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.exception(f"Error in get_project_manager_projects_tasks: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to fetch projects and tasks',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_project_manager_project(request):
    """
    Create a new project for a project manager
    POST /api/user/project-manager/projects
    """
    try:
        user = request.user
        
        # Check if user is a project manager
        if not hasattr(user, 'profile') or user.profile.role != 'project_manager':
            return Response({
                'status': 'error',
                'message': 'Access denied. Project manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get user's company from profile
        user_profile = user.profile
        company = user_profile.company
        
        if not company:
            return Response({
                'status': 'error',
                'message': 'User is not associated with a company'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get project data
        name = request.data.get('name', '').strip()
        if not name:
            return Response({
                'status': 'error',
                'message': 'Project name is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        description = request.data.get('description', '').strip()
        status_val = request.data.get('status', 'planning')
        priority_val = request.data.get('priority', 'medium')
        project_type = request.data.get('project_type', 'web_app')
        # `end_date` is the legacy alias for `deadline`; accept either on the
        # wire and mirror to both DB columns so existing readers keep working.
        deadline = request.data.get('deadline') or request.data.get('end_date')
        start_date = request.data.get('start_date')
        
        # Validate status and priority
        valid_statuses = ['planning', 'active', 'on_hold', 'completed', 'cancelled', 'draft', 'posted', 'in_progress', 'review']
        valid_priorities = ['low', 'medium', 'high', 'urgent']
        valid_project_types = ['website', 'mobile_app', 'web_app', 'ai_bot', 'integration', 'marketing', 'database', 'consulting', 'ai_system']
        
        if status_val not in valid_statuses:
            return Response({
                'status': 'error',
                'message': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if priority_val not in valid_priorities:
            return Response({
                'status': 'error',
                'message': f'Invalid priority. Must be one of: {", ".join(valid_priorities)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if project_type not in valid_project_types:
            return Response({
                'status': 'error',
                'message': f'Invalid project type. Must be one of: {", ".join(valid_project_types)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse dates
        deadline_date = None
        if deadline:
            try:
                deadline_date = datetime.strptime(deadline, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    'status': 'error',
                    'message': 'Invalid deadline format. Use YYYY-MM-DD'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        start_date_obj = None
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    'status': 'error',
                    'message': 'Invalid start_date format. Use YYYY-MM-DD'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Create project. Mirror deadline_date into the legacy end_date column.
        project = Project.objects.create(
            name=name,
            description=description,
            owner=user,
            project_manager=user,
            company=company,
            status=status_val,
            priority=priority_val,
            project_type=project_type,
            deadline=deadline_date,
            start_date=start_date_obj,
            end_date=deadline_date,
        )
        
        return Response({
            'status': 'success',
            'message': 'Project created successfully',
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
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        logger.exception(f"Error in create_project_manager_project: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to create project',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_project_manager_task(request):
    """
    Create a new task in a project (for project managers)
    POST /api/user/project-manager/tasks
    """
    try:
        user = request.user
        
        # Check if user is a project manager
        if not hasattr(user, 'profile') or user.profile.role != 'project_manager':
            return Response({
                'status': 'error',
                'message': 'Access denied. Project manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get task data
        project_id = request.data.get('project_id')
        if not project_id:
            return Response({
                'status': 'error',
                'message': 'project_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # L1 — tenant gate. The existing membership check below was role-based
        # only (creator/owner/has-task); a user accidentally attached to a
        # foreign-company project would have full access. Filter by company at
        # the lookup so that path is closed even before the membership check runs.
        user_company = getattr(getattr(user, 'profile', None), 'company', None)
        project_qs = Project.objects.filter(id=project_id)
        if user_company is not None:
            project_qs = project_qs.filter(company=user_company)
        project = project_qs.first()
        if not project:
            return Response({
                'status': 'error',
                'message': 'Project not found',
            }, status=status.HTTP_404_NOT_FOUND)

        # Check if user has access to this project (has at least one task assigned)
        user_has_access = Task.objects.filter(project=project, assignee=user).exists()
        if not user_has_access and project.project_manager != user and project.owner != user:
            return Response({
                'status': 'error',
                'message': 'Access denied. You must have at least one task in this project.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        title = request.data.get('title', '').strip()
        if not title:
            return Response({
                'status': 'error',
                'message': 'Task title is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        description = request.data.get('description', '').strip()
        status_val = request.data.get('status', 'todo')
        priority_val = request.data.get('priority', 'medium')
        assignee_id = request.data.get('assignee_id')
        due_date_str = request.data.get('due_date')
        estimated_hours = request.data.get('estimated_hours')
        
        # Validate status and priority
        valid_statuses = ['todo', 'in_progress', 'review', 'done', 'blocked']
        valid_priorities = ['low', 'medium', 'high']
        
        if status_val not in valid_statuses:
            return Response({
                'status': 'error',
                'message': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if priority_val not in valid_priorities:
            return Response({
                'status': 'error',
                'message': f'Invalid priority. Must be one of: {", ".join(valid_priorities)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Handle assignee - must be from the same company
        assignee = None
        if assignee_id:
            try:
                assignee_user = User.objects.get(id=assignee_id)
                # Get user's company
                user_company = None
                if hasattr(user, 'profile') and user.profile.company:
                    user_company = user.profile.company
                
                # Verify assignee is from the same company
                assignee_company = None
                if hasattr(assignee_user, 'profile') and assignee_user.profile.company:
                    assignee_company = assignee_user.profile.company
                
                # Check if both users are from the same company (or both have no company)
                if user_company and assignee_company and user_company == assignee_company:
                    assignee = assignee_user
                elif not user_company and not assignee_company:
                    # Both have no company - allow assignment
                    assignee = assignee_user
                else:
                    return Response({
                        'status': 'error',
                        'message': 'Assignee must be from the same company'
                    }, status=status.HTTP_400_BAD_REQUEST)
            except User.DoesNotExist:
                return Response({
                    'status': 'error',
                    'message': 'Invalid assignee_id'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse due date
        due_date = None
        if due_date_str:
            try:
                # Try ISO format first
                if 'T' in due_date_str:
                    due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
                else:
                    due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
                    due_date = timezone.make_aware(due_date)
            except ValueError:
                return Response({
                    'status': 'error',
                    'message': 'Invalid due_date format. Use YYYY-MM-DD or ISO format'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create task
        task = Task.objects.create(
            title=title,
            description=description,
            project=project,
            assignee=assignee,
            status=status_val,
            priority=priority_val,
            due_date=due_date,
            estimated_hours=estimated_hours,
        )

        # Optional initial dependencies (T-F1)
        depends_on_ids = request.data.get('depends_on_ids')
        if depends_on_ids is not None:
            cleaned, dep_error = _validate_dependency_change(task, depends_on_ids)
            if dep_error is not None:
                # Roll back the task we just created so the validation failure isn't
                # silently swallowed
                task.delete()
                return dep_error
            if cleaned:
                task.depends_on.set(cleaned)

        return Response({
            'status': 'success',
            'message': 'Task created successfully',
            'data': {
                'id': task.id,
                'title': task.title,
                'description': task.description,
                'status': task.status,
                'priority': task.priority,
                'assignee_id': task.assignee.id if task.assignee else None,
                'assignee_name': task.assignee.get_full_name() if task.assignee and (task.assignee.first_name or task.assignee.last_name) else (task.assignee.username if task.assignee else None),
                'due_date': task.due_date.isoformat() if task.due_date else None,
                'depends_on_ids': list(task.depends_on.values_list('id', flat=True)),
            }
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        logger.exception(f"Error in create_project_manager_task: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to create task',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_company_users_for_pm(request):
    """
    Get list of users from the same company (for project manager to assign tasks)
    GET /api/user/project-manager/company-users
    """
    try:
        user = request.user
        
        # Check if user is a project manager
        if not hasattr(user, 'profile') or user.profile.role != 'project_manager':
            return Response({
                'status': 'error',
                'message': 'Access denied. Project manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get user's company
        user_profile = user.profile
        company = user_profile.company
        
        if not company:
            return Response({
                'status': 'error',
                'message': 'User is not associated with a company'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get all users from the same company
        company_user_profiles = UserProfile.objects.filter(company=company).select_related('user')
        
        users_data = []
        for profile in company_user_profiles:
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
        logger.exception(f"Error in get_company_users_for_pm: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to fetch company users',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_project_manager_projects(request):
    """
    Get all projects where the project manager has at least one task assigned
    GET /api/user/project-manager/projects
    """
    try:
        user = request.user
        
        # Check if user is a project manager
        if not hasattr(user, 'profile') or user.profile.role != 'project_manager':
            return Response({
                'status': 'error',
                'message': 'Access denied. Project manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get all projects where this user has at least one task assigned OR is the project manager/owner
        projects = Project.objects.filter(
            models.Q(tasks__assignee=user) | models.Q(project_manager=user) | models.Q(owner=user)
        ).distinct().order_by('-created_at')
        
        projects_data = []
        for project in projects:
            projects_data.append({
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'status': project.status,
                'priority': project.priority,
                'project_type': project.project_type,
                'start_date': project.start_date.isoformat() if project.start_date else None,
                'deadline': (project.deadline or project.end_date).isoformat() if (project.deadline or project.end_date) else None,
                'tasks_count': project.tasks.count(),
            })
        
        return Response({
            'status': 'success',
            'data': projects_data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.exception(f"Error in get_project_manager_projects: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to fetch projects',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_project_manager_project(request, project_id):
    """
    Update a project (for project managers)
    PUT/PATCH /api/user/project-manager/projects/{project_id}/update
    """
    try:
        user = request.user
        
        # Check if user is a project manager
        if not hasattr(user, 'profile') or user.profile.role != 'project_manager':
            return Response({
                'status': 'error',
                'message': 'Access denied. Project manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # L1 — tenant gate. Same belt-and-suspenders as create_project_manager_task:
        # filter the lookup by company so a stray cross-tenant project_id can't
        # reach the role-based membership check below.
        user_company = getattr(getattr(user, 'profile', None), 'company', None)
        project_qs = Project.objects.filter(id=project_id)
        if user_company is not None:
            project_qs = project_qs.filter(company=user_company)
        project = project_qs.first()
        if not project:
            return Response({
                'status': 'error',
                'message': 'Project not found',
            }, status=status.HTTP_404_NOT_FOUND)

        # Check if user has access
        user_has_access = (
            project.project_manager == user or
            project.owner == user or
            Task.objects.filter(project=project, assignee=user).exists()
        )

        if not user_has_access:
            return Response({
                'status': 'error',
                'message': 'Access denied. You do not have permission to update this project.'
            }, status=status.HTTP_403_FORBIDDEN)
        
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
        # `end_date` (legacy alias for deadline) is accepted on the wire but
        # treated as the same field. Whichever key the caller sends is mirrored
        # to both DB columns so existing readers keep working.
        if 'deadline' in data or 'end_date' in data:
            deadline_str = data.get('deadline')
            if deadline_str is None:
                deadline_str = data.get('end_date')
            if deadline_str:
                try:
                    parsed = datetime.strptime(deadline_str, '%Y-%m-%d').date()
                    project.deadline = parsed
                    project.end_date = parsed
                except ValueError:
                    return Response({
                        'status': 'error',
                        'message': 'Invalid deadline format. Use YYYY-MM-DD'
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                project.deadline = None
                project.end_date = None
        if 'start_date' in data:
            start_date_str = data.get('start_date')
            if start_date_str:
                try:
                    project.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                except ValueError:
                    return Response({
                        'status': 'error',
                        'message': 'Invalid start_date format. Use YYYY-MM-DD'
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                project.start_date = None

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
            'message': 'Project not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Error updating project: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to update project',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_project_manager_task(request, task_id):
    """
    Update a task (for project managers)
    PUT/PATCH /api/user/project-manager/tasks/{task_id}/update
    """
    try:
        user = request.user
        
        # Check if user is a project manager
        if not hasattr(user, 'profile') or user.profile.role != 'project_manager':
            return Response({
                'status': 'error',
                'message': 'Access denied. Project manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get task and verify it belongs to a project the user has access to
        task = get_object_or_404(Task, id=task_id)
        project = task.project
        
        # Get user's company
        user_company = None
        if hasattr(user, 'profile') and user.profile.company:
            user_company = user.profile.company
        
        # Check if user has access to this project
        # Project managers can edit tasks in projects they manage or own, OR if they're in the same company
        user_has_access = (
            project.project_manager == user or 
            project.owner == user or 
            Task.objects.filter(project=project, assignee=user).exists() or
            (user_company and project.company == user_company)
        )
        
        if not user_has_access:
            return Response({
                'status': 'error',
                'message': 'Access denied. You do not have permission to update this task.'
            }, status=status.HTTP_403_FORBIDDEN)
        
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
                desired = data['status']
                # T-F1 — block transitions to in_progress/done when prerequisites are
                # not yet done. Caller can pass force=true to override.
                force = str(data.get('force', '')).lower() in ('1', 'true', 'yes')
                if desired in ('in_progress', 'done') and not force:
                    blockers = _get_blockers(task)
                    if blockers:
                        return Response({
                            'status': 'error',
                            'message': f'Cannot move task to {desired}: blocked by incomplete dependencies.',
                            'blocked_by': [_serialize_task_brief(b) for b in blockers],
                            'hint': 'Pass force=true to override, or complete the blocking tasks first.',
                        }, status=status.HTTP_409_CONFLICT)
                task.status = desired
        if 'assignee_id' in data:
            # Update assignee - must be from the same company
            assignee_id = data.get('assignee_id')
            # Handle string 'none', empty string, or None
            if assignee_id in [None, '', 'none', 'null']:
                task.assignee = None
            else:
                try:
                    # Convert to int if it's a string
                    if isinstance(assignee_id, str):
                        assignee_id = int(assignee_id)
                    
                    assignee_user = User.objects.get(id=assignee_id)
                    
                    # If the assignee is not changing, allow it (task already exists with this assignee)
                    if task.assignee and task.assignee.id == assignee_id:
                        # Keep the current assignee - no validation needed
                        task.assignee = assignee_user
                    else:
                        # New assignee - verify they are from the same company
                        assignee_company = None
                        if hasattr(assignee_user, 'profile') and assignee_user.profile.company:
                            assignee_company = assignee_user.profile.company
                        
                        # Check if both users are from the same company (or both have no company)
                        if user_company and assignee_company and user_company == assignee_company:
                            task.assignee = assignee_user
                        elif not user_company and not assignee_company:
                            # Both have no company - allow assignment
                            task.assignee = assignee_user
                        else:
                            return Response({
                                'status': 'error',
                                'message': 'Invalid assignee. User must be from the same company.'
                            }, status=status.HTTP_400_BAD_REQUEST)
                except (User.DoesNotExist, ValueError, TypeError) as e:
                    logger.error(f"Error validating assignee_id {assignee_id}: {str(e)}")
                    return Response({
                        'status': 'error',
                        'message': f'Invalid assignee_id: {assignee_id}'
                    }, status=status.HTTP_400_BAD_REQUEST)
        if 'due_date' in data:
            due_date_str = data.get('due_date')
            if due_date_str:
                try:
                    if 'T' in due_date_str:
                        task.due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
                    else:
                        due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
                        task.due_date = timezone.make_aware(due_date)
                except ValueError:
                    return Response({
                        'status': 'error',
                        'message': 'Invalid due_date format. Use YYYY-MM-DD or ISO format'
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                task.due_date = None
        
        task.save()

        # Optional dependency replacement (T-F1)
        if 'depends_on_ids' in data:
            cleaned, dep_error = _validate_dependency_change(task, data['depends_on_ids'])
            if dep_error is not None:
                return dep_error
            task.depends_on.set(cleaned)

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
                'assignee_name': task.assignee.get_full_name() if task.assignee and (task.assignee.first_name or task.assignee.last_name) else (task.assignee.username if task.assignee else None),
                'assignee_email': task.assignee.email if task.assignee else None,
                'due_date': task.due_date.isoformat() if task.due_date else None,
                'depends_on_ids': list(task.depends_on.values_list('id', flat=True)),
            }
        }, status=status.HTTP_200_OK)
    
    except Task.DoesNotExist:
        return Response({
            'status': 'error',
            'message': 'Task not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Error updating task: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to update task',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


BULK_TASK_UPDATE_MAX = 500


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_update_project_manager_tasks(request):
    """
    Bulk update tasks for a project manager.
    POST /api/user/project-manager/tasks/bulk-update

    Body: {
        "ids": [1, 2, 3, ...],
        "status"?: "todo"|"in_progress"|"review"|"done"|"blocked",
        "priority"?: "low"|"medium"|"high",
        "assignee_id"?: <user_id> | null | "none",
        "due_date"?: "YYYY-MM-DD" | ISO datetime | null
    }
    Returns: { updated: [ids], skipped: [{id, reason}], not_found: [ids] }
    """
    try:
        user = request.user

        if not hasattr(user, 'profile') or user.profile.role != 'project_manager':
            return Response({
                'status': 'error',
                'message': 'Access denied. Project manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)

        data = request.data or {}
        ids = data.get('ids') or []
        if not isinstance(ids, list) or not ids:
            return Response({
                'status': 'error',
                'message': 'ids must be a non-empty list of task IDs'
            }, status=status.HTTP_400_BAD_REQUEST)

        if len(ids) > BULK_TASK_UPDATE_MAX:
            return Response({
                'status': 'error',
                'message': f'Too many tasks. Limit is {BULK_TASK_UPDATE_MAX} per request.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Normalise IDs to ints, drop garbage
        normalized_ids = []
        for raw in ids:
            try:
                normalized_ids.append(int(raw))
            except (TypeError, ValueError):
                continue
        if not normalized_ids:
            return Response({
                'status': 'error',
                'message': 'No valid task IDs provided'
            }, status=status.HTTP_400_BAD_REQUEST)

        # At least one updatable field must be supplied
        supplied_fields = [k for k in ('status', 'priority', 'assignee_id', 'due_date') if k in data]
        if not supplied_fields:
            return Response({
                'status': 'error',
                'message': 'No fields to update. Provide status, priority, assignee_id, or due_date.'
            }, status=status.HTTP_400_BAD_REQUEST)

        bulk_force = str(data.get('force', '')).lower() in ('1', 'true', 'yes')

        # Validate the shared update values once
        new_status = None
        if 'status' in data:
            valid_statuses = [c[0] for c in Task.STATUS_CHOICES]
            if data['status'] not in valid_statuses:
                return Response({
                    'status': 'error',
                    'message': f"Invalid status. Allowed: {valid_statuses}"
                }, status=status.HTTP_400_BAD_REQUEST)
            new_status = data['status']

        new_priority = None
        if 'priority' in data:
            valid_priorities = [c[0] for c in Task.PRIORITY_CHOICES]
            if data['priority'] not in valid_priorities:
                return Response({
                    'status': 'error',
                    'message': f"Invalid priority. Allowed: {valid_priorities}"
                }, status=status.HTTP_400_BAD_REQUEST)
            new_priority = data['priority']

        # Resolve assignee once (None means "unassign", missing key means "leave alone")
        assignee_change = ('assignee_id' in data)
        new_assignee = None
        if assignee_change:
            raw_assignee = data.get('assignee_id')
            if raw_assignee in [None, '', 'none', 'null']:
                new_assignee = None
            else:
                try:
                    new_assignee = User.objects.get(id=int(raw_assignee))
                except (User.DoesNotExist, ValueError, TypeError):
                    return Response({
                        'status': 'error',
                        'message': f'Invalid assignee_id: {raw_assignee}'
                    }, status=status.HTTP_400_BAD_REQUEST)

        # Parse due_date once
        due_date_change = ('due_date' in data)
        new_due_date = None
        if due_date_change:
            due_date_str = data.get('due_date')
            if due_date_str in [None, '']:
                new_due_date = None
            else:
                try:
                    if 'T' in str(due_date_str):
                        new_due_date = datetime.fromisoformat(str(due_date_str).replace('Z', '+00:00'))
                    else:
                        parsed = datetime.strptime(str(due_date_str), '%Y-%m-%d')
                        new_due_date = timezone.make_aware(parsed)
                except ValueError:
                    return Response({
                        'status': 'error',
                        'message': 'Invalid due_date format. Use YYYY-MM-DD or ISO format.'
                    }, status=status.HTTP_400_BAD_REQUEST)

        user_company = None
        if hasattr(user, 'profile') and user.profile.company:
            user_company = user.profile.company

        # Pre-validate the new assignee is in the same company as the requester
        if assignee_change and new_assignee is not None:
            assignee_company = None
            if hasattr(new_assignee, 'profile') and new_assignee.profile.company:
                assignee_company = new_assignee.profile.company
            same_company = (
                (user_company and assignee_company and user_company == assignee_company)
                or (not user_company and not assignee_company)
            )
            if not same_company:
                return Response({
                    'status': 'error',
                    'message': 'Invalid assignee. User must be from the same company.'
                }, status=status.HTTP_400_BAD_REQUEST)

        tasks_qs = Task.objects.filter(id__in=normalized_ids).select_related('project', 'assignee')
        found_by_id = {t.id: t for t in tasks_qs}
        not_found = [tid for tid in normalized_ids if tid not in found_by_id]

        updated = []
        skipped = []

        for tid in normalized_ids:
            task = found_by_id.get(tid)
            if task is None:
                continue
            project = task.project

            # Access check — same as single-task update
            has_access = (
                project.project_manager_id == user.id
                or project.owner_id == user.id
                or Task.objects.filter(project=project, assignee=user).exists()
                or (user_company and project.company_id == user_company.id)
            )
            if not has_access:
                skipped.append({'id': tid, 'reason': 'access_denied'})
                continue

            try:
                update_fields = []
                if new_status is not None and task.status != new_status:
                    # T-F1 — honour blockers on transitions to in_progress/done
                    if new_status in ('in_progress', 'done') and not bulk_force:
                        blockers = _get_blockers(task)
                        if blockers:
                            skipped.append({
                                'id': tid,
                                'reason': 'blocked_by_dependencies',
                                'blocked_by': [b.id for b in blockers],
                            })
                            continue
                    task.status = new_status
                    update_fields.append('status')
                if new_priority is not None and task.priority != new_priority:
                    task.priority = new_priority
                    update_fields.append('priority')
                if assignee_change:
                    if (task.assignee_id or None) != (new_assignee.id if new_assignee else None):
                        task.assignee = new_assignee
                        update_fields.append('assignee')
                if due_date_change:
                    if task.due_date != new_due_date:
                        task.due_date = new_due_date
                        update_fields.append('due_date')

                if update_fields:
                    task.save(update_fields=update_fields + ['updated_at'])
                    updated.append(tid)
                else:
                    skipped.append({'id': tid, 'reason': 'no_change'})
            except Exception as exc:
                logger.exception(f"Bulk task update failed for task {tid}: {exc}")
                skipped.append({'id': tid, 'reason': 'save_failed'})

        logger.info(
            f"[BULK TASK UPDATE] user={user.id} requested={len(normalized_ids)} "
            f"updated={len(updated)} skipped={len(skipped)} not_found={len(not_found)}"
        )

        return Response({
            'status': 'success',
            'updated': updated,
            'skipped': skipped,
            'not_found': not_found,
            'summary': {
                'requested': len(normalized_ids),
                'updated': len(updated),
                'skipped': len(skipped),
                'not_found': len(not_found),
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception(f"Error in bulk task update: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to bulk update tasks',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def set_project_manager_task_dependencies(request, task_id):
    """
    Replace the full dependency set for a task.
    PUT/PATCH /api/user/project-manager/tasks/{task_id}/dependencies
    Body: { "depends_on_ids": [<task_id>, ...] }
    """
    try:
        user = request.user
        if not hasattr(user, 'profile') or user.profile.role != 'project_manager':
            return Response({
                'status': 'error',
                'message': 'Access denied. Project manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)

        task = get_object_or_404(Task, id=task_id)
        project = task.project

        user_company = getattr(getattr(user, 'profile', None), 'company', None)
        has_access = (
            project.project_manager_id == user.id
            or project.owner_id == user.id
            or Task.objects.filter(project=project, assignee=user).exists()
            or (user_company and project.company_id == user_company.id)
        )
        if not has_access:
            return Response({
                'status': 'error',
                'message': 'Access denied. You do not have permission to modify this task.'
            }, status=status.HTTP_403_FORBIDDEN)

        raw_ids = request.data.get('depends_on_ids')
        if raw_ids is None:
            return Response({
                'status': 'error',
                'message': 'depends_on_ids is required (pass [] to clear).'
            }, status=status.HTTP_400_BAD_REQUEST)

        cleaned, dep_error = _validate_dependency_change(task, raw_ids)
        if dep_error is not None:
            return dep_error

        task.depends_on.set(cleaned)

        deps = list(task.depends_on.all())
        return Response({
            'status': 'success',
            'message': 'Dependencies updated.',
            'data': {
                'id': task.id,
                'depends_on_ids': [d.id for d in deps],
                'depends_on': [_serialize_task_brief(d) for d in deps],
                'blocked_by': [_serialize_task_brief(d) for d in deps if d.status != 'done'],
            }
        }, status=status.HTTP_200_OK)

    except Task.DoesNotExist:
        return Response({
            'status': 'error',
            'message': 'Task not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Error setting task dependencies: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to update dependencies',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _serialize_recurrence(rec):
    return {
        'id': rec.id,
        'task_id': rec.template_task_id,
        'frequency': rec.frequency,
        'interval': rec.interval,
        'weekdays': rec.weekdays,
        'starts_on': rec.starts_on.isoformat() if rec.starts_on else None,
        'ends_on': rec.ends_on.isoformat() if rec.ends_on else None,
        'max_occurrences': rec.max_occurrences,
        'count_generated': rec.count_generated,
        'last_generated_on': rec.last_generated_on.isoformat() if rec.last_generated_on else None,
        'next_run_date': rec.next_run_date.isoformat() if rec.next_run_date else None,
        'is_active': rec.is_active,
    }


def _task_access_check(user, task):
    user_company = getattr(getattr(user, 'profile', None), 'company', None)
    project = task.project
    if (project.project_manager_id == user.id
            or project.owner_id == user.id
            or Task.objects.filter(project=project, assignee=user).exists()
            or (user_company and project.company_id == user_company.id)):
        return None
    return Response({
        'status': 'error',
        'message': 'Access denied. You do not have permission to modify this task.'
    }, status=status.HTTP_403_FORBIDDEN)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def project_manager_task_recurrence(request, task_id):
    """
    Manage a task's recurrence (T-F2).

    GET    /api/user/project-manager/tasks/{task_id}/recurrence
        Returns the recurrence config (or 404 if none set).
    PUT/PATCH /api/user/project-manager/tasks/{task_id}/recurrence
        Body: {
            frequency: 'daily'|'weekly'|'monthly',
            interval?: int (default 1),
            weekdays?: '0,2,4',
            starts_on: 'YYYY-MM-DD',
            ends_on?: 'YYYY-MM-DD',
            max_occurrences?: int,
            is_active?: bool
        }
    DELETE /api/user/project-manager/tasks/{task_id}/recurrence
        Removes the recurrence.
    """
    try:
        user = request.user
        if not hasattr(user, 'profile') or user.profile.role != 'project_manager':
            return Response({
                'status': 'error',
                'message': 'Access denied. Project manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)

        task = get_object_or_404(Task, id=task_id)
        access_err = _task_access_check(user, task)
        if access_err is not None:
            return access_err

        if request.method == 'GET':
            try:
                rec = task.recurrence
                return Response({'status': 'success', 'data': _serialize_recurrence(rec)}, status=status.HTTP_200_OK)
            except TaskRecurrence.DoesNotExist:
                return Response({'status': 'error', 'message': 'No recurrence set for this task.'}, status=status.HTTP_404_NOT_FOUND)

        if request.method == 'DELETE':
            TaskRecurrence.objects.filter(template_task=task).delete()
            return Response({'status': 'success', 'message': 'Recurrence removed.'}, status=status.HTTP_200_OK)

        # PUT/PATCH — upsert
        data = request.data or {}
        valid_frequencies = {c[0] for c in TaskRecurrence.FREQUENCY_CHOICES}
        frequency = data.get('frequency')
        if frequency not in valid_frequencies:
            return Response({
                'status': 'error',
                'message': f"Invalid frequency. Allowed: {sorted(valid_frequencies)}"
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            interval = int(data.get('interval', 1) or 1)
        except (TypeError, ValueError):
            return Response({'status': 'error', 'message': 'interval must be an integer'}, status=status.HTTP_400_BAD_REQUEST)
        if interval < 1:
            return Response({'status': 'error', 'message': 'interval must be >= 1'}, status=status.HTTP_400_BAD_REQUEST)

        weekdays_raw = (data.get('weekdays') or '').strip()
        if weekdays_raw and frequency != 'weekly':
            return Response({'status': 'error', 'message': 'weekdays only applies to weekly frequency.'}, status=status.HTTP_400_BAD_REQUEST)
        weekdays_clean = ''
        if weekdays_raw:
            try:
                wd_list = sorted({int(w.strip()) for w in weekdays_raw.split(',') if w.strip() != ''})
            except ValueError:
                return Response({'status': 'error', 'message': 'weekdays must be a comma-separated list of integers 0-6.'}, status=status.HTTP_400_BAD_REQUEST)
            if any(w < 0 or w > 6 for w in wd_list):
                return Response({'status': 'error', 'message': 'weekday values must be between 0 (Monday) and 6 (Sunday).'}, status=status.HTTP_400_BAD_REQUEST)
            weekdays_clean = ','.join(str(w) for w in wd_list)

        starts_on_str = data.get('starts_on')
        if not starts_on_str:
            return Response({'status': 'error', 'message': 'starts_on is required (YYYY-MM-DD).'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            starts_on = datetime.strptime(str(starts_on_str), '%Y-%m-%d').date()
        except ValueError:
            return Response({'status': 'error', 'message': 'Invalid starts_on. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

        ends_on = None
        ends_on_str = data.get('ends_on')
        if ends_on_str:
            try:
                ends_on = datetime.strptime(str(ends_on_str), '%Y-%m-%d').date()
            except ValueError:
                return Response({'status': 'error', 'message': 'Invalid ends_on. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)
            if ends_on < starts_on:
                return Response({'status': 'error', 'message': 'ends_on must be on or after starts_on.'}, status=status.HTTP_400_BAD_REQUEST)

        max_occurrences = data.get('max_occurrences')
        if max_occurrences is not None and max_occurrences != '':
            try:
                max_occurrences = int(max_occurrences)
            except (TypeError, ValueError):
                return Response({'status': 'error', 'message': 'max_occurrences must be an integer.'}, status=status.HTTP_400_BAD_REQUEST)
            if max_occurrences < 1:
                return Response({'status': 'error', 'message': 'max_occurrences must be >= 1.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            max_occurrences = None

        is_active = data.get('is_active')
        if is_active is None:
            is_active = True
        else:
            is_active = bool(is_active) if isinstance(is_active, bool) else str(is_active).lower() in ('1', 'true', 'yes')

        existing = TaskRecurrence.objects.filter(template_task=task).first()
        # If we're reconfiguring after some occurrences have already been
        # generated, keep the existing next_run_date so we don't double-generate.
        # Otherwise (fresh or pre-start), seed from starts_on.
        if existing and existing.last_generated_on and existing.last_generated_on >= starts_on:
            next_run = existing.next_run_date
        else:
            next_run = starts_on

        rec, _created = TaskRecurrence.objects.update_or_create(
            template_task=task,
            defaults={
                'frequency': frequency,
                'interval': interval,
                'weekdays': weekdays_clean,
                'starts_on': starts_on,
                'ends_on': ends_on,
                'max_occurrences': max_occurrences,
                'is_active': is_active,
                'next_run_date': next_run,
            },
        )
        return Response({'status': 'success', 'data': _serialize_recurrence(rec)}, status=status.HTTP_200_OK)

    except Task.DoesNotExist:
        return Response({'status': 'error', 'message': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Error managing task recurrence: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to update recurrence',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

"""
User Project Manager API Views
For users with project_manager role to manage projects and tasks
"""

from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.http import Http404
from django.db import models
from datetime import datetime
import logging

from api.authentication import EmployeeTokenAuthentication
from core.models import Project, Task, TaskRecurrence
from core.tenancy import company_of_user, members_of
from project_manager_agent import services as pm_services
from api.pagination import paginate
from django.db.models import Prefetch, prefetch_related_objects

logger = logging.getLogger(__name__)

# Employee logins (auth.User) only, stated explicitly (audit DATA-3). These
# views used to inherit DEFAULT_AUTHENTICATION_CLASSES; a dashboard login's
# token now gets a clear error instead of "Invalid token.".
EMPLOYEE_AUTH = [EmployeeTokenAuthentication, SessionAuthentication]


# Dependency helpers live in project_manager_agent.services.tasks now.
_serialize_task_brief = pm_services.serialize_brief


def _person_name(user):
    if user is None:
        return None
    return user.get_full_name() if (user.first_name or user.last_name) else user.username


def _project_payload(project):
    return {
        'id': project.id,
        'name': project.name,
        'description': project.description,
        'status': project.status,
        'priority': project.priority,
        'project_type': project.project_type,
        'deadline': project.effective_deadline.isoformat() if project.effective_deadline else None,
        'start_date': project.start_date.isoformat() if project.start_date else None,
    }


@api_view(['GET'])
@authentication_classes(EMPLOYEE_AUTH)
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
        # Explicit order with an `id` tiebreak: offset/limit over an unordered
        # queryset can repeat or skip rows between pages.
        page, pagination = paginate(
            request,
            Project.objects.filter(
                models.Q(tasks__assignee=user) | models.Q(project_manager=user) | models.Q(owner=user)
            ).distinct().order_by('-created_at', '-id'),
            default_limit=200, max_limit=500,
        )
        # One query for every task on the page, instead of one per project.
        prefetch_related_objects(page, Prefetch(
            'tasks', queryset=Task.objects.select_related('assignee', 'project', 'recurrence')
                                          .prefetch_related('depends_on')))

        projects_data = []
        for project in page:
            # Get ALL tasks for this project (not just user's tasks)
            all_project_tasks = project.tasks.all()

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
            'data': projects_data,
            'pagination': pagination,
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.exception(f"Error in get_project_manager_projects_tasks: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to fetch projects and tasks',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes(EMPLOYEE_AUTH)
@permission_classes([IsAuthenticated])
def create_project_manager_project(request):
    """
    Create a new project for a project manager
    POST /api/user/project-manager/projects/create
    Rules (validation, duplicate names, audit): project_manager_agent.services.
    """
    try:
        actor = pm_services.EmployeeActor.from_request(request)
        project = pm_services.create_project(actor, request.data)
    except pm_services.ServiceError as exc:
        return exc.response()
    except Exception as e:
        logger.exception(f"Error in create_project_manager_project: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to create project',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({
        'status': 'success',
        'message': 'Project created successfully',
        'data': _project_payload(project),
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@authentication_classes(EMPLOYEE_AUTH)
@permission_classes([IsAuthenticated])
def create_project_manager_task(request):
    """
    Create a new task in a project (for project managers)
    POST /api/user/project-manager/tasks/create
    Rules (validation, dependencies, due-date bounds, audit): project_manager_agent.services.
    """
    try:
        actor = pm_services.EmployeeActor.from_request(request)
        task = pm_services.create_task(actor, request.data)
    except pm_services.ServiceError as exc:
        return exc.response()
    except Exception as e:
        logger.exception(f"Error in create_project_manager_task: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to create task',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({
        'status': 'success',
        'message': 'Task created successfully',
        'data': {
            'id': task.id,
            'title': task.title,
            'description': task.description,
            'status': task.status,
            'priority': task.priority,
            'assignee_id': task.assignee_id,
            'assignee_name': _person_name(task.assignee),
            'due_date': task.due_date.isoformat() if task.due_date else None,
            'depends_on_ids': list(task.depends_on.values_list('id', flat=True)),
        }
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@authentication_classes(EMPLOYEE_AUTH)
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
        
        company = company_of_user(user)

        if not company:
            return Response({
                'status': 'error',
                'message': 'User is not associated with a company'
            }, status=status.HTTP_400_BAD_REQUEST)

        # The company's active employee logins, through either profile link —
        # the same rule the assignment endpoints enforce (core.tenancy). This
        # listed `profile.company` matches only, so colleagues linked through
        # their creating dashboard login were missing, and deactivated users
        # were offered even though assigning them is refused.
        members, pagination = paginate(
            request,
            members_of(company).select_related('profile').order_by('id'),
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
        logger.exception(f"Error in get_company_users_for_pm: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to fetch company users',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes(EMPLOYEE_AUTH)
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
        projects, pagination = paginate(
            request,
            Project.objects.filter(
                models.Q(tasks__assignee=user) | models.Q(project_manager=user) | models.Q(owner=user)
            ).distinct().order_by('-created_at', '-id'),
            default_limit=200, max_limit=500,
        )
        # One grouped COUNT for the page instead of `project.tasks.count()` per
        # row. Not `annotate(Count('tasks'))`: the filter above already joins
        # through tasks (assignee=user), and Django would reuse that filtered
        # join — counting only this user's tasks rather than all of them.
        task_counts = dict(
            Task.objects.filter(project_id__in=[p.id for p in projects])
                        .values('project_id').annotate(c=models.Count('id'))
                        .values_list('project_id', 'c')
        )

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
                'tasks_count': task_counts.get(project.id, 0),
            })
        
        return Response({
            'status': 'success',
            'data': projects_data,
            'pagination': pagination,
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.exception(f"Error in get_project_manager_projects: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to fetch projects',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'PATCH'])
@authentication_classes(EMPLOYEE_AUTH)
@permission_classes([IsAuthenticated])
def update_project_manager_project(request, project_id):
    """
    Update a project (for project managers)
    PUT/PATCH /api/user/project-manager/projects/{project_id}/update
    Rules: project_manager_agent.services.
    """
    try:
        actor = pm_services.EmployeeActor.from_request(request)
        project, _ = pm_services.update_project(actor, project_id, request.data)
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
        'data': _project_payload(project),
    }, status=status.HTTP_200_OK)


@api_view(['PUT', 'PATCH'])
@authentication_classes(EMPLOYEE_AUTH)
@permission_classes([IsAuthenticated])
def update_project_manager_task(request, task_id):
    """
    Update a task (for project managers)
    PUT/PATCH /api/user/project-manager/tasks/{task_id}/update
    Rules: project_manager_agent.services.
    """
    try:
        actor = pm_services.EmployeeActor.from_request(request)
        task, _ = pm_services.update_task(actor, task_id, request.data)
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
            'assignee_name': _person_name(task.assignee),
            'assignee_email': task.assignee.email if task.assignee else None,
            'due_date': task.due_date.isoformat() if task.due_date else None,
            'depends_on_ids': list(task.depends_on.values_list('id', flat=True)),
        }
    }, status=status.HTTP_200_OK)


BULK_TASK_UPDATE_MAX = 500


@api_view(['POST'])
@authentication_classes(EMPLOYEE_AUTH)
@permission_classes([IsAuthenticated])
def bulk_update_project_manager_tasks(request):
    """
    Bulk update tasks for a project manager.
    POST /api/user/project-manager/tasks/bulk-update

    Body: {"ids": [...], "status"?, "priority"?, "assignee_id"?, "due_date"?, "force"?}
    Returns: { updated: [ids], skipped: [{id, reason}], not_found: [ids] }
    Rules: project_manager_agent.services.bulk_update_tasks.
    """
    try:
        actor = pm_services.EmployeeActor.from_request(request)
        result = pm_services.bulk_update_tasks(actor, request.data or {})
    except pm_services.ServiceError as exc:
        return exc.response()
    except Exception as e:
        logger.exception(f"Error in bulk task update: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to bulk update tasks',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    logger.info(
        f"[BULK TASK UPDATE] user={request.user.id} requested={result['requested']} "
        f"updated={len(result['updated'])} skipped={len(result['skipped'])} "
        f"not_found={len(result['not_found'])}"
    )
    return Response({
        'status': 'success',
        'updated': result['updated'],
        'skipped': result['skipped'],
        'not_found': result['not_found'],
        'summary': {
            'requested': result['requested'],
            'updated': len(result['updated']),
            'skipped': len(result['skipped']),
            'not_found': len(result['not_found']),
        }
    }, status=status.HTTP_200_OK)


@api_view(['PUT', 'PATCH'])
@authentication_classes(EMPLOYEE_AUTH)
@permission_classes([IsAuthenticated])
def set_project_manager_task_dependencies(request, task_id):
    """
    Replace a task's dependency list.
    PUT/PATCH /api/user/project-manager/tasks/{task_id}/dependencies
    Body: { "depends_on_ids": [<task_id>, ...] }
    """
    try:
        actor = pm_services.EmployeeActor.from_request(request)
        task = pm_services.set_dependencies(actor, task_id, request.data.get('depends_on_ids'))
    except pm_services.ServiceError as exc:
        return exc.response()
    except Exception as e:
        logger.exception(f"Error setting task dependencies: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to update task dependencies',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
    user_company = company_of_user(user)
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
@authentication_classes(EMPLOYEE_AUTH)
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

    except (Task.DoesNotExist, Http404):
        return Response({'status': 'error', 'message': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Error managing task recurrence: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to update recurrence',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

"""Project / task deletion across the PM API families (GAP-2).

Before this module, delete coverage depended on which API family you called:

    projects  — only /api/project-manager/   (CompanyUser)
    tasks     — only /api/company/           (CompanyUser)
    end users — could create and update, never delete

and the two deletes that did exist had their own bugs:

  * both scoped strictly by `company=company`, so projects saved with
    company=NULL by the old Project Pilot upload path were undeletable;
  * `delete_company_task` caught `Task.DoesNotExist` around a
    `get_object_or_404` (which raises Http404), so the handler was dead code and
    a missing or foreign task returned 500 instead of 404;
  * `delete_company_task` wrote no audit entry.

Deletion stays a hard delete. Soft delete was considered and deliberately left
out: every Project/Task query across three API families, thirteen agents and
the dashboards would need a `deleted_at IS NULL` filter, and missing one would
silently resurrect deleted data. Instead, every delete reports exactly what the
cascade removed, so the irreversibility is visible to the caller.
"""
from __future__ import annotations

import json
import logging

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes, throttle_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.models import Project, Subtask, Task
from api.views.pm_agent import PMCRUDThrottle, _audit_log
from core.tenancy import company_of_user, projects_for_company_user, tasks_for_company_user

logger = logging.getLogger(__name__)


def _not_found(what):
    return Response({'status': 'error',
                     'message': f'{what} not found or you do not have permission to delete it.'},
                    status=status.HTTP_404_NOT_FOUND)


def _cascade_counts_for_project(project):
    tasks = Task.objects.filter(project=project)
    return {
        'tasks': tasks.count(),
        'subtasks': Subtask.objects.filter(task__project=project).count(),
    }


def _cascade_counts_for_task(task):
    return {'subtasks': Subtask.objects.filter(task=task).count()}


# ---------------------------------------------------------------------------
# Shared CompanyUser implementations — used by both the /api/project-manager/
# and /api/company/ routes so the two can't drift apart again.
# ---------------------------------------------------------------------------

def delete_project_as_company_user(request, project_id):
    company_user = request.user
    project = projects_for_company_user(company_user).filter(pk=project_id).first()
    if project is None:
        return _not_found('Project')
    name = project.name
    with transaction.atomic():
        removed = _cascade_counts_for_project(project)
        project.delete()
    _audit_log(company_user, 'project_deleted', 'Project', project_id, name,
               {'cascade': removed})
    return Response({
        'status': 'success',
        'message': 'Project deleted successfully',
        'data': {'id': int(project_id), 'name': name, 'deleted': removed},
    }, status=status.HTTP_200_OK)


def delete_task_as_company_user(request, task_id):
    company_user = request.user
    task = tasks_for_company_user(company_user).filter(pk=task_id).first()
    if task is None:
        return _not_found('Task')
    title, project_id = task.title, task.project_id
    with transaction.atomic():
        removed = _cascade_counts_for_task(task)
        task.delete()
    _audit_log(company_user, 'task_deleted', 'Task', task_id, title,
               {'project_id': project_id, 'cascade': removed})
    return Response({
        'status': 'success',
        'message': 'Task deleted successfully',
        'data': {'id': int(task_id), 'title': title, 'deleted': removed},
    }, status=status.HTTP_200_OK)


@api_view(['DELETE', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([PMCRUDThrottle])
def delete_task_manual(request, task_id):
    """DELETE /api/project-manager/tasks/<task_id>/delete

    The PM family had create-task and delete-project but no delete-task, so the
    dashboard had to reach into /api/company/ for it.
    """
    return delete_task_as_company_user(request, task_id)


# ---------------------------------------------------------------------------
# End-user (auth.User) deletes — /api/user/project-manager/
#
# Stricter than update on purpose. Update lets anyone *assigned a task* in the
# project edit it; applying that to delete would let a person assigned one task
# wipe the entire project and everything beneath it. Deleting requires being the
# project's manager or owner.
# ---------------------------------------------------------------------------

def _require_pm_role(user):
    if not hasattr(user, 'profile') or user.profile.role != 'project_manager':
        return Response({'status': 'error',
                         'message': 'Access denied. Project manager role required.'},
                        status=status.HTTP_403_FORBIDDEN)
    return None


def _can_delete(user, project):
    return project.project_manager_id == user.id or project.owner_id == user.id


def _log_user_activity(request, user, action, entity_type, entity_id, details):
    try:
        from core.models import UserActivityLog
        UserActivityLog.objects.create(
            user=user, action=action, entity_type=entity_type, entity_id=entity_id,
            details=json.dumps(details, default=str),
            ip_address=(request.META.get('REMOTE_ADDR') or None),
        )
    except Exception:
        # Same policy as PM's _audit_log: logging must never undo a user action.
        logger.exception('UserActivityLog write failed for %s %s', action, entity_id)


def _end_user_project(user, project_id):
    qs = Project.objects.filter(pk=project_id)
    company = company_of_user(user)
    if company is not None:
        qs = qs.filter(company=company)
    return qs.first()


@api_view(['DELETE', 'POST'])
@permission_classes([IsAuthenticated])
def delete_project_manager_project(request, project_id):
    """DELETE /api/user/project-manager/projects/<project_id>/delete"""
    user = request.user
    denied = _require_pm_role(user)
    if denied:
        return denied
    project = _end_user_project(user, project_id)
    if project is None:
        return _not_found('Project')
    if not _can_delete(user, project):
        return Response({'status': 'error',
                         'message': 'Only the project manager or owner can delete this project.'},
                        status=status.HTTP_403_FORBIDDEN)
    name = project.name
    with transaction.atomic():
        removed = _cascade_counts_for_project(project)
        project.delete()
    _log_user_activity(request, user, 'project_deleted', 'Project', int(project_id),
                       {'name': name, 'cascade': removed})
    return Response({'status': 'success', 'message': 'Project deleted successfully',
                     'data': {'id': int(project_id), 'name': name, 'deleted': removed}})


@api_view(['DELETE', 'POST'])
@permission_classes([IsAuthenticated])
def delete_project_manager_task(request, task_id):
    """DELETE /api/user/project-manager/tasks/<task_id>/delete"""
    user = request.user
    denied = _require_pm_role(user)
    if denied:
        return denied
    task = Task.objects.select_related('project').filter(pk=task_id).first()
    company = company_of_user(user)
    if task is None or (company is not None and task.project.company_id != company.id):
        return _not_found('Task')
    if not _can_delete(user, task.project):
        return Response({'status': 'error',
                         'message': 'Only the project manager or owner can delete tasks in this project.'},
                        status=status.HTTP_403_FORBIDDEN)
    title, project_id = task.title, task.project_id
    with transaction.atomic():
        removed = _cascade_counts_for_task(task)
        task.delete()
    _log_user_activity(request, user, 'task_deleted', 'Task', int(task_id),
                       {'title': title, 'project_id': project_id, 'cascade': removed})
    return Response({'status': 'success', 'message': 'Task deleted successfully',
                     'data': {'id': int(task_id), 'title': title, 'deleted': removed}})

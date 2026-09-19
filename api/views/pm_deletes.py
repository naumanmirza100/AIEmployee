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

import logging

from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes, throttle_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication, EmployeeTokenAuthentication
from api.permissions import IsCompanyUserOnly
from api.views.pm_agent import PMCRUDThrottle
from project_manager_agent import services as pm_services

logger = logging.getLogger(__name__)


def _deleted(message, result):
    return Response({'status': 'success', 'message': message, 'data': result},
                    status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Dashboard logins — used by both the /api/project-manager/ and /api/company/
# routes. Scope, cascade counts and the audit entry: project_manager_agent.services.
# ---------------------------------------------------------------------------

def delete_project_as_company_user(request, project_id):
    try:
        result = pm_services.delete_project(pm_services.DashboardActor.from_request(request), project_id)
    except pm_services.ServiceError as exc:
        return exc.response()
    return _deleted('Project deleted successfully', result)


def delete_task_as_company_user(request, task_id):
    try:
        result = pm_services.delete_task(pm_services.DashboardActor.from_request(request), task_id)
    except pm_services.ServiceError as exc:
        return exc.response()
    return _deleted('Task deleted successfully', result)


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
# Employee logins — /api/user/project-manager/
#
# Stricter than update on purpose. Update lets anyone *assigned a task* in the
# project edit it; applying that to delete would let a person assigned one task
# wipe the entire project and everything beneath it. Deleting requires being the
# project's manager or owner (EmployeeActor.project_for_delete).
# ---------------------------------------------------------------------------

@api_view(['DELETE', 'POST'])
@authentication_classes([EmployeeTokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def delete_project_manager_project(request, project_id):
    """DELETE /api/user/project-manager/projects/<project_id>/delete"""
    try:
        result = pm_services.delete_project(pm_services.EmployeeActor.from_request(request), project_id)
    except pm_services.ServiceError as exc:
        return exc.response()
    return _deleted('Project deleted successfully', result)


@api_view(['DELETE', 'POST'])
@authentication_classes([EmployeeTokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def delete_project_manager_task(request, task_id):
    """DELETE /api/user/project-manager/tasks/<task_id>/delete"""
    try:
        result = pm_services.delete_task(pm_services.EmployeeActor.from_request(request), task_id)
    except pm_services.ServiceError as exc:
        return exc.response()
    return _deleted('Task deleted successfully', result)

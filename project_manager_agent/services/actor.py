"""Who is making a project/task change, and what they may touch.

Two kinds of login manage projects:

  DashboardActor — a company dashboard login (CompanyUser). May see and change
                   every project and task of its company.
  EmployeeActor  — an employee login (auth.User) with role project_manager.
                   May change a project it manages, owns or has a task in; may
                   change any task in its company; may delete only projects it
                   manages or owns (and their tasks).

Every rule about scope, permission, assignees and the audit trail lives here,
once, for all three API families (see MDS/PM_API_CONSOLIDATION_PLAN.md).
"""
import json
import logging

from core.models import Project, Task, UserProfile
from core.tenancy import (
    AssigneeNotAllowed, company_of_user, projects_for_company_user, resolve_member,
    tasks_for_company_user,
)

from .errors import ServiceError, forbidden, not_found
from .parsing import is_empty

logger = logging.getLogger(__name__)

PROJECT_NOT_FOUND = 'Project not found or you do not have permission to change it.'
TASK_NOT_FOUND = 'Task not found or you do not have permission to change it.'


def project_owner_for(company_user):
    """The auth.User recorded as owner of a project a dashboard login creates.

    Project.owner is required and must be an auth.User, which a dashboard
    login is not. Prefers a user this dashboard login created; otherwise finds
    or creates a stand-in user for it.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    profile = (UserProfile.objects.filter(created_by_company_user=company_user)
               .select_related('user').first())
    if profile and profile.user:
        return profile.user

    names = (company_user.full_name or '').split()
    user, created = User.objects.get_or_create(
        username=f"cu_{company_user.id}_{company_user.email.split('@')[0]}",
        defaults={
            'email': company_user.email,
            'first_name': names[0] if names else '',
            'last_name': ' '.join(names[1:]),
        },
    )
    if created:
        UserProfile.objects.get_or_create(user=user, defaults={'created_by_company_user': company_user})
    return user


def _client_ip(request):
    return (request.META.get('REMOTE_ADDR') or None) if request is not None else None


class Actor:
    kind = ''
    company = None

    # --- lookups; each raises ServiceError (404/403) instead of returning None
    def project_for_edit(self, project_id) -> Project:
        raise NotImplementedError

    def project_for_new_task(self, project_id) -> Project:
        if is_empty(project_id):
            raise ServiceError('project_id is required')
        return self.project_for_edit(project_id)

    def task_for_edit(self, task_id) -> Task:
        raise NotImplementedError

    def project_for_delete(self, project_id) -> Project:
        raise NotImplementedError

    def task_for_delete(self, task_id) -> Task:
        raise NotImplementedError

    def can_edit_task(self, task) -> bool:
        raise NotImplementedError

    # --- people and new rows
    def resolve_assignee(self, raw):
        raise NotImplementedError

    def new_project_fields(self) -> dict:
        raise NotImplementedError

    def duplicate_name_scope(self):
        """Projects whose names a new project's name is compared against."""
        raise NotImplementedError

    # --- audit: one entry per write, whatever the API family
    def audit(self, action, model_name, object_id, title='', details=None):
        raise NotImplementedError


class DashboardActor(Actor):
    kind = 'dashboard'

    def __init__(self, company_user, request=None):
        self.company_user = company_user
        self.company = getattr(company_user, 'company', None)
        self.request = request

    @classmethod
    def from_request(cls, request):
        return cls(request.user, request)

    def _project(self, project_id):
        try:
            pk = int(project_id)
        except (TypeError, ValueError):
            raise not_found(PROJECT_NOT_FOUND)
        project = projects_for_company_user(self.company_user).filter(pk=pk).first()
        if project is None:
            raise not_found(PROJECT_NOT_FOUND)
        return project

    def project_for_edit(self, project_id):
        return self._project(project_id)

    def project_for_delete(self, project_id):
        return self._project(project_id)

    def _task(self, task_id):
        try:
            pk = int(task_id)
        except (TypeError, ValueError):
            raise not_found(TASK_NOT_FOUND)
        task = tasks_for_company_user(self.company_user).select_related('project').filter(pk=pk).first()
        if task is None:
            raise not_found(TASK_NOT_FOUND)
        return task

    def task_for_edit(self, task_id):
        return self._task(task_id)

    def task_for_delete(self, task_id):
        return self._task(task_id)

    def can_edit_task(self, task):
        return tasks_for_company_user(self.company_user).filter(pk=task.pk).exists()

    def resolve_assignee(self, raw):
        if is_empty(raw):
            return None
        try:
            return resolve_member(raw, company=self.company, company_user=self.company_user)
        except AssigneeNotAllowed:
            raise ServiceError('Invalid assignee. User must belong to your company and be active.')

    def new_project_fields(self):
        return {
            'company': self.company,
            'created_by_company_user': self.company_user,
            'owner': project_owner_for(self.company_user),
        }

    def duplicate_name_scope(self):
        if self.company is not None:
            return Project.objects.filter(company=self.company)
        return Project.objects.filter(created_by_company_user=self.company_user)

    def audit(self, action, model_name, object_id, title='', details=None):
        # pm_agent._audit_log keeps the failure counter the health endpoint reports.
        from api.views.pm_agent import _audit_log
        _audit_log(self.company_user, action, model_name, object_id, title, details)


class EmployeeActor(Actor):
    kind = 'employee'

    def __init__(self, user, request=None):
        self.user = user
        self.company = company_of_user(user)
        self.request = request

    @classmethod
    def from_request(cls, request):
        user = request.user
        profile = getattr(user, 'profile', None)
        if profile is None or profile.role != 'project_manager':
            raise forbidden('Access denied. Project manager role required.')
        return cls(user, request)

    def _manages(self, project):
        return (project.project_manager_id == self.user.id
                or project.owner_id == self.user.id)

    def _works_on(self, project):
        return (self._manages(project)
                or Task.objects.filter(project=project, assignee=self.user).exists())

    def _in_company(self, project):
        return self.company is not None and project.company_id == self.company.id

    def _project_in_scope(self, project_id):
        try:
            pk = int(project_id)
        except (TypeError, ValueError):
            raise not_found(PROJECT_NOT_FOUND)
        qs = Project.objects.filter(pk=pk)
        if self.company is not None:
            qs = qs.filter(company=self.company)
        project = qs.first()
        if project is None:
            raise not_found(PROJECT_NOT_FOUND)
        return project

    def project_for_edit(self, project_id):
        project = self._project_in_scope(project_id)
        if not self._works_on(project):
            raise forbidden('Access denied. You can only change projects you manage, own, '
                            'or have a task in.')
        return project

    def project_for_delete(self, project_id):
        project = self._project_in_scope(project_id)
        if not self._manages(project):
            raise forbidden('Only the project manager or owner can delete this project.')
        return project

    def can_edit_task(self, task):
        project = task.project
        return self._works_on(project) or self._in_company(project)

    def _task(self, task_id):
        try:
            pk = int(task_id)
        except (TypeError, ValueError):
            raise not_found(TASK_NOT_FOUND)
        task = Task.objects.select_related('project').filter(pk=pk).first()
        if task is None:
            raise not_found(TASK_NOT_FOUND)
        return task

    def task_for_edit(self, task_id):
        task = self._task(task_id)
        if not self.can_edit_task(task):
            raise forbidden('Access denied. You do not have permission to update this task.')
        return task

    def task_for_delete(self, task_id):
        task = self._task(task_id)
        if self.company is not None and task.project.company_id != self.company.id:
            raise not_found(TASK_NOT_FOUND)
        if not self._manages(task.project):
            raise forbidden('Only the project manager or owner can delete tasks in this project.')
        return task

    def resolve_assignee(self, raw):
        if is_empty(raw):
            return None
        try:
            if int(raw) == self.user.id:
                return self.user
            return resolve_member(raw, company=self.company)
        except (AssigneeNotAllowed, TypeError, ValueError):
            raise ServiceError('Invalid assignee. User must be from the same company.')

    def new_project_fields(self):
        if self.company is None:
            raise ServiceError('User is not associated with a company')
        return {'company': self.company, 'owner': self.user, 'project_manager': self.user}

    def duplicate_name_scope(self):
        if self.company is not None:
            return Project.objects.filter(company=self.company)
        return Project.objects.filter(owner=self.user)

    def audit(self, action, model_name, object_id, title='', details=None):
        try:
            from core.models import UserActivityLog
            UserActivityLog.objects.create(
                user=self.user, action=action, entity_type=model_name, entity_id=object_id,
                details=json.dumps({'title': title, **(details or {})}, default=str),
                ip_address=_client_ip(self.request),
            )
        except Exception:
            # Same policy as the dashboard audit log: logging never undoes a change.
            logger.exception('UserActivityLog write failed for %s %s', action, object_id)

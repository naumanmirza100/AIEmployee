"""Creating, editing, bulk-updating and deleting tasks.

Covers the rules that used to differ between families: assignee scope
(SEC-1), due dates inside the project's dates, dependency blocking, and
validation of status, priority and estimated hours.
"""
from django.contrib.auth.models import User

from api.views import company_projects_tasks as company
from api.views import pm_agent as dashboard
from api.views import pm_deletes as deletes
from api.views import user_project_manager as employee
from core.models import Subtask, Task

from .base import PMTestCase


class DashboardCreateTaskTests(PMTestCase):
    """POST /api/project-manager/tasks/create"""

    def create(self, data, actor=None):
        payload = {'project_id': self.project.id, 'title': 'A task'}
        payload.update(data)
        return self.call(dashboard.create_task_manual, actor or self.dash, payload)

    def test_all_fields_are_stored(self):
        code, body = self.create({'assignee_id': self.dev.id, 'due_date': self.inside,
                                  'estimated_hours': '3.5', 'priority': 'high'})
        self.assertEqual(code, 201, body)
        task = Task.objects.get(pk=body['data']['id'])
        self.assertEqual(task.assignee_id, self.dev.id)
        self.assertEqual(task.estimated_hours, 3.5)
        self.assertEqual(task.priority, 'high')

    def test_assignee_from_another_company_is_refused(self):
        """SEC-1, the cross-tenant leak."""
        code, body = self.create({'assignee_id': self.rival_pm.id})
        self.assertEqual(code, 400)
        self.assertIn('Invalid assignee', body['message'])
        self.assertFalse(Task.objects.filter(assignee=self.rival_pm).exists())

    def test_due_date_after_the_project_deadline_is_refused(self):
        code, body = self.create({'due_date': self.after_deadline})
        self.assertEqual(code, 400)
        self.assertIn('deadline', body['message'])

    def test_due_date_before_the_project_start_is_refused(self):
        code, body = self.create({'due_date': self.before_start})
        self.assertEqual(code, 400)
        self.assertIn('start date', body['message'])

    def test_unreadable_due_date_is_refused(self):
        code, body = self.create({'due_date': '07/02/2026 5am'})
        self.assertEqual(code, 400, body)
        self.assertFalse(Task.objects.filter(title='A task').exists())

    def test_unreadable_estimated_hours_is_a_400(self):
        code, _ = self.create({'estimated_hours': 'abc'})
        self.assertEqual(code, 400)

    def test_invalid_status_is_refused(self):
        code, _ = self.create({'status': 'nope'})
        self.assertEqual(code, 400)

    def test_task_on_a_colleagues_project_is_allowed(self):
        code, body = self.create({'project_id': self.colleague_project.id})
        self.assertEqual(code, 201, body)

    def test_task_on_another_companys_project_is_not_found(self):
        code, _ = self.create({'project_id': self.rival_project.id})
        self.assertEqual(code, 404)

    def test_dependencies_can_be_set_at_creation(self):
        prereq = self.task(title='Prereq')
        code, body = self.create({'title': 'Dependent', 'depends_on_ids': [prereq.id]})
        self.assertEqual(code, 201, body)
        task = Task.objects.get(pk=body['data']['id'])
        self.assertEqual(list(task.depends_on.values_list('id', flat=True)), [prereq.id])

    def test_cannot_be_created_done_while_a_dependency_is_open(self):
        prereq = self.task(title='Prereq', status='todo')
        code, body = self.create({'status': 'done', 'depends_on_ids': [prereq.id]})
        self.assertEqual(code, 409, body)
        self.assertFalse(Task.objects.filter(title='A task').exists())


class CompanyUpdateTaskTests(PMTestCase):
    """PUT /api/company/tasks/<id>/update — the dashboard's edit screen."""

    def setUp(self):
        super().setUp()
        self.editable = self.task(title='Editable', assignee=self.dev)
        self.prereq = self.task(title='Prereq', status='todo')
        self.blocked = self.task(title='Blocked')
        self.blocked.depends_on.set([self.prereq])

    def update(self, data, task=None, actor=None):
        return self.call(company.update_company_task, actor or self.dash, data,
                         method='put', task_id=(task or self.editable).id)

    def test_fields_are_saved(self):
        code, body = self.update({'title': 'Edited', 'priority': 'high', 'status': 'review',
                                  'assignee_id': self.pm.id, 'due_date': self.inside})
        self.assertEqual(code, 200, body)
        self.editable.refresh_from_db()
        self.assertEqual(self.editable.title, 'Edited')
        self.assertEqual(self.editable.assignee_id, self.pm.id)

    def test_invalid_priority_saves_nothing(self):
        code, _ = self.update({'title': 'Half applied', 'priority': 'nope'})
        self.assertEqual(code, 400)
        self.editable.refresh_from_db()
        self.assertEqual(self.editable.title, 'Editable')

    def test_moving_to_done_while_blocked_is_refused(self):
        """D3: the dashboard used to bypass the dependency rule."""
        code, body = self.update({'status': 'done'}, task=self.blocked)
        self.assertEqual(code, 409)
        self.assertEqual([b['id'] for b in body['blocked_by']], [self.prereq.id])
        self.assertIn('force', body['hint'])
        self.blocked.refresh_from_db()
        self.assertNotEqual(self.blocked.status, 'done')

    def test_force_overrides_the_dependency_block(self):
        code, body = self.update({'status': 'done', 'force': True}, task=self.blocked)
        self.assertEqual(code, 200, body)
        self.blocked.refresh_from_db()
        self.assertEqual(self.blocked.status, 'done')

    def test_resending_the_current_status_is_not_blocked(self):
        Task.objects.filter(pk=self.blocked.pk).update(status='done')
        code, body = self.update({'status': 'done', 'title': 'Renamed'}, task=self.blocked)
        self.assertEqual(code, 200, body)

    def test_due_date_outside_the_project_dates_is_refused(self):
        code, _ = self.update({'due_date': self.after_deadline})
        self.assertEqual(code, 400)

    def test_an_existing_out_of_range_due_date_is_left_alone(self):
        """D4 applies when the due date changes, not to every later edit."""
        Task.objects.filter(pk=self.editable.pk).update(due_date='2099-01-01 00:00:00+00:00')
        code, body = self.update({'title': 'Renamed only'})
        self.assertEqual(code, 200, body)

    def test_assignee_from_another_company_is_refused(self):
        code, _ = self.update({'assignee_id': self.rival_pm.id})
        self.assertEqual(code, 400)

    def test_a_task_can_be_unassigned(self):
        code, body = self.update({'assignee_id': ''})
        self.assertEqual(code, 200, body)
        self.editable.refresh_from_db()
        self.assertIsNone(self.editable.assignee_id)

    def test_keeping_a_deactivated_assignee_is_allowed(self):
        """Only a *change* of assignee is checked, or the task couldn't be edited at all."""
        User.objects.filter(pk=self.dev.pk).update(is_active=False)
        code, body = self.update({'title': 'Still editable', 'assignee_id': self.dev.id})
        self.assertEqual(code, 200, body)

    def test_another_companys_task_is_not_found(self):
        foreign = Task.objects.create(project=self.rival_project, title='Theirs')
        code, _ = self.update({'title': 'Stolen'}, task=foreign)
        self.assertEqual(code, 404)


class EmployeeTaskTests(PMTestCase):
    """/api/user/project-manager/tasks/…"""

    def setUp(self):
        super().setUp()
        self.editable = self.task(title='Editable', assignee=self.dev)
        self.prereq = self.task(title='Prereq', status='todo')
        self.blocked = self.task(title='Blocked')
        self.blocked.depends_on.set([self.prereq])

    def test_a_bad_dependency_list_saves_nothing(self):
        """Audit bug 3: fields used to be saved before the list was validated."""
        code, _ = self.call(employee.update_project_manager_task, self.pm,
                            {'title': 'Should not save', 'depends_on_ids': [self.editable.id]},
                            method='put', task_id=self.editable.id)
        self.assertEqual(code, 400)
        self.editable.refresh_from_db()
        self.assertEqual(self.editable.title, 'Editable')

    def test_a_dependency_cycle_is_refused(self):
        code, _ = self.call(employee.set_project_manager_task_dependencies, self.pm,
                            {'depends_on_ids': [self.blocked.id]},
                            method='put', task_id=self.prereq.id)
        self.assertEqual(code, 400)

    def test_dependencies_can_be_replaced(self):
        code, body = self.call(employee.set_project_manager_task_dependencies, self.pm,
                               {'depends_on_ids': []}, method='put', task_id=self.blocked.id)
        self.assertEqual(code, 200, body)
        self.assertEqual(self.blocked.depends_on.count(), 0)

    def test_moving_to_done_while_blocked_is_refused(self):
        code, body = self.call(employee.update_project_manager_task, self.pm,
                               {'status': 'done'}, method='put', task_id=self.blocked.id)
        self.assertEqual(code, 409, body)

    def test_unreadable_estimated_hours_is_a_400_not_a_500(self):
        code, _ = self.call(employee.create_project_manager_task, self.pm,
                            {'project_id': self.project.id, 'title': 'x', 'estimated_hours': 'abc'})
        self.assertEqual(code, 400)


class BulkUpdateTests(PMTestCase):
    """POST /api/user/project-manager/tasks/bulk-update"""

    def setUp(self):
        super().setUp()
        self.one = self.task(title='One')
        self.two = self.task(title='Two')
        self.foreign = Task.objects.create(project=self.rival_project, title='Theirs')

    def bulk(self, data, actor=None):
        return self.call(employee.bulk_update_project_manager_tasks, actor or self.pm, data)

    def test_updates_reports_skips_and_missing_ids(self):
        code, body = self.bulk({'ids': [self.one.id, self.foreign.id, 999999999],
                                'priority': 'high'})
        self.assertEqual(code, 200, body)
        self.assertEqual(body['updated'], [self.one.id])
        self.assertEqual(body['skipped'], [{'id': self.foreign.id, 'reason': 'access_denied'}])
        self.assertEqual(body['not_found'], [999999999])
        self.one.refresh_from_db()
        self.assertEqual(self.one.priority, 'high')

    def test_one_bad_task_does_not_undo_the_others(self):
        """DATA-1: each task gets its own savepoint."""
        prereq = self.task(title='Prereq', status='todo')
        self.two.depends_on.set([prereq])
        code, body = self.bulk({'ids': [self.one.id, self.two.id], 'status': 'done'})
        self.assertEqual(code, 200, body)
        self.assertEqual(body['updated'], [self.one.id])
        self.assertEqual(body['skipped'][0]['reason'], 'blocked_by_dependencies')

    def test_a_due_date_outside_the_project_dates_skips_that_task(self):
        code, body = self.bulk({'ids': [self.one.id], 'due_date': self.after_deadline})
        self.assertEqual(code, 200, body)
        self.assertEqual(body['skipped'][0]['reason'], 'task_after_project_deadline')

    def test_an_invalid_shared_value_refuses_the_whole_request(self):
        code, _ = self.bulk({'ids': [self.one.id], 'priority': 'nope'})
        self.assertEqual(code, 400)
        self.one.refresh_from_db()
        self.assertEqual(self.one.priority, 'medium')


class TaskDeleteTests(PMTestCase):
    """GAP-2: deleting a task, from either login."""

    def test_dashboard_delete_reports_the_cascade(self):
        task = self.task(title='Doomed')
        Subtask.objects.create(task=task, title='Sub')
        code, body = self.call(deletes.delete_task_manual, self.dash, method='delete',
                               task_id=task.id)
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data']['deleted'], {'subtasks': 1})
        self.assertFalse(Task.objects.filter(pk=task.pk).exists())

    def test_a_missing_task_is_a_404_not_a_500(self):
        """Audit NEW-3: the handler caught the wrong exception."""
        code, _ = self.call(deletes.delete_task_manual, self.dash, method='delete',
                            task_id=999999999)
        self.assertEqual(code, 404)

    def test_another_companys_task_cannot_be_deleted(self):
        foreign = Task.objects.create(project=self.rival_project, title='Theirs')
        code, _ = self.call(deletes.delete_task_manual, self.dash, method='delete',
                            task_id=foreign.id)
        self.assertEqual(code, 404)
        self.assertTrue(Task.objects.filter(pk=foreign.pk).exists())

    def test_employee_manager_can_delete_a_task(self):
        task = self.task(title='Doomed')
        code, body = self.call(deletes.delete_project_manager_task, self.pm,
                               method='delete', task_id=task.id)
        self.assertEqual(code, 200, body)

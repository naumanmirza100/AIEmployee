"""Creating, editing and deleting projects, in all three API families.

The families share one implementation (project_manager_agent.services), so
most rules are checked once, in the family whose screen uses them, plus a
cross-check where the families used to disagree.
"""
from api.views import company_projects_tasks as company
from api.views import pm_agent as dashboard
from api.views import pm_deletes as deletes
from api.views import user_project_manager as employee
from core.models import Project, Subtask, Task

from .base import PMTestCase


class DashboardCreateTests(PMTestCase):
    """POST /api/project-manager/projects/create"""

    def create(self, data, actor=None):
        return self.call(dashboard.create_project_manual, actor or self.dash, data)

    def test_minimal_project_belongs_to_the_company(self):
        code, body = self.create({'name': 'Alpha'})
        self.assertEqual(code, 201, body)
        project = Project.objects.get(pk=body['data']['id'])
        self.assertEqual(project.company_id, self.company.id)
        self.assertEqual(project.created_by_company_user_id, self.dash.id)

    def test_all_fields_are_stored(self):
        code, body = self.create({
            'name': 'Beta', 'description': ' spaced ', 'status': 'active', 'priority': 'urgent',
            'project_type': 'website', 'industry_id': self.industry.id,
            'budget_min': '100', 'budget_max': '2500.50',
            'start_date': self.inside, 'deadline': self.after_deadline,
        })
        self.assertEqual(code, 201, body)
        project = Project.objects.get(pk=body['data']['id'])
        self.assertEqual(project.industry_id, self.industry.id)
        self.assertEqual(str(project.budget_max), '2500.50')
        self.assertEqual(project.description, 'spaced')

    def test_invalid_status_is_refused_and_nothing_is_saved(self):
        code, body = self.create({'name': 'Rejected', 'status': 'nope'})
        self.assertEqual(code, 400)
        self.assertIn('Invalid status', body['message'])
        self.assertFalse(Project.objects.filter(name='Rejected').exists())

    def test_budget_min_above_max_is_refused(self):
        code, body = self.create({'name': 'X', 'budget_min': 50, 'budget_max': 10})
        self.assertEqual(code, 400, body)

    def test_unreadable_deadline_is_refused(self):
        code, body = self.create({'name': 'X', 'deadline': '31/01/2027'})
        self.assertEqual(code, 400)
        self.assertIn('YYYY-MM-DD', body['message'])

    def test_blank_name_is_refused(self):
        code, _ = self.create({'name': '   '})
        self.assertEqual(code, 400)

    def test_over_long_name_is_a_400_not_a_database_error(self):
        code, body = self.create({'name': 'x' * 201})
        self.assertEqual(code, 400, body)

    def test_duplicate_name_asks_for_confirmation(self):
        code, body = self.create({'name': 'website rebuild'})  # case-insensitive
        self.assertEqual(code, 409)
        self.assertEqual(body['code'], 'duplicate_project_name')
        self.assertEqual(body['data']['existing_project_id'], self.project.id)
        self.assertEqual(Project.objects.filter(company=self.company).count(), 2)

    def test_confirmed_duplicate_is_created(self):
        code, body = self.create({'name': 'Website rebuild', 'confirm_duplicate_name': True})
        self.assertEqual(code, 201, body)

    def test_the_string_false_is_not_a_confirmation(self):
        code, _ = self.create({'name': 'Website rebuild', 'confirm_duplicate_name': 'false'})
        self.assertEqual(code, 409)

    def test_another_companys_project_name_is_free(self):
        code, body = self.create({'name': 'Their project'})
        self.assertEqual(code, 201, body)


class CompanyUpdateTests(PMTestCase):
    """PUT /api/company/projects/<id>/update"""

    def update(self, data, project=None, actor=None):
        return self.call(company.update_company_project, actor or self.dash, data,
                         method='put', project_id=(project or self.project).id)

    def test_fields_are_saved_and_reported(self):
        code, body = self.update({
            'name': 'Renamed', 'status': 'active', 'deadline': '2027-02-28',
            'budget_min': 10, 'budget_max': 20, 'industry_id': self.industry.id})
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data']['name'], 'Renamed')
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, 'Renamed')
        self.assertEqual(str(self.project.effective_deadline)[:10], '2027-02-28')

    def test_invalid_status_saves_nothing(self):
        code, body = self.update({'name': 'Half applied', 'status': 'nope'})
        self.assertEqual(code, 400)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, 'Website rebuild')

    def test_unreadable_deadline_saves_nothing(self):
        """Audit bug 1: this used to save the raw string, then report failure."""
        code, _ = self.update({'deadline': 'next thursday'})
        self.assertEqual(code, 400)
        self.project.refresh_from_db()
        self.assertEqual(self.project.effective_deadline, self.deadline)

    def test_deadline_can_be_cleared(self):
        code, body = self.update({'deadline': ''})
        self.assertEqual(code, 200, body)
        self.project.refresh_from_db()
        self.assertIsNone(self.project.effective_deadline)

    def test_a_colleagues_project_is_editable(self):
        """Audit bug 6: scope is the company, not whoever created the row."""
        code, body = self.update({'name': 'Edited by colleague'}, project=self.colleague_project)
        self.assertEqual(code, 200, body)

    def test_another_companys_project_is_not_found(self):
        code, body = self.update({'name': 'Stolen'}, project=self.rival_project)
        self.assertEqual(code, 404)
        self.assertIn('not found', body['message'].lower())
        self.rival_project.refresh_from_db()
        self.assertEqual(self.rival_project.name, 'Their project')


class EmployeeProjectTests(PMTestCase):
    """/api/user/project-manager/projects/…"""

    def create(self, data, actor=None):
        return self.call(employee.create_project_manager_project, actor or self.pm, data)

    def test_create_sets_company_owner_and_manager(self):
        """Audit bug 4: the company comes from core.tenancy, not profile.company alone."""
        code, body = self.create({'name': 'Employee project'})
        self.assertEqual(code, 201, body)
        project = Project.objects.get(pk=body['data']['id'])
        self.assertEqual(project.company_id, self.company.id)
        self.assertEqual(project.owner_id, self.pm.id)
        self.assertEqual(project.project_manager_id, self.pm.id)

    def test_budget_and_industry_are_accepted(self):
        code, body = self.create({'name': 'With budget', 'budget_min': 5, 'budget_max': 9,
                                  'industry_id': self.industry.id})
        self.assertEqual(code, 201, body)
        project = Project.objects.get(pk=body['data']['id'])
        self.assertEqual(project.industry_id, self.industry.id)

    def test_duplicate_name_asks_for_confirmation(self):
        code, body = self.create({'name': 'Website rebuild'})
        self.assertEqual(code, 409)
        self.assertEqual(body['code'], 'duplicate_project_name')

    def test_project_manager_role_is_required(self):
        code, body = self.create({'name': 'By a developer'}, actor=self.dev)
        self.assertEqual(code, 403)
        self.assertIn('project manager', body['message'].lower())

    def test_invalid_project_type_is_refused(self):
        code, _ = self.create({'name': 'X', 'project_type': 'nope'})
        self.assertEqual(code, 400)

    def test_cannot_edit_an_unrelated_project(self):
        code, body = self.call(employee.update_project_manager_project, self.other_pm,
                               {'name': 'Not mine'}, method='put',
                               project_id=self.colleague_project.id)
        self.assertEqual(code, 403, body)
        self.colleague_project.refresh_from_db()
        self.assertEqual(self.colleague_project.name, 'Colleague project')

    def test_can_edit_a_project_where_they_have_a_task(self):
        self.task(project=self.colleague_project, title='Mine', assignee=self.other_pm)
        code, body = self.call(employee.update_project_manager_project, self.other_pm,
                               {'name': 'Renamed by assignee'}, method='put',
                               project_id=self.colleague_project.id)
        self.assertEqual(code, 200, body)


class ProjectDeleteTests(PMTestCase):
    """GAP-2: every family can delete, and says what the cascade removed."""

    def test_dashboard_delete_reports_what_it_removed(self):
        task = self.task(project=self.colleague_project)
        Subtask.objects.create(task=task, title='Sub')
        code, body = self.call(dashboard.delete_project_manual, self.dash, method='delete',
                               project_id=self.colleague_project.id)
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data']['deleted'], {'tasks': 1, 'subtasks': 1})
        self.assertFalse(Project.objects.filter(pk=self.colleague_project.pk).exists())
        self.assertFalse(Task.objects.filter(pk=task.pk).exists())

    def test_cannot_delete_another_companys_project(self):
        code, _ = self.call(dashboard.delete_project_manual, self.dash, method='delete',
                            project_id=self.rival_project.id)
        self.assertEqual(code, 404)
        self.assertTrue(Project.objects.filter(pk=self.rival_project.pk).exists())

    def test_employee_delete_requires_manager_or_owner(self):
        code, _ = self.call(deletes.delete_project_manager_project, self.other_pm,
                            method='delete', project_id=self.project.id)
        self.assertEqual(code, 403)
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())

    def test_employee_manager_can_delete(self):
        code, body = self.call(deletes.delete_project_manager_project, self.pm,
                               method='delete', project_id=self.project.id)
        self.assertEqual(code, 200, body)
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())

"""HR workflow steps that only pretended now ask a person; new steps alert and create tasks (CO-74, found 5 Oct 2026).

"Provision account" and "Assign training" wrote a log line and reported done; no step could raise a bell alert or make
a Project Manager task.
"""
from core.models import CompanyModulePurchase, Project, Task
from hr_agent.workflow_engine import STEP_HANDLERS
from project_manager_agent.models import PMNotification

from .base import HRTestCase


class StepTests(HRTestCase):

    def ctx(self):
        return {'company_id': self.company.id, 'employee_id': self.member_emp.id}

    def bell(self, login):
        return list(PMNotification.objects.filter(company_user=login).values_list('title', flat=True))

    def test_provision_account_asks_hr_admins_and_says_so(self):
        ok, result, _ = STEP_HANDLERS['provision_account']({'systems': ['Google Workspace', 'Slack']}, self.ctx(), False)
        self.assertTrue(ok and result['needs_a_person'])
        self.assertIn('To do: Set up accounts for Mo Member: Google Workspace, Slack.', self.bell(self.admin))
        self.assertNotIn('placeholder', str(result))

    def test_notify_reaches_hr_admins_and_nobody_to_tell_fails(self):
        ok, result, _ = STEP_HANDLERS['notify']({'to': 'hr_admins', 'title': 'Welcome {{employee.first_name}}'},
                                                self.ctx(), False)
        self.assertTrue(ok)
        self.assertIn('Welcome Mo', self.bell(self.admin))
        ok, result, _ = STEP_HANDLERS['notify']({'to': 'manager', 'title': 'Hi'}, self.ctx(), False)   # no manager
        self.assertFalse(ok)
        self.assertIn('Nobody to tell', result['error'])

    def test_create_task_makes_a_project_manager_task(self):
        CompanyModulePurchase.objects.create(company=self.company, module_name='project_manager_agent',
                                             status='active', is_complimentary=True)
        from core.logins import user_for
        project = Project.objects.create(name='Onboarding', company=self.company, created_by_company_user=self.admin,
                                         owner=user_for(self.admin))
        ok, result, _ = STEP_HANDLERS['create_task']({
            'project_id': project.id, 'title': 'Laptop for {{employee.full_name}}', 'due_in_days': 3}, self.ctx(), False)
        self.assertTrue(ok, result)
        self.assertTrue(Task.objects.filter(project=project, title='Laptop for Mo Member').exists())

    def test_create_task_without_a_project_asks_hr_admins(self):
        ok, result, _ = STEP_HANDLERS['create_task']({'title': 'Order a desk'}, self.ctx(), False)
        self.assertTrue(ok and result['needs_a_person'])
        self.assertIn('To do: Order a desk', self.bell(self.admin))

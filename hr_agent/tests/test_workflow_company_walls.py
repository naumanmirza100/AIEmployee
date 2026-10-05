"""An HR workflow acts inside its own company, and only HR admins shape or run one.

A step can name a record by number, and steps are whatever the person saving
the workflow typed. The engine looked those numbers up with no company check,
so a workflow saved at one company could change another company's employee,
their leave balance or their manager, and send another company's email
template. The run request could also name another company outright. And any
dashboard login could create, edit, delete and run workflows.
"""
from django.core import mail

from api.views import hr_agent as views
from hr_agent.models import HRNotificationTemplate, HRScheduledNotification, HRWorkflow, LeaveBalance

from .base import HRTestCase


class WorkflowCompanyWallTests(HRTestCase):

    def setUp(self):
        super().setUp()
        self.rival_template = HRNotificationTemplate.objects.create(
            company=self.rival, name='Rival secret', subject='Rival plans', body='Rival text', channel='email')
        self.own_template = HRNotificationTemplate.objects.create(
            company=self.company, name='Welcome', subject='Hello', body='Hi {{employee_name}}', channel='email')

    def run_steps(self, steps, **context):
        workflow = HRWorkflow.objects.create(company=self.company, name='Probe', steps=steps)
        code, body = self.call(views.execute_hr_workflow, self.admin, {'context': context}, workflow_id=workflow.id)
        self.assertIn(code, (200, 500), body)
        return body.get('data') or body

    def assertStepRefused(self, data, error):
        results = (data.get('result_data') or {}).get('results') or []
        self.assertNotEqual(data.get('status'), 'completed', data)
        self.assertEqual([r.get('error') for r in results], [error], data)

    def test_a_step_cannot_change_another_companys_employee(self):
        before = self.rival_emp.job_title
        data = self.run_steps([{'type': 'update_employee', 'employee_id': self.rival_emp.id,
                                'fields': {'job_title': 'Hijacked', 'employment_status': 'offboarded'}}])
        self.assertStepRefused(data, 'Employee not found')
        self.rival_emp.refresh_from_db()
        self.assertEqual((self.rival_emp.job_title, self.rival_emp.employment_status), (before, 'active'))

    def test_a_step_cannot_touch_another_companys_leave_balance(self):
        data = self.run_steps([{'type': 'update_leave_balance', 'employee_id': self.rival_emp.id,
                                'delta_used_days': 30}])
        self.assertStepRefused(data, 'Employee not found')
        self.assertFalse(LeaveBalance.objects.filter(employee=self.rival_emp).exists())

    def test_a_step_cannot_set_or_become_a_manager_across_companies(self):
        data = self.run_steps([{'type': 'assign_manager', 'employee_id': self.rival_emp.id,
                                'manager_id': self.admin_emp.id}])
        self.assertStepRefused(data, 'Employee not found')
        data = self.run_steps([{'type': 'assign_manager', 'employee_id': self.member_emp.id,
                                'manager_id': self.rival_emp.id}])
        self.assertStepRefused(data, 'Manager not found')
        data = self.run_steps([{'type': 'update_employee', 'employee_id': self.member_emp.id,
                                'fields': {'manager_id': self.rival_emp.id}}])
        self.assertStepRefused(data, 'Manager not found')
        self.rival_emp.refresh_from_db()
        self.member_emp.refresh_from_db()
        self.assertIsNone(self.rival_emp.manager_id)
        self.assertIsNone(self.member_emp.manager_id)

    def test_a_step_cannot_send_another_companys_template(self):
        for step in ({'type': 'send_email', 'template_id': self.rival_template.id, 'recipient_email': 'me@test.local'},
                     {'type': 'send_email', 'template_name': 'Rival secret', 'recipient_email': 'me@test.local'}):
            self.assertStepRefused(self.run_steps([step]), 'Template not found')
        self.assertEqual(len(mail.outbox), 0)

    def test_naming_another_company_in_the_run_request_changes_nothing(self):
        # Own template by name: found, because the company is the workflow's, not the caller's claim.
        data = self.run_steps([{'type': 'notify_template', 'template_name': 'Welcome',
                                'recipient_email': 'me@test.local'}], company_id=self.rival.id)
        self.assertEqual(data.get('status'), 'completed', data)
        self.assertEqual(HRScheduledNotification.objects.get().company_id, self.company.id)
        # The other company's template stays out of reach however the request is worded.
        data = self.run_steps([{'type': 'notify_template', 'template_id': self.rival_template.id}],
                              company_id=self.rival.id)
        self.assertStepRefused(data, 'Template not found')
        self.assertEqual(HRScheduledNotification.objects.count(), 1)

    def test_the_engine_itself_ignores_a_company_named_in_the_context(self):
        # Events and resumed runs reach the engine without passing through the Run endpoint.
        from hr_agent.workflow_engine import execute_workflow
        workflow = HRWorkflow.objects.create(company=self.company, name='Probe', steps=[
            {'type': 'update_employee', 'employee_id': self.rival_emp.id, 'fields': {'job_title': 'Hijacked'}}])
        ok, _, error = execute_workflow(workflow, {'company_id': self.rival.id}, None)
        self.assertEqual((ok, error), (False, 'Employee not found'))
        self.rival_emp.refresh_from_db()
        self.assertNotEqual(self.rival_emp.job_title, 'Hijacked')

    def test_a_scheduled_notice_never_names_another_companys_employee(self):
        data = self.run_steps([{'type': 'notify_template', 'template_name': 'Welcome',
                                'employee_id': self.rival_emp.id}])
        self.assertEqual(data.get('status'), 'completed', data)
        notice = HRScheduledNotification.objects.get()
        self.assertIsNone(notice.recipient_employee_id)
        self.assertEqual(notice.recipient_email, '')

    def test_the_same_steps_still_work_inside_the_company(self):
        data = self.run_steps([
            {'type': 'update_employee', 'employee_id': self.member_emp.id, 'fields': {'job_title': 'Designer'}},
            {'type': 'assign_manager', 'employee_id': self.member_emp.id, 'manager_id': self.admin_emp.id},
            {'type': 'send_email', 'template_id': self.own_template.id, 'recipient_email': 'mo@test.local'},
        ])
        self.assertEqual(data.get('status'), 'completed', data)
        self.member_emp.refresh_from_db()
        self.assertEqual((self.member_emp.job_title, self.member_emp.manager_id), ('Designer', self.admin_emp.id))
        self.assertEqual(len(mail.outbox), 1)


class WorkflowAdminOnlyTests(HRTestCase):
    """Reading workflows stays open to the company; shaping and running them is for HR admins."""

    def setUp(self):
        super().setUp()
        self.workflow = HRWorkflow.objects.create(company=self.company, name='Welcome pack', steps=[
            {'type': 'update_employee', 'fields': {'job_title': 'Designer'}}])

    def test_an_ordinary_login_cannot_create_edit_delete_or_run(self):
        attempts = [
            (views.create_hr_workflow, 'post', {'name': 'Mine', 'steps': []}, {}),
            (views.update_hr_workflow, 'patch', {'name': 'Renamed'}, {'workflow_id': self.workflow.id}),
            (views.execute_hr_workflow, 'post', {'context': {'employee_id': self.member_emp.id}},
             {'workflow_id': self.workflow.id}),
            (views.execute_hr_workflow, 'post', {'simulate': True}, {'workflow_id': self.workflow.id}),
            (views.delete_hr_workflow, 'delete', None, {'workflow_id': self.workflow.id}),
        ]
        for view, method, payload, kwargs in attempts:
            code, body = self.call(view, self.member, payload, method=method, **kwargs)
            self.assertEqual(code, 403, (view.__name__, body))
        self.workflow.refresh_from_db()
        self.member_emp.refresh_from_db()
        self.assertEqual(self.workflow.name, 'Welcome pack')
        self.assertNotEqual(self.member_emp.job_title, 'Designer')
        self.assertEqual(HRWorkflow.objects.filter(company=self.company).count(), 1)

    def test_an_ordinary_login_can_still_read_them(self):
        code, body = self.call(views.list_hr_workflows, self.member, method='get')
        self.assertEqual(code, 200, body)
        self.assertEqual([w['name'] for w in body['data']], ['Welcome pack'])

    def test_an_hr_admin_can_do_all_four(self):
        code, body = self.call(views.create_hr_workflow, self.admin, {'name': 'New one', 'steps': []})
        self.assertIn(code, (200, 201), body)
        code, body = self.call(views.update_hr_workflow, self.admin, {'name': 'Renamed'}, method='patch',
                               workflow_id=self.workflow.id)
        self.assertEqual(code, 200, body)
        code, body = self.call(views.execute_hr_workflow, self.admin, {'context': {'employee_id': self.member_emp.id}},
                               workflow_id=self.workflow.id)
        self.assertEqual((code, body['data']['status']), (200, 'completed'), body)
        code, body = self.call(views.delete_hr_workflow, self.admin, method='delete', workflow_id=self.workflow.id)
        self.assertEqual(code, 200, body)

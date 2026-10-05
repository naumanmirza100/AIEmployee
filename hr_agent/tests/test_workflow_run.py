"""Running an HR workflow by hand is previewed first.

The Run button started the workflow at once, with no employee — so a step
emailing "the employee" had nobody to email — and nothing showed what it was
about to send or change. The dashboard now asks who it is for, previews each
step (`simulate`), and runs only when confirmed. Also: a "wait for approval"
step crashed every run (it read an undefined variable).
"""
from django.core import mail

from api.views import hr_agent as views
from hr_agent.models import HRNotificationTemplate, HRWorkflow, HRWorkflowExecution

from .base import HRTestCase


class ManualRunTests(HRTestCase):

    def setUp(self):
        super().setUp()
        template = HRNotificationTemplate.objects.create(
            company=self.company, name='Welcome', subject='Welcome {{employee_name}}',
            body='Hi {{employee_name}}', channel='email')
        self.workflow = HRWorkflow.objects.create(company=self.company, name='Welcome pack', steps=[
            {'type': 'send_email', 'template_id': template.id},
            {'type': 'update_employee', 'fields': {'job_title': 'Designer'}},
        ])

    def run_workflow(self, simulate=False, **context):
        return self.call(views.execute_hr_workflow, self.admin, {'context': context, 'simulate': simulate},
                         workflow_id=self.workflow.id)

    def test_the_preview_says_what_each_step_would_do_for_that_person_and_does_nothing(self):
        code, body = self.run_workflow(simulate=True, employee_id=self.member_emp.id)
        self.assertEqual(code, 200, body)
        data = body['data']
        self.assertTrue(data['simulated'] and data['ok'], data)
        email, update = data['result_data']['results']
        self.assertEqual((email['type'], email['recipient']), ('send_email', 'mo@test.local'))
        self.assertEqual((update['type'], update['fields']), ('update_employee', {'job_title': 'Designer'}))
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(HRWorkflowExecution.objects.exists())
        self.member_emp.refresh_from_db()
        self.assertNotEqual(self.member_emp.job_title, 'Designer')

    def test_running_it_for_someone_uses_their_details(self):
        code, body = self.run_workflow(employee_id=self.member_emp.id)
        self.assertEqual((code, body['data']['status']), (200, 'completed'), body)
        self.assertEqual(mail.outbox[0].to, ['mo@test.local'])
        self.assertEqual(mail.outbox[0].subject, 'Welcome Mo Member')
        self.member_emp.refresh_from_db()
        self.assertEqual(self.member_emp.job_title, 'Designer')
        self.assertEqual(HRWorkflowExecution.objects.get().employee_id, self.member_emp.id)

    def test_someone_from_another_company_is_refused(self):
        code, _ = self.run_workflow(simulate=True, employee_id=self.rival_emp.id)
        self.assertEqual(code, 400)

    def test_an_approval_step_pauses_instead_of_crashing(self):
        self.workflow.steps = [{'type': 'wait_for_approval', 'message': 'OK to onboard {{employee_name}}?'}]
        self.workflow.save()
        code, body = self.run_workflow(simulate=True, employee_id=self.member_emp.id)
        self.assertEqual(code, 200, body)
        [step] = body['data']['result_data']['results']
        self.assertEqual(step['approval_request']['message'], 'OK to onboard Mo Member?')
        code, body = self.run_workflow(employee_id=self.member_emp.id)
        self.assertEqual(code, 202, body)
        self.assertEqual(HRWorkflowExecution.objects.get().status, 'awaiting_approval')

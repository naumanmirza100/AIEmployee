"""The HR items from the test report's "Next" list (24 Nov 2026).

- HR 12: "requires approval" on a manual Run. Only an HR admin may run one by hand, and that run is the approval
  (decision D6); it is now recorded, and the dialog says so. A run started by an event still waits.
- HR 13: the manager's part of a review is the employee's manager's now, not whoever it was when the cycle started
  (decision D7).
- HR 14: "Send now" fills {{employee_name}} as the scheduled sender does.
- HR 3: a numeric goal target and a repeated review-cycle name answered 500.
- HR 4: My HR showed the manager as "—".
- Final 2: "My team" said "Failed to load team" to a login with no HR record.
- HR 15: a reporting loop was accepted; an employee's change to an HR-only field came back "success".
"""
from datetime import date, timedelta
from unittest import mock

from api.views import hr_agent as views
from hr_agent.models import (
    Employee, HRNotificationTemplate, HRWorkflow, HRWorkflowExecution, PerformanceReview, PerformanceReviewCycle,
)

from .base import HRTestCase


class ApprovalOnAManualRun(HRTestCase):

    def setUp(self):
        super().setUp()
        self.workflow = HRWorkflow.objects.create(
            company=self.company, name='Laptop request', requires_approval=True,
            steps=[{'type': 'send_email', 'recipient_email': 'it@test.local', 'subject': 'Laptop', 'body': 'Please'}])

    def test_an_hr_admins_run_is_the_approval_and_is_recorded(self):
        with mock.patch('hr_agent.workflow_engine.execute_workflow', return_value=(True, {'results': []}, None)):
            code, body = self.call(views.execute_hr_workflow, self.admin, {'context': {}},
                                   workflow_id=self.workflow.id)
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data']['approved']['by'], 'Dana Admin')
        run = HRWorkflowExecution.objects.get(pk=body['data']['execution_id'])
        self.assertEqual(run.context_data['approved']['how'], 'ran it by hand')

    def test_without_requires_approval_nothing_is_recorded(self):
        HRWorkflow.objects.filter(pk=self.workflow.pk).update(requires_approval=False)
        with mock.patch('hr_agent.workflow_engine.execute_workflow', return_value=(True, {'results': []}, None)):
            code, body = self.call(views.execute_hr_workflow, self.admin, {'context': {}},
                                   workflow_id=self.workflow.id)
        self.assertIsNone(body['data']['approved'])

    def test_nobody_else_may_run_it(self):
        code, _ = self.call(views.execute_hr_workflow, self.member, {'context': {}}, workflow_id=self.workflow.id)
        self.assertEqual(code, 403)


class TheCurrentManagerWritesTheReview(HRTestCase):

    def setUp(self):
        super().setUp()
        self.una = self.login(self.company, 'una@test.local', 'Una Manager', 'manager')
        self.una_emp = self.employee(self.una, 'Una Manager')
        self.fay = self.login(self.company, 'fay@test.local', 'Fay Former', 'manager')
        self.fay_emp = self.employee(self.fay, 'Fay Former')
        cycle = PerformanceReviewCycle.objects.create(company=self.company, name='H2 2026', status='active',
                                                      period_start=date(2026, 7, 1), period_end=date(2026, 12, 31))
        # Fay was Mo's manager when the cycle started; Una is now.
        self.review = PerformanceReview.objects.create(cycle=cycle, employee=self.member_emp, reviewer=self.fay_emp)
        Employee.objects.filter(pk=self.member_emp.pk).update(manager=self.una_emp)

    def write(self, actor):
        return self.call(views.update_perf_review, actor, {'manager_summary': 'Strong quarter.', 'overall_rating': 4},
                         method='patch', review_id=self.review.id)

    def test_the_manager_now_may_write_it_and_becomes_its_reviewer(self):
        code, body = self.write(self.una)
        self.assertEqual(code, 200, body)
        self.review.refresh_from_db()
        self.assertEqual((self.review.manager_summary, self.review.reviewer_id), ('Strong quarter.', self.una_emp.id))

    def test_a_former_manager_may_not(self):
        self.assertEqual(self.write(self.fay)[0], 403)

    def test_with_no_manager_now_the_one_recorded_keeps_it(self):
        Employee.objects.filter(pk=self.member_emp.pk).update(manager=None)
        self.assertEqual(self.write(self.fay)[0], 200)


class SendNowFillsTheTemplate(HRTestCase):

    def test_double_braces_are_filled_and_the_employee_is_found_from_the_address(self):
        template = HRNotificationTemplate.objects.create(
            company=self.company, name='Reminder', channel='email',
            subject='Reminder for {{employee_name}}', body='Hi {{employee_name}}, your title is {{job_title}}.')
        Employee.objects.filter(pk=self.member_emp.pk).update(job_title='Designer')
        with mock.patch('api.views.hr_agent._dispatch_hr_notification', return_value=(True, 'email')) as sent:
            code, body = self.call(views.send_hr_notification_now, self.admin,
                                   {'template_id': template.id, 'recipient_email': 'MO@test.local'})
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data']['rendered_subject'], 'Reminder for Mo Member')
        self.assertEqual(sent.call_args.args[3], 'Hi Mo Member, your title is Designer.')

    def test_an_older_single_brace_template_still_works(self):
        template = HRNotificationTemplate.objects.create(company=self.company, name='Old', channel='email',
                                                         subject='Hello {employee_name}', body='Body')
        with mock.patch('api.views.hr_agent._dispatch_hr_notification', return_value=(True, 'email')):
            code, body = self.call(views.send_hr_notification_now, self.admin,
                                   {'template_id': template.id, 'recipient_employee_id': self.member_emp.id})
        self.assertEqual(body['data']['rendered_subject'], 'Hello Mo Member')


class NoMoreServerErrors(HRTestCase):

    def test_a_numeric_goal_target_is_kept_as_text(self):
        code, body = self.call(views.create_employee_goal, self.admin,
                               {'title': 'Ship v2', 'target_value': 100, 'current_value': 12.5},
                               employee_id=self.member_emp.id)
        self.assertIn(code, (200, 201), body)
        from hr_agent.models import PerformanceGoal
        goal = PerformanceGoal.objects.get(employee=self.member_emp)
        self.assertEqual((goal.target_value, goal.current_value), ('100', '12.5'))

    def test_a_cycle_name_already_used_is_400_not_500(self):
        data = {'name': 'H2 2026', 'period_start': '2026-07-01', 'period_end': '2026-12-31'}
        self.assertEqual(self.call(views.create_review_cycle, self.admin, data)[0], 201)
        code, body = self.call(views.create_review_cycle, self.admin, {**data, 'name': 'h2 2026'})
        self.assertEqual(code, 400, body)
        self.assertIn('already exists', body['message'])


class MyHRAndMyTeam(HRTestCase):

    def test_my_hr_names_the_manager(self):
        Employee.objects.filter(pk=self.member_emp.pk).update(manager=self.admin_emp)
        code, body = self.call(views.get_my_hr_profile, self.member, method='get')
        self.assertEqual((code, body['data']['employee']['manager_name']), (200, 'Dana Admin'))

    def test_my_team_for_a_login_with_no_hr_record_says_so(self):
        owner = self.login(self.company, 'owner@test.local', 'Olive Owner', 'owner')
        code, body = self.call(views.manager_team_summary, owner, method='get')
        self.assertEqual((code, body['code']), (404, 'no_hr_record'))
        self.assertIn('no HR record of its own', body['message'])


class EmployeeRecordChecks(HRTestCase):

    def update(self, actor, employee, data):
        return self.call(views.update_employee, actor, data, method='patch', employee_id=employee.id)

    def test_a_reporting_loop_is_refused(self):
        Employee.objects.filter(pk=self.member_emp.pk).update(manager=self.admin_emp)
        code, body = self.update(self.admin, self.admin_emp, {'manager_id': self.member_emp.id})
        self.assertEqual(code, 400, body)
        self.assertIn('loop', body['message'])
        self.admin_emp.refresh_from_db()
        self.assertIsNone(self.admin_emp.manager_id)

    def test_a_longer_loop_and_their_own_manager_are_refused_too(self):
        una = self.employee(self.login(self.company, 'una@test.local', 'Una', 'manager'), 'Una')
        Employee.objects.filter(pk=self.member_emp.pk).update(manager=una)
        Employee.objects.filter(pk=una.pk).update(manager=self.admin_emp)
        self.assertEqual(self.update(self.admin, self.admin_emp, {'manager_id': self.member_emp.id})[0], 400)
        code, body = self.update(self.admin, self.member_emp, {'manager_id': self.member_emp.id})
        self.assertEqual(code, 400)
        self.assertIn('own manager', body['message'])

    def test_an_employee_changing_an_hr_field_is_told_no(self):
        code, body = self.update(self.member, self.member_emp, {'job_title': 'CTO', 'manager_id': None})
        self.assertEqual(code, 403, body)
        self.assertIn('job title', body['message'])

    def test_the_whole_form_with_only_the_phone_changed_still_saves(self):
        self.member_emp.refresh_from_db()
        form = {'full_name': 'Mo Member', 'job_title': '', 'department': '', 'employment_status': 'active',
                'employment_type': self.member_emp.employment_type, 'start_date': '', 'probation_end_date': '',
                'timezone_name': '', 'phone': '0300 1234567', 'manager_id': None}
        code, body = self.update(self.member, self.member_emp, form)
        self.assertEqual(code, 200, body)
        self.member_emp.refresh_from_db()
        self.assertEqual(self.member_emp.phone, '0300 1234567')

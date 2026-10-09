"""The answer to a leave request reaches the person who asked.

When leave was approved or rejected nobody was told: not in the bell, not by
email. Someone with only a My Space login has no leave screen at all, so being
told is the only way they could learn the answer. A company could build its own
"when leave is approved" workflow, but one started by a leave event ran once
for each employee, ever.
"""
from datetime import date, timedelta

from django.core import mail

from api.views import hr_agent as views
from core.models import Notification
from core.notification_settings import BY_KEY, topic_for_kind
from hr_agent import alerts
from hr_agent.models import HRWorkflow, HRWorkflowExecution, LeaveRequest
from project_manager_agent.models import PMNotification

from .base import HRTestCase


def bell(company_user):
    return list(PMNotification.objects.filter(company_user=company_user).order_by('id'))


def my_space_bell(employee):
    return list(Notification.objects.filter(user=employee.user).order_by('id'))


class LeaveDecidedTests(HRTestCase):

    def setUp(self):
        super().setUp()
        # Sam has only a My Space login. Mo (the member) has a dashboard login.
        self.sam = self.employee_with_login('sam', 'Sam Staff', self.company, self.admin)
        self.day = date(2027, 3, 1)

    def request(self, employee, **fields):
        fields.setdefault('start_date', self.day)
        fields.setdefault('end_date', self.day + timedelta(days=2))
        return self.leave_request(employee, **fields)

    def decide(self, lr, action='approve', actor=None, note=''):
        with self.captureOnCommitCallbacks(execute=True):
            code, body = self.call(views.decide_leave_request, actor or self.admin,
                                   {'action': action, 'note': note}, request_id=lr.id)
        self.assertEqual(code, 200, body)
        return body

    # ---- someone with a dashboard login --------------------------------------------

    def test_an_approval_reaches_the_bell_of_the_person_who_asked(self):
        lr = self.request(self.member_emp)
        PMNotification.objects.all().delete()                      # the "new request" alerts
        self.decide(lr)
        [alert] = bell(self.member)
        self.assertEqual(alert.title, 'Leave approved: 01 Mar – 03 Mar')
        self.assertIn('was approved by Dana Admin', alert.message)
        self.assertIn('Vacation', alert.message)
        self.assertEqual((alert.data['link'], alert.data['kind']),
                         ('/hr/dashboard?tab=leave&view=mine', 'hr_leave_decided'))

    def test_a_rejection_says_so_and_carries_the_note(self):
        lr = self.request(self.member_emp)
        PMNotification.objects.all().delete()
        self.decide(lr, 'reject', note='Release week')
        [alert] = bell(self.member)
        self.assertEqual(alert.title, 'Leave declined: 01 Mar – 03 Mar')
        self.assertIn('was declined by Dana Admin', alert.message)
        self.assertIn('Release week', alert.message)

    def test_nobody_else_is_told(self):
        lr = self.request(self.member_emp)
        PMNotification.objects.all().delete()
        self.decide(lr)
        self.assertEqual(bell(self.admin), [])                      # the person who decided
        self.assertEqual(bell(self.rival_admin), [])
        self.assertEqual(Notification.objects.count(), 0)           # and not twice, in My Space too

    def test_deciding_your_own_request_tells_you_nothing(self):
        lr = self.request(self.admin_emp)
        PMNotification.objects.all().delete()
        self.decide(lr)
        self.assertEqual(bell(self.admin), [])

    # ---- someone with only My Space ------------------------------------------------

    def test_an_employee_with_only_my_space_hears_in_their_bell_and_by_email(self):
        lr = self.request(self.sam)
        self.decide(lr, note='Enjoy')
        [alert] = my_space_bell(self.sam)
        self.assertEqual(alert.title, 'Leave approved: 01 Mar – 03 Mar')
        self.assertIn('was approved by Dana Admin', alert.message)
        self.assertEqual(alert.type, 'hr_leave_decided')
        [sent] = mail.outbox
        self.assertEqual((sent.to, sent.subject), (['sam@test.local'], 'Leave approved: 01 Mar – 03 Mar'))
        self.assertIn('Enjoy', sent.body)

    def test_a_switched_off_dashboard_login_is_not_where_they_are_told(self):
        old = self.login(self.company, 'sam@test.local', 'Sam Staff', 'company_user')
        old.is_active = False
        old.save()
        self.decide(self.request(self.sam))
        self.assertEqual(bell(old), [])
        self.assertEqual(len(my_space_bell(self.sam)), 1)

    def test_someone_with_no_login_at_all_stops_nothing(self):
        from hr_agent.models import Employee
        nobody = Employee.objects.create(company=self.company, full_name='Pat Paper', work_email='pat@elsewhere.example')
        self.decide(self.request(nobody))
        self.assertEqual((Notification.objects.count(), mail.outbox), (0, []))

    # ---- cancelled or withdrawn by someone else ----------------------------------------

    def test_a_request_cancelled_for_them_is_said(self):
        lr = self.request(self.sam)
        with self.captureOnCommitCallbacks(execute=True):
            code, _ = self.call(views.cancel_leave_request, self.admin, {'note': 'Entered twice'}, request_id=lr.id)
        self.assertEqual(code, 200)
        [alert] = my_space_bell(self.sam)
        self.assertEqual(alert.title, 'Leave request cancelled: 01 Mar – 03 Mar')
        self.assertIn('Entered twice', alert.message)

    def test_approved_leave_withdrawn_for_them_is_said(self):
        lr = self.request(self.sam, status='approved')
        with self.captureOnCommitCallbacks(execute=True):
            code, _ = self.call(views.withdraw_leave_request, self.admin, {'reason': 'Project moved'}, request_id=lr.id)
        self.assertEqual(code, 200)
        [alert] = my_space_bell(self.sam)
        self.assertEqual(alert.title, 'Leave withdrawn: 01 Mar – 03 Mar')
        self.assertIn('Project moved', alert.message)
        self.assertNotIn('[withdraw]', alert.message)

    def test_cancelling_your_own_request_tells_you_nothing(self):
        lr = self.request(self.member_emp)
        PMNotification.objects.all().delete()
        code, _ = self.call(views.cancel_leave_request, self.member, {}, request_id=lr.id)
        self.assertEqual(code, 200)
        self.assertEqual(bell(self.member), [])

    def test_a_refused_decision_tells_nobody(self):
        lr = self.request(self.sam)
        code, _ = self.call(views.decide_leave_request, self.member, {'action': 'approve'}, request_id=lr.id)
        self.assertEqual(code, 403)
        self.assertEqual(my_space_bell(self.sam), [])

    def test_a_single_day_is_named_once(self):
        lr = self.request(self.sam, end_date=self.day, days_requested=1)
        self.decide(lr)
        self.assertEqual(my_space_bell(self.sam)[0].title, 'Leave approved: 01 Mar')

    def test_a_request_still_waiting_is_not_a_decision(self):
        self.assertEqual(alerts.leave_decided(self.request(self.sam), decided_by=self.admin), 0)
        self.assertEqual(my_space_bell(self.sam), [])

    # ---- the settings page -----------------------------------------------------------

    def test_it_has_its_own_topic_on_the_settings_page_and_emails_by_default(self):
        topic = topic_for_kind('hr_leave_decided')
        self.assertEqual((topic.key, topic.agent, topic.email_default), ('leave_decisions', 'hr_agent', True))
        self.assertIs(BY_KEY['leave_decisions'], topic)


class LeaveWorkflowRunsTests(HRTestCase):
    """A company's own "when leave is approved" workflow runs for every request."""

    def setUp(self):
        super().setUp()
        self.workflow = HRWorkflow.objects.create(
            company=self.company, name='Tell payroll', is_active=True,
            trigger_conditions={'on': 'leave_request_approved'}, steps=[])

    def runs(self):
        return HRWorkflowExecution.objects.filter(workflow=self.workflow).count()

    def approve(self, lr):
        lr.status = 'approved'
        lr.save()

    def test_it_runs_again_for_the_same_persons_next_leave(self):
        self.approve(self.leave_request(self.member_emp))
        self.assertEqual(self.runs(), 1)
        # It used to be counted by the person, so this one was skipped as a repeat.
        self.approve(self.leave_request(self.member_emp, start_date=date(2027, 6, 1), end_date=date(2027, 6, 2)))
        self.assertEqual(self.runs(), 2)

    def test_but_once_for_one_request_however_often_it_is_saved(self):
        lr = self.leave_request(self.member_emp)
        self.approve(lr)
        lr.save()
        LeaveRequest.objects.get(pk=lr.pk).save()
        self.assertEqual(self.runs(), 1)

    def test_submitted_and_rejected_are_counted_by_the_request_too(self):
        submitted = HRWorkflow.objects.create(company=self.company, name='On submit', is_active=True,
                                              trigger_conditions={'on': 'leave_request_submitted'}, steps=[])
        rejected = HRWorkflow.objects.create(company=self.company, name='On reject', is_active=True,
                                             trigger_conditions={'on': 'leave_request_rejected'}, steps=[])
        for start in (date(2027, 3, 1), date(2027, 6, 1)):
            lr = self.leave_request(self.member_emp, start_date=start, end_date=start)
            lr.status = 'rejected'
            lr.save()
        self.assertEqual(HRWorkflowExecution.objects.filter(workflow=submitted).count(), 2)
        self.assertEqual(HRWorkflowExecution.objects.filter(workflow=rejected).count(), 2)

    def test_a_workflow_about_the_person_is_still_counted_by_the_person(self):
        hired = HRWorkflow.objects.create(company=self.company, name='On leave', is_active=True,
                                          trigger_conditions={'on': 'employee_on_leave'}, steps=[])
        self.member_emp.employment_status = 'on_leave'
        self.member_emp.save()
        self.member_emp.save()
        self.assertEqual(HRWorkflowExecution.objects.filter(workflow=hired).count(), 1)

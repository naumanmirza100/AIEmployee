"""Automations run once per real event, not once per person ever, nor on every save (CO-68, found 5 Oct 2026)."""
from datetime import timedelta

from django.utils import timezone

from hr_agent.models import HRNotificationTemplate, HRScheduledNotification, HRWorkflow, HRWorkflowExecution
from hr_agent.tasks import process_hr_scheduled_notifications

from .base import HRTestCase


class StatusChangeRunsTests(HRTestCase):

    def test_a_second_leave_runs_again_and_a_re_save_does_not(self):
        workflow = HRWorkflow.objects.create(company=self.company, name='On leave', is_active=True,
                                             trigger_conditions={'on': 'employee_on_leave'}, steps=[])
        runs = lambda: HRWorkflowExecution.objects.filter(workflow=workflow).count()
        emp = self.member_emp
        emp.employment_status = 'on_leave'
        emp.save()
        self.assertEqual(runs(), 1)
        emp.job_title = 'Senior'                       # an edit while on leave is not "going on leave" again
        emp.save()
        self.assertEqual(runs(), 1)
        emp.employment_status = 'active'
        emp.save()
        emp.employment_status = 'on_leave'             # the second real time: it used to be skipped for good
        emp.save()
        self.assertEqual(runs(), 2)


class NotificationClaimTests(HRTestCase):

    def test_a_row_another_run_holds_is_not_sent_twice(self):
        template = HRNotificationTemplate.objects.create(company=self.company, name='Hi', channel='email',
                                                         subject='Hi', body='Hello')
        notif = HRScheduledNotification.objects.create(
            company=self.company, template=template, recipient_email='mo@test.local',
            scheduled_at=timezone.now() - timedelta(minutes=1), status='pending')
        HRScheduledNotification.objects.filter(pk=notif.pk).update(next_retry_at=timezone.now() + timedelta(minutes=5))
        process_hr_scheduled_notifications()             # another run has it: this one leaves it
        notif.refresh_from_db()
        self.assertEqual(notif.status, 'pending')
        HRScheduledNotification.objects.filter(pk=notif.pk).update(next_retry_at=None)
        process_hr_scheduled_notifications()
        notif.refresh_from_db()
        self.assertEqual(notif.status, 'sent')

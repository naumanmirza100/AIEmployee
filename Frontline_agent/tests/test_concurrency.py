"""Read-check-write races: only one caller may win (FL-DATA-4, -5, -7).

None of these spawn threads. Each one simulates the loser of a race the way it
actually happens — a second caller holding a stale in-memory copy of a row
another caller has already changed — which is exactly what the conditional
UPDATE is there to catch.
"""
from datetime import timedelta

from api.views import frontline_agent as views
from Frontline_agent.handoff import accept_handoff, trigger_handoff
from Frontline_agent.models import (
    FrontlineWorkflow, FrontlineWorkflowExecution, NotificationTemplate,
    ScheduledNotification, Ticket,
)

from .base import FrontlineTestCase


class HandoffAcceptTests(FrontlineTestCase):
    """FL-DATA-4 — two agents both accepted, both saw it as theirs."""

    def setUp(self):
        super().setUp()
        trigger_handoff(self.ticket, reason='customer_requested', context={})
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.handoff_status, 'pending')

    def test_first_accept_wins(self):
        self.assertTrue(accept_handoff(self.ticket, self.admin_user))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.handoff_status, 'accepted')
        self.assertEqual(self.ticket.handoff_accepted_by_id, self.admin_user.id)

    def test_second_accept_loses_and_does_not_reassign(self):
        stale = Ticket.objects.get(pk=self.ticket.pk)   # the other agent's copy
        self.assertTrue(accept_handoff(self.ticket, self.admin_user))

        self.assertFalse(accept_handoff(stale, self.member_user))

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.handoff_accepted_by_id, self.admin_user.id)
        self.assertEqual(self.ticket.assigned_to_id, self.admin_user.id)

    def test_the_view_answers_409_to_the_loser(self):
        accept_handoff(Ticket.objects.get(pk=self.ticket.pk), self.admin_user)
        code, _ = self.call(views.accept_ticket_handoff, self.member,
                            ticket_id=self.ticket.id)
        self.assertIn(code, (400, 409))


class WorkflowApprovalTests(FrontlineTestCase):
    """FL-DATA-5 — two approvers ran the whole step list twice."""

    def setUp(self):
        super().setUp()
        self.workflow = FrontlineWorkflow.objects.create(
            company=self.company, name='needs approval', steps=[],
            requires_approval=True, is_active=True)
        self.execution = FrontlineWorkflowExecution.objects.create(
            workflow=self.workflow, workflow_name='needs approval',
            executed_by=self.admin_user, status='awaiting_approval', context_data={})

    def test_first_approval_runs_it(self):
        code, body = self.call(views.approve_workflow_execution, self.admin,
                               {'action': 'approve'}, execution_id=self.execution.id)
        self.assertEqual(code, 200, body)

    def test_second_approval_is_refused(self):
        self.call(views.approve_workflow_execution, self.admin,
                  {'action': 'approve'}, execution_id=self.execution.id)
        code, body = self.call(views.approve_workflow_execution, self.member,
                               {'action': 'approve'}, execution_id=self.execution.id)
        self.assertIn(code, (400, 409), body)


class ScheduledNotificationClaimTests(FrontlineTestCase):
    """FL-DATA-7 — overlapping ticks sent the same notification twice."""

    def setUp(self):
        super().setUp()
        self.template = NotificationTemplate.objects.create(
            company=self.company, name='t', subject='Hi', body='Hello', channel='email')
        self.notification = ScheduledNotification.objects.create(
            company=self.company, template=self.template,
            scheduled_at=self.now() - timedelta(minutes=1),
            status='pending', recipient_email='customer@test.local')

    def test_one_tick_sends_it_once(self):
        from django.core import mail
        from Frontline_agent.tasks import process_scheduled_notifications
        mail.outbox = []
        result = process_scheduled_notifications()
        self.assertEqual(result['sent'], 1, result)
        self.assertEqual(len(mail.outbox), 1)
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, 'sent')

    def test_a_second_overlapping_tick_sends_nothing(self):
        from django.core import mail
        from Frontline_agent.tasks import process_scheduled_notifications
        mail.outbox = []
        process_scheduled_notifications()
        second = process_scheduled_notifications()
        self.assertEqual(second['sent'], 0, second)
        self.assertEqual(len(mail.outbox), 1)

    def test_a_claimed_row_is_not_picked_up_again_while_leased(self):
        """The claim pushes next_retry_at forward, so the row drops out of the
        due window until the lease expires."""
        from Frontline_agent.tasks import process_scheduled_notifications
        ScheduledNotification.objects.filter(pk=self.notification.pk).update(
            next_retry_at=self.now() + timedelta(minutes=4))
        result = process_scheduled_notifications()
        self.assertEqual(result['processed'], 0, result)

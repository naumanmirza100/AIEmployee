"""A "ticket updated" rule runs when the ticket changes, not when only its owner or SLA clock does (CO-68)."""
from Frontline_agent.models import FrontlineWorkflow, FrontlineWorkflowExecution

from .base import FrontlineTestCase


class UpdatedRuleTests(FrontlineTestCase):

    def test_a_hand_over_does_not_run_it_and_a_status_change_does(self):
        workflow = FrontlineWorkflow.objects.create(company=self.company, name='On update', is_active=True,
                                                    steps=[], trigger_conditions={'on': 'ticket_updated'})
        runs = lambda: FrontlineWorkflowExecution.objects.filter(workflow=workflow).count()
        ticket = self.ticket
        ticket.assigned_to = self.member_user
        ticket.save()
        self.assertEqual(runs(), 0)
        ticket.status = 'in_progress'
        ticket.save()
        self.assertEqual(runs(), 1)

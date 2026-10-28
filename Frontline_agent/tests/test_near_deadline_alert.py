"""A ticket about to miss its response time tells its owner, or support when nobody has it (CO-62)."""
from datetime import timedelta

from django.utils import timezone

from Frontline_agent.tasks import escalate_near_breach_tickets
from project_manager_agent.models import PMNotification

from .base import FrontlineTestCase


class NearDeadlineTests(FrontlineTestCase):

    def bell(self, login):
        return list(PMNotification.objects.filter(company_user=login).values_list('title', flat=True))

    def test_the_owner_is_told_once(self):
        self.make_ticket(title='Site down', sla_due_at=timezone.now() + timedelta(minutes=30),
                         assigned_to=self.member_user)
        escalate_near_breach_tickets()
        self.assertTrue(any(t.startswith('About to miss its response time: #') and 'Site down' in t
                            for t in self.bell(self.member)), self.bell(self.member))
        self.assertFalse(any('Site down' in t for t in self.bell(self.admin)))
        escalate_near_breach_tickets()                                       # now Urgent: not again
        self.assertEqual(sum('Site down' in t for t in self.bell(self.member)), 1)

    def test_nobody_on_it_tells_support_but_not_for_knowledge_gaps(self):
        self.make_ticket(title='No owner', sla_due_at=timezone.now() + timedelta(minutes=20))
        self.make_ticket(title='Gap', category='knowledge_gap', sla_due_at=timezone.now() + timedelta(minutes=20))
        escalate_near_breach_tickets()
        self.assertTrue(any('No owner' in t for t in self.bell(self.admin)))
        self.assertFalse(any('Gap' in t for t in self.bell(self.admin)))

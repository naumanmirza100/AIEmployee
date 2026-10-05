"""Frontline events that need someone reach the bell of the people who act.

A customer asking for a person, or a ticket given to someone, raised nothing in
the app. (The old template views wrote notifications into a table company
logins never read.)
"""

from api.views import frontline_agent as views
from Frontline_agent.handoff import trigger_handoff
from project_manager_agent.models import PMNotification

from .base import FrontlineTestCase


def bell(company_user):
    return list(PMNotification.objects.filter(company_user=company_user))


class FrontlineAlertTests(FrontlineTestCase):

    # ---- a customer waiting for a person ------------------------------------

    def test_a_hand_off_reaches_the_admins_with_a_link_to_hand_offs(self):
        trigger_handoff(self.ticket, 'customer_requested')
        [alert] = bell(self.admin)
        self.assertIn('Printer on fire', alert.title)
        self.assertIn('asked for a person', alert.message)
        self.assertEqual(alert.data['link'], '/frontline/dashboard?tab=handoffs')
        self.assertEqual(alert.severity, 'warning')

    def test_with_nobody_given_the_support_role_everyone_is_told(self):
        # It used to be the admins alone, which in practice was the founder's login.
        trigger_handoff(self.ticket, 'customer_requested')
        self.assertEqual((len(bell(self.admin)), len(bell(self.member))), (1, 1))

    def test_and_anyone_given_the_frontline_role(self):
        agent = self.dashboard_login(self.company, 'fay@test.local', 'Fay Agent', 'frontline_agent')
        trigger_handoff(self.ticket, 'low_confidence')
        self.assertEqual(len(bell(agent)), 1)
        self.assertEqual(bell(self.member), [])          # an ordinary login isn't paged

    def test_asking_twice_is_one_alert(self):
        trigger_handoff(self.ticket, 'customer_requested')
        trigger_handoff(self.ticket, 'customer_requested')
        self.assertEqual(len(bell(self.admin)), 1)

    def test_other_companies_hear_nothing(self):
        trigger_handoff(self.ticket, 'customer_requested')
        self.assertEqual(bell(self.rival_admin), [])

    # ---- a ticket given to someone ------------------------------------------

    def assign(self, actor, assignee, ticket=None):
        return self.call(views.update_ticket, actor,
                         {'assigned_to_company_user_id': assignee.id},
                         method='patch', ticket_id=(ticket or self.ticket).id)

    def test_assigning_a_ticket_tells_the_assignee(self):
        code, _ = self.assign(self.admin, self.member)
        self.assertEqual(code, 200)
        [alert] = bell(self.member)
        self.assertIn(f'#{self.ticket.id}', alert.title)
        self.assertEqual(alert.data['link'], '/frontline/dashboard?tab=tickets')

    def test_no_alert_for_taking_a_ticket_yourself_or_saving_it_again(self):
        self.assign(self.member, self.member)
        self.assertEqual(bell(self.member), [])
        self.assign(self.admin, self.admin)
        self.assign(self.member, self.admin)       # already theirs: nothing new
        self.assertEqual(bell(self.admin), [])

    def test_a_bulk_assignment_is_one_alert(self):
        more = [self.make_ticket(title=f'Ticket {i}') for i in range(3)]
        code, _ = self.call(views.bulk_update_tickets, self.admin, {
            'ids': [t.id for t in more], 'assigned_to_company_user_id': self.member.id})
        self.assertEqual(code, 200)
        [alert] = bell(self.member)
        self.assertEqual(alert.title, '3 tickets assigned to you')

    def test_passing_on_a_hand_off_tells_the_new_owner(self):
        trigger_handoff(self.ticket, 'customer_requested')
        code, _ = self.call(views.reassign_ticket_handoff, self.admin,
                            {'to_company_user_id': self.member.id}, ticket_id=self.ticket.id)
        self.assertEqual(code, 200)
        self.assertEqual(len([a for a in bell(self.member) if 'assigned to you' in a.title]), 1)

    # ---- reading the bell ----------------------------------------------------

    def test_a_company_without_the_pm_agent_can_read_its_bell(self):
        # The feed used to be reachable only under /project-manager/, which is
        # gated on buying the PM agent: this company (Frontline only) had a
        # bell that could never load.
        trigger_handoff(self.ticket, 'customer_requested')
        client = self.http(self.admin)
        code, body = self.send(client, 'get', '/api/company/notifications')
        self.assertEqual(code, 200, body)
        [alert] = body['data']['notifications']
        self.assertIn('Customer waiting', alert['title'])
        self.assertEqual(alert['link'], '/frontline/dashboard?tab=handoffs')
        code, _ = self.send(client, 'post', '/api/company/notifications/read',
                            {'notification_ids': [alert['id']]})
        self.assertEqual(code, 200)
        self.assertEqual(self.send(client, 'get', '/api/company/notifications')[1]['data']['unread_count'], 0)
        # The PM address stays gated, as before.
        self.assertEqual(self.send(client, 'get', '/api/project-manager/ai/notifications')[0], 403)

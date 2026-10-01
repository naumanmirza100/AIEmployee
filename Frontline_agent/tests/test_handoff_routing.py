"""Who's suggested for a customer waiting for a person.

The hand-off queue showed nobody's availability. Now each waiting hand-off
names the best-placed colleague — free right now on the shared calendar, on
the Frontline team first, then fewest open tickets — with one click to
assign. Nothing is assigned on its own.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from api.views import frontline_agent as views
from core.models import CalendarBlock, UserProfile
from Frontline_agent.handoff import trigger_handoff
from Frontline_agent.models import Ticket
from Frontline_agent.routing import suggest_assignee
from project_manager_agent.models import PMNotification

from .base import FrontlineTestCase


class HandoffRoutingTests(FrontlineTestCase):

    def setUp(self):
        super().setUp()
        self.fay = self.dashboard_login(self.company, 'fay@test.local', 'Fay Frontline', 'frontline_agent')
        self.gus = self.dashboard_login(self.company, 'gus@test.local', 'Gus Frontline', 'frontline_agent')
        self.fay_login = self.login_user_for(self.fay)
        self.gus_login = self.login_user_for(self.gus)

    def open_tickets(self, user, n):
        for i in range(n):
            self.make_ticket(title=f'Load {i}', assigned_to=user, status='open')

    def busy_now(self, company_user, source='pm'):
        # The calendar knows people by their employee login (same email).
        employee = get_user_model().objects.create_user(username=f'emp-{company_user.id}',
                                                        email=company_user.email, password='x')
        UserProfile.objects.update_or_create(user=employee, defaults={'company': self.company,
                                                                       'role': 'team_member'})
        now = timezone.now()
        CalendarBlock.objects.create(company=self.company, user=employee, starts_at=now - timedelta(minutes=10),
                                     ends_at=now + timedelta(minutes=50), source=source, source_id=1,
                                     role='participant', response='accepted', title='Standup')

    def test_the_frontline_team_comes_first(self):
        self.open_tickets(self.fay_login, 3)
        self.open_tickets(self.gus_login, 1)
        best = suggest_assignee(self.company)
        self.assertEqual(best['name'], 'Gus Frontline')          # team, and fewer open tickets
        self.assertIn('on the Frontline team', best['reason'])
        self.assertIn('1 open ticket', best['reason'])

    def test_closed_tickets_dont_count_as_load(self):
        self.open_tickets(self.gus_login, 1)
        self.make_ticket(title='Done', assigned_to=self.fay_login, status='closed')
        self.assertEqual(suggest_assignee(self.company)['name'], 'Fay Frontline')

    def test_someone_in_a_meeting_or_on_leave_right_now_is_skipped(self):
        self.busy_now(self.fay)
        self.busy_now(self.gus, source='leave')
        best = suggest_assignee(self.company)
        self.assertNotIn(best['name'], ('Fay Frontline', 'Gus Frontline'))   # falls back to others

    def test_nobody_free_means_no_suggestion(self):
        for cu in (self.fay, self.gus, self.admin, self.member):
            self.busy_now(cu)
        self.assertIsNone(suggest_assignee(self.company))

    def test_the_queue_suggests_someone_for_each_waiting_hand_off(self):
        trigger_handoff(self.ticket, 'customer_requested')
        code, body = self.call(views.list_handoff_queue, self.admin, method='get')
        self.assertEqual(code, 200)
        [row] = body['data']
        self.assertEqual(row['suggested_assignee']['id'], self.fay.id)    # alphabetical tie-break

    def test_one_click_assigns_it(self):
        trigger_handoff(self.ticket, 'customer_requested')
        suggestion = self.call(views.list_handoff_queue, self.admin, method='get')[1]['data'][0]['suggested_assignee']
        code, _ = self.call(views.reassign_ticket_handoff, self.admin,
                            {'to_company_user_id': suggestion['id']}, ticket_id=self.ticket.id)
        self.assertEqual(code, 200)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.assigned_to, self.fay_login)

    def test_the_alert_names_who_is_best_placed(self):
        trigger_handoff(self.ticket, 'customer_requested')
        alert = PMNotification.objects.filter(company_user=self.admin).first()
        self.assertIn('Best placed: Fay Frontline', alert.message)

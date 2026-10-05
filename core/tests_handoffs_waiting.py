"""A customer waiting for a person is on somebody's list.

When a visitor to the chat widget asks for a person the ticket is filed under
a system account. The logins who act on hand-offs got one bell alert and then
nothing: no reminder, and the ticket was on nobody's My work. Questions the
assistant could not answer were filed the same way and listed nowhere.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import CompanyModulePurchase, CompanyUser
from core.tests_my_work import MyWorkTestCase
from Frontline_agent import alerts
from Frontline_agent.models import Contact, Ticket
from Frontline_agent.tasks import remind_waiting_handoffs
from project_manager_agent.models import PMNotification


class Waiting(MyWorkTestCase):
    # The parent's tests are not run a second time from here.
    locals().update({name: None for name in dir(MyWorkTestCase) if name.startswith('test_')})

    def setUp(self):
        super().setUp()
        self.bot = get_user_model().objects.create(username='frontline_handoff_bot')
        self.agent = CompanyUser.objects.create(company=self.company, email='fay@test.local', full_name='Fay Front',
                                                role='frontline_agent', password_hash='x', is_active=True)

    def waiting(self, company=None, ago=timedelta(minutes=5), **fields):
        company = company or self.company
        fields.setdefault('status', 'new')
        fields.setdefault('handoff_status', 'pending')
        fields.setdefault('handoff_reason', 'customer_requested')
        contact, _ = Contact.objects.get_or_create(company=company, email='vera@customer.test',
                                                   defaults={'name': 'Vera Visitor'})
        return Ticket.objects.create(title='Where is my refund?', description='x', company=company,
                                     created_by=self.bot, assigned_to=self.bot, contact=contact,
                                     handoff_requested_at=timezone.now() - ago, **fields)

    def gap(self, title, **fields):
        fields.setdefault('status', 'new')
        return Ticket.objects.create(title=title, description='x', company=self.company, category='knowledge_gap',
                                     created_by=self.bot, assigned_to=self.bot, **fields)

    def bell(self, who):
        return list(PMNotification.objects.filter(company_user=who).order_by('id').values_list('title', flat=True))


class OnMyWorkTests(Waiting):

    def test_admins_and_frontline_logins_see_the_customer_waiting(self):
        self.waiting()
        for who in (self.admin, self.agent):
            [item] = self.items(who)
            self.assertEqual((item['kind'], item['agent']), ('handoff', 'frontline'))
            self.assertEqual(item['title'], 'Customer waiting for a person: Where is my refund?')
            self.assertEqual((item['link'], item['action']), ('/frontline/dashboard?tab=handoffs', 'Take it'))
            self.assertIn('The customer asked for a person', item['detail'])
            self.assertIn('Vera Visitor', item['detail'])

    def test_a_login_that_is_not_alerted_about_hand_offs_does_not(self):
        self.waiting()
        self.assertEqual(self.items(self.member), [])

    def test_it_is_due_from_the_moment_they_asked_or_at_its_response_time(self):
        asked = self.waiting()
        due_later = self.waiting(sla_due_at=timezone.now() + timedelta(hours=3))
        first, second = self.items(self.admin)
        self.assertEqual(first['key'], f'handoff:{asked.id}')              # already waiting: on top
        self.assertEqual(timezone.datetime.fromisoformat(first['due']), asked.handoff_requested_at)
        self.assertEqual(timezone.datetime.fromisoformat(second['due']), due_later.sla_due_at)

    def test_it_leaves_everyones_list_once_someone_takes_it(self):
        ticket = self.waiting()
        Ticket.objects.filter(pk=ticket.pk).update(handoff_status='accepted', assigned_to=self.agent.login_user,
                                                   status='open')
        self.assertEqual(self.kinds(self.admin), [])

    def test_resolved_or_another_companys_hand_offs_are_not_listed(self):
        self.waiting(status='resolved')
        CompanyModulePurchase.objects.get_or_create(company=self.rival, module_name='frontline_agent',
                                                    defaults={'status': 'active', 'is_complimentary': True})
        self.waiting(company=self.rival)
        self.assertEqual(self.items(self.admin), [])
        self.assertEqual(len(self.items(self.rival_admin)), 1)

    def test_one_raised_on_your_own_ticket_is_listed_once_as_that_ticket(self):
        mine = self.ticket(self.admin, handoff_status='pending', handoff_reason='manual_escalation',
                           handoff_requested_at=timezone.now())
        self.assertEqual(self.kinds(self.admin), ['ticket'])
        self.assertEqual(self.items(self.agent)[0]['key'], f'handoff:{mine.id}')   # a colleague still sees it waiting

    def test_unanswered_widget_questions_are_one_line_however_many(self):
        self.gap('KB gap: Do you ship to Canada?')
        self.gap('KB gap: Can I pay by invoice?')
        self.gap('KB gap: answered already', status='closed')
        [item] = self.items(self.admin)
        self.assertEqual((item['kind'], item['title']), ('knowledge_gaps', "2 questions the assistant couldn't answer"))
        self.assertIn('Can I pay by invoice?', item['detail'])
        self.assertIsNone(item['due'])
        self.assertEqual(self.items(self.member), [])

    def test_a_gap_given_to_a_person_is_theirs_and_not_counted(self):
        self.gap('KB gap: Do you ship to Canada?')
        self.ticket(self.admin, category='knowledge_gap')
        kinds = sorted(self.kinds(self.admin))
        self.assertEqual(kinds, ['knowledge_gap', 'knowledge_gaps'])
        gaps = [i for i in self.items(self.admin) if i['kind'] == 'knowledge_gaps'][0]
        self.assertEqual(gaps['title'], "1 question the assistant couldn't answer")


class StillWaitingTests(Waiting):

    def test_nothing_is_repeated_in_the_first_hour(self):
        self.waiting(ago=timedelta(minutes=50))
        self.assertEqual(remind_waiting_handoffs(), {'reminded': 0})
        self.assertEqual(self.bell(self.admin), [])

    def test_after_an_hour_the_people_who_act_are_told_again(self):
        self.waiting(ago=timedelta(minutes=75))
        self.assertEqual(remind_waiting_handoffs(), {'reminded': 1})
        for who in (self.admin, self.agent):
            self.assertEqual(self.bell(who), ['Still waiting for a person (1 h 15 min): Where is my refund?'])
        self.assertEqual(self.bell(self.member), [])
        note = PMNotification.objects.filter(company_user=self.admin).get()
        self.assertEqual((note.severity, note.data['link']), ('critical', '/frontline/dashboard?tab=handoffs'))

    def test_once_an_hour_however_often_the_job_runs(self):
        self.waiting(ago=timedelta(minutes=75))
        remind_waiting_handoffs()
        remind_waiting_handoffs()
        self.assertEqual(len(self.bell(self.admin)), 1)
        later = timezone.now() + timedelta(minutes=61)
        self.assertEqual(alerts.handoffs_still_waiting(now=later), 1)
        self.assertEqual(len(self.bell(self.admin)), 2)

    def test_it_stops_when_someone_takes_it_or_after_a_day(self):
        taken = self.waiting(ago=timedelta(hours=2))
        Ticket.objects.filter(pk=taken.pk).update(handoff_status='accepted')
        self.waiting(ago=timedelta(hours=30))
        self.waiting(ago=timedelta(hours=2), status='closed')
        self.assertEqual(remind_waiting_handoffs(), {'reminded': 0})

    def test_not_for_a_company_whose_frontline_subscription_lapsed(self):
        self.waiting(ago=timedelta(hours=2))
        CompanyModulePurchase.objects.filter(company=self.company, module_name='frontline_agent').update(
            status='cancelled')
        self.assertEqual(remind_waiting_handoffs(), {'reminded': 0})

    def test_the_first_alert_still_goes_out_and_the_context_the_screen_shows_is_kept(self):
        ticket = self.waiting(ago=timedelta(hours=2), handoff_context={'question': 'Refund?'})
        remind_waiting_handoffs()
        ticket.refresh_from_db()
        self.assertEqual(ticket.handoff_context['question'], 'Refund?')
        self.assertIn('reminded_at', ticket.handoff_context)

"""The test report's "Later" list (24 Nov 2026), outside HR: ready for Django 5, Recruitment's prints, the Pilot's extra
tasks (decision D10), Frontline's web pages without bs4, its survey link (decision D22) and a customer not emailed."""
import ast
import os
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.utils import timezone


class ReadyForDjango5(SimpleTestCase):

    def test_no_code_uses_djangos_timezone_utc(self):
        """Removed in Django 5.0: every customer-call email would stop, with no error shown."""
        import re
        for path in ('api/views/frontline_agent.py', 'Frontline_agent/notification_utils.py',
                     'project_manager_agent/ics_generator.py'):
            text = open(os.path.join(settings.BASE_DIR, path), encoding='utf-8').read()
            self.assertIsNone(re.search(r'(?<![\w.])timezone\.utc\b', text), path)

    def test_the_agent_choices_stay_lazy(self):
        from core.models import _LazyAgentChoices
        try:
            from django.utils.choices import BaseChoiceIterator
        except ImportError:                 # Django 4.2
            return
        self.assertTrue(issubclass(_LazyAgentChoices, BaseChoiceIterator))


class RecruitmentLogsInsteadOfPrinting(SimpleTestCase):

    def test_no_print_is_left_in_the_interview_agent(self):
        """A print of "✗" to a file on Windows raised, and the request answered 500."""
        path = os.path.join(settings.BASE_DIR, 'recruitment_agent', 'agents', 'interview_scheduling',
                            'interview_scheduling_agent.py')
        tree = ast.parse(open(path, encoding='utf-8').read())
        prints = [n.lineno for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'print']
        self.assertEqual(prints, [])


class ThePilotsExtraTasks(SimpleTestCase):
    """PM 3 (decision D10): asked for exact tasks, the Pilot added 7 to 9 more, all made unless unticked."""

    def test_an_extra_task_is_marked_and_the_card_is_shown(self):
        from project_manager_agent import drafts
        actions = [{'action': 'create_project', 'project_name': 'Shop', 'deadline': '2026-12-31'},
                   {'action': 'create_task', 'task_title': 'Cart', 'due_date': '2026-12-10', 'assignee_id': 1,
                    'extra': False},
                   {'action': 'create_task', 'task_title': 'Load tests', 'due_date': '2026-12-12', 'assignee_id': 1,
                    'extra': True}]
        users = [{'id': 1, 'name': 'Ali'}]
        gaps = drafts.inspect(actions, users)
        extra = {r['title']: r.get('extra') for r in gaps['rows'] if r['action'] == 'create_task'}
        self.assertEqual(list(extra.values()), [False, True])
        self.assertTrue(gaps['needs_input'])

    def test_the_prompt_asks_for_the_listed_tasks_only(self):
        import inspect
        from project_manager_agent.ai_agents import project_pilot_agent
        self.assertIn('LISTED TASKS', inspect.getsource(project_pilot_agent))


class FrontlineWebPageWithoutBs4(SimpleTestCase):

    def test_the_standard_parser_leaves_out_tags_styles_and_scripts(self):
        """Frontline 2: without beautifulsoup4 the page went into the knowledge base as it was."""
        from Frontline_agent.document_processor import DocumentProcessor
        text = DocumentProcessor._html_text('<html><head><style>p{color:red}</style><script>alert(1)</script></head>'
                                            '<body><h1>Refunds</h1><p>Within 30 days &amp; with a receipt.</p></body>')
        self.assertEqual(text, 'Refunds Within 30 days & with a receipt.')


class FrontlineSurveyCloses(TestCase):
    """N9 (decision D22): the link never expired, so anyone holding it could change the rating at any time."""

    def setUp(self):
        from django.contrib.auth.models import User
        from core.models import Company
        from Frontline_agent.models import Ticket, TicketSatisfaction
        company = Company.objects.create(name='Acme', email='acme@test.local')
        user = User.objects.create_user('staff', password='x')
        ticket = Ticket.objects.create(title='Printer', description='Broken', company=company, created_by=user)
        self.survey = TicketSatisfaction.objects.create(ticket=ticket, token='tok-123', sent_at=timezone.now())

    def submit(self):
        from django.test import Client
        return Client().post('/api/frontline/csat/submit', {'token': 'tok-123', 'rating': 4},
                             content_type='application/json')

    def test_it_takes_an_answer_for_14_days_then_closes(self):
        self.assertEqual(self.submit().status_code, 200)
        type(self.survey).objects.filter(pk=self.survey.pk).update(sent_at=timezone.now() - timedelta(days=15))
        response = self.submit()
        self.assertEqual((response.status_code, response.json()['code']), (410, 'survey_closed'))


class ACustomerNotEmailed(TestCase):
    """Frontline 3: the customer's email failing was only logged, and the booking reported success."""

    def test_the_organiser_hears_of_it_in_the_bell(self):
        from django.contrib.auth.models import User
        from core.models import Company, CompanyUser
        from Frontline_agent import meeting_customer
        from Frontline_agent.models import FrontlineMeeting
        company = Company.objects.create(name='Acme', email='acme@test.local')
        user = User.objects.create_user('dana', password='x')
        login = CompanyUser.objects.create(company=company, email='dana@acme.test', full_name='Dana', role='admin',
                                           password_hash='x', is_active=True, login_user=user)
        meeting = FrontlineMeeting.objects.create(title='Onboarding call', company=company, organizer=user,
                                                  scheduled_at=timezone.now() + timedelta(days=1),
                                                  customer_email='cara@customer.example')
        with mock.patch.object(meeting_customer, '_send', side_effect=RuntimeError('SMTP down')), \
             mock.patch('core.notification_utils.notify_company_users') as told, \
             self.captureOnCommitCallbacks(execute=True):
            meeting_customer.tell_customer(meeting, 'booked')
        self.assertEqual(told.call_args[0][0], [login])
        self.assertIn('was not emailed', told.call_args.kwargs['title'])

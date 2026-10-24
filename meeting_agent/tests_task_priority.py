"""Executive Meeting tasks: most urgent first, and AI prioritising that a person can reach.

The priority is stored as a word, and lists were ordered by the word: medium, low, high. High-priority work came
last and was the first left out wherever a list was cut short (CO-165). And AI prioritising had a server side but no
button; when it ran, every suggestion was saved at once, one query per task.
"""
import json
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import meeting_agent as views
from core.models import Company, CompanyModulePurchase, CompanyUser
from meeting_agent.models import ExecutiveTask, MeetingActionItem


class PriorityTests(TestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.company = Company.objects.create(name='Averon', email='averon@test.local')
        CompanyModulePurchase.objects.create(company=self.company, module_name='exec_meeting_agent',
                                             status='active', is_complimentary=True)
        self.hamza = self.login('hamza', 'Hamza Ahmed')
        self.omar = self.login('omar', 'Omar Farooq')

    def login(self, name, full_name):
        return CompanyUser.objects.create(company=self.company, email=f'{name}@averon.test', full_name=full_name,
                                          role='owner', password_hash='x', is_active=True)

    def task(self, title, priority, owner=None, **extra):
        return ExecutiveTask.objects.create(company_user=owner or self.hamza, title=title, priority=priority, **extra)

    def call(self, view, method='post', data=None, actor=None):
        request = getattr(self.factory, method)('/', data or {}, format='json')
        force_authenticate(request, user=actor or self.hamza)
        response = view(request)
        response.render()
        return response.status_code, json.loads(response.content)

    # ---- the order -----------------------------------------------------------------------------------------

    def test_tasks_come_most_urgent_first(self):
        for title, priority in (('Tidy the wiki', 'low'), ('Board pack', 'critical'), ('Budget', 'medium'),
                                ('FinEdge review', 'high')):
            self.task(title, priority)
        self.assertEqual([t.priority for t in ExecutiveTask.objects.filter(company_user=self.hamza)],
                         ['critical', 'high', 'medium', 'low'])
        code, body = self.call(views.task_list, 'get')
        self.assertEqual([t['priority'] for t in body['tasks']], ['critical', 'high', 'medium', 'low'])

    def test_action_items_too(self):
        from meeting_agent.models import ExecutiveMeeting
        from django.utils import timezone
        meeting = ExecutiveMeeting.objects.create(organizer=self.hamza, title='Weekly', scheduled_at=timezone.now())
        for title, priority in (('a', 'low'), ('b', 'high'), ('c', 'medium')):
            MeetingActionItem.objects.create(meeting=meeting, title=title, priority=priority)
        self.assertEqual([a.priority for a in MeetingActionItem.objects.filter(meeting=meeting)],
                         ['high', 'medium', 'low'])

    # ---- AI prioritising -----------------------------------------------------------------------------------

    def suggest(self, suggestions, **data):
        agent = mock.Mock()
        agent.prioritize_tasks.return_value = suggestions
        with mock.patch.object(views, '_get_agent', return_value=agent):
            return self.call(views.task_prioritize_ai, data=data)

    def test_a_preview_suggests_and_saves_nothing(self):
        budget = self.task('Budget', 'low')
        code, body = self.suggest([{'id': budget.id, 'priority': 'critical', 'ai_reasoning': 'Board meets Monday',
                                    'suggested_due_date': '2000-01-01'}], apply=False)
        self.assertEqual((code, body['updated_count']), (200, 0))
        self.assertEqual(body['prioritized'][0]['priority'], 'high')          # 'critical' is shown as high
        self.assertNotEqual(body['prioritized'][0]['suggested_due_date'], '2000-01-01')   # never in the past
        budget.refresh_from_db()
        self.assertEqual(budget.priority, 'low')

    def test_without_preview_it_still_applies_at_once(self):
        budget = self.task('Budget', 'low')
        code, body = self.suggest([{'id': budget.id, 'priority': 'high', 'ai_reasoning': 'Board meets Monday'}])
        budget.refresh_from_db()
        self.assertEqual((body['updated_count'], budget.priority, budget.ai_reasoning), (1, 'high', 'Board meets Monday'))

    def test_applying_saves_only_the_ticked_tasks_of_the_person_asking(self):
        budget, wiki = self.task('Budget', 'low'), self.task('Tidy the wiki', 'low')
        theirs = self.task('Omar’s report', 'low', owner=self.omar)
        code, body = self.call(views.task_prioritize_apply, data={'items': [
            {'id': budget.id, 'priority': 'high', 'ai_reasoning': 'Due before the board', 'suggested_due_date': '2099-01-05'},
            {'id': theirs.id, 'priority': 'high'}]})
        self.assertEqual((code, body['updated_count']), (200, 1))
        for task in (budget, wiki, theirs):
            task.refresh_from_db()
        self.assertEqual((budget.priority, str(budget.due_date)), ('high', '2099-01-05'))
        self.assertEqual((wiki.priority, theirs.priority), ('low', 'low'))

    def test_a_suggested_date_does_not_replace_a_date_already_set(self):
        budget = self.task('Budget', 'low', due_date='2099-03-01')
        self.call(views.task_prioritize_apply, data={'items': [
            {'id': budget.id, 'priority': 'medium', 'suggested_due_date': '2099-01-05'}]})
        budget.refresh_from_db()
        self.assertEqual(str(budget.due_date), '2099-03-01')

    def test_applying_nothing_is_refused(self):
        code, body = self.call(views.task_prioritize_apply, data={'items': []})
        self.assertEqual(code, 400)

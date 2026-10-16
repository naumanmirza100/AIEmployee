"""A task given from Executive Meeting reaches the person it is given to.

The task list and the task page showed a task only to the person who made it. Its
assignee got an email telling them to log in, and could then neither see it nor mark
it done; nothing reached their bell or My work.
"""
import json
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import meeting_agent as views
from core import my_work
from core.models import Company, CompanyModulePurchase, CompanyUser
from meeting_agent.models import ExecutiveTask
from project_manager_agent.models import PMNotification


class GivenTaskTests(TestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.company = Company.objects.create(name='Averon', email='averon@test.local')
        CompanyModulePurchase.objects.create(company=self.company, module_name='exec_meeting_agent',
                                             status='active', is_complimentary=True)
        self.hamza = self.login('hamza', 'Hamza Ahmed', 'owner')
        self.omar = self.login('omar', 'Omar Farooq', 'company_user')
        self.ayesha = self.login('ayesha', 'Ayesha Siddiqui', 'company_user')
        emails = mock.patch.object(views, '_email_login')
        emails.start()
        self.addCleanup(emails.stop)

    def login(self, name, full_name, role):
        return CompanyUser.objects.create(company=self.company, email=f'{name}@averon.test', full_name=full_name,
                                          role=role, password_hash='x', is_active=True)

    def call(self, view, actor, method='get', data=None, **kwargs):
        request = getattr(self.factory, method)('/', data or {}, format='json')
        force_authenticate(request, user=actor)
        response = view(request, **kwargs)
        response.render()
        return response.status_code, json.loads(response.content)

    def give(self, title='Send FinEdge the support response times', to=None, **extra):
        code, body = self.call(views.task_list, self.hamza, 'post', {
            'title': title, 'due_date': '2026-10-23', 'priority': 'high',
            'assignees': [{'id': (to or self.omar).id, 'user_type': 'company_user'}], **extra})
        self.assertEqual(code, 201, body)
        return ExecutiveTask.objects.get(pk=body['task']['id'])

    def listed(self, who):
        code, body = self.call(views.task_list, who)
        self.assertEqual(code, 200, body)
        return {t['title']: t for t in body['tasks']}

    def bell(self, who):
        return list(PMNotification.objects.filter(company_user=who).values_list('title', flat=True))

    def test_the_assignee_sees_the_task_marked_as_given_to_them(self):
        self.give()
        task = self.listed(self.omar)['Send FinEdge the support response times']
        self.assertEqual((task['yours'], task['given_by']), (False, 'Hamza Ahmed'))
        self.assertTrue(self.listed(self.hamza)['Send FinEdge the support response times']['yours'])
        self.assertEqual(self.listed(self.ayesha), {})                    # nobody else sees it

    def test_their_bell_and_my_work_have_it(self):
        task = self.give()
        self.assertEqual(self.bell(self.omar), ['New task: Send FinEdge the support response times'])
        self.assertEqual(self.bell(self.hamza), [])
        [item] = [i for i in my_work.for_company_user(self.omar) if i['agent'] == 'exec']
        self.assertEqual((item['title'], item['detail'], item['due']),
                         (task.title, 'From Hamza Ahmed · To Do', '2026-10-23'))
        self.assertEqual(item['link'], '/exec-meeting/dashboard?tab=tasks')

    def test_the_assignee_moves_the_status_on_and_the_giver_hears(self):
        task = self.give()
        code, body = self.call(views.task_detail, self.omar, 'patch', {'status': 'in_progress'}, task_id=task.id)
        self.assertEqual(code, 200, body)
        task.refresh_from_db()
        self.assertEqual(task.status, 'in_progress')
        self.assertEqual(self.bell(self.hamza),
                         ['Omar Farooq: Send FinEdge the support response times is now In Progress'])

    def test_only_the_giver_may_change_or_delete_it(self):
        task = self.give()
        for method, data in (('patch', {'title': 'Something else'}), ('patch', {'status': 'done', 'priority': 'low'}),
                             ('delete', None)):
            code, _ = self.call(views.task_detail, self.omar, method, data, task_id=task.id)
            self.assertEqual(code, 403, (method, data))
        self.assertTrue(ExecutiveTask.objects.filter(pk=task.pk, title=task.title).exists())
        self.assertEqual(self.call(views.task_detail, self.ayesha, task_id=task.id)[0], 404)

    def test_a_person_added_later_is_told_and_those_already_on_it_are_not_told_again(self):
        task = self.give()
        code, _ = self.call(views.task_detail, self.hamza, 'patch', {'assignees': [
            {'id': self.omar.id, 'user_type': 'company_user'}, {'id': self.ayesha.id, 'user_type': 'company_user'}]},
            task_id=task.id)
        self.assertEqual(code, 200)
        self.assertEqual(len(self.bell(self.omar)), 1)
        self.assertEqual(self.bell(self.ayesha), [f'New task: {task.title}'])

    def test_a_subtask_given_alone_is_listed_and_one_under_their_own_task_is_not_listed_twice(self):
        parent = self.give('Prepare the renewal', to=self.ayesha)
        self.give('Collect uptime figures', to=self.omar, parent_task_id=parent.id)
        self.assertIn('Collect uptime figures', self.listed(self.omar))
        parent.assignees.add(self.omar)
        listed = self.listed(self.omar)
        self.assertNotIn('Collect uptime figures', listed)
        self.assertIn('Collect uptime figures', [s['title'] for s in listed['Prepare the renewal']['subtasks']])

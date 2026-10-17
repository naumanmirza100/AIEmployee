"""An action item keeps the person the notes say does it, and a task made from it goes to them.

The note-taker was asked who does each item, and the answer was dropped: no item had an owner,
and "Convert to task" made a task given to nobody, so the person never heard of it.
"""
import json
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import meeting_agent as views
from core.models import Company, CompanyUser
from meeting_agent.models import ExecutiveMeeting, ExecutiveTask
from project_manager_agent.models import PMNotification


class ActionItemOwnerTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local', timezone_name='Asia/Karachi')
        self.hamza = CompanyUser.objects.create(company=self.company, email='hamza@test.local', full_name='Hamza Ahmed',
                                                role='owner', password_hash='x', is_active=True)
        self.omar = CompanyUser.objects.create(company=self.company, email='omar@test.local', full_name='Omar Farooq',
                                               role='frontline_agent', password_hash='x', is_active=True)
        self.meeting = ExecutiveMeeting.objects.create(organizer=self.hamza, title='FinEdge account review',
                                                       scheduled_at=timezone.now() - timedelta(hours=2))

    def call(self, view, method='get', body=None, **kwargs):
        factory = APIRequestFactory()
        request = getattr(factory, method)('/', body or {}, format='json')
        force_authenticate(request, user=self.hamza)
        response = view(request, **kwargs)
        response.render()
        return response, json.loads(response.content)

    def notes(self, items):
        fake = mock.Mock()
        fake.process_full_transcript.return_value = {
            'summary': 'Reviewed sprint 3.', 'key_decisions': [], 'followup_email': '', 'action_items': items}
        with mock.patch.object(views, '_get_agent', return_value=fake):
            response, body = self.call(views.meeting_notes, 'post', {'transcript': 'Hamza: ... Omar: ...'},
                                       meeting_id=self.meeting.id)
        self.assertEqual(response.status_code, 200, body)

    def test_each_item_keeps_its_owner_and_a_login_is_found_by_name(self):
        self.notes([{'title': 'Send the September support response times', 'assignee_hint': 'Omar'},
                    {'title': 'Fix the two login security issues', 'assignee_hint': 'Faizan Malik'},
                    {'title': 'Book the renewal call', 'assignee_hint': 'null'}])
        _, body = self.call(views.meeting_notes, meeting_id=self.meeting.id)
        owners = {a['title']: (a['assignee_id'], a['assignee_name'], a['owner_name']) for a in body['notes']['action_items']}
        self.assertEqual(owners, {
            'Send the September support response times': (self.omar.id, 'Omar Farooq', 'Omar'),
            'Fix the two login security issues': (None, '', 'Faizan Malik'),   # no login: the name is kept
            'Book the renewal call': (None, '', ''),
        })

    def test_a_task_made_from_an_item_goes_to_its_owner_who_is_told(self):
        self.notes([{'title': 'Send the September support response times', 'assignee_hint': 'Omar Farooq'}])
        item = self.meeting.action_items.get()
        with mock.patch.object(views, '_send_task_assignment_email') as email:
            response, body = self.call(views.action_item_convert_to_task, 'post', item_id=item.id)
        self.assertEqual(response.status_code, 201, body)
        task = ExecutiveTask.objects.get(title=item.title)
        self.assertEqual(list(task.assignees.all()), [self.omar])
        self.assertEqual([a['full_name'] for a in body['task']['assignees']], ['Omar Farooq'])
        email.assert_called_once()
        self.assertTrue(PMNotification.objects.filter(title=f'New task: {item.title}').exists())

    def test_an_item_with_no_login_makes_a_task_for_nobody_as_before(self):
        self.notes([{'title': 'Fix the two login security issues', 'assignee_hint': 'Faizan'}])
        item = self.meeting.action_items.get()
        response, body = self.call(views.action_item_convert_to_task, 'post', item_id=item.id)
        self.assertEqual(response.status_code, 201, body)
        self.assertFalse(ExecutiveTask.objects.get(title=item.title).assignees.exists())

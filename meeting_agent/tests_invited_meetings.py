"""A dashboard login invited to an executive meeting sees it, and can reply to it but not change it (CO-65).

The meeting list showed only meetings the caller arranged. An invitee got an email telling them to log in, and then
could not find the meeting or answer it from any screen.
"""
from datetime import timedelta
import json
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import meeting_agent as views
from core.models import Company, CompanyModulePurchase, CompanyUser
from meeting_agent.models import ExecutiveMeeting, ExecutiveMeetingParticipant


class InvitedMeetingTests(TestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.company = Company.objects.create(name='Averon', email='averon@test.local')
        CompanyModulePurchase.objects.create(company=self.company, module_name='exec_meeting_agent',
                                             status='active', is_complimentary=True)
        self.hamza = self.login('hamza', 'Hamza Ahmed', 'owner')
        self.omar = self.login('omar', 'Omar Farooq', 'company_user')
        self.sara = self.login('sara', 'Sara Malik', 'company_user')
        self.meeting = ExecutiveMeeting.objects.create(
            organizer=self.hamza, title='FinEdge account review', status='scheduled',
            scheduled_at=timezone.now() + timedelta(days=2), duration_minutes=45)
        ExecutiveMeetingParticipant.objects.create(meeting=self.meeting, company_user=self.omar)
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

    def listed(self, who):
        code, body = self.call(views.meeting_list, who)
        self.assertEqual(code, 200, body)
        return {m['title']: m for m in body['meetings']}

    def test_the_invitee_sees_the_meeting_as_invited(self):
        meeting = self.listed(self.omar)['FinEdge account review']
        self.assertFalse(meeting['mine'])
        self.assertEqual(meeting['my_response'], 'pending')
        self.assertEqual(meeting['organizer_name'], 'Hamza Ahmed')
        self.assertTrue(self.listed(self.hamza)['FinEdge account review']['mine'])

    def test_someone_not_invited_does_not_see_it(self):
        self.assertEqual(self.listed(self.sara), {})

    def test_the_invitee_replies_and_the_list_shows_it(self):
        code, _ = self.call(views.meeting_respond, self.omar, 'post', {'response': 'accepted'},
                            meeting_id=self.meeting.id)
        self.assertEqual(code, 200)
        self.assertEqual(self.listed(self.omar)['FinEdge account review']['my_response'], 'accepted')

    def test_the_invitee_can_read_but_not_change_or_cancel_it(self):
        code, _ = self.call(views.meeting_detail, self.omar, meeting_id=self.meeting.id)
        self.assertEqual(code, 200)
        code, body = self.call(views.meeting_detail, self.omar, 'patch', {'title': 'Moved'},
                               meeting_id=self.meeting.id)
        self.assertEqual(code, 403)
        self.assertIn('Only Hamza Ahmed, who arranged this meeting, can change or cancel it', body['message'])
        code, _ = self.call(views.meeting_detail, self.omar, 'delete', meeting_id=self.meeting.id)
        self.assertEqual(code, 403)
        self.meeting.refresh_from_db()
        self.assertEqual((self.meeting.title, self.meeting.status), ('FinEdge account review', 'scheduled'))

    def test_someone_not_invited_cannot_open_it(self):
        code, _ = self.call(views.meeting_detail, self.sara, meeting_id=self.meeting.id)
        self.assertEqual(code, 404)

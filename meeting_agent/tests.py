"""An employee added to an executive meeting or task gets a seat, not a login.

Participants and assignees are stored as dashboard logins (CompanyUser). An
employee has none, so adding one creates a row for them. That row used to be an
active login with a random password, and the employee could claim it with
"Forgot password" on the company sign-in page: from there every candidate's CV,
every project and the AI key settings were open to them.
"""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import meeting_agent as views
from core.models import Company, CompanyUser, UserProfile
from meeting_agent.models import ExecutiveMeeting, ExecutiveMeetingParticipant


class EmployeeSeatTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        self.director = CompanyUser.objects.create(
            company=self.company, email='dana@test.local', full_name='Dana Director', role='admin',
            password_hash='x', is_active=True)
        self.sara = self.employee('sara', 'Sara', 'Staff')
        self.meeting = ExecutiveMeeting.objects.create(
            organizer=self.director, title='Quarterly review', scheduled_at=timezone.now() + timedelta(days=2))

    def employee(self, username, first, last, company=None):
        user = get_user_model().objects.create_user(
            username=username, password='x', email=f'{username}@test.local', first_name=first, last_name=last)
        profile, _ = UserProfile.objects.update_or_create(
            user=user, defaults={'company': company or self.company, 'role': 'team_member'})
        return profile

    def call(self, view, data=None, method='post', query='', **kwargs):
        request = getattr(self.factory, method)('/' + query, data or {}, format='json')
        force_authenticate(request, user=self.director)
        response = view(request, **kwargs)
        response.render()
        return response.status_code, json.loads(response.content)

    def add(self, user_id, user_type='profile'):
        return self.call(views.meeting_participants, {'user_id': user_id, 'user_type': user_type},
                         meeting_id=self.meeting.id)

    def seat(self):
        return CompanyUser.objects.filter(company=self.company, email='sara@test.local').first()

    def test_adding_an_employee_gives_them_a_seat_that_is_not_a_login(self):
        code, body = self.add(self.sara.id)
        self.assertEqual(code, 201, body)
        seat = self.seat()
        self.assertFalse(seat.is_active)
        self.assertTrue(ExecutiveMeetingParticipant.objects.filter(meeting=self.meeting, company_user=seat).exists())

    def test_the_employee_cannot_claim_it_with_forgot_password(self):
        self.add(self.sara.id)
        mail.outbox = []
        response = Client().post('/api/company/forgot-password', json.dumps({'email': 'sara@test.local'}),
                                 content_type='application/json')
        self.assertLess(response.status_code, 500)
        seat = self.seat()
        self.assertIsNone(seat.reset_otp)                               # no code was made
        self.assertEqual([m.subject for m in mail.outbox], [])           # and none was sent
        # Even holding a code, the reset and the sign-in both refuse a seat.
        seat.reset_otp, seat.reset_otp_expires = '123456', timezone.now() + timedelta(minutes=10)
        seat.save()
        Client().post('/api/company/reset-password', json.dumps(
            {'email': 'sara@test.local', 'otp': '123456', 'new_password': 'Chosen-by-sara-1'}),
            content_type='application/json')
        login = Client().post('/api/company/login', json.dumps(
            {'email': 'sara@test.local', 'password': 'Chosen-by-sara-1'}), content_type='application/json')
        self.assertNotEqual(login.status_code, 200, login.content[:200])
        self.assertNotIn(b'token', login.content.lower())

    def test_giving_an_employee_a_task_also_makes_only_a_seat(self):
        seats = views._resolve_assignees([{'id': self.sara.id, 'user_type': 'profile'}], self.company)
        self.assertEqual([(s.email, s.is_active) for s in seats], [('sara@test.local', False)])

    def test_adding_them_again_reuses_the_one_seat(self):
        self.add(self.sara.id)
        code, _ = self.add(self.sara.id)
        self.assertEqual(code, 200)
        self.assertEqual(CompanyUser.objects.filter(email='sara@test.local').count(), 1)
        self.assertEqual(ExecutiveMeetingParticipant.objects.filter(meeting=self.meeting).count(), 1)

    def test_a_deactivated_employee_cannot_be_added_or_picked(self):
        get_user_model().objects.filter(pk=self.sara.user_id).update(is_active=False)
        code, _ = self.add(self.sara.id)
        self.assertEqual(code, 404)
        self.assertIsNone(self.seat())
        self.assertEqual(views._resolve_assignees([{'id': self.sara.id, 'user_type': 'profile'}], self.company), [])
        _, body = self.call(views.search_company_users, method='get', query='?all=true')
        self.assertNotIn('sara@test.local', [u['email'] for u in body['users']])

    def test_an_employee_of_another_company_cannot_be_added(self):
        rival = Company.objects.create(name='Rival', email='rival@test.local')
        outsider = self.employee('omar', 'Omar', 'Other', company=rival)
        code, _ = self.add(outsider.id)
        self.assertEqual(code, 404)
        self.assertFalse(CompanyUser.objects.filter(email='omar@test.local').exists())

    def test_the_people_list_shows_the_employee_once_and_never_the_seat(self):
        self.add(self.sara.id)
        _, body = self.call(views.search_company_users, method='get', query='?all=true')
        sara = [u for u in body['users'] if u['email'] == 'sara@test.local']
        self.assertEqual([u.get('user_type') for u in sara], ['profile'])

    def test_a_real_dashboard_login_is_added_as_before(self):
        colleague = CompanyUser.objects.create(
            company=self.company, email='cole@test.local', full_name='Cole Colleague', role='company_user',
            password_hash='x', is_active=True)
        code, body = self.add(colleague.id, user_type='company_user')
        self.assertEqual(code, 201, body)
        colleague.refresh_from_db()
        self.assertTrue(colleague.is_active)

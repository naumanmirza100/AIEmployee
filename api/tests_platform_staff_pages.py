"""The four Executive Meeting pages for the platform's own staff.

They list meetings, tasks and alerts of every company. They signed the caller in
as a company dashboard login and then asked "is this platform staff?" by looking
up the staff account with the same id number. Dashboard logins and staff accounts
are numbered separately, so the answer was about somebody else: a dashboard login
whose number matched a staff account got every company's data, and real staff,
who sign in the other way, were refused.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIRequestFactory, force_authenticate

from api.permissions import IsAdmin
from core.models import Company, CompanyUser, CompanyUserToken
from meeting_agent.models import ExecutiveMeeting

PAGES = ('meetings', 'tasks', 'notifications', 'stats')


class PlatformStaffPagesTests(TestCase):

    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user('ops', email='ops@platform.example', password='x', is_staff=True)
        self.employee = User.objects.create_user('emp', email='emp@acme.example', password='x')

        self.acme = Company.objects.create(name='Acme', email='acme@test.local')
        self.other = Company.objects.create(name='Other', email='other@test.local')
        # A dashboard login that carries the same id number as the staff account.
        self.lookalike = CompanyUser.objects.create(
            id=self.staff.id, company=self.other, email='lena@other.example', full_name='Lena',
            role='admin', password_hash='x', is_active=True)
        organiser = CompanyUser.objects.create(
            company=self.acme, email='omar@acme.example', full_name='Omar', role='admin',
            password_hash='x', is_active=True)
        ExecutiveMeeting.objects.create(organizer=organiser, title='Acme board meeting',
                                        scheduled_at=timezone.now(), duration_minutes=30)

    def get(self, page, key):
        return Client().get(f'/api/admin/exec-meeting/{page}/', HTTP_AUTHORIZATION=f'Token {key}')

    def test_a_dashboard_login_is_refused_even_when_its_number_matches_a_staff_account(self):
        self.assertEqual(self.lookalike.id, self.staff.id)
        key = CompanyUserToken.objects.create(company_user=self.lookalike).key
        for page in PAGES:
            response = self.get(page, key)
            self.assertIn(response.status_code, (401, 403), page)
            self.assertNotIn(b'Acme board meeting', response.content, page)

    def test_platform_staff_can_open_all_four(self):
        key = Token.objects.create(user=self.staff).key
        for page in PAGES:
            self.assertEqual(self.get(page, key).status_code, 200, page)
        self.assertContains(self.get('meetings', key), 'Acme board meeting')

    def test_an_ordinary_employee_login_is_refused(self):
        key = Token.objects.create(user=self.employee).key
        for page in PAGES:
            self.assertEqual(self.get(page, key).status_code, 403, page)

    def test_nobody_signed_in_is_refused(self):
        for page in PAGES:
            self.assertIn(Client().get(f'/api/admin/exec-meeting/{page}/').status_code, (401, 403), page)


class IsAdminTests(TestCase):
    """The permission itself: a dashboard login is never platform staff."""

    def allowed(self, user):
        request = APIRequestFactory().get('/')
        force_authenticate(request, user=user)
        request.user = user
        return IsAdmin().has_permission(request, None)

    def test_a_dashboard_login_is_not_staff_whatever_its_number(self):
        staff = get_user_model().objects.create_user('ops', password='x', is_staff=True)
        company = Company.objects.create(name='Acme', email='acme@test.local')
        login = CompanyUser.objects.create(id=staff.id, company=company, email='a@acme.example', full_name='A',
                                           role='owner', password_hash='x', is_active=True)
        self.assertFalse(self.allowed(login))

    def test_staff_and_superusers_are(self):
        User = get_user_model()
        self.assertTrue(self.allowed(User.objects.create_user('s', password='x', is_staff=True)))
        self.assertTrue(self.allowed(User.objects.create_user('r', password='x', is_superuser=True)))
        self.assertFalse(self.allowed(User.objects.create_user('e', password='x')))

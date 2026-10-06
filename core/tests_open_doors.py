"""Addresses that answered people they should not have.

`/api/projects` was left on "anyone" during testing, and Project Manager keeps
every company's projects in that table. And the old server-rendered site was
still switched on beside the API: its sign-up page gave anyone an account that
could read and change every company's recruitment data. Requests go through
the URLs.
"""
import importlib
import json
import sys
import uuid
from contextlib import contextmanager

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import Resolver404, clear_url_caches, resolve
from rest_framework.authtoken.models import Token

from core.models import Company, CompanyUser, CompanyUserToken, Project


class ProjectListTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.acme = Company.objects.create(name='Acme', email='acme@test.local')
        self.rival = Company.objects.create(name='Rival', email='rival@test.local')
        self.ali = User.objects.create_user(username='ali', password='x', email='ali@test.local')
        self.rita = User.objects.create_user(username='rita', password='x', email='rita@test.local')
        self.staff = User.objects.create_user(username='staff', password='x', email='staff@test.local', is_staff=True)
        Project.objects.create(name='Acme launch', company=self.acme, owner=self.ali)
        Project.objects.create(name='Acme audit', company=self.acme, owner=self.rita, project_manager=self.ali)
        Project.objects.create(name='Rival secret plan', company=self.rival, owner=self.rita)

    def names(self, client):
        response = client.get('/api/projects')
        body = json.loads(response.content) if response.content else {}
        return response.status_code, sorted(p.get('title') or p.get('name') for p in body.get('data', []))

    def as_user(self, user):
        return Client(HTTP_AUTHORIZATION=f'Token {Token.objects.get_or_create(user=user)[0].key}')

    def test_with_no_login_nothing_is_listed(self):
        code, names = self.names(Client())
        self.assertIn(code, (401, 403))
        self.assertEqual(names, [])

    def test_an_employee_sees_the_projects_they_own_or_manage(self):
        self.assertEqual(self.names(self.as_user(self.ali)), (200, ['Acme audit', 'Acme launch']))

    def test_platform_staff_still_see_all(self):
        code, names = self.names(self.as_user(self.staff))
        self.assertEqual((code, len(names)), (200, 3))

    def test_a_dashboard_login_gets_nothing_from_this_old_address(self):
        login = CompanyUser.objects.create(company=self.acme, email='dana@test.local', full_name='Dana Admin',
                                           role='admin', password_hash='x', is_active=True)
        key = CompanyUserToken.objects.get_or_create(company_user=login)[0].key
        code, names = self.names(Client(HTTP_AUTHORIZATION=f'Token {key}'))
        self.assertIn(code, (401, 403))
        self.assertEqual(names, [])


URL_MODULES = ('recruitment_agent.urls', 'marketing_agent.urls', 'project_manager_ai.urls')


def _reload_urls():
    for name in URL_MODULES:
        if name in sys.modules:
            importlib.reload(sys.modules[name])
    clear_url_caches()


@contextmanager
def old_site(enabled):
    """The URL table as it is built with LEGACY_SITE_ENABLED on or off."""
    try:
        with override_settings(LEGACY_SITE_ENABLED=enabled):
            _reload_urls()
            yield
    finally:
        _reload_urls()


OLD_PAGES = [
    '/signup/', '/login/', '/logout/', '/select-role/', '/dashboard/', '/projects/', '/my-tasks/',
    '/recruitment/', '/recruitment/api/interviews/', '/recruitment/api/interviews/7/',
    '/recruitment/api/job-descriptions/', '/recruitment/api/job-descriptions/7/delete/', '/recruitment/api/process/',
    '/frontline/', '/frontline/api/tickets/', '/api/frontline/api/knowledge/',
    '/marketing/', '/marketing/campaigns/', '/marketing/email-accounts/',
]
GONE_FOR_GOOD = ['/recruitment/debug/parsed/7/', '/recruitment/api/interviews/auto-check/']
EMAILED_LINKS = {
    '/recruitment/interview/select/tok123/': 'candidate_select_slot',
    '/recruitment/application/track/tok123/': 'candidate_application_status',
    '/recruitment/api/interview/available-slots/tok123/': 'get_available_slots_for_interview',
    '/recruitment/api/interviews/confirm/': 'confirm_interview_slot',
    '/marketing/track/email/tok123/open/': 'track_email_open',
    '/marketing/track/email/tok123/click/': 'track_email_click',
    '/marketing/token/': 'simple_track_open',
    '/token/': 'root_simple_track_open',
    f'/book/{uuid.uuid4()}/': 'sdr_book_meeting',
}


def routed(path):
    try:
        return resolve(path).url_name
    except Resolver404:
        return None


class OldSiteTests(TestCase):
    def test_the_old_pages_are_off_unless_switched_on(self):
        with old_site(False):
            for path in OLD_PAGES + GONE_FOR_GOOD:
                self.assertIsNone(routed(path), path)
                self.assertEqual(Client().get(path).status_code, 404, path)

    def test_nobody_can_sign_themselves_up(self):
        with old_site(False):
            response = Client().post('/signup/', {'username': 'stranger', 'email': 's@example.test',
                                                  'password1': 'x-Long-enough-1', 'password2': 'x-Long-enough-1',
                                                  'role': 'recruitment_agent'})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(get_user_model().objects.filter(username='stranger').exists())

    def test_the_links_people_get_by_email_still_work(self):
        with old_site(False):
            for path, name in EMAILED_LINKS.items():
                self.assertEqual(routed(path), name, path)
            self.assertEqual(resolve('/admin/login/').url_name, 'login')
            self.assertIsNotNone(routed('/api/health'))

    def test_the_api_address_itself_sends_people_to_the_app(self):
        with old_site(False):
            with override_settings(FRONTEND_URL='https://app.example.test'):
                response = Client().get('/')
                self.assertEqual((response.status_code, response['Location']), (302, 'https://app.example.test'))
            with override_settings(FRONTEND_URL=''):
                response = Client().get('/')
                self.assertEqual((response.status_code, response.json()['status']), (200, 'ok'))

    def test_the_switch_brings_the_old_pages_back_for_local_work(self):
        with old_site(True):
            for path in OLD_PAGES:
                self.assertIsNotNone(routed(path), path)
            for path, name in EMAILED_LINKS.items():
                self.assertEqual(routed(path), name, path)
            for path in GONE_FOR_GOOD:                      # the two debug addresses never come back
                self.assertIsNone(routed(path), path)
        self.assertIsNone(routed('/signup/'))               # and the table is back to normal afterwards


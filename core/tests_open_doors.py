"""Addresses that answered people they should not have.

`/api/projects` was left on "anyone" during testing, and Project Manager keeps
every company's projects in that table. Requests go through the URLs.
"""
import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
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

"""Shared setup for the Project Manager agent tests.

Every test starts with **two companies and both kinds of login**, because
that is where the bugs this suite guards against lived: one company reaching
into another's data, or one API family behaving differently from the other
two. See MDS/PM_AGENT_AUDIT.md.

  dashboard login  (core.CompanyUser)  -> /api/project-manager/, /api/company/
  employee login   (auth.User)         -> /api/user/project-manager/

`call()` runs a view function directly, which is the quickest way to check a
rule. `http()` goes through the URLs, the authentication classes and the
module-purchase middleware, which is the only way to check those.
"""
from __future__ import annotations

import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIRequestFactory, force_authenticate

from core.models import (
    Company, CompanyModulePurchase, CompanyUser, CompanyUserToken, Industry, Project, Task,
    UserProfile,
)


class PMTestCase(TestCase):
    """Two companies, three employees, two dashboard logins, one dated project."""

    factory = APIRequestFactory()

    def setUp(self):
        super().setUp()
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        self.rival = Company.objects.create(name='Rival', email='rival@test.local')

        self.dash = CompanyUser.objects.create(
            company=self.company, email='dana@test.local', full_name='Dana Dash',
            role='company_user')
        self.dash_colleague = CompanyUser.objects.create(
            company=self.company, email='colin@test.local', full_name='Colin Dash',
            role='company_user')
        self.rival_dash = CompanyUser.objects.create(
            company=self.rival, email='rhea@test.local', full_name='Rhea Rival',
            role='company_user')

        self.pm = self.employee('pat', role='project_manager')
        self.other_pm = self.employee('pia', role='project_manager')
        self.dev = self.employee('dev')
        self.rival_pm = self.employee('rob', role='project_manager',
                                      company=self.rival, creator=self.rival_dash)

        self.industry = Industry.objects.create(name='Software')

        today = timezone.now().date()
        self.start = today + timedelta(days=5)
        self.deadline = today + timedelta(days=60)
        self.inside = (today + timedelta(days=20)).isoformat()
        self.after_deadline = (today + timedelta(days=90)).isoformat()
        self.before_start = today.isoformat()

        # The project every test edits. It has both dates, so the due-date
        # bounds rule (D4) has something to check against.
        self.project = Project.objects.create(
            name='Website rebuild', company=self.company, created_by_company_user=self.dash,
            owner=self.pm, project_manager=self.pm,
            start_date=self.start, deadline=self.deadline, end_date=self.deadline)
        # Same company, created by a different dashboard login: a colleague's
        # project must still be editable (audit bug 6).
        self.colleague_project = Project.objects.create(
            name='Colleague project', company=self.company,
            created_by_company_user=self.dash_colleague, owner=self.pm)
        self.rival_project = Project.objects.create(
            name='Their project', company=self.rival,
            created_by_company_user=self.rival_dash, owner=self.rival_pm,
            project_manager=self.rival_pm)

        self.buy_module(self.company)

    # ------------------------------------------------------------------ data

    def employee(self, name, *, role='team_member', company=None, creator=None):
        user = User.objects.create_user(
            username=name, password='x', email=f'{name}@test.local',
            first_name=name.title(), last_name='Tester')
        UserProfile.objects.update_or_create(user=user, defaults={
            'company': company or self.company,
            'created_by_company_user': creator or self.dash,
            'role': role,
        })
        # Reload: a signal caches a UserProfile on the instance it created,
        # and that cached copy would be the pre-update one.
        return User.objects.get(pk=user.pk)

    def buy_module(self, company, module='project_manager_agent'):
        return CompanyModulePurchase.objects.create(
            company=company, module_name=module, status='active', is_complimentary=True)

    def task(self, **fields):
        fields.setdefault('project', self.project)
        fields.setdefault('title', 'A task')
        return Task.objects.create(**fields)

    # ----------------------------------------------------------- calling code

    def call(self, view, actor, data=None, *, method='post', **url_kwargs):
        """Call a view function directly. Returns (status_code, parsed body)."""
        request = getattr(self.factory, method)('/', data or {}, format='json')
        force_authenticate(request, user=actor)
        response = view(request, **url_kwargs)
        response.render()
        body = json.loads(response.content) if response.content else {}
        return response.status_code, body

    def http(self, actor):
        """A client authenticated as `actor`, for going through the URLs."""
        if isinstance(actor, CompanyUser):
            key = CompanyUserToken.objects.get_or_create(company_user=actor)[0].key
        else:
            key = Token.objects.get_or_create(user=actor)[0].key
        return Client(HTTP_AUTHORIZATION=f'Token {key}')

    @staticmethod
    def send(client, method, url, payload=None):
        """JSON request through a test client. Returns (status_code, body)."""
        kwargs = {'content_type': 'application/json'}
        args = (url,) if payload is None else (url, json.dumps(payload))
        response = getattr(client, method)(*args, **kwargs)
        body = json.loads(response.content) if response.content else {}
        return response.status_code, body

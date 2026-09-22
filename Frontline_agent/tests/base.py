"""Shared setup for the Frontline agent tests.

Every test starts with **two companies**, because most of what this suite
guards against was one tenant reaching into another's data. Company A also has
two dashboard logins — an admin and an ordinary member — since the credential
and destructive endpoints are now admin-only (FL-SEC-7).
"""
from __future__ import annotations

import json

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from core.models import Company, CompanyModulePurchase, CompanyUser, CompanyUserToken
from Frontline_agent.models import Ticket


class FrontlineTestCase(TestCase):
    """Two companies, an admin and a member login each, and a ticket."""

    factory = APIRequestFactory()

    def setUp(self):
        super().setUp()
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        self.rival = Company.objects.create(name='Rival', email='rival@test.local')

        self.admin = self.dashboard_login(self.company, 'dana@test.local', 'Dana Admin', 'admin')
        self.member = self.dashboard_login(self.company, 'mo@test.local', 'Mo Member', 'company_user')
        self.rival_admin = self.dashboard_login(self.rival, 'rhea@test.local', 'Rhea Rival', 'admin')

        self.buy_module(self.company)
        self.buy_module(self.rival)

        self.admin_user = self.login_user_for(self.admin)
        self.member_user = self.login_user_for(self.member)
        self.rival_user = self.login_user_for(self.rival_admin)

        self.ticket = self.make_ticket(title='Printer on fire')
        self.rival_ticket = self.make_ticket(
            title='Their problem', company=self.rival, created_by=self.rival_user)

    # ------------------------------------------------------------------ data

    def dashboard_login(self, company, email, full_name, role):
        return CompanyUser.objects.create(
            company=company, email=email, full_name=full_name, role=role,
            password_hash='x', is_active=True,
        )

    def login_user_for(self, company_user):
        """The auth.User a dashboard login acts as (FL-SEC-3 keys this on id)."""
        from api.views.frontline_agent import _get_or_create_user_for_company_user
        return _get_or_create_user_for_company_user(company_user)

    def buy_module(self, company, module='frontline_agent'):
        return CompanyModulePurchase.objects.create(
            company=company, module_name=module, status='active', is_complimentary=True)

    def make_ticket(self, **fields):
        fields.setdefault('title', 'A ticket')
        fields.setdefault('description', 'Something happened')
        fields.setdefault('company', self.company)
        fields.setdefault('created_by', self.admin_user)
        return Ticket.objects.create(**fields)

    # ----------------------------------------------------------- calling code

    def call(self, view, actor, data=None, *, method='post', **url_kwargs):
        """Call a view function directly. Returns (status_code, parsed body)."""
        request = getattr(self.factory, method)('/', data or {}, format='json')
        force_authenticate(request, user=actor)
        response = view(request, **url_kwargs)
        if hasattr(response, 'render'):
            response.render()
        body = {}
        if getattr(response, 'content', b''):
            try:
                body = json.loads(response.content)
            except ValueError:
                body = {'_raw': response.content[:200].decode('utf-8', 'replace')}
        return response.status_code, body

    def http(self, actor):
        """A client authenticated as `actor`, for going through the URLs."""
        key = CompanyUserToken.objects.get_or_create(company_user=actor)[0].key
        return Client(HTTP_AUTHORIZATION=f'Token {key}')

    @staticmethod
    def send(client, method, url, payload=None):
        kwargs = {'content_type': 'application/json'}
        args = (url,) if payload is None else (url, json.dumps(payload))
        response = getattr(client, method)(*args, **kwargs)
        body = {}
        if response.content:
            try:
                body = json.loads(response.content)
            except ValueError:
                body = {'_raw': response.content[:200].decode('utf-8', 'replace')}
        return response.status_code, body

    @staticmethod
    def now():
        return timezone.now()

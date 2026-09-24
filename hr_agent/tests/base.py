"""Shared setup for the HR agent tests.

Two companies, and within the first an **HR admin** and an ordinary
**member** — because the finding this suite mostly exists for is that the
second one used to be able to do everything the first can (HR-SEC-1).
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from core.models import Company, CompanyModulePurchase, CompanyUser, CompanyUserToken
from hr_agent.models import Employee


class HRTestCase(TestCase):
    """Two companies; an admin and a member login, each with an Employee row."""

    factory = APIRequestFactory()

    def setUp(self):
        super().setUp()
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        self.rival = Company.objects.create(name='Rival', email='rival@test.local')

        self.admin = self.login(self.company, 'dana@test.local', 'Dana Admin', 'admin')
        self.member = self.login(self.company, 'mo@test.local', 'Mo Member', 'company_user')
        self.rival_admin = self.login(self.rival, 'rhea@test.local', 'Rhea Rival', 'admin')

        self.buy_module(self.company)
        self.buy_module(self.rival)

        self.admin_emp = self.employee(self.admin, 'Dana Admin')
        self.member_emp = self.employee(self.member, 'Mo Member')
        self.rival_emp = self.employee(self.rival_admin, 'Rhea Rival', company=self.rival)

    # ------------------------------------------------------------------ data

    def login(self, company, email, full_name, role):
        return CompanyUser.objects.create(
            company=company, email=email, full_name=full_name, role=role,
            password_hash='x', is_active=True,
        )

    def employee(self, company_user, full_name, company=None):
        from api.views.hr_agent import _hr_get_or_create_user_for_company_user
        company = company or company_user.company
        return Employee.objects.create(
            company=company,
            company_user=company_user,
            user=_hr_get_or_create_user_for_company_user(company_user),
            full_name=full_name,
            work_email=company_user.email,
            employment_status='active',
        )

    def buy_module(self, company, module='hr_agent'):
        return CompanyModulePurchase.objects.create(
            company=company, module_name=module, status='active', is_complimentary=True)

    def leave_request(self, employee=None, **fields):
        from hr_agent.models import LeaveRequest
        fields.setdefault('leave_type', 'vacation')
        fields.setdefault('start_date', date.today() + timedelta(days=10))
        fields.setdefault('end_date', date.today() + timedelta(days=12))
        fields.setdefault('days_requested', 3)
        fields.setdefault('status', 'pending')
        return LeaveRequest.objects.create(employee=employee or self.member_emp, **fields)

    def balance(self, employee=None, leave_type='vacation', **fields):
        from hr_agent.models import LeaveBalance, leave_year_start
        fields.setdefault('period_start', leave_year_start())
        return LeaveBalance.objects.create(
            employee=employee or self.member_emp, leave_type=leave_type, **fields)

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

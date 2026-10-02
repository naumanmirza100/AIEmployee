"""Who may use the Project Manager agent: any active dashboard login of a
company that has it. Authentication and IsCompanyUserOnly refuse an inactive
login; api.middleware.module_access refuses a company without the agent
(api/tests_module_access.py). Views used to each repeat a role check of their
own, saying "Project manager or company user role required".
"""
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import company_dashboard, pm_agent
from core.models import Company, CompanyUser


class AccessTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')

    def login(self, role, active=True):
        return CompanyUser.objects.create(company=self.company, email=f'{role}@test.local', full_name=role,
                                          role=role, password_hash='x', is_active=active)

    def call(self, view, actor, method='get', data=None):
        factory = APIRequestFactory()
        request = factory.get('/') if method == 'get' else factory.post('/', data or {}, format='json')
        force_authenticate(request, user=actor)
        response = view(request)
        response.render()
        return response.status_code, response.data

    def test_any_role_may_use_it(self):
        for role in ('admin', 'owner', 'recruiter', 'hr_agent', 'company_user'):
            actor = self.login(role)
            code, body = self.call(company_dashboard.project_manager_dashboard, actor)
            self.assertEqual(code, 200, (role, body))
            code, body = self.call(pm_agent.project_pilot_confirm, actor, 'post', {'actions': []})
            self.assertNotEqual(code, 403, (role, body))

    def test_an_inactive_login_may_not(self):
        actor = self.login('admin', active=False)
        self.assertEqual(self.call(company_dashboard.project_manager_dashboard, actor)[0], 403)
        self.assertEqual(self.call(pm_agent.project_pilot_confirm, actor, 'post', {'actions': []})[0], 403)

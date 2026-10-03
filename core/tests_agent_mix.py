"""A company can buy any one agent, or any mix of them.

The pages every login shares (My work, the bell, notification settings, API
keys, the floating chats' history) and the links between agents must work
whatever was bought, and buying one agent must not need another. Requests go
through the URLs, so the subscription check runs as it does live.
"""
import json

from django.test import Client, TestCase

from api.middleware.module_access import PREFIX_TO_MODULE
from core.models import Company, CompanyModulePurchase, CompanyUser, CompanyUserToken
from hr_agent.models import Employee

ALONE = [(module,) for module in PREFIX_TO_MODULE.values()]
MIXES = ALONE + [
    ('operations_agent', 'recruitment_agent'),
    ('frontline_agent', 'hr_agent'),
    ('recruitment_agent', 'project_manager_agent'),
    ('marketing_agent', 'ai_sdr_agent', 'exec_meeting_agent'),
]
SHARED = [
    '/api/company/my-work',
    '/api/company/notifications',
    '/api/company/notification-settings',
    '/api/company/agent-keys',
    '/api/quick-chats?agent=pm&mode=pilot',
    '/api/quick-chats?agent=hr',
    '/api/quick-chats?agent=frontline',
]


class AgentMixTests(TestCase):
    def company_with(self, modules, n=[0]):
        n[0] += 1
        company = Company.objects.create(name=f'Mix {n[0]}', email=f'mix{n[0]}@test.local')
        for module in modules:
            CompanyModulePurchase.objects.create(company=company, module_name=module, status='active',
                                                 is_complimentary=True)
        login = CompanyUser.objects.create(company=company, email=f'admin{n[0]}@test.local', full_name='Ada Admin',
                                           role='admin', password_hash='x', is_active=True)
        key = CompanyUserToken.objects.get_or_create(company_user=login)[0].key
        return company, Client(HTTP_AUTHORIZATION=f'Token {key}')

    @staticmethod
    def blocked(response):
        return response.status_code == 403 and b'subscription_required' in response.content

    def test_shared_pages_work_whatever_was_bought(self):
        for modules in MIXES:
            with self.subTest(bought=modules):
                _, client = self.company_with(modules)
                for url in SHARED:
                    response = client.get(url)
                    self.assertEqual(response.status_code, 200, f'{url}: {response.content[:200]}')

    def test_notification_settings_offer_only_what_was_bought(self):
        for modules in MIXES:
            with self.subTest(bought=modules):
                _, client = self.company_with(modules)
                topics = json.loads(client.get('/api/company/notification-settings').content)['data']['topics']
                self.assertLessEqual({t['agent'] for t in topics}, set(modules) | {'everyone'})

    def test_each_agent_needs_only_itself(self):
        for modules in MIXES:
            with self.subTest(bought=modules):
                _, client = self.company_with(modules)
                for prefix, module in PREFIX_TO_MODULE.items():
                    response = client.get(f'/api/{prefix}/any-page')
                    self.assertEqual(self.blocked(response), module not in modules, prefix)

    def test_hr_alone_can_hand_over_work(self):
        company, client = self.company_with(['hr_agent'])
        boss = Employee.objects.create(company=company, full_name='Bea Boss', work_email='bea@test.local',
                                       employment_status='active')
        Employee.objects.create(company=company, full_name='Rui Report', work_email='rui@test.local',
                                employment_status='active', manager=boss)
        response = client.get(f'/api/hr/employees/{boss.id}/handover')
        self.assertEqual(response.status_code, 200, response.content[:200])
        groups = [g['key'] for g in json.loads(response.content)['data']['groups']]
        self.assertEqual(groups, ['reports'])     # nothing from the agents it doesn't have

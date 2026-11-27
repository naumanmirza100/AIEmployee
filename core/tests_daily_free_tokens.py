"""Usage limits (27 Nov 2026).

A company could use its whole free AI allowance for an agent in one day, and saving the Pricing page overwrote every
company's allowance for that agent, ones an admin had raised by hand too. Now free tokens have a daily cap per
company and agent (the day in UTC), and a new allowance on the Pricing page is for new purchases unless the admin
asks for existing companies too.
"""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from core.api_key_service import DailyQuotaReached, QuotaExhausted, record_usage, resolve_for_call
from core.models import AdminPricingConfig, Agent, AgentTokenQuota, Company, CompanyAPIKey, CompanyModulePurchase, PlatformAPIKey


class DailyCapTests(TestCase):

    def setUp(self):
        Agent.objects.update_or_create(slug='hr_agent', defaults={'name': 'HR Support Agent', 'default_provider': 'openai'})
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        CompanyModulePurchase.objects.create(company=self.company, module_name='hr_agent', status='active',
                                             is_complimentary=True)
        key = PlatformAPIKey(provider='openai', status='active', encrypted_key='')
        key.set_plaintext_key('platform-key-0123456789')
        key.save()
        AdminPricingConfig.objects.update_or_create(agent_name='hr_agent', defaults={'daily_free_tokens': 1000})
        self.quota = AgentTokenQuota.objects.get(company=self.company, agent_name='hr_agent')
        AgentTokenQuota.objects.filter(pk=self.quota.pk).update(included_tokens=1_000_000)

    def use(self, tokens):
        record_usage(resolve_for_call(self.company, 'hr_agent'), tokens)

    def test_free_tokens_stop_for_the_day_at_the_cap(self):
        self.use(600)
        self.use(500)          # was allowed: 600 < 1000 when the call started
        with self.assertRaises(DailyQuotaReached) as caught:
            resolve_for_call(self.company, 'hr_agent')
        self.assertIn("today's free AI allowance (1,000 tokens)", caught.exception.user_message)
        self.assertEqual(caught.exception.reason, 'daily_quota_reached')
        # Everything that handles a used-up allowance handles this too.
        self.assertIsInstance(caught.exception, QuotaExhausted)
        self.quota.refresh_from_db()
        self.assertEqual((self.quota.used_tokens, self.quota.day_used_tokens), (1100, 1100))

    def test_the_next_day_starts_again(self):
        self.use(1200)
        tomorrow = timezone.now() + timedelta(days=1)
        with mock.patch('core.api_key_service.timezone.now', return_value=tomorrow):
            self.use(100)
        self.quota.refresh_from_db()
        self.assertEqual((self.quota.day_date, self.quota.day_used_tokens), (tomorrow.date(), 100))

    def test_no_cap_means_no_daily_limit(self):
        AdminPricingConfig.objects.filter(agent_name='hr_agent').update(daily_free_tokens=0)
        self.use(50_000)
        self.assertEqual(resolve_for_call(self.company, 'hr_agent').mode, 'platform')

    def test_the_companys_own_key_is_never_limited_by_it(self):
        self.use(1200)
        key = CompanyAPIKey(company=self.company, agent_name='hr_agent', mode='byok', provider='openai',
                            status='active', encrypted_key='')
        key.set_plaintext_key('own-key-0123456789')
        key.save()
        AgentTokenQuota.objects.filter(pk=self.quota.pk).update(preferred_pool='byok')
        self.assertEqual(resolve_for_call(self.company, 'hr_agent').mode, 'byok')


class PricingPageTests(TestCase):

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='root', email='root@test.local', password='x',
                                                          is_staff=True, is_superuser=True)
        Agent.objects.update_or_create(slug='hr_agent', defaults={'name': 'HR Support Agent', 'default_provider': 'openai'})
        self.companies = []
        for name in ('Acme', 'Beta'):
            company = Company.objects.create(name=name, email=f'{name.lower()}@test.local')
            CompanyModulePurchase.objects.create(company=company, module_name='hr_agent', status='active',
                                                 is_complimentary=True)
            self.companies.append(company)
        # Beta was given more by hand.
        AgentTokenQuota.objects.filter(company=self.companies[1], agent_name='hr_agent').update(included_tokens=9_000_000)

    def save(self, data):
        from api.views.admin_api_keys import update_pricing
        request = APIRequestFactory().put('/', data, format='json')
        force_authenticate(request, user=self.admin)
        with mock.patch('api.views.admin_api_keys.IsAdmin.has_permission', return_value=True):
            response = update_pricing(request, agent_name='hr_agent')
        response.render()
        return response.status_code, response.data

    def allowances(self):
        return sorted(AgentTokenQuota.objects.filter(agent_name='hr_agent').values_list('included_tokens', flat=True))

    def test_a_new_allowance_is_for_new_purchases(self):
        before = self.allowances()
        status, body = self.save({'free_tokens_on_purchase': 2_000_000})
        self.assertEqual((status, body['applied_to_existing']), (200, 0))
        self.assertEqual(self.allowances(), before)

    def test_existing_companies_change_only_when_asked(self):
        status, body = self.save({'free_tokens_on_purchase': 2_000_000, 'apply_to_existing': True})
        self.assertEqual((status, body['applied_to_existing']), (200, 2))
        self.assertEqual(self.allowances(), [2_000_000, 2_000_000])

    def test_the_daily_cap_is_saved_and_shown(self):
        status, body = self.save({'daily_free_tokens': 250_000})
        self.assertEqual((status, body['pricing']['daily_free_tokens']), (200, 250_000))
        status, _ = self.save({'daily_free_tokens': -1})
        self.assertEqual(status, 400)

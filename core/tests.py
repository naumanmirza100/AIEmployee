"""An agent is only ever given an AI key it can actually call.

Keys could be saved for five providers, but the four agents call only Groq and
OpenAI (Recruitment only Groq, until it moved onto the shared BaseAgent). Any
other key was accepted and then failed on every call — and the platform-key
fallback could hand an agent a key for a provider it couldn't call.
"""
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from core.api_key_service import (
    NoKeyAvailable, UnsupportedProvider, provider_supported, resolve_for_call,
)
from core.models import (
    Agent, Company, CompanyAPIKey, CompanyModulePurchase, CompanyUser, PlatformAPIKey,
)


class AgentProviderTests(TestCase):

    def setUp(self):
        for slug, default in (('hr_agent', 'openai'), ('recruitment_agent', 'openai')):
            Agent.objects.update_or_create(slug=slug, defaults={'name': slug, 'default_provider': default})
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        self.login = CompanyUser.objects.create(
            company=self.company, email='dana@test.local', full_name='Dana',
            role='admin', password_hash='x', is_active=True)

    def company_key(self, agent, provider, mode='byok'):
        key = CompanyAPIKey(company=self.company, agent_name=agent, mode=mode,
                            provider=provider, status='active', encrypted_key='')
        key.set_plaintext_key('test-key-0123456789')
        key.save()
        return key

    def platform_key(self, provider):
        key = PlatformAPIKey(provider=provider, status='active', encrypted_key='')
        key.set_plaintext_key('platform-key-0123456789')
        key.save()
        return key

    # ---- choosing a key for a call ------------------------------------------

    def test_a_saved_key_the_agent_cant_call_is_a_clear_error(self):
        self.company_key('hr_agent', 'claude')
        with self.assertRaises(UnsupportedProvider) as caught:
            resolve_for_call(self.company, 'hr_agent')
        self.assertIn("can't use Claude / Anthropic keys", caught.exception.user_message)
        self.assertIn('OpenAI or Groq', caught.exception.user_message)

    def test_so_is_a_managed_one(self):
        self.company_key('recruitment_agent', 'claude', mode='managed')
        with self.assertRaises(UnsupportedProvider) as caught:
            resolve_for_call(self.company, 'recruitment_agent')
        self.assertIn('ask your admin', caught.exception.user_message)

    def test_a_supported_key_is_used(self):
        self.company_key('hr_agent', 'groq')
        self.assertEqual(resolve_for_call(self.company, 'hr_agent').provider, 'groq')

    def test_the_platform_fallback_never_hands_an_agent_a_key_it_cant_call(self):
        # Only a Claude platform key exists: it must not be handed out.
        self.platform_key('claude')
        with self.assertRaises(NoKeyAvailable):
            resolve_for_call(self.company, 'recruitment_agent')
        self.platform_key('openai')
        self.assertEqual(resolve_for_call(self.company, 'recruitment_agent').provider, 'openai')

    def test_agents_that_arent_restricted_stay_open(self):
        self.assertTrue(provider_supported('marketing_agent', 'claude'))
        self.assertFalse(provider_supported('recruitment_agent', 'claude'))
        self.assertTrue(provider_supported('recruitment_agent', 'openai'))     # through BaseAgent now

    # ---- saving a key ---------------------------------------------------------

    def save_own_key(self, agent, provider):
        from api.views.company_api_keys import upsert_byok_key
        CompanyModulePurchase.objects.get_or_create(
            company=self.company, module_name=agent, defaults={'status': 'active', 'is_complimentary': True})
        request = APIRequestFactory().post('/', {'agent_name': agent, 'provider': provider,
                                                 'api_key': 'test-key-0123456789'}, format='json')
        force_authenticate(request, user=self.login)
        with mock.patch('api.views.company_api_keys._validate_byok_key', return_value=(True, '')):
            response = upsert_byok_key(request)
        response.render()
        return response

    def test_a_key_for_a_provider_the_agent_cant_call_is_refused_when_saved(self):
        response = self.save_own_key('recruitment_agent', 'claude')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'unsupported_provider')
        self.assertFalse(CompanyAPIKey.objects.exists())

    def test_a_supported_one_is_saved(self):
        response = self.save_own_key('recruitment_agent', 'groq')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(CompanyAPIKey.objects.filter(provider='groq').exists())

    def test_the_key_form_is_told_which_providers_to_offer(self):
        from api.views.company_api_keys import list_agent_keys
        CompanyModulePurchase.objects.create(company=self.company, module_name='recruitment_agent',
                                             status='active', is_complimentary=True)
        request = APIRequestFactory().get('/')
        force_authenticate(request, user=self.login)
        response = list_agent_keys(request)
        [row] = [a for a in response.data['agents'] if a['agent_name'] == 'recruitment_agent']
        self.assertEqual(row['supported_providers'], ['openai', 'groq'])

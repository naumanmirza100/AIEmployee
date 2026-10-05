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
    AgentDisabled, BadAPIKey, ByokCapReached, NoKeyAvailable, UnsupportedProvider, provider_supported,
    resolve_for_call,
)
from core.models import (
    Agent, AgentTokenQuota, Company, CompanyAPIKey, CompanyModulePurchase, CompanyUser, PlatformAPIKey,
)


class AgentProviderTests(TestCase):

    def setUp(self):
        for slug, default in (('hr_agent', 'openai'), ('recruitment_agent', 'openai'),
                              ('marketing_agent', 'openai'), ('ai_sdr_agent', 'groq')):
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

    def test_each_agent_is_limited_to_the_providers_its_code_can_call(self):
        self.assertFalse(provider_supported('recruitment_agent', 'claude'))
        self.assertTrue(provider_supported('recruitment_agent', 'openai'))     # through BaseAgent now
        every = ('openai', 'claude', 'gemini', 'groq', 'grok')
        for agent in ('marketing_agent', 'operations_agent', 'reply_draft_agent', 'exec_meeting_agent'):
            self.assertEqual([p for p in every if provider_supported(agent, p)], ['openai', 'groq'], agent)
        # AI SDR builds a Groq client and nothing else.
        self.assertEqual([p for p in every if provider_supported('ai_sdr_agent', p)], ['groq'])
        self.assertTrue(provider_supported('an_agent_nobody_checked', 'claude'))

    def test_an_openai_key_already_saved_for_ai_sdr_is_a_clear_error_not_a_silent_fallback(self):
        self.company_key('ai_sdr_agent', 'openai')
        with self.assertRaises(UnsupportedProvider) as caught:
            resolve_for_call(self.company, 'ai_sdr_agent')
        self.assertIn('Use Groq (Llama) instead', caught.exception.user_message)

    def test_ai_sdr_is_not_handed_a_platform_key_it_cant_call(self):
        self.platform_key('openai')
        with self.assertRaises(NoKeyAvailable):
            resolve_for_call(self.company, 'ai_sdr_agent')
        self.platform_key('groq')
        self.assertEqual(resolve_for_call(self.company, 'ai_sdr_agent').provider, 'groq')

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

class OwnKeyIsUsedTests(TestCase):
    """Saving the company's own key switches the agent to it.

    Every agent starts with its key preference on 'managed', and that
    preference made the key service skip the company's own key. So the agent
    went on spending free tokens, then stopped and told the admin to add a key
    they had already added, while the page, the pop-up and the bell all said
    the key was active.
    """

    company_key = AgentProviderTests.company_key
    platform_key = AgentProviderTests.platform_key
    save_own_key = AgentProviderTests.save_own_key

    def setUp(self):
        AgentProviderTests.setUp(self)
        self.platform_key('openai')
        self.quota = AgentTokenQuota.objects.create(company=self.company, agent_name='hr_agent')

    def pool(self):
        self.quota.refresh_from_db()
        return self.quota.preferred_pool

    def remove_own_key(self, agent):
        from api.views.company_api_keys import revoke_byok_key
        request = APIRequestFactory().delete('/')
        force_authenticate(request, user=self.login)
        return revoke_byok_key(request, agent_name=agent)

    def test_a_new_agent_starts_on_free_tokens(self):
        self.assertEqual((self.pool(), resolve_for_call(self.company, 'hr_agent').mode), ('managed', 'platform'))

    def test_saving_a_key_switches_the_agent_to_it(self):
        self.assertEqual(self.save_own_key('hr_agent', 'groq').status_code, 200)
        ctx = resolve_for_call(self.company, 'hr_agent')
        self.assertEqual((self.pool(), ctx.mode, ctx.provider), ('byok', 'byok', 'groq'))

    def test_it_takes_over_from_a_managed_key_too(self):
        self.company_key('hr_agent', 'openai', mode='managed')
        self.assertEqual(resolve_for_call(self.company, 'hr_agent').mode, 'managed')
        self.save_own_key('hr_agent', 'groq')
        self.assertEqual(resolve_for_call(self.company, 'hr_agent').mode, 'byok')

    def test_an_agent_the_company_switched_off_stays_off(self):
        AgentTokenQuota.objects.filter(pk=self.quota.pk).update(preferred_pool='none')
        self.save_own_key('hr_agent', 'groq')
        self.assertEqual(self.pool(), 'none')
        with self.assertRaises(AgentDisabled):
            resolve_for_call(self.company, 'hr_agent')

    def test_only_that_agent_changes(self):
        other = AgentTokenQuota.objects.create(company=self.company, agent_name='recruitment_agent')
        self.save_own_key('hr_agent', 'groq')
        other.refresh_from_db()
        self.assertEqual(other.preferred_pool, 'managed')

    def test_removing_the_key_goes_back_to_the_default_order(self):
        self.save_own_key('hr_agent', 'groq')
        self.remove_own_key('hr_agent')
        self.assertEqual((self.pool(), resolve_for_call(self.company, 'hr_agent').mode), ('managed', 'platform'))

    def test_removing_it_leaves_a_choice_made_by_hand_alone(self):
        self.save_own_key('hr_agent', 'groq')
        AgentTokenQuota.objects.filter(pk=self.quota.pk).update(preferred_pool='free')
        self.remove_own_key('hr_agent')
        self.assertEqual(self.pool(), 'free')

    def test_the_spending_cap_really_stops_the_agent_and_the_alert_says_so(self):
        # The page and the alerts used to call it a soft cap that never blocks.
        from core.notification_utils import notify_company_quota
        from project_manager_agent.models import PMNotification
        self.save_own_key('hr_agent', 'groq')
        AgentTokenQuota.objects.filter(pk=self.quota.pk).update(byok_token_limit=1000, byok_tokens_info=1000)
        with self.assertRaises(ByokCapReached):
            resolve_for_call(self.company, 'hr_agent')
        PMNotification.objects.all().delete()
        notify_company_quota(self.company, 'HR', 100, pool='byok')
        notify_company_quota(self.company, 'HR', 80, pool='byok')
        reached, nearly = PMNotification.objects.order_by('id').values_list('message', flat=True)
        self.assertIn('has stopped', reached)
        self.assertIn('stops when the cap', nearly)
        for message in (reached, nearly):
            self.assertNotIn('keep working', message)
            self.assertNotIn('soft cap', message)

    def test_keys_saved_before_this_fix_are_switched_on_once(self):
        from importlib import import_module
        from django.apps import apps
        fix = import_module('core.migrations.0111_use_saved_own_keys').use_saved_keys

        def agent(slug, pool, own=None, managed=False):
            Agent.objects.update_or_create(slug=slug, defaults={'name': slug, 'default_provider': 'openai'})
            quota = AgentTokenQuota.objects.create(company=self.company, agent_name=slug, preferred_pool=pool)
            if own:
                key = self.company_key(slug, 'groq')
                CompanyAPIKey.objects.filter(pk=key.pk).update(status=own)
            if managed:
                self.company_key(slug, 'openai', mode='managed')
            return quota

        rows = {
            'own key, never used': (agent('a1', 'managed', own='active'), 'byok'),
            'own key, no preference stored': (agent('a2', None, own='active'), 'byok'),
            'own key beside a managed key': (agent('a3', 'managed', own='active', managed=True), 'managed'),
            'free tokens chosen by hand': (agent('a4', 'free', own='active'), 'free'),
            'switched off by hand': (agent('a5', 'none', own='active'), 'none'),
            'no key of its own': (agent('a6', 'managed'), 'managed'),
            'a key that was revoked': (agent('a7', 'managed', own='revoked'), 'managed'),
        }
        fix(apps, None)
        fix(apps, None)
        for name, (quota, expected) in rows.items():
            quota.refresh_from_db()
            self.assertEqual(quota.preferred_pool, expected, name)


class AiSdrKeyRefusedTests(TestCase):
    """AI SDR used to carry on without AI when its key was refused: leads
    scored by fixed rules, emails sent unpersonalised, nothing reported."""

    class Refused(Exception):
        status_code = 401

    def checked(self, **behaviour):
        from ai_sdr_agent.agents.sdr_key_resolver import _CheckedGroq
        completions = mock.Mock()
        completions.create = mock.Mock(**behaviour)
        raw = mock.Mock()
        raw.chat.completions = completions
        raw.models = 'passed through'
        return _CheckedGroq(raw, mock.Mock(mode='byok')), completions

    def test_a_refused_key_is_reported_as_a_bad_key(self):
        client, _ = self.checked(side_effect=self.Refused('invalid_api_key'))
        with self.assertRaises(BadAPIKey) as caught:
            client.chat.completions.create(model='m', messages=[])
        self.assertIn('rejected by the provider', caught.exception.user_message)

    def test_any_other_failure_is_left_as_it_was(self):
        client, _ = self.checked(side_effect=TimeoutError('slow'))
        with self.assertRaises(TimeoutError):
            client.chat.completions.create(model='m', messages=[])

    def test_a_normal_call_is_passed_straight_through(self):
        client, completions = self.checked(return_value='the answer')
        self.assertEqual(client.chat.completions.create(model='m', messages=[1], temperature=0.1), 'the answer')
        completions.create.assert_called_once_with(model='m', messages=[1], temperature=0.1)
        self.assertEqual(client.models, 'passed through')

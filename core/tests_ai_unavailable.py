"""The AI provider out of credit or unreachable (19 Nov 2026).

The platform's OpenAI account ran out of credit at 05:59 UTC. Every agent on it answered with a server error, and
nobody who runs the site was told. Now every agent's AI call turns that refusal into AIServiceUnavailable: the screen
gets a 503 with words a person can act on, and when it is the platform's own account, the people who run the site get
one email an hour.
"""
from unittest import mock

import openai
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from core.api_key_service import (
    AIServiceUnavailable, BadAPIKey, CallContext, _provider_failure, raise_if_auth_error,
)
from core.drf_exceptions import key_service_exception_handler

try:                                    # what openai 3.x is built on
    import httpx2 as httpx
except ImportError:                     # pragma: no cover
    import httpx

REQUEST = httpx.Request('POST', 'https://api.openai.com/v1/chat/completions')


def out_of_credit():
    """What OpenAI raised on 19 Nov 2026, word for word."""
    body = {'message': 'You have no credits remaining. Add credits to continue using the API at '
                       'https://platform.openai.com/settings/organization/billing/.',
            'type': 'insufficient_quota', 'code': 'insufficient_quota'}
    return openai.RateLimitError(f"Error code: 429 - {{'error': {body}}}", response=httpx.Response(429, request=REQUEST),
                                 body=body)


def rate_limited():
    body = {'message': 'Rate limit reached for gpt-4.1-mini on tokens per min (TPM): Limit 200000, Used 199000. '
                       'Please try again in 2s.', 'type': 'tokens', 'code': 'rate_limit_exceeded'}
    return openai.RateLimitError(f"Error code: 429 - {{'error': {body}}}", response=httpx.Response(429, request=REQUEST),
                                 body=body)


def context(mode):
    return CallContext(company_id=1, agent_name='data_analyst_agent', mode=mode, provider='openai', api_key='x',
                       key_id=1)


class Instant:
    """threading.Thread that runs its target at once, so the email is in the outbox when the call returns."""

    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class WhichFailures(SimpleTestCase):

    def test_out_of_credit_is_told_apart_from_a_rate_limit_or_a_timeout(self):
        self.assertEqual(_provider_failure(out_of_credit()), 'out_of_credit')
        self.assertEqual(_provider_failure(Exception('402 Insufficient Balance')), 'out_of_credit')
        self.assertEqual(_provider_failure(Exception('Your credit balance is too low to access the API')),
                         'out_of_credit')
        self.assertEqual(_provider_failure(openai.APIConnectionError(request=REQUEST)), 'down')
        # Callers retry these, or fall back to a smaller prompt: left as they are.
        self.assertIsNone(_provider_failure(rate_limited()))
        self.assertIsNone(_provider_failure(openai.APITimeoutError(request=REQUEST)))
        self.assertIsNone(_provider_failure(ValueError('no JSON in the reply')))

    def test_a_rejected_key_is_still_a_bad_key(self):
        with self.assertRaises(BadAPIKey):
            raise_if_auth_error(Exception('Error code: 401 - invalid_api_key'), context('byok'))

    def test_anything_else_is_left_to_the_caller(self):
        raise_if_auth_error(rate_limited(), context('platform'))
        raise_if_auth_error(ValueError('boom'), context('platform'))


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', ERROR_ALERT_EMAILS=[])
class OutOfCredit(TestCase):

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        User.objects.create_superuser('owner', 'owner@example.com', 'x')
        thread = mock.patch('core.error_alerts.threading.Thread', Instant)
        thread.start()
        self.addCleanup(thread.stop)

    def refused(self, mode):
        with self.assertRaises(AIServiceUnavailable) as caught:
            raise_if_auth_error(out_of_credit(), context(mode))
        return caught.exception

    def test_the_platforms_account_out_of_credit_says_so_and_emails_the_super_admin_once(self):
        from django.core import mail
        error = self.refused('platform')
        self.assertEqual(error.reason, 'ai_out_of_credit')
        self.assertIn("the platform's AI account has run out of credit", error.user_message)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['owner@example.com'])
        self.assertIn("The platform's OpenAI account is out of credit", mail.outbox[0].subject)
        self.assertIn('platform.openai.com > Settings > Billing', mail.outbox[0].body)
        # A managed key is the platform's money too; within the hour, no second email.
        self.assertEqual(self.refused('managed').reason, 'ai_out_of_credit')
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(ERROR_ALERT_EMAILS=['ops@example.com'])
    def test_the_alert_addresses_come_first(self):
        from django.core import mail
        self.refused('platform')
        self.assertEqual(mail.outbox[0].to, ['ops@example.com'])

    def test_a_companys_own_key_out_of_credit_is_theirs_to_top_up_and_nobody_else_is_emailed(self):
        from django.core import mail
        error = self.refused('byok')
        self.assertIn('Your own OpenAI key has run out of credit with OpenAI', error.user_message)
        self.assertIn('Settings → API Keys', error.user_message)
        self.assertEqual(mail.outbox, [])

    def test_the_screen_gets_a_503_with_the_words(self):
        response = key_service_exception_handler(self.refused('platform'), {})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data['code'], 'ai_out_of_credit')
        self.assertTrue(response.data['hard_block'])
        self.assertIn('try again a little later', response.data['message'])
        unreachable = key_service_exception_handler(AIServiceUnavailable('down'), {})
        self.assertEqual((unreachable.status_code, unreachable.data['code']), (503, 'ai_unavailable'))

    def test_every_agents_ai_call_raises_it(self):
        """BaseAgent._call_llm, which PM, HR, Frontline, Recruitment, the Data Analyst and the Company Assistant use."""
        from project_manager_agent.ai_agents.base_agent import BaseAgent
        client = mock.Mock()
        client.chat.completions.create.side_effect = out_of_credit()
        agent = BaseAgent()
        with mock.patch.object(BaseAgent, '_resolve_company_client', return_value=(client, context('platform'))), \
             self.assertRaises(AIServiceUnavailable):
            agent._call_llm('How many orders?')
        events = []
        with mock.patch.object(BaseAgent, '_resolve_company_client', return_value=(client, context('platform'))), \
             self.assertRaises(AIServiceUnavailable):
            for event in agent._call_llm_stream('How many orders?'):
                events.append(event)
        self.assertEqual(events, [])

    def test_marketing_operations_and_reply_draft_say_it_too(self):
        """Their shared call took any 429 for a busy provider, so out of credit was "busy, try again" and nobody was
        told (21 Nov 2026, the test report's Retest A). An ordinary rate limit is still waited out and called busy."""
        from django.core import mail
        from marketing_agent.agents.marketing_base_agent import MarketingBaseAgent
        client = mock.Mock()
        client.chat.completions.create.side_effect = out_of_credit()
        agent = MarketingBaseAgent()
        with mock.patch.object(MarketingBaseAgent, '_resolve_company_client', return_value=(client, context('platform'))), \
             mock.patch('marketing_agent.agents.marketing_base_agent.time.sleep') as slept, \
             self.assertRaises(AIServiceUnavailable):
            agent._call_groq_qa('How did the campaign do?')
        self.assertEqual((client.chat.completions.create.call_count, slept.call_count, len(mail.outbox)), (1, 0, 1))
        client.chat.completions.create.side_effect = rate_limited()
        with mock.patch.object(MarketingBaseAgent, '_resolve_company_client', return_value=(client, context('platform'))), \
             mock.patch('marketing_agent.agents.marketing_base_agent.time.sleep'), \
             self.assertRaisesMessage(RuntimeError, 'The service is busy'):
            agent._call_groq_qa('How did the campaign do?')

    def test_with_nobody_to_email_the_hour_is_not_spent(self):
        """The hour's silence was set before looking for someone to tell, so a super admin added a minute later was
        never emailed (21 Nov 2026)."""
        from django.core import mail
        User.objects.filter(is_superuser=True).delete()
        self.refused('platform')
        self.assertEqual(mail.outbox, [])
        User.objects.create_superuser('late', 'late@example.com', 'x')
        self.refused('platform')
        self.assertEqual([m.to for m in mail.outbox], [['late@example.com']])


from data_analyst_agent.tests.test_data_analyst import AnalystCase  # noqa: E402


class NoCredit:
    """The Data Analyst's AI on 19 Nov 2026 at 05:59 UTC."""

    def _call_llm(self, *args, **kwargs):
        raise_if_auth_error(out_of_credit(), context('platform'))


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', ERROR_ALERT_EMAILS=[])
class TheDataAnalystSaysSo(AnalystCase):

    def test_a_question_asked_while_the_platform_is_out_of_credit(self):
        """It answered HTTP 500, "The question could not be answered just now"."""
        cache.clear()
        self.addCleanup(cache.clear)
        source = self.source()
        with mock.patch('core.error_alerts.threading.Thread', Instant):
            code, body = self.ask(self.member, source, 'How many orders?', NoCredit())
        self.assertEqual(code, 503, body)
        self.assertEqual(body['code'], 'ai_out_of_credit')
        self.assertIn("the platform's AI account has run out of credit", body['message'])

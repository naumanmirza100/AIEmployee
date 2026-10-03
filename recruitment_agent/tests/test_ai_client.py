"""Recruitment calls the AI the way the other three agents do.

It had its own Groq-only HTTP client: OpenAI keys couldn't be used, its calls
were missing from the per-call usage log, and fixes to the shared BaseAgent
(fallback model, auth errors, streaming usage) didn't reach it. The client
now keeps the interface the Recruitment agents call and works through
BaseAgent.
"""
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from core.api_key_service import BadAPIKey
from core.models import Agent, Company, CompanyModulePurchase, CompanyUser
from Frontline_agent.models import LLMUsage
from recruitment_agent.core import GroqClientError, RecruitmentAIClient


class APIError(Exception):
    def __init__(self, status):
        super().__init__(f'HTTP {status}')
        self.status_code = status


class FakeStream:
    def __init__(self, chunks):
        self.chunks, self.closed = chunks, False

    def __iter__(self):
        return iter(self.chunks)

    def close(self):
        self.closed = True


class FakeSDK:
    """Stands in for the Groq / OpenAI SDK client: replies in turn."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def answer(text, total=30):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
                           usage=SimpleNamespace(prompt_tokens=20, completion_tokens=total - 20, total_tokens=total))


def pieces(*texts):
    chunks = [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=t))], usage=None, x_groq=None)
              for t in texts]
    chunks[-1].x_groq = SimpleNamespace(usage={'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5})
    return FakeStream(chunks)


class ClientTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        self.ctx = SimpleNamespace(provider='groq', mode='byok')

    def ai_client(self, sdk, provider='groq'):
        self.ctx.provider = provider
        client = RecruitmentAIClient(company_id=self.company.id)
        patcher = mock.patch.object(RecruitmentAIClient, '_resolve_company_client', return_value=(sdk, self.ctx))
        patcher.start()
        self.addCleanup(patcher.stop)
        return client

    def charged(self):
        return mock.patch('core.api_key_service.record_usage')

    def test_a_json_answer_goes_through_the_shared_class(self):
        sdk = FakeSDK(answer('{"keywords": ["React"]}'))
        client = self.ai_client(sdk)
        with self.charged() as record:
            self.assertEqual(client.send_prompt('Return JSON.', 'A job.'), {'keywords': ['React']})
        call = sdk.calls[0]
        self.assertEqual((call['model'], call['temperature'], call['max_tokens'], call['response_format']),
                         ('openai/gpt-oss-20b', 0, 2048, {'type': 'json_object'}))
        record.assert_called_once_with(self.ctx, 30)
        row = LLMUsage.objects.get()
        self.assertEqual((row.agent, row.agent_name, row.total_tokens, row.success),
                         ('recruitment_agent', 'Recruitment', 30, True))
        self.assertEqual(client.last_token_usage['total_tokens'], 30)

    def test_an_openai_key_can_be_used(self):
        sdk = FakeSDK(answer('{"ok": true}'))
        with self.charged():
            self.ai_client(sdk, provider='openai').send_prompt('Return JSON.', 'x')
        self.assertEqual(sdk.calls[0]['model'], getattr(settings, 'OPENAI_MODEL', 'gpt-4.1-mini'))

    def test_plain_text_is_not_json_mode(self):
        sdk = FakeSDK(answer('  A job description.  '))
        with self.charged():
            self.assertEqual(self.ai_client(sdk).send_prompt_text('Write.', 'x'), 'A job description.')
        self.assertNotIn('response_format', sdk.calls[0])

    def test_a_busy_model_falls_back_then_says_rate_limited(self):
        sdk = FakeSDK(APIError(429), APIError(429))
        with self.charged() as record, self.assertRaises(GroqClientError) as caught:
            self.ai_client(sdk).send_prompt('Return JSON.', 'x')
        self.assertTrue(caught.exception.is_rate_limit)
        self.assertEqual([c['model'] for c in sdk.calls], ['openai/gpt-oss-20b', 'llama-3.3-70b-versatile'])
        self.assertEqual(LLMUsage.objects.filter(success=False).count(), 2)
        record.assert_not_called()

    def test_a_refused_key_is_the_key_services_error(self):
        sdk = FakeSDK(APIError(401), APIError(401))
        with self.charged(), self.assertRaises(BadAPIKey):
            self.ai_client(sdk).send_prompt('Return JSON.', 'x')

    def test_an_answer_that_isnt_json_is_a_client_error(self):
        with self.charged(), self.assertRaises(GroqClientError):
            self.ai_client(FakeSDK(answer('not json'))).send_prompt('Return JSON.', 'x')

    def test_no_company_no_call(self):
        with self.assertRaises(GroqClientError):
            RecruitmentAIClient()

    # ---- streaming ------------------------------------------------------------

    def test_a_stream_yields_pieces_and_charges_the_reported_usage(self):
        stream = pieces('Hel', 'lo')
        with self.charged() as record:
            self.assertEqual(list(self.ai_client(FakeSDK(stream)).send_prompt_text_stream('S.', 'Hi?')), ['Hel', 'lo'])
        record.assert_called_once_with(self.ctx, 5)
        self.assertTrue(stream.closed)
        self.assertEqual(LLMUsage.objects.get().agent, 'recruitment_agent')

    def test_a_reader_that_stops_early_is_still_charged(self):
        stream = pieces('Hel', 'lo', ' there')
        with self.charged() as record:
            reader = self.ai_client(FakeSDK(stream)).send_prompt_text_stream('S.', 'Hi?')
            next(reader)
            reader.close()
        record.assert_called_once()
        self.assertGreater(record.call_args.args[1], 0)
        self.assertTrue(stream.closed)

    def test_a_refused_key_fails_before_any_text_and_costs_nothing(self):
        with self.charged() as record, self.assertRaises(BadAPIKey):
            list(self.ai_client(FakeSDK(APIError(401))).send_prompt_text_stream('S.', 'Hi?'))
        record.assert_not_called()


class UsageShownTests(TestCase):
    """The per-call log is read: each agent's AI calls in the last 30 days are
    on the company's AI keys page."""

    def test_calls_and_failures_per_agent(self):
        from api.views.company_api_keys import list_agent_keys
        Agent.objects.update_or_create(slug='recruitment_agent', defaults={'name': 'Recruitment'})
        company = Company.objects.create(name='Acme', email='acme@test.local')
        other = Company.objects.create(name='Rival', email='rival@test.local')
        admin = CompanyUser.objects.create(company=company, email='a@test.local', full_name='A', role='admin',
                                           password_hash='x', is_active=True)
        CompanyModulePurchase.objects.create(company=company, module_name='recruitment_agent', status='active',
                                             is_complimentary=True)
        log = lambda c, ok=True, tokens=100, agent='recruitment_agent': LLMUsage.objects.create(  # noqa: E731
            company=c, agent=agent, agent_name='Recruitment', model='m', total_tokens=tokens, success=ok)
        log(company), log(company), log(company, ok=False, tokens=0)
        old = log(company)
        LLMUsage.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=40))
        log(other)
        request = APIRequestFactory().get('/')
        force_authenticate(request, user=admin)
        [row] = [a for a in list_agent_keys(request).data['agents'] if a['agent_name'] == 'recruitment_agent']
        self.assertEqual(row['usage_30d'], {'calls': 3, 'failed': 1, 'tokens': 200})

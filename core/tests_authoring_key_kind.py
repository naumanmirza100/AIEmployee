"""Operations Authoring writes a new document with whichever kind of AI key the company has.

The streaming route always named the Groq model, so with an OpenAI key the request
went to OpenAI asking for a model it does not have, and every new document failed.
"""
from types import SimpleNamespace
from unittest import mock

from django.conf import settings
from django.test import TestCase

from core.api_key_service import BadAPIKey, CallContext
from core.models import Company
from operations_agent.agents.document_authoring_agent import DocumentAuthoringAgent


def chunk(text=None, usage=None):
    choices = [SimpleNamespace(delta=SimpleNamespace(content=text))] if text else []
    return SimpleNamespace(choices=choices, usage=usage)


class AuthoringKeyKindTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        self.calls = []

    def fake_client(self, *args, **kwargs):
        def create(**call):
            self.calls.append(call)
            return iter([chunk('# Briefing\n\nAll on track.'),
                         chunk(usage=SimpleNamespace(prompt_tokens=50, completion_tokens=10, total_tokens=60))])
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    def run_stream(self, provider):
        ctx = CallContext(company_id=self.company.id, agent_name='operations_agent', mode='byok',
                          provider=provider, api_key='k', key_id=1)
        agent = DocumentAuthoringAgent()
        agent.company_id, agent.agent_key_name = self.company.id, 'operations_agent'
        with mock.patch('core.api_key_service.resolve_for_call', return_value=ctx), \
                mock.patch('core.api_key_service.record_usage'), \
                mock.patch('openai.OpenAI', side_effect=self.fake_client), \
                mock.patch('groq.Groq', side_effect=self.fake_client):
            return agent, list(agent.generate_stream(self.company.id, 'A one-page briefing', title='Briefing'))

    def test_an_openai_key_is_asked_for_an_openai_model(self):
        _, events = self.run_stream('openai')
        expected = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
        self.assertEqual(self.calls[0]['model'], expected)
        done = dict(events)['done']
        self.assertIn('All on track.', done['content_markdown'])
        self.assertEqual((done['tokens_used']['provider'], done['tokens_used']['model']), ('openai', expected))

    def test_a_groq_key_still_gets_the_groq_model(self):
        agent, events = self.run_stream('groq')
        self.assertEqual(self.calls[0]['model'], agent.model)
        self.assertEqual(dict(events)['done']['tokens_used']['provider'], 'groq')

    def test_a_rejected_key_gives_the_usual_bad_key_message(self):
        class AuthenticationError(Exception):
            pass

        def refusing_client(*args, **kwargs):
            def create(**call):
                raise AuthenticationError('Incorrect API key provided')
            return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

        ctx = CallContext(company_id=self.company.id, agent_name='operations_agent', mode='byok',
                          provider='openai', api_key='k', key_id=1)
        agent = DocumentAuthoringAgent()
        agent.company_id, agent.agent_key_name = self.company.id, 'operations_agent'
        with mock.patch('core.api_key_service.resolve_for_call', return_value=ctx), \
                mock.patch('openai.OpenAI', side_effect=refusing_client):
            with self.assertRaises(BadAPIKey):
                list(agent.generate_stream(self.company.id, 'A one-page briefing', title='Briefing'))

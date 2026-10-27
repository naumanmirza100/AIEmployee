"""Marketing, Operations, Reply Draft and AI SDR log every AI call, so the API Keys page counts them (CO-69).

The page counts calls from LLMUsage, which only PM, HR, Frontline, Recruitment and Executive Meeting wrote to. These
four spent tokens (their bars moved) but always showed "Last 30 days: 0 AI calls" and never a failure.
"""
from types import SimpleNamespace
from unittest import mock

from api.views.company_api_keys import _ai_calls_by_agent
from Frontline_agent.models import LLMUsage
from marketing_agent.agents.marketing_base_agent import MarketingBaseAgent

from .base import MarketingTestCase


def reply(text='Hello', total=30):
    usage = SimpleNamespace(prompt_tokens=total - 10, completion_tokens=10, total_tokens=total)
    return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def client(*results):
    fake = mock.Mock()
    fake.chat.completions.create.side_effect = list(results)
    return fake


class AICallsLoggedTests(MarketingTestCase):

    def agent(self, key):
        agent = MarketingBaseAgent()
        agent.company_id, agent.agent_key_name = self.acme.id, key
        return agent

    def ctx(self, provider='groq'):
        return SimpleNamespace(provider=provider, company_id=self.acme.id, mode='byok', quota_id=None)

    def test_a_marketing_answer_is_counted(self):
        agent = self.agent('marketing_agent')
        with mock.patch.object(agent, '_resolve_company_client', return_value=(client(reply()), self.ctx())), \
                mock.patch('core.api_key_service.record_usage'):
            self.assertEqual(agent._call_groq_qa('Hi?'), 'Hello')
        row = LLMUsage.objects.get()
        self.assertEqual((row.agent, row.total_tokens, row.success), ('marketing_agent', 30, True))
        self.assertEqual(_ai_calls_by_agent(self.acme)['marketing_agent'], {'calls': 1, 'failed': 0, 'tokens': 30})

    def test_a_failed_call_is_counted_as_failed(self):
        agent = self.agent('reply_draft_agent')
        with mock.patch.object(agent, '_resolve_company_client',
                               return_value=(client(RuntimeError('provider down')), self.ctx('openai'))):
            with self.assertRaises(RuntimeError):
                agent._call_openai('Write a reply.')
        self.assertEqual(_ai_calls_by_agent(self.acme)['reply_draft_agent'], {'calls': 1, 'failed': 1, 'tokens': 0})

    def test_operations_writing_is_counted(self):
        agent = self.agent('operations_agent')
        with mock.patch.object(agent, '_resolve_company_client', return_value=(client(reply(total=50)), self.ctx())), \
                mock.patch('core.api_key_service.record_usage'):
            agent._call_openai('Write a report.')
        self.assertEqual(_ai_calls_by_agent(self.acme)['operations_agent']['tokens'], 50)

    def test_ai_sdr_calls_are_counted_through_its_key_wrapper(self):
        from ai_sdr_agent.agents.sdr_key_resolver import _CheckedGroq
        groq = _CheckedGroq(client(reply(total=40), RuntimeError('timeout')), self.ctx())
        groq.chat.completions.create(model='openai/gpt-oss-20b', messages=[])
        with self.assertRaises(RuntimeError):
            groq.chat.completions.create(model='openai/gpt-oss-20b', messages=[])
        self.assertEqual(_ai_calls_by_agent(self.acme)['ai_sdr_agent'], {'calls': 2, 'failed': 1, 'tokens': 40})

"""Knowledge Q&A answers stream in as they're written.

PM Knowledge Q&A showed nothing until the whole answer arrived; HR and
Frontline already streamed. And a streamed answer never counted against the
company's token quota — only the non-streaming call recorded usage.
"""
import json
from types import SimpleNamespace
from unittest import mock

from project_manager_agent.ai_agents.base_agent import BaseAgent
from project_manager_agent.ai_agents.knowledge_qa_agent import KnowledgeQAAgent

from .base import PMTestCase

URL = '/api/project-manager/ai/knowledge-qa/stream'


def fake_stream(*pieces):
    def stream(self, prompt, system_prompt=None, temperature=0.3, max_tokens=400):
        for piece in pieces:
            yield {'type': 'token', 'value': piece}
        yield {'type': 'done', 'text': ''.join(pieces)}
    return stream


class KnowledgeStreamTests(PMTestCase):

    def ask(self, question='What is the website rebuild about?'):
        response = self.http(self.dash).post(URL, json.dumps({'question': question}),
                                              content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/x-ndjson')
        self.assertEqual(response['X-Accel-Buffering'], 'no')
        return [json.loads(line) for line in b''.join(response.streaming_content).decode().splitlines() if line]

    def test_the_answer_arrives_in_pieces_then_the_whole_result(self):
        with mock.patch.object(KnowledgeQAAgent, '_call_llm_stream', fake_stream('It is ', 'a redesign.')):
            events = self.ask()
        self.assertEqual([e['type'] for e in events], ['token', 'token', 'done'])
        self.assertEqual([e['value'] for e in events[:2]], ['It is ', 'a redesign.'])
        done = events[-1]
        self.assertIn('a redesign.', done['data']['answer'])
        self.assertTrue(done['data']['success'])
        self.assertEqual(done['session_id'], f'company_user_{self.dash.id}')

    def test_the_same_result_as_the_plain_endpoint(self):
        from api.views import pm_agent
        with mock.patch.object(KnowledgeQAAgent, '_call_llm', return_value='It is a redesign.'):
            code, plain = self.call(pm_agent.knowledge_qa, self.dash, {'question': 'What is the website rebuild about?'})
        with mock.patch.object(KnowledgeQAAgent, '_call_llm_stream', fake_stream('It is ', 'a redesign.')):
            streamed = self.ask()[-1]['data']
        self.assertEqual(code, 200)
        self.assertEqual(streamed['answer'], plain['data']['answer'])
        self.assertEqual(sorted(streamed), sorted(plain['data']))

    def test_a_count_answered_from_the_data_needs_no_model(self):
        def no_model(*args, **kwargs):
            raise AssertionError('the model was called')
        self.task(title='Build the header', status='todo')
        with mock.patch.object(KnowledgeQAAgent, '_call_llm_stream', no_model):
            events = self.ask('How many tasks in each status?')
        self.assertEqual([e['type'] for e in events], ['token', 'done'])
        self.assertEqual(events[0]['value'], events[1]['data']['answer'])

    def test_a_failure_part_way_ends_with_an_error(self):
        def broken(self, *args, **kwargs):
            yield {'type': 'token', 'value': 'It is '}
            raise RuntimeError('connection dropped')
        with mock.patch.object(KnowledgeQAAgent, '_call_llm_stream', broken):
            events = self.ask()
        self.assertEqual([e['type'] for e in events], ['token', 'error'])
        self.assertNotIn('connection dropped', events[-1]['message'])    # no internals

    def test_checks_happen_before_the_stream_starts(self):
        response = self.http(self.dash).post(URL, json.dumps({'question': '  '}), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('question is required', response.json()['message'])


class StreamedUsageTests(PMTestCase):
    """The streaming call records tokens against the quota, like `_call_llm`."""

    def run_stream(self, chunks, provider='groq'):
        ctx = SimpleNamespace(provider=provider)
        create = mock.Mock(return_value=iter(chunks))
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        agent = BaseAgent()
        agent.company_id, agent.agent_key_name = self.company.id, 'project_manager_agent'
        with mock.patch.object(BaseAgent, '_resolve_company_client', return_value=(client, ctx)), \
                mock.patch('core.api_key_service.record_usage') as record:
            events = list(agent._call_llm_stream('Question?', 'System.'))
        return events, record, create, ctx

    @staticmethod
    def chunk(text=None, usage=None, groq_usage=None):
        return SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=text))] if text is not None else [],
            usage=usage, x_groq=SimpleNamespace(usage=groq_usage) if groq_usage else None)

    def test_the_usage_groq_reports_is_recorded(self):
        usage = SimpleNamespace(prompt_tokens=40, completion_tokens=6, total_tokens=46)
        events, record, _, ctx = self.run_stream([self.chunk('Hel'), self.chunk('lo'), self.chunk(groq_usage=usage)])
        self.assertEqual(''.join(e['value'] for e in events if e['type'] == 'token'), 'Hello')
        record.assert_called_once_with(ctx, 46)
        self.assertEqual(events[-1]['usage']['total_tokens'], 46)

    def test_openai_is_asked_for_usage(self):
        usage = {'prompt_tokens': 30, 'completion_tokens': 4, 'total_tokens': 34}
        _, record, create, ctx = self.run_stream([self.chunk('Hi'), self.chunk(usage=usage)], provider='openai')
        self.assertEqual(create.call_args.kwargs['stream_options'], {'include_usage': True})
        record.assert_called_once_with(ctx, 34)

    def test_without_a_report_it_is_estimated_not_free(self):
        events, record, _, ctx = self.run_stream([self.chunk('A fairly short answer.')])
        record.assert_called_once()
        self.assertGreater(record.call_args.args[1], 0)
        self.assertTrue(events[-1]['usage']['estimated'])

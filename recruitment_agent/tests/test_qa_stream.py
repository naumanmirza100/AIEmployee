"""Recruitment Q&A answers stream in as they're written.

It showed nothing until the whole answer arrived, while HR and Frontline Q&A
already streamed. The streamed call must still count against the quota.
"""
import json
from unittest import mock

from django.test import Client, TestCase

from core.models import Company, CompanyModulePurchase, CompanyUser, CompanyUserToken
from recruitment_agent.agents.recruitment_qa_agent import RecruitmentQAAgent
from recruitment_agent.core import GroqClientError

GENERAL = 'What are some good React interview questions?'
ANSWER = '## React questions\n- What is JSX?\n- How do hooks work?'


class FakeGroq:
    """Stands in for the Groq client: the same text, whole or in pieces."""

    def __init__(self, text=ANSWER, fail=False):
        self.text, self.fail, self.calls, self.last_token_usage = text, fail, [], None

    def send_prompt_text(self, system_prompt, text):
        self.calls.append('plain')
        if self.fail:
            raise GroqClientError('boom')
        self.last_token_usage = {'prompt_tokens': 50, 'completion_tokens': 12, 'total_tokens': 62}
        return self.text

    def send_prompt_text_stream(self, system_prompt, text):
        self.calls.append('stream')
        if self.fail:
            raise GroqClientError('boom')
        yield self.text[:12]
        yield self.text[12:]
        self.last_token_usage = {'prompt_tokens': 50, 'completion_tokens': 12, 'total_tokens': 62}


class RecruitmentStreamTestCase(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        self.recruiter = CompanyUser.objects.create(company=self.company, email='rae@test.local',
                                                    full_name='Rae Recruiter', role='admin',
                                                    password_hash='x', is_active=True)
        CompanyModulePurchase.objects.create(company=self.company, module_name='recruitment_agent',
                                             status='active', is_complimentary=True)


class AgentTests(RecruitmentStreamTestCase):

    def stream(self, question, groq=None):
        groq = groq or FakeGroq()
        return list(RecruitmentQAAgent(groq_client=groq).process_stream(question, self.recruiter)), groq

    def test_the_answer_arrives_in_pieces_then_the_same_result_as_before(self):
        events, groq = self.stream(GENERAL)
        self.assertEqual([e['type'] for e in events], ['token', 'token', 'done'])
        self.assertEqual(groq.calls, ['stream'])
        self.assertEqual(''.join(e['value'] for e in events[:2]), ANSWER)
        plain = RecruitmentQAAgent(groq_client=FakeGroq()).process(GENERAL, self.recruiter)
        self.assertEqual(events[-1]['result']['answer'], plain['answer'])
        self.assertIn('Tokens used:** 62', plain['answer'])                    # the usage line, both ways

    def test_answers_that_need_no_model_arrive_whole(self):
        events, groq = self.stream('hi')
        self.assertEqual([e['type'] for e in events], ['token', 'done'])
        self.assertEqual(groq.calls, [])
        self.assertIn('Recruitment Q&A', events[0]['value'])

    def test_an_api_error_ends_with_the_usual_friendly_answer(self):
        events, _ = self.stream(GENERAL, FakeGroq(fail=True))
        self.assertEqual(events[-1]['type'], 'done')
        self.assertIn('API error', events[-1]['result']['answer'])


class EndpointTests(RecruitmentStreamTestCase):
    URL = '/api/recruitment/qa/stream'

    def post(self, question):
        key = CompanyUserToken.objects.get_or_create(company_user=self.recruiter)[0].key
        with mock.patch('api.views.recruitment_agent._make_agents', return_value={'groq_client': FakeGroq()}):
            return Client(HTTP_AUTHORIZATION=f'Token {key}').post(
                self.URL, json.dumps({'question': question}), content_type='application/json')

    def test_streams_tokens_then_the_answer_and_insights(self):
        response = self.post(GENERAL)
        self.assertEqual((response.status_code, response['Content-Type']), (200, 'application/x-ndjson'))
        events = [json.loads(line) for line in b''.join(response.streaming_content).decode().splitlines() if line]
        self.assertEqual([e['type'] for e in events], ['token', 'token', 'done'])
        self.assertEqual(set(events[-1]['data']), {'answer', 'insights'})

    def test_a_blank_question_is_refused_before_streaming(self):
        self.assertEqual(self.post('  ').status_code, 400)

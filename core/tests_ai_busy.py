"""A busy AI provider says "busy, try again", not its own words or a wrong reason (24 Nov 2026).

The test report's Retest B: on an ordinary rate limit the person was shown "Error code: 429 - Rate limit reached for
gpt-4o-mini in organization org_… on tokens per min …" in Operations' memo, Frontline's and HR's Summarize and HR's
meeting scheduler; Operations' figures answered 500; HR's Q&A said the policy wasn't in the documents, and
Recruitment's told people to check the API key.

A rate limit stays an ordinary exception inside the AI call (core/whole_document.py falls back to the passages on it);
the shared calls raise it as ProviderBusy, whose text is fit to show, and raise_if_busy makes it a 503 where nothing
else can be done.
"""
import json
from unittest import mock

import openai
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from core.api_key_service import (
    BUSY_MESSAGE, AIServiceUnavailable, ProviderBusy, is_busy_error, raise_if_busy,
)
from core.drf_exceptions import key_service_exception_handler
from core.tests_ai_unavailable import REQUEST, context, out_of_credit, rate_limited
from Frontline_agent.tests.base import FrontlineTestCase
from hr_agent.tests.base import HRTestCase


def too_large():
    body = {'message': 'Request too large for gpt-4o-mini on tokens per min (TPM): Limit 200000, Requested 250000.',
            'type': 'tokens', 'code': 'rate_limit_exceeded'}
    import httpx
    return openai.RateLimitError(f"Error code: 429 - {{'error': {body}}}",
                                 response=httpx.Response(429, request=REQUEST), body=body)


class WhatCountsAsBusy(SimpleTestCase):

    def test_a_rate_limit_a_timeout_and_an_overloaded_provider_are_busy(self):
        self.assertTrue(is_busy_error(rate_limited()))
        self.assertTrue(is_busy_error(openai.APITimeoutError(request=REQUEST)))
        self.assertTrue(is_busy_error(Exception('Error code: 529 - overloaded_error')))
        self.assertTrue(is_busy_error(ProviderBusy()))
        from recruitment_agent.core import GroqClientError
        self.assertTrue(is_busy_error(GroqClientError('AI request failed: …', is_rate_limit=True)))

    def test_out_of_credit_a_bad_key_a_request_too_big_and_anything_else_are_not(self):
        self.assertFalse(is_busy_error(out_of_credit()))
        self.assertFalse(is_busy_error(Exception('Error code: 401 - invalid_api_key')))
        self.assertFalse(is_busy_error(too_large()))            # asking again won't help
        self.assertFalse(is_busy_error(ValueError('no JSON in the reply')))
        self.assertFalse(is_busy_error(AIServiceUnavailable('down')))

    def test_raise_if_busy_gives_the_screen_a_503_in_plain_words(self):
        with self.assertRaises(AIServiceUnavailable) as caught:
            raise_if_busy(rate_limited(), context('platform'))
        response = key_service_exception_handler(caught.exception, {})
        self.assertEqual((response.status_code, response.data['code']), (503, 'ai_busy'))
        self.assertEqual(response.data['message'], BUSY_MESSAGE)
        self.assertNotIn('org_', json.dumps(response.data))
        raise_if_busy(ValueError('boom'))                       # left to the caller

    def test_out_of_credit_still_wins(self):
        with mock.patch('core.error_alerts.ai_out_of_credit'), self.assertRaises(AIServiceUnavailable) as caught:
            raise_if_busy(out_of_credit(), context('platform'))
        self.assertEqual(caught.exception.reason, 'ai_out_of_credit')


class TheSharedCalls(SimpleTestCase):

    def test_base_agent_raises_provider_busy_with_words_fit_to_show(self):
        from project_manager_agent.ai_agents.base_agent import BaseAgent
        client = mock.Mock()
        client.chat.completions.create.side_effect = rate_limited()
        agent = BaseAgent()
        with mock.patch.object(BaseAgent, '_resolve_company_client', return_value=(client, context('platform'))), \
             mock.patch('project_manager_agent.ai_agents.base_agent._record_llm_usage'), \
             self.assertRaises(ProviderBusy) as caught:
            agent._call_llm('Plan my week')
        self.assertEqual(str(caught.exception), BUSY_MESSAGE)
        self.assertIsInstance(caught.exception.__cause__, openai.RateLimitError)
        self.assertNotIsInstance(caught.exception, AIServiceUnavailable)    # whole_document still falls back

    def test_the_stream_says_busy_not_the_providers_words(self):
        from project_manager_agent.ai_agents.base_agent import BaseAgent
        client = mock.Mock()
        client.chat.completions.create.side_effect = rate_limited()
        with mock.patch.object(BaseAgent, '_resolve_company_client', return_value=(client, context('platform'))), \
             mock.patch('project_manager_agent.ai_agents.base_agent._record_llm_usage'):
            events = list(BaseAgent()._call_llm_stream('Plan my week'))
        self.assertEqual(events, [{'type': 'error', 'message': BUSY_MESSAGE, 'code': 'ai_busy'}])
        client.chat.completions.create.side_effect = ValueError('org_123 secret detail')
        with mock.patch.object(BaseAgent, '_resolve_company_client', return_value=(client, context('platform'))), \
             mock.patch('project_manager_agent.ai_agents.base_agent._record_llm_usage'):
            events = list(BaseAgent()._call_llm_stream('Plan my week'))
        self.assertNotIn('org_123', events[0]['message'])

    def test_whole_document_still_answers_from_the_passages(self):
        from core import whole_document
        agent = mock.Mock()
        agent._call_llm.side_effect = ProviderBusy()
        self.assertIsNone(whole_document.answer(agent, mock.Mock(prompt='p', max_tokens=10), system_prompt='s'))

    def test_the_marketing_call_keeps_its_words_as_provider_busy(self):
        """Marketing, Operations and Reply Draft: the same "The service is busy" as before, now typed."""
        from marketing_agent.agents.marketing_base_agent import MarketingBaseAgent
        client = mock.Mock()
        client.chat.completions.create.side_effect = rate_limited()
        with mock.patch.object(MarketingBaseAgent, '_resolve_company_client', return_value=(client, context('platform'))), \
             mock.patch('marketing_agent.agents.marketing_base_agent.time.sleep'), \
             self.assertRaisesMessage(ProviderBusy, 'The service is busy'):
            MarketingBaseAgent()._call_groq_qa('How did the campaign do?')


class OperationsSaysBusy(TestCase):

    def setUp(self):
        from core.models import Company, CompanyModulePurchase, CompanyUser
        from operations_agent.models import OperationsDocument
        self.factory = APIRequestFactory()
        company = Company.objects.create(name='Crestline', email='crestline@test.local')
        CompanyModulePurchase.objects.create(company=company, module_name='operations_agent', status='active',
                                             is_complimentary=True)
        self.sara = CompanyUser.objects.create(company=company, email='sara@crestline.test', full_name='Sara Ahmed',
                                               role='owner', password_hash='x', is_active=True)
        self.doc = OperationsDocument.objects.create(company=company, title='MSA', original_filename='MSA.pdf',
                                                     file='operations/documents/MSA.pdf',
                                                     parsed_text='The total contract value is PKR 1,250,000.')

    def test_extract_figures_is_503_busy_not_500(self):
        from api.views import operations_agent as views
        request = self.factory.post('/')
        force_authenticate(request, user=self.sara)
        with mock.patch('operations_agent.figures.extract', side_effect=ProviderBusy('The service is busy. Please '
                                                                                     'try again in a moment.')):
            response = views.extract_document_figures(request, document_id=self.doc.id)
        response.render()
        body = json.loads(response.content)
        self.assertEqual((response.status_code, body['code']), (503, 'ai_busy'), body)

    def test_the_streamed_memo_never_shows_the_providers_words(self):
        """Groq's refusal named our provider, model, organisation and billing tier (Operations 2)."""
        from operations_agent.agents.document_authoring_agent import DocumentAuthoringAgent
        agent = DocumentAuthoringAgent()
        client = mock.Mock()
        client.chat.completions.create.side_effect = rate_limited()
        prepared = {'ok': True, 'user_prompt': 'Write a memo', 'resolved_title': 'Memo', 'refs': []}
        with mock.patch.object(DocumentAuthoringAgent, '_prepare_prompt', return_value=prepared), \
             mock.patch.object(DocumentAuthoringAgent, '_resolve_company_client',
                               return_value=(client, context('platform'))), \
             mock.patch.object(DocumentAuthoringAgent, '_log_call'), \
             self.assertRaises(AIServiceUnavailable) as caught:
            list(agent.generate_stream(company_id=1, prompt='Write a memo'))
        self.assertEqual(caught.exception.reason, 'ai_busy')     # the view sends its user_message


class FrontlineSummarizeSaysBusy(FrontlineTestCase):

    def test_summarize_and_extract_are_503_busy(self):
        from api.views import frontline_agent as views
        from Frontline_agent.models import Document
        doc = Document.objects.create(title='Prospectus', file_path='p.pdf', company=self.company,
                                      uploaded_by=self.admin_user, processing_status='ready',
                                      document_content='Fees are due by the 10th of each month.')
        with mock.patch('core.Frontline_agent.frontline_agent.FrontlineAgent._call_llm', side_effect=ProviderBusy()), \
             mock.patch('core.whole_document.document_for_call', return_value=('Given in full.', 'doc', '')):
            for view in (views.summarize_document, views.extract_document):
                code, body = self.call(view, self.member, {}, document_id=doc.id)
                self.assertEqual((code, body.get('code')), (503, 'ai_busy'), body)


class HRSaysBusy(HRTestCase):

    def test_summarize_is_503_busy(self):
        from api.views import hr_agent as views
        from hr_agent.models import HRDocument
        doc = HRDocument.objects.create(company=self.company, title='Handbook', processing_status='ready',
                                        confidentiality='employee', document_content='Meals are paid.')
        with mock.patch('core.HR_agent.hr_agent.HRAgent._call_llm', side_effect=ProviderBusy()), \
             mock.patch('core.whole_document.document_for_call', return_value=('Given in full.', 'doc', '')):
            code, body = self.call(views.summarize_hr_document, self.member, {}, document_id=doc.id)
        self.assertEqual((code, body.get('code')), (503, 'ai_busy'), body)

    def test_the_meeting_scheduler_is_503_busy_not_the_providers_words(self):
        from api.views import hr_agent as views
        with mock.patch('api.views.hr_agent.HRAgent._call_llm', side_effect=ProviderBusy()):
            code, body = self.call(views.hr_meeting_schedule, self.admin,
                                   {'message': 'Book a one-to-one with Mo tomorrow at 3pm'})
        self.assertEqual((code, body.get('code')), (503, 'ai_busy'), body)

    def test_a_failed_answer_says_busy_not_the_passages(self):
        from core.HR_agent.hr_agent import HRAgent
        from core.HR_agent.intent import AI_BUSY_ANSWER
        agent = HRAgent(company_id=self.company.id)
        found = {'has_verified_info': True, 'answer': '--- Source: Handbook ---\nMeals are paid up to PKR 15,000.',
                 'excerpts': [{'title': 'Handbook', 'content': 'Meals are paid up to PKR 15,000.'}],
                 'citations': [{'title': 'Handbook'}], 'confidence': 'medium'}
        with mock.patch.object(agent.knowledge_service, 'get_answer', return_value=found), \
             mock.patch.object(HRAgent, '_call_llm', side_effect=ProviderBusy()), \
             mock.patch.object(HRAgent, '_plan_whole_document', return_value=None):
            result = agent.answer_question('What is the meal limit?', asker_employee=self.member_emp)
        self.assertEqual(result['answer'], AI_BUSY_ANSWER)
        self.assertFalse(result['has_verified_info'])
        self.assertNotIn('Source', result['answer'])

    def test_nothing_found_while_the_search_was_busy_says_busy_not_missing(self):
        from core.HR_agent.hr_agent import HRAgent
        from core.HR_agent.intent import AI_BUSY_ANSWER, NOT_IN_THE_DOCUMENTS
        agent = HRAgent(company_id=self.company.id)
        for busy, words in ((True, AI_BUSY_ANSWER), (False, NOT_IN_THE_DOCUMENTS)):
            with mock.patch.object(agent.knowledge_service, 'get_answer',
                                   return_value={'has_verified_info': False, 'ai_busy': busy}):
                self.assertEqual(agent.answer_question('What is the meal limit?')['answer'], words)
                events = list(agent.answer_question_stream('What is the meal limit?'))
            self.assertEqual(events[-1]['answer'], words)


class HRHandbookSearch(HRTestCase):
    """HR 2: "not found" for policies that are in the handbook."""

    def setUp(self):
        super().setUp()
        from hr_agent.models import HRDocument, HRDocumentChunk
        doc = HRDocument.objects.create(company=self.company, title='Handbook', processing_status='ready',
                                        is_indexed=True, confidentiality='employee', document_content='…')
        for i, (heading, text) in enumerate([
            ('Working hours', 'The working day is 9 to 6, Monday to Friday, with an hour for lunch.'),
            ('Expenses', 'Meals while travelling for work are paid up to PKR 15,000 a day. Claims must be filed '
                         'within 30 days with receipts.'),
            ('Leave', 'Annual leave is 20 working days a year. Sick leave is 10 days.'),
        ]):
            HRDocumentChunk.objects.create(document=doc, chunk_index=i, chunk_text=text, section_heading=heading)
        from core.HR_agent.services import HRKnowledgeService
        self.service = HRKnowledgeService(company_id=self.company.id)
        unavailable = mock.patch.object(self.service.embedding_service, 'is_available', return_value=False)
        unavailable.start()
        self.addCleanup(unavailable.stop)

    def answer(self, question):
        return self.service.get_answer(question, asker_role='employee', asker_employee_id=self.member_emp.id)

    def test_her_three_questions_find_the_expenses_section(self):
        for question in ('What is the meal limit when travelling for work?',
                         'How much can I claim for meals on a work trip?',
                         'How long do I have to file an expense claim?',
                         'What does the handbook say about expenses?'):
            result = self.answer(question)
            self.assertTrue(result['has_verified_info'], question)
            self.assertIn('PKR 15,000', result['excerpts'][0]['content'], question)

    def test_a_question_the_handbook_doesnt_cover_is_still_not_found(self):
        self.assertFalse(self.answer('What is the parental leave for adoption?')['has_verified_info'])

    def test_a_passage_with_the_words_counts_although_its_similarity_is_under_the_line(self):
        """Only the top hit's similarity was checked against 0.3."""
        results = [{'chunk_id': 1, 'content': 'Meals …', 'semantic_score': 0.21, 'keyword_match': True,
                    'title': 'Handbook', 'document_id': 1},
                   {'chunk_id': 2, 'content': 'Hours …', 'semantic_score': 0.27, 'keyword_match': False,
                    'title': 'Handbook', 'document_id': 1}]
        with mock.patch.object(self.service, 'search_knowledge', return_value=results):
            self.assertTrue(self.answer('meal limit')['has_verified_info'])
        for r in results:
            r['keyword_match'] = False
        with mock.patch.object(self.service, 'search_knowledge', return_value=results):
            self.assertFalse(self.answer('meal limit')['has_verified_info'])


class RecruitmentGivesTheRightReason(SimpleTestCase):

    def test_busy_is_busy_and_only_a_key_problem_mentions_the_key(self):
        from recruitment_agent.agents.recruitment_qa_agent import RecruitmentQAAgent
        from recruitment_agent.core import GroqClientError
        agent = RecruitmentQAAgent.__new__(RecruitmentQAAgent)
        agent.groq_client = mock.Mock(last_token_usage=None)
        busy = agent._api_error_response(GroqClientError('AI request failed: …', is_rate_limit=True))['answer']
        key = agent._api_error_response(GroqClientError('AI request failed: …', is_auth_error=True))['answer']
        other = agent._api_error_response(GroqClientError('AI request failed: …'))['answer']
        self.assertIn('busy', busy)
        self.assertNotIn('API key', busy)
        self.assertIn('API key', key)
        self.assertNotIn('API key', other)

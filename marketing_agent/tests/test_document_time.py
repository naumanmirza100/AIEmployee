"""A campaign brief must come back inside the 60 s the API's proxy allows.

Every Marketing LLM call stopped at 30 s, and a brief (about 3,000 tokens) takes ~27 s, so on the live site it
failed with "The AI took too long to respond". When the brief's structure check failed, a second full rewrite
could also push the request past the proxy's limit.
"""
from unittest import mock

from marketing_agent.agents.document_authoring_agent import DocumentAuthoringAgent
from marketing_agent.agents.marketing_base_agent import QA_TIMEOUT, WRITING_TIMEOUT
from marketing_agent.tests.base import MarketingTestCase

BRIEF = '## Campaign Overview\nA yearly care plan.'


class DocumentTimeTests(MarketingTestCase):

    def brief(self, side_effect, clock):
        spring = self.campaign(self.ann, name='Spring till offer')
        agent = DocumentAuthoringAgent()
        with mock.patch.object(DocumentAuthoringAgent, '_call_llm_for_writing', side_effect=side_effect) as llm, \
                mock.patch.object(DocumentAuthoringAgent, '_is_document_structure_valid', return_value=False), \
                mock.patch('marketing_agent.agents.document_authoring_agent.time.monotonic', side_effect=clock):
            result = agent.process('create', self.ann.id, 'brief', {'title': 'Brief'}, campaign_id=spring.id)
        return result, llm

    def test_writing_gets_longer_than_a_question(self):
        agent = DocumentAuthoringAgent()
        with mock.patch.object(DocumentAuthoringAgent, '_call_groq_qa', return_value='ok') as qa:
            agent._call_llm_for_writing('Write it')
            agent._call_llm('Ask it')
        self.assertEqual([c.kwargs['timeout'] for c in qa.call_args_list], [WRITING_TIMEOUT, QA_TIMEOUT])
        self.assertLess(WRITING_TIMEOUT, 60)

    def test_a_slow_first_draft_is_kept_without_a_rewrite(self):
        result, llm = self.brief([BRIEF], clock=[0.0, 40.0])
        self.assertTrue(result['success'], result)
        self.assertEqual(llm.call_count, 1)

    def test_the_rewrite_only_gets_the_time_left(self):
        result, llm = self.brief([BRIEF, BRIEF + '\nRewritten.'], clock=[0.0, 20.0])
        self.assertTrue(result['success'], result)
        self.assertEqual([c.kwargs['timeout'] for c in llm.call_args_list], [WRITING_TIMEOUT, 35.0])
        self.assertIn('Rewritten.', result['content'])

    def test_a_rewrite_that_runs_out_of_time_keeps_the_first_version(self):
        timed_out = RuntimeError('The AI took too long to respond. Please try again.')
        result, llm = self.brief([BRIEF, timed_out], clock=[0.0, 20.0])
        self.assertTrue(result['success'], result)
        self.assertEqual(llm.call_count, 2)
        self.assertIn('Campaign Overview', result['content'])

"""HR Q&A hands the AI every excerpt it found, not the first two.

The excerpts went to the prompt as one block, and the prompt cuts a single
excerpt at 2000 characters, so everything after the first two was dropped.
Asked about working from home and the learning budget, HR answered the first
and said the second was not in the excerpts: it was in the fourth, the
benefits document, behind the new leave policy and the handbook.
"""
from unittest import mock

from django.test import override_settings

from core.HR_agent.hr_agent import HRAgent

from .base import HRTestCase

QUESTION = 'How many days a week can we work from home, and what is the yearly learning budget?'
BUDGET = 'The learning budget is PKR 50,000 a year, approved by your manager.'


def found(title, text, score):
    return {'chunk_id': hash(title) % 1000, 'document_id': 1, 'title': title, 'section_heading': '',
            'page_number': None, 'content': text, 'semantic_score': score}


# What the live site found for that question: three long excerpts, then the benefits one.
RESULTS = [
    found('Leave Policy 2026', 'Carried days must be used by 31 March. ' * 30, 0.437),
    found('Employee Handbook 2026 (Chunk 0)', 'Teams may work from home two days a week. ' * 28, 0.435),
    found('Leave Policy 2026 (Chunk 0)', 'Every employee has 18 days of annual leave. ' * 10, 0.414),
    found('Benefits and Expenses 2026 (Chunk 0)', BUDGET, 0.395),
]


@override_settings(HR_ANSWER_CACHE_TTL_SECONDS=0)
class HRQAExcerptsTests(HRTestCase):

    def setUp(self):
        super().setUp()
        self.agent = HRAgent(company_id=self.company.id)
        search = mock.patch.object(self.agent.knowledge_service, 'search_knowledge', return_value=RESULTS)
        search.start()
        self.addCleanup(search.stop)

    def test_the_answer_sees_the_fourth_excerpt(self):
        with mock.patch.object(HRAgent, '_call_llm', return_value='answer') as llm:
            self.agent.answer_question(QUESTION, asker_role='admin')
        prompt = llm.call_args.kwargs['prompt']
        self.assertIn(BUDGET, prompt)
        self.assertIn('Teams may work from home two days a week.', prompt)

    def test_the_streamed_answer_sees_it_too(self):
        def stream(**kwargs):
            self.prompt = kwargs['prompt']
            yield {'type': 'token', 'value': 'answer'}
        with mock.patch.object(HRAgent, '_call_llm_stream', side_effect=stream):
            list(self.agent.answer_question_stream(QUESTION, asker_role='admin'))
        self.assertIn(BUDGET, self.prompt)

    def test_each_excerpt_is_named_as_its_own_source(self):
        with mock.patch.object(HRAgent, '_call_llm', return_value='answer') as llm:
            self.agent.answer_question(QUESTION, asker_role='admin')
        self.assertIn('--- Source 4: Benefits and Expenses 2026 (Chunk 0) ---', llm.call_args.kwargs['prompt'])

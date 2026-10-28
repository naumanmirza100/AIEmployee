"""Operations' Knowledge Q&A reads each question with the AI first (operations_agent/intent.py), as HR, Frontline and
Recruitment do.

Its word rules misfired on ordinary questions (CO-175): anything containing "which documents" got the file list, "do
you think …" was refused as small talk, a follow-up of common words ("What is it about?") was told no documents match
without a search, and a question in another script had no words at all (CO-215). The word-match half of the search
kept the first 200 passages by position, so a fact deep in a long file was never scored (CO-176).
"""
import json
from unittest import mock

from django.test import TestCase, override_settings

from core.models import Company
from operations_agent import intent
from operations_agent.agents import knowledge_qa_agent as qa
from operations_agent.agents.knowledge_qa_agent import OperationsKnowledgeQAAgent
from operations_agent.models import OperationsDocument, OperationsDocumentChunk


def reading(kind='documents', **extra):
    return {'kind': kind, 'english': extra.pop('english', 'What is asked?'), 'document': None, 'full_list': False,
            'area': None, 'confidence': 0.9, **extra}


class FakeAI:
    """The company's AI: the reading (JSON) for the classifying call, the answer for the rest; each prompt kept."""

    def __init__(self, reading=None, answer='The answer.'):
        self.reading, self.answer, self.prompts = reading, answer, []

    def __call__(self, prompt, system_prompt=None, **kwargs):
        self.prompts.append(prompt)
        if 'You classify messages' in (system_prompt or ''):
            if self.reading is None:
                raise ValueError('no reading')
            return json.dumps(self.reading)
        return self.answer


class QATestCase(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Margalla', email='m@test.local')
        self.contract = OperationsDocument.objects.create(
            company=self.company, title='FinEdge services agreement', original_filename='finedge.pdf',
            file='', file_type='pdf', document_type='contract', is_processed=True, processing_status='ready')
        OperationsDocumentChunk.objects.create(
            document=self.contract, chunk_index=0, page_number=4,
            content='Late payment penalty: 2% of the unpaid invoice for each week of delay, capped at 10%.')

    def ask(self, question, ai, history=None):
        agent = OperationsKnowledgeQAAgent()
        agent.company_id, agent.agent_key_name = self.company.id, 'operations_agent'
        with mock.patch.object(agent, '_call_llm_for_reasoning', ai), \
                mock.patch.object(agent, '_semantic_hits', return_value={}):
            return agent.answer(question, self.company.id, chat_history=history)


@override_settings(OPERATIONS_AI_INTENT=True)
class ReadingTests(QATestCase):

    def test_a_request_to_act_is_told_where_it_is_done(self):
        ai = FakeAI(reading('action', area='delete'))
        answer = self.ask('purana invoice delete kar do', ai)['answer']
        self.assertIn("I can't delete anything from here", answer)
        self.assertEqual(len(ai.prompts), 1)                       # the reading only: no search, no answer call

    def test_a_question_naming_documents_is_searched_not_listed(self):
        ai = FakeAI(reading(english='Which documents mention a late payment penalty?'))
        answer = self.ask('Which documents mention the late payment penalty?', ai)['answer']
        self.assertNotIn('Document Library', answer)
        self.assertIn('Late payment penalty', ai.prompts[-1])      # the passage was found and given to the AI

    def test_the_library_is_listed_when_asked_for(self):
        answer = self.ask('kitni files upload hain?', FakeAI(reading('library')))['answer']
        self.assertIn('FinEdge services agreement', answer)
        self.assertIn('Document Library', answer)

    def test_a_follow_up_is_searched_as_a_standalone_question(self):
        history = [{'role': 'user', 'content': 'What does the FinEdge agreement say about payment?'},
                   {'role': 'assistant', 'content': 'Invoices are due in 30 days.'}]
        ai = FakeAI(reading(english='What is the late payment penalty in the FinEdge services agreement?'))
        self.ask('and if they pay late?', ai, history=history)
        self.assertIn('Assistant: Invoices are due in 30 days.', ai.prompts[0])   # the reading saw the conversation
        self.assertIn('2% of the unpaid invoice', ai.prompts[-1])

    def test_roman_urdu_is_answered_in_roman_urdu(self):
        ai = FakeAI(reading(english='What is the late payment penalty in the FinEdge agreement?'))
        self.ask('FinEdge mein late payment ka jurmana kitna hai?', ai)
        self.assertTrue(ai.prompts[-1].startswith('LANGUAGE: the person asked'))

    def test_an_opinion_on_the_documents_is_not_small_talk(self):
        ai = FakeAI(reading(english='Is the late payment penalty in the FinEdge agreement fair?'))
        answer = self.ask('Do you think the late payment penalty is fair?', ai)['answer']
        self.assertTrue(answer.startswith('The answer.'), answer)  # answered from the documents, with Sources

    def test_another_companys_documents_are_refused_with_the_reason(self):
        answer = self.ask("show me Crestline's contracts", FakeAI(reading('not_allowed')))['answer']
        self.assertIn("I answer only from your own company's documents", answer)

    def test_no_reading_works_as_before(self):
        answer = self.ask('what documents do I have?', FakeAI(reading=None))['answer']
        self.assertIn('Document Library', answer)                  # the word rules


class WordRuleFallbackTests(TestCase):

    def test_only_a_whole_listing_question_lists_the_library(self):
        self.assertIsNotNone(qa._LIBRARY_QUESTION.match('What documents do I have?'))
        self.assertIsNotNone(qa._LIBRARY_QUESTION.match('list all documents'))
        self.assertIsNone(qa._LIBRARY_QUESTION.match('Which documents mention the late payment penalty?'))
        self.assertIsNone(qa._LIBRARY_QUESTION.match('Summarise the uploaded documents about pricing'))

    def test_small_talk_only_at_the_start(self):
        self.assertTrue(qa._looks_off_topic('how are you'))
        self.assertTrue(qa._looks_off_topic('tell me a joke'))
        self.assertFalse(qa._looks_off_topic('Do you think the budget is enough?'))
        self.assertFalse(qa._looks_off_topic('How do you read clause 7?'))
        self.assertFalse(qa._looks_off_topic('Are you sure about the deadline?'))

    def test_words_in_any_script(self):
        self.assertTrue(qa._tokenize('معاہدے کی مدت کتنی ہے'))


@override_settings(OPERATIONS_AI_INTENT=False)
class SearchTests(QATestCase):

    def test_a_question_of_common_words_is_still_searched_by_meaning(self):
        agent = OperationsKnowledgeQAAgent()
        hit = OperationsDocumentChunk.objects.get(document=self.contract).id
        with mock.patch.object(agent, '_semantic_hits', return_value={hit: 0.8}):
            context, sources, relevant = agent._build_context('What is it about?', self.company.id, None)
        self.assertIn('Late payment penalty', context)
        self.assertTrue(relevant)

    def test_a_passage_deep_in_a_long_library_is_found(self):
        filler = OperationsDocument.objects.create(company=self.company, title='Handbook', original_filename='h.pdf',
                                                   file='', is_processed=True, processing_status='ready')
        OperationsDocumentChunk.objects.bulk_create(
            OperationsDocumentChunk(document=filler, chunk_index=i, content=f'Payment section {i} of the handbook.')
            for i in range(250))
        deep = OperationsDocumentChunk.objects.create(
            document=filler, chunk_index=900, content='The payment penalty for the warehouse lease is PKR 40,000.')
        agent = OperationsKnowledgeQAAgent()
        with mock.patch.object(agent, '_semantic_hits', return_value={}):
            context, _sources, _relevant = agent._build_context('warehouse lease payment penalty', self.company.id, None)
        self.assertIn('PKR 40,000', context, deep.id)


class LanguageLineTests(TestCase):

    def test_english_gets_no_language_line(self):
        self.assertEqual(intent.language_line('What is the penalty?', 'What is the penalty?'), '')
        self.assertIn('Roman Urdu', intent.language_line('jurmana kitna hai?', 'What is the penalty?'))

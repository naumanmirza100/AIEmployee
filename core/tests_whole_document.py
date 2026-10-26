"""A question that asks for everything is answered from the documents whole.

HR and Frontline Q&A answer from the few passages that best match a question. On a 245-page prospectus, "list all
the admission categories" named 19 to 21 of 31 and "name all the departments and the subjects they teach" 5 to 12 of
30: the lists run over many pages, and only five or ten passages reach the AI. Given the documents whole, the same
model named all of them. These tests hold the rules for when that happens, and that anything else still answers
from the passages.
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core import whole_document
from core.Frontline_agent.frontline_agent import FrontlineAgent
from core.HR_agent.hr_agent import HRAgent
from core.models import Agent, AgentTokenQuota, Company, CompanyModulePurchase, PlatformAPIKey
from Frontline_agent.models import Document
from hr_agent.models import HRDocument

LIST_QUESTION = 'List all the admission categories, with their codes.'
PLAIN_QUESTION = 'What is category A1?'
CATEGORIES = '\n'.join(f'{code} [seat {n}] Tuition fee rules for {code}.' for n, code in enumerate(
    ['A1', 'A2', 'AP', 'B', 'C', 'D', 'E1', 'E2', 'H1', 'H2', 'J1', 'J2', 'K', 'L', 'M', 'N'], 1))


class WhichQuestionsTests(TestCase):

    def test_questions_that_ask_for_everything(self):
        for question in (LIST_QUESTION, 'List all the departments of the university.',
                         'Name all the departments and the subjects they teach.', 'Can you list every leave type?',
                         'Give me a complete list of the programmes', 'What are all the categories?',
                         'Show me each department and its courses',
                         # Asked in the run-through on 23 Oct, and answered from three passages before this:
                         'how many admission cetagories are there in uet, name them with their descriptions',
                         'How many campuses are there?',
                         'Previous conversation:\nUser: hi\n\nCurrent question: list all the hostels'):
            self.assertTrue(whole_document.asks_for_everything(question), question)

    def test_questions_that_do_not(self):
        for question in (PLAIN_QUESTION, 'Who can get hostel accommodation?',
                         'How many days a week can we work from home, and what is the yearly learning budget?',
                         'Can you tell me if all employees get medical insurance?', 'Do all departments offer a PhD?',
                         'How much does each course cost?',
                         'Previous conversation:\nUser: list all the categories\n\nCurrent question: what is A1?'):
            self.assertFalse(whole_document.asks_for_everything(question), question)


@override_settings(HR_ANSWER_CACHE_TTL_SECONDS=0, FRONTLINE_ANSWER_CACHE_TTL_SECONDS=0)
class WholeDocumentTests(TestCase):

    def setUp(self):
        for slug in ('hr_agent', 'frontline_agent'):
            Agent.objects.update_or_create(slug=slug, defaults={'name': slug, 'default_provider': 'openai'})
        for provider in ('openai', 'groq'):
            key = PlatformAPIKey(provider=provider, status='active', encrypted_key='')
            key.set_plaintext_key(f'{provider}-platform-key-0123456789')
            key.save()
        self.company = Company.objects.create(name='Crestline', email='info@crestline.test')
        self.rival = Company.objects.create(name='Rival', email='info@rival.test')
        self.user = get_user_model().objects.create_user('uploader', 'uploader@crestline.test', 'x')
        for slug in ('hr_agent', 'frontline_agent'):
            CompanyModulePurchase.objects.create(company=self.company, module_name=slug, status='active',
                                                 is_complimentary=True)
            AgentTokenQuota.objects.update_or_create(company=self.company, agent_name=slug,
                                                     defaults={'included_tokens': 30_000_000, 'used_tokens': 0})
        self.prospectus = HRDocument.objects.create(company=self.company, title='Prospectus', file_path='p.pdf',
                                                    processing_status='ready', document_content=CATEGORIES)
        self.handbook = HRDocument.objects.create(company=self.company, title='Handbook', file_path='h.pdf',
                                                  processing_status='ready', document_content='Office hours 9:30.')
        self.unrelated = HRDocument.objects.create(company=self.company, title='Payroll', file_path='x.pdf',
                                                   processing_status='ready', document_content='Salaries: secret.')
        self.theirs = HRDocument.objects.create(company=self.rival, title='Rival rules', file_path='r.pdf',
                                                processing_status='ready', document_content='Rival only.')

    def found(self, *documents):
        """What the HR search returns: excerpts from these documents, most relevant first."""
        return {'success': True, 'has_verified_info': True, 'confidence': 'medium', 'best_score': 0.5,
                'threshold': 0.3, 'answer': 'the joined excerpts',
                'excerpts': [{'title': f'{d.title} (Chunk 0)', 'content': f'excerpt of {d.title}'} for d in documents],
                'citations': [{'type': 'hr_document', 'title': f'{d.title} (Chunk 0)', 'document_id': d.id,
                               'chunk_id': d.id, 'score': 0.5, 'snippet': ''} for d in documents]}

    def hr(self, found):
        agent = HRAgent(company_id=self.company.id)
        patcher = mock.patch.object(agent.knowledge_service, 'get_answer', return_value=found)
        patcher.start()
        self.addCleanup(patcher.stop)
        return agent

    # ---- HR -----------------------------------------------------------------------------------------------

    def test_a_list_question_reads_the_documents_the_search_found(self):
        agent = self.hr(self.found(self.prospectus, self.handbook, self.theirs))
        with mock.patch.object(HRAgent, '_call_llm', return_value='All 16 categories') as llm:
            out = agent.answer_question(LIST_QUESTION, asker_role='hr')
        prompt = llm.call_args.kwargs['prompt']
        self.assertIn(CATEGORIES, prompt)
        self.assertIn('Office hours 9:30.', prompt)
        self.assertNotIn('Salaries: secret.', prompt)       # not found by the search, so not the asker's to see
        self.assertNotIn('Rival only.', prompt)             # another company's, whatever the search said
        self.assertEqual(llm.call_args.kwargs['max_tokens'], 4000)
        self.assertEqual((out['answer'], out['answer_mode']), ('All 16 categories', 'whole_document'))
        self.assertEqual([c['title'] for c in out['citations']],
                         ['Prospectus (whole document)', 'Handbook (whole document)'])
        self.assertIn('whole_document(docs=2', out['timing_ms']['retrieval_path'])

    def test_page_marks_are_given_as_plain_page_lines(self):
        # Seen live: "This list is from the Employee Handbook, page 2 (__PAGE_2__)."
        HRDocument.objects.filter(pk=self.handbook.pk).update(
            document_content='\x0c__PAGE_1__\nOffice hours 9:30.\n\x0c__PAGE_2__\nHolidays: 5 Feb.')
        agent = self.hr(self.found(self.handbook))
        with mock.patch.object(HRAgent, '_call_llm', return_value='Every holiday') as llm:
            agent.answer_question(LIST_QUESTION, asker_role='hr')
        prompt = llm.call_args.kwargs['prompt']
        self.assertIn('[Page 2]\nHolidays: 5 Feb.', prompt)
        self.assertNotIn('__PAGE_2__', prompt)

    def test_an_ordinary_question_still_reads_the_excerpts(self):
        agent = self.hr(self.found(self.prospectus))
        with mock.patch.object(HRAgent, '_call_llm', return_value='A1 is open merit') as llm:
            out = agent.answer_question(PLAIN_QUESTION, asker_role='hr')
        self.assertEqual(llm.call_count, 1)
        self.assertNotIn(CATEGORIES, llm.call_args.kwargs['prompt'])
        self.assertIn('excerpt of Prospectus', llm.call_args.kwargs['prompt'])
        self.assertNotIn('answer_mode', out)

    def test_when_the_whole_document_call_fails_the_excerpts_answer(self):
        agent = self.hr(self.found(self.prospectus))
        with mock.patch.object(HRAgent, '_call_llm', side_effect=[RuntimeError('timeout'), 'from the excerpts']) as llm:
            out = agent.answer_question(LIST_QUESTION, asker_role='hr')
        self.assertEqual(llm.call_count, 2)
        self.assertEqual(out['answer'], 'from the excerpts')
        self.assertEqual(out['citations'][0]['title'], 'Prospectus (Chunk 0)')

    def test_not_with_a_provider_that_reads_little(self):
        Agent.objects.filter(slug='hr_agent').update(default_provider='groq')
        agent = self.hr(self.found(self.prospectus))
        with mock.patch.object(HRAgent, '_call_llm', return_value='from the excerpts') as llm:
            agent.answer_question(LIST_QUESTION, asker_role='hr')
        self.assertEqual(llm.call_count, 1)
        self.assertNotIn(CATEGORIES, llm.call_args.kwargs['prompt'])

    def test_not_when_the_allowance_would_not_cover_it(self):
        # 100,000 free tokens with 95,000 used: the 4,000-token answer alone would not fit.
        AgentTokenQuota.objects.filter(company=self.company, agent_name='hr_agent').update(
            included_tokens=100_000, used_tokens=95_000)
        agent = self.hr(self.found(self.prospectus))
        with mock.patch.object(HRAgent, '_call_llm', return_value='from the excerpts') as llm:
            agent.answer_question(LIST_QUESTION, asker_role='hr')
        self.assertNotIn(CATEGORIES, llm.call_args.kwargs['prompt'])

    @override_settings(KQA_WHOLE_DOCUMENT_MAX_TOKENS=6000)
    def test_not_when_the_most_relevant_document_is_too_big(self):
        HRDocument.objects.filter(pk=self.prospectus.pk).update(document_content='x' * 40_000)   # about 10,000 tokens
        agent = self.hr(self.found(self.prospectus, self.handbook))
        with mock.patch.object(HRAgent, '_call_llm', return_value='from the excerpts') as llm:
            agent.answer_question(LIST_QUESTION, asker_role='hr')
        self.assertNotIn('Office hours 9:30.', llm.call_args.kwargs['prompt'])   # not the lesser one instead

    @override_settings(KQA_WHOLE_DOCUMENT=False)
    def test_it_can_be_switched_off(self):
        agent = self.hr(self.found(self.prospectus))
        with mock.patch.object(HRAgent, '_call_llm', return_value='from the excerpts') as llm:
            agent.answer_question(LIST_QUESTION, asker_role='hr')
        self.assertNotIn(CATEGORIES, llm.call_args.kwargs['prompt'])

    def test_the_streamed_answer_reads_them_too(self):
        agent = self.hr(self.found(self.prospectus))
        seen = {}

        def stream(**kwargs):
            seen['prompt'] = kwargs['prompt']
            yield {'type': 'token', 'value': 'All 16'}
        with mock.patch.object(HRAgent, '_call_llm_stream', side_effect=stream):
            events = list(agent.answer_question_stream(LIST_QUESTION, asker_role='hr'))
        self.assertIn(CATEGORIES, seen['prompt'])
        metas = [e for e in events if e['type'] == 'meta']
        self.assertEqual([c['title'] for c in metas[-1]['citations']], ['Prospectus (whole document)'])
        self.assertEqual(events[-1]['answer'], 'All 16')
        self.assertIn('whole_document(docs=1', events[-1]['timing_ms']['retrieval_path'])

    def test_a_stream_that_fails_before_any_text_falls_back_with_the_excerpts_sources(self):
        agent = self.hr(self.found(self.prospectus))
        calls = []

        def stream(**kwargs):
            calls.append(kwargs['prompt'])
            if len(calls) == 1:
                yield {'type': 'error', 'message': 'context too long'}
                return
            yield {'type': 'token', 'value': 'from the excerpts'}
        with mock.patch.object(HRAgent, '_call_llm_stream', side_effect=stream):
            events = list(agent.answer_question_stream(LIST_QUESTION, asker_role='hr'))
        self.assertEqual(len(calls), 2)
        self.assertNotIn('error', [e['type'] for e in events])
        metas = [e for e in events if e['type'] == 'meta']
        self.assertEqual(metas[-1]['citations'][0]['title'], 'Prospectus (Chunk 0)')
        self.assertEqual(events[-1]['answer'], 'from the excerpts')

    def test_a_stream_that_fails_after_text_is_shown_says_so(self):
        agent = self.hr(self.found(self.prospectus))

        def stream(**kwargs):
            yield {'type': 'token', 'value': 'A1, A2, '}
            yield {'type': 'error', 'message': 'connection reset'}
        with mock.patch.object(HRAgent, '_call_llm_stream', side_effect=stream) as llm:
            events = list(agent.answer_question_stream(LIST_QUESTION, asker_role='hr'))
        self.assertEqual(llm.call_count, 1)
        self.assertEqual(events[-1], {'type': 'error', 'message': 'connection reset'})

    # ---- Frontline ----------------------------------------------------------------------------------------

    def frontline(self, *documents):
        agent = FrontlineAgent(company_id=self.company.id)
        found = {'success': True, 'has_verified_info': True, 'confidence': 'medium', 'best_score': 0.5,
                 'threshold': 0.3, 'type': 'document', 'answer': 'the joined chunks',
                 'citations': [{'type': 'document', 'title': f'{d.title} (Chunk 0)', 'document_id': d.id,
                                'chunk_id': d.id, 'score': 0.5, 'snippet': ''} for d in documents]}
        patcher = mock.patch.object(agent.knowledge_service, 'get_answer', return_value=found)
        patcher.start()
        self.addCleanup(patcher.stop)
        return agent

    def frontline_document(self, title, text, company=None):
        return Document.objects.create(title=title, file_path=f'{title}.pdf', company=company or self.company,
                                       uploaded_by=self.user, processing_status='ready', document_content=text)

    def test_frontline_reads_the_documents_whole_for_a_list_question(self):
        guide = self.frontline_document('Prospectus', CATEGORIES)
        theirs = self.frontline_document('Rival rules', 'Rival only.', company=self.rival)
        agent = self.frontline(guide, theirs)
        with mock.patch.object(FrontlineAgent, '_call_llm', return_value='All 16 categories') as llm:
            out = agent.answer_question(LIST_QUESTION, company_id=self.company.id)
        self.assertIn(CATEGORIES, llm.call_args.kwargs['prompt'])
        self.assertNotIn('Rival only.', llm.call_args.kwargs['prompt'])
        self.assertEqual(out['answer_mode'], 'whole_document')
        self.assertEqual([c['title'] for c in out['citations']], ['Prospectus (whole document)'])

    def test_frontline_streams_it_too_and_falls_back_before_any_text(self):
        guide = self.frontline_document('Prospectus', CATEGORIES)
        agent = self.frontline(guide)
        calls = []

        def stream(**kwargs):
            calls.append(kwargs['prompt'])
            if len(calls) == 1:
                raise RuntimeError('timeout')
            yield {'type': 'token', 'value': 'from the chunks'}
        with mock.patch.object(FrontlineAgent, '_call_llm_stream', side_effect=stream):
            events = list(agent.answer_question_stream(LIST_QUESTION, company_id=self.company.id))
        self.assertIn(CATEGORIES, calls[0])
        self.assertEqual(len(calls), 2)
        metas = [e for e in events if e['type'] == 'meta']
        self.assertEqual(metas[0]['citations'][0]['title'], 'Prospectus (whole document)')
        self.assertEqual(metas[-1]['citations'][0]['title'], 'Prospectus (Chunk 0)')
        self.assertEqual(events[-1]['answer'], 'from the chunks')

    def test_frontline_answers_an_ordinary_question_from_the_chunks(self):
        guide = self.frontline_document('Prospectus', CATEGORIES)
        agent = self.frontline(guide)
        with mock.patch.object(FrontlineAgent, '_call_llm', return_value='A1 is open merit') as llm:
            out = agent.answer_question(PLAIN_QUESTION, company_id=self.company.id)
        self.assertEqual(llm.call_count, 1)
        self.assertNotIn(CATEGORIES, llm.call_args.kwargs['prompt'])
        self.assertNotIn('answer_mode', out)

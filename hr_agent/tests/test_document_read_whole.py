"""HR's Summarize and Extract read the whole document, keep their result, and only for those who may read it.

- They read the first 12,000 characters, so a long policy's summary described its opening pages and a contract's
  fields near its end were missed. Now as Frontline (core/tests_document_read_whole.py): the whole document when it
  fits one call, otherwise passages from all through it, and a note.
- Reading whole is one large call, so the result is kept on the document (HRDocument.ai_results) until its text
  changes.
- The document view, Summarize and Extract checked the company only: any login could read another person's payslip
  or contract by its number. They now keep to the list's rule (confidentiality by role; below HR, only the
  company's general documents and the person's own).
"""
from unittest import mock

from django.test import TestCase

from api.views import hr_agent as views
from core.HR_agent.hr_agent import HRAgent
from core.models import Agent, AgentTokenQuota, Company, CompanyModulePurchase, PlatformAPIKey
from core.tests_document_read_whole import long_text
from hr_agent.models import HRDocument

from .base import HRTestCase

SUMMARIZE = 'core.HR_agent.hr_agent.HRAgent.summarize_document'
EXTRACT = 'core.HR_agent.hr_agent.HRAgent.extract_from_document'


class HRReadsTheWholeDocumentTests(TestCase):

    def setUp(self):
        Agent.objects.update_or_create(slug='hr_agent', defaults={'name': 'hr_agent', 'default_provider': 'openai'})
        for provider in ('openai', 'groq'):
            key = PlatformAPIKey(provider=provider, status='active', encrypted_key='')
            key.set_plaintext_key(f'{provider}-platform-key-0123456789')
            key.save()
        company = Company.objects.create(name='Margalla', email='hr@margalla.test')
        CompanyModulePurchase.objects.create(company=company, module_name='hr_agent', status='active',
                                             is_complimentary=True)
        AgentTokenQuota.objects.update_or_create(company=company, agent_name='hr_agent',
                                                 defaults={'included_tokens': 30_000_000, 'used_tokens': 0})
        self.agent = HRAgent(company_id=company.id)

    def test_a_long_policy_is_summarized_to_its_last_page(self):
        with mock.patch.object(HRAgent, '_call_llm', return_value='Leave and pay rules.') as llm:
            result = self.agent.summarize_document(long_text(300_000))
        prompt = llm.call_args.kwargs['prompt']
        self.assertIn('END-OF-DOCUMENT', prompt)                # it stopped at 12,000 characters
        self.assertIn('given in full', prompt)
        self.assertEqual((result['summary'], result['note']), ('Leave and pay rules.', ''))

    def test_a_contracts_fields_near_its_end_are_read(self):
        contract = long_text(60_000) + '\nSalary: PKR 450,000 a month. Probation: 3 months.'
        with mock.patch.object(HRAgent, '_call_llm', return_value='{"compensation": "PKR 450,000"}') as llm:
            result = self.agent.extract_from_document(contract)
        self.assertIn('Salary: PKR 450,000', llm.call_args.kwargs['prompt'])
        self.assertEqual(result['data'], {'compensation': 'PKR 450,000'})

    def test_a_provider_that_reads_little_gets_passages_and_a_note(self):
        Agent.objects.filter(slug='hr_agent').update(default_provider='groq')
        with mock.patch.object(HRAgent, '_call_llm', return_value='Rules.') as llm:
            result = self.agent.summarize_document(long_text(300_000))
        self.assertIn('END-OF-DOCUMENT', llm.call_args.kwargs['prompt'])
        self.assertIn('passages from all through it', result['note'])


class HRDocumentReadersAndKeptResultsTests(HRTestCase):

    def setUp(self):
        super().setUp()
        def doc(title, **fields):
            fields.setdefault('confidentiality', 'employee')
            return HRDocument.objects.create(company=self.company, title=title, processing_status='ready',
                                             document_content=f'{title}: the text.', **fields)
        self.handbook = doc('Handbook')
        self.payroll = doc('Payroll', confidentiality='hr_only')
        self.dana_contract = doc("Dana's contract", employee=self.admin_emp, document_type='contract')
        self.mo_offer = doc("Mo's offer letter", employee=self.member_emp, document_type='offer_letter')
        self.theirs = HRDocument.objects.create(company=self.rival, title='Rival', processing_status='ready',
                                                document_content='Rival text.')

    def read(self, actor, document):
        return self.call(views.get_hr_document, actor, method='get', document_id=document.id)

    def summarize(self, actor, document, data=None):
        return self.call(views.summarize_hr_document, actor, data or {}, document_id=document.id)

    def extract(self, actor, document, data=None):
        return self.call(views.extract_hr_document, actor, data or {}, document_id=document.id)

    # ---- who may read ---------------------------------------------------------------------------------------

    def test_a_member_cannot_read_hr_only_or_someone_elses_documents(self):
        for document in (self.payroll, self.dana_contract, self.theirs):
            with self.subTest(document=document.title), mock.patch(SUMMARIZE) as ai, mock.patch(EXTRACT) as ex:
                code, body = self.read(self.member, document)
                self.assertEqual(code, 404)
                self.assertNotIn('the text', str(body))
                self.assertEqual(self.summarize(self.member, document)[0], 404)
                self.assertEqual(self.extract(self.member, document)[0], 404)
                ai.assert_not_called()
                ex.assert_not_called()

    def test_a_member_reads_the_general_documents_and_their_own(self):
        for document in (self.handbook, self.mo_offer):
            with self.subTest(document=document.title):
                code, body = self.read(self.member, document)
                self.assertEqual((code, body['data']['document_content']), (200, f'{document.title}: the text.'))

    def test_hr_reads_them_all(self):
        for document in (self.handbook, self.payroll, self.dana_contract, self.mo_offer):
            with self.subTest(document=document.title):
                self.assertEqual(self.read(self.admin, document)[0], 200)
        self.assertEqual(self.read(self.admin, self.theirs)[0], 404)

    def test_the_list_keeps_its_rule(self):
        code, body = self.call(views.list_hr_documents, self.member, method='get')
        self.assertEqual(code, 200, body)
        rows = body['data'] if isinstance(body.get('data'), list) else body['data'].get('documents', body['data'])
        titles = sorted(r['title'] for r in rows)
        self.assertEqual(titles, ['Handbook', "Mo's offer letter"])

    # ---- kept results -----------------------------------------------------------------------------------------

    def test_a_summary_is_made_once_and_kept_until_the_text_changes(self):
        with mock.patch(SUMMARIZE, return_value={'success': True, 'summary': 'Leave: 18 days.', 'note': ''}) as ai:
            first = self.summarize(self.member, self.handbook)
            again = self.summarize(self.member, self.handbook)
        self.assertEqual(ai.call_count, 1)
        self.assertEqual(first, again)
        self.assertEqual(again[1]['data']['summary'], 'Leave: 18 days.')
        HRDocument.objects.filter(pk=self.handbook.pk).update(document_content='Leave: 20 days a year.')
        with mock.patch(SUMMARIZE, return_value={'success': True, 'summary': 'Leave: 20 days.', 'note': ''}) as ai:
            self.assertEqual(self.summarize(self.member, self.handbook)[1]['data']['summary'], 'Leave: 20 days.')
        ai.assert_called_once()

    def test_the_note_reaches_the_screen_and_a_bad_number_of_sentences_is_not_an_error(self):
        note = 'This document is too long to read whole here, so this is based on passages from all through it.'
        with mock.patch(SUMMARIZE, return_value={'success': True, 'summary': 'S.', 'note': note}) as ai:
            code, body = self.summarize(self.admin, self.payroll, {'max_sentences': 'many'})
        self.assertEqual((code, body['data']['note']), (200, note))
        self.assertEqual(ai.call_args.kwargs['max_sentences'], 5)

    def test_an_extraction_is_kept_and_its_fields_saved_once(self):
        found = {'success': True, 'data': {'job_title': 'Designer'}, 'note': ''}
        with mock.patch(EXTRACT, return_value=found) as ai:
            for _ in range(2):
                code, body = self.extract(self.admin, self.dana_contract)
                self.assertEqual((code, body['data']['extracted']), (200, {'job_title': 'Designer'}))
        self.assertEqual(ai.call_count, 1)
        self.dana_contract.refresh_from_db()
        self.assertEqual(self.dana_contract.extracted_fields, {'job_title': 'Designer'})

    def test_a_failed_summary_is_not_kept(self):
        with mock.patch(SUMMARIZE, side_effect=[{'success': False, 'error': 'No answer'},
                                                {'success': True, 'summary': 'Now.', 'note': ''}]):
            self.assertEqual(self.summarize(self.admin, self.handbook)[0], 500)
            self.assertEqual(self.summarize(self.admin, self.handbook)[1]['data']['summary'], 'Now.')

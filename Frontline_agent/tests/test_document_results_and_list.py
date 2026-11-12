"""Frontline documents: kept summaries, private documents, and every document in the Documents tab.

- Summarize and Extract read the whole document now (core/tests_document_read_whole.py), so a result is kept on
  the document until its text changes: the card asked again on every page load.
- A private document's text was open to anyone in the company through the document view, Summarize and Extract;
  the AI's answers already kept to its list of people.
- The Documents tab showed the dashboard's newest 10 documents only; it now pages through the list endpoint, which
  took `page` only, had no ceiling on `limit` and answered 500 to a bad number.
"""
from unittest import mock

from api.views import frontline_agent as views
from Frontline_agent.models import Document

from .base import FrontlineTestCase

SUMMARIZE = 'core.Frontline_agent.frontline_agent.FrontlineAgent.summarize_document'
EXTRACT = 'core.Frontline_agent.frontline_agent.FrontlineAgent.extract_from_document'


class KeptResultsTests(FrontlineTestCase):

    def setUp(self):
        super().setUp()
        self.doc = Document.objects.create(title='Prospectus', file_path='p.pdf', company=self.company,
                                           uploaded_by=self.admin_user, processing_status='ready',
                                           document_content='Fees are due by the 10th of each month.')

    def summarize(self, options=None, actor=None):
        return self.call(views.summarize_document, actor or self.member, options or {}, document_id=self.doc.id)

    def test_a_summary_is_made_once_and_kept_until_the_text_changes(self):
        made = {'success': True, 'summary': 'Fees are due by the 10th.', 'note': ''}
        with mock.patch(SUMMARIZE, return_value=made) as ai:
            first = self.summarize()
            again = self.summarize()
        self.assertEqual(ai.call_count, 1)
        self.assertEqual(first, again)
        self.assertEqual(again[1]['data']['summary'], 'Fees are due by the 10th.')

        Document.objects.filter(pk=self.doc.pk).update(document_content='Fees are due by the 5th.')
        with mock.patch(SUMMARIZE, return_value={'success': True, 'summary': 'By the 5th.', 'note': ''}) as ai:
            code, body = self.summarize()
        ai.assert_called_once()
        self.assertEqual(body['data']['summary'], 'By the 5th.')

    def test_the_short_and_the_full_summary_are_kept_apart(self):
        with mock.patch(SUMMARIZE, side_effect=[{'success': True, 'summary': 'Short.', 'note': ''},
                                                {'success': True, 'summary': 'Full.', 'note': ''}]) as ai:
            short = self.summarize({'max_sentences': 3})[1]['data']['summary']
            full = self.summarize()[1]['data']['summary']
            self.assertEqual((short, full), ('Short.', 'Full.'))
            self.assertEqual(self.summarize({'max_sentences': 3})[1]['data']['summary'], 'Short.')
        self.assertEqual(ai.call_count, 2)

    def test_a_failed_summary_is_not_kept(self):
        with mock.patch(SUMMARIZE, side_effect=[{'success': False, 'error': 'The AI did not answer'},
                                                {'success': True, 'summary': 'Now it did.', 'note': ''}]):
            self.assertEqual(self.summarize()[0], 500)
            self.assertEqual(self.summarize()[1]['data']['summary'], 'Now it did.')

    def test_the_note_about_passages_reaches_the_screen(self):
        note = 'This document is too long to read whole here, so this is based on passages from all through it.'
        with mock.patch(SUMMARIZE, return_value={'success': True, 'summary': 'S.', 'note': note}):
            self.assertEqual(self.summarize()[1]['data']['note'], note)
        with mock.patch(EXTRACT, return_value={'success': True, 'data': {'parties': []}, 'note': note}):
            code, body = self.call(views.extract_document, self.member, {}, document_id=self.doc.id)
        self.assertEqual((code, body['data']['note']), (200, note))

    def test_extractions_are_kept_per_list_of_fields(self):
        with mock.patch(EXTRACT, return_value={'success': True, 'data': {'dates': ['10th']}, 'note': ''}) as ai:
            for _ in range(2):
                self.call(views.extract_document, self.member, {'schema': ['dates']}, document_id=self.doc.id)
            self.call(views.extract_document, self.member, {}, document_id=self.doc.id)
        self.assertEqual(ai.call_count, 2)

    def test_keeping_a_result_does_not_touch_updated_at_or_other_settings(self):
        Document.objects.filter(pk=self.doc.pk).update(processed_data={'chunk_size': 900})
        self.doc.refresh_from_db()
        before = self.doc.updated_at
        with mock.patch(SUMMARIZE, return_value={'success': True, 'summary': 'S.', 'note': ''}):
            self.summarize()
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.updated_at, before)       # how a stuck document is found
        self.assertEqual(self.doc.processed_data['chunk_size'], 900)


class PrivateDocumentTests(FrontlineTestCase):

    def setUp(self):
        super().setUp()
        self.private = Document.objects.create(title='Salaries', file_path='s.pdf', company=self.company,
                                               uploaded_by=self.admin_user, processing_status='ready',
                                               visibility='private', document_content='Salaries: secret.')
        self.private.allowed_users.add(self.admin)

    def test_someone_not_on_the_list_cannot_read_it(self):
        for view in (views.summarize_document, views.extract_document):
            with self.subTest(view=view.__name__), mock.patch(SUMMARIZE) as ai, mock.patch(EXTRACT) as ex:
                code, _ = self.call(view, self.member, {}, document_id=self.private.id)
                self.assertEqual(code, 404)
                ai.assert_not_called()
                ex.assert_not_called()
        code, body = self.call(views.get_document, self.member, method='get', document_id=self.private.id)
        self.assertEqual(code, 404)
        self.assertNotIn('secret', str(body))

    def test_someone_on_the_list_can(self):
        with mock.patch(SUMMARIZE, return_value={'success': True, 'summary': 'Pay bands.', 'note': ''}):
            code, body = self.call(views.summarize_document, self.admin, {}, document_id=self.private.id)
        self.assertEqual((code, body['data']['summary']), (200, 'Pay bands.'))
        code, body = self.call(views.get_document, self.admin, method='get', document_id=self.private.id)
        self.assertEqual((code, body['data']['document_content']), (200, 'Salaries: secret.'))

    def test_another_companys_document_is_not_found_in_the_document_view(self):
        theirs = Document.objects.create(title='Theirs', file_path='t.pdf', company=self.rival,
                                         uploaded_by=self.rival_user, processing_status='ready')
        self.assertEqual(self.call(views.get_document, self.admin, method='get', document_id=theirs.id)[0], 404)


class DocumentsListTests(FrontlineTestCase):

    def setUp(self):
        super().setUp()
        for n in range(35):
            Document.objects.create(title=f'Doc {n:02d}', file_path=f'{n}.pdf', company=self.company,
                                    uploaded_by=self.admin_user, processing_status='ready', is_outdated=(n == 0))
        Document.objects.create(title='Theirs', file_path='t.pdf', company=self.rival, uploaded_by=self.rival_user)

    def page(self, **params):
        code, body = self.call(views.list_documents, self.member, params, method='get')
        self.assertEqual(code, 200, body)
        return body['data']

    def test_every_document_can_be_reached_a_page_at_a_time(self):
        first = self.page(offset=0, limit=30)
        rest = self.page(offset=30, limit=30)
        self.assertEqual((first['total'], len(first['documents']), len(rest['documents'])), (35, 30, 5))
        titles = [d['title'] for d in first['documents'] + rest['documents']]
        self.assertEqual(len(set(titles)), 35)
        self.assertNotIn('Theirs', titles)

    def test_the_cards_get_what_they_show(self):
        docs = {d['title']: d for d in self.page(limit=200)['documents']}
        self.assertTrue(docs['Doc 00']['is_outdated'])            # the card's Outdated / Restore
        self.assertFalse(docs['Doc 01']['is_outdated'])
        for field in ('processing_status', 'processing_error', 'file_size', 'created_at', 'document_type'):
            self.assertIn(field, docs['Doc 01'])

    def test_pages_by_number_still_work(self):
        self.assertEqual(len(self.page(page=2, limit=20)['documents']), 15)

    def test_bad_numbers_fall_back_and_a_page_has_a_ceiling(self):
        data = self.page(limit='lots', page='x', offset='y')
        self.assertEqual((data['limit'], data['offset'], len(data['documents'])), (20, 0, 20))
        self.assertEqual(self.page(limit=100000)['limit'], 200)

"""Summarize and Extract say why a document has no text yet.

The text is saved when the background job has read the file: about two minutes for a 10 MB PDF on the live
site (12 Nov 2026). Pressed in that time, Summarize answered "Document has no text content to summarize", which
read as if the file were empty; a minute later the same button worked.
"""
from unittest import mock

from api.views import frontline_agent as views
from Frontline_agent.models import Document

from .base import FrontlineTestCase


class DocumentNotReadYetTests(FrontlineTestCase):

    def doc(self, state, content='', **extra):
        return Document.objects.create(title=f'{state} doc', file_path='x.pdf', company=self.company,
                                       uploaded_by=self.admin_user, processing_status=state,
                                       document_content=content, **extra)

    def summarize(self, doc):
        return self.call(views.summarize_document, self.member, {}, document_id=doc.id)

    def extract(self, doc):
        return self.call(views.extract_document, self.member, {}, document_id=doc.id)

    def test_a_document_still_being_read_says_so_and_to_wait(self):
        for state in ('pending', 'processing'):
            with self.subTest(state=state):
                code, body = self.summarize(self.doc(state))
                self.assertEqual(code, 409, body)
                self.assertEqual(body['processing_status'], state)
                self.assertIn('still being read', body['message'])
                self.assertIn('Indexed', body['message'])
                self.assertNotIn('no text content', body['message'])

    def test_extract_says_the_same(self):
        code, body = self.extract(self.doc('processing'))
        self.assertEqual(code, 409)
        self.assertIn('still being read', body['message'])

    def test_a_document_that_failed_gives_the_reason_and_retry(self):
        code, body = self.summarize(self.doc('failed', processing_error='The file could not be opened'))
        self.assertEqual(code, 400)
        self.assertIn('could not be read (The file could not be opened)', body['message'])
        self.assertIn('Retry', body['message'])

    def test_a_read_document_without_text_says_no_text_was_found(self):
        code, body = self.summarize(self.doc('ready'))
        self.assertEqual(code, 400)
        self.assertIn('No text could be read', body['message'])

    def test_once_the_text_is_saved_it_summarizes_even_while_still_indexing(self):
        # The text is saved before the parts are embedded, so Summarize works from then on.
        doc = self.doc('processing', content='Fees are due by the 10th of each month.')
        with mock.patch('core.Frontline_agent.frontline_agent.FrontlineAgent.summarize_document',
                        return_value={'success': True, 'summary': 'Fees are due by the 10th.'}) as summarize:
            code, body = self.summarize(doc)
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data']['summary'], 'Fees are due by the 10th.')
        summarize.assert_called_once()

    def test_another_companys_document_is_not_found(self):
        # It was a 500: the catch-all turned the 404 into "Failed to summarize document".
        theirs = Document.objects.create(title='theirs', file_path='x.pdf', company=self.rival,
                                         uploaded_by=self.rival_user, processing_status='ready',
                                         document_content='Their text.')
        self.assertEqual(self.summarize(theirs)[0], 404)
        self.assertEqual(self.extract(theirs)[0], 404)

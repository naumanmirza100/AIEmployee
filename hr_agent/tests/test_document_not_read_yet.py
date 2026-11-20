"""HR's Summarize and Extract wait until a document has been read (19 Nov 2026), as Frontline's do since 12 Nov.

A browser check on a local copy found HR still answering "Document has no extracted text yet" (400, a red error) for a
document the background job was still reading, and the buttons clickable. The server now says it is still being read
(409), or why it couldn't be read and to press Retry, with the same words as Frontline (api/documents.py).
"""
from unittest import mock

from api.views import hr_agent as views
from hr_agent.models import HRDocument

from .base import HRTestCase
from .test_document_read_whole import EXTRACT, SUMMARIZE


class NotReadYetTests(HRTestCase):

    def document(self, state, **fields):
        return HRDocument.objects.create(company=self.company, title=f'Policy ({state})', confidentiality='employee',
                                         processing_status=state, document_content='', **fields)

    def ask(self, view, document):
        with mock.patch(SUMMARIZE) as summarize, mock.patch(EXTRACT) as extract:
            code, body = self.call(view, self.admin, {}, document_id=document.id)
            summarize.assert_not_called()
            extract.assert_not_called()
        return code, body

    def test_a_document_being_read_is_still_being_read(self):
        for state in ('pending', 'processing'):
            document = self.document(state)
            for view, action in ((views.summarize_hr_document, 'summarized'), (views.extract_hr_document, 'read for data')):
                with self.subTest(state=state, action=action):
                    code, body = self.ask(view, document)
                    self.assertEqual(code, 409, body)
                    self.assertIn(f"still being read, so it can't be {action} yet", body['message'])
                    self.assertEqual(body['processing_status'], state)

    def test_a_document_that_could_not_be_read_says_why_and_to_retry(self):
        code, body = self.ask(views.summarize_hr_document, self.document('failed', processing_error='Not a PDF'))
        self.assertEqual(code, 400)
        self.assertEqual(body['message'], 'This document could not be read (Not a PDF). Press Retry on its card.')

    def test_a_read_document_without_text(self):
        code, body = self.ask(views.extract_hr_document, self.document('ready'))
        self.assertEqual(code, 400)
        self.assertIn('No text could be read from this document', body['message'])

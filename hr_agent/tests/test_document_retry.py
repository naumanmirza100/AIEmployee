"""Retrying a failed HR document (the re-ingest endpoint behind Retry).

It dispatched with a bare `.delay()`, which hangs ~100s when the broker is
down, and would start a second run over one still in progress. The
stuck-document check itself is covered in
Frontline_agent/tests/test_stuck_documents.py, which checks both agents.
"""
from unittest import mock

from api.views import hr_agent as views
from hr_agent.models import HRDocument, HRDocumentChunk

from .base import HRTestCase


class HRDocumentRetryTests(HRTestCase):

    def doc(self, status, company=None):
        return HRDocument.objects.create(title='Handbook', file_path='x.pdf',
                                         company=company or self.company, processing_status=status,
                                         processing_error='boom' if status == 'failed' else '')

    def retry(self, doc, actor=None):
        return self.call(views.reingest_hr_document, actor or self.admin, document_id=doc.id)

    @mock.patch.object(views, '_hr_dispatch_document_processing', return_value='async')
    def test_retry_requeues_a_failed_document_from_a_clean_slate(self, dispatch):
        failed = self.doc('failed')
        HRDocumentChunk.objects.create(document=failed, chunk_index=0, chunk_text='stale')
        code, body = self.retry(failed)
        self.assertEqual(code, 200, body)
        dispatch.assert_called_once()
        failed.refresh_from_db()
        self.assertEqual((failed.processing_status, failed.processing_error), ('pending', ''))
        self.assertFalse(HRDocumentChunk.objects.filter(document=failed).exists())

    @mock.patch.object(views, '_hr_dispatch_document_processing', return_value='async')
    def test_retry_is_refused_while_it_is_really_still_processing(self, dispatch):
        code, body = self.retry(self.doc('processing'))
        self.assertEqual((code, body['code']), (409, 'still_processing'))
        dispatch.assert_not_called()

    def test_retry_processes_inline_when_the_broker_is_down(self):
        with mock.patch.object(views, '_hr_celery_broker_ready', return_value=False), \
                mock.patch('hr_agent.tasks.process_hr_document.apply') as apply, \
                mock.patch('hr_agent.tasks.process_hr_document.delay') as delay:
            code, body = self.retry(self.doc('failed'))
        self.assertEqual(code, 200)
        self.assertEqual(body['data']['dispatch_mode'], 'inline')
        apply.assert_called_once()
        delay.assert_not_called()

    def test_still_hr_admins_only(self):
        code, _ = self.retry(self.doc('failed'), actor=self.member)
        self.assertEqual(code, 403)

    def test_another_companys_document_is_not_found(self):
        code, _ = self.retry(self.doc('failed', company=self.rival))
        self.assertEqual(code, 404)

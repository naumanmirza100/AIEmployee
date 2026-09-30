"""A document can no longer sit on "processing" forever, and can be retried.

When the queue was reachable but no worker took the job, or a worker died
partway, nothing ever updated the row. There was also no Retry: the existing
re-ingest endpoint wasn't wired to any button, and it dispatched with a bare
`.delay()` that hangs ~100s when the broker is down.
"""
from datetime import timedelta
from unittest import mock

from django.utils import timezone

from api.views import frontline_agent as views
from core.tasks import DOCUMENT_STALL_MINUTES, fail_stalled_documents
from Frontline_agent.models import Document, DocumentChunk
from hr_agent.models import HRDocument

from .base import FrontlineTestCase


class StuckDocumentTests(FrontlineTestCase):

    def doc(self, status, minutes_ago=0, model=Document, **extra):
        if model is Document:
            d = Document.objects.create(title=f'{status} doc', file_path='x.pdf', company=self.company,
                                        uploaded_by=self.admin_user, processing_status=status, **extra)
        else:
            d = HRDocument.objects.create(title=f'{status} doc', file_path='x.pdf', company=self.company,
                                          processing_status=status, **extra)
        # `updated_at` is auto_now; only a queryset update can put it in the past.
        model.objects.filter(pk=d.pk).update(updated_at=timezone.now() - timedelta(minutes=minutes_ago))
        d.refresh_from_db()
        return d

    # ---- the stuck-document check -----------------------------------------------

    def test_a_document_stuck_processing_is_failed_with_a_reason(self):
        stuck = self.doc('processing', DOCUMENT_STALL_MINUTES + 1)
        never = self.doc('pending', DOCUMENT_STALL_MINUTES + 1)
        fail_stalled_documents()
        stuck.refresh_from_db(); never.refresh_from_db()
        self.assertEqual((stuck.processing_status, never.processing_status), ('failed', 'failed'))
        self.assertIn('stopped before it finished', stuck.processing_error)
        self.assertIn('never started', never.processing_error)
        self.assertIn('Retry', stuck.processing_error)

    def test_work_still_making_progress_is_left_alone(self):
        busy = self.doc('processing', DOCUMENT_STALL_MINUTES - 5)
        done = self.doc('ready', 600)
        fail_stalled_documents()
        busy.refresh_from_db(); done.refresh_from_db()
        self.assertEqual((busy.processing_status, done.processing_status), ('processing', 'ready'))

    def test_hr_documents_are_checked_too(self):
        stuck = self.doc('processing', DOCUMENT_STALL_MINUTES + 1, model=HRDocument)
        fail_stalled_documents()
        stuck.refresh_from_db()
        self.assertEqual(stuck.processing_status, 'failed')

    # ---- Retry --------------------------------------------------------------

    def retry(self, doc):
        return self.call(views.reingest_document, self.member, document_id=doc.id)

    @mock.patch.object(views, '_dispatch_document_processing', return_value='async')
    def test_retry_requeues_a_failed_document_from_a_clean_slate(self, dispatch):
        failed = self.doc('failed', processing_error='boom')
        DocumentChunk.objects.create(document=failed, chunk_index=0, chunk_text='stale')
        code, body = self.retry(failed)
        self.assertEqual(code, 200, body)
        dispatch.assert_called_once()
        failed.refresh_from_db()
        self.assertEqual((failed.processing_status, failed.processing_error), ('pending', ''))
        self.assertFalse(DocumentChunk.objects.filter(document=failed).exists())

    @mock.patch.object(views, '_dispatch_document_processing', return_value='async')
    def test_retry_is_refused_while_it_is_really_still_processing(self, dispatch):
        code, body = self.retry(self.doc('processing', 2))
        self.assertEqual((code, body['code']), (409, 'still_processing'))
        dispatch.assert_not_called()

    @mock.patch.object(views, '_dispatch_document_processing', return_value='async')
    def test_but_allowed_once_it_is_stuck(self, dispatch):
        code, _ = self.retry(self.doc('processing', DOCUMENT_STALL_MINUTES + 1))
        self.assertEqual(code, 200)

    def test_retry_processes_inline_when_the_broker_is_down(self):
        # It called `.delay()`, which blocks ~100s on Celery's reconnect loop.
        failed = self.doc('failed')
        with mock.patch.object(views, '_celery_broker_ready', return_value=False), \
                mock.patch('Frontline_agent.tasks.process_document.apply') as apply, \
                mock.patch('Frontline_agent.tasks.process_document.delay') as delay:
            code, body = self.retry(failed)
        self.assertEqual(code, 200)
        self.assertEqual(body['data']['dispatch_mode'], 'inline')
        apply.assert_called_once()
        delay.assert_not_called()

    def test_another_companys_document_is_not_found(self):
        theirs = Document.objects.create(title='theirs', file_path='x.pdf', company=self.rival,
                                         uploaded_by=self.rival_user, processing_status='failed')
        code, _ = self.retry(theirs)
        self.assertEqual(code, 404)

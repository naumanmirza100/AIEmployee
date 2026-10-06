"""An Operations document cannot stay on "Processing" for good.

Operations processes uploads inside the web server, so a restart or a deploy
partway left the row on "Processing". The clean-up job covered Frontline and
HR only; Operations' own clean-up command existed but nothing ran it.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import Company
from core.tasks import (
    DOCUMENT_STALL_MINUTES, OPERATIONS_SUMMARY_STALL_MINUTES, fail_stalled_documents,
)
from operations_agent.models import OperationsDocument, OperationsDocumentSummary


class StuckOperationsTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')

    def document(self, status, minutes_ago):
        doc = OperationsDocument.objects.create(company=self.company, title='Q3 report', original_filename='q3.pdf',
                                                file='operations/q3.pdf', processing_status=status)
        # `updated_at` is set on save; only a queryset update can put it in the past.
        OperationsDocument.objects.filter(pk=doc.pk).update(updated_at=timezone.now() - timedelta(minutes=minutes_ago))
        return doc

    def summary(self, status, minutes_ago):
        row = OperationsDocumentSummary.objects.create(company=self.company, original_filename='q3.pdf',
                                                       rich_summary='', processing_status=status)
        OperationsDocumentSummary.objects.filter(pk=row.pk).update(
            created_at=timezone.now() - timedelta(minutes=minutes_ago))
        return row

    def state(self, row):
        row.refresh_from_db()
        return row.processing_status

    def test_a_document_stuck_processing_is_failed_with_what_to_do_next(self):
        stuck = self.document('processing', DOCUMENT_STALL_MINUTES + 1)
        never = self.document('pending', DOCUMENT_STALL_MINUTES + 1)
        fail_stalled_documents()
        self.assertEqual((self.state(stuck), self.state(never)), ('failed', 'failed'))
        self.assertIn('delete this and upload the file again', stuck.processing_error)

    def test_one_still_being_worked_on_or_finished_is_left_alone(self):
        fresh = self.document('processing', DOCUMENT_STALL_MINUTES - 5)
        ready = self.document('ready', DOCUMENT_STALL_MINUTES + 100)
        fail_stalled_documents()
        self.assertEqual((self.state(fresh), self.state(ready)), ('processing', 'ready'))
        self.assertEqual(ready.processing_error, '')

    def test_a_summary_is_given_longer_because_its_only_time_never_moves(self):
        slow = self.summary('processing', DOCUMENT_STALL_MINUTES + 30)        # a big file, still going
        stuck = self.summary('processing', OPERATIONS_SUMMARY_STALL_MINUTES + 1)
        done = self.summary('ready', OPERATIONS_SUMMARY_STALL_MINUTES + 500)
        fail_stalled_documents()
        self.assertEqual((self.state(slow), self.state(stuck), self.state(done)), ('processing', 'failed', 'ready'))

    def test_the_job_says_how_many(self):
        self.document('processing', DOCUMENT_STALL_MINUTES + 1)
        self.summary('pending', OPERATIONS_SUMMARY_STALL_MINUTES + 1)
        self.assertEqual(fail_stalled_documents(), 'Marked 2 stuck document(s) failed')
        self.assertEqual(fail_stalled_documents(), 'Marked 0 stuck document(s) failed')

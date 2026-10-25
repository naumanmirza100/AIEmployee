"""Operations raises its summary alerts: critical documents, risks, opportunities and deadlines.

The alerts were checked only when the summary row was created, and the row is created empty before the AI fills
it in, so none of them ever fired (CO-173). A deadline more than a week away got no alert at all, ever.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import Company
from operations_agent.models import OperationsDocumentSummary, OperationsNotification
from operations_agent.tasks import _alert_deadlines_impl



class SummaryAlertTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Crestline', email='info@crestline.test')

    def summary(self, **filled):
        """A summary as the pipeline makes it: created empty and pending, then filled in and made ready."""
        row = OperationsDocumentSummary.objects.create(company=self.company, original_filename='FinEdge_MSA.pdf',
                                                       rich_summary='', processing_status='pending')
        for name, value in filled.items():
            setattr(row, name, value)
        row.rich_summary = 'The agreement covers...'
        row.processing_status = 'ready'
        row.save()
        return row

    def alerts(self, kind=None):
        rows = OperationsNotification.objects.filter(company=self.company)
        return list(rows.filter(notification_type=kind) if kind else rows)

    def deadline(self, days, what='Security review'):
        return {'date': (timezone.localdate() + timedelta(days=days)).isoformat(), 'description': what}

    def test_a_ready_summary_raises_its_alerts(self):
        self.summary(importance_level='critical', importance_reason='Liability is uncapped',
                     risks=['Uncapped liability', 'Auto-renewal'], opportunities=['Upsell support', 'Second app'],
                     deadlines=[self.deadline(3)])
        titles = sorted(a.title for a in self.alerts())
        self.assertEqual(len(titles), 4, titles)
        self.assertIn('Critical document: FinEdge_MSA.pdf', titles)
        self.assertIn('Deadline in 3 days', titles)

    def test_nothing_while_it_is_still_being_written(self):
        OperationsDocumentSummary.objects.create(company=self.company, original_filename='x.pdf', rich_summary='',
                                                 processing_status='processing', importance_level='critical')
        self.assertEqual(self.alerts(), [])

    def test_saving_it_again_adds_nothing(self):
        row = self.summary(risks=['a', 'b'], deadlines=[self.deadline(2)])
        row.sentiment = 'neutral'
        row.save()
        self.assertEqual(len(self.alerts()), 2)

    def test_a_far_deadline_is_alerted_when_it_comes_within_the_week_and_only_once(self):
        today = timezone.localdate()
        self.summary(deadlines=[self.deadline(10, 'Go-live')])
        self.assertEqual(self.alerts('threshold_breach'), [])
        self.assertEqual(_alert_deadlines_impl(today + timedelta(days=2)), 0)       # still 8 days out
        self.assertEqual(_alert_deadlines_impl(today + timedelta(days=4)), 1)       # 6 days out
        self.assertEqual(_alert_deadlines_impl(today + timedelta(days=5)), 0)       # already told
        alert = self.alerts('threshold_breach')[0]
        self.assertIn('Go-live', alert.message)

    def test_a_deadline_alerted_when_the_summary_was_ready_is_not_repeated_each_morning(self):
        self.summary(deadlines=[self.deadline(4)])
        self.assertEqual(len(self.alerts('threshold_breach')), 1)
        self.assertEqual(_alert_deadlines_impl(timezone.localdate() + timedelta(days=1)), 0)

    def test_a_second_deadline_in_the_same_document_gets_its_own_alert(self):
        first, second = self.deadline(2, 'Sign the SOW'), self.deadline(12, 'Launch')
        self.summary(deadlines=[first, second])
        self.assertEqual(_alert_deadlines_impl(timezone.localdate() + timedelta(days=6)), 1)
        self.assertEqual(len(self.alerts('threshold_breach')), 2)

    def test_past_and_undated_deadlines_are_left_alone(self):
        self.summary(deadlines=[self.deadline(-3), 'Sometime next quarter', {'description': 'No date'}])
        self.assertEqual(self.alerts('threshold_breach'), [])

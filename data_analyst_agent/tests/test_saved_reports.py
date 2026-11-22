"""The company's notes on its data, and saved reports that run by themselves (22 Nov 2026)."""
from datetime import datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.core import mail
from django.utils import timezone

from api.views import data_analyst_agent as views
from data_analyst_agent import reports
from data_analyst_agent.models import DataQuestion, SavedQuestion

from .test_data_analyst import AnalystCase, FakeAI

COUNT = 'SELECT count(*) AS orders FROM orders'


class NoAI:
    def __init__(self, *args, **kwargs):
        raise AssertionError('a saved report called the AI')


class CompanyNotes(AnalystCase):

    def setUp(self):
        super().setUp()
        self.shop = self.source()

    def test_admins_write_them_and_everyone_who_may_ask_reads_them(self):
        notes = 'Revenue means orders.total. An active customer ordered in the last 90 days.'
        code, body = self.call(views.source_detail, self.member, {'company_notes': 'mine'}, method='patch',
                               source_id=self.shop.pk)
        self.assertEqual(code, 403, body)
        code, body = self.call(views.source_detail, self.admin, {'company_notes': notes}, method='patch',
                               source_id=self.shop.pk)
        self.assertEqual((code, body['data']['company_notes']), (200, notes), body)
        code, body = self.call(views.source_detail, self.member, method='get', source_id=self.shop.pk)
        self.assertEqual(body['data']['company_notes'], notes)

    def test_the_agent_reads_them_before_it_writes_the_query(self):
        self.shop.company_notes = 'Revenue means orders.total, never counting cancelled ones.'
        self.shop.save()
        fake = FakeAI({'sql': 'SELECT sum(total) AS revenue FROM orders'}, 'Revenue is 4750.5.')
        code, body = self.ask(self.member, self.shop, 'What is our revenue?', fake)
        self.assertEqual(code, 200, body)
        self.assertIn('What this company says its data means', fake.prompts[0])
        self.assertIn('Revenue means orders.total, never counting cancelled ones.', fake.prompts[0])


class SavedCase(AnalystCase):

    def setUp(self):
        super().setUp()
        self.shop = self.source()
        self.company.timezone_name = 'Asia/Karachi'
        self.company.save()
        code, body = self.ask(self.member, self.shop, 'How many orders?', FakeAI({'sql': COUNT}, 'There are 4.'))
        self.assertEqual(code, 200, body)
        self.question = DataQuestion.objects.get(pk=body['data']['id'])

    def save_it(self, actor=None, **fields):
        return self.call(views.saved_reports, actor or self.member, {'question_id': self.question.pk, **fields})

    def saved(self, **fields):
        code, body = self.save_it(**fields)
        self.assertEqual(code, 201, body)
        return SavedQuestion.objects.get(pk=body['data']['id'])


class Saving(SavedCase):

    def test_an_answered_question_is_kept_with_its_query_and_its_next_time(self):
        code, body = self.save_it(title='Orders', schedule='weekly', weekday=0, hour=9)
        self.assertEqual(code, 201, body)
        data = body['data']
        self.assertEqual((data['when'], [r['id'] for r in data['recipients']]), ('Every Monday at 09:00 (Asia/Karachi)', [self.member.pk]))
        saved = SavedQuestion.objects.get(pk=data['id'])
        self.assertEqual(saved.sql, COUNT)
        when = timezone.localtime(saved.next_run_at, ZoneInfo('Asia/Karachi'))
        self.assertEqual((when.weekday(), when.hour), (0, 9))

    def test_its_rules(self):
        self.shop.everyone_may_ask = False
        self.shop.save()
        self.shop.allowed_users.set([self.member])
        outsider = self.login(self.company, 'out@test.local', 'Out Sider', 'company_user')
        code, body = self.save_it(recipient_ids=[self.member.pk, outsider.pk])
        self.assertEqual(code, 400, body)
        self.assertIn('Out Sider may not ask', body['message'])
        code, body = self.save_it(alert_op='above', alert_column='revenue', alert_value=3)
        self.assertEqual(code, 400, body)
        self.assertIn("answer's columns", body['message'])
        DataQuestion.objects.filter(pk=self.question.pk).update(status=DataQuestion.STATUS_FAILED)
        self.assertEqual(self.save_it()[0], 400)

    def test_someone_elses_saved_report_is_not_theirs_to_see(self):
        saved = self.saved()
        other = self.login(self.company, 'zed@test.local', 'Zed', 'company_user')
        code, _ = self.call(views.saved_report_detail, other, method='get', saved_id=saved.pk)
        self.assertEqual(code, 404)
        code, body = self.call(views.saved_reports, other, method='get')
        self.assertEqual(body['data'], [])
        code, body = self.call(views.saved_reports, self.admin, method='get')
        self.assertEqual([s['id'] for s in body['data']], [saved.pk])


class Running(SavedCase):

    def setUp(self):
        super().setUp()
        patcher = mock.patch('data_analyst_agent.engine.AnalystAI', NoAI)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_it_runs_its_own_query_without_the_ai_and_emails_the_table(self):
        saved = self.saved(title='Orders this month')
        out = reports.run(saved)
        self.assertEqual((out['status'], out['rows'], out['emailed']), ('sent', [[4]], 1))
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.member.email])
        self.assertIn('Orders this month: orders: 4', message.subject)
        self.assertEqual(message.attachments[0][0], 'Orders this month.csv')
        self.assertIn('orders\r\n4', message.attachments[0][1])

    def test_a_watched_figure_is_sent_only_when_it_crosses_the_line(self):
        saved = self.saved(alert_op='above', alert_column='orders', alert_value=10)
        self.assertEqual(reports.run(saved)['status'], 'quiet')
        self.assertEqual(mail.outbox, [])
        saved.alert_value = 3
        saved.save()
        out = reports.run(saved)
        self.assertEqual((out['status'], out['emailed']), ('sent', 1))
        self.assertIn('orders is 4 (above 3)', mail.outbox[0].subject)

    def test_a_query_that_stops_working_is_told_once(self):
        saved = self.saved()
        saved.sql = 'SELECT nope FROM orders'
        saved.save()
        self.assertEqual(reports.run(saved)['status'], 'failed')
        self.assertEqual(reports.run(saved)['status'], 'failed')
        self.assertEqual([m.subject for m in mail.outbox], ['Your saved report "How many orders?" could not run'])

    def test_a_due_report_runs_once_and_moves_on(self):
        saved = self.saved(schedule='daily', hour=9)
        SavedQuestion.objects.filter(pk=saved.pk).update(next_run_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(reports.run_due(), [saved.pk])
        self.assertEqual(reports.run_due(), [])
        saved.refresh_from_db()
        self.assertGreater(saved.next_run_at, timezone.now())
        self.assertEqual((saved.last_status, len(mail.outbox)), ('sent', 1))

    def test_run_now_shows_the_result_and_sends_only_when_asked(self):
        saved = self.saved()
        code, body = self.call(views.saved_report_run, self.member, {}, saved_id=saved.pk)
        self.assertEqual((code, body['data']['rows'], body['data']['emailed']), (200, [[4]], 0), body)
        code, body = self.call(views.saved_report_run, self.member, {'send': True}, saved_id=saved.pk)
        self.assertEqual(body['data']['emailed'], 1)


class NextTime(SavedCase):

    def test_on_the_companys_clock(self):
        saved = self.saved()
        karachi = ZoneInfo('Asia/Karachi')
        monday_10 = datetime(2026, 11, 23, 10, 0, tzinfo=karachi)            # a Monday
        saved.schedule, saved.hour = 'daily', 9
        self.assertEqual(reports.next_run(saved, monday_10), datetime(2026, 11, 24, 9, 0, tzinfo=karachi))
        saved.schedule, saved.weekday = 'weekly', 0
        self.assertEqual(reports.next_run(saved, monday_10), datetime(2026, 11, 30, 9, 0, tzinfo=karachi))
        saved.schedule, saved.month_day = 'monthly', 28
        self.assertEqual(reports.next_run(saved, monday_10), datetime(2026, 11, 28, 9, 0, tzinfo=karachi))
        saved.schedule = 'off'
        self.assertIsNone(reports.next_run(saved, monday_10))

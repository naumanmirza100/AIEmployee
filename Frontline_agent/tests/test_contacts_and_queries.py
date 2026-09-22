"""Contact merge, deferred CRM dispatch, and the query-count / pagination
guards (FL-DATA-1, -2, -16, FL-PERF-4, -10, -11, -14)."""
from datetime import timedelta
from unittest import mock

from api.views import frontline_agent as views
from Frontline_agent.models import (
    Contact, ContactNote, FrontlineQAChat, FrontlineQAChatMessage, FrontlineMeeting, Ticket,
)

from .base import FrontlineTestCase


class ContactMergeTests(FrontlineTestCase):
    """FL-DATA-1 and -2 — merging crashed on every call, and wasn't atomic."""

    def setUp(self):
        super().setUp()
        self.source = Contact.objects.create(
            company=self.company, email='dup@test.local', name='Dup Person', phone='555')
        self.target = Contact.objects.create(
            company=self.company, email='real@test.local', name='')
        self.moved = self.make_ticket(title='Their ticket', contact=self.source)
        ContactNote.objects.create(contact=self.source, body='a note')

    def test_merge_succeeds(self):
        code, body = self.call(views.merge_contacts, self.admin,
                               {'source_id': self.source.id, 'target_id': self.target.id})
        self.assertEqual(code, 200, body)
        self.assertFalse(Contact.objects.filter(pk=self.source.pk).exists())

    def test_merge_moves_tickets_and_notes(self):
        code, body = self.call(views.merge_contacts, self.admin,
                               {'source_id': self.source.id, 'target_id': self.target.id})
        self.assertEqual(code, 200, body)
        self.moved.refresh_from_db()
        self.assertEqual(self.moved.contact_id, self.target.id)
        self.assertEqual(ContactNote.objects.filter(contact=self.target).count(), 1)

    def test_merge_fills_blank_fields_from_the_source(self):
        self.call(views.merge_contacts, self.admin,
                  {'source_id': self.source.id, 'target_id': self.target.id})
        self.target.refresh_from_db()
        self.assertEqual(self.target.name, 'Dup Person')

    def test_merge_refreshes_the_denormalised_count(self):
        self.call(views.merge_contacts, self.admin,
                  {'source_id': self.source.id, 'target_id': self.target.id})
        self.target.refresh_from_db()
        self.assertEqual(self.target.total_tickets_count,
                         Ticket.objects.filter(contact=self.target).count())

    def test_another_companys_contact_cannot_be_merged(self):
        theirs = Contact.objects.create(company=self.rival, email='x@rival.test')
        code, _ = self.call(views.merge_contacts, self.admin,
                            {'source_id': theirs.id, 'target_id': self.target.id})
        self.assertEqual(code, 404)
        self.assertTrue(Contact.objects.filter(pk=theirs.pk).exists())


class ContactSyncDispatchTests(FrontlineTestCase):
    """FL-DATA-16 — the CRM job fired before the row was committed."""

    def test_sync_is_queued_after_commit(self):
        self.company.hubspot_config = {'enabled': True, 'access_token': 'pat-x'}
        self.company.save(update_fields=['hubspot_config'])

        with mock.patch('Frontline_agent.tasks.sync_contact_to_hubspot.delay') as delay:
            from Frontline_agent.contacts import upsert_contact_from_email
            # captureOnCommitCallbacks runs on_commit hooks inside the test's
            # transaction, which is the only way to observe them here.
            with self.captureOnCommitCallbacks(execute=True):
                contact = upsert_contact_from_email(
                    self.company, 'new@test.local', 'New Person')
            self.assertIsNotNone(contact)
            delay.assert_called_once_with(contact.id)

    def test_nothing_is_queued_without_the_integration(self):
        with mock.patch('Frontline_agent.tasks.sync_contact_to_hubspot.delay') as delay:
            from Frontline_agent.contacts import upsert_contact_from_email
            with self.captureOnCommitCallbacks(execute=True):
                upsert_contact_from_email(self.company, 'quiet@test.local', 'Quiet')
            delay.assert_not_called()


class QueryCountTests(FrontlineTestCase):
    """FL-PERF-4 and -10 — list endpoints must not scale queries with rows."""

    def test_chat_list_does_not_scale_with_chat_count(self):
        for i in range(6):
            chat = FrontlineQAChat.objects.create(company_user=self.admin, title=f'c{i}')
            FrontlineQAChatMessage.objects.create(chat=chat, role='user', content='hi')
            FrontlineQAChatMessage.objects.create(chat=chat, role='assistant', content='hello')
        with self.assertNumQueries(2):
            code, body = self.call(views.list_qa_chats, self.admin, method='get')
        self.assertEqual(code, 200, body)
        self.assertEqual(len(body['data']), 6)

    def test_meeting_list_does_not_scale_with_meeting_count(self):
        for i in range(5):
            meeting = FrontlineMeeting.objects.create(
                title=f'm{i}', company=self.company, organizer=self.admin_user,
                scheduled_at=self.now() + timedelta(days=1))
            meeting.participants.add(self.member_user)
        code, body = self.call(views.list_meetings, self.admin, method='get')
        self.assertEqual(code, 200, body)
        # One more meeting must not cost more queries.
        def count_queries():
            from django.test.utils import CaptureQueriesContext
            from django.db import connection
            with CaptureQueriesContext(connection) as ctx:
                self.call(views.list_meetings, self.admin, method='get')
            return len(ctx)
        before = count_queries()
        extra = FrontlineMeeting.objects.create(
            title='extra', company=self.company, organizer=self.admin_user,
            scheduled_at=self.now() + timedelta(days=2))
        extra.participants.add(self.member_user)
        self.assertEqual(count_queries(), before)


class PaginationTests(FrontlineTestCase):
    """FL-PERF-11 — these four used to return every row."""

    def test_ticket_tasks_reports_its_window(self):
        code, body = self.call(views.list_ticket_tasks, self.admin, method='get')
        self.assertEqual(code, 200, body)
        self.assertEqual(set(body['pagination']),
                         {'limit', 'offset', 'total', 'returned', 'has_more'})

    def test_workflows_report_their_window(self):
        code, body = self.call(views.list_workflows, self.admin, method='get')
        self.assertEqual(code, 200, body)
        self.assertIn('pagination', body)

    def test_ticket_messages_report_their_window(self):
        code, body = self.call(views.list_ticket_messages, self.admin, method='get',
                               ticket_id=self.ticket.id)
        self.assertEqual(code, 200, body)
        self.assertIn('pagination', body)

    def test_aging_list_reports_totals_and_truncation(self):
        code, body = self.call(views.list_tickets_aging, self.admin, method='get')
        self.assertEqual(code, 200, body)
        self.assertIn('count_breached', body['data'])
        self.assertIn('truncated', body['data'])


class WidgetTicketCapTests(FrontlineTestCase):
    """FL-PERF-14 / FL-SEC-10 — public traffic must not open tickets without limit."""

    def test_cap_allows_tickets_under_the_limit(self):
        self.assertTrue(views._widget_may_open_ticket(self.company))

    def test_cap_stops_tickets_once_reached(self):
        system_user = views._ensure_handoff_system_user()
        self.company.frontline_widget_config = {'auto_ticket_max_per_hour': 2}
        self.company.save(update_fields=['frontline_widget_config'])
        for i in range(2):
            self.make_ticket(title=f'KB gap: q{i}', category='knowledge_gap',
                             created_by=system_user)
        self.assertFalse(views._widget_may_open_ticket(self.company))

    def test_a_zero_cap_disables_the_check(self):
        self.company.frontline_widget_config = {'auto_ticket_max_per_hour': 0}
        self.company.save(update_fields=['frontline_widget_config'])
        system_user = views._ensure_handoff_system_user()
        for i in range(3):
            self.make_ticket(title=f'KB gap: z{i}', category='knowledge_gap',
                             created_by=system_user)
        self.assertTrue(views._widget_may_open_ticket(self.company))

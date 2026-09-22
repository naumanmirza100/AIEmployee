"""Inbound mail: idempotency, field sizes, and the reply branch
(FL-DATA-8, -9, -10)."""
from datetime import timedelta

from Frontline_agent.models import Ticket, TicketMessage
from Frontline_agent.tasks import process_inbound_email

from .base import FrontlineTestCase


def payload(company_id, **overrides):
    data = {
        'provider': 'generic',
        'company_id': company_id,
        'existing_ticket_id': None,
        'from_address': 'customer@test.local',
        'from_name': 'A Customer',
        'to_addresses': ['support@acme.test'],
        'cc_addresses': [],
        'subject': 'Help please',
        'body_text': 'My printer is on fire.',
        'body_html': '',
        'message_id': '<msg-1@test.local>',
        'in_reply_to': '',
        'references': [],
        'raw_headers': {},
        'is_auto_reply': False,
        'attachments': [],
    }
    data.update(overrides)
    return data


class IdempotencyTests(FrontlineTestCase):
    """FL-DATA-8 — a redelivered webhook used to create a second ticket."""

    def test_first_delivery_creates_a_ticket(self):
        before = Ticket.objects.filter(company=self.company).count()
        result = process_inbound_email(payload(self.company.id))
        self.assertNotEqual(result.get('status'), 'duplicate', result)
        self.assertEqual(Ticket.objects.filter(company=self.company).count(), before + 1)

    def test_redelivery_creates_nothing(self):
        process_inbound_email(payload(self.company.id))
        after_first = Ticket.objects.filter(company=self.company).count()

        result = process_inbound_email(payload(self.company.id))

        self.assertEqual(result.get('status'), 'duplicate', result)
        self.assertEqual(Ticket.objects.filter(company=self.company).count(), after_first)
        self.assertEqual(
            TicketMessage.objects.filter(message_id='<msg-1@test.local>').count(), 1)

    def test_a_different_message_creates_its_own_ticket(self):
        process_inbound_email(payload(self.company.id))
        before = Ticket.objects.filter(company=self.company).count()
        process_inbound_email(payload(self.company.id, message_id='<msg-2@test.local>',
                                      subject='Another thing'))
        self.assertEqual(Ticket.objects.filter(company=self.company).count(), before + 1)


class FieldSizeTests(FrontlineTestCase):
    """FL-DATA-9 — ids were cut to 998 for columns that hold 255."""

    def test_a_long_message_id_is_stored_not_rejected(self):
        long_id = '<' + ('x' * 400) + '@test.local>'
        result = process_inbound_email(payload(self.company.id, message_id=long_id))
        self.assertNotEqual(result.get('status'), 'duplicate', result)
        msg = TicketMessage.objects.order_by('-id').first()
        self.assertIsNotNone(msg)
        self.assertLessEqual(len(msg.message_id), 255)

    def test_no_orphan_ticket_when_the_message_cannot_be_stored(self):
        """The ticket and its first message commit together."""
        before = Ticket.objects.filter(company=self.company).count()
        process_inbound_email(payload(self.company.id, message_id='<' + 'y' * 400 + '>'))
        after = Ticket.objects.filter(company=self.company).count()
        # Either both were created or neither was — never a ticket with no message.
        for ticket in Ticket.objects.filter(company=self.company).order_by('-id')[:after - before or 1]:
            if ticket.intent == 'email_inbound':
                self.assertTrue(TicketMessage.objects.filter(ticket=ticket).exists())


class ReplyBranchTests(FrontlineTestCase):
    """FL-DATA-10 — the reply branch hung off the wrong statement."""

    def test_a_reply_reopens_a_closed_ticket(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(
            status='closed', resolved_at=self.now())
        process_inbound_email(payload(
            self.company.id, existing_ticket_id=self.ticket.id,
            message_id='<reply-1@test.local>', body_text='Still broken'))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'open')
        self.assertIsNone(self.ticket.resolved_at)

    def test_a_reply_resumes_a_paused_sla(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(
            status='open',
            sla_paused_at=self.now() - timedelta(hours=1),
            sla_due_at=self.now() + timedelta(hours=1),
            sla_paused_accumulated_seconds=0)
        process_inbound_email(payload(
            self.company.id, existing_ticket_id=self.ticket.id,
            message_id='<reply-2@test.local>', body_text='Any news?'))
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.sla_paused_at)
        self.assertGreater(self.ticket.sla_paused_accumulated_seconds, 3000)

    def test_a_reply_is_appended_to_the_same_ticket(self):
        before = Ticket.objects.filter(company=self.company).count()
        process_inbound_email(payload(
            self.company.id, existing_ticket_id=self.ticket.id,
            message_id='<reply-3@test.local>'))
        self.assertEqual(Ticket.objects.filter(company=self.company).count(), before)
        self.assertTrue(TicketMessage.objects.filter(
            ticket=self.ticket, message_id='<reply-3@test.local>').exists())

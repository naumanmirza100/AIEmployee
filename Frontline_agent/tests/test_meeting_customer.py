"""The customer of a Frontline call is invited, told of changes, and reminded (Frontline_agent/meeting_customer.py).

Only staff were invited: the customer was a line in the description and heard nothing — no invitation, no link, no
reminder. Staff got two emails, 24 hours and 15 minutes before.
"""
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.utils import timezone

from api.views import frontline_agent as views
from Frontline_agent.models import Contact, FrontlineMeeting, Ticket
from Frontline_agent.tasks import send_meeting_reminders

from .test_meeting_invites import MeetingTestCase


class CustomerCallTests(MeetingTestCase):

    def to_customer(self):
        return [m for m in mail.outbox if m.to == ['farhan@bakery.test']]

    def test_the_customer_is_invited_with_the_link_and_a_calendar_file(self):
        code, body = self.book(customer_name='Farhan Qureshi', customer_email='farhan@bakery.test')
        self.assertEqual(code, 201, body)
        self.assertEqual((body['data']['customer_name'], body['data']['customer_email']),
                         ('Farhan Qureshi', 'farhan@bakery.test'))
        [email] = self.to_customer()
        self.assertEqual(email.subject, 'Call booked: Customer call')
        self.assertIn('Hello Farhan Qureshi,', email.body)
        self.assertIn('https://meet.jit.si/', email.body)
        self.assertIn('please join 5 minutes before the start', email.body)
        [(name, content, kind)] = email.attachments
        self.assertEqual((name, kind), ('call.ics', 'text/calendar'))
        self.assertIn('METHOD:REQUEST', content)
        from email.utils import parseaddr
        self.assertEqual(parseaddr(email.from_email)[0], self.company.name)

    def test_the_customer_comes_from_the_ticket_the_call_was_asked_for_on(self):
        customer = Contact.objects.create(company=self.company, email='farhan@bakery.test', name='Farhan')
        ticket = Ticket.objects.create(company=self.company, title='Call requested: menu page', description='-',
                                       created_by=self.admin_user, contact=customer)
        code, body = self.book(ticket_id=ticket.id)
        self.assertEqual(code, 201, body)
        meeting = FrontlineMeeting.objects.get(pk=body['data']['id'])
        self.assertEqual((meeting.customer_email, meeting.ticket_id), ('farhan@bakery.test', ticket.id))
        self.assertEqual(len(self.to_customer()), 1)

    def test_booking_the_call_takes_its_hand_off_off_the_queue(self):
        # Live (27 Oct) the "call requested" hand-off stayed pending after the call was booked.
        customer = Contact.objects.create(company=self.company, email='farhan@bakery.test', name='Farhan')
        ticket = Ticket.objects.create(company=self.company, title='Call requested: menu page', description='-',
                                       created_by=self.admin_user, contact=customer, handoff_status='pending',
                                       handoff_reason='call_requested')
        self.assertEqual(self.book(ticket_id=ticket.id)[0], 201)
        ticket.refresh_from_db()
        self.assertEqual(ticket.handoff_status, 'accepted')
        self.assertEqual(ticket.assigned_to, views._get_or_create_user_for_company_user(self.admin))

    def test_another_companys_ticket_or_a_bad_address_is_refused(self):
        rival_ticket = Ticket.objects.create(company=self.rival, title='Theirs', description='-',
                                             created_by=self.admin_user)
        self.assertEqual(self.book(ticket_id=rival_ticket.id)[0], 400)
        self.assertEqual(self.book(customer_email='not an address')[0], 400)
        self.assertFalse(FrontlineMeeting.objects.exists())

    def test_a_call_with_no_customer_emails_no_customer(self):
        self.book()
        self.assertEqual([m for m in mail.outbox if m.attachments], [])

    def test_moving_and_cancelling_tell_the_customer(self):
        meeting = self.booked(customer_email='farhan@bakery.test')
        self.edit(meeting, scheduled_at=(self.when + timedelta(hours=2)).isoformat())
        self.edit(meeting, status='cancelled')
        self.assertEqual([m.subject for m in self.to_customer()], ['New time: Customer call', 'Cancelled: Customer call'])
        self.assertIn('METHOD:CANCEL', self.to_customer()[1].attachments[0][1])

    def test_deleting_an_upcoming_call_tells_the_customer(self):
        meeting = self.booked(customer_email='farhan@bakery.test')
        with self.captureOnCommitCallbacks(execute=True):
            code, _ = self.call(views.delete_meeting, self.admin, method='delete', meeting_id=meeting.id)
        self.assertEqual(code, 200)
        self.assertEqual([m.subject for m in self.to_customer()], ['Cancelled: Customer call'])


class CustomerReminderTests(MeetingTestCase):

    def remind_at(self, minutes_before):
        meeting = self.booked(customer_email='farhan@bakery.test')
        later = meeting.scheduled_at - timedelta(minutes=minutes_before)
        with mock.patch('django.utils.timezone.now', return_value=later):
            with self.captureOnCommitCallbacks(execute=True):
                send_meeting_reminders()
        meeting.refresh_from_db()
        return meeting

    def test_an_hour_before_everyone_is_reminded_with_the_real_minutes_and_the_link(self):
        meeting = self.remind_at(58)
        customer = [m for m in mail.outbox if m.to == ['farhan@bakery.test']]
        [email] = customer
        self.assertEqual(email.subject, 'Reminder: Customer call starts in 58 minutes')
        self.assertIn('https://meet.jit.si/', email.body)
        staff = sorted(a for m in mail.outbox if m.to != ['farhan@bakery.test'] for a in m.to)
        self.assertEqual(staff, ['ali@test.local', 'bea@test.local', 'dana@test.local'])    # dana organises it
        from core.models import Notification
        self.assertTrue(Notification.objects.filter(user=self.ali, type='frontline_meeting_reminder').exists())
        self.assertTrue(meeting.reminder_60m_sent_at and meeting.reminder_24h_sent_at)   # the earlier one too

    def test_five_minutes_before_is_the_last_one(self):
        meeting = self.remind_at(5)
        self.assertTrue(meeting.reminder_5m_sent_at and meeting.reminder_15m_sent_at)
        self.assertIn('Reminder: Customer call starts in 5 minutes',
                      [m.subject for m in mail.outbox if m.to == ['farhan@bakery.test']])

    def test_moving_a_call_reminds_again(self):
        meeting = self.remind_at(58)
        self.edit(meeting, scheduled_at=(meeting.scheduled_at + timedelta(days=1)).isoformat())
        meeting.refresh_from_db()
        self.assertEqual([getattr(meeting, f) for f in FrontlineMeeting.REMINDER_FIELDS], [None] * 4)

    def test_a_cancelled_call_is_not_reminded(self):
        meeting = self.booked(customer_email='farhan@bakery.test')
        self.edit(meeting, status='cancelled')
        mail.outbox.clear()
        with mock.patch('django.utils.timezone.now', return_value=meeting.scheduled_at - timedelta(minutes=58)):
            send_meeting_reminders()
        self.assertEqual(mail.outbox, [])

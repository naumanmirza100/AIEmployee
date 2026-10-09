"""Telling an employee login something: their bell, and an email.

`notify_company_users` reaches dashboard logins. Members of staff sign in to
My Space, whose bell reads `core.Notification`, and nothing shared could tell
them anything: HR, Frontline and Recruitment each booked people and said
nothing. `notify_employees` is the one way to do it.
"""
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import transaction
from django.test import TestCase

from core.models import Notification
from core.notification_utils import notify_employees

User = get_user_model()


class NotifyEmployeesTests(TestCase):

    def setUp(self):
        self.ali = User.objects.create_user('ali', email='ali@test.local', password='x')
        self.bea = User.objects.create_user('bea', email='bea@test.local', password='x')

    def tell(self, users, **more):
        words = {'title': 'Meeting booked: Review', 'message': 'Tuesday at 10:00.', 'link': '/me/meetings',
                 'kind': 'hr_meeting_booked', 'email_subject': 'Meeting booked: Review'}
        words.update(more)
        with self.captureOnCommitCallbacks(execute=True):
            return notify_employees(users, **words)

    def test_each_person_gets_a_bell_row_that_opens_the_page(self):
        self.assertEqual(self.tell([self.ali, self.bea]), 2)
        [row] = Notification.objects.filter(user=self.ali)
        self.assertEqual((row.title, row.message, row.action_url, row.link, row.type, row.is_read),
                         ('Meeting booked: Review', 'Tuesday at 10:00.', '/me/meetings', '/me/meetings',
                          'hr_meeting_booked', False))
        self.assertEqual(Notification.objects.filter(user=self.bea).count(), 1)

    def test_and_an_email_of_their_own(self):
        self.tell([self.ali, self.bea])
        self.assertEqual(sorted(m.to for m in mail.outbox), [['ali@test.local'], ['bea@test.local']])
        sent = mail.outbox[0]
        self.assertEqual(sent.subject, 'Meeting booked: Review')
        self.assertIn('Tuesday at 10:00.', sent.body)
        self.assertIn('/me/meetings', sent.body)                    # where to open it

    def test_the_email_can_say_more_than_the_bell_and_carry_a_file(self):
        self.tell([self.ali], email_body='Tuesday at 10:00, in the boardroom.',
                  attachments=[('meeting.ics', 'BEGIN:VCALENDAR', 'text/calendar')])
        [sent] = mail.outbox
        self.assertIn('in the boardroom', sent.body)
        self.assertEqual(sent.attachments, [('meeting.ics', 'BEGIN:VCALENDAR', 'text/calendar')])

    def test_no_email_unless_a_subject_is_given(self):
        self.tell([self.ali], email_subject=None)
        self.assertEqual(Notification.objects.filter(user=self.ali).count(), 1)
        self.assertEqual(mail.outbox, [])

    def test_a_person_named_twice_is_told_once(self):
        self.assertEqual(self.tell([self.ali, self.ali]), 1)
        self.assertEqual(Notification.objects.filter(user=self.ali).count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_a_switched_off_login_is_told_nothing(self):
        self.ali.is_active = False
        self.ali.save()
        self.assertEqual(self.tell([self.ali, None]), 0)
        self.assertEqual((Notification.objects.count(), mail.outbox), (0, []))

    def test_an_address_that_cannot_receive_mail_is_not_written_to(self):
        self.ali.email = 'ali@demo.invalid'
        self.ali.save()
        self.bea.email = ''
        self.bea.save()
        self.assertEqual(self.tell([self.ali, self.bea]), 2)       # the bell still has it
        self.assertEqual(mail.outbox, [])

    def test_nobody_is_emailed_about_something_that_was_undone(self):
        class Undone(Exception):
            pass
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    notify_employees([self.ali], title='Booked', message='m', email_subject='Booked')
                    raise Undone()
            except Undone:
                pass
        self.assertEqual((Notification.objects.count(), mail.outbox), (0, []))

    def test_a_failure_never_reaches_the_caller(self):
        self.assertEqual(notify_employees([object()], title='t', message='m'), 0)

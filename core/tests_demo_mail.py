"""Mail for demo addresses goes to the practice server; everyone else's goes out as before."""
from unittest import mock

from django.core import mail
from django.core.mail import EmailMessage, send_mail
from django.test import SimpleTestCase, override_settings

from core.demo_mail import DemoRoutingBackend, is_demo_address

DEMO = dict(
    EMAIL_BACKEND='core.demo_mail.DemoRoutingBackend',
    DEMO_MAIL_REAL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEMO_MAIL_DOMAIN='demo.payperproject.com', DEMO_MAIL_HOST='mail.example', DEMO_MAIL_PORT=2525,
)


class _Practice:
    def __init__(self):
        self.sent = []

    def send_messages(self, messages):
        self.sent.extend(messages)
        return len(messages)

    def close(self):
        pass


@override_settings(**DEMO)
class DemoMailTests(SimpleTestCase):
    def setUp(self):
        self.practice = _Practice()
        patcher = mock.patch.object(DemoRoutingBackend, '_demo_connection', return_value=self.practice)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_which_addresses_are_demo(self):
        self.assertTrue(is_demo_address('ayesha@crestline.demo.payperproject.com'))
        self.assertTrue(is_demo_address('Ayesha Khan <AYESHA@demo.payperproject.com>'))
        self.assertFalse(is_demo_address('someone@payperproject.com'))
        self.assertFalse(is_demo_address('someone@notdemo.payperproject.com'))
        self.assertFalse(is_demo_address('someone@demo.payperproject.com.evil.com'))
        self.assertFalse(is_demo_address(''))

    def test_demo_mail_stays_on_the_practice_server(self):
        send_mail('Leave approved', 'Enjoy it.', 'site@example.com', ['ayesha@crestline.demo.payperproject.com'])
        self.assertEqual(mail.outbox, [])
        self.assertEqual([m.to for m in self.practice.sent], [['ayesha@crestline.demo.payperproject.com']])

    def test_real_mail_goes_out_as_before(self):
        send_mail('Welcome', 'Hello.', 'site@example.com', ['real.person@gmail.com'])
        self.assertEqual(self.practice.sent, [])
        self.assertEqual([m.to for m in mail.outbox], [['real.person@gmail.com']])

    def test_a_message_to_both_is_split(self):
        EmailMessage('Kickoff', 'Thursday.', 'site@example.com',
                     to=['ayesha@crestline.demo.payperproject.com', 'real.person@gmail.com'],
                     cc=['hafsa@crestline.demo.payperproject.com'], bcc=['boss@gmail.com']).send()
        demo, = self.practice.sent
        real, = mail.outbox
        self.assertEqual((demo.to, demo.cc, demo.bcc),
                         (['ayesha@crestline.demo.payperproject.com'], ['hafsa@crestline.demo.payperproject.com'], []))
        self.assertEqual((real.to, real.cc, real.bcc), (['real.person@gmail.com'], [], ['boss@gmail.com']))


@override_settings(**{**DEMO, 'DEMO_MAIL_DOMAIN': ''})
class NotSetTests(SimpleTestCase):
    def test_no_address_is_demo_when_no_domain_is_set(self):
        self.assertFalse(is_demo_address('ayesha@crestline.demo.payperproject.com'))

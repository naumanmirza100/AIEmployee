"""A company's mail server must be a public host on a mail port (21 Nov 2026, the test report's Marketing 1).

Marketing and Reply Draft connected to whatever host and port a company typed, so "Test" on an account at
127.0.0.1:6379 told an admin which ports were open on the server. AI SDR already refused that; now every mailbox does,
when it is saved, tested and connected to. The test settings let made-up hosts through (ALLOW_PRIVATE_MAIL_HOSTS), so
these tests switch the check back on and answer the name lookups themselves.
"""
import socket
from unittest import mock

from django.test import SimpleTestCase, override_settings

from api.views import marketing_agent as marketing_views
from core.mail_hosts import MailServerRefused, check_mail_server, mail_server_error
from hr_agent.tests.base import HRTestCase


def resolves_to(address):
    return mock.patch.object(socket, 'getaddrinfo', return_value=[(socket.AF_INET, 1, 6, '', (address, 0))])


@override_settings(ALLOW_PRIVATE_MAIL_HOSTS=False, SDR_ALLOW_PRIVATE_MAIL_HOSTS=False)
class TheCheck(SimpleTestCase):

    def test_internal_addresses_are_refused(self):
        for address in ('127.0.0.1', '10.0.0.5', '172.18.0.4', '169.254.169.254'):
            with self.subTest(address=address), resolves_to(address):
                self.assertEqual(mail_server_error('mail.example.com', 587), 'Mail server must be a public host.')

    def test_only_mail_ports(self):
        with resolves_to('93.184.216.34'):
            self.assertIn('port must be one of', mail_server_error('mail.example.com', 6379))
            self.assertIn('port must be one of', mail_server_error('mail.example.com', 25, 'imap'))
            self.assertIsNone(mail_server_error('mail.example.com', 2525))
            self.assertIsNone(mail_server_error('mail.example.com', 993, 'imap'))

    def test_a_connection_is_refused_too(self):
        with resolves_to('127.0.0.1'), self.assertRaises(MailServerRefused):
            check_mail_server('localhost', 587)

    @override_settings(ALLOW_PRIVATE_MAIL_HOSTS=True)
    def test_a_local_mail_catcher_may_be_allowed(self):
        self.assertIsNone(mail_server_error('127.0.0.1', 3025))


@override_settings(ALLOW_PRIVATE_MAIL_HOSTS=False, SDR_ALLOW_PRIVATE_MAIL_HOSTS=False)
class MarketingAccounts(HRTestCase):

    def test_an_account_on_an_internal_address_is_not_saved(self):
        from marketing_agent.models import EmailAccount
        self.buy_module(self.company, 'marketing_agent')
        with resolves_to('127.0.0.1'):
            code, body = self.call(marketing_views.create_email_account, self.admin, {
                'name': 'Probe', 'email': 'probe@example.com', 'smtp_host': 'localhost', 'smtp_port': 6379,
                'smtp_password': 'x'})
        self.assertEqual(code, 400, body)
        self.assertEqual(body['error'], 'mail_server_refused')
        self.assertFalse(EmailAccount.objects.filter(email='probe@example.com').exists())

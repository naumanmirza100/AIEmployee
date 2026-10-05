"""Operators hear when the live site breaks (core/error_alerts.py), and the
screens can tell when the server is older than they need (core/version.py).

The addresses, tokens and messages here are made up.
"""
import logging
import re
import sys
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils.module_loading import import_string

from core import error_alerts
from core.error_alerts import AlertEmailHandler
from core.models import Company, CompanyModulePurchase, CompanyUser, CompanyUserToken
from core.version import API_LEVEL

OPS = ['ops@test.local']


def log_record(message='Internal Server Error: %s', args=('/api/hr/employees/41/handover',),
               name='django.request', request=None, status_code=None, exc_info=None, **extra):
    record = logging.LogRecord(name, logging.ERROR, __file__, 1, message, args, exc_info)
    if request is not None:
        record.request = request
    if status_code:
        record.status_code = status_code
    for key, value in extra.items():
        setattr(record, key, value)
    return record


@override_settings(ERROR_ALERT_EMAILS=OPS)
class AlertEmailTests(TestCase):
    def setUp(self):
        cache.clear()
        self.requests = RequestFactory()
        self.handler = AlertEmailHandler()
        self.handler.background = False             # send in line, so the test can look

    def server_error(self, path):
        return log_record(args=(path,), request=self.requests.get(path), status_code=500)

    def test_a_server_error_is_emailed_with_where_and_what(self):
        self.handler.emit(self.server_error('/api/hr/employees/41/handover'))
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, OPS)
        self.assertIn('Internal Server Error: /api/hr/employees/41/handover', email.subject)
        self.assertIn('Where: GET /api/hr/employees/41/handover  (HTTP 500)', email.body)

    def test_the_same_problem_on_another_record_is_not_emailed_again(self):
        self.handler.emit(self.server_error('/api/hr/employees/41/handover'))
        self.handler.emit(self.server_error('/api/hr/employees/77/handover'))
        self.assertEqual(len(mail.outbox), 1)

    def test_a_different_problem_is_emailed(self):
        self.handler.emit(self.server_error('/api/hr/employees/41/handover'))
        self.handler.emit(self.server_error('/api/frontline/tickets/9/task'))
        self.assertEqual(len(mail.outbox), 2)

    def test_code_can_name_the_problem_itself(self):
        def said(message, key):
            self.handler.emit(log_record(message, (), name='alerts', alert_key=key))
        said('PUT /api/quick-chats/a1 is not on this server', 'unknown-endpoint:/api/quick-chats')
        said('GET /api/quick-chats is not on this server', 'unknown-endpoint:/api/quick-chats')
        self.assertEqual(len(mail.outbox), 1)          # two wordings, one named problem
        said('PUT /api/quick-chats/a1 is not on this server', 'unknown-endpoint:/api/other')
        self.assertEqual(len(mail.outbox), 2)          # same wording, another named problem

    def test_nobody_is_emailed_when_no_address_is_set(self):
        with override_settings(ERROR_ALERT_EMAILS=[]), mock.patch.object(error_alerts, 'send_mail') as send:
            self.handler.emit(self.server_error('/api/hr/employees/41/handover'))
        send.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)

    def test_a_burst_of_different_problems_is_capped_per_hour(self):
        for n in range(error_alerts.MAX_PER_HOUR + 5):
            self.handler.emit(log_record('Problem in part %s', (n,), name=f'part{n}'))
        self.assertEqual(len(mail.outbox), error_alerts.MAX_PER_HOUR)

    def test_the_email_carries_the_traceback_but_no_login_token_or_address(self):
        token = 'k' * 40
        request = self.requests.get('/api/hr/employees/41/handover', HTTP_AUTHORIZATION=f'Token {token}')
        try:
            raise ValueError('could not email jo@customer.example')
        except ValueError:
            self.handler.emit(log_record(request=request, status_code=500, exc_info=sys.exc_info()))
        body = mail.outbox[0].body
        self.assertIn('ValueError', body)
        self.assertIn('Traceback', body)
        self.assertNotIn(token, body)
        self.assertNotIn('jo@customer.example', body)

    def test_a_failing_mail_server_never_breaks_the_request(self):
        with mock.patch.object(error_alerts, 'send_mail', side_effect=OSError('mail server down')), \
                mock.patch.object(self.handler, 'handleError') as swallowed:
            self.handler.emit(self.server_error('/api/hr/employees/41/handover'))     # must not raise
        swallowed.assert_called_once()

    def test_the_live_settings_send_server_errors_and_billing_errors_to_it(self):
        live = sys.modules['project_manager_ai.settings'].LOGGING
        self.assertIs(import_string(live['handlers']['alert_email']['class']), AlertEmailHandler)
        for logger in ('django.request', 'api.views.module_purchase', 'alerts'):
            self.assertIn('alert_email', live['loggers'][logger]['handlers'], logger)


class ServerBehindTheScreensTests(TestCase):
    """What a frontend newer than the backend looks like, from the server."""

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        CompanyModulePurchase.objects.create(company=self.company, module_name='hr_agent', status='active',
                                             is_complimentary=True)
        login = CompanyUser.objects.create(company=self.company, email='ada@test.local', full_name='Ada Admin',
                                           role='admin', password_hash='x', is_active=True)
        key = CompanyUserToken.objects.get_or_create(company_user=login)[0].key
        self.screen = Client(HTTP_AUTHORIZATION=f'Token {key}')      # a logged-in screen
        self.stranger = Client()

    def reported(self, call):
        """The alert messages logged while `call` runs."""
        with mock.patch('logging.Logger.error') as said:
            response = call()
        return response, [(c.args[0], c.kwargs.get('extra') or {}) for c in said.call_args_list]

    def test_a_logged_in_screen_calling_a_missing_address_is_reported(self):
        response, alerts = self.reported(lambda: self.screen.put('/api/quick-chats-next/abc123'))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(alerts), 1, alerts)
        message, extra = alerts[0]
        self.assertIn('which this server does not have', message)
        self.assertEqual(extra['alert_key'], 'unknown-endpoint:/api/quick-chats-next')

    def test_a_stranger_guessing_addresses_is_not(self):
        response, alerts = self.reported(lambda: self.stranger.get('/api/wp-login.php'))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(alerts, [])

    def test_a_real_address_saying_a_record_was_not_found_is_not(self):
        response, alerts = self.reported(lambda: self.screen.get('/api/hr/employees/999999/handover'))
        self.assertEqual(response.status_code, 404)
        self.assertEqual([m for m, _ in alerts if 'does not have' in m], [])

    def test_anyone_can_ask_the_api_level(self):
        response = self.stranger.get('/api/version')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'api_level': API_LEVEL})

    def test_a_screen_that_needs_a_newer_server_is_reported(self):
        response, alerts = self.reported(lambda: self.screen.get(f'/api/version?needs={API_LEVEL + 1}'))
        self.assertEqual(response.json(), {'api_level': API_LEVEL})
        self.assertEqual([extra.get('alert_key') for _, extra in alerts], ['api-level-behind'])

    def test_a_screen_the_server_is_new_enough_for_is_not(self):
        _, alerts = self.reported(lambda: self.screen.get(f'/api/version?needs={API_LEVEL}'))
        self.assertEqual(alerts, [])

    def test_a_stranger_cannot_set_the_alert_off(self):
        _, alerts = self.reported(lambda: self.stranger.get(f'/api/version?needs={API_LEVEL + 50}'))
        self.assertEqual(alerts, [])

    def test_the_screens_and_the_server_name_the_same_level(self):
        source = (Path(settings.BASE_DIR) / 'PaPerProjectFront' / 'src' / 'config' / 'apiLevel.js').read_text('utf-8')
        needed = int(re.search(r'REQUIRED_API_LEVEL\s*=\s*(\d+)', source).group(1))
        self.assertEqual(needed, API_LEVEL, 'Raise API_LEVEL (core/version.py) and REQUIRED_API_LEVEL '
                                            '(PaPerProjectFront/src/config/apiLevel.js) together.')

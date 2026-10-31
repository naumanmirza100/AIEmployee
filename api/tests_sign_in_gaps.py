"""The eight sign-in gaps of the inside-gaps report (31 Oct 2026): CO-97, 99, 100, 219, 220, 269, 270, 271."""
import json
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token

from core import sign_in
from core.models import Company, CompanyRegistrationToken, CompanyUser, CompanyUserToken, UserProfile, UserToken

PASSWORD = 'a-synthetic-password'


def _json(response):
    return json.loads(response.content.decode() or '{}')


class Base(TestCase):

    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name='Margalla Foods', email='hello@margalla.test')
        self.admin = CompanyUser.objects.create(company=self.company, email='sana@margalla.test', full_name='Sana Malik',
                                                role='admin', password_hash=make_password(PASSWORD), is_active=True)
        self.member = CompanyUser.objects.create(company=self.company, email='bilal@margalla.test', full_name='Bilal Ahmed',
                                                 role='company_user', password_hash=make_password(PASSWORD), is_active=True)
        self.employee = get_user_model().objects.create_user(username='kiran', email='kiran@margalla.test',
                                                             password=PASSWORD, first_name='Kiran')
        UserProfile.objects.update_or_create(user=self.employee, defaults={
            'company': self.company, 'created_by_company_user': self.admin, 'role': 'team_member'})

    def dashboard_sign_in(self, email='sana@margalla.test', password=PASSWORD):
        return Client().post('/api/company/login', {'email': email, 'password': password}, content_type='application/json')

    def employee_sign_in(self, email='kiran@margalla.test', password=PASSWORD):
        return Client().post('/api/auth/login', {'email': email, 'password': password}, content_type='application/json')

    @staticmethod
    def as_token(key):
        return Client(HTTP_AUTHORIZATION=f'Token {key}')


class GoogleCalendarAndProfileAreForAdmins(Base):
    """CO-97."""

    def test_a_member_may_not_connect_or_disconnect_the_calendar(self):
        key = CompanyUserToken.objects.create(company_user=self.member, key='m' * 40).key
        connect = self.as_token(key).post('/api/company/integrations/google-calendar/connect', {}, content_type='application/json')
        disconnect = self.as_token(key).delete('/api/company/integrations/google-calendar/disconnect')
        self.assertEqual((connect.status_code, disconnect.status_code), (403, 403))
        self.assertIn('owner or admin', _json(connect)['message'])
        status = _json(self.as_token(key).get('/api/company/integrations/google-calendar'))
        self.assertIs(status['data']['mayManage'], False)

    @override_settings(GOOGLE_CLIENT_ID='id', GOOGLE_CLIENT_SECRET='secret', GOOGLE_OAUTH_REDIRECT_URI='https://x.test/cb')
    def test_an_admin_still_may(self):
        key = CompanyUserToken.objects.create(company_user=self.admin, key='a' * 40).key
        connect = self.as_token(key).post('/api/company/integrations/google-calendar/connect', {}, content_type='application/json')
        self.assertEqual(connect.status_code, 200, connect.content[:200])
        self.assertIs(_json(self.as_token(key).get('/api/company/integrations/google-calendar'))['data']['mayManage'], True)

    def test_a_member_may_not_change_the_profile_but_may_read_it(self):
        key = CompanyUserToken.objects.create(company_user=self.member, key='m' * 40).key
        changed = self.as_token(key).patch('/api/company/profile/update', {'name': 'Someone Else Ltd'}, content_type='application/json')
        self.assertEqual(changed.status_code, 403)
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, 'Margalla Foods')
        self.assertEqual(self.as_token(key).get('/api/company/profile').status_code, 200)
        admin_key = CompanyUserToken.objects.create(company_user=self.admin, key='a' * 40).key
        self.assertEqual(self.as_token(admin_key).patch('/api/company/profile/update', {'phone': '+92 51 1234567'},
                                                        content_type='application/json').status_code, 200)

    def test_the_google_token_is_stored_encrypted_and_still_read(self):
        from core.google_calendar import refresh_token_of, seal_refresh_token
        sealed = seal_refresh_token('1//a-refresh-token')
        self.assertNotIn('a-refresh-token', sealed)
        self.assertEqual(refresh_token_of({'refresh_token': sealed}), '1//a-refresh-token')
        self.assertEqual(refresh_token_of({'refresh_token': '1//saved-before'}), '1//saved-before')     # before CO-97

    def test_the_callback_saves_it_encrypted(self):
        import base64
        from django.core import signing
        state = base64.urlsafe_b64encode(signing.dumps({'company_id': self.company.id, 'return_to': ''},
                                                       salt='recruitment.gcal.oauth').encode()).decode().rstrip('=')
        token_reply = mock.Mock(status_code=200, json=lambda: {'refresh_token': '1//fresh', 'access_token': 'x'})
        with mock.patch('requests.post', return_value=token_reply), \
                mock.patch('requests.get', return_value=mock.Mock(status_code=200, json=lambda: {'email': 'cal@margalla.test'})):
            Client().get('/api/company/integrations/google-calendar/callback', {'code': 'c', 'state': state})
        self.company.refresh_from_db()
        stored = self.company.google_calendar_config['refresh_token']
        self.assertTrue(stored.startswith('gAAAAA'))
        from core.google_calendar import refresh_token_of
        self.assertEqual(refresh_token_of(self.company.google_calendar_config), '1//fresh')

    def test_the_migration_seals_plain_tokens_and_can_undo_it(self):
        import importlib
        from django.apps import apps
        migration = importlib.import_module('core.migrations.0120_sign_in_sessions')
        Company.objects.filter(pk=self.company.pk).update(google_calendar_config={'connected': True, 'refresh_token': '1//plain'})
        migration.seal_google_tokens(apps, None)
        self.company.refresh_from_db()
        self.assertTrue(self.company.google_calendar_config['refresh_token'].startswith('gAAAAA'))
        migration.seal_google_tokens(apps, None)            # twice changes nothing
        migration.unseal_google_tokens(apps, None)
        self.company.refresh_from_db()
        self.assertEqual(self.company.google_calendar_config['refresh_token'], '1//plain')


class RegistrationUsesTheLinksAddress(Base):
    """CO-99."""

    def link(self, company):
        return CompanyRegistrationToken.objects.create(company=company, token='t' * 64,
                                                       expires_at=timezone.now() + timedelta(days=7)).token

    def test_an_address_sent_by_the_browser_is_ignored(self):
        company = Company.objects.create(name='Rawal Traders', email='office@rawal.test')
        reply = Client().post('/api/company/register', {'token': self.link(company), 'password': PASSWORD,
                                                        'email': 'someone@elsewhere.test'}, content_type='application/json')
        self.assertEqual(reply.status_code, 201, reply.content[:300])
        self.assertEqual(_json(reply)['data']['user']['email'], 'office@rawal.test')
        self.assertFalse(CompanyUser.objects.filter(email='someone@elsewhere.test').exists())

    def test_an_address_with_a_login_at_another_company_is_refused(self):
        company = Company.objects.create(name='Copy Cat', email='SANA@margalla.test')
        reply = Client().post('/api/company/register', {'token': self.link(company), 'password': PASSWORD},
                              content_type='application/json')
        self.assertEqual(reply.status_code, 400)
        self.assertIn('already has a dashboard login', _json(reply)['message'])
        self.assertEqual(CompanyUser.objects.filter(email__iexact='sana@margalla.test').count(), 1)
        self.assertFalse(CompanyRegistrationToken.objects.get(company=company).is_used)


class WrongPasswordsAreCountedOnTheAccount(Base):
    """CO-100."""

    def test_employee_sign_in_locks_after_too_many_wrong_passwords(self):
        for _ in range(sign_in.MAX_WRONG_PASSWORDS):
            self.assertEqual(self.employee_sign_in(password='wrong').status_code, 401)
        locked = self.employee_sign_in()             # the right password, while locked
        self.assertEqual(locked.status_code, 429)
        self.assertIn('Too many wrong passwords', _json(locked)['message'])
        self.assertFalse(UserToken.objects.filter(user=self.employee).exists())

    def test_the_address_is_counted_whatever_its_case(self):
        for _ in range(sign_in.MAX_WRONG_PASSWORDS):
            self.employee_sign_in(email='KIRAN@margalla.test', password='wrong')
        self.assertEqual(self.employee_sign_in().status_code, 429)

    def test_dashboard_sign_in_locks_too_and_for_unknown_addresses_alike(self):
        for _ in range(sign_in.MAX_WRONG_PASSWORDS):
            self.dashboard_sign_in(password='wrong')
            self.dashboard_sign_in(email='nobody@margalla.test', password='wrong')
        self.assertEqual(self.dashboard_sign_in().status_code, 429)
        self.assertEqual(self.dashboard_sign_in(email='nobody@margalla.test').status_code, 429)
        self.assertEqual(self.dashboard_sign_in(email='bilal@margalla.test').status_code, 200)    # others go on

    def test_a_right_password_clears_the_count(self):
        for _ in range(sign_in.MAX_WRONG_PASSWORDS - 1):
            self.employee_sign_in(password='wrong')
        self.assertEqual(self.employee_sign_in().status_code, 200)
        self.employee_sign_in(password='wrong')
        self.assertEqual(self.employee_sign_in().status_code, 200)

    def test_employee_sign_in_has_the_per_caller_limit_of_dashboard_sign_in(self):
        from api.views import auth, company_auth
        self.assertIn(company_auth.CompanyAuthThrottle, auth.login.cls.throttle_classes)


class NoDebugBlock(Base):
    """CO-219."""

    def test_who_am_i_has_no_debug_section(self):
        key = _json(self.employee_sign_in())['data']['token']
        body = _json(self.as_token(key).get('/api/auth/me'))
        self.assertNotIn('debug', body['data'])
        self.assertNotIn('is_superuser', json.dumps(body))


class NoSignInWithoutASecret(Base):
    """CO-220."""

    def test_the_header_sign_in_is_gone(self):
        import api.authentication as authentication
        self.assertFalse(hasattr(authentication, 'CompanyUserAuthentication'))
        reply = Client(HTTP_X_COMPANY_USER_ID=str(self.admin.id), HTTP_X_COMPANY_ID=str(self.company.id)).get('/api/company/profile')
        self.assertIn(reply.status_code, (401, 403))

    def test_the_dashboard_permission_refuses_an_employee_login(self):
        from rest_framework.test import APIRequestFactory
        from api.permissions import IsCompanyUserOnly
        request = APIRequestFactory().get('/')
        request.user = self.employee
        self.assertFalse(IsCompanyUserOnly().has_permission(request, None))
        request.user = self.admin
        self.assertTrue(IsCompanyUserOnly().has_permission(request, None))


class OldMarketplaceIsGone(Base):
    """CO-269."""

    def test_its_addresses_no_longer_answer(self):
        key = _json(self.employee_sign_in())['data']['token']
        client = self.as_token(key)
        for method, path in (('post', '/api/auth/register'), ('post', '/api/payments'), ('get', '/api/payments/list'),
                             ('get', '/api/pricing/plans'), ('post', '/api/pricing/subscriptions'),
                             ('get', '/api/referrals/my-code'), ('post', '/api/referrals/use-code'),
                             ('post', '/api/chatbot/messages'), ('post', '/api/projects/create'),
                             ('post', '/api/projects/1/apply'), ('get', '/api/projects/1/applications')):
            self.assertEqual(getattr(client, method)(path, {}, content_type='application/json').status_code, 404, path)

    def test_nobody_can_make_an_account_there(self):
        Client().post('/api/auth/register', {'email': 'new@x.test', 'password': PASSWORD}, content_type='application/json')
        self.assertFalse(get_user_model().objects.filter(email='new@x.test').exists())

    def test_reading_own_projects_still_works(self):
        key = _json(self.employee_sign_in())['data']['token']
        self.assertEqual(self.as_token(key).get('/api/projects').status_code, 200)


class SessionsPerSignIn(Base):
    """CO-270."""

    def test_each_dashboard_sign_in_gets_its_own_token_and_signs_out_alone(self):
        phone = _json(self.dashboard_sign_in())['data']['token']
        laptop = _json(self.dashboard_sign_in())['data']['token']
        self.assertNotEqual(phone, laptop)
        self.assertEqual(self.as_token(phone).post('/api/company/logout').status_code, 200)
        self.assertIn(self.as_token(phone).get('/api/company/profile').status_code, (401, 403))
        self.assertEqual(self.as_token(laptop).get('/api/company/profile').status_code, 200)

    def test_each_employee_sign_in_gets_its_own_token_and_signs_out_alone(self):
        phone = _json(self.employee_sign_in())['data']['token']
        laptop = _json(self.employee_sign_in())['data']['token']
        self.assertNotEqual(phone, laptop)
        self.assertEqual(self.as_token(phone).post('/api/auth/logout').status_code, 200)
        self.assertIn(self.as_token(phone).get('/api/auth/me').status_code, (401, 403))
        self.assertEqual(self.as_token(laptop).get('/api/auth/me').status_code, 200)

    def test_a_dashboard_session_unused_for_too_long_ends(self):
        key = _json(self.dashboard_sign_in())['data']['token']
        CompanyUserToken.objects.filter(key=key).update(last_used=timezone.now() - timedelta(days=sign_in.idle_days() + 1))
        reply = self.as_token(key).get('/api/company/profile')
        self.assertIn(reply.status_code, (401, 403))
        self.assertIn('session has ended', _json(reply)['detail'])
        self.assertFalse(CompanyUserToken.objects.filter(key=key).exists())

    def test_an_employee_session_unused_for_too_long_ends(self):
        key = _json(self.employee_sign_in())['data']['token']
        UserToken.objects.filter(key=key).update(last_used=timezone.now() - timedelta(days=sign_in.idle_days() + 1))
        self.assertIn(self.as_token(key).get('/api/auth/me').status_code, (401, 403))
        self.assertFalse(UserToken.objects.filter(key=key).exists())

    def test_a_session_in_use_keeps_going_and_is_written_at_most_hourly(self):
        key = _json(self.dashboard_sign_in())['data']['token']
        nearly = timezone.now() - timedelta(days=sign_in.idle_days() - 1)
        CompanyUserToken.objects.filter(key=key).update(last_used=nearly)
        self.assertEqual(self.as_token(key).get('/api/company/profile').status_code, 200)
        used = CompanyUserToken.objects.get(key=key).last_used
        self.assertGreater(used, timezone.now() - timedelta(minutes=1))
        self.as_token(key).get('/api/company/profile')
        self.assertEqual(CompanyUserToken.objects.get(key=key).last_used, used)

    @override_settings(SESSION_IDLE_DAYS=3)
    def test_the_idle_limit_is_a_setting(self):
        key = _json(self.dashboard_sign_in())['data']['token']
        CompanyUserToken.objects.filter(key=key).update(last_used=timezone.now() - timedelta(days=4))
        self.assertIn(self.as_token(key).get('/api/company/profile').status_code, (401, 403))

    def test_a_token_from_before_still_works_once_and_becomes_a_session(self):
        old = Token.objects.create(user=self.employee)
        self.assertEqual(self.as_token(old.key).get('/api/auth/me').status_code, 200)
        self.assertFalse(Token.objects.filter(key=old.key).exists())
        self.assertTrue(UserToken.objects.filter(key=old.key, user=self.employee).exists())
        self.assertEqual(self.as_token(old.key).get('/api/auth/me').status_code, 200)

    def test_a_reset_password_or_a_switched_off_login_ends_every_session(self):
        sana = [_json(self.dashboard_sign_in())['data']['token'] for _ in range(2)]
        bilal = [_json(self.dashboard_sign_in(email='bilal@margalla.test'))['data']['token'] for _ in range(2)]
        # Sana switches Bilal off on Logins & roles: both of Bilal's devices end, Sana's do not.
        switched = self.as_token(sana[0]).patch(f'/api/company/logins/{self.member.id}', {'is_active': False},
                                                content_type='application/json')
        self.assertEqual(switched.status_code, 200, switched.content[:300])
        self.assertFalse(CompanyUserToken.objects.filter(key__in=bilal).exists())
        self.assertEqual(CompanyUserToken.objects.filter(key__in=sana).count(), 2)
        # A password reset ends all of that login's sessions.
        from api.views.company_auth import _code_fingerprint
        CompanyUser.objects.filter(pk=self.admin.pk).update(
            reset_otp=_code_fingerprint(self.admin, '123456'), reset_otp_expires=timezone.now() + timedelta(minutes=5))
        reset = Client().post('/api/company/reset-password', {'email': 'sana@margalla.test', 'otp': '123456',
                                                               'password': 'A-new-synthetic-pass'}, content_type='application/json')
        self.assertEqual(reset.status_code, 200, reset.content[:300])
        self.assertFalse(CompanyUserToken.objects.filter(company_user=self.admin).exists())

    def test_old_tokens_are_kept_signed_in_by_the_migration(self):
        import importlib
        from django.apps import apps
        migration = importlib.import_module('core.migrations.0120_sign_in_sessions')
        token = CompanyUserToken.objects.create(company_user=self.admin, key='o' * 40)
        CompanyUserToken.objects.filter(pk=token.pk).update(last_used=None,
                                                            created=timezone.now() - timedelta(days=400))
        migration.mark_tokens_used_now(apps, None)
        self.assertEqual(self.as_token(token.key).get('/api/company/profile').status_code, 200)

    def test_a_new_employee_login_hands_no_token_to_the_admin(self):
        key = _json(self.dashboard_sign_in())['data']['token']
        reply = self.as_token(key).post('/api/company/users/create', {
            'email': 'nadia@margalla.test', 'password': 'Synthetic-pass1!', 'username': 'nadia',
            'fullName': 'Nadia Khan', 'role': 'team_member', 'phoneNumber': '+92 300 1234567'},
            content_type='application/json')
        self.assertEqual(reply.status_code, 201, reply.content[:300])
        self.assertNotIn('token', _json(reply)['data'])
        nadia = get_user_model().objects.get(email='nadia@margalla.test')
        self.assertFalse(UserToken.objects.filter(user=nadia).exists() or Token.objects.filter(user=nadia).exists())

    def test_signing_in_clears_that_logins_sessions_that_ran_out(self):
        stale = CompanyUserToken.objects.create(company_user=self.admin, key='s' * 40)
        CompanyUserToken.objects.filter(pk=stale.pk).update(last_used=timezone.now() - timedelta(days=90))
        self.dashboard_sign_in()
        self.assertFalse(CompanyUserToken.objects.filter(pk=stale.pk).exists())


class NoServerTextInErrorReplies(Base):
    """CO-271."""

    def test_a_server_error_on_sign_in_says_nothing_of_the_server(self):
        with mock.patch('api.views.company_auth.CompanyUser.objects.filter',
                        side_effect=RuntimeError("(1054, \"Unknown column 'core_companyuser.secret'\")")):
            reply = self.dashboard_sign_in()
        self.assertEqual(reply.status_code, 500)
        self.assertNotIn('Unknown column', reply.content.decode())
        self.assertEqual(_json(reply)['message'], 'Failed to login')

    def test_the_safety_net_cleans_any_api_server_error(self):
        from api.middleware.error_text import GENERIC, clean
        body, removed = clean({'status': 'error', 'message': 'Failed to fetch project',
                               'error': "OperationalError(2006, 'MySQL server has gone away')"})
        self.assertEqual(body, {'status': 'error', 'message': 'Failed to fetch project', 'error': GENERIC})
        self.assertTrue(removed)
        body, _ = clean({'message': "'NoneType' object has no attribute 'company'"})
        self.assertEqual(body['message'], GENERIC)
        body, _ = clean({'message': 'Failed: KeyError(\'x\')', 'error': "KeyError('x')"})
        self.assertEqual(body['message'], GENERIC)
        body, _ = clean({'message': "'company_id'"})                               # a bare KeyError
        self.assertEqual(body['message'], GENERIC)
        body, _ = clean({'message': 'HTTPSConnectionPool(host=api.openai.com): Max retries exceeded'})
        self.assertEqual(body['message'], GENERIC)
        body, _ = clean({'message': 'File "/app/core/x.py", line 3', 'traceback': '...'})
        self.assertEqual(body, {'message': GENERIC})

    def test_messages_a_person_wrote_are_kept(self):
        from api.middleware.error_text import clean
        for text in ('Failed to fetch project', 'No AI key is set for this company. Add one under API Keys.',
                     'Validation error', 'Please select a project from the list.', 'Server error',
                     'Could not reach the CRM just now. Try again in a minute.'):
            body, removed = clean({'message': text})
            self.assertEqual((body['message'], removed), (text, []), text)

    def test_only_server_errors_from_the_api_are_touched(self):
        from api.middleware.error_text import ServerErrorTextMiddleware
        from django.http import JsonResponse
        from django.test import RequestFactory
        raw = {'status': 'error', 'error': "IntegrityError(1062, \"Duplicate entry 'x'\")"}
        for path, code, cleaned in (('/api/x', 500, True), ('/api/x', 400, False), ('/admin/x', 500, False)):
            response = ServerErrorTextMiddleware(lambda request: JsonResponse(raw, status=code))(RequestFactory().get(path))
            self.assertEqual('Duplicate entry' not in response.content.decode(), cleaned, (path, code))

    def test_it_is_in_the_middleware_and_reads_before_gzip(self):
        chain = settings.MIDDLEWARE
        self.assertIn('api.middleware.error_text.ServerErrorTextMiddleware', chain)
        self.assertGreater(chain.index('api.middleware.error_text.ServerErrorTextMiddleware'),
                           chain.index('api.middleware.gzip.GZipExceptStreamsMiddleware'))

    def test_no_view_anyone_can_call_returns_an_exceptions_text(self):
        import ast
        root = Path(settings.BASE_DIR) / 'api' / 'views'
        offenders = []
        for path in root.glob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for fn in ast.walk(tree):
                if not isinstance(fn, ast.FunctionDef) or 'AllowAny' not in ' '.join(ast.unparse(d) for d in fn.decorator_list):
                    continue
                for handler in ast.walk(fn):
                    if isinstance(handler, ast.ExceptHandler) and handler.name:
                        for node in ast.walk(handler):
                            if isinstance(node, ast.Dict):
                                for value in node.values:
                                    if any(isinstance(n, ast.Name) and n.id == handler.name for n in ast.walk(value)):
                                        offenders.append(f'{path.name}:{node.lineno} {fn.name}')
        self.assertEqual(offenders, [])


class AppPortIsNotOpenToTheInternet(TestCase):

    def test_compose_publishes_the_app_on_this_machine_only(self):
        compose = (Path(settings.BASE_DIR) / 'docker-compose.yml').read_text(encoding='utf-8')
        self.assertIn('"127.0.0.1:8000:8000"', compose)
        self.assertNotIn('- "8000:8000"', compose)

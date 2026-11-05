"""Company sign-in, end to end over HTTP: what the dashboard sign-in form refuses and how it says so, what a
switched-off or signed-out login can still do, which tokens are taken, and how a company login reaches the
AI SDR agent (only with the agent bought, and its admin-only screens only as an owner or admin)."""
import json
import warnings
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core import mail
from django.core.cache import cache
from django.core.cache.backends.base import CacheKeyWarning
from django.test import Client, TestCase
from django.utils import timezone

from core import sign_in
from core.models import (Company, CompanyModulePurchase, CompanyRegistrationToken, CompanyUser, CompanyUserToken,
                         UserProfile, UserToken)

PASSWORD = 'a-synthetic-password'
LOGIN = '/api/company/login'


def _json(response):
    try:
        return json.loads(response.content.decode() or '{}')
    except ValueError:
        return {}


class Base(TestCase):

    def setUp(self):
        cache.clear()
        # Odd addresses make cache keys memcached would refuse; locmem only warns, and the warning is noise here.
        quiet = warnings.catch_warnings()
        quiet.__enter__()
        warnings.simplefilter('ignore', CacheKeyWarning)
        self.addCleanup(quiet.__exit__, None, None, None)
        self.company = Company.objects.create(name='Margalla Foods', email='hello@margalla.test')
        self.admin = CompanyUser.objects.create(company=self.company, email='sana@margalla.test', full_name='Sana Malik',
                                                role='admin', password_hash=make_password(PASSWORD), is_active=True)
        self.member = CompanyUser.objects.create(company=self.company, email='bilal@margalla.test', full_name='Bilal Ahmed',
                                                 role='company_user', password_hash=make_password(PASSWORD), is_active=True)

    def sign_in(self, body):
        return Client().post(LOGIN, body, content_type='application/json')

    def sign_in_raw(self, raw, content_type='application/json'):
        return Client().post(LOGIN, data=raw, content_type=content_type)

    def token_for(self, company_user):
        return sign_in.new_dashboard_token(company_user).key

    @staticmethod
    def as_header(value):
        return Client(HTTP_AUTHORIZATION=value)

    @staticmethod
    def as_token(key):
        return Client(HTTP_AUTHORIZATION=f'Token {key}')

    def buy_ai_sdr(self, **fields):
        fields.setdefault('status', 'active')
        fields.setdefault('is_complimentary', True)
        return CompanyModulePurchase.objects.create(company=self.company, module_name='ai_sdr_agent', **fields)

    def assertRefusedWithoutToken(self, reply, status, message):
        self.assertEqual(reply.status_code, status, reply.content[:300])
        body = _json(reply)
        self.assertEqual(body.get('status'), 'error')
        self.assertIn(message, body.get('message', ''))
        self.assertNotIn('token', json.dumps(body.get('data') or {}))
        self.assertFalse(CompanyUserToken.objects.exists())


class SignInFormValidationTests(Base):
    """What the sign-in form refuses: always a 4xx with words a person can read, never a 500, never a token."""

    def test_a_missing_email_is_refused_as_required(self):
        self.assertRefusedWithoutToken(self.sign_in({'password': PASSWORD}), 400, 'Email and password are required')

    def test_an_empty_email_is_refused_as_required(self):
        self.assertRefusedWithoutToken(self.sign_in({'email': '', 'password': PASSWORD}), 400,
                                       'Email and password are required')

    def test_a_null_email_is_refused_as_required(self):
        self.assertRefusedWithoutToken(self.sign_in({'email': None, 'password': PASSWORD}), 400,
                                       'Email and password are required')

    def test_a_whitespace_only_email_is_refused_and_signs_nobody_in(self):
        reply = self.sign_in({'email': '   ', 'password': PASSWORD})
        self.assertIn(reply.status_code, (400, 401), reply.content[:300])
        self.assertTrue(_json(reply)['message'])
        self.assertFalse(CompanyUserToken.objects.exists())

    def test_a_malformed_email_is_refused_like_a_wrong_one(self):
        for email in ('not-an-email', 'sana@', '@margalla.test', 'sana margalla.test'):
            reply = self.sign_in({'email': email, 'password': PASSWORD})
            self.assertEqual(reply.status_code, 401, email)
            self.assertEqual(_json(reply)['message'], 'Invalid email or password', email)
        self.assertFalse(CompanyUserToken.objects.exists())

    def test_a_missing_password_is_refused_as_required(self):
        self.assertRefusedWithoutToken(self.sign_in({'email': 'sana@margalla.test'}), 400,
                                       'Email and password are required')

    def test_an_empty_password_is_refused_as_required(self):
        self.assertRefusedWithoutToken(self.sign_in({'email': 'sana@margalla.test', 'password': ''}), 400,
                                       'Email and password are required')

    def test_an_empty_body_is_refused_as_required(self):
        self.assertRefusedWithoutToken(self.sign_in({}), 400, 'Email and password are required')
        self.assertRefusedWithoutToken(self.sign_in_raw(''), 400, 'Email and password are required')

    def test_a_wrong_password_is_refused_without_a_token(self):
        self.assertRefusedWithoutToken(self.sign_in({'email': 'sana@margalla.test', 'password': 'wrong'}), 401,
                                       'Invalid email or password')

    def test_an_unknown_email_is_refused_without_a_token(self):
        self.assertRefusedWithoutToken(self.sign_in({'email': 'nobody@margalla.test', 'password': PASSWORD}), 401,
                                       'Invalid email or password')

    def test_the_reply_does_not_say_whether_the_email_has_a_login(self):
        wrong_password = self.sign_in({'email': 'sana@margalla.test', 'password': 'wrong'})
        unknown_email = self.sign_in({'email': 'nobody@margalla.test', 'password': 'wrong'})
        self.assertEqual(wrong_password.status_code, unknown_email.status_code)
        self.assertEqual(_json(wrong_password), _json(unknown_email))

    def test_a_password_that_is_not_text_is_refused_not_a_crash(self):
        for password in (12345678, ['a', 'b'], {'x': 1}, True):
            reply = self.sign_in({'email': 'sana@margalla.test', 'password': password})
            self.assertEqual(reply.status_code, 401, (password, reply.content[:200]))
            self.assertEqual(_json(reply)['message'], 'Invalid email or password')

    def test_an_email_that_is_not_text_is_refused_not_a_crash(self):
        for email in (12345, ['sana@margalla.test'], {'email': 'sana@margalla.test'}):
            reply = self.sign_in({'email': email, 'password': PASSWORD})
            self.assertIn(reply.status_code, (400, 401), (email, reply.content[:200]))
        self.assertFalse(CompanyUserToken.objects.exists())

    def test_extra_long_inputs_are_refused_not_a_crash(self):
        reply = self.sign_in({'email': 'a' * 5000 + '@margalla.test', 'password': PASSWORD})
        self.assertRefusedWithoutToken(reply, 401, 'Invalid email or password')
        reply = self.sign_in({'email': 'sana@margalla.test', 'password': 'p' * 100_000})
        self.assertRefusedWithoutToken(reply, 401, 'Invalid email or password')

    def test_a_body_that_is_not_json_is_refused_with_400(self):
        reply = self.sign_in_raw('email=sana@margalla.test&password={')
        self.assertEqual(reply.status_code, 400, reply.content[:300])
        self.assertTrue(_json(reply).get('message') or _json(reply).get('detail'))
        self.assertFalse(CompanyUserToken.objects.exists())

    def test_a_json_body_that_is_not_an_object_is_refused_with_400(self):
        reply = self.sign_in_raw(json.dumps(['sana@margalla.test', PASSWORD]))
        self.assertEqual(reply.status_code, 400, reply.content[:300])
        self.assertFalse(CompanyUserToken.objects.exists())

    def test_a_company_id_that_is_not_a_number_is_refused_not_a_crash(self):
        reply = self.sign_in({'email': 'sana@margalla.test', 'password': PASSWORD, 'companyId': 'abc'})
        self.assertIn(reply.status_code, (400, 401), reply.content[:300])
        self.assertFalse(CompanyUserToken.objects.exists())

    def test_a_company_id_of_another_company_is_refused_like_a_wrong_password(self):
        other = Company.objects.create(name='Rawal Traders', email='office@rawal.test')
        reply = self.sign_in({'email': 'sana@margalla.test', 'password': PASSWORD, 'companyId': other.id})
        self.assertRefusedWithoutToken(reply, 401, 'Invalid email or password')

    def test_reading_the_form_is_not_allowed(self):
        self.assertEqual(Client().get(LOGIN).status_code, 405)

    def test_the_right_details_sign_in_and_say_who_and_which_company(self):
        reply = self.sign_in({'email': 'sana@margalla.test', 'password': PASSWORD})
        self.assertEqual(reply.status_code, 200, reply.content[:300])
        data = _json(reply)['data']
        self.assertEqual((data['user']['email'], data['user']['role'], data['user']['companyId']),
                         ('sana@margalla.test', 'admin', self.company.id))
        self.assertTrue(CompanyUserToken.objects.filter(key=data['token'], company_user=self.admin).exists())
        self.assertNotIn('password', json.dumps(data).lower())


class EmailIsReadAsAPersonTypesItTests(Base):
    """One dashboard login per address whatever its case (registration checks `iexact`), the wrong-password
    count ignores case and spaces, and "Forgot password" trims the address; sign-in should read it the same."""

    def test_the_email_in_another_case_signs_in(self):
        reply = self.sign_in({'email': 'Sana@Margalla.TEST', 'password': PASSWORD})
        self.assertEqual(reply.status_code, 200, reply.content[:300])

    def test_spaces_around_the_email_are_ignored(self):
        reply = self.sign_in({'email': '  sana@margalla.test  ', 'password': PASSWORD})
        self.assertEqual(reply.status_code, 200, reply.content[:300])

    def test_wrong_passwords_in_any_case_or_spacing_count_on_the_same_account(self):
        for typed in ('SANA@margalla.test', ' sana@margalla.test', 'sana@MARGALLA.test '):
            for _ in range(sign_in.MAX_WRONG_PASSWORDS // 3 + 1):
                self.sign_in({'email': typed, 'password': 'wrong'})
        locked = self.sign_in({'email': 'sana@margalla.test', 'password': PASSWORD})
        self.assertRefusedWithoutToken(locked, 429, 'Too many wrong passwords')


class AccountStateTests(Base):
    """A switched-off login, a removed company, a signed-out device."""

    def test_a_switched_off_login_with_the_right_password_is_refused_without_a_token(self):
        CompanyUser.objects.filter(pk=self.member.pk).update(is_active=False)
        self.assertRefusedWithoutToken(self.sign_in({'email': 'bilal@margalla.test', 'password': PASSWORD}), 403,
                                       'Account is inactive')

    def test_a_switched_off_login_with_a_wrong_password_looks_like_any_wrong_password(self):
        CompanyUser.objects.filter(pk=self.member.pk).update(is_active=False)
        self.assertRefusedWithoutToken(self.sign_in({'email': 'bilal@margalla.test', 'password': 'wrong'}), 401,
                                       'Invalid email or password')

    def test_a_switched_off_logins_old_token_stops_working(self):
        key = self.token_for(self.member)
        CompanyUser.objects.filter(pk=self.member.pk).update(is_active=False)
        reply = self.as_token(key).get('/api/company/profile')
        self.assertIn(reply.status_code, (401, 403))
        self.assertIn('inactive', _json(reply)['detail'])

    def test_a_deleted_companys_logins_cannot_sign_in_and_their_tokens_stop(self):
        key = self.token_for(self.admin)
        self.company.delete()
        self.assertRefusedWithoutToken(self.sign_in({'email': 'sana@margalla.test', 'password': PASSWORD}), 401,
                                       'Invalid email or password')
        self.assertIn(self.as_token(key).get('/api/company/profile').status_code, (401, 403))

    def test_after_signing_out_the_token_no_longer_works_anywhere(self):
        self.buy_ai_sdr()
        key = _json(self.sign_in({'email': 'sana@margalla.test', 'password': PASSWORD}))['data']['token']
        self.assertEqual(self.as_token(key).get('/api/sdr/leads').status_code, 200)
        self.assertEqual(self.as_token(key).post('/api/company/logout').status_code, 200)
        for path in ('/api/company/profile', '/api/sdr/leads'):
            reply = self.as_token(key).get(path)
            self.assertIn(reply.status_code, (401, 403), path)
            self.assertEqual(_json(reply)['detail'], 'Invalid token', path)
        self.assertIn(self.as_token(key).post('/api/company/logout').status_code, (401, 403))

    def test_signing_out_without_a_token_is_refused(self):
        self.assertIn(Client().post('/api/company/logout').status_code, (401, 403))


class TokenHeaderTests(Base):
    """How the Authorization header is read on company endpoints."""

    def test_the_token_keyword_is_accepted(self):
        self.assertEqual(self.as_header(f'Token {self.token_for(self.admin)}').get('/api/company/profile').status_code, 200)

    def test_the_bearer_keyword_is_accepted_too(self):
        reply = self.as_header(f'Bearer {self.token_for(self.admin)}').get('/api/company/profile')
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(_json(reply)['data']['user']['email'], 'sana@margalla.test')

    def test_a_key_without_a_keyword_is_not_a_sign_in(self):
        for header in (self.token_for(self.admin), f'token {self.token_for(self.admin)}', 'Token ', 'Token'):
            reply = self.as_header(header).get('/api/company/profile')
            self.assertIn(reply.status_code, (401, 403), header)
            self.assertIn('not provided', _json(reply)['detail'], header)

    def test_a_garbage_token_is_refused_as_invalid(self):
        for key in ('garbage', 'x' * 40, 'x' * 5000, "' OR 1=1 --"):
            reply = self.as_token(key).get('/api/company/profile')
            self.assertIn(reply.status_code, (401, 403), key[:20])
            self.assertEqual(_json(reply)['detail'], 'Invalid token', key[:20])

    def test_no_header_at_all_is_refused(self):
        self.assertIn(Client().get('/api/company/profile').status_code, (401, 403))


class OnlyCompanyLoginsAreTakenTests(Base):
    """Employee and platform-staff logins are not company logins, even with a valid token of their own."""

    def setUp(self):
        super().setUp()
        self.buy_ai_sdr()
        User = get_user_model()
        self.staff = User.objects.create_user(username='root', email='root@platform.test', password=PASSWORD,
                                              is_staff=True, is_superuser=True)
        self.employee = User.objects.create_user(username='kiran', email='kiran@margalla.test', password=PASSWORD)
        UserProfile.objects.update_or_create(user=self.employee, defaults={
            'company': self.company, 'created_by_company_user': self.admin, 'role': 'team_member'})

    def user_token(self, user):
        return sign_in.new_user_token(user).key

    def test_a_staff_token_is_not_a_company_login(self):
        key = self.user_token(self.staff)
        for path in ('/api/company/profile', '/api/sdr/leads', '/api/sdr/checks'):
            reply = self.as_token(key).get(path)
            self.assertIn(reply.status_code, (401, 403), path)
            self.assertNotEqual(_json(reply).get('error'), 'subscription_required', path)
            self.assertNotIn('data', _json(reply), path)

    def test_an_employee_token_is_not_a_company_login(self):
        key = self.user_token(self.employee)
        for path in ('/api/company/profile', '/api/sdr/leads'):
            reply = self.as_token(key).get(path)
            self.assertIn(reply.status_code, (401, 403), path)
            self.assertNotIn('data', _json(reply), path)

    def test_a_staff_or_employee_password_does_not_sign_in_to_the_dashboard(self):
        for email in ('root@platform.test', 'kiran@margalla.test'):
            self.assertEqual(self.sign_in({'email': email, 'password': PASSWORD}).status_code, 401, email)
        self.assertFalse(CompanyUserToken.objects.exists())

    def test_a_company_token_on_an_employee_endpoint_is_told_what_it_is(self):
        reply = self.as_token(self.token_for(self.admin)).get('/api/auth/me')
        self.assertIn(reply.status_code, (401, 403))
        self.assertIn('company dashboard login', _json(reply)['detail'])


class AISDRNeedsTheAgentTests(Base):
    """GET /api/sdr/leads through the module-access middleware with real rows (api/tests_module_access.py stubs them)."""

    def leads(self, company_user=None):
        return self.as_token(self.token_for(company_user or self.admin)).get('/api/sdr/leads')

    def assertBlocked(self, reply, reason):
        self.assertEqual(reply.status_code, 403, reply.content[:300])
        body = _json(reply)
        self.assertEqual((body['error'], body['reason'], body['module_name']),
                         ('subscription_required', reason, 'ai_sdr_agent'))
        self.assertTrue(body['message'])

    def test_a_company_without_the_agent_is_refused(self):
        self.assertBlocked(self.leads(), 'not_bought')

    def test_a_company_with_the_agent_gets_its_leads(self):
        self.buy_ai_sdr()
        reply = self.leads()
        self.assertEqual(reply.status_code, 200, reply.content[:300])
        self.assertEqual(self.leads(self.member).status_code, 200)

    def test_a_cancelled_agent_is_refused_as_lapsed(self):
        self.buy_ai_sdr(status='cancelled')
        self.assertBlocked(self.leads(), 'lapsed')

    def test_free_access_that_ran_out_is_refused(self):
        self.buy_ai_sdr(expires_at=timezone.now() - timedelta(days=1))
        self.assertBlocked(self.leads(), 'lapsed')

    def test_a_failed_payment_says_to_update_the_card(self):
        self.buy_ai_sdr(status='past_due', is_complimentary=False)
        reply = self.leads()
        self.assertBlocked(reply, 'payment_failed')
        self.assertIn('card', _json(reply)['message'])

    def test_another_companys_agent_does_not_count(self):
        other = Company.objects.create(name='Rawal Traders', email='office@rawal.test')
        CompanyModulePurchase.objects.create(company=other, module_name='ai_sdr_agent', status='active',
                                             is_complimentary=True)
        self.assertBlocked(self.leads(), 'not_bought')

    def test_without_a_sign_in_the_agent_is_refused(self):
        self.buy_ai_sdr()
        self.assertIn(Client().get('/api/sdr/leads').status_code, (401, 403))

    def test_a_switched_off_login_cannot_reach_the_agent(self):
        self.buy_ai_sdr()
        key = self.token_for(self.member)
        CompanyUser.objects.filter(pk=self.member.pk).update(is_active=False)
        reply = self.as_token(key).get('/api/sdr/leads')
        self.assertIn(reply.status_code, (401, 403))
        self.assertIn('inactive', _json(reply)['detail'])


class AISDRAdminScreensTests(Base):
    """AI SDR -> Tests (/api/sdr/checks) is for an owner or admin; other roles are refused."""

    def setUp(self):
        super().setUp()
        self.buy_ai_sdr()

    def checks(self, role):
        login = CompanyUser.objects.create(company=self.company, email=f'{role}@margalla.test', full_name=role,
                                           role=role, password_hash=make_password(PASSWORD), is_active=True)
        return self.as_token(self.token_for(login)).get('/api/sdr/checks')

    def test_an_ordinary_login_is_refused(self):
        for role in ('company_user', 'manager', 'project_manager'):
            reply = self.checks(role)
            self.assertEqual(reply.status_code, 403, role)
            self.assertNotIn('data', _json(reply), role)

    def test_an_owner_and_an_admin_get_in(self):
        for role in ('owner', 'admin'):
            reply = self.checks(role)
            self.assertEqual(reply.status_code, 200, (role, reply.content[:300]))
            self.assertIn('suites', _json(reply)['data'])


class OtherSignInFormsTests(Base):
    """Registration and password reset refuse what is missing or broken with a 400 and a message."""

    def test_registration_without_a_token_or_password_is_refused(self):
        for body in ({}, {'token': 'x'}, {'password': PASSWORD}, {'token': '', 'password': ''}):
            reply = Client().post('/api/company/register', body, content_type='application/json')
            self.assertEqual(reply.status_code, 400, body)
            self.assertEqual(_json(reply)['message'], 'Token and password are required')

    def test_registration_with_an_unknown_used_or_expired_link_is_refused_without_a_token(self):
        company = Company.objects.create(name='Rawal Traders', email='office@rawal.test')
        CompanyRegistrationToken.objects.create(company=company, token='u' * 64, is_used=True,
                                                expires_at=timezone.now() + timedelta(days=7))
        CompanyRegistrationToken.objects.create(company=company, token='e' * 64,
                                                expires_at=timezone.now() - timedelta(minutes=1))
        for token, message in (('n' * 64, 'Invalid token'), ('u' * 64, 'already been used'), ('e' * 64, 'expired')):
            reply = Client().post('/api/company/register', {'token': token, 'password': PASSWORD},
                                  content_type='application/json')
            self.assertEqual(reply.status_code, 400, token[:1])
            self.assertIn(message, _json(reply)['message'])
            self.assertNotIn('data', _json(reply))
        self.assertFalse(CompanyUser.objects.filter(company=company).exists())

    def test_checking_a_link_without_a_token_is_refused(self):
        reply = Client().get('/api/company/verify-token')
        self.assertEqual((reply.status_code, _json(reply)['message']), (400, 'Token is required'))

    def test_forgot_password_needs_an_email_and_never_says_if_it_has_a_login(self):
        reply = Client().post('/api/company/forgot-password', {'email': '   '}, content_type='application/json')
        self.assertEqual((reply.status_code, _json(reply)['message']), (400, 'Email is required'))
        known = Client().post('/api/company/forgot-password', {'email': 'sana@margalla.test'}, content_type='application/json')
        unknown = Client().post('/api/company/forgot-password', {'email': 'nobody@margalla.test'},
                                content_type='application/json')
        self.assertEqual((known.status_code, _json(known)), (unknown.status_code, _json(unknown)))
        self.assertEqual(len(mail.outbox), 1)

    def test_a_new_password_that_is_too_short_or_missing_is_refused(self):
        reply = Client().post('/api/company/reset-password', {'email': 'sana@margalla.test', 'otp': '123456',
                                                              'password': 'short'}, content_type='application/json')
        self.assertEqual((reply.status_code, _json(reply)['message']), (400, 'Password must be at least 8 characters long'))
        reply = Client().post('/api/company/reset-password', {'email': 'sana@margalla.test', 'otp': '123456'},
                              content_type='application/json')
        self.assertEqual(reply.status_code, 400)
        self.assertIn('required', _json(reply)['message'])

    def test_checking_a_code_without_the_email_or_code_is_refused(self):
        for body in ({}, {'email': 'sana@margalla.test'}, {'otp': '123456'}, {'email': ' ', 'otp': ' '}):
            reply = Client().post('/api/company/verify-otp', body, content_type='application/json')
            self.assertEqual((reply.status_code, _json(reply)['message']), (400, 'Email and code are required'), body)

    def test_a_body_that_is_not_json_is_refused_with_400_on_every_public_form(self):
        for path in ('/api/company/register', '/api/company/verify-otp', '/api/company/reset-password'):
            reply = Client().post(path, data='{not json', content_type='application/json')
            self.assertEqual(reply.status_code, 400, (path, reply.content[:200]))


class SignInRateLimitTests(Base):
    """Throttles are off in settings_test; what can break is the wiring and the production rate."""

    PUBLIC = ('register_company_user', 'company_signup', 'login_company_user', 'forgot_password',
              'verify_reset_otp', 'reset_password')

    def test_every_public_sign_in_form_has_the_per_caller_limit(self):
        from api.views import company_auth
        for name in self.PUBLIC:
            self.assertIn(company_auth.CompanyAuthThrottle, getattr(company_auth, name).cls.throttle_classes, name)

    def test_production_sets_a_rate_for_it(self):
        from project_manager_ai import settings as production
        self.assertTrue(production.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].get('company_auth'))

    def test_the_limit_answers_429_once_reached(self):
        from api.views.company_auth import CompanyAuthThrottle
        with mock.patch.object(CompanyAuthThrottle, 'THROTTLE_RATES', {'company_auth': '3/min'}):
            replies = [self.sign_in({'email': 'nobody@margalla.test', 'password': 'wrong'}).status_code
                       for _ in range(4)]
            self.assertEqual(replies, [401, 401, 401, 429])
            self.assertEqual(self.sign_in({'email': 'sana@margalla.test', 'password': PASSWORD}).status_code, 429)
        self.assertFalse(CompanyUserToken.objects.exists())

    def test_a_locked_account_refuses_the_right_password_without_a_token(self):
        for _ in range(sign_in.MAX_WRONG_PASSWORDS):
            self.sign_in({'email': 'sana@margalla.test', 'password': 'wrong'})
        self.assertRefusedWithoutToken(self.sign_in({'email': 'sana@margalla.test', 'password': PASSWORD}), 429,
                                       'reset the password')
        self.assertFalse(UserToken.objects.exists())

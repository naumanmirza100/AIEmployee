"""The emailed code that resets a dashboard login's password.

Six digits, good for ten minutes. A wrong code was refused and nothing else: the
code stayed good, so it could be tried again and again, held back only by a
limit per caller address that a caller could sidestep. The code was also kept
in the database as typed.
"""
import json
import re
from datetime import timedelta

from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from api.views import company_auth
from core.models import Company, CompanyUser, CompanyUserToken


class ResetCodeTests(TestCase):

    def setUp(self):
        cache.clear()
        company = Company.objects.create(name='Acme', email='acme@test.local')
        self.dana = CompanyUser.objects.create(company=company, email='dana@acme.test', full_name='Dana Malik',
                                               role='admin', password_hash='x', is_active=True)
        self.omar = CompanyUser.objects.create(company=company, email='omar@acme.test', full_name='Omar Sheikh',
                                               role='company_user', password_hash='x', is_active=True)

    def post(self, path, **body):
        response = Client().post(f'/api/company/{path}', json.dumps(body), content_type='application/json')
        return response.status_code, json.loads(response.content)

    def ask(self, email='dana@acme.test'):
        """Press 'Forgot password' and read the code out of the email, if one came."""
        before = len(mail.outbox)
        code, _ = self.post('forgot-password', email=email)
        self.assertEqual(code, 200)
        if len(mail.outbox) == before:
            return None
        return re.search(r'code is: (\d{6})', mail.outbox[-1].body).group(1)

    def verify(self, typed, email='dana@acme.test'):
        return self.post('verify-otp', email=email, otp=typed)[0]

    def reset(self, typed, password='A-new-one-2026', email='dana@acme.test'):
        return self.post('reset-password', email=email, otp=typed, password=password)[0]

    def wrong(self, right):
        return '000000' if right != '000000' else '111111'

    def can_sign_in(self, password, email='dana@acme.test'):
        return self.post('login', email=email, password=password)[0] == 200

    # ---- the ordinary way through ------------------------------------------

    def test_the_emailed_code_resets_the_password(self):
        CompanyUserToken.objects.create(company_user=self.dana)
        code = self.ask()
        self.assertEqual(self.verify(code), 200)
        self.assertEqual(self.reset(code), 200)
        self.assertTrue(self.can_sign_in('A-new-one-2026'))
        self.dana.refresh_from_db()
        self.assertEqual((self.dana.reset_otp, self.dana.reset_otp_expires, self.dana.reset_otp_attempts),
                         (None, None, 0))
        self.assertEqual(self.reset(code, password='Another-one-2026'), 400)        # a code works once

    def test_checking_the_code_first_does_not_use_up_the_try_that_sets_the_password(self):
        code = self.ask()
        for _ in range(company_auth.OTP_MAX_TRIES + 2):
            self.assertEqual(self.verify(code), 200)
        self.assertEqual(self.reset(code), 200)

    # ---- guessing ----------------------------------------------------------

    def test_five_wrong_tries_and_the_code_is_dead(self):
        code = self.ask()
        for _ in range(company_auth.OTP_MAX_TRIES):
            self.assertEqual(self.verify(self.wrong(code)), 400)
        self.assertEqual(self.verify(code), 400)
        self.assertEqual(self.reset(code), 400)
        self.assertFalse(self.can_sign_in('A-new-one-2026'))
        self.dana.refresh_from_db()
        self.assertIsNone(self.dana.reset_otp)

    def test_four_wrong_tries_still_leave_the_right_code_working(self):
        code = self.ask()
        for _ in range(company_auth.OTP_MAX_TRIES - 1):
            self.assertEqual(self.verify(self.wrong(code)), 400)
        self.assertEqual(self.reset(code), 200)

    def test_wrong_tries_at_setting_the_password_count_too(self):
        code = self.ask()
        for _ in range(3):
            self.assertEqual(self.verify(self.wrong(code)), 400)
        for _ in range(2):
            self.assertEqual(self.reset(self.wrong(code)), 400)
        self.assertEqual(self.reset(code), 400)

    def test_the_count_is_on_the_login_not_on_where_the_tries_come_from(self):
        code = self.ask()
        for n in range(company_auth.OTP_MAX_TRIES):
            response = Client().post('/api/company/verify-otp',
                                     json.dumps({'email': 'dana@acme.test', 'otp': self.wrong(code)}),
                                     content_type='application/json',
                                     REMOTE_ADDR=f'10.0.0.{n + 1}', HTTP_X_FORWARDED_FOR=f'203.0.113.{n + 1}')
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.verify(code), 400)

    def test_one_logins_wrong_tries_do_not_touch_anothers_code(self):
        danas, omars = self.ask(), self.ask('omar@acme.test')
        for _ in range(company_auth.OTP_MAX_TRIES):
            self.verify(self.wrong(danas))
        self.assertEqual(self.verify(omars, 'omar@acme.test'), 200)

    def test_the_reply_is_the_same_whether_or_not_the_address_has_a_login(self):
        self.ask()
        known = self.post('verify-otp', email='dana@acme.test', otp='not-it')
        unknown = self.post('verify-otp', email='nobody@acme.test', otp='not-it')
        self.assertEqual(known, unknown)
        self.assertIn('ask for a new one', known[1]['message'])

    # ---- new codes ---------------------------------------------------------

    def test_a_new_code_replaces_the_old_one_and_starts_the_count_again(self):
        first = self.ask()
        for _ in range(company_auth.OTP_MAX_TRIES - 1):
            self.verify(self.wrong(first))
        second = self.ask()
        self.dana.refresh_from_db()
        self.assertEqual(self.dana.reset_otp_attempts, 0)
        if first != second:
            self.assertEqual(self.verify(first), 400)
        self.assertEqual(self.reset(second), 200)

    def test_only_so_many_codes_an_hour_for_one_login(self):
        codes = [self.ask() for _ in range(company_auth.OTP_MAX_CODES_PER_HOUR)]
        self.assertNotIn(None, codes)
        self.dana.refresh_from_db()
        kept = self.dana.reset_otp
        self.assertIsNone(self.ask())                       # the reply is the usual one; no email goes
        self.dana.refresh_from_db()
        self.assertEqual(self.dana.reset_otp, kept)         # and the last code sent still stands
        self.assertEqual(self.verify(codes[-1]), 200)
        self.assertIsNotNone(self.ask('omar@acme.test'))    # somebody else is not held up by it

    # ---- what is stored ----------------------------------------------------

    def test_the_code_itself_is_not_kept(self):
        code = self.ask()
        self.dana.refresh_from_db()
        self.assertNotIn(code, self.dana.reset_otp)
        self.assertEqual(len(self.dana.reset_otp), 64)
        self.assertNotEqual(company_auth._code_fingerprint(self.dana, code),
                            company_auth._code_fingerprint(self.omar, code))

    def test_a_code_written_into_the_database_as_typed_does_not_work(self):
        CompanyUser.objects.filter(pk=self.dana.pk).update(
            reset_otp='123456', reset_otp_expires=timezone.now() + timedelta(minutes=5))
        self.assertEqual(self.verify('123456'), 400)
        self.assertEqual(self.reset('123456'), 400)

    def test_a_login_that_is_switched_off_cannot_be_reset(self):
        self.dana.is_active = False
        self.dana.reset_otp = company_auth._code_fingerprint(self.dana, '123456')
        self.dana.reset_otp_expires = timezone.now() + timedelta(minutes=5)
        self.dana.save()
        self.assertEqual(self.verify('123456'), 400)
        self.assertEqual(self.reset('123456'), 400)
        self.dana.refresh_from_db()
        self.assertEqual(self.dana.password_hash, 'x')

    def test_an_expired_code_does_not_work(self):
        code = self.ask()
        CompanyUser.objects.filter(pk=self.dana.pk).update(reset_otp_expires=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.verify(code), 400)
        self.assertEqual(self.reset(code), 400)

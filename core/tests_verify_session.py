"""Fulfilling a checkout must follow the subscription Stripe says it bought.

verify_session is public and a paid checkout session stays paid forever, so an
old success-page URL could be replayed after its subscription ended. That
pointed the row back at the dead subscription (the one the company now pays
for was orphaned and they were locked out), or undid an admin deactivation.
And when Stripe could not be asked for the subscription, the purchase was
stored as a 30-day one-time buy that no later webhook could match.
Stripe itself is faked here.
"""
from datetime import timedelta
from unittest import mock

import stripe
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from api.views import module_purchase
from core.models import AgentPlan, Company, CompanyModulePurchase, CompanyUser


class FakeSession(dict):
    __getattr__ = dict.__getitem__


def at_stripe(sub_id, status, period_end=None):
    end = period_end or timezone.now() + timedelta(days=30)
    return {'id': sub_id, 'status': status, 'cancel_at_period_end': False,
            'current_period_start': int((end - timedelta(days=30)).timestamp()),
            'current_period_end': int(end.timestamp())}


class VerifySessionTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local', stripe_customer_id='cus_1')
        self.login = CompanyUser.objects.create(company=self.company, email='dana@test.local', full_name='Dana',
                                                role='admin', password_hash='x', is_active=True)
        self.plan = AgentPlan.objects.create(agent_name='hr_agent', billing_interval='month', price_usd=10,
                                             stripe_price_id='price_1', is_active=True)
        patcher = mock.patch.object(module_purchase.stripe, 'api_key', 'sk_test_' + 'x' * 24)   # made up
        patcher.start()
        self.addCleanup(patcher.stop)

    def checkout_paid_for(self, sub_id):
        session = FakeSession(payment_status='paid', subscription=sub_id, metadata={
            'company_id': str(self.company.id), 'company_user_id': str(self.login.id),
            'module_name': 'hr_agent', 'plan_id': str(self.plan.id), 'type': 'module_subscription'})
        patcher = mock.patch.object(module_purchase.stripe.checkout.Session, 'retrieve', return_value=session)
        patcher.start()
        self.addCleanup(patcher.stop)
        return session

    def stripe_says(self, answer):
        patcher = mock.patch.object(module_purchase.stripe.Subscription, 'retrieve',
                                    **({'side_effect': answer} if isinstance(answer, Exception) else {'return_value': answer}))
        patcher.start()
        self.addCleanup(patcher.stop)

    def verify(self):
        request = APIRequestFactory().post('/', {'session_id': 'cs_1'}, format='json')
        return module_purchase.verify_session(request)

    def row(self, **fields):
        return CompanyModulePurchase.objects.create(company=self.company, module_name='hr_agent', **fields)

    # ---- a fresh checkout ---------------------------------------------------------

    def test_a_new_subscription_opens_the_agent(self):
        self.checkout_paid_for('sub_new')
        self.stripe_says(at_stripe('sub_new', 'active'))
        self.assertEqual(self.verify().status_code, 200)
        purchase = CompanyModulePurchase.objects.get(company=self.company, module_name='hr_agent')
        self.assertEqual(purchase.stripe_subscription_id, 'sub_new')
        self.assertTrue(purchase.is_active())

    def test_a_first_payment_still_in_progress_grants_nothing_yet(self):
        self.checkout_paid_for('sub_new')
        self.stripe_says(at_stripe('sub_new', 'incomplete'))
        self.verify()
        purchase = CompanyModulePurchase.objects.get(company=self.company, module_name='hr_agent')
        self.assertEqual(purchase.stripe_subscription_id, 'sub_new')   # tracked, so the next event finds it
        self.assertFalse(purchase.is_active())

    # ---- an old session replayed ------------------------------------------------

    def test_replaying_an_ended_subscription_leaves_the_live_one_in_charge(self):
        purchase = self.row(status='active', stripe_subscription_id='sub_live',
                            current_period_end=timezone.now() + timedelta(days=20))
        self.checkout_paid_for('sub_old')
        self.stripe_says(at_stripe('sub_old', 'canceled', period_end=timezone.now() - timedelta(days=40)))
        self.assertEqual(self.verify().status_code, 409)
        purchase.refresh_from_db()
        self.assertEqual(purchase.stripe_subscription_id, 'sub_live')
        self.assertTrue(purchase.is_active())

    def test_replaying_does_not_undo_an_admin_deactivation(self):
        # Admin deactivation cancels at Stripe immediately; the period end stays in the future.
        purchase = self.row(status='cancelled', cancelled_reason='admin_deactivated',
                            stripe_subscription_id='sub_1',
                            current_period_end=timezone.now() + timedelta(days=20))
        self.checkout_paid_for('sub_1')
        self.stripe_says(at_stripe('sub_1', 'canceled'))
        self.assertEqual(self.verify().status_code, 409)
        purchase.refresh_from_db()
        self.assertEqual((purchase.status, purchase.cancelled_reason), ('cancelled', 'admin_deactivated'))
        self.assertFalse(purchase.is_active())

    # ---- Stripe cannot be asked ---------------------------------------------------

    def test_verify_waits_rather_than_storing_a_one_time_purchase(self):
        self.checkout_paid_for('sub_new')
        self.stripe_says(stripe.error.APIConnectionError('down'))
        self.assertEqual(self.verify().status_code, 502)
        self.assertFalse(CompanyModulePurchase.objects.filter(company=self.company).exists())

    def test_the_webhook_fails_so_stripe_retries(self):
        session = self.checkout_paid_for('sub_new')
        self.stripe_says(stripe.error.APIConnectionError('down'))
        with self.assertRaises(stripe.error.StripeError):
            module_purchase._handle_checkout_completed(session)
        self.assertFalse(CompanyModulePurchase.objects.filter(company=self.company).exists())

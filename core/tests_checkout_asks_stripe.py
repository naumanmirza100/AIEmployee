"""Before a second subscription is opened, ask Stripe about the first.

Checkout looked only at our own record. When that record was out of date (a
renewal whose event never arrived), the agent looked expired, the lock screen
invited the admin to buy again, and checkout opened a second subscription
beside the live one: billed twice. Stripe itself is faked here.
"""
from datetime import timedelta
from unittest import mock

import stripe
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import module_purchase
from core.models import AgentPlan, Company, CompanyModulePurchase, CompanyUser


def at_stripe(status, period_end=None):
    end = period_end or timezone.now() + timedelta(days=30)
    return {'id': 'sub_old', 'status': status, 'cancel_at_period_end': False,
            'current_period_start': int((end - timedelta(days=30)).timestamp()),
            'current_period_end': int(end.timestamp())}


class CheckoutAsksStripeTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local', stripe_customer_id='cus_1')
        self.login = CompanyUser.objects.create(company=self.company, email='dana@test.local', full_name='Dana',
                                                role='admin', password_hash='x', is_active=True)
        self.plan = AgentPlan.objects.create(agent_name='hr_agent', billing_interval='month', price_usd=10,
                                             stripe_price_id='price_1', is_active=True)
        for patcher in (mock.patch.object(module_purchase.stripe, 'api_key', 'sk_test_' + 'x' * 24),   # made up
                        mock.patch.object(module_purchase, '_ensure_stripe_customer', return_value='cus_1')):
            patcher.start()
            self.addCleanup(patcher.stop)
        opened = mock.patch.object(module_purchase.stripe.checkout.Session, 'create',
                                   return_value=mock.Mock(url='https://checkout.example/1', id='cs_1'))
        self.opened = opened.start()
        self.addCleanup(opened.stop)

    def row(self, **fields):
        defaults = dict(status='active', stripe_subscription_id='sub_old', billing_interval='month',
                        current_period_end=timezone.now() - timedelta(hours=2))      # looks expired to us
        return CompanyModulePurchase.objects.create(company=self.company, module_name='hr_agent',
                                                    **{**defaults, **fields})

    def stripe_says(self, answer):
        patcher = mock.patch.object(module_purchase.stripe.Subscription, 'retrieve',
                                    **({'side_effect': answer} if isinstance(answer, Exception) else {'return_value': answer}))
        asked = patcher.start()
        self.addCleanup(patcher.stop)
        return asked

    def checkout(self):
        request = APIRequestFactory().post('/', {'module_name': 'hr_agent', 'plan_id': self.plan.id}, format='json')
        force_authenticate(request, user=self.login)
        return module_purchase.create_checkout_session(request)

    # ---- still live at Stripe ---------------------------------------------------

    def test_a_renewal_we_missed_is_put_right_instead_of_sold_twice(self):
        purchase = self.row()
        self.assertFalse(purchase.is_active())                       # what the lock screen saw
        self.stripe_says(at_stripe('active'))
        response = self.checkout()
        self.assertEqual((response.status_code, response.data['error']), (409, 'already_active'))
        self.assertIn('Reload the page', response.data['message'])
        self.opened.assert_not_called()
        purchase.refresh_from_db()
        self.assertTrue(purchase.is_active())                        # and the agent is open again

    def test_one_whose_payment_is_being_retried_is_sent_to_billing(self):
        purchase = self.row()
        self.stripe_says(at_stripe('past_due'))
        response = self.checkout()
        self.assertEqual((response.status_code, response.data['error']), (409, 'payment_required'))
        self.assertIn('Billing page', response.data['message'])
        self.opened.assert_not_called()
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, 'past_due')

    def test_any_state_stripe_has_not_finished_with_is_refused(self):
        for state in ('unpaid', 'incomplete', 'paused', 'trialing', 'something_new'):
            CompanyModulePurchase.objects.all().delete()
            self.row(status='expired')
            self.stripe_says(at_stripe(state, period_end=timezone.now() - timedelta(days=1)))
            self.assertEqual(self.checkout().status_code, 409, state)
        self.opened.assert_not_called()

    def test_one_an_admin_switched_off_is_not_switched_back_on_or_sold_again(self):
        purchase = self.row(status='cancelled', cancelled_reason='admin_deactivated')
        self.stripe_says(at_stripe('active'))
        response = self.checkout()
        self.assertEqual((response.status_code, response.data['error']), (409, 'payment_required'))
        self.opened.assert_not_called()
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, 'cancelled')

    # ---- ended at Stripe: buying again is right -----------------------------------

    def test_a_subscription_that_really_ended_can_be_bought_again(self):
        for state in ('canceled', 'incomplete_expired'):
            CompanyModulePurchase.objects.all().delete()
            self.opened.reset_mock()
            purchase = self.row(status='cancelled')
            self.stripe_says(at_stripe(state))
            response = self.checkout()
            self.assertEqual((response.status_code, response.data.get('url')), (200, 'https://checkout.example/1'), state)
            self.opened.assert_called_once()
            purchase.refresh_from_db()
            self.assertEqual(purchase.status, 'cancelled')            # left as it was

    def test_so_can_one_stripe_has_never_heard_of(self):
        self.row(status='expired')
        self.stripe_says(stripe.error.InvalidRequestError('No such subscription', 'id', code='resource_missing'))
        self.assertEqual(self.checkout().status_code, 200)
        self.opened.assert_called_once()

    # ---- cannot tell ----------------------------------------------------------------

    def test_nothing_is_sold_when_stripe_cannot_be_asked(self):
        purchase = self.row()
        self.stripe_says(stripe.error.APIConnectionError('network down'))
        response = self.checkout()
        self.assertEqual((response.status_code, response.data['error']), (503, 'stripe_unreachable'))
        self.assertIn('try again in a few minutes', response.data['message'])
        self.opened.assert_not_called()
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, 'active')                  # untouched

    def test_nor_when_stripe_refuses_the_question_for_another_reason(self):
        self.row()
        self.stripe_says(stripe.error.InvalidRequestError('Bad request', 'id', code='parameter_invalid'))
        self.assertGreaterEqual(self.checkout().status_code, 500)
        self.opened.assert_not_called()

    # ---- nothing to ask ---------------------------------------------------------------

    def test_stripe_is_not_asked_when_there_is_no_subscription_to_ask_about(self):
        asked = self.stripe_says(at_stripe('active'))
        self.assertEqual(self.checkout().status_code, 200)              # never bought
        CompanyModulePurchase.objects.create(company=self.company, module_name='hr_agent', status='expired',
                                             expires_at=timezone.now() - timedelta(days=3))   # an old one-off purchase
        self.assertEqual(self.checkout().status_code, 200)
        asked.assert_not_called()
        self.assertEqual(self.opened.call_count, 2)

    def test_an_agent_already_open_is_refused_without_asking(self):
        self.row(current_period_end=timezone.now() + timedelta(days=5))
        asked = self.stripe_says(at_stripe('active'))
        response = self.checkout()
        self.assertEqual(response.status_code, 400)
        self.assertIn('already active', response.data['message'])
        asked.assert_not_called()
        self.opened.assert_not_called()

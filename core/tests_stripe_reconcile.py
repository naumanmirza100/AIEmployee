"""The net under the Stripe webhooks.

Stripe tells us about renewals, cancellations and failed payments by webhook.
If those never arrive (production ran with no webhook secret), a subscription's
stored period simply runs out and a paying customer is locked out. The
reconcile job re-reads Stripe and puts the row right. Stripe itself is faked
here; no network, no real keys.
"""
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from api.views import module_purchase
from core.models import Company, CompanyModulePurchase
from core.tasks import reconcile_stripe_subscriptions as reconcile_task


def at_stripe(sub_id, status='active', period_end=None, cancel_at_period_end=False):
    """What Stripe would answer for one subscription."""
    end = period_end or timezone.now() + timedelta(days=30)
    return {'id': sub_id, 'status': status, 'cancel_at_period_end': cancel_at_period_end,
            'current_period_start': int((end - timedelta(days=30)).timestamp()),
            'current_period_end': int(end.timestamp())}


class StripeReconcileTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        self.now = timezone.now().replace(microsecond=0)        # Stripe's times are whole seconds
        key = mock.patch.object(module_purchase.stripe, 'api_key', 'sk_test_' + 'x' * 24)   # made up
        key.start()
        self.addCleanup(key.stop)

    def bought(self, module, sub_id, period_end, **fields):
        return CompanyModulePurchase.objects.create(
            company=self.company, module_name=module, status=fields.pop('status', 'active'),
            stripe_subscription_id=sub_id, current_period_end=period_end, billing_interval='month', **fields)

    def stripe_says(self, *subscriptions):
        """Fake Stripe: returns the given subscriptions by id, raises for any other."""
        known = {s['id']: s for s in subscriptions}

        def retrieve(sub_id):
            if sub_id not in known:
                raise RuntimeError(f'No such subscription: {sub_id}')
            return known[sub_id]
        patcher = mock.patch.object(module_purchase.stripe.Subscription, 'retrieve', side_effect=retrieve)
        fake = patcher.start()
        self.addCleanup(patcher.stop)
        return fake

    def test_a_renewal_nobody_told_us_about_keeps_the_customer_in(self):
        purchase = self.bought('hr_agent', 'sub_renewed', self.now - timedelta(hours=3))
        self.assertFalse(purchase.is_active())                      # locked out today
        next_month = self.now + timedelta(days=30)
        self.stripe_says(at_stripe('sub_renewed', period_end=next_month))

        stats = module_purchase.reconcile_stripe_subscriptions()

        purchase.refresh_from_db()
        self.assertTrue(purchase.is_active())
        self.assertEqual(int(purchase.current_period_end.timestamp()), int(next_month.timestamp()))
        self.assertEqual((stats['checked'], stats['corrected'], stats['missed'], stats['failed']), (1, 1, 1, 0))

    def test_a_cancellation_nobody_told_us_about_ends_access(self):
        purchase = self.bought('hr_agent', 'sub_gone', self.now - timedelta(hours=3))
        self.stripe_says(at_stripe('sub_gone', status='canceled', period_end=self.now - timedelta(hours=3)))

        module_purchase.reconcile_stripe_subscriptions()

        purchase.refresh_from_db()
        self.assertEqual(purchase.status, 'cancelled')
        self.assertFalse(purchase.is_active())

    def test_retries_running_out_ends_access_and_tells_the_company_why(self):
        from core.models import CompanyUser
        from project_manager_agent.models import PMNotification
        owner = CompanyUser.objects.create(company=self.company, email='owner@test.local', full_name='Olu Owner',
                                           role='admin', password_hash='x', is_active=True)
        purchase = self.bought('hr_agent', 'sub_unpaid', self.now - timedelta(days=2), status='past_due')
        self.stripe_says(at_stripe('sub_unpaid', status='canceled', period_end=self.now - timedelta(days=2)))

        module_purchase.reconcile_stripe_subscriptions()

        purchase.refresh_from_db()
        self.assertEqual((purchase.status, purchase.cancelled_reason), ('cancelled', 'payment_failed'))
        self.assertTrue(PMNotification.objects.filter(company_user=owner, title__startswith='Access ended').exists())

    def test_a_payment_that_went_through_on_retry_restores_access(self):
        purchase = self.bought('hr_agent', 'sub_retried', self.now + timedelta(days=20), status='past_due')
        self.stripe_says(at_stripe('sub_retried', period_end=self.now + timedelta(days=20)))

        module_purchase.reconcile_stripe_subscriptions()

        purchase.refresh_from_db()
        self.assertEqual(purchase.status, 'active')

    def test_the_frequent_run_leaves_subscriptions_in_good_standing_alone(self):
        self.bought('hr_agent', 'sub_fine', self.now + timedelta(days=12))
        stripe = self.stripe_says(at_stripe('sub_fine', period_end=self.now + timedelta(days=12)))

        stats = module_purchase.reconcile_stripe_subscriptions(only_due=True)

        stripe.assert_not_called()                                   # no Stripe traffic when all is well
        self.assertEqual(stats['checked'], 0)

    def test_the_nightly_run_checks_every_live_subscription(self):
        purchase = self.bought('hr_agent', 'sub_leaving', self.now + timedelta(days=12))
        self.stripe_says(at_stripe('sub_leaving', period_end=self.now + timedelta(days=12),
                                   cancel_at_period_end=True))

        stats = module_purchase.reconcile_stripe_subscriptions(only_due=False)

        purchase.refresh_from_db()
        self.assertTrue(purchase.cancel_at_period_end)               # the customer cancelled; we now know
        self.assertEqual((stats['checked'], stats['corrected']), (1, 1))

    def test_free_access_granted_by_an_admin_is_never_touched(self):
        gift = self.bought('hr_agent', 'sub_old', self.now - timedelta(days=5), is_complimentary=True)
        stripe = self.stripe_says(at_stripe('sub_old', status='canceled'))

        module_purchase.reconcile_stripe_subscriptions(only_due=False)

        gift.refresh_from_db()
        stripe.assert_not_called()
        self.assertEqual(gift.status, 'active')

    def test_one_unreadable_subscription_does_not_stop_the_rest(self):
        self.bought('hr_agent', 'sub_missing_at_stripe', self.now - timedelta(hours=3))
        good = self.bought('frontline_agent', 'sub_ok', self.now - timedelta(hours=3))
        self.stripe_says(at_stripe('sub_ok'))

        stats = module_purchase.reconcile_stripe_subscriptions()

        good.refresh_from_db()
        self.assertTrue(good.is_active())
        self.assertEqual((stats['checked'], stats['corrected'], stats['failed']), (2, 1, 1))

    def test_nothing_happens_when_stripe_is_not_set_up(self):
        self.bought('hr_agent', 'sub_x', self.now - timedelta(hours=3))
        stripe = self.stripe_says(at_stripe('sub_x'))
        with mock.patch.object(module_purchase.stripe, 'api_key', 'sk_test_placeholder'):
            stats = module_purchase.reconcile_stripe_subscriptions()
        stripe.assert_not_called()
        self.assertEqual(stats['checked'], 0)

    def test_a_renewal_caught_within_minutes_is_not_called_a_missed_webhook(self):
        self.bought('hr_agent', 'sub_just_now', self.now - timedelta(minutes=2))
        self.stripe_says(at_stripe('sub_just_now'))

        stats = module_purchase.reconcile_stripe_subscriptions()

        self.assertEqual((stats['corrected'], stats['missed']), (1, 0))

    def test_the_job_tells_the_operators_when_webhooks_are_not_arriving(self):
        self.bought('hr_agent', 'sub_renewed', self.now - timedelta(hours=3))
        self.stripe_says(at_stripe('sub_renewed'))
        with mock.patch('logging.Logger.error') as said:
            result = reconcile_task()
        self.assertIn('corrected 1', result)
        messages = [call.args[0] for call in said.call_args_list]
        self.assertTrue(any('Stripe events are probably not reaching this server' in m for m in messages), messages)

    def test_the_job_says_nothing_when_there_was_nothing_to_correct(self):
        self.bought('hr_agent', 'sub_fine', self.now + timedelta(days=12))
        self.stripe_says(at_stripe('sub_fine', period_end=self.now + timedelta(days=12)))
        with mock.patch('logging.Logger.error') as said:
            reconcile_task(full=True)
        said.assert_not_called()

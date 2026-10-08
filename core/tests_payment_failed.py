"""A failed card pauses the agent at once. Say so, to everyone, every time.

The bell alert said the payment would be retried and to update the card "to
avoid losing access", when access had already gone. It was sent only when the
failed invoice's own event arrived first: if the subscription's event or the
scheduled re-check paused the agent, nobody was told at all.
"""
from datetime import timedelta
from unittest import mock

from django.test import RequestFactory, TestCase
from django.utils import timezone

from api.middleware.module_access import ModuleAccessMiddleware
from api.views import module_purchase
from core.models import Company, CompanyModulePurchase, CompanyUser, CompanyUserToken
from project_manager_agent.models import PMNotification


def subscription(status, sub_id='sub_1'):
    end = timezone.now() + timedelta(days=20)
    return {'id': sub_id, 'status': status, 'cancel_at_period_end': False,
            'current_period_start': int((end - timedelta(days=30)).timestamp()),
            'current_period_end': int(end.timestamp())}


INVOICE = {'subscription': 'sub_1', 'hosted_invoice_url': 'https://invoice.example/1'}


class PaymentFailedTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        self.dana = self.login('dana@test.local')
        self.eli = self.login('eli@test.local')
        self.login('gone@test.local', is_active=False)
        self.purchase = CompanyModulePurchase.objects.create(
            company=self.company, module_name='hr_agent', status='active', stripe_subscription_id='sub_1',
            current_period_end=timezone.now() + timedelta(days=20), billing_interval='month')

    def login(self, email, **fields):
        return CompanyUser.objects.create(company=self.company, email=email, full_name=email.split('@')[0],
                                          role='admin', password_hash='x', **{'is_active': True, **fields})

    def status(self):
        self.purchase.refresh_from_db()
        return self.purchase.status

    def alerts(self):
        return list(PMNotification.objects.order_by('id'))

    # ---- the alert ------------------------------------------------------------

    def test_the_alert_says_the_agent_is_paused_and_where_to_fix_it(self):
        module_purchase._handle_invoice_payment_failed(INVOICE)
        self.assertEqual(self.status(), 'past_due')
        self.assertFalse(self.purchase.is_active())
        alerts = self.alerts()
        self.assertEqual({a.company_user_id for a in alerts}, {self.dana.id, self.eli.id})   # not the switched-off login
        for alert in alerts:
            self.assertIn('is paused', alert.title)
            self.assertIn('paused for everyone in your company', alert.message)
            self.assertIn('try the card again', alert.message)
            self.assertNotIn('avoid losing access', alert.message)
            self.assertEqual(alert.severity, 'critical')
            self.assertEqual(alert.data['link'], '/company/dashboard/billing')
            self.assertEqual(alert.data['hosted_invoice_url'], 'https://invoice.example/1')

    def test_it_is_sent_when_the_subscription_event_gets_there_first(self):
        module_purchase._handle_subscription_updated(subscription('past_due'))
        self.assertEqual(self.status(), 'past_due')
        self.assertEqual(len(self.alerts()), 2)
        self.assertIn('paused for everyone', self.alerts()[0].message)

    def test_and_when_the_scheduled_check_does(self):
        with mock.patch.object(module_purchase.stripe, 'api_key', 'sk_test_' + 'x' * 24), \
                mock.patch.object(module_purchase.stripe.Subscription, 'retrieve',
                                  return_value=subscription('past_due')):
            CompanyModulePurchase.objects.filter(pk=self.purchase.pk).update(
                current_period_end=timezone.now() - timedelta(hours=1))
            module_purchase.reconcile_stripe_subscriptions()
        self.assertEqual(self.status(), 'past_due')
        self.assertEqual(len(self.alerts()), 2)

    def test_one_failed_charge_is_one_alert_whichever_order_the_events_come_in(self):
        for first, second in ((0, 1), (1, 0)):
            PMNotification.objects.all().delete()
            CompanyModulePurchase.objects.filter(pk=self.purchase.pk).update(status='active')
            events = [lambda: module_purchase._handle_invoice_payment_failed(INVOICE),
                      lambda: module_purchase._handle_subscription_updated(subscription('past_due'))]
            events[first]()
            events[second]()
            events[second]()
            self.assertEqual(len(self.alerts()), 2, (first, second))       # one each for two logins

    def test_nothing_is_sent_for_a_subscription_that_is_fine(self):
        module_purchase._handle_subscription_updated(subscription('active'))
        self.assertEqual((self.status(), self.alerts()), ('active', []))

    def test_nor_for_one_the_customer_cancelled(self):
        module_purchase._handle_subscription_updated(subscription('canceled'))
        self.assertEqual((self.status(), self.alerts()), ('cancelled', []))

    def test_a_payment_that_never_completed_is_not_promised_a_retry(self):
        module_purchase._handle_subscription_updated(subscription('paused'))
        self.assertEqual(self.status(), 'past_due')
        message = self.alerts()[0].message
        self.assertIn('has not gone through', message)
        self.assertNotIn('try the card again', message)

    def test_a_free_grant_is_left_alone(self):
        CompanyModulePurchase.objects.filter(pk=self.purchase.pk).update(is_complimentary=True)
        module_purchase._handle_subscription_updated(subscription('past_due'))
        self.assertEqual((self.status(), self.alerts()), ('active', []))

    # ---- what the screens and the API are told -----------------------------------

    def refusal(self, path='/api/hr/employees'):
        token, _ = CompanyUserToken.objects.get_or_create(company_user=self.dana)
        request = RequestFactory().get(path, HTTP_AUTHORIZATION=f'Token {token.key}')
        response = ModuleAccessMiddleware(lambda r: mock.Mock(status_code=200, content=b'{}'))(request)
        if response.status_code == 200:
            return None
        import json
        return json.loads(response.content)

    def test_the_api_says_payment_failed_not_subscribe(self):
        self.assertIsNone(self.refusal())
        CompanyModulePurchase.objects.filter(pk=self.purchase.pk).update(status='past_due')
        body = self.refusal()
        self.assertEqual((body['error'], body['reason']), ('subscription_required', 'payment_failed'))
        self.assertIn('Update your card on the Billing page', body['message'])
        self.assertNotIn('subscribe', body['message'].lower())

    def test_and_keeps_its_old_answer_for_the_rest(self):
        CompanyModulePurchase.objects.filter(pk=self.purchase.pk).update(status='cancelled')
        self.assertEqual(self.refusal()['reason'], 'lapsed')
        self.assertIn('subscribe or renew', self.refusal()['message'])
        self.assertEqual(self.refusal('/api/marketing/campaigns')['reason'], 'not_bought')

    def test_the_lock_screen_is_told_the_status(self):
        from rest_framework.test import APIRequestFactory, force_authenticate
        CompanyModulePurchase.objects.filter(pk=self.purchase.pk).update(status='past_due')
        request = APIRequestFactory().get('/')
        force_authenticate(request, user=self.dana)
        response = module_purchase.check_module_access(request, module_name='hr_agent')
        self.assertEqual((response.data['has_access'], response.data['purchase_status']), (False, 'past_due'))
        never = module_purchase.check_module_access(request, module_name='marketing_agent')
        self.assertEqual((never.data['has_access'], never.data.get('purchase_status')), (False, None))

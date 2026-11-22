"""AI spend in dollars, and warnings before the money runs out (22 Nov 2026).

On 19 Nov the platform's OpenAI credit ran out and every agent stopped, with no warning: nothing showed spend in
money, and gpt-4.1-mini, the live model, was priced at a $0.50 default.
"""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from core import ai_spend
from core.ai_prices import cost_usd, price_of
from core.models import Company, SentAlert
from Frontline_agent.models import LLMUsage
from project_manager_agent.ai_agents.base_agent import _record_llm_usage


class Prices(SimpleTestCase):

    def test_a_dated_model_name_is_priced_as_its_model(self):
        self.assertEqual(price_of('gpt-4.1-mini-2025-04-14'), ((0.40, 1.60), True))
        self.assertEqual(price_of('gpt-4.1-2025-04-14'), ((2.00, 8.00), True))
        self.assertEqual(cost_usd('gpt-4.1-mini', 1_000_000, 1_000_000), Decimal('2.0'))

    def test_an_unknown_model_counts_at_the_dear_rate_and_settings_can_add_one(self):
        self.assertEqual(price_of('some-new-model'), ((2.00, 8.00), False))
        with override_settings(AI_PRICES_PER_MTOK={'some-new-model': (1.0, 2.0)}):
            self.assertEqual(price_of('some-new-model'), ((1.0, 2.0), True))


class SpendCase(TestCase):

    def setUp(self):
        self.acme = Company.objects.create(name='Acme', email='acme@test.local')
        self.zen = Company.objects.create(name='Zen', email='zen@test.local')

    def call(self, company, mode, tokens=1_000_000, model='gpt-4.1-mini', agent='hr_agent', provider='openai',
             days_ago=0):
        ctx = SimpleNamespace(mode=mode, provider=provider) if mode else None
        _record_llm_usage(company_id=company.id, agent_name='HRAgent', model=model, agent=agent, key_ctx=ctx,
                          usage_dict={'prompt_tokens': tokens, 'completion_tokens': 0}, duration_ms=5, success=True)
        row = LLMUsage.objects.latest('id')
        if days_ago:
            LLMUsage.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
        return row


class Spend(SpendCase):

    def test_each_call_says_whose_money_it_spent(self):
        row = self.call(self.acme, 'platform')
        self.assertEqual((row.key_mode, row.provider, row.estimated_cost_usd), ('platform', 'openai', Decimal('0.4')))

    def test_the_company_sees_its_month_split_by_whose_key(self):
        self.call(self.acme, 'platform')
        self.call(self.acme, 'byok', tokens=500_000)
        self.call(self.zen, 'platform')
        month = ai_spend.company_month(self.acme)
        self.assertEqual(month['hr_agent'], {'usd': 0.6, 'platform_usd': 0.4, 'own_key_usd': 0.2, 'calls': 2})

    def test_the_platform_report_counts_only_the_platforms_money(self):
        self.call(self.acme, 'platform')
        self.call(self.zen, 'managed', tokens=3_000_000)
        self.call(self.acme, 'byok')
        self.call(self.acme, '')                                    # before modes were recorded: the platform's
        report = ai_spend.platform_report(days=3)
        self.assertEqual(report['month_usd'], 2.0)
        self.assertEqual((report['own_keys_usd'], report['unsplit_usd']), (0.4, 0.4))
        self.assertEqual([c['company'] for c in report['by_company']], ['Zen', 'Acme'])
        self.assertEqual(len(report['daily']), 3)


@override_settings(AI_MONTHLY_BUDGET_USD=1.0, AI_DAILY_SPIKE_USD=1.0, GROQ_DAILY_REQUESTS=10, GROQ_DAILY_TOKENS=0,
                   ERROR_ALERT_EMAILS=['ops@example.com'])
class Alerts(SpendCase):

    def test_the_budget_warning_goes_once_per_threshold(self):
        self.call(self.acme, 'platform', tokens=2_100_000)         # $0.84 of $1: past 50% and 80%
        sent = ai_spend.check_and_alert()
        self.assertEqual(sent, ['ai-budget:%s:80' % timezone.localtime().strftime('%Y-%m')])
        self.assertIn('84', mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ['ops@example.com'])
        self.assertEqual(ai_spend.check_and_alert(), [])           # the next hour: nothing new
        self.assertEqual(SentAlert.objects.count(), 2)              # 50 and 80 both claimed

    def test_a_day_far_above_the_usual_is_told(self):
        for back in range(1, 8):
            self.call(self.acme, 'platform', tokens=100_000, days_ago=back)    # $0.04 a day
        self.call(self.zen, 'byok', tokens=9_000_000)                        # their own money: not counted
        self.call(self.acme, 'platform', tokens=3_000_000)                   # $1.20 today
        sent = ai_spend.check_and_alert()
        self.assertTrue(any(k.startswith('ai-spike:') for k in sent), sent)
        spike = [m for m in mail.outbox if 'today' in m.subject][0]
        self.assertIn('times the usual', spike.subject)

    def test_groqs_free_day_is_warned_at_80_percent(self):
        for _ in range(8):
            self.call(self.acme, 'platform', tokens=10, model='openai/gpt-oss-20b', provider='groq', agent='ai_sdr_agent')
        sent = ai_spend.check_and_alert()
        self.assertTrue(any(k.startswith('ai-groq-daily:') for k in sent), sent)
        self.assertIn('AI SDR stops', [m for m in mail.outbox if 'Groq' in m.subject][0].subject)

    @override_settings(ERROR_ALERT_EMAILS=[])
    def test_nobody_to_tell_spends_no_alert(self):
        User.objects.filter(is_superuser=True).delete()
        self.call(self.acme, 'platform', tokens=3_000_000)
        self.assertEqual(ai_spend.check_and_alert(), [])
        self.assertEqual(SentAlert.objects.count(), 0)


class Screens(SpendCase):

    def test_the_super_admin_page_gets_the_report(self):
        from rest_framework.test import APIClient
        self.call(self.acme, 'platform')
        admin = User.objects.create_superuser('boss', 'boss@example.com', 'x')
        client = APIClient()
        client.force_authenticate(admin)
        response = client.get('/api/admin/api-keys/spend')
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual(response.json()['data']['month_usd'], 0.4)

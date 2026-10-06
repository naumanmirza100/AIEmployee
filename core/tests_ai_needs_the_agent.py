"""AI works only for an agent the company has.

The key service never asked. A company with no allowance was handed a free one
on the spot, so posting a job from the dashboard ran Recruitment's AI for a
company that had never bought Recruitment, and background jobs kept using a
lapsed agent's AI on the platform's key.
"""
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from core.api_key_service import NoKeyAvailable, NotSubscribed, resolve_for_call
from core.models import Agent, AgentTokenQuota, Company, CompanyAPIKey, CompanyModulePurchase, CompanyUser, PlatformAPIKey


class AiNeedsTheAgentTests(TestCase):

    def setUp(self):
        for slug in ('recruitment_agent', 'marketing_agent', 'hr_agent'):
            Agent.objects.update_or_create(slug=slug, defaults={'name': slug, 'default_provider': 'openai'})
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        self.login = CompanyUser.objects.create(company=self.company, email='dana@test.local', full_name='Dana',
                                                role='admin', password_hash='x', is_active=True)
        key = PlatformAPIKey(provider='openai', status='active', encrypted_key='')
        key.set_plaintext_key('platform-key-0123456789')
        key.save()

    def buy(self, agent, **fields):
        fields = {'status': 'active', 'is_complimentary': True, **fields}
        purchase, _ = CompanyModulePurchase.objects.update_or_create(
            company=self.company, module_name=agent, defaults=fields)
        return purchase

    def refused(self, agent='recruitment_agent'):
        try:
            resolve_for_call(self.company, agent)
        except NotSubscribed:
            return True
        return False

    # ---- the key service ------------------------------------------------------

    def test_no_key_for_an_agent_the_company_never_bought(self):
        self.assertTrue(self.refused())
        # ...and it is not handed a free allowance on the way.
        self.assertFalse(AgentTokenQuota.objects.filter(company=self.company).exists())

    def test_a_key_once_it_has_the_agent(self):
        self.buy('recruitment_agent')
        self.assertEqual(resolve_for_call(self.company, 'recruitment_agent').mode, 'platform')

    def test_having_one_agent_does_not_switch_on_another(self):
        self.buy('hr_agent')
        self.assertFalse(self.refused('hr_agent'))
        self.assertTrue(self.refused('recruitment_agent'))

    def test_none_once_it_lapses(self):
        purchase = self.buy('recruitment_agent')
        for name, fields in (
            ('cancelled', {'status': 'cancelled'}),
            ('payment failed', {'status': 'past_due'}),
            ('ran out', {'status': 'active', 'expires_at': timezone.now() - timedelta(days=1)}),
        ):
            CompanyModulePurchase.objects.filter(pk=purchase.pk).update(
                status='active', expires_at=None)
            self.assertFalse(self.refused(), name)
            CompanyModulePurchase.objects.filter(pk=purchase.pk).update(**fields)
            self.assertTrue(self.refused(), name)

    def test_its_own_key_does_not_get_round_it(self):
        self.buy('recruitment_agent')
        AgentTokenQuota.objects.filter(company=self.company).update(preferred_pool='byok')
        own = CompanyAPIKey(company=self.company, agent_name='recruitment_agent', mode='byok',
                            provider='groq', status='active', encrypted_key='')
        own.set_plaintext_key('test-key-0123456789')
        own.save()
        self.assertEqual(resolve_for_call(self.company, 'recruitment_agent').mode, 'byok')
        CompanyModulePurchase.objects.filter(company=self.company).update(status='cancelled')
        self.assertTrue(self.refused())

    def test_the_screen_is_told_in_plain_words(self):
        from core.drf_exceptions import key_service_exception_handler
        response = key_service_exception_handler(NotSubscribed(), {})
        self.assertEqual((response.status_code, response.data['code'], response.data['hard_block']),
                         (403, 'not_subscribed', True))
        self.assertIn('subscription for this agent is not active', response.data['message'])
        # A missing key is a different message: nothing to renew there.
        self.assertNotEqual(response.data['message'], NoKeyAvailable.user_message)

    # ---- posting a job from the dashboard ---------------------------------------

    def post_job(self):
        from api.views.company_jobs import create_company_job
        request = APIRequestFactory().post('/', {
            'title': 'Welder', 'description': 'Welds things. Five years of MIG and TIG.',
            'location': 'Leeds', 'type': 'Full-time'}, format='json')
        force_authenticate(request, user=self.login)
        response = create_company_job(request)
        response.render()
        return response

    def edit_job(self, job_id):
        from api.views.company_jobs import update_company_job
        request = APIRequestFactory().put('/', {'description': 'Welds other things too. Seven years of MIG and TIG.'}, format='json')
        force_authenticate(request, user=self.login)
        response = update_company_job(request, id=job_id)
        response.render()
        return response

    def test_a_job_is_posted_without_keywords_when_the_company_has_no_recruitment(self):
        from recruitment_agent.models import JobDescription
        with mock.patch('api.views.company_jobs._make_agents') as make:
            response = self.post_job()
            self.assertEqual(response.status_code, 201, response.data)
            job = JobDescription.objects.get(company=self.company)
            edited = self.edit_job(job.id)
            self.assertEqual(edited.status_code, 200, edited.data)
        make.assert_not_called()
        job.refresh_from_db()
        self.assertFalse(job.keywords_json)

    def test_and_with_them_when_it_has(self):
        from recruitment_agent.models import JobDescription
        self.buy('recruitment_agent')
        parser = mock.Mock()
        parser.parse_text.return_value = {'keywords': ['MIG', 'TIG']}
        with mock.patch('api.views.company_jobs._make_agents',
                        return_value={'job_desc_agent': parser, 'log_service': mock.Mock()}) as make:
            self.assertEqual(self.post_job().status_code, 201)
            job = JobDescription.objects.get(company=self.company)
            self.assertIn('TIG', job.keywords_json)
            edited = self.edit_job(job.id)
            self.assertEqual(edited.status_code, 200, edited.data)
        self.assertEqual(make.call_count, 2)

    # ---- a reply to a marketing email -------------------------------------------

    def test_a_reply_is_still_sorted_by_fixed_rules_and_says_why(self):
        from marketing_agent.utils.reply_analyzer import ReplyAnalyzer
        result = ReplyAnalyzer().analyze_reply(
            reply_subject='Re: hello', campaign_name='Spring', company_id=self.company.id,
            reply_content='We looked at the deck with the team on Tuesday and will come back to you after the board meets.')
        self.assertTrue(result['ai_fallback'])
        self.assertIn('Marketing agent is not active', result['ai_fallback_reason'])
        self.assertIn('interest_level', result)

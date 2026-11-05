"""AI SDR → Tests, the checks of a company's live AI SDR. Here no check reaches an AI, a mail server, a website or
a CRM: those calls are replaced, and what is tested is what each check concludes and what it must never do (save a
lead, email anyone but the typed address, look at another company's campaign)."""
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent import live_checks
from ai_sdr_agent.models import SDRCampaign, SDRIcpProfile, SDRJobLock, SDRLead
from ai_sdr_agent.tests import SDRBase
from api.views import sdr_checks as views
from core.do_not_email import block
from core.models import Company, CompanyUser

SCORED = {'score': 71, 'temperature': 'warm', 'qualification_reasoning': 'Good fit.', 'score_breakdown': {}}


class LiveChecksBase(SDRBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.rf = APIRequestFactory()
        resolve = mock.patch('ai_sdr_agent.agents.sdr_key_resolver.resolve_sdr_groq_client',
                             return_value=(mock.MagicMock(), None))
        self.resolve = resolve.start()
        self.addCleanup(resolve.stop)

    def call(self, view, method='get', data=None, user=None, **kwargs):
        request = getattr(self.rf, method)('/', data or {}, format='json')
        force_authenticate(request, user=user or self.cu)
        return view(request, **kwargs)

    def run_check(self, key, **data):
        return self.call(views.live_run, 'post', data, key=key)


class AccessTests(LiveChecksBase):
    def test_a_salesperson_may_not_look_or_run(self):
        seller = CompanyUser.objects.create(company=self.company, email='s@test.local', full_name='S',
                                            role='company_user', password_hash='x', is_active=True)
        self.assertEqual(self.call(views.live_catalog, user=seller).status_code, 403)
        self.assertEqual(self.call(views.live_run, 'post', user=seller, key='ai_key').status_code, 403)

    def test_the_catalog_offers_only_this_companys_campaigns_with_a_mailbox(self):
        SDRCampaign.objects.create(company_user=self.cu, name='No mailbox', status='active')
        other = Company.objects.create(name='Other', email='o@test.local')
        boss = CompanyUser.objects.create(company=other, email='b@o.local', full_name='B', role='owner',
                                          password_hash='x', is_active=True)
        SDRCampaign.objects.create(company_user=boss, name='Theirs', smtp_host='h', smtp_username='u')
        data = self.call(views.live_catalog).data['data']
        self.assertEqual([c['name'] for c in data['campaigns']], ['C1'])
        self.assertEqual(len(data['health']), len(live_checks.HEALTH))
        self.assertEqual(data['email'], 'cu@test.local')

    def test_an_unknown_check_is_refused(self):
        self.assertEqual(self.run_check('../x').status_code, 404)

    def test_a_live_test_pressed_twice_runs_once(self):
        with mock.patch('ai_sdr_agent.agents.lead_qualification_agent.LeadQualificationAgent._ai_qualify',
                        return_value=SCORED) as ai:
            self.assertEqual(self.run_check('live_qualification').status_code, 200)
            self.assertEqual(self.run_check('live_qualification').status_code, 429)
        ai.assert_called_once()

    def test_a_check_that_breaks_is_a_failed_result_not_an_error_page(self):
        with mock.patch.object(live_checks, 'check_scheduler', side_effect=RuntimeError('boom')), \
                mock.patch.dict(live_checks.CHECKS, {'scheduler': {**live_checks.CHECKS['scheduler'],
                                                                   'fn': live_checks.check_scheduler}}):
            result = self.run_check('scheduler').data['data']
        self.assertEqual(result['status'], 'failed')
        self.assertIn('RuntimeError: boom', result['summary'])


class LiveQualificationTests(LiveChecksBase):
    def test_the_ai_scores_a_lead_that_is_never_saved(self):
        SDRIcpProfile.objects.create(company_user=self.cu, industries=['Dentistry'], job_titles=['Practice Owner'],
                                     is_active=True)
        with mock.patch('ai_sdr_agent.agents.lead_qualification_agent.LeadQualificationAgent._ai_qualify',
                        return_value=SCORED) as ai:
            result = self.run_check('live_qualification').data['data']
        self.assertEqual((result['status'], result['summary']), ('passed', 'The AI scored a sample lead 71 (warm).'))
        lead, icp = ai.call_args.args
        self.assertEqual((lead['company_industry'], lead['job_title']), ('Dentistry', 'Practice Owner'))
        self.assertEqual(SDRLead.all_objects.count(), 0)

    def test_a_rejected_key_fails_instead_of_falling_back_to_rules(self):
        refused = Exception('invalid api key')
        refused.status_code = 401
        with mock.patch('ai_sdr_agent.agents.lead_qualification_agent.LeadQualificationAgent._ai_qualify',
                        side_effect=refused):
            result = self.run_check('live_qualification').data['data']
        self.assertEqual((result['status'], result['summary']), ('failed', 'The AI key was rejected by the provider.'))

    def test_no_usable_key_says_why(self):
        from core.api_key_service import NoKeyAvailable
        self.resolve.side_effect = NoKeyAvailable('no key assigned')
        result = self.run_check('live_qualification').data['data']
        self.assertEqual(result['status'], 'failed')
        self.assertIn('No AI key can be used', result['summary'])


class LiveSendTests(LiveChecksBase):
    def send(self, **data):
        with mock.patch('ai_sdr_agent.agents.outreach_agent.OutreachAgent._send_via_smtp') as smtp:
            result = self.run_check('live_send', **data).data['data']
        return result, smtp

    def test_one_email_goes_to_the_typed_address_and_nowhere_else(self):
        result, smtp = self.send(email='qa@acme.test', campaign_id=self.campaign.id)
        self.assertEqual(result['status'], 'passed')
        smtp.assert_called_once()
        self.assertEqual(smtp.call_args.kwargs.get('to_email') or smtp.call_args.args[7], 'qa@acme.test')

    def test_without_an_address_nothing_is_sent(self):
        result, smtp = self.send(email='', campaign_id=self.campaign.id)
        self.assertEqual(result['status'], 'failed')
        smtp.assert_not_called()

    def test_another_companys_campaign_cannot_be_used(self):
        other = Company.objects.create(name='Other', email='o@test.local')
        boss = CompanyUser.objects.create(company=other, email='b@o.local', full_name='B', role='owner',
                                          password_hash='x', is_active=True)
        theirs = SDRCampaign.objects.create(company_user=boss, name='Theirs', smtp_host='h', smtp_username='u',
                                            smtp_password='p')
        result, smtp = self.send(email='qa@acme.test', campaign_id=theirs.id)
        self.assertEqual(result['status'], 'failed')
        smtp.assert_not_called()

    def test_the_do_not_email_list_still_applies(self):
        block(self.company.id, 'qa@acme.test')
        result, smtp = self.send(email='qa@acme.test', campaign_id=self.campaign.id)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('do-not-email', result['summary'])
        smtp.assert_not_called()


class HealthTests(LiveChecksBase):
    def test_waiting_leads_without_an_icp_fail(self):
        self.make_lead(qualification_status='pending', qualification_queued_at=timezone.now())
        result = self.run_check('qualification').data['data']
        self.assertEqual(result['status'], 'failed')
        self.assertIn('no active ICP', result['summary'])

    def test_leads_that_failed_to_be_scored_today_fail_with_the_reason(self):
        SDRIcpProfile.objects.create(company_user=self.cu, is_active=True)
        self.make_lead(qualification_status='failed', qualification_attempts=3,
                       qualification_error='AI key was rejected')
        result = self.run_check('qualification').data['data']
        self.assertEqual(result['status'], 'failed')
        self.assertIn('Latest reason: AI key was rejected', result['details'])

    def test_another_companys_leads_are_not_counted(self):
        other = Company.objects.create(name='Other', email='o@test.local')
        boss = CompanyUser.objects.create(company=other, email='b@o.local', full_name='B', role='owner',
                                          password_hash='x', is_active=True)
        SDRLead.objects.create(company_user=boss, qualification_status='failed', qualification_attempts=3)
        SDRIcpProfile.objects.create(company_user=self.cu, is_active=True)
        self.assertEqual(self.run_check('qualification').data['data']['status'], 'passed')

    def test_the_scheduler_is_late_until_its_jobs_have_run(self):
        self.assertEqual(self.run_check('scheduler').data['data']['status'], 'failed')
        for name, _label, _every in live_checks.SCHEDULER_JOBS:
            SDRJobLock.objects.create(name=name, locked_until=timezone.now(), last_run_at=timezone.now())
        self.assertEqual(self.run_check('scheduler').data['data']['status'], 'passed')
        SDRJobLock.objects.filter(name='check_inbox').update(last_run_at=timezone.now() - timedelta(hours=2))
        result = self.run_check('scheduler').data['data']
        self.assertEqual(result['status'], 'failed')
        self.assertIn('Reading replies', result['summary'])

    def test_a_mailbox_that_cannot_log_in_fails_and_nothing_is_sent(self):
        with mock.patch('ai_sdr_agent.agents.outreach_agent.try_mailbox_logins',
                        return_value='Authentication failed') as logins, \
                mock.patch('ai_sdr_agent.agents.outreach_agent.OutreachAgent._send_via_smtp') as smtp:
            result = self.run_check('mailboxes').data['data']
        self.assertEqual(result['status'], 'failed')
        self.assertIn('C1', result['details'][0])
        logins.assert_called_once()
        smtp.assert_not_called()

    def test_no_crm_is_skipped(self):
        self.assertEqual(self.run_check('crm').data['data']['status'], 'skipped')

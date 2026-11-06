"""Regression tests for the lead research / enrichment work owned in
`feature/lead-gen` (status doc §4.1 R-items + the auto-enrichment and
export-all features).

NOTE: booking→CRM (S1), meeting→converted (S2) and re-score-after-enrichment
(§5) belong to the other developer's area and are intentionally NOT changed or
tested here.
"""
import contextlib
import uuid
from datetime import timedelta
from unittest import mock

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import ai_sdr_agent as views
from ai_sdr_agent import tasks
from ai_sdr_agent.models import SDRIcpProfile, SDRLead, SDRMeeting
from ai_sdr_agent.tests import SDRBase


class AutoResearchLeavesQualificationToTheButtonTests(SDRBase):
    """Auto-researched (Apify) leads are not queued for qualification: that waits for the Qualify button."""

    @override_settings(APIFY_API_TOKEN='tok')
    def test_auto_researched_leads_are_not_queued_for_qualification(self):
        SDRIcpProfile.objects.create(company_user=self.cu, is_active=True, job_titles=['CEO'])
        fake_leads = [{
            'full_name': 'New Prospect', 'first_name': 'New', 'last_name': 'Prospect',
            'email': 'new.prospect@target.example', 'job_title': 'CEO',
            'company_name': 'Target Co',
        }]
        with mock.patch(
            'ai_sdr_agent.agents.lead_research_agent.LeadResearchAgent.search_leads',
            return_value=fake_leads,
        ):
            tasks.auto_research_leads_impl(leads_per_run=5)

        lead = SDRLead.objects.get(email='new.prospect@target.example')
        self.assertEqual(lead.qualification_status, 'none')
        self.assertIsNone(lead.qualification_queued_at)


class StatusFollowsTheScoreTests(SDRBase):
    """A cold lead scoring 11 showed as Qualified: scoring set every lead "qualified"."""

    def scored(self, temperature, status='new'):
        lead = self.make_lead(f'{temperature}-{status}@acme.com', status=status, temperature=temperature)
        lead.set_status_from_score()
        return lead.status

    def test_hot_and_warm_are_qualified_and_cold_is_not(self):
        self.assertEqual(self.scored('hot'), 'qualified')
        self.assertEqual(self.scored('warm'), 'qualified')
        self.assertEqual(self.scored('cold'), 'new')
        self.assertEqual(self.scored('cold', status='qualified'), 'new')   # re-scored after enrichment

    def test_later_stages_and_unsubscribes_are_kept(self):
        self.assertEqual(self.scored('cold', status='contacted'), 'contacted')
        self.assertEqual(self.scored('hot', status='disqualified'), 'disqualified')


class ResearchJobSourceTests(SDRBase):
    """Failed Apify searches were labelled ai_generated: the job only took its provider when a search succeeded."""

    def _start(self, count):
        from ai_sdr_agent.agents.lead_research_agent import LeadResearchAgent
        from ai_sdr_agent.models import SDRLeadResearchJob
        SDRIcpProfile.objects.get_or_create(company_user=self.cu, is_active=True, defaults={'job_titles': ['CEO']})
        agent = LeadResearchAgent(apify_token='tok', apify_actor='code_crafter/leads-finder')
        request = APIRequestFactory().post('/x', {'source': 'apify', 'count': count}, format='json')
        force_authenticate(request, user=self.cu)
        with mock.patch.object(views, '_get_research_agent', return_value=agent), mock.patch('threading.Thread'):
            response = views.research_leads(request)
        return SDRLeadResearchJob.objects.get(pk=response.data['job_id'])

    def test_one_search_finds_at_most_1000_leads(self):
        # 1,500 was one click away (4 Nov 2026), then 200 was too few (6 Nov 2026); the dialog confirms above 200.
        self.assertEqual(self._start(1500).search_params['count'], 1000)
        self.assertEqual(self._start(1000).search_params['count'], 1000)
        self.assertEqual(self._start(50).search_params['count'], 50)

    def test_a_search_cut_short_by_a_restart_stops_saying_running(self):
        job = self._start(20)
        job.started_at = timezone.now() - views.RESEARCH_JOB_STALE_AFTER - timedelta(minutes=1)
        job.save(update_fields=['started_at'])
        request = APIRequestFactory().get('/x')
        force_authenticate(request, user=self.cu)
        data = views.research_job_status(request, job.pk).data['job']
        self.assertEqual((data['state'], data['done'], data['error_code']), ('failed', True, 'interrupted'))
        fresh = self._start(20)
        data = views.research_job_status(request, fresh.pk).data['job']
        self.assertEqual(data['state'], 'running')

    def test_a_failed_search_keeps_the_provider_it_asked(self):
        from ai_sdr_agent.agents.lead_research_agent import LeadResearchAgent
        from ai_sdr_agent.models import SDRLeadResearchJob
        SDRIcpProfile.objects.create(company_user=self.cu, is_active=True, job_titles=['CEO'])
        agent = LeadResearchAgent(apify_token='tok', apify_actor='code_crafter/leads-finder')
        request = APIRequestFactory().post('/x', {'source': 'apify', 'count': 5}, format='json')
        force_authenticate(request, user=self.cu)
        with mock.patch.object(views, '_get_research_agent', return_value=agent), \
                mock.patch('threading.Thread'):
            response = views.research_leads(request)
        job = SDRLeadResearchJob.objects.get(pk=response.data['job_id'])
        self.assertEqual(job.source, 'apify')


class EnrichmentReportsUpdatedFieldsTests(SDRBase):
    """The UI decides 'Enrichment Complete' vs 'No New Data' from the result's
    top-level `fields_updated`. Guard that the result exposes it alongside
    `changes` (it was only on the run history before, so the UI always saw
    none)."""

    def test_enrich_result_lists_fields_it_updated(self):
        from ai_sdr_agent.agents.enrichment_agent import EnrichmentAgent
        from ai_sdr_agent.agents.enrichment_contract import FieldProvenance

        lead = self.make_lead('nophone@acme.com')  # starts with no phone

        def fake_waterfall(contract, **kwargs):
            contract.fields['phone'] = FieldProvenance(
                field_name='phone', value='+1-555-0100', source='public_web')
            return contract, {'status': 'completed', 'providers_called': ['public_web']}

        agent = EnrichmentAgent(company=self.company, company_user=self.cu, apollo_api_key=None)
        with mock.patch.object(agent.waterfall, 'execute_waterfall', side_effect=fake_waterfall):
            res = agent.enrich_lead(lead, force=True)

        self.assertIn('fields_updated', res)
        self.assertIn('phone', res['fields_updated'])
        self.assertEqual(sorted(res['fields_updated']), sorted(res['changes'].keys()))
        lead.refresh_from_db()
        self.assertEqual(lead.phone, '+1-555-0100')


class AutoEnrichmentQueueTests(SDRBase):
    """New leads are auto-enriched in the background (enrichment_status queue),
    mirroring auto-qualification. Enrichment does NOT re-score the lead."""

    def test_enrich_queue_drains_pending_and_marks_done(self):
        from ai_sdr_agent.tasks import enrich_queue_impl
        lead = self.make_lead('toenrich@acme.com',
                              enrichment_status='pending', enrichment_queued_at=timezone.now(),
                              qualification_status='pending', qualification_queued_at=timezone.now())
        with mock.patch('ai_sdr_agent.agents.enrichment_agent.EnrichmentAgent') as EA:
            EA.return_value.enrich_lead.return_value = {'status': 'success', 'changes': {'phone': {}}}
            r = enrich_queue_impl()
        lead.refresh_from_db()
        self.assertEqual(lead.enrichment_status, 'done')
        self.assertGreaterEqual(r['enriched'], 1)
        # Enrichment must not touch qualification (that stays the other dev's call).
        self.assertEqual(lead.qualification_status, 'pending')

    def test_enrich_queue_marks_failed_and_increments_attempts(self):
        from ai_sdr_agent.tasks import enrich_queue_impl
        lead = self.make_lead('failenrich@acme.com', enrichment_status='pending',
                              enrichment_queued_at=timezone.now())
        with mock.patch('ai_sdr_agent.agents.enrichment_agent.EnrichmentAgent') as EA:
            EA.return_value.enrich_lead.return_value = {'status': 'failed'}
            enrich_queue_impl()
        lead.refresh_from_db()
        self.assertEqual(lead.enrichment_status, 'failed')
        self.assertEqual(lead.enrichment_attempts, 1)

    def test_done_leads_are_not_repicked(self):
        from ai_sdr_agent.tasks import enrich_queue_impl
        self.make_lead('alreadydone@acme.com', enrichment_status='done')
        with mock.patch('ai_sdr_agent.agents.enrichment_agent.EnrichmentAgent') as EA:
            r = enrich_queue_impl()
            EA.assert_not_called()
        self.assertEqual(r['processed'], 0)


class EnrichingStatCountTests(SDRBase):
    """The lead-list stats expose an `enriching` count (pending/processing in the
    background enrichment queue) so the screen can show an "Enriching N…" badge
    the same way it shows "Qualifying N…"."""

    def test_enriching_counts_only_pending_and_processing(self):
        self.make_lead('a@acme.com', enrichment_status='pending')
        self.make_lead('b@acme.com', enrichment_status='processing')
        self.make_lead('c@acme.com', enrichment_status='done')
        self.make_lead('d@acme.com', enrichment_status='none')
        stats = views._lead_stats(self.cu)
        self.assertEqual(stats['enriching'], 2)

    def test_enriching_is_company_scoped(self):
        from core.models import Company, CompanyUser
        other_co = Company.objects.create(name='Other', email='o2@test.local')
        other_cu = CompanyUser.objects.create(
            company=other_co, email='o2@cu.local', full_name='O',
            role='admin', password_hash='x', is_active=True)
        SDRLead.objects.create(company_user=other_cu, email='leak@other.com',
                               full_name='Leak', enrichment_status='pending')
        self.make_lead('mine@acme.com', enrichment_status='pending')
        self.assertEqual(views._lead_stats(self.cu)['enriching'], 1)


class LeadsExportAllTests(SDRBase):
    """Export ALL leads (every page) as CSV, respecting filters + company scope."""

    def _csv(self, params):
        req = APIRequestFactory().get('/x', params)
        force_authenticate(req, user=self.cu)
        resp = views.sdr_leads_export(req)
        self.assertIn('text/csv', resp['Content-Type'])
        self.assertIn('attachment', resp['Content-Disposition'])
        return b''.join(resp.streaming_content).decode('utf-8')

    def test_export_streams_all_and_respects_filters(self):
        self.make_lead('hot1@acme.com', temperature='hot', score=90, status='qualified')
        self.make_lead('cold1@acme.com', temperature='cold', score=10, status='qualified')
        body = self._csv({'temperature': 'hot'})
        self.assertIn('hot1@acme.com', body)
        self.assertNotIn('cold1@acme.com', body)   # filter applied, not just current page
        self.assertTrue(body.splitlines()[0].startswith('Name,Email,Phone'))

    def test_export_is_company_scoped(self):
        from core.models import Company, CompanyUser
        other_co = Company.objects.create(name='Other', email='o@test.local')
        other_cu = CompanyUser.objects.create(
            company=other_co, email='o@cu.local', full_name='O',
            role='admin', password_hash='x', is_active=True)
        SDRLead.objects.create(company_user=other_cu, email='leak@other.com', full_name='Leak')
        self.make_lead('mine@acme.com', temperature='hot', score=90)
        body = self._csv({})
        self.assertIn('mine@acme.com', body)
        self.assertNotIn('leak@other.com', body)    # no cross-company leak

    def test_a_cell_excel_would_run_stays_text_and_a_phone_stays_as_it_is(self):
        self.make_lead('x@acme.com', company_name='=HYPERLINK("http://bad.example","Click")',
                       job_title='-2+3+cmd|" /C calc"!A0', phone='+92 300 1234567')
        body = self._csv({})
        self.assertIn('"\'=HYPERLINK(""http://bad.example"",""Click"")"', body)
        self.assertIn('\'-2+3+cmd', body)
        self.assertIn(',+92 300 1234567,', body)


class BookingConfirmSyncsToCrmTests(SDRBase):
    """S1: the public booking-page confirm tells the CRM about the meeting."""

    def test_public_booking_confirm_notifies_crm(self):
        lead = self.make_lead('lead@acme.com')
        meeting = SDRMeeting.objects.create(
            company_user=self.cu, lead=lead, status='pending',
            duration_minutes=30, booking_token=uuid.uuid4(),
        )
        future = (timezone.now() + timedelta(days=3)).replace(
            hour=14, minute=0, second=0, microsecond=0)
        req = APIRequestFactory().post('/x', {'scheduled_at': future.isoformat()}, format='json')
        with mock.patch.object(views, '_in_work_hours', return_value=True), \
                mock.patch.object(views, '_host_booking', return_value=contextlib.nullcontext()), \
                mock.patch.object(views, '_give_call_a_link', return_value='https://meet.example/x'), \
                mock.patch('core.scheduling.sync.safe_sync_id'), \
                mock.patch('ai_sdr_agent.alerts.call_booked'), \
                mock.patch('crm_sync_agent.signals.log_meeting') as log_m:
            views.sdr_booking_confirm(req, token=str(meeting.booking_token))
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, 'scheduled')
        log_m.assert_called_once()
        self.assertEqual(log_m.call_args.args[0].id, meeting.id)


class ResearchAsyncTests(SDRBase):
    """R1: per-lead research endpoints run in the background on async=true
    (queued via the task) instead of blocking the request."""

    def test_single_research_async_queues_and_does_not_run_sync(self):
        lead = self.make_lead('r@acme.com')
        req = APIRequestFactory().post('/x', {'async': True, 'force': True}, format='json')
        force_authenticate(req, user=self.cu)
        fake_task = mock.MagicMock(id='task-123')
        with mock.patch('ai_sdr_agent.tasks.research_lead_task.delay', return_value=fake_task) as delay, \
                mock.patch('ai_sdr_agent.tasks.research_lead_impl') as impl:
            resp = views.research_lead_endpoint(req, lead_id=lead.id)
        self.assertEqual(resp.data['status'], 'queued')
        self.assertEqual(resp.data['task_id'], 'task-123')
        delay.assert_called_once()
        impl.assert_not_called()   # did NOT run inside the request

    def test_single_research_sync_still_works(self):
        lead = self.make_lead('r2@acme.com')
        req = APIRequestFactory().post('/x', {'force': True}, format='json')
        force_authenticate(req, user=self.cu)
        with mock.patch('ai_sdr_agent.tasks.research_lead_impl',
                        return_value={'status': 'success', 'profile': {'research_status': 'completed'}}) as impl:
            resp = views.research_lead_endpoint(req, lead_id=lead.id)
        self.assertEqual(resp.data['status'], 'success')
        impl.assert_called_once()

    def test_batch_research_async_queues(self):
        l1 = self.make_lead('b1@acme.com')
        l2 = self.make_lead('b2@acme.com')
        req = APIRequestFactory().post('/x', {'lead_ids': [l1.id, l2.id], 'async': True}, format='json')
        force_authenticate(req, user=self.cu)
        fake_task = mock.MagicMock(id='batch-1')
        with mock.patch('ai_sdr_agent.tasks.research_leads_batch_task.delay', return_value=fake_task) as delay, \
                mock.patch('ai_sdr_agent.tasks.research_leads_batch_impl') as impl:
            resp = views.research_leads_batch_endpoint(req)
        self.assertEqual(resp.data['status'], 'queued')
        self.assertEqual(resp.data['lead_count'], 2)
        delay.assert_called_once()
        impl.assert_not_called()


class ContactVerifierMxTests(SDRBase):
    """R3: a domain with no A/AAAA record (possibly MX-only) is RISKY, not
    INVALID — so a legitimate email on a receive-only domain isn't dropped."""

    def test_no_a_record_is_risky_not_invalid(self):
        import socket
        from ai_sdr_agent.agents.contact_verifier import verify_email
        from ai_sdr_agent.agents.enrichment_contract import VerificationStatus
        with mock.patch('socket.getaddrinfo', side_effect=socket.gaierror('no A record')):
            res = verify_email('ceo@mail-only.acme-corp.net', check_dns=True)
        self.assertEqual(res['status'], VerificationStatus.RISKY)
        self.assertTrue(res['is_valid'])   # not dropped


class BadKeyTerminalTests(SDRBase):
    """S3: a rejected AI key fails the lead (terminal), not endless 'pending';
    a quota error stays transient (retried)."""

    def _run_with(self, exc):
        SDRIcpProfile.objects.create(company_user=self.cu, is_active=True, job_titles=['CEO'])
        lead = self.make_lead('k@acme.com', qualification_status='pending',
                              qualification_queued_at=timezone.now())
        fake_agent = mock.MagicMock()
        fake_agent.qualify_lead.side_effect = exc
        with mock.patch('api.views.ai_sdr_agent._get_qualification_agent', return_value=fake_agent):
            tasks.qualify_queue_impl()
        lead.refresh_from_db()
        return lead

    def test_bad_api_key_fails_lead(self):
        from core.api_key_service import BadAPIKey
        lead = self._run_with(BadAPIKey())
        self.assertEqual(lead.qualification_status, 'failed')
        self.assertEqual(lead.qualification_attempts, 3)   # QUALIFY_MAX_ATTEMPTS

    def test_quota_error_stays_pending(self):
        from core.api_key_service import QuotaExhausted
        lead = self._run_with(QuotaExhausted())
        self.assertEqual(lead.qualification_status, 'pending')   # transient, retried


class BookingLinkExpiryTests(SDRBase):
    """S8: an unbooked booking link older than its TTL is rejected (410)."""

    def test_expired_link_is_rejected(self):
        lead = self.make_lead('exp@acme.com')
        meeting = SDRMeeting.objects.create(
            company_user=self.cu, lead=lead, status='pending',
            duration_minutes=30, booking_token=uuid.uuid4())
        # Age the link well past the TTL (created_at is auto, so update directly).
        SDRMeeting.objects.filter(pk=meeting.pk).update(
            created_at=timezone.now() - timedelta(days=60))
        req = APIRequestFactory().get('/x')
        resp = views.sdr_booking_info(req, token=str(meeting.booking_token))
        self.assertEqual(resp.status_code, 410)

    def test_fresh_link_still_works(self):
        lead = self.make_lead('fresh@acme.com')
        meeting = SDRMeeting.objects.create(
            company_user=self.cu, lead=lead, status='pending',
            duration_minutes=30, booking_token=uuid.uuid4())
        req = APIRequestFactory().get('/x')
        resp = views.sdr_booking_info(req, token=str(meeting.booking_token))
        self.assertEqual(resp.status_code, 200)


class ScoreReconcileTests(SDRBase):
    """C1: the AI score is always reconciled to the breakdown sum, so the number
    and the bars can't disagree (previously only when they differed by >10)."""

    def test_ai_score_reconciled_to_breakdown(self):
        import json
        from ai_sdr_agent.agents.lead_qualification_agent import LeadQualificationAgent
        icp = SDRIcpProfile.objects.create(
            company_user=self.cu, is_active=True, hot_threshold=75, warm_threshold=60)
        lead = self.make_lead('rec@acme.com')
        # AI returns score=85 but a breakdown that sums to 76 (gap 9 — within the
        # old 10 tolerance, so it used to stay 85).
        content = json.dumps({
            'score': 85, 'temperature': 'hot',
            'breakdown': {'company_quality': 30, 'contact_quality': 20, 'business_fit': 10,
                          'engagement_signals': 6, 'data_completeness': 10},
            'reasoning': 'x', 'key_strengths': [], 'concerns': [], 'outreach_strategy': 'y',
        })
        fake_resp = mock.MagicMock()
        fake_resp.choices = [mock.MagicMock(message=mock.MagicMock(content=content))]
        fake_resp.usage = mock.MagicMock(total_tokens=100)
        agent = LeadQualificationAgent(company=None)
        agent.groq_client = mock.MagicMock()
        agent.groq_client.chat.completions.create.return_value = fake_resp
        with mock.patch('ai_sdr_agent.agents.sdr_key_resolver.record_sdr_usage'):
            res = agent.qualify_lead(lead, icp)
        self.assertEqual(res['score'], 76)                       # reconciled, not 85
        self.assertEqual(sum(res['score_breakdown'].values()), 76)

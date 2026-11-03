"""Regression tests for the Phase-1 funnel hand-off fixes (remediation plan):

- P2-2 / I-3: a completed meeting converts its lead (funnel's terminal stage).
- P2-1 / I-2: the public booking-page confirm tells the CRM about the meeting.
- P2-3 / I-4: auto-researched (Apify) leads are queued for qualification.
- P2-16:      a successful enrichment re-queues the lead for (re-)scoring.
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


class MeetingCompletedConvertsLeadTests(SDRBase):
    def test_completing_a_meeting_sets_lead_converted(self):
        lead = self.make_lead('won@acme.com', status='meeting_scheduled')
        meeting = SDRMeeting.objects.create(
            company_user=self.cu, lead=lead, status='scheduled',
            scheduled_at=timezone.now() - timedelta(hours=1), duration_minutes=30,
        )
        rf = APIRequestFactory()
        req = rf.put('/x', {'status': 'completed'}, format='json')
        force_authenticate(req, user=self.cu)
        resp = views.sdr_meeting_detail(req, meeting_id=meeting.id)
        self.assertIn(resp.status_code, (200, 201))
        lead.refresh_from_db()
        self.assertEqual(lead.status, 'converted')

    def test_non_completed_transition_does_not_convert(self):
        lead = self.make_lead('pending@acme.com', status='meeting_scheduled')
        meeting = SDRMeeting.objects.create(
            company_user=self.cu, lead=lead, status='scheduled',
            scheduled_at=timezone.now() + timedelta(days=1), duration_minutes=30,
        )
        rf = APIRequestFactory()
        req = rf.put('/x', {'status': 'no_show'}, format='json')
        force_authenticate(req, user=self.cu)
        views.sdr_meeting_detail(req, meeting_id=meeting.id)
        lead.refresh_from_db()
        self.assertNotEqual(lead.status, 'converted')


class BookingConfirmSyncsToCrmTests(SDRBase):
    def test_public_booking_confirm_notifies_crm(self):
        lead = self.make_lead('lead@acme.com')
        meeting = SDRMeeting.objects.create(
            company_user=self.cu, lead=lead, status='pending',
            duration_minutes=30, booking_token=uuid.uuid4(),
        )
        future = (timezone.now() + timedelta(days=3)).replace(
            hour=14, minute=0, second=0, microsecond=0)
        rf = APIRequestFactory()
        req = rf.post('/x', {'scheduled_at': future.isoformat()}, format='json')

        # Isolate the slot/work-hour gating + side effects so the test asserts
        # only the new behavior: a successful confirm calls log_meeting.
        with mock.patch.object(views, '_in_work_hours', return_value=True), \
                mock.patch.object(views, '_host_booking', return_value=contextlib.nullcontext()), \
                mock.patch.object(views, '_give_call_a_link', return_value='https://meet.example/x'), \
                mock.patch('core.scheduling.sync.safe_sync_id'), \
                mock.patch('ai_sdr_agent.alerts.call_booked'), \
                mock.patch('crm_sync_agent.signals.log_meeting') as log_m:
            resp = views.sdr_booking_confirm(req, token=str(meeting.booking_token))

        meeting.refresh_from_db()
        self.assertEqual(meeting.status, 'scheduled')
        log_m.assert_called_once()
        # The meeting handed to the CRM is the one that was just booked.
        self.assertEqual(log_m.call_args.args[0].id, meeting.id)


class AutoResearchQueuesQualificationTests(SDRBase):
    @override_settings(APIFY_API_TOKEN='tok')
    def test_auto_researched_leads_are_queued_for_qualification(self):
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
        self.assertEqual(lead.qualification_status, 'pending')
        self.assertIsNotNone(lead.qualification_queued_at)


class EnrichRequeuesQualificationTests(SDRBase):
    def test_successful_enrichment_requeues_for_scoring(self):
        lead = self.make_lead('scored@acme.com', score=60, temperature='warm',
                              qualification_status='done')
        with mock.patch('ai_sdr_agent.agents.enrichment_agent.EnrichmentAgent') as EA:
            EA.return_value.enrich_lead.return_value = {'status': 'success'}
            tasks.enrich_lead_impl(lead.id)
        lead.refresh_from_db()
        self.assertEqual(lead.qualification_status, 'pending')
        self.assertIsNotNone(lead.qualification_queued_at)

    def test_failed_enrichment_does_not_requeue(self):
        lead = self.make_lead('stay@acme.com', score=60, temperature='warm',
                              qualification_status='done')
        with mock.patch('ai_sdr_agent.agents.enrichment_agent.EnrichmentAgent') as EA:
            EA.return_value.enrich_lead.return_value = {'status': 'failed'}
            tasks.enrich_lead_impl(lead.id)
        lead.refresh_from_db()
        self.assertEqual(lead.qualification_status, 'done')


class EnrichmentReportsUpdatedFieldsTests(SDRBase):
    """The UI decides 'Enrichment Complete' vs 'No New Data' from the result's
    top-level `fields_updated`. It was only ever on the run history, so the UI
    always saw none. Guard that the result exposes it alongside `changes`."""

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
        # The flat list must match the keys of `changes` (the UI's fallback).
        self.assertEqual(sorted(res['fields_updated']), sorted(res['changes'].keys()))
        lead.refresh_from_db()
        self.assertEqual(lead.phone, '+1-555-0100')


class AutoEnrichmentQueueTests(SDRBase):
    """New leads are auto-enriched in the background (enrichment_status queue),
    mirroring auto-qualification."""

    def test_enrich_queue_drains_pending_and_marks_done(self):
        from ai_sdr_agent.tasks import enrich_queue_impl
        # A brand-new lead as the create paths make it: queued for BOTH.
        lead = self.make_lead('toenrich@acme.com',
                              enrichment_status='pending', enrichment_queued_at=timezone.now(),
                              qualification_status='pending', qualification_queued_at=timezone.now())
        with mock.patch('ai_sdr_agent.agents.enrichment_agent.EnrichmentAgent') as EA:
            EA.return_value.enrich_lead.return_value = {'status': 'success', 'changes': {'phone': {}}}
            r = enrich_queue_impl()
        lead.refresh_from_db()
        self.assertEqual(lead.enrichment_status, 'done')
        self.assertGreaterEqual(r['enriched'], 1)
        # A new (unscored) lead is NOT double-queued — its one pending
        # qualification still handles it.
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

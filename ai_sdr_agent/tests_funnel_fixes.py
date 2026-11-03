"""Regression tests for the lead research / enrichment work owned in
`feature/lead-gen` (status doc §4.1 R-items + the auto-enrichment and
export-all features).

NOTE: booking→CRM (S1), meeting→converted (S2) and re-score-after-enrichment
(§5) belong to the other developer's area and are intentionally NOT changed or
tested here.
"""
from unittest import mock

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import ai_sdr_agent as views
from ai_sdr_agent import tasks
from ai_sdr_agent.models import SDRIcpProfile, SDRLead
from ai_sdr_agent.tests import SDRBase


class AutoResearchQueuesQualificationTests(SDRBase):
    """R2: auto-researched (Apify) leads are queued for qualification."""

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

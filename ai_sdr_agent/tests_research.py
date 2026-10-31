"""
Unit and integration tests for Independent Lead Research Workflow (Agent 1).
All external API calls (HTTP web scraping, Apify, Groq) are mocked for deterministic testing.
The same behaviour is measured against the real services by `manage.py eval_lead_research`.
"""

import json
from unittest import mock

import requests
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from ai_sdr_agent.agents.lead_research_agent import LeadResearchAgent, title_matches_icp
from ai_sdr_agent.agents.lead_research_tools import (
    ApifySearchTool, GOOGLE_SEARCH_ACTOR, WebpageExtractor, classify_page, is_public_host,
)
from ai_sdr_agent.agents.lead_research_verification import (
    assess_prospect, assess_site, ground_claim, is_stale, seniority_from_title,
)
from ai_sdr_agent.agents.lead_validator import dedupe_leads, is_decision_maker, normalize_linkedin_url, validate_lead
from ai_sdr_agent.agents.lead_research_workflow import LeadResearchWorkflow
from ai_sdr_agent.agents.lead_qualification_agent import LeadQualificationAgent
from ai_sdr_agent.models import SDRLead, SDRIcpProfile, SDRCampaign
from ai_sdr_agent.tasks import research_lead_impl, research_leads_batch_impl
from core.models import Company, CompanyModulePurchase, CompanyUser


class LeadResearchTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Test Corp', email='corp@test.local')
        self.cu = CompanyUser.objects.create(
            company=self.company, email='admin@test.local', full_name='Admin User',
            role='admin', password_hash='hash', is_active=True,
        )
        CompanyModulePurchase.objects.create(
            company=self.company, module_name='ai_sdr_agent',
            status='active', is_complimentary=True,
        )
        self.icp = SDRIcpProfile.objects.create(
            company_user=self.cu, name='Default SaaS ICP',
            industries=['Software', 'SaaS'], job_titles=['VP Engineering', 'CTO'],
        )
        self.campaign = SDRCampaign.objects.create(
            company_user=self.cu, name='Q1 Enterprise Outreach',
            description='Automated DevOps and Cloud Security Solutions',
            sender_name='Jane SDR', sender_company='CloudSec Global',
        )

    def _make_mock_pages(self, company='AcmeCloud', domain='acmecloud.io'):
        return [
            {
                'page_type': 'homepage',
                'url': f'https://{domain}',
                'content': f'{company} provides cloud-native data observability and automated pipelines for B2B enterprises.',
            },
            {
                'page_type': 'about',
                'url': f'https://{domain}/about',
                'content': f'Founded in 2021, {company} is headquartered in San Francisco with over 150 team members.',
            },
            {
                'page_type': 'products',
                'url': f'https://{domain}/products',
                'content': 'Our core platform includes DataPulse Engine, Telemetry Watchdog, and Cloud Cost Optimizer.',
            },
        ]

    def _make_mock_snippets(self):
        return [
            {
                'title': 'AcmeCloud Raises $18M Series A for Cloud Observability',
                'url': 'https://techcrunch.com/2026/01/acmecloud-series-a',
                'description': 'AcmeCloud announced an $18M Series A round led by Scale Venture Partners to expand European sales and hiring.',
                'query': 'AcmeCloud funding 2026',
            },
            {
                'title': 'John Doe Appointed VP of Engineering at AcmeCloud',
                'url': 'https://businesswire.com/news/john-doe-vp-acmecloud',
                'description': 'AcmeCloud has appointed John Doe as VP of Engineering to lead infrastructure development.',
                'query': 'John Doe AcmeCloud',
            },
        ]

    def _make_mock_groq_response(self, content_dict):
        mock_choice = mock.MagicMock()
        mock_choice.message.content = json.dumps(content_dict)
        mock_resp = mock.MagicMock()
        mock_resp.choices = [mock_choice]
        mock_resp.usage.total_tokens = 450
        mock_groq = mock.MagicMock()
        mock_groq.chat.completions.create.return_value = mock_resp
        return mock_groq

    # -------------------------------------------------------------------------
    # 1. Research for an Apollo-originated lead
    # -------------------------------------------------------------------------
    def test_apollo_originated_lead_research(self):
        lead = SDRLead.objects.create(
            company_user=self.cu, source='apollo', apollo_id='apollo-12345',
            first_name='Alex', last_name='Smith', full_name='Alex Smith',
            job_title='Chief Technology Officer', company_name='DataFlow Inc',
            company_domain='dataflow.io', company_website='https://dataflow.io',
        )
        agent = LeadResearchAgent(company=self.company)
        pages = self._make_mock_pages('DataFlow', 'dataflow.io')
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=pages), \
             mock.patch.object(ApifySearchTool, 'search', return_value=self._make_mock_snippets()):
            profile = agent.research_lead(lead, campaign=self.campaign)

        self.assertEqual(profile['lead_id'], str(lead.id))
        self.assertIn(profile['research_status'], ('completed', 'partially_completed'))
        self.assertTrue(len(profile['evidence']) > 0)

    # -------------------------------------------------------------------------
    # 2. Research for an Apify-originated lead
    # -------------------------------------------------------------------------
    def test_apify_originated_lead_research(self):
        lead = SDRLead.objects.create(
            company_user=self.cu, source='apify',
            first_name='Sarah', last_name='Connor', full_name='Sarah Connor',
            job_title='VP Engineering', company_name='Cyberdyne Analytics',
            company_domain='cyberdyne.ai',
        )
        agent = LeadResearchAgent(company=self.company)
        pages = self._make_mock_pages('Cyberdyne Analytics', 'cyberdyne.ai')
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=pages), \
             mock.patch.object(ApifySearchTool, 'search', return_value=[]):
            profile = agent.research_lead(lead)

        self.assertEqual(profile['lead_id'], str(lead.id))
        self.assertEqual(profile['research_status'], 'completed')
        self.assertEqual(lead.raw_data.get('research_status'), 'completed')

    # -------------------------------------------------------------------------
    # 3. Research for a CSV-imported lead
    # -------------------------------------------------------------------------
    def test_csv_imported_lead_research(self):
        lead = SDRLead.objects.create(
            company_user=self.cu, source='csv_import',
            full_name='Michael Scott', job_title='Regional Manager',
            company_name='Dunder Mifflin Paper', company_domain='dundermifflin.com',
            company_industry='',
        )
        agent = LeadResearchAgent(company=self.company)
        pages = self._make_mock_pages('Dunder Mifflin Paper', 'dundermifflin.com')
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=pages), \
             mock.patch.object(ApifySearchTool, 'search', return_value=[]):
            profile = agent.research_lead(lead)

        self.assertEqual(profile['research_status'], 'completed')
        lead.refresh_from_db()
        self.assertIn('research_profile', lead.raw_data)

    # -------------------------------------------------------------------------
    # 4. Research when only a company domain is available
    # -------------------------------------------------------------------------
    def test_domain_only_research(self):
        lead = SDRLead.objects.create(
            company_user=self.cu, source='manual',
            company_name='Stripe', company_domain='stripe.com',
        )
        agent = LeadResearchAgent(company=self.company)
        pages = self._make_mock_pages('Stripe', 'stripe.com')
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=pages), \
             mock.patch.object(ApifySearchTool, 'search', return_value=[]):
            profile = agent.research_lead(lead)

        self.assertEqual(profile['lead_id'], str(lead.id))
        self.assertTrue(len(profile['company_research']['overview']) > 0)

    # -------------------------------------------------------------------------
    # 5. Company overview extraction
    # -------------------------------------------------------------------------
    def test_company_overview_extraction(self):
        lead = SDRLead.objects.create(
            company_user=self.cu, company_name='AcmeCloud', company_domain='acmecloud.io',
        )
        workflow = LeadResearchWorkflow()
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=self._make_mock_pages()), \
             mock.patch.object(ApifySearchTool, 'search', return_value=[]):
            profile = workflow.execute_research(lead)

        overview = profile['company_research']['overview']
        self.assertTrue(bool(overview))
        self.assertIn('data observability', overview.lower())

    # -------------------------------------------------------------------------
    # 6. Product and service extraction
    # -------------------------------------------------------------------------
    def test_product_and_service_extraction(self):
        lead = SDRLead.objects.create(
            company_user=self.cu, company_name='AcmeCloud', company_domain='acmecloud.io',
        )
        workflow = LeadResearchWorkflow()
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=self._make_mock_pages()), \
             mock.patch.object(ApifySearchTool, 'search', return_value=[]):
            profile = workflow.execute_research(lead)

        products = profile['company_research']['products_services']
        self.assertIsInstance(products, list)
        self.assertTrue(len(products) > 0)

    # -------------------------------------------------------------------------
    # 7. Recent company signal extraction
    # -------------------------------------------------------------------------
    def test_recent_company_signal_extraction(self):
        lead = SDRLead.objects.create(
            company_user=self.cu, company_name='AcmeCloud', company_domain='acmecloud.io',
        )
        workflow = LeadResearchWorkflow()
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=[]), \
             mock.patch.object(ApifySearchTool, 'search', return_value=self._make_mock_snippets()):
            profile = workflow.execute_research(lead)

        signals = profile['company_signals']
        self.assertTrue(len(signals) > 0)
        first_signal = signals[0]
        self.assertIn('type', first_signal)
        self.assertIn('source_url', first_signal)
        self.assertIn('confidence', first_signal)
        self.assertEqual(first_signal['type'], 'funding')

    # -------------------------------------------------------------------------
    # 8. Prospect context extraction
    # -------------------------------------------------------------------------
    def test_prospect_context_extraction(self):
        lead = SDRLead.objects.create(
            company_user=self.cu, full_name='Rachel Green', job_title='Chief Executive Officer',
            company_name='Ralph Lauren Corp', company_domain='ralphlauren.com',
        )
        workflow = LeadResearchWorkflow()
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=[]), \
             mock.patch.object(ApifySearchTool, 'search', return_value=[]):
            profile = workflow.execute_research(lead)

        prospect = profile['prospect_research']
        self.assertEqual(prospect['name'], 'Rachel Green')
        self.assertEqual(prospect['designation'], 'Chief Executive Officer')
        self.assertEqual(prospect['seniority'], 'C-Level')
        self.assertEqual(prospect['department'], 'Executive')

    # -------------------------------------------------------------------------
    # 9. Evidence attribution
    # -------------------------------------------------------------------------
    def test_evidence_attribution(self):
        lead = SDRLead.objects.create(
            company_user=self.cu, company_name='AcmeCloud', company_domain='acmecloud.io',
        )
        workflow = LeadResearchWorkflow()
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=self._make_mock_pages()), \
             mock.patch.object(ApifySearchTool, 'search', return_value=self._make_mock_snippets()):
            profile = workflow.execute_research(lead)

        evidence = profile['evidence']
        self.assertTrue(len(evidence) >= 3)
        for item in evidence:
            self.assertIn('finding', item)
            self.assertIn('source_url', item)
            self.assertIn('source_type', item)
            self.assertIn('retrieved_at', item)
            self.assertIn('confidence', item)

    # -------------------------------------------------------------------------
    # 10. Groq structured output validation
    # -------------------------------------------------------------------------
    def test_groq_structured_output_validation(self):
        lead = SDRLead.objects.create(
            company_user=self.cu, full_name='David Kim', job_title='VP Sales',
            company_name='FinScale', company_domain='finscale.co',
        )
        pages = [
            {'page_type': 'homepage', 'url': 'https://finscale.co',
             'content': 'FinScale provides automated treasury management for SaaS companies.'},
            {'page_type': 'news', 'url': 'https://finscale.co/news/london',
             'content': 'February 15, 2026: FinScale opened a new London office to serve EMEA clients.'},
        ]
        model_output = {
            'claims': [
                {'field': 'overview', 'value': 'FinScale provides automated treasury management for SaaS companies.',
                 'source': 'S1', 'quote': 'FinScale provides automated treasury management for SaaS companies.'},
                {'field': 'industry', 'value': 'Treasury management', 'source': 'S1',
                 'quote': 'FinScale provides automated treasury management for SaaS companies.'},
            ],
            'signals': [
                {'type': 'expansion', 'description': 'FinScale opened a London office.', 'source': 'S2',
                 'quote': 'FinScale opened a new London office to serve EMEA clients.'},
            ],
            'campaign_relevance': {'relevant_opportunities': ['EMEA expansion outreach']},
        }
        mock_groq = self._make_mock_groq_response(model_output)
        workflow = LeadResearchWorkflow(groq_client=mock_groq)

        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=pages), \
             mock.patch.object(ApifySearchTool, 'search', return_value=[]):
            profile = workflow.execute_research(lead, campaign=self.campaign)

        self.assertEqual(profile['company_research']['industry'], 'Treasury management')
        self.assertEqual(len(profile['company_signals']), 1)
        self.assertEqual(profile['company_signals'][0]['type'], 'expansion')
        self.assertEqual(profile['company_signals'][0]['source_url'], 'https://finscale.co/news/london')
        self.assertEqual(profile['provider_status']['llm'], 'ok')

    # -------------------------------------------------------------------------
    # 11. Missing website handling
    # -------------------------------------------------------------------------
    def test_missing_website_handling(self):
        lead = SDRLead.objects.create(
            company_user=self.cu, full_name='Alice Wonderland', job_title='Consultant',
            company_name='NonExistentBrandXYZ', company_domain='', company_website='',
        )
        agent = LeadResearchAgent(company=self.company)
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=[]), \
             mock.patch.object(ApifySearchTool, 'search', return_value=[]):
            profile = agent.research_lead(lead)

        self.assertEqual(profile['research_status'], 'partially_completed')
        self.assertEqual(profile['company_research']['overview'], 'unknown')

    # -------------------------------------------------------------------------
    # 12. Search provider failure
    # -------------------------------------------------------------------------
    def test_search_provider_failure(self):
        lead = SDRLead.objects.create(
            company_user=self.cu, company_name='AcmeCloud', company_domain='acmecloud.io',
        )
        workflow = LeadResearchWorkflow()
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=self._make_mock_pages()), \
             mock.patch.object(ApifySearchTool, 'search', side_effect=Exception('Apify connection refused')):
            profile = workflow.execute_research(lead)

        self.assertEqual(profile['research_status'], 'completed')
        self.assertTrue(len(profile['evidence']) > 0)

    # -------------------------------------------------------------------------
    # 13. Website extraction failure
    # -------------------------------------------------------------------------
    def test_website_extraction_failure(self):
        lead = SDRLead.objects.create(
            company_user=self.cu, company_name='AcmeCloud', company_domain='acmecloud.io',
        )
        workflow = LeadResearchWorkflow()
        with mock.patch.object(WebpageExtractor, 'extract_company_site', side_effect=Exception('DNS lookup failed')), \
             mock.patch.object(ApifySearchTool, 'search', return_value=self._make_mock_snippets()):
            profile = workflow.execute_research(lead)

        self.assertEqual(profile['research_status'], 'completed')
        self.assertTrue(len(profile['company_signals']) > 0)

    # -------------------------------------------------------------------------
    # 14. Partial research completion
    # -------------------------------------------------------------------------
    def test_partial_research_completion(self):
        lead = SDRLead.objects.create(
            company_user=self.cu, company_name='Quiet Stealth Startup',
        )
        workflow = LeadResearchWorkflow()
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=[]), \
             mock.patch.object(ApifySearchTool, 'search', return_value=[]):
            profile = workflow.execute_research(lead)

        self.assertEqual(profile['research_status'], 'partially_completed')
        self.assertTrue(profile['research_confidence'] < 50)

    # -------------------------------------------------------------------------
    # 15. Individual and batch execution
    # -------------------------------------------------------------------------
    def test_individual_and_batch_execution(self):
        lead1 = SDRLead.objects.create(company_user=self.cu, company_name='Comp1', company_domain='comp1.io')
        lead2 = SDRLead.objects.create(company_user=self.cu, company_name='Comp2', company_domain='comp2.io')

        agent = LeadResearchAgent(company=self.company)
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=self._make_mock_pages()), \
             mock.patch.object(ApifySearchTool, 'search', return_value=[]):
            batch_results = agent.research_leads_batch([lead1, lead2])

        self.assertEqual(len(batch_results), 2)
        self.assertEqual(batch_results[0]['lead_id'], str(lead1.id))
        self.assertEqual(batch_results[1]['lead_id'], str(lead2.id))

    # -------------------------------------------------------------------------
    # 16. Duplicate execution prevention
    # -------------------------------------------------------------------------
    def test_duplicate_execution_prevention(self):
        lead = SDRLead.objects.create(
            company_user=self.cu, company_name='SavedCorp', company_domain='savedcorp.com',
            raw_data={'research_status': 'completed', 'research_profile': {'cached': True}},
        )
        res = research_lead_impl(lead.id, force=False)
        self.assertEqual(res['status'], 'already_completed')
        self.assertTrue(res['profile']['cached'])

        # With force=True, it re-runs
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=[]), \
             mock.patch.object(ApifySearchTool, 'search', return_value=[]):
            forced_res = research_lead_impl(lead.id, force=True)
        self.assertEqual(forced_res['status'], 'success')

    # -------------------------------------------------------------------------
    # 17. Research persistence
    # -------------------------------------------------------------------------
    def test_research_persistence(self):
        lead = SDRLead.objects.create(
            company_user=self.cu, company_name='AcmeCloud', company_domain='acmecloud.io',
            company_industry='',
        )
        agent = LeadResearchAgent(company=self.company)
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=self._make_mock_pages()), \
             mock.patch.object(ApifySearchTool, 'search', return_value=self._make_mock_snippets()):
            agent.research_lead(lead)

        lead.refresh_from_db()
        self.assertEqual(lead.raw_data.get('research_status'), 'completed')
        self.assertIn('research_profile', lead.raw_data)
        self.assertTrue(len(lead.buying_signals) > 0)
        self.assertTrue(len(lead.recent_news) > 0)
        self.assertTrue(lead.company_website.startswith('https://'))

    # -------------------------------------------------------------------------
    # 18. Downstream Qualification Compatibility
    # -------------------------------------------------------------------------
    def test_downstream_qualification_compatibility(self):
        lead = SDRLead.objects.create(
            company_user=self.cu, full_name='Tim Cook', job_title='CEO',
            company_name='Apple', company_domain='apple.com',
            company_industry='Consumer Electronics', company_size=160000,
        )
        agent = LeadResearchAgent(company=self.company)
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=self._make_mock_pages()), \
             mock.patch.object(ApifySearchTool, 'search', return_value=self._make_mock_snippets()):
            agent.research_lead(lead)

        lead.refresh_from_db()
        # Verify Qualification Agent consumes enriched fields without error
        qualifier = LeadQualificationAgent()  # rule-based fallback without LLM
        qual_res = qualifier.qualify_lead(lead, self.icp)
        self.assertIn('score', qual_res)
        self.assertIn('temperature', qual_res)
        self.assertTrue(0 <= qual_res['score'] <= 100)


def _lead(**fields):
    return {'id': 1, **fields}


def _search_result(title, description='', url='https://news.example/a', published_at='2026-09-01'):
    return {'title': title, 'description': description, 'url': url, 'published_at': published_at,
            'provider': 'google_search'}


class _Fixture:
    """A workflow with its website and search replaced, for testing what it concludes from them."""

    PAGES = [{'page_type': 'homepage', 'url': 'https://stripe.com', 'title': 'Stripe | Financial Infrastructure',
              'content': 'Stripe builds financial infrastructure for the internet to accept payments.'}]

    def research(self, lead, pages=None, snippets=(), groq=None, status='ok'):
        workflow = LeadResearchWorkflow(groq_client=groq)
        workflow.search_tool.last_status = status
        with mock.patch.object(WebpageExtractor, 'extract_company_site',
                               return_value=self.PAGES if pages is None else pages), \
                mock.patch.object(ApifySearchTool, 'search', return_value=list(snippets)):
            return workflow.execute_research(lead)


class AuthenticityTests(_Fixture, SimpleTestCase):
    def test_a_person_nobody_mentions_is_not_confirmed(self):
        profile = self.research(_lead(full_name='Velmora Quistan', job_title='VP Sales', company_name='Stripe',
                                 company_domain='stripe.com'))
        self.assertEqual(profile['verification']['prospect']['status'], 'not_found')
        self.assertLessEqual(profile['research_confidence'], 40)
        self.assertEqual(profile['prospect_research']['responsibilities'], [])
        self.assertEqual(profile['research_status'], 'partially_completed')

    def test_a_nonexistent_company_gets_no_story(self):
        profile = self.research(_lead(company_name='Zyntrafloq Dynamics', full_name='Velmora Quistan', job_title='CEO'),
                           pages=[{'page_type': 'unreachable', 'url': 'https://zyntrafloqdynamics.com', 'content': ''}])
        self.assertEqual(profile['verification']['company']['status'], 'not_found')
        self.assertEqual(profile['company_research']['overview'], 'unknown')
        self.assertEqual(profile['company_signals'], [])
        self.assertLessEqual(profile['research_confidence'], 15)
        self.assertEqual(profile['research_status'], 'partially_completed')

    def test_no_evidence_never_reaches_the_model(self):
        # Otherwise it answers from memory, which is exactly the fabrication we are preventing.
        groq = mock.MagicMock()
        self.research(_lead(company_name='Quiet Co'), pages=[], groq=groq)
        groq.chat.completions.create.assert_not_called()

    def test_guessed_domain_for_another_company_is_rejected(self):
        # linear.com really does redirect to Analog Devices.
        analog = [{'page_type': 'homepage', 'url': 'https://www.analog.com/', 'title': 'Analog Devices',
                   'content': 'Analog Devices is a global semiconductor leader. ' * 5}]
        profile = self.research(_lead(company_name='Linear', full_name='Karri Saarinen', job_title='CEO'), pages=analog)
        self.assertNotEqual(profile['verification']['website']['status'], 'verified')
        self.assertEqual(profile['company_research']['overview'], 'unknown')
        self.assertEqual([e for e in profile['evidence'] if e['source_type'] == 'official_website'], [])

    def test_website_found_through_search_when_the_guess_is_wrong(self):
        analog = [{'page_type': 'homepage', 'url': 'https://www.analog.com/', 'title': 'Analog Devices',
                   'content': 'Analog Devices is a global semiconductor leader. ' * 5}]
        linear = [{'page_type': 'homepage', 'url': 'https://linear.app/', 'title': 'Linear',
                   'content': 'Linear is a purpose-built tool for planning and building products.'}]
        workflow = LeadResearchWorkflow()
        workflow.search_tool.last_status = 'ok'
        results = [_search_result('Linear', 'Plan and build products', url='https://linear.app/')]
        with mock.patch.object(WebpageExtractor, 'extract_company_site', side_effect=[analog, linear]), \
                mock.patch.object(ApifySearchTool, 'search', return_value=results):
            profile = workflow.execute_research(_lead(company_name='Linear'))
        self.assertEqual(profile['verification']['website']['status'], 'verified')
        self.assertIn('linear.app', profile['verification']['website']['url'])

    def test_failed_website_never_counts_as_a_page_read(self):
        profile = self.research(_lead(company_name='Ox Delivers', company_website='https://www.oxdelivers.com',
                                 company_industry='Automotive'),
                           pages=[{'page_type': 'unreachable', 'url': 'https://www.oxdelivers.com', 'content': '',
                                   'status_code': 404, 'error': 'HTTP 404'}], status='ok')
        self.assertEqual(profile['verification']['website']['status'], 'unreachable')
        self.assertEqual(profile['company_research']['overview'], 'unknown')
        self.assertEqual(profile['research_status'], 'partially_completed')

    def test_missing_contact_details_stay_missing(self):
        profile = self.research(_lead(full_name='Patrick Collison', job_title='CEO', company_name='Stripe',
                                 company_domain='stripe.com'))
        for field in ('email', 'phone', 'linkedin_url'):
            self.assertIn(field, profile['missing_information'])
        self.assertNotIn('@', json.dumps(profile['company_research']))

    def test_provider_data_is_labelled_not_verified(self):
        profile = self.research(_lead(company_name='Ox Delivers', company_website='https://www.oxdelivers.com',
                                 raw_data={'company_description': 'OX is a startup automotive company.'}),
                           pages=[{'page_type': 'unreachable', 'url': 'https://www.oxdelivers.com', 'content': ''}])
        self.assertEqual(profile['verification']['company']['status'], 'provider_reported')
        row = next(e for e in profile['evidence'] if e['source_type'] == 'provider_data')
        self.assertEqual(row['status'], 'provider_reported')
        self.assertEqual(row['confidence'], 'low')

    def test_search_outage_is_not_reported_as_not_found(self):
        profile = self.research(_lead(full_name='Patrick Collison', job_title='CEO', company_name='Unknown Ltd'),
                           pages=[], status='failed')
        self.assertEqual(profile['verification']['prospect']['status'], 'unverified')
        self.assertEqual(profile['verification']['company']['status'], 'unverified')
        self.assertEqual(profile['provider_status']['search'], 'failed')

    def test_no_template_text_in_a_profile_with_no_evidence(self):
        profile = self.research(_lead(full_name='A Person', job_title='VP Sales', company_name='Quiet Co'), pages=[])
        body = json.dumps(profile).lower()
        for phrase in ('evaluates operational', 'quality commercial', 'operational efficiency', 'directs vp'):
            self.assertNotIn(phrase, body)
        self.assertIn('No public source confirms', profile['prospect_research']['decision_making_relevance'])
        self.assertEqual(profile['campaign_relevance']['personalization_angles'], [])

    def test_contradicted_role_gets_no_buying_context(self):
        result = _search_result('Stripe', 'Stripe CEO Patrick Collison spoke.', url='https://n.example/a')
        profile = self.research(_lead(full_name='Patrick Collison', job_title='CFO', company_name='Stripe',
                                      company_domain='stripe.com'), snippets=[result])
        self.assertEqual(profile['prospect_research']['decision_making_relevance'], 'unknown')


class ConfidenceTests(_Fixture, SimpleTestCase):
    def test_an_unstated_role_cannot_score_high(self):
        results = [_search_result('Stripe news', 'Stripe founder Patrick Collison spoke.', url=f'https://n{i}.example/a')
                   for i in range(4)]
        profile = self.research(_lead(full_name='Patrick Collison', job_title='CFO', company_name='Stripe',
                                      company_domain='stripe.com'), snippets=results)
        self.assertEqual(profile['verification']['prospect']['status'], 'inferred')
        self.assertLessEqual(profile['research_confidence'], 60)


class GroundingTests(_Fixture, SimpleTestCase):
    def groq(self, output):
        choice = mock.MagicMock()
        choice.message.content = json.dumps(output)
        client = mock.MagicMock()
        client.chat.completions.create.return_value.choices = [choice]
        return client

    def lead(self):
        return _lead(company_name='Stripe', company_domain='stripe.com')

    def test_claim_with_an_invented_quote_is_dropped(self):
        groq = self.groq({'claims': [{'field': 'overview', 'value': 'Stripe sells shoes.', 'source': 'S1',
                                      'quote': 'Stripe sells the finest shoes in Ireland.'}]})
        profile = self.research(self.lead(), groq=groq)
        self.assertEqual(profile['company_research']['overview'], 'unknown')
        self.assertEqual(profile['verification']['unsupported_claims_removed'], 1)

    def test_claim_citing_a_source_that_does_not_exist_is_dropped(self):
        groq = self.groq({'claims': [{'field': 'overview', 'value': 'Financial infrastructure.', 'source': 'S9',
                                      'quote': 'Stripe builds financial infrastructure for the internet'}]})
        self.assertEqual(self.research(self.lead(), groq=groq)['company_research']['overview'], 'unknown')

    def test_invented_number_is_dropped_even_with_a_real_quote(self):
        groq = self.groq({'claims': [{'field': 'overview', 'value': 'Stripe infrastructure raised $900M',
                                      'source': 'S1', 'quote': 'Stripe builds financial infrastructure for the internet'}]})
        self.assertEqual(self.research(self.lead(), groq=groq)['company_research']['overview'], 'unknown')

    def test_grounded_claim_is_kept_with_its_source(self):
        quote = 'Stripe builds financial infrastructure for the internet'
        groq = self.groq({'claims': [{'field': 'overview', 'value': 'Stripe builds financial infrastructure',
                                      'source': 'S1', 'quote': quote}]})
        profile = self.research(self.lead(), groq=groq)
        self.assertEqual(profile['company_research']['overview'], 'Stripe builds financial infrastructure')
        row = profile['evidence'][0]
        self.assertEqual((row['source_url'], row['status'], row['quote']), ('https://stripe.com', 'verified', quote))

    def test_signal_date_comes_from_the_source_not_the_model(self):
        result = _search_result('Stripe raises $1B', 'Stripe raises $1B in new funding', published_at='2026-05-01')
        groq = self.groq({'signals': [{'type': 'funding', 'description': 'Stripe raises $1B', 'source': 'S2',
                                       'quote': 'Stripe raises $1B', 'published_at': '2031-01-01'}]})
        self.assertEqual(self.research(self.lead(), snippets=[result], groq=groq)['company_signals'][0]['published_at'],
                         '2026-05-01')

    def test_marketing_copy_is_not_a_signal(self):
        # What the old agent really produced from stripe.com when its search was down.
        quote = 'Stripe builds financial infrastructure for the internet'
        groq = self.groq({'signals': [{'type': 'expansion', 'description': 'Stripe builds financial infrastructure',
                                       'source': 'S1', 'quote': quote}]})
        profile = self.research(self.lead(), groq=groq)
        self.assertEqual(profile['company_signals'], [])

    def test_acquisition_is_not_labelled_as_expansion(self):
        result = _search_result('Stripe expands reach', 'Stripe expands crypto reach through Bridge acquisition')
        self.assertEqual(self.research(self.lead(), snippets=[result])['company_signals'][0]['type'],
                         'strategic_announcement')

    def test_a_front_page_is_not_a_citation(self):
        result = _search_result('Stripe raises $1B', 'Stripe raises $1B', url='https://news.example/')
        self.assertEqual(self.research(self.lead(), snippets=[result])['company_signals'], [])

    def test_stale_signal_is_dropped(self):
        old = _search_result('Stripe raises $600M', 'Stripe raises $600M', published_at='2021-03-14')
        self.assertEqual(self.research(self.lead(), snippets=[old])['company_signals'], [])

    def test_snippet_about_a_different_company_is_ignored(self):
        other = _search_result('Acme raises $5M', 'Acme raises $5M in funding')
        self.assertEqual(self.research(self.lead(), snippets=[other])['company_signals'], [])

    def test_malformed_model_output_falls_back_to_copying_sources(self):
        groq = mock.MagicMock()
        groq.chat.completions.create.return_value.choices = [mock.MagicMock(**{'message.content': 'not json'})]
        profile = self.research(self.lead(), groq=groq)
        self.assertEqual(profile['provider_status']['llm'], 'failed')
        self.assertIn('financial infrastructure', profile['company_research']['overview'])
        self.assertEqual(groq.chat.completions.create.call_count, 2)

    def test_a_refused_key_is_not_swallowed(self):
        from core.api_key_service import KeyServiceError
        groq = mock.MagicMock()
        groq.chat.completions.create.side_effect = KeyServiceError('bad key')
        with self.assertRaises(KeyServiceError):
            self.research(self.lead(), groq=groq)


class ProspectAssessmentTests(SimpleTestCase):
    def check(self, title, company, *texts, name='Patrick Collison', official=False):
        sources = [{'url': f'https://s/{i}', 'text': text, 'official': official} for i, text in enumerate(texts)]
        return assess_prospect(name, title, company, sources, search_ran=True)['status']

    def test_confirmed_from_a_news_sentence(self):
        self.assertEqual(self.check('CEO', 'Stripe', 'Stripe CEO Patrick Collison said revenue grew.'), 'verified')

    def test_confirmed_with_chief_executive_spelled_out(self):
        self.assertEqual(self.check('CEO', 'Stripe', 'Patrick Collison, chief executive of Stripe, spoke.'), 'verified')

    def test_confirmed_on_the_companys_own_leadership_page(self):
        self.assertEqual(self.check('CEO', 'Stripe', 'Patrick Collison, CEO and co-founder', official=True), 'verified')

    def test_title_conflict(self):
        self.assertEqual(self.check('CFO', 'Stripe', 'Stripe CEO Patrick Collison said revenue grew.'), 'conflict')

    def test_wrong_company_even_when_both_are_in_the_sentence(self):
        self.assertEqual(
            self.check('CEO', 'Salesforce', 'Salesforce CEO Marc Benioff and Microsoft CEO Satya Nadella spoke.',
                       name='Satya Nadella'), 'conflict')

    def test_former_title_is_outdated(self):
        self.assertEqual(self.check('CEO', 'Amazon', 'Former Amazon CEO Jeff Bezos spoke.', name='Jeff Bezos'),
                         'outdated')

    def test_stepped_down_is_outdated_despite_older_current_sources(self):
        self.assertEqual(
            self.check('CEO', 'Apple', 'Apple CEO Tim Cook announced the iPhone.',
                       'Tim Cook will step down as Apple CEO in September.', name='Tim Cook'), 'outdated')

    def test_successor_sentence_is_outdated_for_the_predecessor(self):
        self.assertEqual(self.check('CEO', 'Apple', 'John Ternus succeeded Tim Cook as Apple CEO.', name='Tim Cook'),
                         'outdated')

    def test_successor_is_not_outdated_for_the_new_ceo(self):
        self.assertEqual(self.check('CEO', 'Apple', 'John Ternus succeeded Tim Cook as Apple CEO.', name='John Ternus'),
                         'verified')

    def test_name_with_company_but_no_role_is_only_inferred(self):
        self.assertEqual(self.check('CEO', 'Stripe', 'Patrick Collison spoke at a Stripe event.'), 'inferred')

    def test_handing_over_the_reins_is_outdated(self):
        # A real snippet that the benchmark caught passing as confirmation.
        text = 'Amazon CEO Jeff Bezos will hand the reins over to cloud boss Andy Jassy.'
        self.assertEqual(self.check('CEO', 'Amazon', text, name='Jeff Bezos'), 'outdated')

    def test_an_old_article_cannot_confirm_a_current_role(self):
        sources = [{'url': 'https://s/1', 'text': 'Amazon CEO Jeff Bezos spoke.', 'published_at': '2019-05-01'}]
        self.assertNotEqual(assess_prospect('Jeff Bezos', 'CEO', 'Amazon', sources, True)['status'], 'verified')

    def test_a_job_word_is_not_an_employer(self):
        # From a real lead: "Owner CEO Dan Claypool" came back as "Sources place them at Owner".
        self.assertEqual(self.check('Owner/CEO', 'Merric', 'Merric Owner and CEO Dan Claypool spoke.',
                                    name='Dan Claypool'), 'verified')

    def test_either_half_of_a_double_title_confirms_it(self):
        self.assertEqual(self.check('Founder, Director', 'Lynchpin', 'Pippa Sanderson, founder of Lynchpin, spoke.',
                                    name='Pippa Sanderson'), 'verified')

    def test_short_first_name_matches(self):
        self.assertEqual(self.check('CEO', 'Shopify', 'Shopify CEO Tobi Lutke wrote a memo.', name='Tobias Lutke'),
                         'verified')

    def test_accented_name_matches(self):
        self.assertEqual(self.check('CEO', 'Shopify', 'Shopify CEO Tobi L\u00fctke wrote a memo.', name='Tobias Lutke'),
                         'verified')

    def test_non_c_level_title_needs_every_word(self):
        self.assertEqual(self.check('VP Sales', 'Stripe', 'Jane Roe, VP Sales at Stripe, spoke.', name='Jane Roe'),
                         'verified')
        self.assertEqual(self.check('VP Sales', 'Stripe', 'Jane Roe, VP Marketing at Stripe, spoke.', name='Jane Roe'),
                         'inferred')


class VerificationHelperTests(SimpleTestCase):
    def test_seniority_uses_whole_words(self):
        self.assertEqual(seniority_from_title('Director of Sales')[0], 'Director')  # "cto" is inside Director
        self.assertEqual(seniority_from_title('Vice President, Sales')[0], 'VP / Head')  # so is "president"
        self.assertEqual(seniority_from_title('President')[0], 'C-Level')
        self.assertEqual(seniority_from_title('Account Executive')[0], 'unknown')

    def test_redirect_to_an_unrelated_domain_is_a_conflict(self):
        page = {'url': 'https://intelligentglobalmedia.com/', 'content': 'Intelligent Global Media is a publisher.',
                'title': 'Intelligent Global Media'}
        self.assertEqual(assess_site('Lynchpin Media', page, 'lynchpinmedia.com')['status'], 'conflict')

    def test_rebranded_domain_is_accepted_when_the_site_names_the_company(self):
        page = {'url': 'https://acme.io/', 'title': 'Acme', 'content': 'Acme makes rockets.'}
        self.assertEqual(assess_site('Acme', page, 'acme.com')['status'], 'verified')

    def test_ground_claim_ignores_punctuation_and_spacing(self):
        self.assertTrue(ground_claim('Payments for the internet', 'payments  for the\ninternet!',
                                     'We do payments for the internet.'))

    def test_is_stale(self):
        self.assertTrue(is_stale('Sun, 14 Mar 2021 10:00:00 GMT'))
        self.assertFalse(is_stale(timezone.now().isoformat()))
        self.assertFalse(is_stale(''))  # unknown is not the same as old


class ValidatorTests(SimpleTestCase):
    def test_decision_maker_matches_whole_words(self):
        for title in ('Office Coordinator', 'Segment Analyst', 'Product Owner', 'Partner Success Manager', 'PA to Founders'):
            self.assertFalse(is_decision_maker(title), title)
        for title in ('CEO', 'Director of Sales', 'VP Marketing', 'Owner', 'Managing Partner'):
            self.assertTrue(is_decision_maker(title), title)

    def test_apollo_placeholder_email_is_rejected(self):
        result = validate_lead({'full_name': 'Jo Bloggs', 'email': 'email_not_unlocked@domain.com', 'job_title': 'CEO',
                                'company_name': 'Real Co'})
        self.assertFalse(result['email_format_valid'])

    def test_ai_generated_record_cannot_score_well(self):
        result = validate_lead({'full_name': 'Sarah Chen', 'email': 'sarah@novatech.com', 'job_title': 'CTO',
                                'company_name': 'NovaTech', 'company_location': 'Austin', 'source': 'ai_generated'})
        self.assertLessEqual(result['confidence_score'], 20)
        self.assertFalse(result['is_valid'])

    def test_mismatched_email_domain_is_flagged(self):
        result = validate_lead({'full_name': 'A B', 'email': 'a@other.com', 'company_domain': 'real.com'})
        self.assertIn('Email domain differs from company domain', result['data_quality_flags'])

    def test_linkedin_variants_are_one_person(self):
        expected = 'linkedin.com/in/jane-doe'
        for url in ('https://uk.linkedin.com/in/jane-doe/', 'http://www.linkedin.com/in/Jane-Doe?trk=x',
                    'https://www.linkedin.com/in/jane-doe'):
            self.assertEqual(normalize_linkedin_url(url), expected)

    def test_dedupe_by_linkedin_email_and_name(self):
        leads = [
            {'full_name': 'Jane Doe', 'company_name': 'A', 'linkedin_url': 'https://uk.linkedin.com/in/jane'},
            {'full_name': 'Jane D', 'company_name': 'B', 'linkedin_url': 'https://www.linkedin.com/in/jane/'},
            {'full_name': 'Sam Roe', 'email': 'sam@a.com'},
            {'full_name': 'S Roe', 'email': 'SAM@a.com'},
            {'full_name': 'Kim Lee', 'company_name': 'A'},
            {'full_name': 'kim lee', 'company_name': 'a'},
            {'full_name': 'Kim Lee', 'company_name': 'B'},
        ]
        self.assertEqual(len(dedupe_leads(leads)), 4)


class LeadSearchTests(SimpleTestCase):
    def icp(self, **fields):
        return mock.MagicMock(**{'job_titles': ['CTO'], 'industries': ['SaaS'], 'locations': ['USA'], 'keywords': [],
                                 'company_size_min': None, 'company_size_max': None, **fields})

    def agent(self, **kwargs):
        return LeadResearchAgent(**{'apify_actor': 'code_crafter/leads-finder', **kwargs})

    def response(self, status=200, body=None):
        resp = mock.MagicMock(status_code=status, text=json.dumps(body or {}))
        resp.json.return_value = body or {}
        return resp

    def test_there_is_no_ai_lead_source(self):
        agent = LeadResearchAgent(apify_token='', apollo_api_key='', apify_actor='x')
        agent.apify_token = agent.apollo_api_key = ''
        agent.groq_client = mock.MagicMock()
        self.assertEqual(agent.available_sources, [])
        for source in ('auto', 'ai', 'ai_generated'):
            with self.assertRaises(ValueError):
                agent.search_leads(self.icp(), source=source)
        agent.groq_client.chat.completions.create.assert_not_called()

    def test_auto_moves_on_when_apollo_fails(self):
        agent = self.agent(apollo_api_key='k', apify_token='t')
        with mock.patch.object(agent, '_search_apollo', side_effect=ValueError('down')), \
                mock.patch.object(agent, '_search_apify', return_value=[{'full_name': 'A B'}]) as apify:
            self.assertEqual(len(agent.search_leads(self.icp())), 1)
        apify.assert_called_once()

    def test_auto_moves_on_when_apollo_finds_nobody(self):
        agent = self.agent(apollo_api_key='k', apify_token='t')
        with mock.patch.object(agent, '_search_apollo', return_value=[]), \
                mock.patch.object(agent, '_search_apify', return_value=[{'full_name': 'A B'}]):
            self.assertEqual(len(agent.search_leads(self.icp())), 1)

    def test_every_provider_failing_reports_both_and_invents_nothing(self):
        agent = self.agent(apollo_api_key='k', apify_token='t')
        with mock.patch.object(agent, '_search_apollo', side_effect=ValueError('apollo down')), \
                mock.patch.object(agent, '_search_apify', side_effect=ValueError('apify down')):
            with self.assertRaisesRegex(ValueError, 'apollo down.*apify down'):
                agent.search_leads(self.icp())

    def test_apollo_request_matches_the_documented_endpoint(self):
        agent = self.agent(apollo_api_key='k')
        with mock.patch('requests.post', return_value=self.response(200, {'people': []})) as post:
            agent._search_apollo(self.icp(company_size_min=20000), 10)
        args, kwargs = post.call_args
        self.assertTrue(args[0].endswith('/api/v1/mixed_people/api_search'))
        self.assertEqual(kwargs['params']['person_titles[]'], ['CTO'])
        self.assertEqual(kwargs['params']['organization_num_employees_ranges[]'], ['10001,1000000'])

    def test_apollo_status_codes_are_readable(self):
        agent = self.agent(apollo_api_key='k')
        for status, text in ((401, 'rejected the API key'), (403, 'access denied'), (429, 'rate limit')):
            with mock.patch('requests.post', return_value=self.response(status)), mock.patch('time.sleep'), \
                    self.assertRaisesRegex(ValueError, text):
                agent._search_apollo(self.icp(), 5)

    def test_apollo_timeout_is_a_clean_error(self):
        agent = self.agent(apollo_api_key='k')
        with mock.patch('requests.post', side_effect=requests.Timeout('slow')), \
                self.assertRaisesRegex(ValueError, 'request failed'):
            agent._search_apollo(self.icp(), 5)

    def test_apollo_masked_person_keeps_only_real_data(self):
        parsed = self.agent()._parse_apollo_person({
            'id': '1', 'first_name': 'Andrew', 'last_name_obfuscated': 'Hu***n', 'title': 'CTO',
            'email': 'email_not_unlocked@domain.com', 'city': 'Austin',
            'phone_numbers': [{'sanitized_number': '+15550001111'}],
            'organization': {'name': 'Real Co', 'city': 'Boston', 'country': 'United States'},
        })
        self.assertEqual(parsed['full_name'], 'Andrew')
        self.assertEqual(parsed['email'], '')
        self.assertEqual(parsed['phone'], '+15550001111')
        self.assertEqual(parsed['company_location'], 'Boston, United States')

    def test_apify_token_is_never_in_a_url(self):
        agent = self.agent(apify_token='secret-token')
        with mock.patch('requests.post', side_effect=requests.ConnectionError('boom')) as post, \
                self.assertRaises(ValueError) as caught:
            agent._search_apify(self.icp(), 5)
        self.assertNotIn('secret-token', str(caught.exception))
        self.assertNotIn('params', post.call_args.kwargs)

    def test_apify_failed_run_reports_why(self):
        agent = self.agent(apify_token='t')
        start = self.response(201, {'data': {'id': 'r1'}})
        failed = self.response(200, {'data': {'status': 'FAILED', 'statusMessage': 'Add at least one filter'}})
        with mock.patch('requests.post', return_value=start), mock.patch('requests.get', return_value=failed), \
                mock.patch('time.sleep'), self.assertRaisesRegex(ValueError, 'Add at least one filter'):
            agent._search_apify(self.icp(), 5)

    def test_apify_timeout_aborts_the_run(self):
        agent = self.agent(apify_token='t')
        start = self.response(201, {'data': {'id': 'r1'}})
        running = self.response(200, {'data': {'status': 'RUNNING'}})
        with mock.patch('requests.post', return_value=start) as post, mock.patch('requests.get', return_value=running), \
                mock.patch('time.sleep'), self.assertRaisesRegex(ValueError, 'timed out'):
            agent._search_apify(self.icp(), 5)
        self.assertTrue(post.call_args.args[0].endswith('/actor-runs/r1/abort'))

    def test_apify_empty_dataset_returns_no_leads(self):
        agent = self.agent(apify_token='t')
        start = self.response(201, {'data': {'id': 'r1'}})
        done = self.response(200, {'data': {'status': 'SUCCEEDED', 'defaultDatasetId': 'd'}})
        items = self.response(200)
        items.json.return_value = []
        with mock.patch('requests.post', return_value=start), mock.patch('requests.get', side_effect=[done, items]), \
                mock.patch('time.sleep'):
            self.assertEqual(agent._search_apify(self.icp(), 5), [])

    def test_inputs_contain_only_what_the_user_asked_for(self):
        for actor in ('evascrape/b2b-leads-finder', 'apify/google-search-scraper'):
            agent = LeadResearchAgent(apify_actor=actor)
            body = json.dumps(agent._build_apify_input(self.icp(locations=[]), 5)).lower()
            self.assertNotIn('united states', body, actor)
            self.assertNotIn('vp sales', body, actor)
        with self.assertRaises(ValueError):
            LeadResearchAgent(apify_actor='apify/google-search-scraper')._build_apify_input(
                self.icp(job_titles=[], industries=[]), 5)

    def test_google_result_uses_structured_profile_data(self):
        # Shape and values of a real result; the title is a stale headline and the ellipsis is Google's.
        parsed = self.agent()._parse_google_result({
            'url': 'https://www.linkedin.com/in/someone',
            'title': 'Sam Example - Chief AI Transformation Officer (CAIO) & ...',
            'description': 'A long biography',
            'personalInfo': {'location': 'Jersey City', 'jobTitle': 'Founder & Principal', 'companyName': 'Example Advisory'},
        })
        self.assertEqual(parsed['job_title'], 'Founder & Principal')
        self.assertEqual(parsed['company_name'], 'Example Advisory')
        self.assertEqual(parsed['company_location'], 'Jersey City')
        self.assertEqual(parsed['buying_signals'], [])

    def test_google_result_without_structured_data_loses_the_ellipsis(self):
        parsed = self.agent()._parse_google_result({
            'url': 'https://www.linkedin.com/in/x', 'title': 'Sam Example - Head of Growth & ...'})
        self.assertEqual(parsed['job_title'], 'Head of Growth')

    def test_google_result_that_is_not_a_person_is_skipped(self):
        for title, url in (('Stripe | LinkedIn', 'https://www.linkedin.com/in/stripe'),
                           ('Sam Example - CEO', 'https://example.com/sam'),
                           ('Sam Example - Former CEO', 'https://www.linkedin.com/in/sam')):
            self.assertEqual(self.agent()._parse_google_result({'title': title, 'url': url}), {}, title)

    def test_provider_record_keeps_company_and_person_apart(self):
        parsed = self.agent()._parse_apify_item({
            'full_name': 'A B', 'city': 'Bedford', 'company_city': 'Warwick', 'company_country': 'United Kingdom',
            'company_phone': '+44 1', 'mobile_number': None,
        })
        self.assertEqual(parsed['company_location'], 'Warwick, United Kingdom')
        self.assertEqual(parsed['phone'], '')

    def test_evascrape_gets_the_minimum_it_accepts(self):
        # Found live: the actor refuses maxResults under 10.
        agent = LeadResearchAgent(apify_actor='evascrape/b2b-leads-finder')
        self.assertEqual(agent._build_apify_input(self.icp(), 5)['maxResults'], 10)

    def test_vp_titles_are_searched_in_every_common_spelling(self):
        agent = LeadResearchAgent(apify_actor='apify/google-search-scraper')
        queries = agent._build_apify_input(self.icp(job_titles=['VP Sales']), 5)['queries']
        for spelling in ('"VP Sales"', '"VP of Sales"', '"Vice President of Sales"'):
            self.assertIn(spelling, queries)

    def test_title_filter(self):
        self.assertTrue(title_matches_icp('Chief Technology Officer', ['CTO']))
        self.assertTrue(title_matches_icp('Vice President, Sales', ['VP Sales']))
        self.assertTrue(title_matches_icp('Senior VP of Sales', ['VP Sales']))
        self.assertFalse(title_matches_icp('Founder & Principal', ['CTO']))
        self.assertTrue(title_matches_icp('', ['CTO']))  # unknown: research decides, not the filter


class SearchToolTests(SimpleTestCase):
    def response(self, status=200, body=None):
        resp = mock.MagicMock(status_code=status, text='x')
        resp.json.return_value = body if body is not None else {}
        return resp

    def done(self):
        return self.response(200, {'data': {'status': 'SUCCEEDED', 'defaultDatasetId': 'd'}})

    def test_search_always_uses_the_google_actor(self):
        # The stored actor was evascrape: it failed on these inputs with "Add at least one filter" on every run.
        tool = ApifySearchTool(apify_token='t')
        start = self.response(201, {'data': {'id': 'r'}})
        items = self.response(200, [{'searchQuery': {'term': 'q'}, 'organicResults': [
            {'title': 'T', 'url': 'https://a', 'description': 'D', 'date': '2026-01-01'}]}])
        with mock.patch('requests.post', return_value=start) as post, \
                mock.patch('requests.get', side_effect=[self.done(), items]), mock.patch('time.sleep'):
            results = tool.search(['q'])
        self.assertIn(GOOGLE_SEARCH_ACTOR, post.call_args.args[0])
        self.assertEqual(results[0]['published_at'], '2026-01-01')
        self.assertEqual(tool.last_status, 'ok')

    def test_one_failed_poll_does_not_abandon_the_run(self):
        tool = ApifySearchTool(apify_token='t')
        start = self.response(201, {'data': {'id': 'r'}})
        items = self.response(200, [{'organicResults': [{'title': 'T', 'url': 'https://a'}]}])
        with mock.patch('requests.post', return_value=start), mock.patch('time.sleep'),                 mock.patch('requests.get', side_effect=[requests.Timeout('slow'), self.done(), items]):
            self.assertEqual(len(tool.search(['q'])), 1)
        self.assertEqual(tool.last_status, 'ok')

    def test_actor_failure_falls_back_to_news(self):
        tool = ApifySearchTool(apify_token='t')
        with mock.patch('requests.post', return_value=self.response(500)), mock.patch('time.sleep'), \
                mock.patch.object(tool, '_fallback_rss_search', return_value=[{'title': 'N'}]) as rss:
            self.assertEqual(tool.search(['q']), [{'title': 'N'}])
        rss.assert_called_once()
        self.assertEqual(tool.last_status, 'news_only')

    def test_network_failure_falls_back_to_news(self):
        tool = ApifySearchTool(apify_token='t')
        with mock.patch('requests.post', side_effect=requests.ConnectionError('x')), \
                mock.patch.object(tool, '_fallback_rss_search', return_value=[]):
            self.assertEqual(tool.search(['q']), [])
        self.assertEqual(tool.last_status, 'news_only')

    def test_news_feed_failure_reports_failed(self):
        tool = ApifySearchTool()
        with mock.patch('requests.get', return_value=self.response(503)):
            self.assertEqual(tool.search(['q']), [])
        self.assertEqual(tool.last_status, 'failed')

    def test_news_feed_keeps_its_publication_date(self):
        rss = (b'<rss><channel><item><title>Stripe raises</title><link>https://n/1</link>'
               b'<pubDate>Tue, 01 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>')
        resp = self.response(200)
        resp.content = rss
        with mock.patch('requests.get', return_value=resp):
            results = ApifySearchTool().search(['q'])
        self.assertEqual(results[0]['published_at'], 'Tue, 01 Sep 2026 10:00:00 GMT')


class ExtractorTests(SimpleTestCase):
    def test_private_addresses_are_refused(self):
        for host in ('localhost', '127.0.0.1', '169.254.169.254', '10.0.0.5'):
            self.assertFalse(is_public_host(host), host)
            page = WebpageExtractor().fetch_page(f'http://{host}/')
            self.assertFalse(page['success'])

    def test_redirect_to_a_private_address_is_refused(self):
        extractor = WebpageExtractor()
        redirect = mock.MagicMock(is_redirect=True, headers={'Location': 'http://169.254.169.254/latest/meta-data'})
        with mock.patch('ai_sdr_agent.agents.lead_research_tools.is_public_host', side_effect=lambda h: h == 'evil.example'), \
                mock.patch.object(extractor.session, 'get', return_value=redirect) as get:
            page = extractor.fetch_page('http://evil.example/')
        self.assertFalse(page['success'])
        get.assert_called_once()

    def test_pages_that_answer_200_but_say_nothing(self):
        self.assertEqual(classify_page('Just a moment...', ''), 'blocked')
        self.assertEqual(classify_page('Page not found', ''), 'not_found')
        self.assertEqual(classify_page('example.com', 'This domain is for sale'), 'parked')
        self.assertEqual(classify_page('Stripe', 'Payments infrastructure'), 'ok')

    def test_title_and_meta_description_are_kept(self):
        parsed = WebpageExtractor().parse_html(
            '<html><head><title>Acme</title><meta name="description" content="Acme makes rockets."></head>'
            '<body><header><h1>Rockets for all</h1></header><nav>Menu</nav><script>evil()</script></body></html>')
        self.assertEqual(parsed['title'], 'Acme')
        self.assertIn('Acme makes rockets.', parsed['content'])
        self.assertIn('Rockets for all', parsed['content'])
        self.assertNotIn('Menu', parsed['content'])
        self.assertNotIn('evil', parsed['content'])


class DuplicateResearchTests(LeadResearchTestCase):
    def test_colleagues_share_one_company_crawl(self):
        workflow = LeadResearchWorkflow()
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=self._make_mock_pages()) as crawl, \
                mock.patch.object(ApifySearchTool, 'search', return_value=[]):
            for name in ('Ana One', 'Ben Two'):
                workflow.execute_research({'id': 1, 'full_name': name, 'job_title': 'CTO', 'company_name': 'AcmeCloud',
                                           'company_domain': 'acmecloud.io'})
        self.assertEqual(crawl.call_count, 1)

    def test_a_running_lead_is_not_started_again_even_with_force(self):
        lead = SDRLead.objects.create(company_user=self.cu, company_name='X', raw_data={'research_status': 'running'})
        with mock.patch.object(LeadResearchAgent, 'research_lead') as research:
            self.assertEqual(research_lead_impl(lead.id, force=True)['status'], 'already_running')
        research.assert_not_called()

    def test_batch_with_repeated_ids_researches_once(self):
        lead = SDRLead.objects.create(company_user=self.cu, company_name='AcmeCloud', company_domain='acmecloud.io')
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=self._make_mock_pages()) as crawl, \
                mock.patch.object(ApifySearchTool, 'search', return_value=[]):
            result = research_leads_batch_impl([lead.id, lead.id])
        self.assertEqual(result['total'], 2)
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(crawl.call_count, 1)

    def test_task_uses_the_keys_saved_in_settings(self):
        from ai_sdr_agent.models import SDRAgentSettings
        SDRAgentSettings.objects.create(company_user=self.cu, apify_api_token='saved-token')
        lead = SDRLead.objects.create(company_user=self.cu, company_name='AcmeCloud', company_domain='acmecloud.io')
        with mock.patch.object(LeadResearchAgent, 'research_lead', return_value={}) as research, \
                mock.patch.object(LeadResearchAgent, '__init__', return_value=None) as init:
            research_lead_impl(lead.id)
        self.assertEqual(init.call_args.kwargs['apify_token'], 'saved-token')
        research.assert_called_once()

    def test_rerunning_research_does_not_repeat_news(self):
        lead = SDRLead.objects.create(company_user=self.cu, company_name='AcmeCloud', company_domain='acmecloud.io')
        agent = LeadResearchAgent(company=self.company)
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=self._make_mock_pages()), \
                mock.patch.object(ApifySearchTool, 'search', return_value=self._make_mock_snippets()):
            agent.research_lead(lead)
            agent.research_lead(lead)
        lead.refresh_from_db()
        urls = [n['url'] for n in lead.recent_news]
        self.assertEqual(len(urls), len(set(urls)))

    def test_undated_news_gets_no_invented_date(self):
        lead = SDRLead.objects.create(company_user=self.cu, company_name='AcmeCloud', company_domain='acmecloud.io')
        agent = LeadResearchAgent(company=self.company)
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=self._make_mock_pages()), \
                mock.patch.object(ApifySearchTool, 'search', return_value=self._make_mock_snippets()):
            agent.research_lead(lead)
        lead.refresh_from_db()
        self.assertEqual({n['date'] for n in lead.recent_news}, {''})

    def test_false_prospect_is_flagged_on_the_lead(self):
        lead = SDRLead.objects.create(company_user=self.cu, full_name='Nobody Here', job_title='CEO',
                                      company_name='AcmeCloud', company_domain='acmecloud.io')
        workflow = LeadResearchWorkflow()
        workflow.search_tool.last_status = 'ok'
        agent = LeadResearchAgent(company=self.company)
        agent.workflow = workflow
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=self._make_mock_pages()), \
                mock.patch.object(ApifySearchTool, 'search', return_value=[]):
            agent.research_lead(lead)
        lead.refresh_from_db()
        self.assertTrue(any(f.startswith('Research: ') for f in lead.data_quality_flags))

    def test_unverified_website_is_not_saved_on_the_lead(self):
        lead = SDRLead.objects.create(company_user=self.cu, company_name='Linear')
        analog = [{'page_type': 'homepage', 'url': 'https://www.analog.com/', 'title': 'Analog Devices',
                   'content': 'Analog Devices is a semiconductor company. ' * 5}]
        agent = LeadResearchAgent(company=self.company)
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=analog), \
                mock.patch.object(ApifySearchTool, 'search', return_value=[]):
            agent.research_lead(lead)
        lead.refresh_from_db()
        self.assertEqual(lead.company_website, '')

"""
Unit and integration tests for Independent Lead Research Workflow (Agent 1).
All external API calls (HTTP web scraping, Apify, Groq) are mocked for deterministic testing.
"""

import json
from unittest import mock
from django.test import TestCase
from django.utils import timezone

from ai_sdr_agent.agents.lead_research_agent import LeadResearchAgent
from ai_sdr_agent.agents.lead_research_tools import WebpageExtractor, ApifySearchTool
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

    def _make_mock_pages(self):
        return [
            {
                'page_type': 'homepage',
                'url': 'https://acmecloud.io',
                'content': 'AcmeCloud provides cloud-native data observability and automated pipelines for B2B enterprises.',
            },
            {
                'page_type': 'about',
                'url': 'https://acmecloud.io/about',
                'content': 'Founded in 2021, AcmeCloud is headquartered in San Francisco with over 150 team members.',
            },
            {
                'page_type': 'products',
                'url': 'https://acmecloud.io/products',
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
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=self._make_mock_pages()), \
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
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=self._make_mock_pages()), \
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
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=self._make_mock_pages()), \
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
        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=self._make_mock_pages()), \
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
        self.assertTrue(len(evidence) >= 4)
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
        expected_output = {
            "lead_id": str(lead.id),
            "research_status": "completed",
            "company_research": {
                "overview": "FinScale provides automated treasury management for SaaS companies.",
                "industry": "FinTech",
                "business_model": "B2B SaaS",
                "products_services": ["Treasury Router", "FX Hedge Engine"],
                "target_customers": ["Mid-market SaaS"],
                "value_proposition": "Optimize idle cash yields automatically.",
                "business_challenges": ["Multi-currency fragmentation"],
                "market_context": "North America and Europe"
            },
            "prospect_research": {
                "name": "David Kim",
                "designation": "VP Sales",
                "department": "Sales",
                "seniority": "VP",
                "responsibilities": ["GTM Strategy", "Enterprise Deals"],
                "decision_making_relevance": "Key decision maker for revenue tools"
            },
            "company_signals": [
                {
                    "type": "expansion",
                    "description": "Opened new London office to serve EMEA clients.",
                    "source_url": "https://finscale.co/news/london",
                    "published_at": "2026-02-15",
                    "campaign_relevance": "European market expansion",
                    "confidence": "high"
                }
            ],
            "campaign_relevance": {
                "relevant_opportunities": ["EMEA expansion outreach"],
                "potential_pain_points": ["Cross-border compliance"],
                "personalization_angles": ["Congratulate on London office"]
            },
            "evidence": [],
            "research_confidence": 90,
            "researched_at": timezone.now().isoformat()
        }
        mock_groq = self._make_mock_groq_response(expected_output)
        workflow = LeadResearchWorkflow(groq_client=mock_groq)

        with mock.patch.object(WebpageExtractor, 'extract_company_site', return_value=self._make_mock_pages()), \
             mock.patch.object(ApifySearchTool, 'search', return_value=[]):
            profile = workflow.execute_research(lead, campaign=self.campaign)

        self.assertEqual(profile['company_research']['industry'], 'FinTech')
        self.assertEqual(profile['company_research']['business_model'], 'B2B SaaS')
        self.assertEqual(len(profile['company_signals']), 1)
        self.assertEqual(profile['company_signals'][0]['type'], 'expansion')

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
            company_user=self.cu, company_name='PersistCloud', company_domain='persistcloud.com',
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


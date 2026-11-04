"""
Comprehensive Test Suite for Lead Enrichment Agent (Phases 1 - 9)
-----------------------------------------------------------------
Validates all required scenarios:
1. Lead with complete data (no redundant queries)
2. Lead missing only email
3. Lead missing multiple fields
4. Provider success & data extraction
5. Provider failure and fallback
6. Conflicting results from multiple sources (audit trail & arbitration)
7. Invalid or mismatched identity data
8. robots.txt compliance & crawl log
9. Rate-limit handling & domain throttling
10. Partial enrichment success
11. Repeated enrichment without unnecessary duplicate calls
12. End-to-end provenance and auditability
"""

from typing import Any, Dict, Optional, Set
from unittest import mock
from django.test import SimpleTestCase

from ai_sdr_agent.agents.enrichment_contract import (
    ConflictRecord,
    EnrichmentContract,
    FieldProvenance,
    VerificationStatus,
    can_overwrite_field,
    is_placeholder_or_empty,
)
from ai_sdr_agent.agents.contact_verifier import (
    verify_email,
    verify_phone,
    normalize_phone,
    check_domain_mx,
)
from ai_sdr_agent.agents.enrichment_validator import (
    clean_company_name,
    name_tokens_match,
    validate_identity,
    validate_and_merge_enrichment,
)
from ai_sdr_agent.agents.enrichment_web import (
    CompliantWebEnricher,
    DomainRateLimiter,
    RobotsCache,
)
from ai_sdr_agent.agents.enrichment_providers import (
    ApolloEnrichmentProvider,
    BaseEnrichmentProvider,
    HunterEnrichmentProvider,
    PublicWebEnrichmentProvider,
)
from ai_sdr_agent.agents.enrichment_waterfall import EnrichmentWaterfall
from ai_sdr_agent.agents.enrichment_agent import EnrichmentAgent


class MockEnrichmentProvider(BaseEnrichmentProvider):
    """Deterministic mock provider for unit/integration testing.

    Lives in the tests, not the production module (R5)."""

    def __init__(
        self,
        name: str = "mock",
        priority: int = 70,
        mock_data: Optional[Dict[str, Any]] = None,
        should_fail: bool = False,
        supported_fields: Optional[Set[str]] = None,
    ):
        self.name = name
        self.priority = priority
        self.mock_data = mock_data or {}
        self.should_fail = should_fail
        self.supported_fields = supported_fields or set(self.mock_data.keys())

    def is_configured(self) -> bool:
        return True

    def enrich(self, lead_data: Dict[str, Any], missing_fields: Set[str]) -> Dict[str, FieldProvenance]:
        if self.should_fail:
            raise RuntimeError(f"Mock provider {self.name} failed")
        results: Dict[str, FieldProvenance] = {}
        for f in missing_fields & self.supported_fields:
            if f in self.mock_data:
                results[f] = FieldProvenance(
                    field_name=f,
                    value=self.mock_data[f],
                    source=self.name,
                    confidence=80,
                    verification_status=VerificationStatus.UNVERIFIED,
                )
        return results


class CompleteLeadEnrichmentTests(SimpleTestCase):
    """Scenario 1: Lead with complete data does not invoke unnecessary provider queries."""

    def test_complete_lead_skips_queries(self):
        lead_dict = {
            "id": 1,
            "full_name": "Satya Nadella",
            "job_title": "CEO",
            "company_name": "Microsoft",
            "company_domain": "microsoft.com",
            "company_website": "https://microsoft.com",
            "email": "satya@microsoft.com",
            "phone": "+14258828080",
            "linkedin_url": "https://www.linkedin.com/in/satyanadella",
            "source": "manual",
        }
        mock_provider = MockEnrichmentProvider(name="apollo", priority=80)
        agent = EnrichmentAgent(providers=[mock_provider], check_dns=False)

        res = agent.enrich_lead(lead_dict)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["summary"]["providers_called"], [])
        self.assertEqual(res["summary"]["status"], "completed")


class MissingEmailEnrichmentTests(SimpleTestCase):
    """Scenario 2: Lead missing only an email queries only for email and stops."""

    def test_missing_email_resolved_and_stopped(self):
        lead_dict = {
            "id": 2,
            "full_name": "Satya Nadella",
            "job_title": "CEO",
            "company_name": "Microsoft",
            "company_domain": "microsoft.com",
            "company_website": "https://microsoft.com",
            "email": "",  # missing
            "phone": "+14258828080",
            "linkedin_url": "https://www.linkedin.com/in/satyanadella",
            "source": "manual",
        }
        provider1 = MockEnrichmentProvider(
            name="apollo",
            priority=80,
            mock_data={"email": "satya@microsoft.com"},
        )
        provider2 = MockEnrichmentProvider(
            name="hunter",
            priority=70,
            mock_data={"email": "snadella@microsoft.com"},
        )

        agent = EnrichmentAgent(providers=[provider1, provider2], check_dns=False)
        res = agent.enrich_lead(lead_dict)

        self.assertEqual(res["status"], "success")
        self.assertIn("apollo", res["summary"]["providers_called"])
        # Provider 2 should NOT be called because email was resolved by Apollo
        self.assertNotIn("hunter", res["summary"]["providers_called"])
        self.assertEqual(res["contract"]["fields"]["email"]["value"], "satya@microsoft.com")
        self.assertEqual(res["contract"]["fields"]["email"]["source"], "apollo")


class MultipleMissingFieldsTests(SimpleTestCase):
    """Scenario 3: Lead missing multiple fields resolved across providers."""

    def test_multiple_missing_fields_resolved(self):
        lead_dict = {
            "id": 3,
            "full_name": "Satya Nadella",
            "job_title": "CEO",
            "company_name": "Microsoft",
            "company_domain": "microsoft.com",
            "company_website": "",  # missing
            "email": "",            # missing
            "phone": "",            # missing
            "linkedin_url": "",     # missing
        }
        # Provider 1 supplies email and phone
        provider1 = MockEnrichmentProvider(
            name="provider1",
            priority=80,
            mock_data={"email": "satya@microsoft.com", "phone": "+14258828080"},
        )
        # Provider 2 supplies website and linkedin
        provider2 = MockEnrichmentProvider(
            name="provider2",
            priority=70,
            mock_data={"company_website": "https://microsoft.com", "linkedin_url": "https://www.linkedin.com/in/satyanadella"},
        )

        agent = EnrichmentAgent(providers=[provider1, provider2], check_dns=False)
        res = agent.enrich_lead(lead_dict)

        self.assertEqual(res["status"], "success")
        self.assertIn("provider1", res["summary"]["providers_called"])
        self.assertIn("provider2", res["summary"]["providers_called"])
        contract_fields = res["contract"]["fields"]
        self.assertEqual(contract_fields["email"]["value"], "satya@microsoft.com")
        self.assertEqual(contract_fields["phone"]["value"], "+14258828080")
        self.assertEqual(contract_fields["company_website"]["value"], "https://microsoft.com")
        self.assertEqual(contract_fields["linkedin_url"]["value"], "https://www.linkedin.com/in/satyanadella")


class ProviderFailureAndFallbackTests(SimpleTestCase):
    """Scenario 5: Primary provider fails, falls back to secondary provider."""

    def test_provider_failure_and_fallback(self):
        lead_dict = {
            "id": 4,
            "full_name": "Tim Cook",
            "job_title": "CEO",
            "company_name": "Apple",
            "company_domain": "apple.com",
            "email": "",
        }
        # Primary provider fails with exception
        provider1 = MockEnrichmentProvider(
            name="flaky_provider",
            priority=90,
            should_fail=True,
            supported_fields={"email"},
        )
        # Secondary provider succeeds
        provider2 = MockEnrichmentProvider(
            name="reliable_fallback",
            priority=70,
            mock_data={"email": "tcook@apple.com"},
        )

        agent = EnrichmentAgent(providers=[provider1, provider2], check_dns=False)
        res = agent.enrich_lead(lead_dict)

        self.assertEqual(res["status"], "success")
        self.assertIn("flaky_provider", res["summary"]["providers_called"])
        self.assertIn("reliable_fallback", res["summary"]["providers_called"])
        self.assertEqual(res["contract"]["fields"]["email"]["value"], "tcook@apple.com")
        self.assertEqual(res["contract"]["fields"]["email"]["source"], "reliable_fallback")

        # Verify attempt log captured error
        attempts = res["contract"]["provider_attempts"]
        self.assertTrue(any(a["provider"] == "flaky_provider" and a["status"] == "error" for a in attempts))


class ConflictArbitrationTests(SimpleTestCase):
    """Scenario 6: Conflicting results from multiple sources with audit trail."""

    def test_valid_status_cannot_be_overwritten_by_unverified(self):
        existing = FieldProvenance(
            field_name="email",
            value="tim@apple.com",
            source="crm_sync",
            confidence=95,
            verification_status=VerificationStatus.VALID,
        )
        incoming = FieldProvenance(
            field_name="email",
            value="tcook@apple.com",
            source="apollo",
            confidence=70,
            verification_status=VerificationStatus.UNVERIFIED,
        )
        decision = can_overwrite_field("email", existing, incoming)
        self.assertFalse(decision.should_overwrite)
        self.assertTrue(decision.is_conflict)

    def test_conflicts_recorded_in_contract(self):
        lead_dict = {
            "id": 5,
            "full_name": "Tim Cook",
            "company_name": "Apple",
            "company_domain": "apple.com",
            "email": "tcook@apple.com",  # unverified existing
        }
        contract = EnrichmentContract.from_lead(lead_dict)
        contract.fields["email"] = FieldProvenance(
            field_name="email",
            value="tcook@apple.com",
            source="existing",
            confidence=60,
            verification_status=VerificationStatus.UNVERIFIED,
        )

        # Incoming conflicting candidate from higher-priority provider
        candidates = {
            "email": FieldProvenance(
                field_name="email",
                value="tim.cook@apple.com",
                source="apollo",
                confidence=85,
                verification_status=VerificationStatus.VALID,
                verification_details={"company_domain": "apple.com"},
            )
        }

        updated_contract, summary = validate_and_merge_enrichment(
            contract=contract,
            candidate_fields=candidates,
            source_name="apollo",
            check_dns=False,
        )

        # Higher verification status (VALID) overwrites UNVERIFIED
        self.assertEqual(updated_contract.fields["email"].value, "tim.cook@apple.com")
        self.assertEqual(len(updated_contract.conflicts), 1)
        conflict = updated_contract.conflicts[0]
        self.assertEqual(conflict.existing_value, "tcook@apple.com")
        self.assertEqual(conflict.conflicting_value, "tim.cook@apple.com")
        self.assertEqual(conflict.resolution, "overwritten")


class IdentityResolutionTests(SimpleTestCase):
    """Scenario 7: Invalid or mismatched identity data detection."""

    def test_reject_name_mismatch(self):
        lead_state = {"full_name": "Satya Nadella", "company_name": "Microsoft"}
        candidate = {"full_name": "Bill Gates", "company_name": "Microsoft"}
        is_match, score, reasons = validate_identity(lead_state, candidate)
        self.assertFalse(is_match)
        self.assertTrue(any("Name mismatch" in r for r in reasons))

    def test_reject_company_mismatch(self):
        lead_state = {"full_name": "Satya Nadella", "company_name": "Microsoft", "company_domain": "microsoft.com"}
        candidate = {"full_name": "Satya Nadella", "company_name": "Google LLC", "company_domain": "google.com"}
        is_match, score, reasons = validate_identity(lead_state, candidate)
        self.assertFalse(is_match)
        self.assertTrue(any("Company mismatch" in r or "domain mismatch" in r for r in reasons))

    def test_reject_former_role(self):
        lead_state = {"full_name": "Satya Nadella", "company_name": "Microsoft"}
        candidate = {"full_name": "Satya Nadella", "company_name": "Microsoft", "job_title": "Former VP of Sales"}
        is_match, score, reasons = validate_identity(lead_state, candidate)
        self.assertFalse(is_match)
        self.assertTrue(any("former role" in r for r in reasons))


class RobotsTxtComplianceTests(SimpleTestCase):
    """Scenario 8: robots.txt disallows page crawling."""

    def test_robots_txt_disallow_respected(self):
        robots_cache = RobotsCache()

        # Mock robots.txt allowing root but disallowing /team
        with mock.patch("requests.get") as mock_get, \
             mock.patch("ai_sdr_agent.agents.enrichment_web.is_public_host", return_value=True):
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "User-agent: *\nDisallow: /team\n"
            mock_get.return_value = mock_resp

            allowed, reason = robots_cache.can_fetch("https://example.com/team")
            self.assertFalse(allowed)
            self.assertIn("Disallowed", reason)

            allowed_home, _ = robots_cache.can_fetch("https://example.com/")
            self.assertTrue(allowed_home)

    def test_compliant_enricher_logs_disallowance(self):
        robots_cache = RobotsCache()
        enricher = CompliantWebEnricher(robots_cache=robots_cache)

        with mock.patch.object(robots_cache, "can_fetch", return_value=(False, "Disallowed by robots.txt")):
            enriched, crawl_log = enricher.enrich_from_website(
                domain_or_url="https://securecorp.com",
                lead_name="Alice Smith",
                missing_fields={"email"},
            )
            self.assertEqual(len(enriched), 0)
            self.assertTrue(any(log["status"] == "robots_disallowed" for log in crawl_log))


class DomainRateLimiterTests(SimpleTestCase):
    """Scenario 9: Domain-level rate limiting throttles requests."""

    def test_rate_limiter_throttles(self):
        limiter = DomainRateLimiter(min_interval_seconds=0.05)
        limiter.wait_for_domain("example.com")
        start = limiter._last_access["example.com"]
        limiter.wait_for_domain("example.com")
        second = limiter._last_access["example.com"]
        self.assertGreaterEqual(second - start, 0.04)


class PartialSuccessEnrichmentTests(SimpleTestCase):
    """Scenario 10: Partial enrichment success when some fields cannot be found."""

    def test_partial_enrichment_status(self):
        lead_dict = {
            "id": 6,
            "full_name": "Satya Nadella",
            "company_name": "Microsoft",
            "company_domain": "microsoft.com",
            "email": "",  # will be resolved
            "phone": "",  # remains unresolvable
        }
        # Provider only knows email
        provider = MockEnrichmentProvider(
            name="email_only_provider",
            priority=80,
            mock_data={"email": "satya@microsoft.com"},
            supported_fields={"email"},
        )
        agent = EnrichmentAgent(providers=[provider], check_dns=False)
        res = agent.enrich_lead(lead_dict)

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["enrichment_status"], "partial")
        self.assertIn("email", res["summary"]["resolved_fields"])
        self.assertIn("phone", res["summary"]["unresolved_fields"])


class RepeatedEnrichmentTests(SimpleTestCase):
    """Scenario 11: Repeated enrichment without redundant queries (idempotent)."""

    def test_repeated_enrichment_does_not_repeat_resolved(self):
        lead_dict = {
            "id": 7,
            "full_name": "Satya Nadella",
            "company_name": "Microsoft",
            "company_domain": "microsoft.com",
            "email": "",
        }
        provider = MockEnrichmentProvider(
            name="provider",
            priority=80,
            mock_data={"email": "satya@microsoft.com"},
            supported_fields={"email"},
        )
        agent = EnrichmentAgent(providers=[provider], check_dns=False)

        # Run 1
        res1 = agent.enrich_lead(lead_dict)
        self.assertEqual(res1["summary"]["providers_called"], ["provider"])

        # Run 2 on the updated lead contract
        updated_lead = {
            "id": 7,
            "full_name": "Satya Nadella",
            "company_name": "Microsoft",
            "company_domain": "microsoft.com",
            "email": "satya@microsoft.com",
            "raw_data": {"enrichment": res1["contract"]},
        }
        res2 = agent.enrich_lead(updated_lead)
        # Email is already resolved; provider should NOT be called again
        self.assertEqual(res2["summary"]["providers_called"], [])


class ContactVerifierUnitTests(SimpleTestCase):
    """Scenario 12: Contact verification layer."""

    def test_verify_email_syntax_and_status(self):
        # Fake email
        res_fake = verify_email("test@example.com", check_dns=False)
        self.assertEqual(res_fake["status"], VerificationStatus.INVALID)

        # Disposable email
        res_disp = verify_email("john@mailinator.com", check_dns=False)
        self.assertEqual(res_disp["status"], VerificationStatus.INVALID)
        self.assertTrue(res_disp["is_disposable"])

        # Personal free email
        res_free = verify_email("john@gmail.com", check_dns=False)
        self.assertEqual(res_free["status"], VerificationStatus.RISKY)
        self.assertTrue(res_free["is_free"])

        # Valid business email format
        res_bus = verify_email("satya@microsoft.com", company_domain="microsoft.com", check_dns=False)
        self.assertEqual(res_bus["status"], VerificationStatus.UNVERIFIED)
        self.assertTrue(res_bus["matches_company_domain"])

    def test_verify_phone_normalization(self):
        norm = normalize_phone("(415) 555-2671")
        self.assertEqual(norm, "+14155552671")

        res = verify_phone("(415) 555-2671")
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["status"], VerificationStatus.VALID)

        # Invalid short phone
        res_short = verify_phone("123")
        self.assertFalse(res_short["is_valid"])
        self.assertEqual(res_short["status"], VerificationStatus.INVALID)


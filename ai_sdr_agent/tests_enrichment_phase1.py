"""
Unit tests for Phase 1: Architecture & Data Contract
"""
from django.test import SimpleTestCase
from ai_sdr_agent.agents.enrichment_contract import (
    EnrichmentContract,
    FieldProvenance,
    VerificationStatus,
    OverwriteDecision,
    can_overwrite_field,
    is_placeholder_or_empty,
    ENRICHABLE_FIELDS,
)


class EnrichmentContractTests(SimpleTestCase):
    def test_is_placeholder_or_empty(self):
        self.assertTrue(is_placeholder_or_empty("full_name", ""))
        self.assertTrue(is_placeholder_or_empty("full_name", "John Doe"))
        self.assertTrue(is_placeholder_or_empty("full_name", "test user"))
        self.assertFalse(is_placeholder_or_empty("full_name", "Satya Nadella"))

        self.assertTrue(is_placeholder_or_empty("email", "test@test.com"))
        self.assertTrue(is_placeholder_or_empty("email", "noreply@company.com"))
        self.assertFalse(is_placeholder_or_empty("email", "satya@microsoft.com"))

        self.assertTrue(is_placeholder_or_empty("company_name", "Acme Corp"))
        self.assertFalse(is_placeholder_or_empty("company_name", "Microsoft"))

    def test_contract_from_lead_dict(self):
        lead_dict = {
            "id": 101,
            "full_name": "Satya Nadella",
            "job_title": "CEO",
            "company_name": "Microsoft",
            "email": "",
            "phone": None,
            "linkedin_url": "https://www.linkedin.com/in/satyanadella",
            "source": "manual",
        }
        contract = EnrichmentContract.from_lead(lead_dict)
        self.assertEqual(contract.lead_id, 101)
        self.assertIn("full_name", contract.fields)
        self.assertEqual(contract.fields["full_name"].value, "Satya Nadella")
        self.assertNotIn("email", contract.fields)

        missing = contract.get_missing_fields()
        self.assertIn("email", missing)
        self.assertIn("phone", missing)
        self.assertIn("company_domain", missing)
        self.assertNotIn("full_name", missing)

    def test_can_overwrite_missing_or_placeholder(self):
        existing = FieldProvenance(
            field_name="email",
            value="noreply@example.com",
            verification_status=VerificationStatus.INVALID,
        )
        incoming = FieldProvenance(
            field_name="email",
            value="satya@microsoft.com",
            source="apollo",
            confidence=85,
            verification_status=VerificationStatus.VALID,
        )
        decision = can_overwrite_field("email", existing, incoming)
        self.assertTrue(decision.should_overwrite)

    def test_never_overwrite_valid_with_unverified(self):
        existing = FieldProvenance(
            field_name="email",
            value="satya@microsoft.com",
            source="crm_sync",
            confidence=95,
            verification_status=VerificationStatus.VALID,
        )
        incoming = FieldProvenance(
            field_name="email",
            value="snadella@microsoft.com",
            source="public_web",
            confidence=60,
            verification_status=VerificationStatus.UNVERIFIED,
        )
        decision = can_overwrite_field("email", existing, incoming)
        self.assertFalse(decision.should_overwrite)
        self.assertTrue(decision.is_conflict)

    def test_upgrade_unverified_to_valid(self):
        existing = FieldProvenance(
            field_name="email",
            value="satya@microsoft.com",
            source="apollo",
            confidence=70,
            verification_status=VerificationStatus.UNVERIFIED,
        )
        incoming = FieldProvenance(
            field_name="email",
            value="satya@microsoft.com",
            source="email_verifier",
            confidence=95,
            verification_status=VerificationStatus.VALID,
        )
        decision = can_overwrite_field("email", existing, incoming)
        self.assertTrue(decision.should_overwrite)
        self.assertFalse(decision.is_conflict)

    def test_contract_serialization_roundtrip(self):
        contract = EnrichmentContract(lead_id=42, status="completed")
        contract.fields["email"] = FieldProvenance(
            field_name="email",
            value="alex@domain.com",
            source="hunter",
            confidence=80,
            verification_status=VerificationStatus.VALID,
        )
        data = contract.to_dict()
        self.assertEqual(data["lead_id"], 42)
        self.assertEqual(data["fields"]["email"]["verification_status"], "valid")

        # Rebuild from lead raw_data containing this dict
        lead_mock = {"id": 42, "raw_data": {"enrichment": data}}
        restored = EnrichmentContract.from_lead(lead_mock)
        self.assertEqual(restored.lead_id, 42)
        self.assertEqual(restored.fields["email"].value, "alex@domain.com")
        self.assertEqual(restored.fields["email"].verification_status, VerificationStatus.VALID)


"""
Enrichment Providers
--------------------
Modular, interchangeable provider adapters for lead enrichment.
Implements the BaseEnrichmentProvider interface:
  - ApolloEnrichmentProvider
  - HunterEnrichmentProvider
  - PublicWebEnrichmentProvider
"""

import abc
import logging
import time
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

import requests

from ai_sdr_agent.agents.enrichment_contract import (
    FieldProvenance,
    VerificationStatus,
)
from ai_sdr_agent.agents.enrichment_web import CompliantWebEnricher

logger = logging.getLogger(__name__)


class BaseEnrichmentProvider(abc.ABC):
    """Abstract base class for all enrichment providers."""

    name: str = "base"
    priority: int = 50
    supported_fields: Set[str] = set()

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """Return True if credentials or prerequisites are available."""
        pass

    @abc.abstractmethod
    def enrich(
        self,
        lead_data: Dict[str, Any],
        missing_fields: Set[str],
    ) -> Dict[str, FieldProvenance]:
        """
        Query provider for missing fields.
        Returns a dict mapping field_name -> FieldProvenance.
        """
        pass


class ApolloEnrichmentProvider(BaseEnrichmentProvider):
    """
    Enrichment adapter for Apollo.io people & organization endpoints.
    Resolves work email, phone, personal email, title, domain, and linkedin.
    """

    name = "apollo"
    priority = 80
    supported_fields = {
        "email",
        "personal_email",
        "phone",
        "job_title",
        "company_name",
        "company_domain",
        "company_website",
        "linkedin_url",
        "seniority_level",
        "department",
    }

    def __init__(self, api_key: Optional[str] = None, timeout: float = 8.0):
        self.api_key = (api_key or "").strip()
        self.timeout = timeout
        self.base_url = "https://api.apollo.io/v1"

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def enrich(
        self,
        lead_data: Dict[str, Any],
        missing_fields: Set[str],
    ) -> Dict[str, FieldProvenance]:
        if not self.is_configured():
            return {}

        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": self.api_key,
        }

        # Build payload for Apollo people match
        first_name = lead_data.get("first_name") or ""
        last_name = lead_data.get("last_name") or ""
        full_name = lead_data.get("full_name") or ""
        if not (first_name and last_name) and full_name:
            parts = full_name.split()
            first_name = parts[0]
            last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

        payload: Dict[str, Any] = {
            "first_name": first_name,
            "last_name": last_name,
            "name": full_name or f"{first_name} {last_name}".strip(),
            "organization_name": lead_data.get("company_name", ""),
            "domain": lead_data.get("company_domain", ""),
        }

        if lead_data.get("linkedin_url"):
            payload["linkedin_url"] = lead_data.get("linkedin_url")

        results: Dict[str, FieldProvenance] = {}
        try:
            resp = requests.post(
                f"{self.base_url}/people/match",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            if resp.status_code == 429:
                logger.warning("Apollo API rate limited (429)")
                raise requests.RequestException("Apollo rate limited (429)")
            if resp.status_code >= 400:
                logger.info("Apollo people/match returned %d: %s", resp.status_code, resp.text[:200])
                return results

            data = resp.json()
            person = data.get("person") or {}
            if not person:
                return results

            # Map returned person data to FieldProvenance
            # Work email
            email_val = (person.get("email") or "").strip()
            if email_val and "email" in missing_fields:
                ext_status = person.get("email_status")
                is_ext_valid = ext_status == "verified"
                results["email"] = FieldProvenance(
                    field_name="email",
                    value=email_val.lower(),
                    source="apollo",
                    confidence=85 if is_ext_valid else 70,
                    verification_status=VerificationStatus.VALID if is_ext_valid else VerificationStatus.UNVERIFIED,
                    verification_details={"apollo_email_status": ext_status},
                )

            # Personal email
            personal_email = (person.get("personal_email") or "").strip()
            if personal_email and "personal_email" in missing_fields:
                results["personal_email"] = FieldProvenance(
                    field_name="personal_email",
                    value=personal_email.lower(),
                    source="apollo",
                    confidence=70,
                    verification_status=VerificationStatus.UNVERIFIED,
                )

            # Phone / phone numbers
            phone_val = (
                person.get("sanitized_phone")
                or person.get("phone_number")
                or (person.get("phone_numbers", [{}])[0].get("raw_number") if person.get("phone_numbers") else None)
            )
            if phone_val and "phone" in missing_fields:
                results["phone"] = FieldProvenance(
                    field_name="phone",
                    value=str(phone_val).strip(),
                    source="apollo",
                    confidence=75,
                    verification_status=VerificationStatus.UNVERIFIED,
                )

            # LinkedIn URL
            li_url = (person.get("linkedin_url") or "").strip()
            if li_url and "linkedin_url" in missing_fields:
                results["linkedin_url"] = FieldProvenance(
                    field_name="linkedin_url",
                    value=li_url,
                    source="apollo",
                    confidence=90,
                    verification_status=VerificationStatus.VALID,
                )

            # Job title
            title_val = (person.get("title") or "").strip()
            if title_val and "job_title" in missing_fields:
                results["job_title"] = FieldProvenance(
                    field_name="job_title",
                    value=title_val,
                    source="apollo",
                    confidence=85,
                    verification_status=VerificationStatus.UNVERIFIED,
                )

            # Company details
            org = person.get("organization") or {}
            domain_val = (org.get("primary_domain") or org.get("domain") or "").strip()
            if domain_val and "company_domain" in missing_fields:
                results["company_domain"] = FieldProvenance(
                    field_name="company_domain",
                    value=domain_val.lower(),
                    source="apollo",
                    confidence=90,
                    verification_status=VerificationStatus.VALID,
                )

            website_val = (org.get("website_url") or "").strip()
            if website_val and "company_website" in missing_fields:
                results["company_website"] = FieldProvenance(
                    field_name="company_website",
                    value=website_val,
                    source="apollo",
                    confidence=90,
                    verification_status=VerificationStatus.VALID,
                )

        except Exception as exc:
            logger.warning("ApolloEnrichmentProvider query failed: %s", exc)

        return results


class HunterEnrichmentProvider(BaseEnrichmentProvider):
    """
    Enrichment adapter for Hunter.io (email-finder).
    Finds verified professional emails given name and company domain.
    """

    name = "hunter"
    priority = 75
    supported_fields = {"email"}

    def __init__(self, api_key: Optional[str] = None, timeout: float = 6.0):
        self.api_key = (api_key or "").strip()
        self.timeout = timeout
        self.base_url = "https://api.hunter.io/v2"

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def enrich(
        self,
        lead_data: Dict[str, Any],
        missing_fields: Set[str],
    ) -> Dict[str, FieldProvenance]:
        if not self.is_configured() or "email" not in missing_fields:
            return {}

        domain = lead_data.get("company_domain", "")
        full_name = lead_data.get("full_name", "")
        first_name = lead_data.get("first_name", "")
        last_name = lead_data.get("last_name", "")

        if not domain or not (full_name or (first_name and last_name)):
            return {}

        params = {
            "api_key": self.api_key,
            "domain": domain,
            "full_name": full_name or f"{first_name} {last_name}".strip(),
        }

        results: Dict[str, FieldProvenance] = {}
        try:
            resp = requests.get(
                f"{self.base_url}/email-finder",
                params=params,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json().get("data") or {}
                found_email = data.get("email")
                score = data.get("score") or 60
                verification = data.get("verification") or {}
                is_valid = verification.get("status") == "valid"

                if found_email:
                    results["email"] = FieldProvenance(
                        field_name="email",
                        value=found_email.lower(),
                        source="hunter",
                        confidence=min(100, int(score)),
                        verification_status=VerificationStatus.VALID if is_valid else VerificationStatus.UNVERIFIED,
                        verification_details=verification,
                    )
        except Exception as exc:
            logger.warning("HunterEnrichmentProvider query failed: %s", exc)

        return results


class PublicWebEnrichmentProvider(BaseEnrichmentProvider):
    """
    Compliant public web crawl provider.
    Runs when third-party providers cannot resolve target fields.
    """

    name = "public_web"
    priority = 65
    supported_fields = {
        "email",
        "phone",
        "company_website",
        "company_domain",
        "linkedin_url",
        "other_profiles",
    }

    def __init__(self, web_enricher: Optional[CompliantWebEnricher] = None):
        self.web_enricher = web_enricher or CompliantWebEnricher()

    def is_configured(self) -> bool:
        return True  # Built-in public crawler requires no external API keys

    def enrich(
        self,
        lead_data: Dict[str, Any],
        missing_fields: Set[str],
    ) -> Dict[str, FieldProvenance]:
        domain = lead_data.get("company_website") or lead_data.get("company_domain")
        if not domain:
            return {}

        lead_name = lead_data.get("full_name") or f"{lead_data.get('first_name', '')} {lead_data.get('last_name', '')}".strip()

        enriched, _ = self.web_enricher.enrich_from_website(
            domain_or_url=domain,
            lead_name=lead_name,
            missing_fields=missing_fields,
            max_pages=5,
        )
        return enriched


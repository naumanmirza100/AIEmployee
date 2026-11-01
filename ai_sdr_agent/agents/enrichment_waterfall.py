"""
Enrichment Waterfall Pipeline
-----------------------------
Executes field-aware, prioritized waterfall enrichment across multiple providers.
Guarantees:
1. Queries only providers needed for currently missing or insufficiently verified fields.
2. Validates and verifies each candidate result before accepting it.
3. Halts subsequent queries for a field once that field is resolved with high confidence.
4. Prevents duplicate provider calls within the same run.
5. Records detailed provider attempts, latency, and outcomes in an audit trail.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from ai_sdr_agent.agents.enrichment_contract import (
    EnrichmentContract,
    FieldProvenance,
    ProviderAttempt,
    VerificationStatus,
)
from ai_sdr_agent.agents.enrichment_providers import BaseEnrichmentProvider
from ai_sdr_agent.agents.enrichment_validator import validate_and_merge_enrichment

logger = logging.getLogger(__name__)


class EnrichmentWaterfall:
    """
    Field-aware waterfall coordinator.
    Sorts providers by priority and steps through them sequentially,
    dropping resolved fields at each stage to avoid redundant API queries.
    """

    def __init__(self, providers: Optional[List[BaseEnrichmentProvider]] = None):
        # Sort providers by priority descending
        self.providers = sorted(
            [p for p in (providers or []) if p.is_configured()],
            key=lambda p: p.priority,
            reverse=True,
        )

    def create_plan(self, missing_fields: Set[str]) -> List[Dict[str, Any]]:
        """
        Builds an enrichment plan outlining which providers will be consulted
        for which missing fields.
        """
        plan = []
        covered = set()
        for p in self.providers:
            relevant = (p.supported_fields & missing_fields) - covered
            if relevant:
                plan.append({
                    "provider": p.name,
                    "priority": p.priority,
                    "target_fields": sorted(list(relevant)),
                })
        return plan

    def execute_waterfall(
        self,
        contract: EnrichmentContract,
        lead_summary: Dict[str, Any],
        required_fields: Optional[Set[str]] = None,
        check_dns: bool = True,
    ) -> Tuple[EnrichmentContract, Dict[str, Any]]:
        """
        Runs the waterfall for the given lead.

        Returns:
            (updated_contract, execution_summary)
        """
        missing = set(contract.get_missing_fields(required_fields))
        if not missing:
            logger.info("Waterfall: No missing fields for lead %s. Skipping queries.", contract.lead_id)
            return contract, {
                "status": "completed",
                "resolved_fields": [],
                "unresolved_fields": [],
                "providers_called": [],
                "attempts": [],
            }

        providers_called: List[str] = []
        attempts: List[ProviderAttempt] = []
        resolved_fields: Set[str] = set()

        for provider in self.providers:
            # Check if this provider can address any remaining missing fields
            actionable_fields = provider.supported_fields & missing
            if not actionable_fields:
                continue

            providers_called.append(provider.name)
            start_t = time.monotonic()
            status = "success"
            err_msg = None
            candidate_fields: Dict[str, FieldProvenance] = {}

            try:
                candidate_fields = provider.enrich(lead_summary, actionable_fields)
                if not candidate_fields:
                    status = "not_found"
            except Exception as exc:
                status = "error"
                err_msg = str(exc)
                logger.warning("Waterfall provider %s failed: %s", provider.name, exc)

            latency_ms = int((time.monotonic() - start_t) * 1000)
            attempt = ProviderAttempt(
                provider=provider.name,
                target_field=",".join(sorted(actionable_fields)),
                status=status,
                latency_ms=latency_ms,
                message=err_msg,
            )
            attempts.append(attempt)
            contract.provider_attempts.append(attempt)

            # If provider returned data, validate and merge
            if candidate_fields:
                contract, merge_summary = validate_and_merge_enrichment(
                    contract=contract,
                    candidate_fields=candidate_fields,
                    source_name=provider.name,
                    check_dns=check_dns,
                )

                # Check which fields were resolved and can be dropped from missing list
                for f in merge_summary.get("updated_fields", []):
                    prov = contract.fields.get(f)
                    if prov and prov.verification_status in (VerificationStatus.VALID, VerificationStatus.RISKY):
                        resolved_fields.add(f)
                        missing.discard(f)
                    elif prov and prov.confidence >= 80:
                        resolved_fields.add(f)
                        missing.discard(f)

                # Update lead summary with newly merged fields for downstream providers
                for f in merge_summary.get("updated_fields", []):
                    if f in contract.fields:
                        lead_summary[f] = contract.fields[f].value

            # Early exit: all missing fields resolved!
            if not missing:
                logger.info("Waterfall: All target fields resolved early after querying %s.", provider.name)
                break

        final_unresolved = list(contract.get_missing_fields(required_fields))
        return contract, {
            "status": "completed" if not final_unresolved else ("partial" if resolved_fields else "no_data"),
            "resolved_fields": sorted(list(resolved_fields)),
            "unresolved_fields": final_unresolved,
            "providers_called": providers_called,
            "attempts": [a.to_dict() for a in attempts],
        }


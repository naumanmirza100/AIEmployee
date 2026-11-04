"""
Enrichment Agent Orchestrator
-----------------------------
Autonomous, provider-agnostic orchestrator responsible for lead data enrichment.
Finds, completes, validates, and verifies missing lead and contact information
using prioritized providers and compliant web sources.

Provides single entry points:
  - enrich_lead(lead_or_id, force=False)
  - enrich_leads_batch(lead_ids, force=False)
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Union

from django.db import transaction

from ai_sdr_agent.agents.contact_verifier import verify_email, verify_phone
from ai_sdr_agent.agents.enrichment_contract import (
    EnrichmentContract,
    FieldProvenance,
    VerificationStatus,
)
from ai_sdr_agent.agents.enrichment_providers import (
    ApolloEnrichmentProvider,
    BaseEnrichmentProvider,
    HunterEnrichmentProvider,
    PublicWebEnrichmentProvider,
)
from ai_sdr_agent.agents.enrichment_waterfall import EnrichmentWaterfall
from ai_sdr_agent.agents.lead_validator import validate_lead

logger = logging.getLogger(__name__)


class EnrichmentAgent:
    """
    Independent, provider-agnostic agent orchestrating lead enrichment workflows.
    """

    def __init__(
        self,
        company: Any = None,
        company_user: Any = None,
        apollo_api_key: Optional[str] = None,
        hunter_api_key: Optional[str] = None,
        providers: Optional[List[BaseEnrichmentProvider]] = None,
        check_dns: bool = True,
    ):
        self.company = company
        self.company_user = company_user
        self.check_dns = check_dns

        if providers is not None:
            self.providers = providers
        else:
            # Build default provider suite based on available credentials
            prov_list: List[BaseEnrichmentProvider] = []
            if apollo_api_key:
                prov_list.append(ApolloEnrichmentProvider(api_key=apollo_api_key))
            if hunter_api_key:
                prov_list.append(HunterEnrichmentProvider(api_key=hunter_api_key))
            # Always include compliant public web discovery
            prov_list.append(PublicWebEnrichmentProvider())
            self.providers = prov_list

        self.waterfall = EnrichmentWaterfall(providers=self.providers)

    def plan_enrichment(self, lead_dict_or_contract: Union[Dict[str, Any], EnrichmentContract]) -> Dict[str, Any]:
        """
        Inspects missing fields and generates a prioritized execution plan.
        """
        if isinstance(lead_dict_or_contract, EnrichmentContract):
            contract = lead_dict_or_contract
        else:
            contract = EnrichmentContract.from_lead(lead_dict_or_contract)

        missing = set(contract.get_missing_fields())
        plan = self.waterfall.create_plan(missing)
        return {
            "lead_id": contract.lead_id,
            "missing_fields": sorted(list(missing)),
            "plan_steps": plan,
        }

    def enrich_lead(
        self,
        lead_or_id: Union[int, str, Any, Dict[str, Any]],
        force: bool = False,
        required_fields: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """
        Single entry point for enriching an individual lead.
        Accepts an SDRLead instance, an integer ID, or a dictionary.
        Updates model non-destructively and returns structured enrichment results.
        """
        from ai_sdr_agent.models import SDRLead

        lead_obj = None
        lead_dict: Dict[str, Any] = {}

        if isinstance(lead_or_id, (int, str)) and str(lead_or_id).isdigit():
            lead_obj = SDRLead.all_objects.filter(pk=int(lead_or_id)).first()
            if not lead_obj:
                raise ValueError(f"SDRLead with id {lead_or_id} not found")
        elif hasattr(lead_or_id, "pk"):
            lead_obj = lead_or_id
        elif isinstance(lead_or_id, dict):
            lead_dict = lead_or_id

        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc).isoformat()

        # If lead model instance exists, initialize contract from it
        if lead_obj:
            lead_dict = {
                "id": lead_obj.id,
                "full_name": lead_obj.full_name or lead_obj.display_name,
                "first_name": lead_obj.first_name,
                "last_name": lead_obj.last_name,
                "email": lead_obj.email,
                "phone": lead_obj.phone,
                "job_title": lead_obj.job_title,
                "company_name": lead_obj.company_name,
                "company_domain": lead_obj.company_domain,
                "company_website": lead_obj.company_website,
                "linkedin_url": lead_obj.linkedin_url,
                "source": lead_obj.source,
                "raw_data": lead_obj.raw_data if isinstance(lead_obj.raw_data, dict) else {},
            }

        contract = EnrichmentContract.from_lead(lead_dict)
        contract.last_run_id = run_id
        contract.status = "running"

        # Record start state in DB if model
        if lead_obj:
            if not isinstance(lead_obj.raw_data, dict):
                lead_obj.raw_data = {}
            lead_obj.raw_data["enrichment"] = contract.to_dict()
            lead_obj.save(update_fields=["raw_data", "updated_at"])

        try:
            # Snapshot previous field values for audit history
            prev_snapshot = {k: v.value for k, v in contract.fields.items()}

            # Run Waterfall
            contract, wf_summary = self.waterfall.execute_waterfall(
                contract=contract,
                lead_summary=lead_dict,
                required_fields=required_fields,
                check_dns=self.check_dns,
            )

            # Record change history
            changes: Dict[str, Any] = {}
            for k, prov in contract.fields.items():
                old_val = prev_snapshot.get(k)
                if old_val != prov.value:
                    changes[k] = {
                        "old": old_val,
                        "new": prov.value,
                        "source": prov.source,
                        "confidence": prov.confidence,
                        "verification_status": (
                            prov.verification_status.value
                            if isinstance(prov.verification_status, VerificationStatus)
                            else prov.verification_status
                        ),
                    }

            run_record = {
                "run_id": run_id,
                "timestamp": started_at,
                "status": wf_summary.get("status"),
                "providers_called": wf_summary.get("providers_called"),
                "fields_updated": list(changes.keys()),
                "changes": changes,
                "conflicts_count": len(contract.conflicts),
            }
            contract.history.append(run_record)
            contract.last_enriched_at = datetime.now(timezone.utc).isoformat()
            contract.status = wf_summary.get("status", "completed")

            # If lead_obj is present, update model fields non-destructively
            if lead_obj:
                update_fields = ["raw_data", "updated_at"]
                lead_obj.raw_data["enrichment"] = contract.to_dict()

                # Sync primary model fields
                if "email" in contract.fields and contract.fields["email"].value:
                    lead_obj.email = str(contract.fields["email"].value)[:255]
                    update_fields.append("email")
                if "phone" in contract.fields and contract.fields["phone"].value:
                    lead_obj.phone = str(contract.fields["phone"].value)[:100]
                    update_fields.append("phone")
                if "job_title" in contract.fields and contract.fields["job_title"].value:
                    lead_obj.job_title = str(contract.fields["job_title"].value)[:255]
                    update_fields.append("job_title")
                if "company_domain" in contract.fields and contract.fields["company_domain"].value:
                    lead_obj.company_domain = str(contract.fields["company_domain"].value)[:255]
                    update_fields.append("company_domain")
                if "company_website" in contract.fields and contract.fields["company_website"].value:
                    lead_obj.company_website = str(contract.fields["company_website"].value)[:500]
                    update_fields.append("company_website")
                if "linkedin_url" in contract.fields and contract.fields["linkedin_url"].value:
                    lead_obj.linkedin_url = str(contract.fields["linkedin_url"].value)[:500]
                    update_fields.append("linkedin_url")

                # Re-validate overall lead quality
                current_dict = {
                    "full_name": lead_obj.full_name,
                    "email": lead_obj.email,
                    "phone": lead_obj.phone,
                    "job_title": lead_obj.job_title,
                    "company_name": lead_obj.company_name,
                    "company_domain": lead_obj.company_domain,
                    "linkedin_url": lead_obj.linkedin_url,
                    "source": lead_obj.source,
                }
                val_res = validate_lead(current_dict)
                lead_obj.confidence_score = val_res.get("confidence_score")
                lead_obj.data_quality_flags = val_res.get("data_quality_flags", [])
                update_fields.extend(["confidence_score", "data_quality_flags"])

                lead_obj.save(update_fields=list(set(update_fields)))

            return {
                "status": "success",
                "lead_id": contract.lead_id,
                "run_id": run_id,
                "enrichment_status": contract.status,
                "summary": wf_summary,
                "changes": changes,
                # Flat list of the fields this run actually added/updated. The UI
                # reads this to decide between "Enrichment Complete" and "No New
                # Data"; it is NOT part of contract.to_dict(), so expose it here.
                "fields_updated": list(changes.keys()),
                "contract": contract.to_dict(),
            }

        except Exception as exc:
            logger.error("EnrichmentAgent failed for lead %s: %s", lead_or_id, exc, exc_info=True)
            contract.status = "failed"
            if lead_obj:
                lead_obj.raw_data["enrichment"] = contract.to_dict()
                lead_obj.save(update_fields=["raw_data", "updated_at"])
            return {
                "status": "error",
                "lead_id": contract.lead_id,
                "run_id": run_id,
                "error": str(exc),
            }

    def enrich_leads_batch(
        self,
        lead_ids: List[int],
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Enriches a batch of leads sequentially.
        """
        results = []
        completed = 0
        failed = 0

        for lid in dict.fromkeys(lead_ids):
            res = self.enrich_lead(lid, force=force)
            results.append(res)
            if res.get("status") == "success":
                completed += 1
            else:
                failed += 1

        return {
            "total": len(lead_ids),
            "completed": completed,
            "failed": failed,
            "results": results,
        }


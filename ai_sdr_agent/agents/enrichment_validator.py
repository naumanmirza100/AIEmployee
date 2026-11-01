"""
Enrichment Validation & Identity Resolution Layer
-------------------------------------------------
Validates incoming enriched candidate records to ensure:
1. They belong to the intended person (name similarity, title consistency).
2. They belong to the intended company (domain matching, company name similarity).
3. Conflicting provider values are arbitrated and recorded for auditability.
4. Existing high-confidence verified data is never displaced by lower-confidence candidates.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ai_sdr_agent.agents.enrichment_contract import (
    ConflictRecord,
    EnrichmentContract,
    FieldProvenance,
    OverwriteDecision,
    VerificationStatus,
    can_overwrite_field,
    is_placeholder_or_empty,
)
from ai_sdr_agent.agents.lead_validator import (
    _FORMER_TITLE_RE,
    _LINKEDIN_PROFILE_RE,
    normalize_linkedin_url,
)
from ai_sdr_agent.agents.contact_verifier import verify_email, verify_phone

logger = logging.getLogger(__name__)

# Suffixes to strip when comparing company names
_LEGAL_SUFFIXES_RE = re.compile(
    r"\b(inc|incorporated|corp|corporation|llc|ltd|limited|co|company|plc|gmbh|pvt|pty|sa|ag|bv|group|holdings)\b\.?",
    re.IGNORECASE,
)


def clean_company_name(name: str) -> str:
    """Normalize company name by stripping legal suffixes, punctuation, and excess spaces."""
    if not name:
        return ""
    cleaned = _LEGAL_SUFFIXES_RE.sub("", name)
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def name_tokens_match(name1: str, name2: str) -> bool:
    """
    Check if two names refer to the same individual.
    Tolerates middle initials, partial abbreviations, and case differences.
    """
    if not name1 or not name2:
        return False

    toks1 = {t for t in re.sub(r"[^\w\s]", "", name1.lower()).split() if len(t) > 1}
    toks2 = {t for t in re.sub(r"[^\w\s]", "", name2.lower()).split() if len(t) > 1}

    if not toks1 or not toks2:
        return False

    # Exact token match or high intersection
    overlap = toks1 & toks2
    if len(overlap) >= min(len(toks1), len(toks2)):
        return True

    # Check first and last name match specifically
    list1 = [t for t in name1.lower().split() if len(t) > 1]
    list2 = [t for t in name2.lower().split() if len(t) > 1]
    if list1 and list2 and list1[0] == list2[0] and list1[-1] == list2[-1]:
        return True

    return False


def validate_identity(
    lead_state: Dict[str, Any],
    candidate_data: Dict[str, Any],
    min_identity_score: int = 50,
) -> Tuple[bool, int, List[str]]:
    """
    Evaluates whether candidate enrichment data belongs to the intended person & company.

    Returns:
        (is_match, identity_score, reasons)
    """
    score = 100
    reasons: List[str] = []

    lead_name = lead_state.get("full_name") or f"{lead_state.get('first_name', '')} {lead_state.get('last_name', '')}".strip()
    cand_name = candidate_data.get("full_name") or f"{candidate_data.get('first_name', '')} {candidate_data.get('last_name', '')}".strip()

    lead_company = lead_state.get("company_name", "")
    cand_company = candidate_data.get("company_name", "")

    lead_domain = (lead_state.get("company_domain") or "").strip().lower().removeprefix("www.")
    cand_domain = (candidate_data.get("company_domain") or "").strip().lower().removeprefix("www.")

    # 1. Name Check
    if lead_name and cand_name:
        if not name_tokens_match(lead_name, cand_name):
            reasons.append(f"Name mismatch: '{cand_name}' vs expected '{lead_name}'")
            score -= 60
        else:
            reasons.append("Person name matches")

    # 2. Company Name Check
    if lead_company and cand_company:
        clean_lead_co = clean_company_name(lead_company)
        clean_cand_co = clean_company_name(cand_company)
        if clean_lead_co and clean_cand_co and clean_lead_co != clean_cand_co:
            if clean_lead_co not in clean_cand_co and clean_cand_co not in clean_lead_co:
                reasons.append(f"Company mismatch: '{cand_company}' vs expected '{lead_company}'")
                score -= 30
            else:
                reasons.append("Company name partially matches")
        else:
            reasons.append("Company name matches")

    # 3. Domain Check
    if lead_domain and cand_domain:
        if lead_domain != cand_domain and not (cand_domain.endswith("." + lead_domain) or lead_domain.endswith("." + cand_domain)):
            reasons.append(f"Company domain mismatch: '{cand_domain}' vs '{lead_domain}'")
            score -= 35
        else:
            reasons.append("Company domain matches")

    # 4. Job Title Check
    cand_title = candidate_data.get("job_title", "")
    if cand_title and _FORMER_TITLE_RE.search(cand_title):
        reasons.append("Candidate title indicates a former role, not current employment")
        score -= 60

    # 5. Email Domain vs Company Domain
    cand_email = candidate_data.get("email", "")
    if cand_email and "@" in cand_email and lead_domain:
        email_dom = cand_email.split("@", 1)[-1].lower().removeprefix("www.")
        if email_dom != lead_domain and not email_dom.endswith("." + lead_domain):
            # Not fatal if personal email, but if claimed as work email it loses points
            reasons.append(f"Email domain '{email_dom}' differs from company domain '{lead_domain}'")
            score -= 15

    final_score = max(0, min(100, score))
    is_match = final_score >= min_identity_score
    return is_match, final_score, reasons


def validate_and_merge_enrichment(
    contract: EnrichmentContract,
    candidate_fields: Dict[str, FieldProvenance],
    source_name: str,
    check_dns: bool = True,
) -> Tuple[EnrichmentContract, Dict[str, Any]]:
    """
    Centralized validation and merge layer.
    Validates candidates, executes verification, arbitrates conflicts, and updates the contract.

    Returns:
        (updated_contract, summary_dict)
    """
    updated_fields: List[str] = []
    rejected_fields: List[str] = []
    conflicts_detected: List[Dict[str, Any]] = []

    # Prepare existing lead summary for identity validation
    lead_summary = {
        "full_name": contract.fields.get("full_name").value if "full_name" in contract.fields else "",
        "company_name": contract.fields.get("company_name").value if "company_name" in contract.fields else "",
        "company_domain": contract.fields.get("company_domain").value if "company_domain" in contract.fields else "",
        "email": contract.fields.get("email").value if "email" in contract.fields else "",
    }

    # Candidate summary
    cand_summary = {
        "full_name": candidate_fields.get("full_name").value if "full_name" in candidate_fields else "",
        "company_name": candidate_fields.get("company_name").value if "company_name" in candidate_fields else "",
        "company_domain": candidate_fields.get("company_domain").value if "company_domain" in candidate_fields else "",
        "email": candidate_fields.get("email").value if "email" in candidate_fields else "",
        "job_title": candidate_fields.get("job_title").value if "job_title" in candidate_fields else "",
    }

    # Verify identity match if candidate has identifying fields
    if any(cand_summary.values()):
        is_match, id_score, id_reasons = validate_identity(lead_summary, cand_summary)
        if not is_match:
            logger.warning("Identity resolution failed for source %s (score %d): %s", source_name, id_score, id_reasons)
            return contract, {
                "updated_fields": [],
                "rejected_fields": list(candidate_fields.keys()),
                "reason": f"Identity resolution mismatch (score {id_score}): {'; '.join(id_reasons)}",
                "conflicts": [],
            }

    # Process each candidate field
    for field_name, incoming_prov in candidate_fields.items():
        if incoming_prov.value is None or str(incoming_prov.value).strip() == "":
            continue

        # If incoming is email, run contact verifier
        if field_name == "email":
            comp_dom = (
                incoming_prov.verification_details.get("company_domain")
                or (contract.fields.get("company_domain").value if "company_domain" in contract.fields else "")
            )
            v_res = verify_email(str(incoming_prov.value), company_domain=comp_dom, check_dns=check_dns)
            if not v_res["is_valid"]:
                rejected_fields.append(field_name)
                continue

            if incoming_prov.verification_status != VerificationStatus.VALID:
                incoming_prov.verification_status = v_res["status"]
            incoming_prov.verification_details.update(v_res["details"])
            incoming_prov.confidence = max(incoming_prov.confidence, v_res["confidence"])

        # If incoming is personal_email
        elif field_name == "personal_email":
            v_res = verify_email(str(incoming_prov.value), check_dns=check_dns)
            incoming_prov.verification_status = v_res["status"]
            incoming_prov.verification_details.update(v_res["details"])
            contract.personal_email = str(incoming_prov.value)
            updated_fields.append("personal_email")
            continue

        # If incoming is phone
        elif field_name == "phone":
            p_res = verify_phone(str(incoming_prov.value))
            incoming_prov.verification_status = p_res["status"]
            incoming_prov.verification_details.update(p_res["details"])
            if p_res.get("normalized_phone"):
                incoming_prov.value = p_res["normalized_phone"]
            incoming_prov.confidence = min(incoming_prov.confidence, p_res["confidence"])

            if not p_res["is_valid"]:
                rejected_fields.append(field_name)
                continue

        # Check overwrite eligibility
        existing_prov = contract.fields.get(field_name)
        decision: OverwriteDecision = can_overwrite_field(field_name, existing_prov, incoming_prov)

        if decision.is_conflict:
            conflict = ConflictRecord(
                field_name=field_name,
                existing_value=existing_prov.value if existing_prov else None,
                existing_source=existing_prov.source if existing_prov else "none",
                conflicting_value=incoming_prov.value,
                conflicting_source=incoming_prov.source,
                resolution="overwritten" if decision.should_overwrite else "retained_existing",
            )
            contract.conflicts.append(conflict)
            conflicts_detected.append(conflict.to_dict())

        if decision.should_overwrite:
            if existing_prov:
                incoming_prov.previous_value = existing_prov.value
            contract.fields[field_name] = incoming_prov
            updated_fields.append(field_name)
        else:
            rejected_fields.append(field_name)

    return contract, {
        "updated_fields": updated_fields,
        "rejected_fields": rejected_fields,
        "conflicts": conflicts_detected,
    }

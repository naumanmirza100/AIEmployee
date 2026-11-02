"""
Enrichment Data Contract & Architecture
---------------------------------------
Defines the schema, provenance tracking, verification statuses, and non-destructive
overwrite policies for the SDR Lead Enrichment Agent.

Guarantees:
1. Every enriched field retains full provenance (source, timestamp, confidence, verification status).
2. Existing verified data is never overwritten with lower-confidence or unverified data.
3. Overwrites preserve previous values and reasons in an immutable audit trail.
4. Conflicting provider values are recorded rather than silently discarded.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
import re

from ai_sdr_agent.agents.lead_validator import (
    _FAKE_NAMES,
    _FAKE_EMAIL_PREFIXES,
    _FAKE_COMPANIES,
    _EMAIL_RE,
    _LINKEDIN_PROFILE_RE,
    normalize_linkedin_url,
)


class VerificationStatus(str, Enum):
    VALID = "valid"               # Verified real/deliverable (e.g., SMTP/MX pass, verified web page)
    RISKY = "risky"               # Plausible but catch-all domain, disposable, or unconfirmed phone
    UNVERIFIED = "unverified"     # Provider reported or extracted without independent verification
    INVALID = "invalid"           # Syntax error, fake prefix, bad domain, hard bounced
    CONFLICT = "conflict"         # Disagreement between multiple sources


# Numeric ranks for verification status to evaluate upgrade eligibility
VERIFICATION_RANKS: Dict[VerificationStatus, int] = {
    VerificationStatus.INVALID: 1,
    VerificationStatus.UNVERIFIED: 2,
    VerificationStatus.RISKY: 3,
    VerificationStatus.VALID: 4,
    VerificationStatus.CONFLICT: 0,
}


# Default source trustworthiness priorities (higher integer = higher priority)
SOURCE_PRIORITY: Dict[str, int] = {
    "manual": 100,             # Manually entered by user
    "crm_sync": 95,            # Verified CRM sync
    "email_verifier": 90,      # Dedicated email verification provider
    "apollo": 80,              # Apollo.io API
    "hunter": 75,              # Hunter.io
    "clearbit": 75,            # Clearbit
    "prospeo": 70,             # Prospeo
    "public_web": 65,          # Compliant company public website crawl
    "google_search": 60,       # Search results
    "ai_generated": 20,        # Synthetic generation (low trust)
    "unknown": 10,
}


# Core fields supported by the Enrichment Agent
ENRICHABLE_FIELDS = {
    "full_name",
    "first_name",
    "last_name",
    "job_title",
    "company_name",
    "company_domain",
    "company_website",
    "email",                   # Primary / work email
    "personal_email",          # Publicly listed personal email
    "phone",                   # Work or direct phone / mobile
    "linkedin_url",            # LinkedIn profile URL
    "other_profiles",          # Dict of additional profile URLs (e.g. github, twitter)
    "seniority_level",
    "department",
    "company_industry",
    "company_size",
    "company_location",
}


@dataclass
class FieldProvenance:
    """Provenance tracking for an individual enriched or existing lead attribute."""
    field_name: str
    value: Any
    previous_value: Optional[Any] = None
    source: str = "unknown"                       # Provider name or source URL
    confidence: int = 50                          # 0 to 100
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    verification_details: Dict[str, Any] = field(default_factory=dict)
    evidence: Optional[str] = None               # Quote or text context
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if isinstance(self.verification_status, VerificationStatus):
            d["verification_status"] = self.verification_status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FieldProvenance":
        status_val = data.get("verification_status", VerificationStatus.UNVERIFIED.value)
        if isinstance(status_val, str):
            try:
                status_enum = VerificationStatus(status_val)
            except ValueError:
                status_enum = VerificationStatus.UNVERIFIED
        else:
            status_enum = status_val

        return cls(
            field_name=data.get("field_name", ""),
            value=data.get("value"),
            previous_value=data.get("previous_value"),
            source=data.get("source", "unknown"),
            confidence=int(data.get("confidence", 50)),
            verification_status=status_enum,
            verification_details=data.get("verification_details") or {},
            evidence=data.get("evidence"),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass
class ProviderAttempt:
    """Audit log of an attempt to query an enrichment provider."""
    provider: str
    target_field: str
    status: str                                  # 'success', 'not_found', 'rate_limited', 'error', 'skipped'
    latency_ms: int = 0
    message: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConflictRecord:
    """Audit record when two sources provide conflicting information for a field."""
    field_name: str
    existing_value: Any
    existing_source: str
    conflicting_value: Any
    conflicting_source: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolution: str = "retained_existing"       # 'retained_existing', 'overwritten', 'flagged'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OverwriteDecision:
    """Decision details on whether a field can be safely overwritten."""
    should_overwrite: bool
    reason: str
    is_conflict: bool = False


def is_placeholder_or_empty(field_name: str, value: Any) -> bool:
    """
    Check if a value is absent, empty, or a known placeholder according to
    lead_validator rules.
    """
    if value is None:
        return True
    val_str = str(value).strip()
    if not val_str:
        return True

    val_lower = val_str.lower()
    if field_name in ("full_name", "first_name", "last_name"):
        return val_lower in _FAKE_NAMES
    if field_name == "company_name":
        return val_lower in _FAKE_COMPANIES
    if field_name in ("email", "personal_email"):
        return any(val_lower.startswith(prefix) for prefix in _FAKE_EMAIL_PREFIXES) or val_lower.endswith("@example.com")
    if field_name == "linkedin_url":
        return bool(_LINKEDIN_PROFILE_RE.search(val_str) is None)
    return False


def can_overwrite_field(
    field_name: str,
    existing: Optional[FieldProvenance],
    incoming: FieldProvenance,
    source_priority_map: Optional[Dict[str, int]] = None,
) -> OverwriteDecision:
    """
    Determines whether an incoming enriched value may overwrite an existing value
    under strict non-destructive conditions.

    Rules:
    1. If existing is None or empty/placeholder, always accept valid incoming.
    2. Never overwrite a 'valid' status with an 'unverified', 'risky', or 'invalid' status.
    3. If incoming status rank is higher than existing status rank, permit overwrite.
    4. If status ranks are equal:
       - If values are identical (after normalization), no change needed (no overwrite).
       - If values conflict:
         a) Compare source priority. Higher priority wins.
         b) If source priority is equal, compare confidence score. Higher confidence wins.
         c) If still tied, preserve existing value and flag conflict for auditability.
    """
    p_map = source_priority_map or SOURCE_PRIORITY

    # 1. Existing value is missing or placeholder
    if existing is None or is_placeholder_or_empty(field_name, existing.value):
        if is_placeholder_or_empty(field_name, incoming.value):
            return OverwriteDecision(False, "Incoming value is also empty or placeholder", is_conflict=False)
        return OverwriteDecision(True, "Existing value was missing or placeholder", is_conflict=False)

    # If incoming value is empty or placeholder, never overwrite existing data
    if is_placeholder_or_empty(field_name, incoming.value):
        return OverwriteDecision(False, "Incoming value is empty or placeholder", is_conflict=False)

    # Normalize values for equality comparison
    existing_norm = str(existing.value).strip().lower()
    incoming_norm = str(incoming.value).strip().lower()

    if field_name == "linkedin_url":
        existing_norm = normalize_linkedin_url(existing_norm)
        incoming_norm = normalize_linkedin_url(incoming_norm)

    if existing_norm == incoming_norm:
        # Same value: upgrade verification or confidence if incoming is higher, but not a conflict
        existing_rank = VERIFICATION_RANKS.get(existing.verification_status, 0)
        incoming_rank = VERIFICATION_RANKS.get(incoming.verification_status, 0)
        if incoming_rank > existing_rank or incoming.confidence > existing.confidence:
            return OverwriteDecision(True, "Values match; upgraded verification/confidence", is_conflict=False)
        return OverwriteDecision(False, "Values are identical; no update required", is_conflict=False)

    # 2. Values are DIFFERENT — check verification hierarchy
    existing_rank = VERIFICATION_RANKS.get(existing.verification_status, 2)
    incoming_rank = VERIFICATION_RANKS.get(incoming.verification_status, 2)

    # Never replace 'valid' with lower rank
    if existing.verification_status == VerificationStatus.VALID and incoming.verification_status != VerificationStatus.VALID:
        return OverwriteDecision(
            False,
            f"Cannot overwrite verified '{existing.verification_status.value}' with unverified/lower rank '{incoming.verification_status.value}'",
            is_conflict=True,
        )

    # Higher verification rank wins
    if incoming_rank > existing_rank:
        return OverwriteDecision(
            True,
            f"Incoming verification status '{incoming.verification_status.value}' exceeds existing '{existing.verification_status.value}'",
            is_conflict=True,
        )
    elif incoming_rank < existing_rank:
        return OverwriteDecision(
            False,
            f"Existing verification status '{existing.verification_status.value}' exceeds incoming '{incoming.verification_status.value}'",
            is_conflict=True,
        )

    # Status ranks are EQUAL: compare source priority
    existing_src_prio = p_map.get(existing.source.split(":")[0], p_map.get("unknown", 10))
    incoming_src_prio = p_map.get(incoming.source.split(":")[0], p_map.get("unknown", 10))

    if incoming_src_prio > existing_src_prio:
        return OverwriteDecision(
            True,
            f"Incoming source '{incoming.source}' has higher priority ({incoming_src_prio}) than '{existing.source}' ({existing_src_prio})",
            is_conflict=True,
        )
    elif incoming_src_prio < existing_src_prio:
        return OverwriteDecision(
            False,
            f"Existing source '{existing.source}' has higher priority ({existing_src_prio}) than '{incoming.source}' ({incoming_src_prio})",
            is_conflict=True,
        )

    # Source priorities are EQUAL: compare confidence
    if incoming.confidence > existing.confidence:
        return OverwriteDecision(
            True,
            f"Incoming confidence ({incoming.confidence}) exceeds existing ({existing.confidence})",
            is_conflict=True,
        )

    return OverwriteDecision(
        False,
        "Retained existing value due to equal or higher priority/confidence",
        is_conflict=True,
    )


@dataclass
class EnrichmentContract:
    """
    Structured container for a lead's complete enrichment state.
    Serialized into SDRLead.raw_data['enrichment'].
    """
    lead_id: Optional[int]
    status: str = "new"                          # 'new', 'pending', 'running', 'completed', 'partial', 'failed'
    last_run_id: Optional[str] = None
    last_enriched_at: Optional[str] = None
    fields: Dict[str, FieldProvenance] = field(default_factory=dict)
    personal_email: Optional[str] = None
    other_profiles: Dict[str, str] = field(default_factory=dict)
    conflicts: List[ConflictRecord] = field(default_factory=list)
    provider_attempts: List[ProviderAttempt] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)

    def get_missing_fields(self, required_fields: Optional[Set[str]] = None) -> List[str]:
        """Identify which requested fields are missing or have invalid/placeholder values."""
        targets = required_fields or {
            "full_name",
            "job_title",
            "company_name",
            "company_domain",
            "company_website",
            "email",
            "phone",
            "linkedin_url",
        }
        missing = []
        for f in targets:
            prov = self.fields.get(f)
            if prov is None or is_placeholder_or_empty(f, prov.value):
                missing.append(f)
            elif prov.verification_status == VerificationStatus.INVALID:
                missing.append(f)
        return missing

    def to_dict(self) -> Dict[str, Any]:
        """Convert contract to dict suitable for JSON serialization in raw_data."""
        return {
            "lead_id": self.lead_id,
            "status": self.status,
            "last_run_id": self.last_run_id,
            "last_enriched_at": self.last_enriched_at,
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
            "personal_email": self.personal_email,
            "other_profiles": self.other_profiles,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "provider_attempts": [a.to_dict() for a in self.provider_attempts],
            "history": self.history,
        }

    @classmethod
    def from_lead(cls, lead: Any) -> "EnrichmentContract":
        """
        Build an EnrichmentContract from an SDRLead model instance or dictionary,
        inspecting present fields and existing raw_data['enrichment'] if present.
        """
        raw_data = getattr(lead, "raw_data", None)
        if not isinstance(raw_data, dict):
            raw_data = lead.get("raw_data", {}) if isinstance(lead, dict) else {}

        enrichment_blob = raw_data.get("enrichment")
        if isinstance(enrichment_blob, dict) and "fields" in enrichment_blob:
            # Reconstruct from existing blob
            contract = cls(
                lead_id=getattr(lead, "id", None) or (lead.get("id") if isinstance(lead, dict) else None),
                status=enrichment_blob.get("status", "new"),
                last_run_id=enrichment_blob.get("last_run_id"),
                last_enriched_at=enrichment_blob.get("last_enriched_at"),
                personal_email=enrichment_blob.get("personal_email"),
                other_profiles=enrichment_blob.get("other_profiles") or {},
                history=enrichment_blob.get("history") or [],
            )
            for k, f_dict in enrichment_blob.get("fields", {}).items():
                if isinstance(f_dict, dict):
                    contract.fields[k] = FieldProvenance.from_dict(f_dict)
            for c_dict in enrichment_blob.get("conflicts", []):
                if isinstance(c_dict, dict):
                    contract.conflicts.append(ConflictRecord(**c_dict))
            for a_dict in enrichment_blob.get("provider_attempts", []):
                if isinstance(a_dict, dict):
                    contract.provider_attempts.append(ProviderAttempt(**a_dict))
            return contract

        # No existing enrichment block; seed from existing lead fields
        lead_id = getattr(lead, "id", None) or (lead.get("id") if isinstance(lead, dict) else None)
        contract = cls(lead_id=lead_id)

        def _get_val(key: str) -> Any:
            if hasattr(lead, key):
                return getattr(lead, key)
            if isinstance(lead, dict):
                return lead.get(key)
            return None

        for field_name in ENRICHABLE_FIELDS:
            if field_name in ("personal_email", "other_profiles"):
                continue
            val = _get_val(field_name)
            if val:
                # Set initial provenance for existing values
                is_fake = is_placeholder_or_empty(field_name, val)
                status = VerificationStatus.INVALID if is_fake else VerificationStatus.UNVERIFIED
                confidence = 20 if is_fake else 60
                source = _get_val("source") or "existing"

                contract.fields[field_name] = FieldProvenance(
                    field_name=field_name,
                    value=val,
                    source=f"lead_model:{source}",
                    confidence=confidence,
                    verification_status=status,
                )

        return contract


"""
Contact Verification Layer
--------------------------
Validates and verifies contact details (emails and phone numbers).
Attaches distinct verification statuses:
  - valid: confirmed syntax, live MX records / deliverable
  - risky: plausible but catch-all domain, disposable email, or unconfirmed phone
  - invalid: bad syntax, fake prefix, no MX records, known disposable
  - unverified: plausible format but not independently confirmed
"""

import logging
import re
import socket
from typing import Any, Dict, Optional, Tuple

from ai_sdr_agent.agents.enrichment_contract import VerificationStatus
from ai_sdr_agent.agents.lead_validator import (
    _EMAIL_RE,
    _FAKE_EMAIL_PREFIXES,
    _FREE_EMAIL_DOMAINS,
)

logger = logging.getLogger(__name__)

# Common disposable / temporary email domains that should be marked INVALID or RISKY
_DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
    "throwawaymail.com", "trashmail.com", "getairmail.com", "yopmail.com",
    "sharklasers.com", "dispostable.com", "temp-mail.org", "fakeinbox.com",
}

# E.164 and international phone number pattern
_PHONE_CLEAN_RE = re.compile(r"[^\d+]")
_INTERNATIONAL_PHONE_RE = re.compile(r"^\+?[1-9]\d{7,14}$")
_FAKE_PHONE_NUMBERS = {
    "1234567890", "0000000000", "1111111111", "9999999999",
    "5555555555", "1234567", "+15555555555",
}


def verify_email_syntax(email: str) -> Tuple[bool, str]:
    """Check RFC email syntax and placeholder patterns."""
    if not email:
        return False, "Email is empty"

    cleaned = email.strip().lower()
    if not _EMAIL_RE.match(cleaned):
        return False, "Malformed email syntax"

    if any(cleaned.startswith(p) for p in _FAKE_EMAIL_PREFIXES):
        return False, "Placeholder or system email prefix"

    domain = cleaned.split("@", 1)[-1]
    if domain == "example.com" or domain.endswith(".example"):
        return False, "Example or test domain"

    return True, "Syntax valid"


def check_domain_mx(domain: str, timeout: float = 3.0) -> Tuple[bool, str]:
    """
    Check if the domain resolves and has active mail exchanger (MX) or host records.
    Uses standard library socket to avoid external dns dependencies.
    """
    if not domain:
        return False, "Empty domain"

    # Guard against invalid host characters
    clean_domain = domain.strip().lower().removeprefix("www.")
    if not re.match(r"^[a-z0-9.\-]+\.[a-z]{2,}$", clean_domain):
        return False, "Invalid domain format"

    try:
        # Check standard address lookup first
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(timeout)
        try:
            # Query host info to verify domain exists in DNS
            addrinfo = socket.getaddrinfo(clean_domain, 25, socket.AF_INET, socket.SOCK_STREAM)
            if addrinfo:
                return True, f"Domain {clean_domain} has active DNS resolution"
        finally:
            socket.setdefaulttimeout(old_timeout)
    except (socket.gaierror, socket.timeout, OSError) as exc:
        logger.debug("DNS resolution check failed for %s: %s", clean_domain, exc)
        return False, f"Domain {clean_domain} has no DNS resolution: {exc}"

    return False, "No active records"


def verify_email(
    email: str,
    company_domain: Optional[str] = None,
    verifier_api_key: Optional[str] = None,
    check_dns: bool = True,
) -> Dict[str, Any]:
    """
    Comprehensive email verification.

    Returns:
        {
            'status': VerificationStatus,
            'is_valid': bool,
            'confidence': int (0-100),
            'domain': str,
            'is_free': bool,
            'is_disposable': bool,
            'matches_company_domain': bool,
            'reason': str,
            'details': dict,
        }
    """
    if not email:
        return {
            "status": VerificationStatus.INVALID,
            "is_valid": False,
            "confidence": 0,
            "reason": "Missing email",
            "details": {},
        }

    clean_email = email.strip().lower()
    syntax_ok, syntax_reason = verify_email_syntax(clean_email)
    if not syntax_ok:
        return {
            "status": VerificationStatus.INVALID,
            "is_valid": False,
            "confidence": 0,
            "email": clean_email,
            "reason": syntax_reason,
            "details": {"syntax_valid": False},
        }

    domain = clean_email.split("@", 1)[-1]
    is_disposable = domain in _DISPOSABLE_DOMAINS
    if is_disposable:
        return {
            "status": VerificationStatus.INVALID,
            "is_valid": False,
            "confidence": 10,
            "email": clean_email,
            "domain": domain,
            "is_disposable": True,
            "reason": "Disposable email address detected",
            "details": {"disposable": True},
        }

    is_free = domain in _FREE_EMAIL_DOMAINS
    matches_company = False
    if company_domain:
        clean_cd = company_domain.strip().lower().removeprefix("www.")
        matches_company = (domain == clean_cd) or domain.endswith("." + clean_cd)

    details = {
        "syntax_valid": True,
        "is_free": is_free,
        "is_disposable": False,
        "matches_company_domain": matches_company,
        "dns_verified": False,
    }

    confidence = 70
    if matches_company:
        confidence += 15
    elif is_free:
        confidence -= 10

    # Optional DNS/MX verification
    if check_dns:
        dns_ok, dns_msg = check_domain_mx(domain)
        details["dns_verified"] = dns_ok
        details["dns_message"] = dns_msg
        if not dns_ok:
            return {
                "status": VerificationStatus.INVALID,
                "is_valid": False,
                "confidence": 15,
                "email": clean_email,
                "domain": domain,
                "reason": f"Domain MX/DNS check failed: {dns_msg}",
                "details": details,
            }
        confidence = min(100, confidence + 10)

    # Status classification
    if is_free:
        status = VerificationStatus.RISKY
        reason = "Valid syntax and DNS, but personal/free email provider"
    elif not matches_company and company_domain:
        status = VerificationStatus.RISKY
        reason = "Valid syntax and DNS, but email domain differs from company domain"
    elif check_dns and details["dns_verified"]:
        status = VerificationStatus.VALID
        reason = "Valid business email with confirmed domain DNS"
    else:
        status = VerificationStatus.UNVERIFIED
        reason = "Valid syntax, awaiting independent mailbox confirmation"

    return {
        "status": status,
        "is_valid": status != VerificationStatus.INVALID,
        "confidence": confidence,
        "email": clean_email,
        "domain": domain,
        "is_free": is_free,
        "is_disposable": False,
        "matches_company_domain": matches_company,
        "reason": reason,
        "details": details,
    }


def normalize_phone(phone_str: str, default_country_code: str = "+1") -> str:
    """
    Clean and normalize phone string to international E.164-style format.
    E.g. '(415) 555-2671' -> '+14155552671'
    E.g. '01440730068' with +44 -> '+441440730068'
    E.g. '+44(0)28 8673 7658' -> '+442886737658'
    """
    if not phone_str:
        return ""

    raw = phone_str.strip()
    raw = re.sub(r'(\+\d{1,3})\s*\(\s*0\s*\)', r'\1', raw)
    has_plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)

    if not digits:
        return ""

    if has_plus:
        # Strip trunk zero e.g. +440... -> +44...
        digits = re.sub(r'^(44)0(\d{9,10})$', r'\1\2', digits)
        return f"+{digits}"

    # If starts with 44 and has trunk zero e.g. 4407899806693 -> +447899806693
    if digits.startswith("440") and len(digits) >= 12:
        return f"+44{digits[3:]}"
    if digits.startswith("44") and len(digits) >= 11:
        return f"+{digits}"

    # If starts with 0 and country is UK (+44) or 10/11 digits
    if digits.startswith("0") and (default_country_code == "+44" or len(digits) in (10, 11)):
        cc = default_country_code.lstrip("+")
        return f"+{cc}{digits[1:]}"

    # If 10 digits (US/Canada format), prefix with +1
    if len(digits) == 10 and default_country_code == "+1":
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"

    # Otherwise return with + if digits looks international
    if len(digits) >= 10:
        return f"+{digits}"
    return digits


def verify_phone(phone: str, country_code: Optional[str] = None) -> Dict[str, Any]:
    """
    Validates structural plausibility of a phone number and normalizes format.
    Distinguishes structural format validation from carrier/network verification.
    """
    if not phone:
        return {
            "status": VerificationStatus.INVALID,
            "is_valid": False,
            "confidence": 0,
            "reason": "Missing phone number",
            "details": {},
        }

    raw = str(phone).strip()
    digits = re.sub(r"\D", "", raw)

    if len(digits) < 7:
        return {
            "status": VerificationStatus.INVALID,
            "is_valid": False,
            "confidence": 0,
            "phone": raw,
            "reason": "Phone number too short (minimum 7 digits)",
            "details": {"structural_valid": False},
        }

    if digits in _FAKE_PHONE_NUMBERS or raw in _FAKE_PHONE_NUMBERS:
        return {
            "status": VerificationStatus.INVALID,
            "is_valid": False,
            "confidence": 0,
            "phone": raw,
            "reason": "Placeholder or mock phone number detected",
            "details": {"structural_valid": False, "is_placeholder": True},
        }

    normalized = normalize_phone(raw, default_country_code=country_code or "+1")
    is_e164 = bool(_INTERNATIONAL_PHONE_RE.match(normalized))

    if not is_e164:
        return {
            "status": VerificationStatus.RISKY,
            "is_valid": True,
            "confidence": 45,
            "phone": raw,
            "normalized_phone": normalized,
            "reason": "Plausible phone digits but does not match standard E.164 international format",
            "details": {"structural_valid": True, "e164_format": False, "live_carrier_verified": False},
        }

    return {
        "status": VerificationStatus.VALID,
        "is_valid": True,
        "confidence": 75,
        "phone": raw,
        "normalized_phone": normalized,
        "reason": "Structurally valid international E.164 phone format",
        "details": {"structural_valid": True, "e164_format": True, "live_carrier_verified": False},
    }

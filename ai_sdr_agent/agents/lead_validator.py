"""
Lead Data Validator
-------------------
Validates lead data quality before saving.
Calculates confidence_score, detects fake/placeholder data, flags incomplete records.
"""

import re
import logging

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')

_FAKE_NAMES = {
    'test', 'user', 'john doe', 'jane doe', 'sample', 'demo', 'example',
    'unknown', 'n/a', 'na', 'test user', 'test lead', 'first last',
    'firstname lastname', 'full name',
}

_FAKE_EMAIL_PREFIXES = (
    'test@', 'example@', 'noreply@', 'no-reply@', 'fake@',
    'sample@', 'demo@', 'placeholder@', 'donotreply@', 'info@test',
    'user@example',
)

_FREE_EMAIL_DOMAINS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com',
    'protonmail.com', 'aol.com', 'live.com', 'msn.com', 'yahoo.co.uk',
    'googlemail.com', 'mail.com',
}

_FAKE_COMPANIES = {
    'acme', 'test', 'demo', 'example', 'company', 'your company', 'n/a',
    'unknown', 'test company', 'sample company', 'acme corp', 'na',
    'company name', 'mycompany',
}

_DECISION_MAKER_KEYWORDS = (
    'ceo', 'cto', 'coo', 'cmo', 'cfo', 'chief', 'founder', 'co-founder',
    'president', 'vp', 'vice president', 'director', 'head of', 'head,',
    'managing director', 'md', 'owner', 'partner', 'principal', 'svp',
    'evp', 'gm', 'general manager',
)


def validate_lead(lead_dict: dict) -> dict:
    """
    Validate a lead dict and return quality metadata.

    Returns:
        {
            'confidence_score': int (0-100),
            'data_quality_flags': list[str],
            'is_valid': bool,           # True if confidence_score >= 40
            'email_format_valid': bool,
        }
    """
    flags = []
    score = 100

    name = (lead_dict.get('full_name') or '').strip()
    email = (lead_dict.get('email') or '').strip().lower()
    phone = (lead_dict.get('phone') or '').strip()
    job_title = (lead_dict.get('job_title') or '').strip()
    company_name = (lead_dict.get('company_name') or '').strip()
    company_location = (lead_dict.get('company_location') or '').strip()
    linkedin_url = (lead_dict.get('linkedin_url') or '').strip()
    company_website = (lead_dict.get('company_website') or '').strip()

    # ── Name ──────────────────────────────────────────────────────────────
    if not name:
        flags.append('Missing full name')
        score -= 20
    elif name.lower().strip() in _FAKE_NAMES:
        flags.append('Placeholder name detected')
        score -= 30
    elif len(name.split()) < 2:
        flags.append('Incomplete name (single word only)')
        score -= 8

    # ── Email ──────────────────────────────────────────────────────────────
    email_valid = False
    if not email:
        flags.append('Missing email address')
        score -= 20
    elif not _EMAIL_RE.match(email):
        flags.append('Invalid email format')
        score -= 18
    elif any(email.startswith(p) for p in _FAKE_EMAIL_PREFIXES):
        flags.append('Placeholder email detected')
        score -= 25
    else:
        email_valid = True
        domain = email.split('@', 1)[-1].lower()
        if domain in _FREE_EMAIL_DOMAINS:
            flags.append('Personal email (not business domain)')
            score -= 8
        elif domain == 'example.com' or domain.endswith('.example'):
            flags.append('Example domain email')
            score -= 20
            email_valid = False

    # ── Company ────────────────────────────────────────────────────────────
    if not company_name:
        flags.append('Missing company name')
        score -= 15
    elif company_name.lower().strip() in _FAKE_COMPANIES:
        flags.append('Placeholder company name detected')
        score -= 20

    # ── Job title ──────────────────────────────────────────────────────────
    if not job_title:
        flags.append('Missing job title')
        score -= 10

    # ── Contact reachability ───────────────────────────────────────────────
    has_contact = bool(email_valid or phone or linkedin_url)
    if not has_contact:
        flags.append('No reachable contact method (email/phone/LinkedIn)')
        score -= 20

    # ── Location ───────────────────────────────────────────────────────────
    if not company_location:
        flags.append('Missing location')
        score -= 5

    confidence = max(0, min(100, score))

    return {
        'confidence_score': confidence,
        'data_quality_flags': flags,
        'is_valid': confidence >= 40,
        'email_format_valid': email_valid,
    }


def is_decision_maker(job_title: str) -> bool:
    """Return True if the job title suggests a decision-maker role."""
    if not job_title:
        return False
    title_lower = job_title.lower()
    return any(kw in title_lower for kw in _DECISION_MAKER_KEYWORDS)

"""
Lead Data Validator
-------------------
Validates lead data quality before saving.
Calculates confidence_score, detects fake/placeholder data, flags incomplete records.

confidence_score measures how complete and plausible a record looks, not whether it is true. Truth is the
research workflow's job: see verification in the research profile.
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
    'user@example', 'email_not_unlocked@', 'not_unlocked@',
)

_LINKEDIN_PROFILE_RE = re.compile(r'linkedin\.com/(?:in|pub)/[^/?#]+', re.IGNORECASE)
_FORMER_TITLE_RE = re.compile(r'^\s*(?:former\b|ex[- ]|retired\b|previously\b)', re.IGNORECASE)

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

# Whole words only: as substrings "coo" is in Coordinator, "gm" in Segment and "cto" in Director.
_DECISION_MAKER_RE = re.compile(
    r'\b(ceo|cto|coo|cmo|cfo|cio|cro|ciso|chief|founder|co-founder|cofounder|president|vp|vice president|'
    r'director|head of|managing director|md|partner|principal|svp|evp|gm|general manager)\b'
    r'|(?<!product )\bowner\b',
    re.IGNORECASE,
)
_NOT_DECISION_MAKER_RE = re.compile(r'\b(partner (?:success|manager|marketing)|assistant|pa to)\b', re.IGNORECASE)


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
    company_domain = (lead_dict.get('company_domain') or '').strip().lower().removeprefix('www.')

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
        elif company_domain and not (domain == company_domain or domain.endswith('.' + company_domain)):
            flags.append('Email domain differs from company domain')
            score -= 10

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
    elif _FORMER_TITLE_RE.search(job_title):
        flags.append('Job title describes a former role')
        score -= 25

    # ── Origin ─────────────────────────────────────────────────────────────
    if lead_dict.get('source') == 'ai_generated':
        flags.append('AI-generated record: not a verified real person')
        score = min(score, 20)

    if linkedin_url and not _LINKEDIN_PROFILE_RE.search(linkedin_url):
        flags.append('LinkedIn URL is not a profile link')
        score -= 5

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
    if not job_title or _NOT_DECISION_MAKER_RE.search(job_title):
        return False
    return bool(_DECISION_MAKER_RE.search(job_title))


def normalize_linkedin_url(url: str) -> str:
    """One key per profile, whatever country host, scheme, query or case a provider returned."""
    match = _LINKEDIN_PROFILE_RE.search(url or '')
    return match.group(0).lower() if match else (url or '').strip().lower().rstrip('/')


def dedupe_leads(leads: list[dict]) -> list[dict]:
    """Drop repeats within one result set. LinkedIn is the strongest key, then email, then name + company."""
    seen, unique = set(), []
    for lead in leads:
        name = (lead.get('full_name') or '').strip().lower()
        company = (lead.get('company_name') or '').strip().lower()
        keys = {
            ('linkedin', normalize_linkedin_url(lead.get('linkedin_url'))) if lead.get('linkedin_url') else None,
            ('email', (lead.get('email') or '').strip().lower()) if lead.get('email') else None,
            ('person', name, company) if name and company else None,
        } - {None}
        if keys & seen:
            continue
        seen |= keys
        unique.append(lead)
    return unique

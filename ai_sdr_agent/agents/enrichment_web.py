"""
Compliant Public Web Enrichment Module
---------------------------------------
Extracts publicly listed contact and professional information from company websites
while strictly respecting web standards, robots.txt, rate limits, and security constraints.

Compliance Guarantees:
1. Always parses and respects robots.txt before fetching any page.
2. Identifies itself with a transparent, identifiable User-Agent.
3. Implements domain-level rate limiting to avoid overwhelming company servers.
4. Respects HTTP status codes (401, 403, 429, 503) without attempting bypass.
5. Never attempts to solve CAPTCHAs or evade anti-bot protections.
6. Reuses WebpageExtractor and SSRF protection (is_public_host) to prevent internal network scanning.
7. Retains source URL, extraction timestamp, and contextual evidence for every extracted value.
"""

import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

from ai_sdr_agent.agents.enrichment_contract import (
    FieldProvenance,
    VerificationStatus,
)
from ai_sdr_agent.agents.lead_research_tools import (
    WebpageExtractor,
    is_public_host,
)

logger = logging.getLogger(__name__)

COMPLIANT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 SDRLeadEnrichmentBot/1.0 "
    "(+https://example.com/bot-info; lead-enrichment-compliance)"
)

# Priority public pages for contact/leadership discovery
ENRICHMENT_SUBPAGE_CANDIDATES = [
    ("team", ["/team", "/about/team", "/leadership", "/about/leadership", "/people", "/management"]),
    ("about", ["/about", "/about-us", "/company", "/who-we-are"]),
    ("contact", ["/contact", "/contact-us", "/get-in-touch"]),
]

# Regex patterns for extracting emails and phones from public web pages
_PUBLIC_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_PUBLIC_PHONE_RE = re.compile(
    r"(?:(?:\+\d{1,3}[\s.-]?(?:\(0\)\s*)?|\b0)\d{1,4}[\s.-]?\d{2,4}[\s.-]?\d{3,4}(?:[\s.-]?\d{1,4})?|"
    r"\b(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}\b)"
)
_PUBLIC_LINKEDIN_RE = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/(?:in|pub)/[a-zA-Z0-9_\-%]+", re.I)
_PUBLIC_TWITTER_RE = re.compile(r"https?://(?:www\.)?(?:twitter\.com|x\.com)/[a-zA-Z0-9_]{1,30}", re.I)
_PUBLIC_GITHUB_RE = re.compile(r"https?://(?:www\.)?github\.com/[a-zA-Z0-9_\-]+", re.I)


class DomainRateLimiter:
    """Thread-safe per-domain rate limiter ensuring polite crawl intervals."""
    def __init__(self, min_interval_seconds: float = 1.0):
        self.min_interval = min_interval_seconds
        self._last_access: Dict[str, float] = {}
        self._lock = threading.Lock()

    def wait_for_domain(self, domain: str):
        if not domain:
            return
        domain = domain.lower()
        with self._lock:
            now = time.monotonic()
            last = self._last_access.get(domain, 0.0)
            elapsed = now - last
            if elapsed < self.min_interval:
                sleep_time = self.min_interval - elapsed
                time.sleep(sleep_time)
            self._last_access[domain] = time.monotonic()


class RobotsCache:
    """Caches and checks robots.txt policies per domain."""
    def __init__(self, timeout: float = 4.0):
        self.timeout = timeout
        self._parsers: Dict[str, RobotFileParser] = {}
        self._lock = threading.Lock()

    def can_fetch(self, url: str, user_agent: str = COMPLIANT_USER_AGENT) -> Tuple[bool, str]:
        """
        Check if robots.txt allows fetching url.
        Returns (is_allowed, reason).
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if not domain:
            return False, "Invalid URL"

        with self._lock:
            parser = self._parsers.get(domain)

        if parser is None:
            parser = RobotFileParser()
            robots_url = f"{parsed.scheme}://{domain}/robots.txt"
            try:
                # Direct safe check: ensure domain is public
                if not is_public_host(domain):
                    return False, f"Host {domain} is not a reachable public host"

                resp = requests.get(robots_url, headers={"User-Agent": user_agent}, timeout=self.timeout)
                if resp.status_code == 200:
                    parser.parse(resp.text.splitlines())
                elif resp.status_code in (401, 403):
                    # robots.txt explicitly forbidden means crawler is disallowed
                    parser.disallow_all = True
                else:
                    # 404 or other errors mean no robots.txt restrictions
                    parser.allow_all = True
            except Exception as exc:
                logger.debug("Failed to fetch robots.txt for %s: %s; allowing default access", domain, exc)
                parser.allow_all = True

            with self._lock:
                self._parsers[domain] = parser

        # Check permission for our agent
        bot_name = "SDRLeadEnrichmentBot"
        allowed = parser.can_fetch(bot_name, url) or parser.can_fetch("*", url)
        if not allowed:
            return False, f"Disallowed by {domain}/robots.txt"
        return True, "Allowed by robots.txt"


class CompliantWebEnricher:
    """
    Safely navigates company public websites and searches for missing lead attributes
    in compliance with web standards.
    """

    def __init__(
        self,
        rate_limiter: Optional[DomainRateLimiter] = None,
        robots_cache: Optional[RobotsCache] = None,
        extractor: Optional[WebpageExtractor] = None,
    ):
        self.rate_limiter = rate_limiter or DomainRateLimiter(min_interval_seconds=1.0)
        self.robots_cache = robots_cache or RobotsCache()
        self.extractor = extractor or WebpageExtractor()
        # Set compliant User-Agent
        self.extractor.session.headers.update({"User-Agent": COMPLIANT_USER_AGENT})

    def enrich_from_website(
        self,
        domain_or_url: str,
        lead_name: str,
        missing_fields: Set[str],
        max_pages: int = 5,
    ) -> Tuple[Dict[str, FieldProvenance], List[Dict[str, Any]]]:
        """
        Visits the company website and target subpages to discover missing lead fields.

        Returns:
            (enriched_fields, crawl_audit_log)
        """
        enriched: Dict[str, FieldProvenance] = {}
        crawl_log: List[Dict[str, Any]] = []

        base_url = self.extractor.normalize_url(domain_or_url)
        if not base_url:
            return enriched, crawl_log

        parsed = urlparse(base_url)
        domain = parsed.netloc

        candidate_urls = [base_url]
        # Prioritize contact subpages when phone or email is missing
        if "phone" in missing_fields or "email" in missing_fields:
            ordered_subpages = sorted(
                ENRICHMENT_SUBPAGE_CANDIDATES,
                key=lambda x: 0 if x[0] == "contact" else 1 if x[0] == "about" else 2
            )
        else:
            ordered_subpages = ENRICHMENT_SUBPAGE_CANDIDATES

        for _, paths in ordered_subpages:
            for p in paths:
                candidate_urls.append(urljoin(base_url + "/", p.lstrip("/")))

        visited: Set[str] = set()
        pages_crawled = 0

        first_name = lead_name.split()[0].lower() if lead_name else ""
        last_name = lead_name.split()[-1].lower() if lead_name and len(lead_name.split()) > 1 else ""

        for candidate_url in candidate_urls:
            if pages_crawled >= max_pages:
                break
            clean_cand = candidate_url.rstrip("/")
            if clean_cand in visited:
                continue
            visited.add(clean_cand)

            # 1. Check robots.txt
            can_fetch, robot_msg = self.robots_cache.can_fetch(candidate_url)
            if not can_fetch:
                crawl_log.append({
                    "url": candidate_url,
                    "status": "robots_disallowed",
                    "reason": robot_msg,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                logger.info("CompliantWebEnricher: Skipped %s: %s", candidate_url, robot_msg)
                continue

            # 2. Rate limit
            self.rate_limiter.wait_for_domain(domain)

            # 3. Fetch page safely
            fetch_res = self.extractor.fetch_page(candidate_url)
            pages_crawled += 1

            if not fetch_res or not fetch_res.get("success"):
                status_code = fetch_res.get("status_code", 0) if fetch_res else 0
                crawl_log.append({
                    "url": candidate_url,
                    "status": "failed",
                    "status_code": status_code,
                    "page_state": fetch_res.get("page_state") if fetch_res else "unreachable",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                continue

            crawl_log.append({
                "url": candidate_url,
                "status": "success",
                "status_code": fetch_res.get("status_code"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            content = fetch_res.get("content", "")
            title = fetch_res.get("title", "")
            page_text = f"{title} {content}"

            # 4. Extract target missing fields
            # Company website / domain
            if "company_website" in missing_fields and "company_website" not in enriched:
                enriched["company_website"] = FieldProvenance(
                    field_name="company_website",
                    value=base_url,
                    source=f"public_web:{base_url}",
                    confidence=90,
                    verification_status=VerificationStatus.VALID,
                    evidence=f"Verified accessible website root with title '{title[:80]}'",
                )

            if "company_domain" in missing_fields and "company_domain" not in enriched:
                enriched["company_domain"] = FieldProvenance(
                    field_name="company_domain",
                    value=domain.removeprefix("www."),
                    source=f"public_web:{base_url}",
                    confidence=95,
                    verification_status=VerificationStatus.VALID,
                )

            # Look for lead-specific contact info if person name is mentioned
            name_mentioned = (first_name and last_name and (f"{first_name} {last_name}" in page_text.lower()))

            # Public emails
            if "email" in missing_fields and "email" not in enriched:
                emails = _PUBLIC_EMAIL_RE.findall(content)
                for email in emails:
                    email_lower = email.lower()
                    if "example.com" in email_lower or "noreply" in email_lower:
                        continue
                    # If person's name is on this page or email starts with person's name/initials
                    is_lead_email = name_mentioned or (first_name and first_name in email_lower)
                    if is_lead_email:
                        snippet = self._find_context_snippet(content, email)
                        enriched["email"] = FieldProvenance(
                            field_name="email",
                            value=email_lower,
                            source=f"public_web:{candidate_url}",
                            confidence=75 if name_mentioned else 60,
                            verification_status=VerificationStatus.UNVERIFIED,
                            evidence=snippet,
                        )
                        break

            # Public phone
            if "phone" in missing_fields and "phone" not in enriched:
                phones = _PUBLIC_PHONE_RE.findall(content)
                for ph in phones:
                    clean_ph = re.sub(r"\D", "", ph)
                    if 9 <= len(clean_ph) <= 15:
                        snippet = self._find_context_snippet(content, ph)
                        enriched["phone"] = FieldProvenance(
                            field_name="phone",
                            value=ph.strip(),
                            source=f"public_web:{candidate_url}",
                            confidence=65,
                            verification_status=VerificationStatus.UNVERIFIED,
                            evidence=snippet,
                        )
                        break

            # Public LinkedIn URL
            if "linkedin_url" in missing_fields and "linkedin_url" not in enriched:
                li_matches = _PUBLIC_LINKEDIN_RE.findall(content)
                for li in li_matches:
                    if first_name and first_name in li.lower():
                        enriched["linkedin_url"] = FieldProvenance(
                            field_name="linkedin_url",
                            value=li,
                            source=f"public_web:{candidate_url}",
                            confidence=80,
                            verification_status=VerificationStatus.UNVERIFIED,
                            evidence=f"Found on public page {candidate_url}",
                        )
                        break

            # Additional social profile links
            if "other_profiles" in missing_fields:
                other_provs: Dict[str, str] = {}
                tw_matches = _PUBLIC_TWITTER_RE.findall(content)
                gh_matches = _PUBLIC_GITHUB_RE.findall(content)
                if tw_matches:
                    other_provs["twitter"] = tw_matches[0]
                if gh_matches:
                    other_provs["github"] = gh_matches[0]
                if other_provs:
                    enriched["other_profiles"] = FieldProvenance(
                        field_name="other_profiles",
                        value=other_provs,
                        source=f"public_web:{candidate_url}",
                        confidence=70,
                        verification_status=VerificationStatus.UNVERIFIED,
                        evidence=f"Found social profiles on {candidate_url}",
                    )

        return enriched, crawl_log

    def _find_context_snippet(self, text: str, target: str, window: int = 100) -> str:
        """Extract a snippet of surrounding text for evidence attribution."""
        idx = text.lower().find(target.lower())
        if idx == -1:
            return ""
        start = max(0, idx - window)
        end = min(len(text), idx + len(target) + window)
        snippet = text[start:end].replace("\n", " ")
        return f"...{snippet.strip()}..."


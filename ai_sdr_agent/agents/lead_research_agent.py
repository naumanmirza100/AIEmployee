"""
Lead Research & Enrichment Agent
---------------------------------
Finds B2B sales leads matching the company's Ideal Customer Profile.

Sources (in priority order):
  1. Apollo.io REST API  — if APOLLO_API_KEY is set
  2. Apify              — if APIFY_API_TOKEN is set
  3. Groq AI generation — fallback, always available
"""

import json
import logging
import os
import re
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

APOLLO_SEARCH_URL = "https://api.apollo.io/v1/people/search"
APIFY_BASE = "https://api.apify.com/v2"

# Default Apify actor — Google Search scraper (free, no Bright Data needed)
DEFAULT_APIFY_ACTOR = "apify/google-search-scraper"

# Employee-count bands used by code_crafter/leads-finder's `size` filter.
_LEADS_FINDER_BANDS = [
    (1, 10), (11, 20), (21, 50), (51, 100), (101, 200),
    (201, 500), (501, 1000), (1001, 2000), (2001, 5000),
    (5001, 10000), (10001, None),
]


def _employee_bands(min_size, max_size):
    """Return the leads-finder `size` band labels overlapping [min,max].
    e.g. min=9 max=60 → ['1-10','11-20','21-50','51-100']. Empty → no filter."""
    try:
        lo = int(min_size) if min_size not in (None, '') else None
        hi = int(max_size) if max_size not in (None, '') else None
    except (TypeError, ValueError):
        return []
    if lo is None and hi is None:
        return []
    lo = lo if lo is not None else 1
    hi = hi if hi is not None else 10**9
    out = []
    for b_lo, b_hi in _LEADS_FINDER_BANDS:
        top = b_hi if b_hi is not None else 10**9
        if b_lo <= hi and top >= lo:  # overlaps [lo, hi]
            # leads-finder's API expects plain-hyphen band labels, e.g. "51-100".
            out.append(f"{b_lo}-{b_hi}" if b_hi is not None else f"{b_lo}+")
    return out


# Common location aliases → the canonical lowercase value leads-finder expects.
_LOCATION_ALIASES = {
    'usa': 'united states', 'us': 'united states', 'u.s.': 'united states',
    'u.s.a.': 'united states', 'america': 'united states',
    'united states of america': 'united states',
    'uk': 'united kingdom', 'u.k.': 'united kingdom', 'britain': 'united kingdom',
    'england': 'united kingdom', 'uae': 'united arab emirates',
}


def _norm(v):
    """Lowercase + trim a free-text enum value (industries, keywords)."""
    return str(v or '').strip().lower()


def _norm_location(v):
    """Normalise a location to the actor's lowercase enum, applying aliases."""
    s = _norm(v)
    return _LOCATION_ALIASES.get(s, s)


def _fix_enum_input(actor_input, err_msg):
    """Repair an Apify "not one of the allowed values" validation error.

    Apify reports these as, e.g.:
      Field input.contact_location.0 must be equal to one of the allowed values:
      "united states", "germany", "india", ...

    We parse the field path and the allowed list, drop any of our values that
    aren't allowed (empty field → removed entirely), and return the fixed input.
    Returns None when the error isn't a repairable enum error (caller then
    surfaces the message as-is). Generic — works for any actor / any array field.
    """
    if 'allowed values' not in (err_msg or ''):
        return None
    # field path: input.<field>[.<index>]
    m = re.search(r'input\.([A-Za-z0-9_]+)', err_msg)
    if not m:
        return None
    field = m.group(1)
    if field not in actor_input or not isinstance(actor_input.get(field), list):
        return None
    # allowed values are the quoted strings after "allowed values:"
    tail = err_msg.split('allowed values', 1)[1]
    allowed = {a.strip().lower() for a in re.findall(r'"([^"]+)"', tail)}
    if not allowed:
        return None
    kept = [v for v in actor_input[field] if str(v).strip().lower() in allowed]
    new_input = dict(actor_input)
    if kept:
        new_input[field] = kept
    else:
        new_input.pop(field, None)  # nothing valid → drop the filter entirely
    # If nothing actually changed, don't loop forever.
    if new_input.get(field) == actor_input.get(field) and field in new_input:
        return None
    return new_input


def _apify_err(resp):
    """Extract a readable error message from an Apify error response."""
    try:
        j = resp.json()
        err = j.get('error', j)
        if isinstance(err, dict):
            return str(err.get('message') or err.get('type') or j)[:400]
        return str(j)[:400]
    except Exception:
        return (resp.text or '')[:400]


def _size_to_int(val):
    """Best-effort company-size → int. Accepts an int, or a band string like
    '201-500' / '10001+' (takes the lower bound)."""
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        import re as _re
        m = _re.search(r'\d[\d,]*', val)
        if m:
            try:
                return int(m.group(0).replace(',', ''))
            except ValueError:
                return None
    return None

# Apollo employee-range strings
APOLLO_SIZE_BUCKETS = [
    (1, 10, "1,10"),
    (11, 50, "11,50"),
    (51, 200, "51,200"),
    (201, 500, "201,500"),
    (501, 1000, "501,1000"),
    (1001, 5000, "1001,5000"),
    (5001, 10000, "5001,10000"),
]


class LeadResearchAgent:
    """Finds and enriches leads against an ICP profile."""

    def __init__(self, company=None, apollo_api_key: str = None,
                 apify_token: str = None, apify_actor: str = None):
        # Apollo & Apify are third-party data services (not LLM providers) — still from env
        # Per-user keys (apollo_api_key etc.) take priority over env/settings
        self.apollo_api_key = (
            apollo_api_key
            or getattr(settings, 'APOLLO_API_KEY', None)
            or os.environ.get('APOLLO_API_KEY', '')
        ).strip()

        self.apify_token = (
            apify_token
            or getattr(settings, 'APIFY_API_TOKEN', None)
            or os.environ.get('APIFY_API_TOKEN', '')
        ).strip()

        self.apify_actor = (
            apify_actor
            or getattr(settings, 'APIFY_ACTOR_ID', None)
            or os.environ.get('APIFY_ACTOR_ID', '')
            or DEFAULT_APIFY_ACTOR
        ).strip()

        # Groq LLM key — resolved per-company through platform key service
        self._key_ctx = None
        self.groq_client = None

        if company is not None:
            from ai_sdr_agent.agents.sdr_key_resolver import resolve_sdr_groq_client
            self.groq_client, self._key_ctx = resolve_sdr_groq_client(company)
        else:
            logger.warning(
                "LeadResearchAgent initialised without a company — no LLM key resolved."
            )

        self.model = getattr(settings, 'GROQ_MODEL', 'openai/gpt-oss-20b')

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search_leads(self, icp_profile, count: int = 20, source: str = 'auto') -> list[dict]:
        """Return a list of raw lead dicts for the given ICP profile."""
        if source == 'apify':
            if not self.apify_token:
                raise ValueError(
                    'Apify API token not configured. '
                    'Go to SDR Agent → Settings and enter your Apify API token.'
                )
            return self._search_apify(icp_profile, count)
        if source == 'apollo':
            if not self.apollo_api_key:
                raise ValueError(
                    'Apollo API key not configured. '
                    'Go to SDR Agent → Settings and enter your Apollo.io API key.'
                )
            return self._search_apollo(icp_profile, count)
        if source in ('ai', 'ai_generated'):
            return self._generate_ai_leads(icp_profile, count)
        # auto priority — apify only if both token AND actor are set
        if self.apollo_api_key:
            return self._search_apollo(icp_profile, count)
        if self.apify_token and self.apify_actor:
            return self._search_apify(icp_profile, count)
        return self._generate_ai_leads(icp_profile, count)

    @property
    def source_label(self) -> str:
        if self.apollo_api_key:
            return 'apollo'
        if self.apify_token:
            return 'apify'
        return 'ai_generated'

    @property
    def available_sources(self) -> list[str]:
        sources = ['ai']
        if self.apify_token:
            sources.insert(0, 'apify')
        if self.apollo_api_key:
            sources.insert(0, 'apollo')
        return sources

    # ------------------------------------------------------------------
    # Apollo.io
    # ------------------------------------------------------------------

    def _search_apollo(self, icp, count: int) -> list[dict]:
        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": self.apollo_api_key,
        }
        payload = {
            "page": 1,
            "per_page": min(count, 25),
        }

        if icp.job_titles:
            payload["person_titles"] = icp.job_titles[:10]

        if icp.locations:
            payload["person_locations"] = icp.locations[:5]

        size_min = icp.company_size_min or 0
        size_max = icp.company_size_max or 999_999
        if icp.company_size_min or icp.company_size_max:
            payload["organization_num_employees_ranges"] = [
                label for lo, hi, label in APOLLO_SIZE_BUCKETS
                if lo <= size_max and hi >= size_min
            ] or ["11,50", "51,200"]

        if icp.keywords:
            payload["q_keywords"] = " ".join(icp.keywords[:5])

        if icp.industries:
            payload["organization_industry_tag_ids"] = []
            payload["q_organization_keyword_tags"] = icp.industries[:5]

        logger.info("Apollo search payload: %s", payload)
        try:
            resp = requests.post(
                APOLLO_SEARCH_URL,
                json=payload,
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 403:
                raise ValueError(
                    "Apollo.io API access denied (403). Your plan may not include People Search. "
                    "Use Apify instead, or upgrade your Apollo plan at apollo.io."
                )
            if resp.status_code == 422:
                logger.error("Apollo 422 response: %s", resp.text)
                raise ValueError(
                    f"Apollo.io rejected the request (422). Check your API key and plan. Response: {resp.text[:200]}"
                )
            resp.raise_for_status()
            data = resp.json()
            people = data.get('people', [])
            logger.info("Apollo returned %d people", len(people))
            return [self._parse_apollo_person(p) for p in people]
        except requests.RequestException as exc:
            logger.error("Apollo API error: %s", exc)
            raise ValueError(f"Apollo.io request failed: {exc}") from exc

    def _parse_apollo_person(self, person: dict) -> dict:
        org = person.get('organization') or {}
        full_name = person.get('name', '')
        parts = full_name.split(' ', 1)
        return {
            'apollo_id': person.get('id', ''),
            'first_name': parts[0] if parts else '',
            'last_name': parts[1] if len(parts) > 1 else '',
            'full_name': full_name,
            'email': person.get('email', ''),
            'phone': person.get('phone', ''),
            'job_title': person.get('title', ''),
            'seniority_level': person.get('seniority', ''),
            'department': (person.get('departments') or [''])[0],
            'company_name': org.get('name', ''),
            'company_domain': org.get('primary_domain', ''),
            'company_industry': org.get('industry', ''),
            'company_size': org.get('estimated_num_employees') or None,
            'company_size_range': '',
            'company_location': person.get('city', ''),
            'company_technologies': (org.get('current_technologies') or [])[:10],
            'linkedin_url': person.get('linkedin_url', ''),
            'company_linkedin_url': org.get('linkedin_url', ''),
            'company_website': org.get('website_url', ''),
            'recent_news': [],
            'buying_signals': [],
            'source': 'apollo',
            'raw_data': person,
        }

    # ------------------------------------------------------------------
    # Apify
    # ------------------------------------------------------------------

    def _search_apify(self, icp, count: int) -> list[dict]:
        """Run Apify actor (async) and return mapped leads."""
        actor_id = self.apify_actor.replace('/', '~')
        actor_input = self._build_apify_input(icp, count)

        logger.info("Apify: starting actor=%s input=%s", self.apify_actor, actor_input)
        try:
            # Step 1: Start the run. Some actors validate array fields against a
            # fixed enum; if a value isn't allowed the run 400s with the list of
            # allowed values. We parse that, drop/repair the offending values,
            # and retry — so an out-of-vocabulary ICP value never fails the run
            # (works for ANY actor + ANY enum field, not just this one).
            run_resp = None
            for _attempt in range(4):
                run_resp = requests.post(
                    f"{APIFY_BASE}/acts/{actor_id}/runs",
                    json=actor_input,
                    params={'token': self.apify_token},
                    timeout=30,
                )
                if run_resp.status_code != 400:
                    break
                fixed = _fix_enum_input(actor_input, _apify_err(run_resp))
                if fixed is None:
                    break  # not an enum error we can repair — fall through to raise
                logger.info("Apify: repaired invalid enum value, retrying input=%s", fixed)
                actor_input = fixed

            if run_resp.status_code == 403:
                # Distinguish "actor needs permission approval" from a bad token.
                body = _apify_err(run_resp)
                if 'not-approved' in body or 'approvePermissions' in body:
                    approval = ''
                    try:
                        approval = run_resp.json().get('error', {}).get('data', {}).get('approvalUrl', '')
                    except Exception:
                        pass
                    logger.warning("Apify actor '%s' needs permission approval: %s", self.apify_actor, approval)
                    raise ValueError(
                        f"The Apify actor '{self.apify_actor}' needs a one-time permission approval. "
                        f"Open it in Apify Console and click Approve"
                        + (f": {approval}" if approval else "") + ", then try again."
                    )
                logger.warning("Apify 403 on actor '%s': %s", self.apify_actor, body)
                raise ValueError(f"Apify actor '{self.apify_actor}' is not accessible. Check your token or choose a different actor.")
            if run_resp.status_code == 400:
                # Surface the actor's actual validation message instead of a bare 400.
                body = _apify_err(run_resp)
                logger.error("Apify 400 for actor '%s' input=%s -> %s", self.apify_actor, actor_input, body)
                raise ValueError(f"Apify rejected the request: {body}")
            run_resp.raise_for_status()
            run_id = run_resp.json().get('data', {}).get('id')
            if not run_id:
                raise ValueError("Apify did not return a run ID")

            logger.info("Apify: run started id=%s — polling for completion", run_id)

            # Step 2: Poll until finished (max 120s)
            for _ in range(24):
                time.sleep(5)
                status_resp = requests.get(
                    f"{APIFY_BASE}/actor-runs/{run_id}",
                    params={'token': self.apify_token},
                    timeout=15,
                )
                status_resp.raise_for_status()
                run_data = status_resp.json().get('data', {})
                status = run_data.get('status', '')
                logger.info("Apify: run=%s status=%s", run_id, status)
                if status == 'SUCCEEDED':
                    break
                if status in ('FAILED', 'ABORTED', 'TIMED-OUT'):
                    raise ValueError(f"Apify run failed with status: {status}")
            else:
                raise ValueError("Apify run timed out after 120s")

            # Step 3: Fetch dataset items
            dataset_id = run_data.get('defaultDatasetId')
            items_resp = requests.get(
                f"{APIFY_BASE}/datasets/{dataset_id}/items",
                params={'token': self.apify_token, 'limit': count, 'clean': 'true'},
                timeout=30,
            )
            items_resp.raise_for_status()
            items = items_resp.json()
            if not isinstance(items, list):
                items = []

        except requests.RequestException as exc:
            logger.error("Apify request error: %s", exc)
            raise ValueError(f"Apify request failed: {exc}") from exc

        # Flatten: a google-search-scraper item holds MANY organicResults (each a
        # separate lead), so expand those instead of keeping only the first.
        leads = []
        for item in items:
            if not item:
                continue
            if isinstance(item, dict) and 'organicResults' in item:
                for r in item.get('organicResults', []):
                    lead = self._parse_google_result(r)
                    if lead:
                        leads.append(lead)
            else:
                lead = self._parse_apify_item(item)
                if lead:
                    leads.append(lead)
        logger.info("Apify: got %d raw items → %d leads parsed", len(items), len(leads))
        return leads[:count]

    def fetch_apify_runs(self, max_leads: int = 200, actor: str = None) -> list[dict]:
        """Import leads from the user's EXISTING Apify runs (created via the Apify
        UI), without starting a new run. Free-plan accounts can't run paid actors
        via the API, but they CAN read their finished runs' datasets — so this
        lets the user generate in the Apify Console and pull the results here.

        Fetches the most recent SUCCEEDED runs of `actor` (defaults to the
        configured actor, else leads-finder) and parses their dataset items.
        """
        if not self.apify_token:
            raise ValueError('Add your Apify API token in SDR Agent → Settings first.')
        actor_ref = (actor or self.apify_actor or 'code_crafter/leads-finder')
        actor_id = actor_ref.replace('/', '~')

        # List recent runs (newest first). This read works on the free plan.
        runs_resp = requests.get(
            f"{APIFY_BASE}/acts/{actor_id}/runs",
            params={'token': self.apify_token, 'desc': '1', 'limit': 10},
            timeout=25,
        )
        if runs_resp.status_code == 404:
            raise ValueError(f"No runs found for actor '{actor_ref}'. Run it once in the Apify Console first.")
        runs_resp.raise_for_status()
        runs = runs_resp.json().get('data', {}).get('items', [])
        succeeded = [r for r in runs if r.get('status') == 'SUCCEEDED' and r.get('defaultDatasetId')]
        if not succeeded:
            raise ValueError(
                f"No finished runs found for '{actor_ref}'. Generate leads in the Apify "
                "Console (the run must finish), then fetch again."
            )

        leads = []
        seen = set()
        for run in succeeded:
            if len(leads) >= max_leads:
                break
            ds = run['defaultDatasetId']
            try:
                items_resp = requests.get(
                    f"{APIFY_BASE}/datasets/{ds}/items",
                    params={'token': self.apify_token, 'clean': 'true', 'limit': max_leads},
                    timeout=30,
                )
                items_resp.raise_for_status()
                items = items_resp.json()
            except requests.RequestException as exc:
                logger.warning("Apify fetch: dataset %s failed: %s", ds, exc)
                continue
            if not isinstance(items, list):
                continue
            for item in items:
                if not item:
                    continue
                if isinstance(item, dict) and 'organicResults' in item:
                    parsed_list = [self._parse_google_result(r) for r in item.get('organicResults', [])]
                else:
                    parsed_list = [self._parse_apify_item(item)]
                for lead in parsed_list:
                    if not lead:
                        continue
                    key = (lead.get('email') or '').lower() or (lead.get('linkedin_url') or '').lower() or lead.get('full_name', '')
                    if key and key in seen:
                        continue
                    if key:
                        seen.add(key)
                    leads.append(lead)
                    if len(leads) >= max_leads:
                        break
        logger.info("Apify fetch: imported %d leads from %d runs of %s", len(leads), len(succeeded), actor_ref)
        return leads[:max_leads]

    def _build_apify_input(self, icp, count: int) -> dict:
        """Build actor input from the ICP profile for whichever Apify actor is
        configured. Different actors take completely different input shapes, so
        we branch on the actor id."""
        actor = (self.apify_actor or '').lower()

        # code_crafter/leads-finder — an Apollo-style people-search actor that
        # returns real contact data (name + email + company). Its input maps
        # 1:1 to the ICP fields. https://apify.com/code_crafter/leads-finder
        if 'leads-finder' in actor:
            return self._build_leads_finder_input(icp, count)

        # Default: apify/google-search-scraper — scrapes LinkedIn profiles off
        # Google (name/title/company only, no email). We run one query per title
        # (up to 5) and pull several pages so a single run yields many more
        # profiles than the old 3-query × 10-result cap.
        titles = icp.job_titles[:5] if icp.job_titles else ['CEO', 'CTO', 'VP Sales']
        industries = icp.industries[:2] if icp.industries else ['SaaS', 'Technology']
        location = (icp.locations or [''])[0]

        query_lines = []
        for title in titles:
            q = f'site:linkedin.com/in "{title}" {" ".join(industries[:2])}'
            if location:
                q += f' "{location}"'
            query_lines.append(q)

        # Enough pages to comfortably cover `count` across the queries.
        pages = max(2, min(5, (int(count or 20) // (len(query_lines) * 10)) + 2))
        return {
            'queries': '\n'.join(query_lines),
            'resultsPerPage': 100,
            'maxPagesPerQuery': pages,
            'mobileResults': False,
            'saveHtml': False,
            'includeUnfilteredResults': False,
        }

    def _build_leads_finder_input(self, icp, count: int) -> dict:
        """Map the ICP profile to code_crafter/leads-finder's input schema.

        This actor validates several fields against fixed enums (all lowercase),
        so free-text ICP values are normalised: lowercased, common aliases
        applied (e.g. USA → united states). Anything still invalid is auto-dropped
        by the retry logic in _search_apify, so a bad value never fails the run.
        """
        data = {
            'fetch_count': max(1, min(int(count or 20), 50000)),
            'email_status': ['validated'],
        }
        if icp.job_titles:
            data['contact_job_title'] = icp.job_titles[:20]  # free-text, no enum
        if icp.industries:
            data['company_industry'] = [_norm(v) for v in icp.industries[:20]]
        if icp.locations:
            data['contact_location'] = [_norm_location(v) for v in icp.locations[:20]]
        # ICP keywords double as company keywords for this actor.
        keywords = getattr(icp, 'keywords', None) or []
        if keywords:
            data['company_keywords'] = [_norm(v) for v in keywords[:20]]
        # Employee-count range → the actor's banded `size` filter.
        size_bands = _employee_bands(
            getattr(icp, 'company_size_min', None),
            getattr(icp, 'company_size_max', None),
        )
        if size_bands:
            data['size'] = size_bands
        return data

    def _parse_apify_item(self, item: dict) -> dict:
        """Parse Google Search Scraper result or generic Apify actor output into lead dict."""
        # Handle google-search-scraper nested format
        if 'organicResults' in item:
            leads = []
            for r in item.get('organicResults', []):
                lead = self._parse_google_result(r)
                if lead:
                    leads.append(lead)
            return leads[0] if leads else {}

        # Handle direct result (already a person object). Field fallbacks cover
        # both camelCase actors and code_crafter/leads-finder's snake_case keys
        # (email, mobile_number, linkedin, company_size, city/state/country, …).
        name = item.get('name') or item.get('fullName') or item.get('full_name') or ''
        first = item.get('firstName') or item.get('first_name') or ''
        last = item.get('lastName') or item.get('last_name') or ''
        if name and not first:
            parts = name.split(' ', 1)
            first = parts[0]
            last = parts[1] if len(parts) > 1 else ''

        # leads-finder splits location into city/state/country.
        location = (
            item.get('location') or item.get('city')
            or ', '.join([p for p in (item.get('city'), item.get('state'), item.get('country')) if p])
        )
        size_raw = item.get('companySize') or item.get('company_size')

        return {
            'apollo_id': '',
            'first_name': first,
            'last_name': last,
            'full_name': name or f"{first} {last}".strip(),
            'email': item.get('email') or item.get('emailAddress') or '',
            'phone': item.get('phone') or item.get('phoneNumber') or item.get('mobile_number') or '',
            'job_title': item.get('jobTitle') or item.get('title') or item.get('job_title') or item.get('headline') or '',
            'seniority_level': item.get('seniority') or item.get('seniority_level') or '',
            'department': item.get('department') or item.get('functional_level') or '',
            'company_name': item.get('companyName') or item.get('company_name') or item.get('company') or '',
            'company_domain': item.get('companyDomain') or item.get('company_domain') or '',
            'company_industry': item.get('industry') or item.get('company_industry') or '',
            'company_size': _size_to_int(size_raw),
            'company_size_range': size_raw if isinstance(size_raw, str) else '',
            'company_location': location or '',
            'company_technologies': item.get('technologies') or item.get('company_technologies') or [],
            'linkedin_url': item.get('linkedinUrl') or item.get('linkedin_url') or item.get('linkedin') or item.get('profileUrl') or '',
            'company_linkedin_url': item.get('company_linkedin') or '',
            'company_website': item.get('companyWebsite') or item.get('company_website') or item.get('website') or '',
            'recent_news': [],
            'buying_signals': [],
            'source': 'apify',
            'raw_data': item,
        }

    def _parse_google_result(self, result: dict) -> dict:
        """Parse a single Google organic result into a lead. Works for LinkedIn URLs."""
        url = result.get('url', '')
        title = result.get('title', '')
        description = result.get('description', '') or result.get('snippet', '')

        if 'linkedin.com/in/' not in url and 'linkedin.com/pub/' not in url:
            return {}

        # Extract name from title: "John Doe - CEO at TechCorp | LinkedIn"
        name = ''
        job_title = ''
        company = ''
        parts = title.replace(' | LinkedIn', '').replace(' - LinkedIn', '').split(' - ', 1)
        if parts:
            name = parts[0].strip()
            if len(parts) > 1:
                role_part = parts[1].strip()
                if ' at ' in role_part:
                    job_title, _, company = role_part.partition(' at ')
                elif ' @ ' in role_part:
                    job_title, _, company = role_part.partition(' @ ')
                else:
                    job_title = role_part

        first, _, last = name.partition(' ')
        return {
            'apollo_id': '',
            'first_name': first.strip(),
            'last_name': last.strip(),
            'full_name': name,
            'email': '',
            'phone': '',
            'job_title': job_title.strip(),
            'seniority_level': '',
            'department': '',
            'company_name': company.strip(),
            'company_domain': '',
            'company_industry': '',
            'company_size': None,
            'company_size_range': '',
            'company_location': '',
            'company_technologies': [],
            'linkedin_url': url,
            'company_linkedin_url': '',
            'company_website': '',
            'recent_news': [],
            'buying_signals': [description[:100]] if description else [],
            'source': 'apify',
            'raw_data': result,
        }

    # ------------------------------------------------------------------
    # Groq AI lead generation (fallback / demo)
    # ------------------------------------------------------------------

    def _generate_ai_leads(self, icp, count: int) -> list[dict]:
        if not self.groq_client:
            raise ValueError(
                "No lead source available. Configure APOLLO_API_KEY or GROQ_API_KEY."
            )

        industries = ", ".join(icp.industries) if icp.industries else "Technology, SaaS"
        titles = ", ".join(icp.job_titles) if icp.job_titles else "CEO, VP Sales, Head of Marketing"
        locations = ", ".join(icp.locations) if icp.locations else "United States"
        size = (
            f"{icp.company_size_min or 10}-{icp.company_size_max or 500}"
            if (icp.company_size_min or icp.company_size_max)
            else "10-500"
        )
        keywords = ", ".join(icp.keywords) if icp.keywords else ""

        system_prompt = (
            "You are a B2B sales data expert. "
            "Return ONLY a valid JSON array, no markdown, no extra text."
        )

        # Generate in batches of 5 to stay within Groq free-tier TPM limits
        BATCH_SIZE = 5
        all_leads = []
        batches = (count + BATCH_SIZE - 1) // BATCH_SIZE

        for batch_i in range(batches):
            batch_count = min(BATCH_SIZE, count - len(all_leads))
            if batch_count <= 0:
                break

            user_prompt = f"""Generate {batch_count} B2B sales leads matching this ICP:
Industries: {industries} | Titles: {titles} | Size: {size} employees | Locations: {locations}{" | Tech: " + keywords if keywords else ""}

Return a JSON array with {batch_count} objects, each having these keys:
first_name, last_name, full_name, email, phone, job_title, seniority_level, department,
company_name, company_domain, company_industry, company_size (integer), company_size_range,
company_location, linkedin_url, company_linkedin_url, company_website,
company_technologies (array of 2-3 strings),
recent_news (array with 1 object: title, date, summary),
buying_signals (array of 2 short strings), source ("ai_generated")

IMPORTANT URL rules:
- linkedin_url must be a full URL: "https://linkedin.com/in/firstname-lastname-xxxxx"
- company_linkedin_url must start with "https://linkedin.com/company/"
- company_website must start with "https://" (e.g. "https://acmecorp.com")
- email must be a real business email using company_domain (not gmail/yahoo)

Use realistic varied data. Each lead must be a different person at a different company."""

            try:
                resp = self.groq_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.75,
                    max_tokens=3000,
                )
                from ai_sdr_agent.agents.sdr_key_resolver import record_sdr_usage
                record_sdr_usage(self._key_ctx, getattr(resp.usage, 'total_tokens', 0))

                content = resp.choices[0].message.content.strip()

                # Strip markdown fences if present
                if "```" in content:
                    parts = content.split("```")
                    for part in parts:
                        if "[" in part or "{" in part:
                            content = part.lstrip("json").strip()
                            break

                batch_leads = json.loads(content)
                if not isinstance(batch_leads, list):
                    batch_leads = [batch_leads]

                for lead in batch_leads:
                    lead.setdefault('apollo_id', '')
                    lead.setdefault('raw_data', {})
                    lead['source'] = 'ai_generated'

                all_leads.extend(batch_leads)
                logger.info("Batch %d/%d: got %d leads", batch_i + 1, batches, len(batch_leads))

            except json.JSONDecodeError as exc:
                logger.error("Groq returned invalid JSON in batch %d: %s", batch_i + 1, exc)
                if not all_leads:
                    raise ValueError("AI returned invalid JSON — please try again.") from exc
                break
            except Exception as exc:
                logger.error("AI lead generation failed in batch %d: %s", batch_i + 1, exc)
                if not all_leads:
                    raise
                break

        if not all_leads:
            raise ValueError("No leads generated — please try again.")

        return all_leads

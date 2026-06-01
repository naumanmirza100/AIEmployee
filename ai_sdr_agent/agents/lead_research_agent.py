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
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

APOLLO_SEARCH_URL = "https://api.apollo.io/v1/people/search"
APIFY_BASE = "https://api.apify.com/v2"

# Default Apify actor — LinkedIn People Search (free, no login needed)
DEFAULT_APIFY_ACTOR = "curious_coder/linkedin-people-search-scraper"

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

    def __init__(self, apollo_api_key: str = None, apify_token: str = None,
                 apify_actor: str = None):
        # Per-user keys take priority; fall back to global env/settings
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

        groq_key = (
            getattr(settings, 'GROQ_API_KEY', None)
            or getattr(settings, 'GROQ_REC_API_KEY', None)
            or os.environ.get('GROQ_API_KEY', '')
            or os.environ.get('GROQ_REC_API_KEY', '')
        ).strip()

        self.groq_client = None
        if groq_key:
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=groq_key)
            except Exception as exc:
                logger.error("Groq init failed in LeadResearchAgent: %s", exc)

        self.model = getattr(settings, 'GROQ_MODEL', 'llama-3.1-8b-instant')

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
        if source == 'ai':
            return self._generate_ai_leads(icp_profile, count)
        # auto priority
        if self.apollo_api_key:
            return self._search_apollo(icp_profile, count)
        if self.apify_token:
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

        logger.info("Apify: starting actor=%s count=%d", self.apify_actor, count)
        try:
            # Step 1: Start the run
            run_resp = requests.post(
                f"{APIFY_BASE}/acts/{actor_id}/runs",
                json=actor_input,
                params={'token': self.apify_token},
                timeout=30,
            )
            if run_resp.status_code == 403:
                logger.warning("Apify 403 on actor '%s' — check token permissions", self.apify_actor)
                raise ValueError(f"Apify actor '{self.apify_actor}' is not accessible. Check your token or choose a different actor.")
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

        leads = [self._parse_apify_item(item) for item in items if item]
        logger.info("Apify: got %d raw items → %d leads parsed", len(items), len(leads))
        return leads[:count]

    def _build_apify_input(self, icp, count: int) -> dict:
        """Build actor input for apify/google-search-scraper from ICP profile."""
        titles = icp.job_titles[:3] if icp.job_titles else ['CEO', 'CTO', 'VP Sales']
        industries = icp.industries[:2] if icp.industries else ['SaaS', 'Technology']
        location = (icp.locations or [''])[0]

        # google-search-scraper expects newline-separated queries string
        query_lines = []
        for title in titles[:3]:
            q = f'site:linkedin.com/in "{title}" {" ".join(industries[:2])}'
            if location:
                q += f' "{location}"'
            query_lines.append(q)

        return {
            'queries': '\n'.join(query_lines),
            'resultsPerPage': 10,
            'maxPagesPerQuery': 1,
            'mobileResults': False,
            'saveHtml': False,
            'includeUnfilteredResults': False,
        }

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

        # Handle direct result (already a person object)
        name = item.get('name') or item.get('fullName') or item.get('full_name') or ''
        first = item.get('firstName') or item.get('first_name') or ''
        last = item.get('lastName') or item.get('last_name') or ''
        if name and not first:
            parts = name.split(' ', 1)
            first = parts[0]
            last = parts[1] if len(parts) > 1 else ''

        return {
            'apollo_id': '',
            'first_name': first,
            'last_name': last,
            'full_name': name or f"{first} {last}".strip(),
            'email': item.get('email') or item.get('emailAddress') or '',
            'phone': item.get('phone') or item.get('phoneNumber') or '',
            'job_title': item.get('jobTitle') or item.get('title') or item.get('headline') or '',
            'seniority_level': item.get('seniority') or '',
            'department': item.get('department') or '',
            'company_name': item.get('companyName') or item.get('company_name') or item.get('company') or '',
            'company_domain': item.get('companyDomain') or '',
            'company_industry': item.get('industry') or '',
            'company_size': item.get('companySize') or None,
            'company_size_range': '',
            'company_location': item.get('location') or item.get('city') or '',
            'company_technologies': item.get('technologies') or [],
            'linkedin_url': item.get('linkedinUrl') or item.get('linkedin_url') or item.get('profileUrl') or '',
            'company_linkedin_url': '',
            'company_website': item.get('companyWebsite') or item.get('website') or '',
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

Use realistic varied data matching the ICP."""

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

"""
Lead Research & Enrichment Agent
---------------------------------
Finds B2B sales leads matching the company's Ideal Customer Profile.

Sources (in priority order):
  1. Apollo.io REST API  — if APOLLO_API_KEY is set
  2. Apify              — if APIFY_API_TOKEN is set

There is deliberately no AI source. Leads must be real people: an LLM asked for leads invents names, emails
and LinkedIn URLs that look genuine, and outreach would then go to them. With no provider, search fails loudly.
"""

import logging
import os
import re
import time

import requests
from django.conf import settings
from ai_sdr_agent.agents.lead_research_verification import host_of, role_keys
from ai_sdr_agent.agents.lead_validator import dedupe_leads, normalize_linkedin_url

logger = logging.getLogger(__name__)

# People API Search. It costs no credits, and by design returns no emails or phone numbers and only part of the
# surname; contact details need Apollo's enrichment endpoints. https://docs.apollo.io/reference/people-api-search
APOLLO_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_people/api_search"
APIFY_BASE = "https://api.apify.com/v2"
APIFY_POLL_ATTEMPTS = 60  # 5 seconds apart


def _is_error_item(item) -> bool:
    """True for a dataset item that is the actor reporting a failure, not a lead.

    Some actors "succeed" at the run level but write {"error": "..."} as their only
    output (e.g. leads-finder on the free plan when started via the API).
    """
    return isinstance(item, dict) and bool(item.get('error')) and not any(
        item.get(k) for k in ('email', 'name', 'fullName', 'full_name', 'first_name', 'firstName', 'linkedin')
    )


def _apify_headers(token: str) -> dict:
    # In a header, not ?token=: requests puts the URL in its exceptions, and those messages reach the API response.
    return {'Authorization': f'Bearer {token}'}


def _raise_for_error_items(items, actor: str):
    errors = [str(i.get('error')) for i in items if _is_error_item(i)]
    if not errors or len(errors) != len([i for i in items if i]):
        return
    message = errors[0][:300]
    if 'free' in message.lower() and 'plan' in message.lower():
        raise ValueError(
            f"Apify says: {message} Run the '{actor}' actor on the Apify website with your filters, "
            "then click 'Fetch from Apify' here to import the results (or upgrade your Apify plan "
            "to run it from this app)."
        )
    raise ValueError(f"The Apify actor '{actor}' returned an error instead of leads: {message}")


def apify_actor_page_url(actor: str) -> str:
    """Public Apify Store page for an actor id like "code_crafter/leads-finder"."""
    return f"https://apify.com/{(actor or '').replace('~', '/').strip('/')}"


class ApifyApprovalRequired(ValueError):
    """The Apify actor needs a one-time permission approval by its user.

    Only the user can approve it (it is tied to their Apify account), so callers
    surface ``approval_url`` as a link for them to open.
    """

    def __init__(self, actor: str, approval_url: str = ''):
        self.actor = actor
        # Apify's own approval link when it sends one, else the actor's Store page.
        self.approval_url = approval_url or apify_actor_page_url(actor)
        super().__init__(
            f"The Apify actor '{actor}' needs a one-time permission approval. "
            f"Open it on Apify and click Approve, then try again: {self.approval_url}"
        )

NO_SOURCE_MESSAGE = (
    'Lead search needs an Apollo.io or Apify key. Add one under SDR Agent → Settings, '
    'or bring your leads in from a file (Import CSV) or add them one by one.'
)


class NoLeadSource(ValueError):
    """Neither an Apollo nor an Apify key is set, so there is nothing to search: the person adds one."""

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
    (10001, 999_999, "10001,1000000"),
]


def _title_words(title: str) -> set:
    text = re.sub(r'\bvice president\b', 'vp', (title or '').lower())
    return set(re.findall(r'[a-z0-9]+', text)) - {'of', 'and', 'the', 'for', 'at', 'in', 'senior', 'sr'}


def title_matches_icp(title: str, wanted: list) -> bool:
    """Does this job title fit the ICP? Search engines match any page that mentions a title anywhere, which
    returns people who only list it in past experience."""
    if not wanted or not title:
        return True
    roles, words = role_keys(title), _title_words(title)
    for candidate in wanted:
        if role_keys(candidate) & roles:
            return True
        wanted_words = _title_words(candidate)
        if wanted_words and wanted_words <= words:
            return True
    return False


def _title_query(title: str) -> str:
    """A quoted title for Google. "VP Sales" alone misses most people, who write "VP of Sales" or spell it out."""
    vp = re.match(r'(?:vp|vice president)\s+(?:of\s+)?(.+)', title.strip(), re.IGNORECASE)
    if not vp:
        return f'"{title}"'
    area = vp.group(1)
    return f'("VP {area}" OR "VP of {area}" OR "Vice President of {area}")'


def _clean_truncated(text: str) -> str:
    """Google cuts long titles with an ellipsis; "Head of AI & ..." is not a job title."""
    return re.sub(r'[\s&,|/-]*(\.\.\.|\u2026)\s*$', '', text or '').strip()


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
            try:
                self.groq_client, self._key_ctx = resolve_sdr_groq_client(company)
            except Exception as exc:
                logger.warning(
                    "LeadResearchAgent: key resolution failed for company %s (%s) — using deterministic extraction.",
                    company, exc
                )
                self.groq_client = None
                self._key_ctx = None
        else:
            logger.warning(
                "LeadResearchAgent initialised without a company — no LLM key resolved."
            )

        self.model = getattr(settings, 'GROQ_MODEL', 'openai/gpt-oss-20b')

        from ai_sdr_agent.agents.lead_research_workflow import LeadResearchWorkflow
        self.workflow = LeadResearchWorkflow(
            groq_client=self.groq_client,
            model=self.model,
            key_ctx=self._key_ctx,
            apify_token=self.apify_token,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def research_lead(self, lead_or_id, campaign=None) -> dict:
        """
        Research an existing lead (independent of its discovery origin).
        Accepts an SDRLead instance, an integer ID, or a lead dict.
        Updates lead record non-destructively and returns structured profile.
        """
        from ai_sdr_agent.models import SDRLead
        lead_obj = None
        if isinstance(lead_or_id, (int, str)) and str(lead_or_id).isdigit():
            lead_obj = SDRLead.all_objects.filter(pk=int(lead_or_id)).first()
            if not lead_obj:
                raise ValueError(f"Lead with id {lead_or_id} not found.")
            lead = lead_obj
        elif hasattr(lead_or_id, 'pk'):
            lead_obj = lead_or_id
            lead = lead_obj
        else:
            lead = lead_or_id

        # Mark running status in lead record if model instance
        if lead_obj:
            if not isinstance(lead_obj.raw_data, dict):
                lead_obj.raw_data = {}
            lead_obj.raw_data['research_status'] = 'running'
            lead_obj.save(update_fields=['raw_data', 'updated_at'])

        try:
            profile = self.workflow.execute_research(lead, campaign=campaign)

            if lead_obj:
                update_fields = ['raw_data', 'updated_at']
                lead_obj.raw_data['research_profile'] = profile
                lead_obj.raw_data['research_status'] = profile.get('research_status', 'completed')

                # Only what research established goes on the lead. Other agents read these fields as fact.
                comp_res = profile.get('company_research', {})
                if not lead_obj.company_industry and comp_res.get('industry') and comp_res.get('industry').lower() != 'unknown':
                    lead_obj.company_industry = comp_res['industry'][:255]
                    update_fields.append('company_industry')

                verification = profile.get('verification') or {}
                site = verification.get('website') or {}
                if site.get('status') == 'verified' and site.get('url'):
                    if not lead_obj.company_website:
                        lead_obj.company_website = site['url'].rstrip('/')
                        update_fields.append('company_website')
                    if not lead_obj.company_domain:
                        lead_obj.company_domain = host_of(site['url'])
                        update_fields.append('company_domain')

                prospect_res = profile.get('prospect_research', {})
                if not lead_obj.seniority_level and prospect_res.get('seniority') and prospect_res.get('seniority').lower() != 'unknown':
                    lead_obj.seniority_level = prospect_res['seniority'][:100]
                    update_fields.append('seniority_level')
                if not lead_obj.department and prospect_res.get('department') and prospect_res.get('department').lower() != 'unknown':
                    lead_obj.department = prospect_res['department'][:100]
                    update_fields.append('department')

                prospect_check = verification.get('prospect') or {}
                flags = [f for f in (lead_obj.data_quality_flags or []) if not f.startswith('Research: ')]
                has_linkedin = bool(lead_obj.linkedin_url and 'linkedin.com/in/' in lead_obj.linkedin_url.lower())
                # Only penalize genuinely conflicting or outdated roles, or not_found if no LinkedIn profile exists
                if prospect_check.get('status') in ('conflict', 'outdated'):
                    flags.append(f"Research: {prospect_check.get('reason')}")
                elif prospect_check.get('status') == 'not_found' and not has_linkedin and lead_obj.source not in ('apollo', 'apify'):
                    flags.append(f"Research: {prospect_check.get('reason')}")
                lead_obj.data_quality_flags = flags
                update_fields.append('data_quality_flags')

                signals = profile.get('company_signals', [])
                if signals:
                    existing_signals = list(lead_obj.buying_signals or [])
                    new_signals = [s.get('description', '') for s in signals if s.get('description')]
                    combined_signals = list(dict.fromkeys(new_signals + existing_signals))
                    lead_obj.buying_signals = combined_signals[:10]
                    update_fields.append('buying_signals')

                    new_news = [
                        {
                            'title': s.get('description', '')[:120],
                            'date': s.get('published_at', ''),
                            'summary': s.get('description', ''),
                            'url': s.get('source_url', ''),
                        }
                        for s in signals if s.get('description')
                    ]
                    new_urls = {n['url'] for n in new_news}
                    # Newest first, or re-research never gets past the cap; replaced by URL so nothing repeats
                    kept_news = [n for n in (lead_obj.recent_news or [])
                                 if not (isinstance(n, dict) and n.get('url') in new_urls)]
                    lead_obj.recent_news = (new_news + kept_news)[:10]
                    update_fields.append('recent_news')

                lead_obj.save(update_fields=list(set(update_fields)))

            return profile

        except Exception as exc:
            logger.error("LeadResearchAgent.research_lead failed for lead %s: %s", lead_or_id, exc, exc_info=True)
            if lead_obj:
                lead_obj.raw_data['research_status'] = 'failed'
                lead_obj.raw_data['research_error'] = str(exc)
                lead_obj.save(update_fields=['raw_data', 'updated_at'])
            raise

    def research_leads_batch(self, leads, campaign=None) -> list[dict]:
        """
        Research multiple existing leads in a batch.
        Isolates failures so one failing lead does not abort the batch.
        """
        results = []
        for item in leads:
            try:
                profile = self.research_lead(item, campaign=campaign)
                results.append(profile)
            except Exception as exc:
                lead_id = str(getattr(item, 'id', '') or (item.get('id') if isinstance(item, dict) else item))
                logger.warning("Batch research failed for lead %s: %s", lead_id, exc)
                results.append({
                    'lead_id': lead_id,
                    'research_status': 'failed',
                    'error': str(exc),
                })
        return results

    def search_leads(self, icp_profile, count: int = 20, source: str = 'auto') -> list[dict]:
        """Return a list of raw lead dicts for the given ICP profile."""
        if source == 'apify':
            if not self.apify_token:
                raise NoLeadSource(
                    'Apify API token not configured. '
                    'Go to SDR Agent → Settings and enter your Apify API token.'
                )
            return dedupe_leads(self._search_apify(icp_profile, count))
        if source == 'apollo':
            if not self.apollo_api_key:
                raise NoLeadSource(
                    'Apollo API key not configured. '
                    'Go to SDR Agent → Settings and enter your Apollo.io API key.'
                )
            return dedupe_leads(self._search_apollo(icp_profile, count))
        if source in ('ai', 'ai_generated'):
            raise ValueError(
                'AI-generated leads are no longer available: they were invented people, not real prospects. '
                'Add an Apollo.io key or an Apify token in SDR Agent → Settings.'
            )

        # auto priority — each provider gets its turn, so one provider's outage doesn't end the search
        providers = []
        if self.apollo_api_key:
            providers.append(('Apollo.io', self._search_apollo))
        if self.apify_token and self.apify_actor:
            return self._search_apify(icp_profile, count)
        raise NoLeadSource(NO_SOURCE_MESSAGE)

    def _apify_headers(self) -> dict:
        """The token goes in a header: in the web address it was written into the log, the research record and the
        message on the customer's screen by any failed request (CO-142)."""
        return {'Authorization': f'Bearer {self.apify_token}'}
            providers.append(('Apify', self._search_apify))
        if not providers:
            raise ValueError(
                'No lead source available. Add an Apollo.io key or an Apify token in SDR Agent → Settings.'
            )

        failures = []
        for name, search in providers:
            try:
                leads = dedupe_leads(search(icp_profile, count))
            except ApifyApprovalRequired:
                raise  # Only the user can fix this, and the UI shows them the link
            except ValueError as exc:
                logger.warning("Lead search: %s failed, trying the next source: %s", name, exc)
                failures.append(f"{name}: {exc}")
                continue
            if leads:
                return leads
            logger.info("Lead search: %s returned no leads", name)
        if failures:
            raise ValueError(' | '.join(failures))
        return []

    @property
    def source_label(self) -> str:
        if self.apollo_api_key:
            return 'apollo'
        if self.apify_token:
            return 'apify'
        return 'none'

    @property
    def available_sources(self) -> list[str]:
        sources = []
        if self.apify_token:
            sources.insert(0, 'apify')
        if self.apollo_api_key:
            sources.append('apollo')
        if self.apify_token:
            sources.append('apify')
        return sources

    # ------------------------------------------------------------------
    # Apollo.io
    # ------------------------------------------------------------------

    def _search_apollo(self, icp, count: int) -> list[dict]:
        headers = {
            "Cache-Control": "no-cache",
            "X-Api-Key": self.apollo_api_key,
        }
        # This endpoint takes its filters in the query string, with [] on list parameters.
        params = {
            "page": 1,
            "per_page": min(count, 100),
        }

        if icp.job_titles:
            params["person_titles[]"] = icp.job_titles[:10]

        if icp.locations:
            params["person_locations[]"] = icp.locations[:5]

        size_min = icp.company_size_min or 0
        size_max = icp.company_size_max or 999_999
        if icp.company_size_min or icp.company_size_max:
            params["organization_num_employees_ranges[]"] = [
                label for lo, hi, label in APOLLO_SIZE_BUCKETS
                if lo <= size_max and hi >= size_min
            ]

        if icp.keywords:
            params["q_keywords"] = " ".join(icp.keywords[:5])

        if icp.industries:
            params["organization_industries[]"] = icp.industries[:5]

        logger.info("Apollo search params: %s", params)
        try:
            resp = requests.post(APOLLO_SEARCH_URL, params=params, headers=headers, timeout=30)
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(2)
                resp = requests.post(APOLLO_SEARCH_URL, params=params, headers=headers, timeout=30)
            if resp.status_code == 401:
                raise ValueError("Apollo.io rejected the API key (401). Check it in SDR Agent → Settings.")
            if resp.status_code == 403:
                raise ValueError(
                    "Apollo.io API access denied (403). Your plan or key may not include People Search. "
                    "Use Apify instead, or upgrade your Apollo plan at apollo.io."
                )
            if resp.status_code == 422:
                logger.error("Apollo 422 response: %s", resp.text)
                raise ValueError(
                    f"Apollo.io rejected the request (422). Check your API key and plan. Response: {resp.text[:200]}"
                )
            if resp.status_code == 429:
                raise ValueError("Apollo.io rate limit reached (429). Try again in a few minutes.")
            resp.raise_for_status()
            data = resp.json()
            people = data.get('people') or []
            logger.info("Apollo returned %d people", len(people))
            return [self._parse_apollo_person(p) for p in people]
        except requests.RequestException as exc:
            logger.error("Apollo API error: %s", exc)
            raise ValueError(f"Apollo.io request failed: {exc}") from exc

    def _parse_apollo_person(self, person: dict) -> dict:
        org = person.get('organization') or {}
        first = (person.get('first_name') or '').strip()
        # The search endpoint masks surnames in last_name_obfuscated ("Hu***n"). That is not a name, so it stays out.
        last = (person.get('last_name') or '').strip()
        full_name = (person.get('name') or f"{first} {last}").strip()
        if not first and full_name:
            first, _, last = full_name.partition(' ')

        # Apollo stands in email_not_unlocked@domain.com for an email the plan may not see; that is no address.
        email = (person.get('email') or '').strip()
        if 'not_unlocked' in email.lower():
            email = ''
        numbers = person.get('phone_numbers') or []
        phone = person.get('phone') or (numbers[0].get('sanitized_number') or numbers[0].get('raw_number') or ''
                                        if numbers and isinstance(numbers[0], dict) else '')
        return {
            'apollo_id': person.get('id', ''),
            'first_name': first,
            'last_name': last,
            'full_name': full_name,
            'email': email,
            'phone': phone,
            'job_title': person.get('title') or '',
            'seniority_level': person.get('seniority') or '',
            'department': (person.get('departments') or [''])[0],
            'company_name': org.get('name') or '',
            'company_domain': org.get('primary_domain') or '',
            'company_industry': org.get('industry') or '',
            'company_size': org.get('estimated_num_employees') or None,
            'company_size_range': '',
            # Apollo's city is the person's. Their company can be somewhere else entirely.
            'company_location': ', '.join(p for p in (org.get('city'), org.get('country')) if p),
            'company_technologies': (org.get('current_technologies') or [])[:10],
            'linkedin_url': person.get('linkedin_url') or '',
            'company_linkedin_url': org.get('linkedin_url') or '',
            'company_website': org.get('website_url') or '',
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
                    headers=_apify_headers(self.apify_token),
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
                    raise ApifyApprovalRequired(self.apify_actor, approval)
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

            # Step 2: Poll until finished (max 300s)
            for _ in range(APIFY_POLL_ATTEMPTS):
                time.sleep(5)
                status_resp = requests.get(
                    f"{APIFY_BASE}/actor-runs/{run_id}",
                    headers=_apify_headers(self.apify_token),
                    timeout=15,
                )
                if status_resp.status_code == 429 or status_resp.status_code >= 500:
                    continue  # A failed poll says nothing about the run; ask again
                status_resp.raise_for_status()
                run_data = status_resp.json().get('data', {})
                status = run_data.get('status', '')
                logger.info("Apify: run=%s status=%s", run_id, status)
                if status == 'SUCCEEDED':
                    break
                if status in ('FAILED', 'ABORTED', 'TIMED-OUT'):
                    detail = run_data.get('statusMessage') or ''
                    raise ValueError(f"Apify run failed with status: {status}. {detail}".strip())
            else:
                # An abandoned run keeps spending the user's credit
                requests.post(f"{APIFY_BASE}/actor-runs/{run_id}/abort",
                              headers=_apify_headers(self.apify_token), timeout=10)
                raise ValueError("Apify run timed out after 300s")

            # Step 3: Fetch dataset items
            dataset_id = run_data.get('defaultDatasetId')
            items_resp = requests.get(
                f"{APIFY_BASE}/datasets/{dataset_id}/items",
                params={'limit': count, 'clean': 'true'},
                headers=_apify_headers(self.apify_token),
                timeout=30,
            )
            items_resp.raise_for_status()
            items = items_resp.json()
            if not isinstance(items, list):
                items = []
            _raise_for_error_items(items, self.apify_actor)

        except requests.RequestException as exc:
            logger.error("Apify request error: %s", exc)
            raise ValueError(f"Apify request failed: {exc}") from exc

        # Flatten: a google-search-scraper item holds MANY organicResults (each a
        # separate lead), so expand those instead of keeping only the first.
        leads = []
        for item in items:
            if not item or _is_error_item(item):
                continue
            if isinstance(item, dict) and 'organicResults' in item:
                for r in item.get('organicResults', []):
                    lead = self._parse_google_result(r)
                    # Actors filter by title themselves; Google only matches text somewhere on the page
                    if lead and title_matches_icp(lead['job_title'], icp.job_titles):
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
            params={'desc': '1', 'limit': 10},
            headers=_apify_headers(self.apify_token),
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
                    params={'clean': 'true', 'limit': max_leads},
                    headers=_apify_headers(self.apify_token),
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
                if not item or _is_error_item(item):
                    continue   # skip runs that only contain an actor error (e.g. free-plan API runs)
                if isinstance(item, dict) and 'organicResults' in item:
                    parsed_list = [self._parse_google_result(r) for r in item.get('organicResults', [])]
                else:
                    parsed_list = [self._parse_apify_item(item)]
                for lead in parsed_list:
                    if not lead:
                        continue
                    key = (lead.get('email') or '').lower() or normalize_linkedin_url(lead.get('linkedin_url')) or lead.get('full_name', '')
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

        # evascrape/b2b-leads-finder — Apollo-style scraper with filters or Apollo URL
        if 'evascrape' in actor:
            return self._build_evascrape_input(icp, count)

        # code_crafter/leads-finder — an Apollo-style people-search actor that
        # returns real contact data (name + email + company). Its input maps
        # 1:1 to the ICP fields. https://apify.com/code_crafter/leads-finder
        if 'leads-finder' in actor:
            return self._build_leads_finder_input(icp, count)

        # Default: apify/google-search-scraper — scrapes LinkedIn profiles off
        # Google (name/title/company only, no email). We run one query per title
        # (up to 5) and pull several pages so a single run yields many more
        # profiles than the old 3-query × 10-result cap.
        titles = icp.job_titles[:5]
        industries = icp.industries[:2]
        location = (icp.locations or [''])[0]
        if not titles and not industries:
            # Filling these in with defaults would return people the user never asked for
            raise ValueError('Add job titles or industries to your ICP before searching.')

        query_lines = []
        for title in titles or ['']:
            q = 'site:linkedin.com/in'
            if title:
                q += f' {_title_query(title)}'
            if industries:
                q += f' {" ".join(industries)}'
            if location:
                q += f' "{location}"'
            query_lines.append(q)

        # Enough pages to comfortably cover `count` across the queries.
        pages = max(2, min(5, (int(count or 20) // (len(query_lines) * 10)) + 2))
        return {
            'queries': '\n'.join(query_lines),
            'maxPagesPerQuery': pages,
            'mobileResults': False,
            'saveHtml': False,
            'includeUnfilteredResults': False,
        }

    def _build_evascrape_input(self, icp, count: int) -> dict:
        """Map the ICP profile to evascrape/b2b-leads-finder's input schema.
        Supports direct filter search and Apollo-style criteria.
        """
        data = {
            'searchMode': 'filters',
            'maxResults': max(10, min(int(count or 10), 100)),  # The actor rejects anything under 10
            'includeUnverifiedEmails': False,
            'verifyEmails': False,
        }
        # Only the user's filters. The actor refuses an empty search, which is better than guessing one.
        if icp.job_titles:
            data['jobTitles'] = icp.job_titles[:20]
        if icp.locations:
            data['locations'] = [_norm_location(v) for v in icp.locations[:20]]
        if icp.industries:
            data['industries'] = [_norm(v) for v in icp.industries[:20]]

        size_bands = _employee_bands(
            getattr(icp, 'company_size_min', None),
            getattr(icp, 'company_size_max', None),
        )
        if size_bands:
            data['companySizes'] = size_bands

        keywords = getattr(icp, 'keywords', None) or []
        if keywords:
            data['companyKeywords'] = [_norm(v) for v in keywords[:20]]

        return data

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
        # The company's address when the actor gives one: its city/state/country are the person's.
        location = (
            ', '.join([p for p in (item.get('company_city'), item.get('company_country')) if p])
            or item.get('location')
            or ', '.join([p for p in (item.get('city'), item.get('state'), item.get('country')) if p])
        )
        size_raw = item.get('companySize') or item.get('company_size')

        # Personal numbers only: a switchboard saved as the lead's phone would get dialled as if it were theirs.
        phone = item.get('phone') or item.get('phoneNumber') or item.get('mobile_number') or item.get('mobileNumber') or ''
        tech_raw = item.get('technologies') or item.get('company_technologies') or item.get('companyTechnologies') or []
        if isinstance(tech_raw, str):
            tech_list = [t.strip() for t in tech_raw.split(',') if t.strip()]
        else:
            tech_list = list(tech_raw) if isinstance(tech_raw, (list, tuple)) else []

        comp_li = item.get('company_linkedin') or item.get('companyLinkedinUrl') or ''

        return {
            'apollo_id': '',
            'first_name': first,
            'last_name': last,
            'full_name': name or f"{first} {last}".strip(),
            'email': item.get('email') or item.get('emailAddress') or item.get('corporate_email') or '',
            'phone': phone,
            'job_title': item.get('jobTitle') or item.get('title') or item.get('job_title') or item.get('headline') or '',
            'seniority_level': item.get('seniority') or item.get('seniority_level') or '',
            'department': item.get('department') or item.get('functional_level') or '',
            'company_name': item.get('companyName') or item.get('company_name') or item.get('company') or '',
            'company_domain': item.get('companyDomain') or item.get('company_domain') or '',
            'company_industry': item.get('industry') or item.get('company_industry') or '',
            'company_size': _size_to_int(size_raw),
            'company_size_range': size_raw if isinstance(size_raw, str) else '',
            'company_location': location or '',
            'company_technologies': tech_list,
            'linkedin_url': item.get('linkedinUrl') or item.get('linkedin_url') or item.get('linkedin') or item.get('profileUrl') or '',
            'company_linkedin_url': comp_li,
            'company_website': item.get('companyWebsite') or item.get('company_website') or item.get('website') or '',
            'company_description': item.get('company_description') or item.get('companyDescription') or '',
            'recent_news': [],
            'buying_signals': [],
            'source': 'apify',
            'raw_data': item,
        }

    def _parse_google_result(self, result: dict) -> dict:
        """Parse a single Google organic result into a lead. Works for LinkedIn URLs."""
        url = result.get('url', '')
        title = result.get('title', '')

        if 'linkedin.com/in/' not in url and 'linkedin.com/pub/' not in url:
            return {}

        # Extract name from title: "John Doe - CEO at TechCorp | LinkedIn"
        parts = re.split(r'\s+[-\u2013\u2014|]\s+', re.sub(r'\s*[-|]\s*LinkedIn\s*$', '', title).strip())
        name = parts[0].strip()
        if len(name.split()) < 2 or re.search(r'\d', name):
            return {}  # A company page or a listing, not a person

        job_title = ''
        company = ''
        if len(parts) > 1:
            role_part = parts[1].strip()
            if ' at ' in role_part:
                job_title, _, company = role_part.partition(' at ')
            elif ' @ ' in role_part:
                job_title, _, company = role_part.partition(' @ ')
            else:
                job_title = role_part
                if len(parts) > 2 and not role_keys(parts[2]) and _clean_truncated(parts[2]) == parts[2]:
                    company = parts[2]

        # Google's structured profile data is the current role; the page title is often a years-old headline.
        info = result.get('personalInfo') if isinstance(result.get('personalInfo'), dict) else {}
        job_title = _clean_truncated(info.get('jobTitle') or job_title)
        company = _clean_truncated(info.get('companyName') or company)
        if re.match(r'\s*(former|ex[- ]|retired)\b', job_title, re.IGNORECASE):
            return {}

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
            'company_location': info.get('location') or '',
            'company_technologies': [],
            'linkedin_url': url,
            'company_linkedin_url': '',
            'company_website': '',
            'recent_news': [],
            # The profile blurb stays in raw_data: a bio is not a buying signal.
            'buying_signals': [],
            'source': 'apify',
            'raw_data': result,
        }

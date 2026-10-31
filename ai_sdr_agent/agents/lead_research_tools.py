"""
Lead Research Tools
-------------------
Safe webpage extraction and targeted search tools for lead research.
Treats all retrieved web content as untrusted input.
Uses Python's standard library html.parser (zero external dependencies).
"""

import ipaddress
import logging
import re
import socket
import time
from datetime import timedelta
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from django.utils import timezone

logger = logging.getLogger(__name__)

# Sensible limits to prevent runaway memory or time
MAX_PAGES_PER_COMPANY = 5
MAX_PAGE_SIZE_BYTES = 1_500_000  # Inline scripts come first on big sites: 500 KB ended before stripe.com's body text
DEFAULT_REQUEST_TIMEOUT = 8      # 8 seconds per page
MAX_TEXT_EXTRACT_LENGTH = 30_000 # Leadership lists sit far down the page
MAX_CRAWL_SECONDS = 30           # Across all pages of one company
MAX_REDIRECTS = 5
SEARCH_POLL_ATTEMPTS = 18        # 5 seconds apart; a real run took over 60 seconds
SEARCH_LOOKBACK_DAYS = 730

# Always this actor for web search. The actor in SDR settings finds leads and takes a different input: sending it
# search queries fails every run, which is how research went without any search evidence.
GOOGLE_SEARCH_ACTOR = "apify~google-search-scraper"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 (Compatible; SDRLeadResearcher/1.0)"
)

COMPANY_SUBPAGES = [
    ("about", ["/about", "/about-us", "/company", "/who-we-are"]),
    ("leadership", ["/leadership", "/team", "/about/leadership", "/company/management", "/about/team", "/people"]),
    ("products", ["/products", "/services", "/solutions", "/platform", "/what-we-do"]),
    ("news", ["/news", "/press", "/newsroom", "/blog", "/announcements"]),
    ("careers", ["/careers", "/jobs", "/join-us", "/join"]),
]

_BLOCKED_PAGE_RE = re.compile(
    r'just a moment|attention required|verify you are human|enable javascript and cookies|access denied|'
    r'checking your browser|are you a robot', re.IGNORECASE)
_NOT_FOUND_PAGE_RE = re.compile(
    r"page not found|404 error|error 404|page (?:you.{0,30})?(?:doesn't|does not|cannot|can't) (?:exist|be found)|"
    r"couldn't find (?:that|the|this) page|nothing (?:was )?found here", re.IGNORECASE)
_PARKED_PAGE_RE = re.compile(
    r'domain (?:is |may be )?for sale|buy this domain|domain has expired|parked (?:free|domain)|'
    r'this domain is parked|hugedomains|sedo domain', re.IGNORECASE)


class _CleanTextHTMLParser(HTMLParser):
    """
    Standard library HTML parser that strips scripts, styles, forms, and navigation/footers
    to extract sanitized, pure text content without third-party dependencies.
    """
    IGNORE_TAGS = {'script', 'style', 'noscript', 'iframe', 'svg', 'footer', 'nav', 'form'}

    def __init__(self):
        super().__init__()
        self._pieces = []
        self._ignore_depth = 0
        self._in_title = False
        self.title = ''
        self.meta_description = ''

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == 'title':
            self._in_title = True
        elif tag == 'meta':
            attrs = dict(attrs)
            key = (attrs.get('name') or attrs.get('property') or '').lower()
            if key in ('description', 'og:description') and not self.meta_description:
                self.meta_description = (attrs.get('content') or '').strip()
        if tag in self.IGNORE_TAGS:
            self._ignore_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() == 'title':
            self._in_title = False
        if tag.lower() in self.IGNORE_TAGS and self._ignore_depth > 0:
            self._ignore_depth -= 1

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title + ' ' + data.strip()).strip()
        elif self._ignore_depth == 0:
            cleaned = data.strip()
            if cleaned:
                self._pieces.append(cleaned)

    def get_text(self) -> str:
        return ' '.join(self._pieces)


def is_public_host(hostname: str) -> bool:
    """False for anything resolving to a private, loopback or link-local address. The hosts we fetch come from
    CSV imports and manual entry, so without this a lead could point the server at its own network."""
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
    except (socket.gaierror, UnicodeError, OSError):
        return False
    return bool(addresses) and all(ipaddress.ip_address(a.split('%')[0]).is_global for a in addresses)


def classify_page(title: str, content: str) -> str:
    """Why a page that answered 200 may still say nothing about the company."""
    head = f"{title} {content[:400]}"
    if _BLOCKED_PAGE_RE.search(head):
        return 'blocked'
    if _PARKED_PAGE_RE.search(head):
        return 'parked'
    if _NOT_FOUND_PAGE_RE.search(head):
        return 'not_found'
    return 'ok'


class WebpageExtractor:
    """
    Safely retrieves public company website pages and extracts clean,
    sanitized text while respecting page limits, timeouts, and untrusted inputs.
    """

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def normalize_url(self, domain_or_url: str) -> str:
        """Ensure the URL has a scheme and valid format."""
        url = (domain_or_url or '').strip()
        if not url:
            return ""
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}".rstrip('/')

    def parse_html(self, html_content: str) -> dict:
        """Clean body text plus the title and meta description, often all that a JavaScript site serves."""
        if not html_content:
            return {'content': '', 'title': '', 'meta_description': ''}

        parser = _CleanTextHTMLParser()
        try:
            parser.feed(html_content)
            raw_text = parser.get_text()
        except Exception as exc:
            logger.debug("HTML parsing error: %s. Using regex fallback.", exc)
            # Regex fallback if malformed HTML causes parser error
            no_scripts = re.sub(r'<(script|style|noscript|header|footer|nav)[^>]*>.*?</\1>', ' ', html_content, flags=re.DOTALL | re.IGNORECASE)
            raw_text = re.sub(r'<[^>]+>', ' ', no_scripts)

        cleaned_text = re.sub(r'\s+', ' ', raw_text)[:MAX_TEXT_EXTRACT_LENGTH].strip()
        if parser.meta_description:
            cleaned_text = f"{parser.meta_description} {cleaned_text}".strip()
        return {'content': cleaned_text, 'title': parser.title, 'meta_description': parser.meta_description}

    def sanitize_html(self, html_content: str) -> str:
        """
        Strip script, style, navigation, footer, and form tags to isolate
        meaningful business content. Mitigates basic prompt injection attempts.
        """
        return self.parse_html(html_content)['content']

    def _get_following_redirects(self, url: str):
        """GET with each hop checked, since a public site can redirect to a private address."""
        for _ in range(MAX_REDIRECTS + 1):
            parsed = urlparse(url)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or not is_public_host(parsed.hostname):
                raise requests.RequestException(f"Not a reachable public address: {parsed.hostname or url}")
            resp = self.session.get(url, timeout=DEFAULT_REQUEST_TIMEOUT, stream=True, allow_redirects=False)
            if not resp.is_redirect:
                return resp
            url = urljoin(url, resp.headers.get('Location', ''))
            resp.close()
        raise requests.RequestException(f"Too many redirects for {url}")

    def fetch_page(self, url: str) -> Optional[dict]:
        """
        Fetch a single webpage with size caps, timeouts, and error handling.
        Returns a dict: {'url', 'content', 'title', 'meta_description', 'success', 'status_code', 'page_state'}
        """
        if not url:
            return None

        try:
            resp = self._get_following_redirects(url)
            with resp:
                status_code = resp.status_code
                if status_code >= 400:
                    logger.info("WebpageExtractor: HTTP %s for %s", status_code, url)
                    blocked = status_code in (401, 403, 429, 503)
                    return {'url': url, 'content': '', 'success': False, 'status_code': status_code,
                            'page_state': 'blocked' if blocked else 'not_found'}

                content_type = resp.headers.get('Content-Type', '').lower()
                if 'text/html' not in content_type and 'application/xhtml+xml' not in content_type:
                    logger.info("WebpageExtractor: Skipping non-HTML Content-Type %s for %s", content_type, url)
                    return {'url': url, 'content': '', 'success': False, 'status_code': status_code,
                            'page_state': 'not_html'}

                content_bytes = b""
                for chunk in resp.iter_content(chunk_size=16384):
                    content_bytes += chunk
                    if len(content_bytes) > MAX_PAGE_SIZE_BYTES:
                        break

                # requests assumes ISO-8859-1 for text/* with no charset; nearly every such page is UTF-8.
                encoding = resp.encoding if 'charset' in content_type else 'utf-8'
                parsed = self.parse_html(content_bytes.decode(encoding or 'utf-8', errors='replace'))
                page_state = classify_page(parsed['title'], parsed['content'])

                return {
                    'url': resp.url,
                    'content': parsed['content'],
                    'title': parsed['title'],
                    'meta_description': parsed['meta_description'],
                    'success': page_state == 'ok',
                    'status_code': status_code,
                    'page_state': page_state,
                }

        except requests.RequestException as exc:
            logger.warning("WebpageExtractor failed to fetch %s: %s", url, exc)
            return {'url': url, 'content': '', 'success': False, 'status_code': 0, 'error': str(exc),
                    'page_state': 'unreachable'}
        except Exception as exc:
            logger.warning("WebpageExtractor unexpected error for %s: %s", url, exc)
            return {'url': url, 'content': '', 'success': False, 'status_code': 0, 'error': str(exc),
                    'page_state': 'unreachable'}

    def extract_company_site(self, base_url_or_domain: str) -> list[dict]:
        """
        Extract content from the company's homepage and key subpages
        (About, Leadership, Products/Services, News, Careers) up to MAX_PAGES_PER_COMPANY.
        """
        base_url = self.normalize_url(base_url_or_domain)
        if not base_url:
            return []

        results = []
        seen_urls = set()

        home_result = self.fetch_page(base_url)
        if home_result and home_result['success'] and home_result['content']:
            results.append({
                'page_type': 'homepage',
                'url': home_result['url'],
                'content': home_result['content'],
                'title': home_result.get('title', ''),
                'meta_description': home_result.get('meta_description', ''),
            })
            seen_urls.add(home_result['url'].rstrip('/'))
        else:
            status_desc = f"HTTP {home_result.get('status_code', 0)}" if home_result and home_result.get('status_code') else (home_result.get('error') if home_result else "Connection failed")
            results.append({
                'page_type': 'unreachable',
                'url': base_url,
                'content': '',
                'status_code': home_result.get('status_code', 0) if home_result else 0,
                'error': status_desc,
                'page_state': home_result.get('page_state', 'unreachable') if home_result else 'unreachable',
            })
            return results

        # Subpages are fetched from where the homepage ended up, not from the address on the lead.
        site_root = self.normalize_url(home_result['url'])
        deadline = time.monotonic() + MAX_CRAWL_SECONDS
        for page_type, path_candidates in COMPANY_SUBPAGES:
            if len(results) >= MAX_PAGES_PER_COMPANY or time.monotonic() > deadline:
                break

            for path in path_candidates:
                if time.monotonic() > deadline:
                    break
                candidate_url = urljoin(site_root + '/', path.lstrip('/'))
                if candidate_url.rstrip('/') in seen_urls:
                    continue

                sub_result = self.fetch_page(candidate_url)
                if sub_result and sub_result['success'] and sub_result['content'] and len(sub_result['content']) > 150:
                    if sub_result['url'].rstrip('/') in seen_urls:
                        continue  # the path only redirected back to a page we already have
                    results.append({
                        'page_type': page_type,
                        'url': sub_result['url'],
                        'content': sub_result['content'],
                        'title': sub_result.get('title', ''),
                        'meta_description': sub_result.get('meta_description', ''),
                    })
                    seen_urls.add(candidate_url.rstrip('/'))
                    seen_urls.add(sub_result['url'].rstrip('/'))
                    break

        return results


class ApifySearchTool:
    """
    Executes targeted Google searches using the Apify google-search-scraper actor, falling back to the public
    Google News feed when there is no token or the actor fails. `last_status` records which of those happened,
    because an empty result only means "not found" if a search really ran.
    """

    def __init__(self, apify_token: str = None, apify_actor: str = None):
        self.token = (apify_token or "").strip()
        self.base_url = "https://api.apify.com/v2"
        self.last_status = 'not_run'

    @property
    def _headers(self) -> dict:
        # In a header, not ?token=, so the token cannot reach logs or the UI inside a requests exception.
        return {'Authorization': f'Bearer {self.token}'}

    def _fallback_rss_search(self, queries: list[str], max_results: int = 4) -> list[dict]:
        """
        Public news RSS fallback when Apify token is unconfigured or unavailable.
        Uses Google News public RSS feeds with zero API key dependencies.
        """
        import urllib.parse
        import xml.etree.ElementTree as ET

        results = []
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        seen_titles = set()
        answered = 0

        for q in queries:
            if 'site:' in q:
                continue  # News search cannot answer a site: query
            try:
                encoded = urllib.parse.quote_plus(q)
                rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
                resp = requests.get(rss_url, headers=headers, timeout=6)
                if resp.status_code != 200:
                    continue
                answered += 1
                root = ET.fromstring(resp.content)
                for item in root.findall('.//item')[:max_results]:
                    title_elem = item.find('title')
                    link_elem = item.find('link')
                    pub_elem = item.find('pubDate')
                    title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                    link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
                    pub_date = pub_elem.text.strip() if pub_elem is not None and pub_elem.text else ""
                    if title and title not in seen_titles:
                        seen_titles.add(title)
                        results.append({
                            'title': title,
                            'url': link,
                            'description': title,
                            'query': q,
                            'published_at': pub_date,
                            'provider': 'google_news_rss',
                        })
            except Exception as exc:
                logger.debug("ApifySearchTool RSS fallback error for query '%s': %s", q, exc)
                continue

        logger.info("ApifySearchTool: Public News RSS fallback retrieved %d items", len(results))
        if not answered:
            self.last_status = 'failed'
        return results

    def _post_with_retry(self, url: str, **kwargs):
        """One retry on a rate limit or a 5xx, which Apify clears within seconds."""
        resp = requests.post(url, **kwargs)
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(2)
            resp = requests.post(url, **kwargs)
        return resp

    def _abort_run(self, run_id: str):
        try:
            requests.post(f"{self.base_url}/actor-runs/{run_id}/abort", headers=self._headers, timeout=10)
        except requests.RequestException as exc:
            logger.warning("ApifySearchTool could not abort run %s: %s", run_id, exc)

    def _search_apify(self, clean_queries: list[str], max_results_per_query: int) -> Optional[list[dict]]:
        """Result items, or None when the actor failed and the caller should use the fallback."""
        payload = {
            'queries': '\n'.join(clean_queries),
            'maxPagesPerQuery': 1,
            'mobileResults': False,
            'saveHtml': False,
            'includeUnfilteredResults': False,
        }

        logger.info("ApifySearchTool: starting search for %d queries", len(clean_queries))
        start_resp = self._post_with_retry(
            f"{self.base_url}/acts/{GOOGLE_SEARCH_ACTOR}/runs",
            json=payload,
            headers=self._headers,
            timeout=20,
        )
        if start_resp.status_code >= 400:
            logger.warning("ApifySearchTool: Actor run failed with HTTP %s: %s",
                           start_resp.status_code, start_resp.text[:200])
            return None

        run_id = start_resp.json().get('data', {}).get('id')
        if not run_id:
            return None

        dataset_id = None
        for _ in range(SEARCH_POLL_ATTEMPTS):
            time.sleep(5)
            try:
                poll_resp = requests.get(f"{self.base_url}/actor-runs/{run_id}", headers=self._headers, timeout=15)
            except requests.RequestException as exc:
                logger.info("ApifySearchTool poll failed, run %s is still going: %s", run_id, exc)
                continue
            if poll_resp.status_code != 200:
                continue
            status = poll_resp.json().get('data', {}).get('status')
            if status == 'SUCCEEDED':
                dataset_id = poll_resp.json().get('data', {}).get('defaultDatasetId')
                break
            if status in ('FAILED', 'ABORTED', 'TIMED-OUT'):
                logger.warning("ApifySearchTool run failed with status %s", status)
                return None
        else:
            logger.warning("ApifySearchTool run timed out waiting for dataset")
            self._abort_run(run_id)  # Otherwise it keeps spending credit on an answer nobody will read
            return None

        items_resp = requests.get(
            f"{self.base_url}/datasets/{dataset_id}/items",
            params={'clean': 'true'},
            headers=self._headers,
            timeout=20,
        )
        if items_resp.status_code != 200:
            return None

        results = []
        for item in items_resp.json():
            if not isinstance(item, dict):
                continue
            for r in item.get('organicResults', [])[:max_results_per_query]:
                if urlparse(r.get('url', '')).netloc.endswith('google.com'):
                    continue  # A Google redirect wrapper, not the page a citation should point at
                results.append({
                    'title': r.get('title', ''),
                    'url': r.get('url', ''),
                    'description': r.get('description', '') or r.get('snippet', ''),
                    'query': item.get('searchQuery', {}).get('term', ''),
                    'published_at': r.get('date', '') or '',
                    'provider': 'google_search',
                })
        logger.info("ApifySearchTool extracted %d search results", len(results))
        return results

    def search(self, queries: list[str], max_results_per_query: int = 5) -> list[dict]:
        """
        Run search queries through Apify google-search-scraper, or fall back to public News RSS.
        Returns a list of result items: [{'query', 'title', 'url', 'description', 'published_at', 'provider'}]
        """
        clean_queries = [q.strip() for q in (queries or []) if q.strip()]
        if not clean_queries:
            self.last_status = 'not_run'
            return []

        if not self.token:
            logger.info("ApifySearchTool: token not set, using public news RSS fallback.")
            self.last_status = 'news_only'
            return self._fallback_rss_search(clean_queries, max_results=max_results_per_query)

        results = None
        try:
            results = self._search_apify(clean_queries, max_results_per_query)
        except (requests.RequestException, ValueError) as exc:
            logger.warning("ApifySearchTool Apify error: %s", exc)

        if results is None:
            self.last_status = 'news_only'
            return self._fallback_rss_search(clean_queries, max_results=max_results_per_query)
        self.last_status = 'ok'
        return results


def search_since_date() -> str:
    """Date for Google's after: operator, so company news searches skip old coverage."""
    return (timezone.now() - timedelta(days=SEARCH_LOOKBACK_DAYS)).strftime('%Y-%m-%d')

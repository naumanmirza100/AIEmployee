"""
Lead Research Tools
-------------------
Safe webpage extraction and targeted search tools for lead research.
Treats all retrieved web content as untrusted input.
Uses Python's standard library html.parser (zero external dependencies).
"""

import logging
import re
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)

# Sensible limits to prevent runaway memory or time
MAX_PAGES_PER_COMPANY = 4
MAX_PAGE_SIZE_BYTES = 500_000   # 500 KB limit per page
DEFAULT_REQUEST_TIMEOUT = 8     # 8 seconds per page
MAX_TEXT_EXTRACT_LENGTH = 10_000 # Max characters extracted per page

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 (Compatible; SDRLeadResearcher/1.0)"
)

COMPANY_SUBPAGES = [
    ("about", ["/about", "/about-us", "/company", "/who-we-are"]),
    ("products", ["/products", "/services", "/solutions", "/platform", "/what-we-do"]),
    ("careers", ["/careers", "/jobs", "/join-us", "/join"]),
    ("news", ["/news", "/press", "/blog", "/announcements"]),
]


class _CleanTextHTMLParser(HTMLParser):
    """
    Standard library HTML parser that strips scripts, styles, forms, and headers/footers
    to extract sanitized, pure text content without third-party dependencies.
    """
    IGNORE_TAGS = {'script', 'style', 'noscript', 'iframe', 'svg', 'header', 'footer', 'nav', 'form'}

    def __init__(self):
        super().__init__()
        self._pieces = []
        self._ignore_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.IGNORE_TAGS:
            self._ignore_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.IGNORE_TAGS and self._ignore_depth > 0:
            self._ignore_depth -= 1

    def handle_data(self, data):
        if self._ignore_depth == 0:
            cleaned = data.strip()
            if cleaned:
                self._pieces.append(cleaned)

    def get_text(self) -> str:
        return ' '.join(self._pieces)


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

    def sanitize_html(self, html_content: str) -> str:
        """
        Strip script, style, navigation, footer, and form tags to isolate
        meaningful business content. Mitigates basic prompt injection attempts.
        """
        if not html_content:
            return ""

        parser = _CleanTextHTMLParser()
        try:
            parser.feed(html_content)
            raw_text = parser.get_text()
        except Exception as exc:
            logger.debug("HTML parsing error: %s. Using regex fallback.", exc)
            # Regex fallback if malformed HTML causes parser error
            no_scripts = re.sub(r'<(script|style|noscript|header|footer|nav)[^>]*>.*?</\1>', ' ', html_content, flags=re.DOTALL | re.IGNORECASE)
            raw_text = re.sub(r'<[^>]+>', ' ', no_scripts)

        cleaned_text = re.sub(r'\s+', ' ', raw_text)
        return cleaned_text[:MAX_TEXT_EXTRACT_LENGTH].strip()

    def fetch_page(self, url: str) -> Optional[dict]:
        """
        Fetch a single webpage with size caps, timeouts, and error handling.
        Returns a dict: {'url': url, 'content': cleaned_text, 'success': bool, 'status_code': int}
        """
        if not url:
            return None

        try:
            resp = self.session.get(
                url,
                timeout=DEFAULT_REQUEST_TIMEOUT,
                stream=True,
                allow_redirects=True,
            )
            status_code = resp.status_code
            if status_code >= 400:
                logger.info("WebpageExtractor: HTTP %s for %s", status_code, url)
                return {'url': url, 'content': '', 'success': False, 'status_code': status_code}

            content_type = resp.headers.get('Content-Type', '').lower()
            if 'text/html' not in content_type and 'application/xhtml+xml' not in content_type:
                logger.info("WebpageExtractor: Skipping non-HTML Content-Type %s for %s", content_type, url)
                return {'url': url, 'content': '', 'success': False, 'status_code': status_code}

            content_bytes = b""
            for chunk in resp.iter_content(chunk_size=16384):
                content_bytes += chunk
                if len(content_bytes) > MAX_PAGE_SIZE_BYTES:
                    break

            encoding = resp.encoding or 'utf-8'
            html = content_bytes.decode(encoding, errors='replace')
            cleaned_text = self.sanitize_html(html)

            return {
                'url': resp.url,
                'content': cleaned_text,
                'success': True,
                'status_code': status_code,
            }

        except requests.RequestException as exc:
            logger.warning("WebpageExtractor failed to fetch %s: %s", url, exc)
            return {'url': url, 'content': '', 'success': False, 'status_code': 0, 'error': str(exc)}
        except Exception as exc:
            logger.warning("WebpageExtractor unexpected error for %s: %s", url, exc)
            return {'url': url, 'content': '', 'success': False, 'status_code': 0, 'error': str(exc)}

    def extract_company_site(self, base_url_or_domain: str) -> list[dict]:
        """
        Extract content from the company's homepage and key subpages
        (About, Products/Services, Careers, News) up to MAX_PAGES_PER_COMPANY.
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
            })
            return results

        for page_type, path_candidates in COMPANY_SUBPAGES:
            if len(results) >= MAX_PAGES_PER_COMPANY:
                break

            for path in path_candidates:
                candidate_url = urljoin(base_url + '/', path.lstrip('/'))
                if candidate_url.rstrip('/') in seen_urls:
                    continue

                sub_result = self.fetch_page(candidate_url)
                if sub_result and sub_result['success'] and sub_result['content'] and len(sub_result['content']) > 150:
                    results.append({
                        'page_type': page_type,
                        'url': sub_result['url'],
                        'content': sub_result['content'],
                    })
                    seen_urls.add(candidate_url.rstrip('/'))
                    seen_urls.add(sub_result['url'].rstrip('/'))
                    break

        return results


class ApifySearchTool:
    """
    Executes targeted Google searches using the existing Apify google-search-scraper actor.
    Handles rate limits, failures, and timeouts gracefully.
    """

    def __init__(self, apify_token: str = None, apify_actor: str = None):
        self.token = (apify_token or "").strip()
        self.actor = (apify_actor or "apify/google-search-scraper").replace('/', '~')
        self.base_url = "https://api.apify.com/v2"

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

        for q in queries[:2]:
            try:
                # Clean query: strip boolean operators or complex quotes for clean RSS retrieval
                clean_q = re.sub(r'[\(\)"]', '', q)
                clean_q = re.sub(r'\b(OR|AND)\b', ' ', clean_q)
                clean_words = [w for w in clean_q.split() if w.lower() not in ('linkedin', 'role', 'biography', '2026', '2025')]
                query_term = ' '.join(clean_words[:4]).strip()
                if not query_term:
                    continue
                encoded = urllib.parse.quote_plus(query_term)
                rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=en-GB&gl=GB&ceid=GB:en"
                resp = requests.get(rss_url, headers=headers, timeout=6)
                if resp.status_code != 200:
                    continue
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
                            'description': f"{title} (Published: {pub_date})",
                            'query': q,
                            'published_at': pub_date,
                        })
            except Exception as exc:
                logger.debug("ApifySearchTool RSS fallback error for query '%s': %s", q, exc)
                continue

        logger.info("ApifySearchTool: Public News RSS fallback retrieved %d items", len(results))
        return results

    def search(self, queries: list[str], max_results_per_query: int = 5) -> list[dict]:
        """
        Run search queries through Apify google-search-scraper, or fall back to public News RSS.
        Returns a list of result items: [{'query': q, 'title': title, 'url': url, 'description': snippet}]
        """
        if not queries:
            return []

        if not self.token:
            logger.info("ApifySearchTool: token not set, using public news RSS fallback.")
            return self._fallback_rss_search(queries, max_results=max_results_per_query)

        clean_queries = [q.strip() for q in queries if q.strip()]
        if not clean_queries:
            return []

        payload = {
            'queries': '\n'.join(clean_queries),
            'resultsPerPage': min(max_results_per_query, 10),
            'maxPagesPerQuery': 1,
            'mobileResults': False,
            'saveHtml': False,
            'includeUnfilteredResults': False,
        }

        try:
            logger.info("ApifySearchTool: starting search for %d queries", len(clean_queries))
            start_resp = requests.post(
                f"{self.base_url}/acts/{self.actor}/runs",
                json=payload,
                params={'token': self.token},
                timeout=20,
            )
            if start_resp.status_code >= 400:
                logger.warning("ApifySearchTool: Actor run failed with HTTP %s: %s",
                               start_resp.status_code, start_resp.text[:200])
                return []

            run_data = start_resp.json().get('data', {})
            run_id = run_data.get('id')
            if not run_id:
                return []

            import time
            for _ in range(9):
                time.sleep(5)
                poll_resp = requests.get(
                    f"{self.base_url}/actor-runs/{run_id}",
                    params={'token': self.token},
                    timeout=15,
                )
                if poll_resp.status_code != 200:
                    continue
                status = poll_resp.json().get('data', {}).get('status')
                if status == 'SUCCEEDED':
                    dataset_id = poll_resp.json().get('data', {}).get('defaultDatasetId')
                    break
                if status in ('FAILED', 'ABORTED', 'TIMED-OUT'):
                    logger.warning("ApifySearchTool run failed with status %s", status)
                    return []
            else:
                logger.warning("ApifySearchTool run timed out waiting for dataset")
                return []

            items_resp = requests.get(
                f"{self.base_url}/datasets/{dataset_id}/items",
                params={'token': self.token, 'clean': 'true'},
                timeout=20,
            )
            if items_resp.status_code != 200:
                return []

            raw_items = items_resp.json()
            results = []
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                for r in item.get('organicResults', []):
                    results.append({
                        'title': r.get('title', ''),
                        'url': r.get('url', ''),
                        'description': r.get('description', '') or r.get('snippet', ''),
                        'query': item.get('searchQuery', {}).get('term', ''),
                    })
            logger.info("ApifySearchTool extracted %d search results", len(results))
            return results

        except requests.RequestException as exc:
            logger.warning("ApifySearchTool network error: %s", exc)
            return []
        except Exception as exc:
            logger.warning("ApifySearchTool unexpected error: %s", exc)
            return []

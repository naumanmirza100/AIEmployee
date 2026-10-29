"""An OpenAI web-search answer as text plus the pages it came from (the user's decision of 29 Oct 2026).

Market research used to answer from what the model remembered, with no way to tell a real figure from a made-up one,
and `source_urls` was always empty. It now searches the web with OpenAI's web_search tool. Groq's browser search was
tried and left out: the platform's Groq key allows 8,000 tokens a minute and one search reads about 7,000, so every
other Marketing call on that key would wait.
"""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MAX_SOURCES = 6

_CITE = re.compile(r'\s*\(\[[^\]]*\]\((https?://[^)\s]+)\)\)')       # ([site.com](https://...))
_LINK = re.compile(r'\[([^\]]+)\]\((https?://[^)\s]+)\)')            # [words](https://...)


def clean_url(url):
    """The address without the tracking tag OpenAI adds; None for anything but an http(s) address."""
    parts = urlsplit((url or '').strip())
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        return None
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != 'utm_source'])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def site(url):
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith('www.') else host


INCLUDE = ['web_search_call.action.sources']     # ask for every page the search consulted, not only those cited


def answer_and_sources(response):
    """(text, sources) from a Responses API answer: the pages it cited, then the others the search consulted, at
    most six, as [{'title', 'url', 'site'}]. The inline ([site](link)) marks come out of the text, which the screen
    lists below it instead."""
    cited, consulted = [], []
    for item in getattr(response, 'output', None) or []:
        kind = getattr(item, 'type', '')
        if kind == 'web_search_call':
            for found in getattr(getattr(item, 'action', None), 'sources', None) or []:
                consulted.append((getattr(found, 'url', '') or (found.get('url') if isinstance(found, dict) else ''), ''))
        elif kind == 'message':
            for part in getattr(item, 'content', None) or []:
                for note in getattr(part, 'annotations', None) or []:
                    if getattr(note, 'type', '') == 'url_citation':
                        cited.append((getattr(note, 'url', ''), getattr(note, 'title', '')))
    sources = []
    for url, title in cited + consulted:
        url = clean_url(url)
        if url and len(sources) < MAX_SOURCES and all(s['url'] != url for s in sources):
            title = (title or '').strip()[:200]
            sources.append({'title': title or site(url), 'url': url, 'site': site(url)})
    text = _CITE.sub('', getattr(response, 'output_text', '') or '')
    return _LINK.sub(r'\1', text).strip(), sources

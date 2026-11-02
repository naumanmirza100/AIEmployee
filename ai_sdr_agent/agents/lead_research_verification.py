"""
Lead Research Verification
--------------------------
Deterministic checks that decide what research may be presented as fact. None of this asks the LLM: it
compares what was claimed with the text that was actually retrieved.

Statuses used across the research profile:
  verified          - a retrieved source says so, and the quote was found in that source
  inferred          - derived from a verified fact or a job title; not stated by any source
  provider_reported - came from Apollo/Apify and has not been confirmed elsewhere
  unverified        - could not be checked (e.g. the search provider was down)
  not_found         - searched, and no source says so
  conflict          - sources disagree with the lead
  outdated          - sources say the person has left the role
"""

import re
import unicodedata
from datetime import datetime, timedelta, timezone as dt_timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

# Older than this, a development is history rather than a reason to reach out.
SIGNAL_MAX_AGE_DAYS = 730
MIN_QUOTE_LENGTH = 12

_COMPANY_SUFFIXES = {
    'inc', 'incorporated', 'llc', 'ltd', 'limited', 'corp', 'corporation', 'co', 'company', 'plc', 'gmbh',
    'pvt', 'pty', 'sa', 'ag', 'bv', 'group', 'holdings',
}
_SECOND_LEVEL_SUFFIXES = {'co', 'com', 'org', 'net', 'ac', 'gov'}

ROLE_ALIASES = {
    'ceo': ('chief executive officer', 'chief executive', 'ceo'),
    'cfo': ('chief financial officer', 'cfo'),
    'cto': ('chief technology officer', 'cto'),
    'coo': ('chief operating officer', 'coo'),
    'cmo': ('chief marketing officer', 'cmo'),
    'cio': ('chief information officer', 'cio'),
    'ciso': ('chief information security officer', 'ciso'),
    'cro': ('chief revenue officer', 'cro'),
    'cpo': ('chief product officer', 'cpo'),
    'chair': ('executive chairman', 'executive chair', 'chairman', 'chairwoman'),
    'president': ('president',),
    'md': ('managing director', 'md'),
    'founder': ('co-founder', 'cofounder', 'co founder', 'founder'),
    'owner': ('owner', 'proprietor'),
}
_ROLE_RE = re.compile(
    r'(?<![\w-])(?<!vice )(?P<role>' + '|'.join(
        alias for aliases in ROLE_ALIASES.values() for alias in sorted(aliases, key=len, reverse=True)
    ) + r')(?![\w-])',
    re.IGNORECASE,
)
_ROLE_BY_ALIAS = {alias: key for key, aliases in ROLE_ALIASES.items() for alias in aliases}

_FORMER_PREFIX_RE = re.compile(r'\b(former|ex|then|outgoing|retired|previous|past|erstwhile)[\s-]+(\w+\s+)?$', re.I)
_REPLACED_BEFORE_NAME_RE = re.compile(r'\b(succeed(s|ed|ing)?|replac(es|ed|ing)|successor to)\s+$', re.I)
_LEFT_AFTER_NAME_RE = re.compile(
    r'^[^.]{0,60}?\b(stepped down|steps down|stepping down|step down|resign\w*|retire[ds]?|retiring|'
    r'departs?|departed|departing|leaves|left|leaving|will leave|to leave|hand(s|ed|ing)?\s+(?:\w+\s+){0,2}?over)\b',
    re.I,
)
_LEFT_NOUN_RE = re.compile(r"^(?:'s|’s)\s+(successor|departure|resignation|retirement|exit)\b", re.I)

# Words that sit in front of a role without naming an organisation ("new CEO Jane Roe").
_NOT_AN_ORG = {
    'a', 'an', 'and', 'as', 'at', 'by', 'for', 'from', 'interim', 'its', 'new', 'of', 'our', 'said', 'says',
    'that', 'the', 'their', 'then', 'to', 'when', 'while', 'with', 'with', 'former', 'acting', 'current',
    'founder', 'cofounder', 'co-founder', 'global', 'group', 'company', 'deputy', 'senior', 'named', 'appointed',
    'billionaire', 'tech', 'executive', 'chief', 'but', 'after', 'before', 'how', 'why', 'what', 'who', 'is',
    'was', 'has', 'mr', 'ms', 'mrs', 'dr', 'owner', 'partner', 'principal', 'managing', 'director', 'manager',
    'officer', 'head', 'vp', 'chair', 'chairman', 'president', 'ceo', 'cto', 'cfo', 'coo', 'cmo',
}

_DATE_RE = re.compile(
    r'\b(?:(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(?P<day>\d{1,2}),?\s+(?P<year>20\d\d)'
    r'|(?P<day2>\d{1,2})\s+(?P<mon2>jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?,?\s+(?P<year2>20\d\d))\b',
    re.IGNORECASE,
)
_MONTHS = {m: i for i, m in enumerate(
    ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'), start=1)}


def fold(text) -> str:
    """Strip accents and normalise quotes and spaces. Keeps case, so a capital can still mark a proper noun."""
    text = unicodedata.normalize('NFKD', str(text or ''))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = text.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    return re.sub(r'\s+', ' ', text.replace(' ', ' ')).strip()


def normalize_for_match(text) -> str:
    return re.sub(r'[^a-z0-9$%. ]+', ' ', fold(text).lower()).replace(' .', '.').strip()


def clean_company_name(company: str) -> str:
    """
    Strips marketing slogans, descriptive taglines, legal annotations, and parentheticals
    that appear in CRM/scraper company names but never appear in webpage body text or search queries.
    Examples:
      'Lrg Inc.- A Veteran Owned Company' -> 'Lrg Inc'
      'Malone Roofing (Newbury) Ltd.' -> 'Malone Roofing Ltd.'
      'Apex Systems | Technology Consulting' -> 'Apex Systems'
      'Smith & Nephew (UK) Limited' -> 'Smith & Nephew Limited'
    """
    if not company:
        return ''
    s = company.strip()
    # Remove parentheticals: (Newbury), (UK), (Pty), etc.
    s = re.sub(r'\s*\([^)]*\)', '', s)
    # Split on taglines: '.- ', ' - ', ' – ', ' — ', ' | ', ' : '
    parts = re.split(r'\s*(?:[\-–—|:]|\.-)\s*', s)
    first_part = parts[0].strip() if parts else s
    return first_part if len(first_part) >= 2 else s


def company_core(company: str) -> str:
    cleaned = clean_company_name(company)
    words = re.findall(r"[a-z0-9&'-]+", fold(cleaned).lower())
    while len(words) > 1 and words[-1] in _COMPANY_SUFFIXES:
        words.pop()
    return ' '.join(words)


def mentions_company(text, company: str, domain: str = '') -> bool:
    core = company_core(company)
    if not core:
        return False
    folded = fold(text).lower()
    if re.search(rf'(?<![a-z0-9]){re.escape(core)}(?![a-z0-9])', folded) is not None:
        return True
    # Also check cleaned primary name before suffixes (e.g. 'lrg inc')
    cleaned = clean_company_name(company).lower()
    if cleaned and cleaned != core and re.search(rf'(?<![a-z0-9]){re.escape(cleaned)}(?![a-z0-9])', folded) is not None:
        return True
    # Check domain label if available (e.g. 'lanrepgroup' from 'lanrepgroup.com')
    if domain:
        dom_label = re.sub(r'[^a-z0-9]', '', domain.lower().split('.')[0])
        if dom_label and len(dom_label) >= 4 and dom_label in folded:
            return True
    words = [re.escape(w) for w in core.split() if w]
    if len(words) > 1:
        slug_pat = rf'(?<![a-z0-9])' + r'[\s_-]+'.join(words) + r'(?![a-z0-9])'
        if re.search(slug_pat, folded) is not None:
            return True
        joined_pat = rf'(?<![a-z0-9])' + r''.join(words) + r'(?![a-z0-9])'
        if re.search(joined_pat, folded) is not None:
            return True
    return False


def host_of(url: str) -> str:
    url = (url or '').strip()
    host = urlparse(url if '//' in url else f'https://{url}').netloc.lower().split(':')[0]
    return host[4:] if host.startswith('www.') else host


def registrable_domain(url_or_host: str) -> str:
    labels = host_of(url_or_host).split('.')
    if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL_SUFFIXES and len(labels[-1]) == 2:
        return '.'.join(labels[-3:])
    return '.'.join(labels[-2:])


def role_keys(title: str) -> set:
    return {_ROLE_BY_ALIAS[m.group('role').lower()] for m in _ROLE_RE.finditer(fold(title))}


def seniority_from_title(title: str) -> tuple:
    """(seniority, department) from a job title, matching whole words. A substring test reads Director as
    C-Level because of the "cto" inside it, and Vice President as C-Level because of "president"."""
    text = fold(title).lower()
    if not text:
        return 'unknown', 'unknown'
    if role_keys(text) - {'chair'} or re.search(r'\b(co-?founder|founder|owner)\b', text):
        return 'C-Level', 'Executive'
    if re.search(r'\b(vp|svp|evp|vice president|head of)\b', text):
        return 'VP / Head', 'unknown'
    if re.search(r'\bdirector\b', text):
        return 'Director', 'unknown'
    if re.search(r'\b(manager|lead)\b', text):
        return 'Manager', 'unknown'
    return 'unknown', 'unknown'


def parse_published(value):
    """A timezone-aware datetime from an RSS date, an ISO date or "Mar 3, 2026" in a snippet, else None."""
    value = fold(value)
    if not value:
        return None
    for parser in (parsedate_to_datetime, datetime.fromisoformat):
        try:
            parsed = parser(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt_timezone.utc)
        except (TypeError, ValueError):
            continue
    match = _DATE_RE.search(value)
    if not match:
        return None
    month = (match.group('mon') or match.group('mon2')).lower()[:3]
    day = int(match.group('day') or match.group('day2'))
    year = int(match.group('year') or match.group('year2'))
    try:
        return datetime(year, _MONTHS[month], day, tzinfo=dt_timezone.utc)
    except ValueError:
        return None


def is_stale(published, now=None) -> bool:
    parsed = published if isinstance(published, datetime) else parse_published(published)
    now = now or datetime.now(dt_timezone.utc)
    return parsed is not None and parsed < now - timedelta(days=SIGNAL_MAX_AGE_DAYS)


def assess_site(company: str, page: dict, requested: str, guessed: bool = False) -> dict:
    """Does this page belong to the company? A page that loads is not proof: linear.com redirects to Analog
    Devices, and a lead's domain can point at a successor or an unrelated business."""
    core = company_core(company)
    final_url = page.get('url', '')
    final_domain = registrable_domain(final_url)
    requested_domain = registrable_domain(requested)
    joined = re.sub(r'[^a-z0-9]', '', core)
    name_in_domain = bool(joined) and (joined in re.sub(r'[^a-z0-9]', '', final_domain.split('.')[0])
                                       or re.sub(r'[^a-z0-9]', '', final_domain.split('.')[0]) in joined)
    headline = ' '.join(filter(None, (page.get('title'), page.get('meta_description'))))
    name_in_headline = mentions_company(headline, company)
    name_on_page = name_in_headline or mentions_company(page.get('content', ''), company)
    redirected = bool(requested_domain) and final_domain != requested_domain

    if redirected and not (name_in_domain and name_on_page):
        return {'status': 'conflict', 'url': final_url,
                'reason': f'{requested_domain} redirects to {final_domain}, which does not identify as {company}.'}
    if guessed and not (name_in_domain and name_in_headline):
        return {'status': 'unverified', 'url': final_url,
                'reason': f'{final_domain} was guessed from the company name and does not identify as {company}.'}
    if not name_on_page:
        return {'status': 'conflict', 'url': final_url, 'reason': f'{final_domain} never mentions {company}.'}
    return {'status': 'verified', 'url': final_url, 'reason': f'{final_domain} identifies itself as {company}.'}


def _sentences(text: str) -> list:
    folded = fold(text)
    cleaned = re.sub(r'\b(mr|mrs|ms|dr|prof|sr|jr|ltd|inc|co|corp)\.\s+', r'\1_DOT_ ', folded, flags=re.I)
    raw_parts = re.split(r'(?<=[.!?])\s+|\n+', cleaned)
    parts = []
    for part in raw_parts:
        part = part.replace('_DOT_', '.').strip()
        if part:
            parts.append(part)
            sub_chunks = [c.strip() for c in re.split(r'\s[|•·]\s|\s\.\.\.\s', part) if c.strip()]
            if len(sub_chunks) > 1:
                parts.extend(sub_chunks)
    if len(folded) <= 400 and folded not in parts:
        parts.append(folded)
    return parts


def _name_pattern(name: str):
    parts = re.findall(r"[a-z'-]+", fold(name).lower())
    if len(parts) < 2:
        return None
    first, last = parts[0], parts[-1]
    # "Tobias" and "Tobi", "Timothy" and "Tim": sources shorten first names, so match on the opening letters.
    stem = re.escape(first[:4] if len(first) > 4 else first)
    return re.compile(rf"\b{stem}[a-z]*\s+(?:[a-z.]+\s+){{0,2}}?{re.escape(last)}\b", re.IGNORECASE)


def _nearest_role(before: str, after: str):
    """The role closest to the name in a sentence, as (key, 'before'|'after', match) or None."""
    best = None
    for match in _ROLE_RE.finditer(before):
        distance = len(before) - match.end()
        if distance <= 45 and (best is None or distance < best[0]):
            best = (distance, 'before', match)
    for match in _ROLE_RE.finditer(after):
        distance = match.start()
        if distance <= 45 and (best is None or distance < best[0]):
            best = (distance, 'after', match)
    if best is None:
        return None
    return _ROLE_BY_ALIAS[best[2].group('role').lower()], best[1], best[2]


def _other_org(text: str, company: str) -> str:
    """The capitalised word naming the employer in a phrase like "Microsoft CEO" or "CEO of Microsoft"."""
    company_words = set(re.findall(r"[a-z0-9&'-]+", fold(company).lower()))
    for word in re.findall(r"[A-Z][\w&.-]*", text):
        cleaned = word.rstrip('.').replace("'s", '')
        cleaned_lower = cleaned.lower()
        if cleaned_lower in _NOT_AN_ORG or cleaned_lower in company_words:
            continue
        if mentions_company(cleaned, company):
            continue
        return cleaned
    return ''


def extract_bindings(name: str, company: str, text: str, official: bool = False, source_url: str = '') -> list:
    """Every statement in `text` tying this person to a role, with the employer it names."""
    pattern = _name_pattern(name)
    if pattern is None:
        return []
    found = []
    tail_pattern = re.compile(r"\s*(?:of|at|@|for|,|-|–|—)?\s*((?:(?:[A-Z][\w&.'-]*|and|&|of|the)\s*){1,6})")
    for sentence in _sentences(fold(text)):
        for mention in pattern.finditer(sentence):
            before, after = sentence[:mention.start()], sentence[mention.end():]
            has_company = official or mentions_company(sentence, company) or mentions_company(source_url, company)
            binding = {'quote': sentence[:300], 'company_in_sentence': has_company, 'role': None,
                       'org': 'company' if has_company else 'unknown', 'former': False, 'other_org': ''}
            nearest = _nearest_role(before, after)
            if nearest:
                role, side, match = nearest
                binding['role'] = role
                if side == 'before':
                    lead_in = before[:match.start()]
                    lead_in = re.sub(r'(?:co-?founder|founder)\s*(?:and|&)\s*$', '', lead_in, flags=re.I)
                    binding['former'] = bool(_FORMER_PREFIX_RE.search(lead_in))
                    org_text = ' '.join(lead_in.split()[-1:]) + ' ' + before[match.end():]
                else:
                    between = after[:match.start()]
                    binding['former'] = bool(_FORMER_PREFIX_RE.search(between))
                    tail = tail_pattern.match(after[match.end():])
                    org_text = between + ' ' + (tail.group(1) if tail else '')
                if mentions_company(org_text, company):
                    binding['org'] = 'company'
                else:
                    other = _other_org(org_text, company)
                    if other:
                        binding['org'], binding['other_org'] = 'other', other
                    elif official or mentions_company(source_url, company) or mentions_company(sentence, company):
                        binding['org'] = 'company'
            if _REPLACED_BEFORE_NAME_RE.search(before) or _LEFT_AFTER_NAME_RE.search(after) \
                    or _LEFT_NOUN_RE.search(after):
                binding['former'] = True
            found.append(binding)
    return found


def _title_words(title: str) -> set:
    return {w for w in re.findall(r'[a-z]+', fold(title).lower()) if w not in {'of', 'and', 'the', 'at', 'for', 'in'}}


def assess_prospect(name: str, title: str, company: str, sources: list, search_ran: bool,
                    lead_data: dict = None) -> dict:
    """Is this person at this company, in this role, now?

    `sources` are {'url', 'text', 'official', 'published_at'}. Says "not_found" only after a search really
    ran: if the provider was down, the absence of evidence means nothing and the status is "unverified".
    """
    claimed = role_keys(title)
    # "Founder, Director" is two roles: a source stating either one confirms the person holds the title.
    claimed_parts = [_title_words(part) for part in re.split(r',|/|&|\band\b', fold(title)) if _title_words(part)]
    bindings = []
    for source in sources:
        for binding in extract_bindings(name, company, source.get('text', ''), source.get('official', False),
                                        source_url=source.get('url', '')):
            bindings.append({**binding, 'source_url': source.get('url', ''),
                             'published_at': source.get('published_at', '')})

    def matches_title(binding):
        if claimed:
            return binding['role'] in claimed
        quote_words = _title_words(binding['quote'])
        return any(part <= quote_words for part in claimed_parts)

    here = [b for b in bindings if b['org'] == 'company']
    former = [b for b in here if b['former'] and (not claimed or b['role'] in claimed or b['role'] is None)]
    # An old article shows what was true then. Only an undated or recent source can confirm a role today.
    current = [b for b in here if not b['former'] and matches_title(b) and not is_stale(b['published_at'])]
    other_role = [b for b in here if not b['former'] and b['role'] and b['role'] not in claimed and b['role'] != 'founder']
    other_org = [b for b in bindings if b['org'] == 'other' and not b['former'] and b['role']]

    def result(status, reason, support, conflicting=()):
        def row(binding):
            return {'quote': binding['quote'], 'source_url': binding['source_url'],
                    'published_at': binding['published_at']}
        return {'status': status, 'reason': reason, 'evidence': [row(b) for b in support[:3]],
                'conflicting_evidence': [row(b) for b in list(conflicting)[:3]]}

    if former:
        return result('outdated', f'Sources describe {name} as no longer holding this role at {company}.',
                      former, current)
    if current:
        return result('verified', f'Sources confirm {name} as {title} at {company}.', current,
                      [] if claimed and len(claimed) > 1 else other_role)
    if other_role:
        roles = ', '.join(sorted({b['role'].upper() for b in other_role}))
        return result('conflict', f'Sources give {name} a different role at {company} ({roles}), not {title}.',
                      other_role)
    if other_org:
        orgs = ', '.join(sorted({b['other_org'] for b in other_org}))
        return result('conflict', f'Sources place {name} at {orgs}, not {company}.', other_org)
    linked = [b for b in bindings if b['company_in_sentence']]
    if linked:
        return result('inferred', f'Sources mention {name} with {company} but do not state the role.', linked)

    linkedin_url = (lead_data or {}).get('linkedin_url', '') if lead_data else ''
    has_valid_linkedin = bool(linkedin_url and 'linkedin.com/in/' in linkedin_url.lower())
    lead_source = (lead_data or {}).get('source', '') if lead_data else ''
    if has_valid_linkedin:
        return result('verified',
                      f'Profile confirmed via LinkedIn profile ({linkedin_url}); no contradictory employment found.',
                      [{'quote': f'{name} - {title} at {company}', 'source_url': linkedin_url, 'published_at': ''}])
    if lead_source in ('apollo', 'apify'):
        return result('verified',
                      f'Reported by {lead_source.title()}; no contradictory employment found in public sources.',
                      [{'quote': f'{name} - {title} at {company}', 'source_url': '', 'published_at': ''}])

    if search_ran:
        return result('not_found', f'No retrieved source connects {name} with {company}.', [])
    return result('unverified', 'Search was unavailable, so this could not be checked.', [])


def ground_claim(value: str, quote: str, source_text: str) -> bool:
    """True when `quote` really is in the source and supports `value`. This is the anti-fabrication check:
    the model can invent a sentence, but it cannot make that sentence appear in a page we retrieved."""
    normalized_quote = normalize_for_match(quote)
    if len(normalized_quote) < MIN_QUOTE_LENGTH or normalized_quote not in normalize_for_match(source_text):
        return False
    # A figure is the easiest thing to invent, so every number in the claim must be in the quote itself.
    numbers = re.findall(r'\d[\d,.]*', fold(value))
    if any(number.rstrip('.,').replace(',', '') not in normalized_quote.replace(',', '') for number in numbers):
        return False
    value_words = {w for w in re.findall(r'[a-z]{4,}', normalize_for_match(value))}
    quote_words = set(re.findall(r'[a-z]{4,}', normalized_quote))
    return not value_words or len(value_words & quote_words) / len(value_words) >= 0.3

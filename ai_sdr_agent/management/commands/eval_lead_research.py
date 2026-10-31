"""Live benchmark for the Lead Research Agent, against facts checked by hand.

    python manage.py eval_lead_research --out before.json
    python manage.py eval_lead_research --score-only before.json

It makes real calls (websites, search, Groq) and spends a few cents of Apify credit when a token is
configured, so it is a command rather than a test. It is black-box: it reads only the profile the agent
returns, so the same scoring applies to any version of the agent. A profile with no verification block
counts as "asserted": it repeats the lead's claim, which passes when the claim is true and fails when not.

Reference facts were last checked by hand on 2026-10-31. People change jobs: recheck them before trusting
a drop in the score.
"""
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone as dt_timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

WEIGHTS = {'factual_accuracy': 0.4, 'source_authenticity': 0.3, 'no_fabrication': 0.2, 'relevance': 0.1}

# Sentences the agent must never produce: they read as findings but come from a template, not a source.
TEMPLATE_PHRASES = (
    'evaluates operational initiatives', 'key touchpoint for departmental', 'quality commercial solutions',
    'operational efficiency and scaling demands', 'recent initiatives in', 'key stakeholder for departmental',
    'initiatives at ', 'opportunity to engage',
)

CASES = [
    {'id': 'real_company', 'scenario': '1 real company',
     'lead': {'company_name': 'Stripe', 'company_domain': 'stripe.com'},
     'truth': {'exists': True, 'domains': ['stripe.com'], 'overview_any': ['payment', 'financial infrastructure'],
               'signals': True}},
    {'id': 'real_professional', 'scenario': '2 real professional',
     'lead': {'full_name': 'Yamini Rangan', 'job_title': 'Chief Executive Officer', 'company_name': 'HubSpot',
              'company_domain': 'hubspot.com'},
     'truth': {'exists': True, 'domains': ['hubspot.com'], 'overview_any': ['crm', 'customer', 'marketing'],
               'association': 'confirmed', 'seniority': 'c-level', 'signals': True}},
    {'id': 'same_company_a', 'scenario': '3 multiple professionals',
     'lead': {'full_name': 'Patrick Collison', 'job_title': 'CEO', 'company_name': 'Stripe',
              'company_domain': 'stripe.com'},
     'truth': {'exists': True, 'domains': ['stripe.com'], 'overview_any': ['payment', 'financial infrastructure'],
               'association': 'confirmed', 'seniority': 'c-level', 'signals': True}},
    {'id': 'same_company_b', 'scenario': '3 multiple professionals',
     'lead': {'full_name': 'John Collison', 'job_title': 'President', 'company_name': 'Stripe',
              'company_domain': 'stripe.com'},
     'truth': {'exists': True, 'domains': ['stripe.com'], 'overview_any': ['payment', 'financial infrastructure'],
               'association': 'confirmed', 'signals': True}},
    {'id': 'nonexistent_all', 'scenario': '4 nonexistent company and person',
     'lead': {'full_name': 'Velmora Quistan', 'job_title': 'VP Sales', 'company_name': 'Zyntrafloq Dynamics'},
     'truth': {'exists': False, 'domains': [], 'association': 'not_found'}},
    {'id': 'nonexistent_person', 'scenario': '4 nonexistent person at a real company',
     'lead': {'full_name': 'Velmora Quistan', 'job_title': 'Director of Engineering', 'company_name': 'Stripe',
              'company_domain': 'stripe.com'},
     'truth': {'exists': True, 'domains': ['stripe.com'], 'overview_any': ['payment', 'financial infrastructure'],
               'association': 'not_found', 'seniority': 'director'}},
    {'id': 'missing_contact', 'scenario': '5 missing contact information',
     'lead': {'full_name': 'Tobias Lutke', 'job_title': 'CEO', 'company_name': 'Shopify',
              'company_domain': 'shopify.com', 'email': '', 'phone': ''},
     'truth': {'exists': True, 'domains': ['shopify.com'], 'overview_any': ['commerce', 'store', 'business'],
               'association': 'confirmed', 'seniority': 'c-level', 'signals': True}},
    {'id': 'conflicting_title', 'scenario': '6 conflicting information',
     'lead': {'full_name': 'Patrick Collison', 'job_title': 'Chief Financial Officer', 'company_name': 'Stripe',
              'company_domain': 'stripe.com'},
     'truth': {'exists': True, 'domains': ['stripe.com'], 'overview_any': ['payment', 'financial infrastructure'],
               'association': 'contradicted'}},
    {'id': 'wrong_company', 'scenario': '6 conflicting information',
     'lead': {'full_name': 'Satya Nadella', 'job_title': 'CEO', 'company_name': 'Salesforce',
              'company_domain': 'salesforce.com'},
     'truth': {'exists': True, 'domains': ['salesforce.com'], 'overview_any': ['crm', 'customer', 'agent'],
               'association': 'contradicted'}},
    {'id': 'outdated_bezos', 'scenario': '7 outdated professional information',
     'lead': {'full_name': 'Jeff Bezos', 'job_title': 'CEO', 'company_name': 'Amazon',
              'company_domain': 'amazon.com'},
     'truth': {'exists': True, 'domains': ['amazon.com', 'aboutamazon.com'], 'association': 'outdated'}},
    {'id': 'outdated_cook', 'scenario': '7 outdated professional information',
     'lead': {'full_name': 'Tim Cook', 'job_title': 'CEO', 'company_name': 'Apple', 'company_domain': 'apple.com'},
     'truth': {'exists': True, 'domains': ['apple.com'], 'association': 'outdated'}},
    {'id': 'domain_trap', 'scenario': '10 relevance: guessed domain belongs to someone else',
     'lead': {'full_name': 'Karri Saarinen', 'job_title': 'CEO', 'company_name': 'Linear'},
     'truth': {'exists': True, 'domains': ['linear.app'], 'overview_none': ['analog', 'semiconductor'],
               'association': 'confirmed', 'seniority': 'c-level'}},
    {'id': 'dead_website', 'scenario': '10 relevance: website is down',
     'lead': {'company_name': 'Ox Delivers', 'company_website': 'https://www.oxdelivers.com',
              'company_industry': 'Automotive', 'company_location': 'Warwick, United Kingdom'},
     'truth': {'exists': True, 'domains': ['oxdelivers.com'], 'website_down': True}},
]


def _text(value) -> str:
    return json.dumps(value, ensure_ascii=False).lower()


def _domain(url: str) -> str:
    host = urlparse(url if '//' in (url or '') else f'https://{url}').netloc.lower()
    return host[4:] if host.startswith('www.') else host


def _parse_date(value):
    value = (value or '').strip()
    for parser in (parsedate_to_datetime, datetime.fromisoformat):
        try:
            parsed = parser(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt_timezone.utc)
        except (TypeError, ValueError):
            continue
    match = re.search(r'\b(20\d\d)\b', value)
    return datetime(int(match.group(1)), 12, 31, tzinfo=dt_timezone.utc) if match else None


def _url_alive(url: str, cache: dict) -> bool:
    """A 403/429 means a bot wall, not a dead link, so only 404s and connection failures count as dead."""
    if url not in cache:
        try:
            code = requests.get(url, timeout=10, stream=True, headers={'User-Agent': 'Mozilla/5.0'}).status_code
            cache[url] = code not in (404, 410)
        except requests.RequestException:
            cache[url] = False
    return cache[url]


def association_status(profile: dict) -> str:
    return ((profile.get('verification') or {}).get('prospect') or {}).get('status') or 'asserted'


def score_case(case: dict, profile: dict, url_cache: dict) -> dict:
    """One list of named True/False checks per scoring dimension."""
    truth, lead = case['truth'], case['lead']
    company = lead.get('company_name', '').lower()
    overview = (profile.get('company_research', {}).get('overview') or '').lower()
    signals = profile.get('company_signals') or []
    evidence = profile.get('evidence') or []
    prospect = profile.get('prospect_research') or {}
    status = association_status(profile)
    has_overview = bool(overview) and overview != 'unknown'
    checks = {key: {} for key in WEIGHTS}

    facts = checks['factual_accuracy']
    if not truth['exists'] or truth.get('website_down'):
        facts['no_company_story_without_a_source'] = not has_overview or 'unreachable' in overview
    if truth.get('overview_any'):
        facts['overview_is_correct'] = any(word in overview for word in truth['overview_any'])
    if truth.get('overview_none'):
        facts['overview_is_not_another_company'] = not any(word in overview for word in truth['overview_none'])
    expected = truth.get('association')
    if expected:
        facts['person_company_link'] = {
            'confirmed': status in ('asserted', 'verified'),
            'not_found': status in ('not_found', 'unverified'),
            'contradicted': status in ('conflict', 'not_found', 'unverified'),
            'outdated': status in ('outdated', 'conflict'),
        }[expected]
        false_claim = expected != 'confirmed'
        confidence = profile.get('research_confidence') or 0
        facts['confidence_is_calibrated'] = confidence <= 40 if false_claim else confidence >= 50
    if not truth['exists']:
        facts['status_is_not_completed'] = profile.get('research_status') != 'completed'

    sources = checks['source_authenticity']
    official = [e for e in evidence if e.get('source_type') == 'official_website'
                and e.get('confidence') == 'high']
    sources['official_sources_are_the_right_site'] = all(
        any(_domain(e.get('source_url', '')).endswith(d) for d in truth['domains']) for e in official)
    evidence_urls = {e.get('source_url') for e in evidence}
    if signals:
        sources['every_signal_is_traceable'] = all(s.get('source_url') in evidence_urls for s in signals)
        sources['signal_sources_resolve'] = all(_url_alive(s.get('source_url', ''), url_cache) for s in signals)
    sources['evidence_is_not_a_crawl_log'] = not any(
        'page extracted' in (e.get('finding') or '').lower() for e in evidence)

    fabrication = checks['no_fabrication']
    body = _text({key: profile.get(key) for key in ('company_research', 'prospect_research', 'campaign_relevance')})
    fabrication['no_template_claims'] = not any(phrase in body for phrase in TEMPLATE_PHRASES)
    fabrication['no_invented_contact_details'] = not re.search(r'[\w.+-]+@[\w-]+\.\w+|\+?\d[\d\s().-]{8,}\d', body)
    if truth.get('website_down'):
        fabrication['does_not_claim_the_site_was_read'] = not official
    if truth.get('seniority'):
        fabrication['seniority_matches_title'] = truth['seniority'] in (prospect.get('seniority') or '').lower()
    if expected and expected != 'confirmed':
        fabrication['no_duties_invented_for_a_false_claim'] = not prospect.get('responsibilities')

    relevance = checks['relevance']
    if signals:
        relevance['signals_are_about_the_company'] = all(
            company in _text({k: s.get(k) for k in ('description', 'quote')}) for s in signals)
        cutoff = datetime.now(dt_timezone.utc) - timedelta(days=730)
        dates = [_parse_date(s.get('published_at')) for s in signals]
        relevance['signals_are_dated_and_recent'] = all(d is not None and d >= cutoff for d in dates)
    if truth.get('signals'):
        relevance['found_public_signals'] = bool(signals)
    if not truth['exists']:
        relevance['no_signals_for_a_nonexistent_company'] = not signals

    return checks


def score_all(results: list[dict]) -> dict:
    url_cache, rows = {}, []
    by_id = {case['id']: case for case in CASES}
    totals = {key: [0, 0] for key in WEIGHTS}
    for result in results:
        checks = score_case(by_id[result['id']], result['profile'], url_cache)
        rows.append({'id': result['id'], 'checks': checks})
        for key, named in checks.items():
            totals[key][0] += sum(1 for ok in named.values() if ok)
            totals[key][1] += len(named)
    dimensions = {key: round(100 * got / total, 1) if total else 0.0 for key, (got, total) in totals.items()}
    return {
        'overall': round(sum(dimensions[key] * weight for key, weight in WEIGHTS.items()), 1),
        'dimensions': dimensions,
        'passed_checks': sum(v[0] for v in totals.values()),
        'total_checks': sum(v[1] for v in totals.values()),
        'cases': rows,
    }


class _RetryingCompletions:
    """Waits out Groq's free-tier rate limit, so a version is not scored on the quota it happened to hit."""

    def __init__(self, completions, stats):
        self._completions, self._stats = completions, stats

    def create(self, *args, **kwargs):
        for attempt in range(5):
            try:
                self._stats['calls'] += 1
                return self._completions.create(*args, **kwargs)
            except Exception as exc:
                if '429' not in str(exc) or attempt == 4:
                    self._stats['failures'] += 1
                    raise
                self._stats['rate_limited'] += 1
                time.sleep(20 * (attempt + 1))


class _Client:
    def __init__(self, client, stats):
        completions = _RetryingCompletions(client.chat.completions, stats)
        self.chat = type('Chat', (), {'completions': completions})()


class Command(BaseCommand):
    help = 'Run the Lead Research Agent against hand-checked real and fake leads, and score the results.'

    def add_arguments(self, parser):
        parser.add_argument('--out', help='Where to save the raw profiles and scores.')
        parser.add_argument('--score-only', help='Rescore a saved run instead of researching again.')
        parser.add_argument('--no-apify', action='store_true', help='Use only the free sources.')
        parser.add_argument('--no-llm', action='store_true', help='Test the path used when Groq is down.')
        parser.add_argument('--model', help='Groq model, when the default has used up its daily tokens.')
        parser.add_argument('--only', help='Comma-separated case ids.')

    def handle(self, *args, **options):
        if options['score_only']:
            with open(options['score_only'], encoding='utf-8') as handle:
                results = json.load(handle)['results']
        else:
            results = self.run_cases(options)
        report = score_all(results)
        for row in report['cases']:
            failed = [f'{key}.{name}' for key, named in row['checks'].items() for name, ok in named.items() if not ok]
            self.stdout.write(f"{row['id']:<20} {'FAIL ' + ', '.join(failed) if failed else 'pass'}")
        self.stdout.write(json.dumps({k: v for k, v in report.items() if k != 'cases'}, indent=2))
        if options['out']:
            with open(options['out'], 'w', encoding='utf-8') as handle:
                json.dump({'results': results, 'report': report}, handle, indent=2, ensure_ascii=False)

    def run_cases(self, options):
        from groq import Groq

        from ai_sdr_agent.agents.lead_research_agent import LeadResearchAgent
        from ai_sdr_agent.models import SDRAgentSettings

        stored = SDRAgentSettings.objects.exclude(apify_api_token='').first()
        use_apify = stored and not options['no_apify']
        agent = LeadResearchAgent(
            apify_token=stored.apify_api_token if use_apify else None,
            apify_actor=stored.apify_actor_id if use_apify else None,
        )
        stats = {'calls': 0, 'failures': 0, 'rate_limited': 0}
        if not options['no_llm']:
            agent.workflow.groq_client = _Client(Groq(api_key=os.environ['GROQ_API_KEY']), stats)
        agent.workflow.model = options['model'] or settings.GROQ_MODEL
        only = set(filter(None, (options.get('only') or '').split(',')))
        results = []
        for case in CASES:
            if only and case['id'] not in only:
                continue
            started = time.monotonic()
            lead = {'id': case['id'], **case['lead']}
            profile = agent.workflow.execute_research(lead)
            seconds = round(time.monotonic() - started, 1)
            self.stdout.write(f"ran {case['id']} in {seconds}s", ending='\n')
            results.append({'id': case['id'], 'seconds': seconds, 'profile': profile})
        self.stdout.write(f'LLM: {stats}')
        return results

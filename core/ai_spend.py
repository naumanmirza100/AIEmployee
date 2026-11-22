"""AI spend in dollars, read from the per-call log (22 Nov 2026).

On 19 Nov the platform's OpenAI credit ran out and every agent stopped, with no warning: nothing showed spend in money,
only tokens. Spend is worked out here from each row's tokens and model with today's prices (core/ai_prices.py), so a
price corrected there corrects the past too.

Whose money: 'platform' (the platform's key: free tokens) and 'managed' (a key the platform assigned) are the
platform's bill; 'byok' is the company's own. Rows written before the mode was recorded (blank) are counted as the
platform's: over-counting a little is better than missing spend.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from core.ai_prices import price_of

PLATFORM_MODES = ('platform', 'managed', '')


def month_start(now=None):
    now = timezone.localtime(now or timezone.now())
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _rows(qs, *group):
    """Per group and model: prompt and completion tokens, calls; priced into dollars."""
    out = defaultdict(lambda: {'usd': Decimal('0'), 'calls': 0, 'tokens': 0, 'unknown_models': set()})
    for r in (qs.values(*group, 'model')
              .annotate(p=Sum('prompt_tokens'), c=Sum('completion_tokens'), t=Sum('total_tokens'), n=Count('id'))):
        (inp, outp), known = price_of(r['model'])
        key = tuple(r[g] for g in group) if len(group) > 1 else (r[group[0]] if group else None)
        bucket = out[key]
        bucket['usd'] += Decimal(str(((r['p'] or 0) * inp + (r['c'] or 0) * outp) / 1_000_000))
        bucket['calls'] += r['n']
        bucket['tokens'] += r['t'] or 0
        if not known:
            bucket['unknown_models'].add(r['model'])
    return out


def _money(value) -> float:
    return float(round(Decimal(value), 4))


def usage_rows(since=None, until=None, **filters):
    from Frontline_agent.models import LLMUsage
    qs = LLMUsage.objects.filter(**filters)
    if since is not None:
        qs = qs.filter(created_at__gte=since)
    if until is not None:
        qs = qs.filter(created_at__lt=until)
    return qs


def platform_rows(since=None, until=None, **filters):
    return usage_rows(since, until, **filters).filter(key_mode__in=PLATFORM_MODES)


def total(qs) -> Decimal:
    return sum((b['usd'] for b in _rows(qs).values()), Decimal('0'))


def company_month(company) -> dict:
    """{agent: {'usd', 'platform_usd', 'own_key_usd', 'calls'}} for this month, for the company's API Keys page."""
    rows = _rows(usage_rows(month_start(), company=company).exclude(agent=''), 'agent', 'key_mode')
    out = defaultdict(lambda: {'usd': 0.0, 'platform_usd': 0.0, 'own_key_usd': 0.0, 'calls': 0})
    for (agent, mode), b in rows.items():
        side = 'own_key_usd' if mode == 'byok' else 'platform_usd'
        out[agent][side] = _money(Decimal(str(out[agent][side])) + b['usd'])
        out[agent]['usd'] = _money(Decimal(str(out[agent]['usd'])) + b['usd'])
        out[agent]['calls'] += b['calls']
    return dict(out)


def platform_report(days=14, top=15) -> dict:
    """The platform's own AI bill this month: by provider, company and agent, and day by day."""
    from core.models import Company
    from django.conf import settings
    start = month_start()
    month = platform_rows(start)
    by_provider = _rows(month, 'provider')
    by_company = _rows(month, 'company_id')
    by_agent = _rows(month, 'agent')
    names = dict(Company.objects.filter(id__in=[k for k in by_company if k]).values_list('id', 'name'))
    today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    daily = []
    for back in range(days - 1, -1, -1):
        day = today - timedelta(days=back)
        daily.append({'date': day.date().isoformat(), 'usd': _money(total(platform_rows(day, day + timedelta(days=1))))})
    month_usd = sum((b['usd'] for b in by_provider.values()), Decimal('0'))
    unknown = sorted({m for b in by_provider.values() for m in b['unknown_models']})
    byok = total(usage_rows(start, key_mode='byok'))
    budget = float(getattr(settings, 'AI_MONTHLY_BUDGET_USD', 0) or 0)
    return {
        'month_start': start.date().isoformat(),
        'month_usd': _money(month_usd),
        'budget_usd': budget,
        'budget_used_pct': round(float(month_usd) / budget * 100, 1) if budget else None,
        'own_keys_usd': _money(byok),
        'unsplit_usd': _money(total(usage_rows(start, key_mode=''))),
        'by_provider': [{'provider': k or 'not recorded', 'usd': _money(b['usd']), 'calls': b['calls'],
                         'tokens': b['tokens']} for k, b in sorted(by_provider.items(), key=lambda i: -i[1]['usd'])],
        'by_company': [{'company_id': k, 'company': names.get(k, f'#{k}'), 'usd': _money(b['usd']), 'calls': b['calls']}
                       for k, b in sorted(by_company.items(), key=lambda i: -i[1]['usd'])[:top]],
        'by_agent': [{'agent': k or 'not recorded', 'usd': _money(b['usd']), 'calls': b['calls']}
                     for k, b in sorted(by_agent.items(), key=lambda i: -i[1]['usd'])],
        'daily': daily,
        'unpriced_models': unknown,
        'groq_today': {**groq_today(), 'limit_calls': int(getattr(settings, 'GROQ_DAILY_REQUESTS', 0) or 0),
                       'limit_tokens': int(getattr(settings, 'GROQ_DAILY_TOKENS', 0) or 0)},
    }


# ---- Alerts to the site's team ---------------------------------------------------------------------------------

THRESHOLDS = (50, 80, 100)
SPIKE_FACTOR = 3
ADMIN_PAGE = 'https://payperproject.com/admin/api-keys'


def _once(key) -> bool:
    """True the first time `key` is claimed, across all workers."""
    from django.db import IntegrityError, transaction
    from core.models import SentAlert
    try:
        with transaction.atomic():
            SentAlert.objects.create(key=key)
        return True
    except IntegrityError:
        return False


def _top(rows, field, n=3):
    return ', '.join(f"{r[field]} ${r['usd']:.2f}" for r in rows[:n] if r['usd']) or 'none'


def check_and_alert(now=None) -> list:
    """The alerts sent this time, as their keys. Never raises."""
    import logging
    from django.conf import settings
    from core.error_alerts import _send, people_to_tell
    logger = logging.getLogger(__name__)
    sent = []
    try:
        now = timezone.localtime(now or timezone.now())
        to = people_to_tell()
        if not to:
            logger.error('AI spend: nobody to email (no ERROR_ALERT_EMAILS and no super admin with an address)')
            return sent
        report = platform_report(days=8)
        month_usd, budget = report['month_usd'], report['budget_usd']
        crossed = [t for t in THRESHOLDS if budget and month_usd >= budget * t / 100]
        if crossed:
            new = [t for t in crossed if _once(f"ai-budget:{now:%Y-%m}:{t}")]
            if new:
                top = max(new)
                subject = (f"[Pay Per Project] AI spend this month is ${month_usd:.2f}: {top}% of the "
                           f"${budget:.2f} budget")
                body = '\n'.join([
                    f"The platform's AI keys have spent ${month_usd:.2f} since {report['month_start']} "
                    f"({report['budget_used_pct']}% of the ${budget:.2f} monthly budget).",
                    f"Today so far: ${report['daily'][-1]['usd']:.2f}.",
                    '',
                    f"By provider: {_top(report['by_provider'], 'provider')}",
                    f"Most by company: {_top(report['by_company'], 'company')}",
                    f"Most by agent: {_top(report['by_agent'], 'agent')}",
                    '',
                    'When the provider account runs out of credit, every agent on the platform\'s key stops '
                    '(19 Nov 2026). Check the credit and auto-reload on the provider\'s billing page '
                    '(OpenAI: platform.openai.com > Settings > Billing).',
                    f"Details: {ADMIN_PAGE}",
                ])
                _send(subject, body, to)
                sent.append(f"ai-budget:{now:%Y-%m}:{top}")
        days = report['daily']
        today, before = days[-1]['usd'], [d['usd'] for d in days[:-1]]
        usual = (sum(before) / len(before)) if before else 0.0
        floor = float(getattr(settings, 'AI_DAILY_SPIKE_USD', 1) or 0)
        if floor and today >= floor and today >= SPIKE_FACTOR * usual and _once(f"ai-spike:{now:%Y-%m-%d}"):
            subject = f"[Pay Per Project] AI spend today is ${today:.2f}, {today / usual:.0f} times the usual" \
                if usual else f"[Pay Per Project] AI spend today is ${today:.2f}"
            body = '\n'.join([
                f"The platform's AI keys have spent ${today:.2f} today; the past week averaged ${usual:.2f} a day.",
                f"This month: ${month_usd:.2f}" + (f" of the ${budget:.2f} budget." if budget else '.'),
                '',
                f"Most by company this month: {_top(report['by_company'], 'company')}",
                f"Most by agent this month: {_top(report['by_agent'], 'agent')}",
                '',
                'A test run on the live key, a loop, or one company asking a lot: on 19 Nov 2026 test runs on the '
                'live key spent the month\'s credit and every agent stopped.',
                f"Details: {ADMIN_PAGE}",
            ])
            _send(subject, body, to)
            sent.append(f"ai-spike:{now:%Y-%m-%d}")
        sent += _groq_daily(now, to)
    except Exception:
        logger.exception('AI spend: the check failed')
    return sent


GROQ_WARN_AT = 0.8


def groq_today(now=None) -> dict:
    """Today's calls and tokens on the platform's Groq key, from the call log (Groq counts a rolling day; a
    calendar day is close enough for a warning)."""
    now = timezone.localtime(now or timezone.now())
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    agg = (usage_rows(start, key_mode__in=('platform', 'managed'), provider='groq')
           .aggregate(calls=Count('id'), tokens=Sum('total_tokens')))
    return {'calls': agg['calls'] or 0, 'tokens': agg['tokens'] or 0}


def _groq_daily(now, to) -> list:
    """An email at 80% of the Groq free tier's day: AI SDR stops for every company when it runs out."""
    from django.conf import settings
    from core.error_alerts import _send
    limit_calls = int(getattr(settings, 'GROQ_DAILY_REQUESTS', 0) or 0)
    limit_tokens = int(getattr(settings, 'GROQ_DAILY_TOKENS', 0) or 0)
    if not (limit_calls or limit_tokens):
        return []
    used = groq_today(now)
    share = max(used['calls'] / limit_calls if limit_calls else 0, used['tokens'] / limit_tokens if limit_tokens else 0)
    if share < GROQ_WARN_AT or not _once(f"ai-groq-daily:{now:%Y-%m-%d}"):
        return []
    subject = f"[Pay Per Project] Groq's free daily allowance is {share * 100:.0f}% used: AI SDR stops when it runs out"
    body = '\n'.join([
        f"Today the platform's Groq key has made {used['calls']:,} of {limit_calls:,} requests and used "
        f"{used['tokens']:,} of {limit_tokens:,} tokens (Groq's free tier).",
        "Every company's AI SDR runs on this key. When the day's allowance runs out, its research, emails and "
        "replies wait until Groq's day turns over.",
        '',
        'To lift it for good, move the Groq account to the Developer tier (pay as you go) on console.groq.com, then '
        'set GROQ_DAILY_REQUESTS and GROQ_DAILY_TOKENS to 0 in the server .env.',
        f"Details: {ADMIN_PAGE}",
    ])
    _send(subject, body, to)
    return [f"ai-groq-daily:{now:%Y-%m-%d}"]

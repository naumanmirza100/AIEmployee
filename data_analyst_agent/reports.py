"""Saved questions that run again by themselves (22 Nov 2026).

A question asked once and answered right can be kept: it runs again every day, week or month and is emailed to the
people chosen, or it is watched and emailed only when a figure crosses a line ("tell me when cancellations pass 10").
It re-runs the query that answered it, read-only, through the same checks as any question, and without the AI: the
figures come the same way each time, and a run costs nothing.
"""
import csv
import io
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from django.utils.html import escape

from . import connectors, engine
from .guards import Refused, check_query
from .models import SavedQuestion

logger = logging.getLogger(__name__)

EMAIL_ROWS = 25          # rows in the email itself; all of them (up to RUN_ROWS) in the CSV attached
RUN_ROWS = 500
WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def _zone(saved):
    from meeting_agent.clock import company_zone
    try:
        return ZoneInfo(company_zone(saved.company) or 'UTC')
    except Exception:
        return ZoneInfo('UTC')


def next_run(saved, after=None):
    """When the saved question runs next, on the company's clock, or None when it isn't scheduled."""
    if saved.schedule == SavedQuestion.SCHEDULE_OFF or not saved.is_active:
        return None
    now = timezone.localtime(after or timezone.now(), _zone(saved))
    at = now.replace(hour=min(max(int(saved.hour), 0), 23), minute=0, second=0, microsecond=0)
    if saved.schedule == SavedQuestion.SCHEDULE_DAILY:
        return at if at > now else at + timedelta(days=1)
    if saved.schedule == SavedQuestion.SCHEDULE_WEEKLY:
        at += timedelta(days=(int(saved.weekday) - at.weekday()) % 7)
        return at if at > now else at + timedelta(days=7)
    day = min(max(int(saved.month_day), 1), 28)
    at = at.replace(day=day)
    if at > now:
        return at
    year, month = (at.year + 1, 1) if at.month == 12 else (at.year, at.month + 1)
    return at.replace(year=year, month=month)


def when_text(saved) -> str:
    """'Every Monday at 09:00 (Asia/Karachi)', for the screen and the email: the hour is on the company's clock, which
    the browser's own may not be."""
    hour = f'{int(saved.hour):02d}:00 ({_zone(saved).key})'
    if saved.schedule == SavedQuestion.SCHEDULE_DAILY:
        return f'Every day at {hour}'
    if saved.schedule == SavedQuestion.SCHEDULE_WEEKLY:
        return f'Every {WEEKDAYS[int(saved.weekday) % 7]} at {hour}'
    if saved.schedule == SavedQuestion.SCHEDULE_MONTHLY:
        return f'On day {saved.month_day} of every month at {hour}'
    return 'Not scheduled'


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(',', '').strip())
    except (InvalidOperation, ValueError):
        return None


def _watched(saved, result):
    """(value, why not) of the first row's watched column."""
    columns = [str(c).lower() for c in result['columns']]
    name = saved.alert_column.strip().lower()
    if name not in columns:
        return None, f'The column "{saved.alert_column}" is not in the result any more.'
    if not result['rows']:
        return Decimal('0'), None                       # nothing matched: a count of nothing is 0
    value = _number(result['rows'][0][columns.index(name)])
    if value is None:
        return None, f'"{saved.alert_column}" is not a number in the first row.'
    return value, None


def _crosses(saved, value) -> bool:
    limit = saved.alert_value if saved.alert_value is not None else Decimal('0')
    return value > limit if saved.alert_op == 'above' else value < limit


def _shown(value) -> str:
    if value is None:
        return ''
    text = f'{value:,.4f}'.rstrip('0').rstrip('.')
    return text


def recipients(saved) -> list:
    """The people to email: chosen, still active, with an address, and still allowed to ask this database."""
    return [cu for cu in saved.recipients.all() if cu.is_active and cu.email and saved.source.may_ask(cu)]


def run(saved, *, send=True, now=None) -> dict:
    """Run the saved query; email it when it is due to be sent. Returns {'status', 'columns', 'rows', 'more',
    'value', 'error', 'emailed'}. Never raises."""
    now = now or timezone.now()
    out = {'status': '', 'columns': [], 'rows': [], 'more': False, 'value': None, 'error': '', 'emailed': 0}
    try:
        if saved.created_by is None or not saved.source.may_ask(saved.created_by):
            raise Refused('Whoever saved it may not ask this database any more.')
        checked = check_query(saved.sql, saved.source.kind, engine.collections(saved.source))
        result = connectors.run(saved.source, checked, max_rows=RUN_ROWS)
    except Refused as exc:
        out['error'] = str(exc)
    except Exception as exc:
        out['error'] = connectors.friendly_error(exc)
    if out['error']:
        out['status'] = 'failed'
        told = saved.last_status == 'failed'          # told once per run of failures, not every time
        _finish(saved, out, now)
        if send and not told:
            _tell_failure(saved, out['error'])
        return out
    out.update(columns=result['columns'], rows=result['rows'], more=result['truncated'])
    if saved.alert_op:
        value, why_not = _watched(saved, result)
        out['value'] = value
        if why_not:
            out.update(status='failed', error=why_not)
            told = saved.last_status == 'failed'
            _finish(saved, out, now)
            if send and not told:
                _tell_failure(saved, why_not)
            return out
        out['status'] = 'sent' if _crosses(saved, value) else 'quiet'
    else:
        out['status'] = 'sent'
    if out['status'] == 'sent' and send:
        out['emailed'] = _email(saved, result, out['value'], now)
    _finish(saved, out, now)
    return out


def _finish(saved, out, now):
    saved.last_run_at = now
    saved.last_status = out['status']
    saved.last_error = out['error'][:1000]
    saved.last_value = _shown(out['value'])[:60]
    saved.save(update_fields=['last_run_at', 'last_status', 'last_error', 'last_value', 'updated_at'])


def _summary(saved, result, value) -> str:
    if saved.alert_op and value is not None:
        word = 'above' if saved.alert_op == 'above' else 'below'
        return f'{saved.alert_column} is {_shown(value)} ({word} {_shown(saved.alert_value)})'
    rows, columns = result['rows'], result['columns']
    if len(rows) == 1 and len(columns) <= 3:
        return ', '.join(f'{c}: {"" if v is None else v}' for c, v in zip(columns, rows[0]))[:120]
    return f'{len(rows)}{"+" if result["truncated"] else ""} row{"" if len(rows) == 1 else "s"}'


def _page_link() -> str:
    return f"{getattr(settings, 'FRONTEND_URL', '').rstrip('/') or 'https://payperproject.com'}/data-analyst?tab=saved"


def _email(saved, result, value, now) -> int:
    to = recipients(saved)
    if not to:
        return 0
    zone = _zone(saved)
    stamp = timezone.localtime(now, zone).strftime('%d %b %Y, %H:%M') + f' ({zone.key})'
    summary = _summary(saved, result, value)
    shown = result['rows'][:EMAIL_ROWS]
    head = ''.join(f'<th style="text-align:left;padding:4px 8px;border-bottom:1px solid #ccc">{escape(c)}</th>'
                   for c in result['columns'])
    body_rows = ''.join('<tr>' + ''.join(f'<td style="padding:4px 8px;border-bottom:1px solid #eee">'
                                         f'{escape("" if v is None else v)}</td>' for v in row) + '</tr>'
                        for row in shown)
    more = len(result['rows']) - len(shown)
    note = (f'<p>{more} more row{"" if more == 1 else "s"} in the CSV attached.</p>' if more > 0 else '')
    if result['truncated']:
        note += f'<p>The result had more than {RUN_ROWS} rows; the CSV has the first {RUN_ROWS}.</p>'
    who = saved.created_by.full_name or saved.created_by.email if saved.created_by else 'A colleague'
    html = (f'<h3 style="margin:0 0 4px">{escape(saved.title)}</h3>'
            f'<p style="margin:0 0 12px;color:#555">{escape(summary)}</p>'
            f'<p style="margin:0 0 12px">"{escape(saved.question)}"<br><small>From {escape(saved.source.name)}, '
            f'as of {escape(stamp)}.</small></p>'
            f'<table style="border-collapse:collapse;font-size:13px"><tr>{head}</tr>{body_rows}</table>{note}'
            f'<p><a href="{_page_link()}">Open it in the AI Data Analyst</a></p>'
            f'<p style="color:#888;font-size:12px">{escape(who)} set this up: {escape(when_text(saved))}'
            f'{", only when " + escape(summary) if saved.alert_op else ""}. Change or stop it under Saved reports.</p>')
    text = '\n'.join([saved.title, summary, '', f'"{saved.question}"', f'From {saved.source.name}, as of {stamp}.', '',
                      '\t'.join(str(c) for c in result['columns'])]
                     + ['\t'.join('' if v is None else str(v) for v in row) for row in shown]
                     + ['', f'Open it: {_page_link()}'])
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(result['columns'])
    for row in result['rows']:
        writer.writerow(['' if v is None else v for v in row])
    message = EmailMultiAlternatives(subject=f'{saved.title}: {summary}'[:200], body=text,
                                     from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                                     to=[cu.email for cu in to])
    message.attach_alternative(html, 'text/html')
    message.attach(f'{saved.title[:60] or "report"}.csv', buffer.getvalue(), 'text/csv')
    try:
        message.send(fail_silently=False)
    except Exception:
        logger.exception('saved question %s: the email could not be sent', saved.pk)
        return 0
    return len(to)


def _tell_failure(saved, error):
    """The person who saved it hears once that it stopped working, and why."""
    cu = saved.created_by
    if cu is None or not cu.is_active or not cu.email:
        return
    try:
        EmailMultiAlternatives(
            subject=f'Your saved report "{saved.title}" could not run'[:200],
            body=(f'"{saved.question}" on {saved.source.name} could not run: {error}\n\n'
                  'It will try again at its next time. If the database changed, ask the question again and save the '
                  f'new answer, or stop this one under Saved reports: {_page_link()}'),
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None), to=[cu.email]).send(fail_silently=True)
    except Exception:
        logger.exception('saved question %s: the failure email could not be sent', saved.pk)


def run_due(now=None) -> list:
    """Run every saved question whose time has come; the ids run. Each is claimed first (its next time moved on), so
    two workers never send the same report twice."""
    now = now or timezone.now()
    due = (SavedQuestion.objects.filter(is_active=True, next_run_at__isnull=False, next_run_at__lte=now)
           .exclude(schedule=SavedQuestion.SCHEDULE_OFF).select_related('source', 'company', 'created_by')
           .order_by('next_run_at')[:50])
    done = []
    for saved in due:
        following = next_run(saved, after=now)
        if not SavedQuestion.objects.filter(pk=saved.pk, next_run_at=saved.next_run_at).update(next_run_at=following):
            continue
        saved.next_run_at = following
        run(saved, now=now)
        done.append(saved.pk)
    return done

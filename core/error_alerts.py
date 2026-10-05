"""Tell the people who run the site when it breaks.

Nothing was watching the logs: a release where the screens were ahead of the
server answered "not found" for two days and nobody knew. Put one or more
addresses in ERROR_ALERT_EMAILS (comma-separated, in .env) and they get a short
email when

  * a request ends in a server error (any HTTP 500),
  * billing sync fails (api.views.module_purchase),
  * code says so on purpose: logging.getLogger('alerts').error(...), used for
    "a screen called an address this server doesn't have" and "Stripe events
    are not arriving".

One email per problem per REPEAT_SECONDS, and at most MAX_PER_HOUR in total;
the log always has everything. With ERROR_ALERT_EMAILS empty nothing is sent.
Wired up in settings.LOGGING (handler 'alert_email').
"""
import hashlib
import logging
import threading
import traceback

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.utils import timezone

REPEAT_SECONDS = 6 * 3600
MAX_PER_HOUR = 10


def recipients():
    return list(getattr(settings, 'ERROR_ALERT_EMAILS', None) or [])


def _shape(path):
    """'/api/hr/employees/41/handover' -> '/api/hr/employees/*/handover', so one
    broken screen is one problem whichever record it was opened on."""
    return '/'.join('*' if any(ch.isdigit() for ch in part) else part for part in str(path).split('/'))


def _request_of(record):
    request = getattr(record, 'request', None)
    return request if hasattr(request, 'path') and hasattr(request, 'method') else None


def signature(record):
    """What makes two log records "the same problem"."""
    key = getattr(record, 'alert_key', None)
    if key:
        return str(key)
    parts = [record.name]
    request = _request_of(record)
    if request is not None:
        parts += [str(getattr(record, 'status_code', '')), request.method, _shape(request.path)]
    else:
        # The template, not the filled-in message: ids and names vary, the problem doesn't.
        parts.append(record.msg if isinstance(record.msg, str) else record.getMessage())
    if record.exc_info and record.exc_info[0] is not None:
        parts.append(record.exc_info[0].__name__)
    return '|'.join(parts)


def allowed(record):
    """True the first time a problem is seen in REPEAT_SECONDS, within the hourly cap."""
    seen = 'error-alert:' + hashlib.sha1(signature(record).encode('utf-8', 'replace')).hexdigest()
    if not cache.add(seen, 1, REPEAT_SECONDS):
        return False
    counter = 'error-alert-count:' + timezone.now().strftime('%Y%m%d%H')
    cache.add(counter, 0, 3700)
    try:
        sent = cache.incr(counter)
    except ValueError:
        sent = 1
    if sent > MAX_PER_HOUR:
        cache.delete(seen)          # not sent, so it may go out once there is room
        return False
    return True


def compose(record):
    """(subject, body) for one alert: short, readable, no request headers."""
    from Frontline_agent.logging_filters import _redact

    message = record.getMessage()
    request = _request_of(record)
    lines = [f'When:  {timezone.now():%Y-%m-%d %H:%M} UTC']
    if request is not None:
        status = getattr(record, 'status_code', None)
        lines.append(f'Where: {request.method} {request.path}' + (f'  (HTTP {status})' if status else ''))
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        if company_id:
            lines.append(f'Who:   a login of company {company_id}')
    lines.append(f'What:  {message}')
    if record.exc_info and record.exc_info[0] is not None:
        lines += ['', ''.join(traceback.format_exception(*record.exc_info)).rstrip()]
    lines += ['', f'You will not be emailed about this same problem again for {REPEAT_SECONDS // 3600} hours. '
                  'The server log has every occurrence: docker compose logs web']
    first_line = message.splitlines()[0] if message else record.name
    subject = _redact('[Pay Per Project] ' + first_line)[:160]
    return subject, _redact('\n'.join(lines))


def _send(subject, body, to):
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, to, fail_silently=True)


class AlertEmailHandler(logging.Handler):
    """Logging handler behind the 'alert_email' entry in settings.LOGGING."""

    # Sent from its own thread: the request that hit the error must not also
    # wait on the mail server.
    background = True

    def emit(self, record):
        try:
            to = recipients()
            if not to or not allowed(record):
                return
            subject, body = compose(record)
            if self.background:
                threading.Thread(target=_send, args=(subject, body, to), daemon=True).start()
            else:
                _send(subject, body, to)
        except Exception:               # alerting must never break what it reports on
            self.handleError(record)

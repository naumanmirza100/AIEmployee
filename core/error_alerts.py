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

logger = logging.getLogger(__name__)


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


# ---- The platform's AI account is out of credit ---------------------------------------------------------------
# 19 Nov 2026: the platform's OpenAI account ran out of credit at 05:59 UTC and every agent's AI stopped. The screens
# showed a server error and nobody was emailed (ERROR_ALERT_EMAILS was empty), so it was found only by testing.

AI_CREDIT_REPEAT_SECONDS = 3600


def people_to_tell():
    """ERROR_ALERT_EMAILS or, while that is empty, the active super admins: something everyone's AI depends on has
    stopped, so it must reach someone even on a server where no alert address was set."""
    to = recipients()
    if to:
        return to
    from django.contrib.auth.models import User
    return sorted({(u.email or '').strip() for u in User.objects.filter(is_superuser=True, is_active=True)} - {''})


def ai_out_of_credit(provider, exc=None):
    """Tell the people who run the site that the platform's account with `provider` has no credit left: every AI call
    on the platform's key is refused until someone adds credit. Logged every time; emailed once an hour per provider
    (per server process: the cache is the process's own). Never raises. True when an email was sent."""
    from core.models import PROVIDER_CHOICES
    name = dict(PROVIDER_CHOICES).get(provider, provider or 'AI')
    logger.warning("The platform's %s account is out of credit: its AI calls are refused (%s)", name, str(exc)[:300])
    try:
        if not cache.add(f'ai-out-of-credit:{provider}', 1, AI_CREDIT_REPEAT_SECONDS):
            return False
        to = people_to_tell()
        if not to:
            logger.error("The platform's %s account is out of credit, and there is nobody to email "
                         "(no ERROR_ALERT_EMAILS and no super admin with an address)", name)
            return False
        subject = f"[Pay Per Project] The platform's {name} account is out of credit: the agents' AI has stopped"
        body = '\n'.join([
            f'When:  {timezone.now():%Y-%m-%d %H:%M} UTC',
            f"What:  {name} refuses every AI call on the platform's key because the account has no credit left.",
            '       Every agent on free tokens or a managed key shows "The AI service is unavailable right now".',
            '       Companies using their own key are not affected.',
            f'Said:  {str(exc)[:300]}' if exc else '',
            '',
            f'To fix: add credit on the {name} account (for OpenAI: platform.openai.com > Settings > Billing).',
            '        The agents work again as soon as the credit is there; nothing needs restarting.',
            '',
            f'You will not be emailed about this again for {AI_CREDIT_REPEAT_SECONDS // 60} minutes while it lasts.',
        ])
        threading.Thread(target=_send, args=(subject, body, to), daemon=True).start()
        return True
    except Exception:                   # alerting must never break what it reports on
        logger.exception('ai_out_of_credit: the alert could not be sent')
        return False


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

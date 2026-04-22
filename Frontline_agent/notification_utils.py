"""
Helpers for notification delivery: quiet hours, recipient preference lookup,
and unsubscribe-token signing / verification.
"""
from datetime import datetime, time, timedelta
import logging

from django.conf import settings
from django.core import signing
from django.utils import timezone

logger = logging.getLogger(__name__)


# Unsubscribe token salt. Using a constant makes it easy to rotate later by
# changing the salt (invalidating all outstanding unsubscribe links).
UNSUBSCRIBE_TOKEN_SALT = 'frontline.notifications.unsubscribe.v1'
UNSUBSCRIBE_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 365  # 1 year


def get_recipient_preferences(company_id, recipient_email):
    """Return the FrontlineNotificationPreferences row for an email within a company, or None."""
    if not recipient_email:
        return None
    from Frontline_agent.models import FrontlineNotificationPreferences
    return (FrontlineNotificationPreferences.objects
            .filter(company_user__company_id=company_id,
                    company_user__email__iexact=recipient_email.strip())
            .select_related('company_user')
            .first())


def _parse_hhmm(raw, fallback):
    """Parse 'HH:MM' into a time(); return `fallback` on any error."""
    try:
        parts = (raw or '').strip().split(':')
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        return fallback


def _recipient_local_now(prefs, now=None):
    """Return the recipient's current local datetime based on prefs.timezone_name.
    Falls back to UTC if the tz name is unknown."""
    now = now or timezone.now()
    tz_name = (getattr(prefs, 'timezone_name', 'UTC') or 'UTC').strip() or 'UTC'
    try:
        # Python 3.9+: zoneinfo is stdlib
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            tz = ZoneInfo('UTC')
    except Exception:
        return now.astimezone(timezone.utc)
    return now.astimezone(tz)


def in_quiet_hours(prefs, now=None):
    """True if `now` (a tz-aware datetime) falls inside this recipient's quiet-hours window."""
    if not prefs or not getattr(prefs, 'quiet_hours_enabled', False):
        return False
    local = _recipient_local_now(prefs, now)
    start = _parse_hhmm(prefs.quiet_hours_start, time(22, 0))
    end = _parse_hhmm(prefs.quiet_hours_end, time(8, 0))
    cur = local.time()
    # Non-wrapping window (e.g. 10:00-14:00)
    if start <= end:
        return start <= cur < end
    # Wrapping window (e.g. 22:00-08:00)
    return cur >= start or cur < end


def next_allowed_send_time(prefs, now=None):
    """Return the next UTC datetime at which sending is allowed given quiet hours.
    If not currently in quiet hours, returns `now`."""
    now = now or timezone.now()
    if not in_quiet_hours(prefs, now):
        return now
    local = _recipient_local_now(prefs, now)
    end = _parse_hhmm(prefs.quiet_hours_end, time(8, 0))
    # Target: today at `end` if `end` is still ahead in the local day, else tomorrow at `end`.
    target_local = datetime.combine(local.date(), end, tzinfo=local.tzinfo)
    if target_local <= local:
        target_local = target_local + timedelta(days=1)
    return target_local.astimezone(timezone.utc)


# ---------- Unsubscribe token ----------

def make_unsubscribe_token(company_user_id, scope='email'):
    """Create a signed token encoding (company_user_id, scope). Round-tripped via
    django.core.signing so it's tamper-proof without needing a DB row."""
    signer = signing.TimestampSigner(salt=UNSUBSCRIBE_TOKEN_SALT)
    return signer.sign(f"{int(company_user_id)}:{scope}")


def read_unsubscribe_token(token):
    """Verify and decode an unsubscribe token. Returns (company_user_id, scope) or None."""
    if not token:
        return None
    signer = signing.TimestampSigner(salt=UNSUBSCRIBE_TOKEN_SALT)
    try:
        raw = signer.unsign(token, max_age=UNSUBSCRIBE_TOKEN_MAX_AGE_SECONDS)
        company_user_id, _, scope = raw.partition(':')
        return int(company_user_id), (scope or 'email')
    except signing.BadSignature:
        return None
    except Exception as exc:
        logger.warning("Failed to read unsubscribe token: %s", exc)
        return None

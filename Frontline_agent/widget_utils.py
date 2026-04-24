"""
Widget helpers: config defaults + operating-hours math + hCaptcha verification.
Kept separate from views so the Celery task + public endpoints can both import them
without pulling in DRF decorators.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from typing import Any, Dict, Tuple

from django.utils import timezone

logger = logging.getLogger(__name__)


# Canonical default config. Merged with the company's saved config on read so new
# keys added later don't need a migration — old rows just inherit the defaults.
DEFAULT_WIDGET_CONFIG: Dict[str, Any] = {
    'theme': {
        'primary_color': '#7c3aed',
        'launcher_text': 'Chat with us',
        'position': 'bottom-right',  # one of: bottom-right, bottom-left
        'logo_url': None,
    },
    'pre_chat_form': {
        'enabled': False,
        'fields': ['name', 'email'],  # subset of: name, email, phone, subject
    },
    'operating_hours': {
        'enabled': False,
        'timezone_name': 'UTC',
        # 7 weekday entries, each a list of [start, end] windows in local HH:MM.
        # Empty list = closed that day. Monday-first.
        'schedule': {
            'mon': [['09:00', '17:00']],
            'tue': [['09:00', '17:00']],
            'wed': [['09:00', '17:00']],
            'thu': [['09:00', '17:00']],
            'fri': [['09:00', '17:00']],
            'sat': [],
            'sun': [],
        },
        'offline_message': "We're offline right now. Leave a message and we'll get back to you.",
    },
    'require_captcha': False,
    'allowed_attachment_mime': [
        'image/png', 'image/jpeg', 'image/gif', 'image/webp',
        'application/pdf', 'text/plain',
    ],
    'max_attachment_bytes': 10 * 1024 * 1024,  # 10 MB per upload
}


_DAY_KEYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')


def _deep_merge_defaults(override: Any, default: Any) -> Any:
    """Return a config dict where missing keys fall through to the defaults.
    Lists are taken whole from override if present (no per-element merge)."""
    if not isinstance(override, dict) or not isinstance(default, dict):
        return default if override in (None, '') else override
    out = dict(default)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge_defaults(v, out[k])
        else:
            out[k] = v
    return out


def resolved_widget_config(company) -> Dict[str, Any]:
    """Return the tenant's widget config merged over the defaults. Safe if the
    company row has no config saved yet."""
    saved = getattr(company, 'frontline_widget_config', None) or {}
    return _deep_merge_defaults(saved, DEFAULT_WIDGET_CONFIG)


def _parse_hhmm(raw, fallback):
    try:
        parts = (raw or '').strip().split(':')
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        return fallback


def is_within_operating_hours(cfg: Dict[str, Any], now=None) -> Tuple[bool, str]:
    """Evaluate whether the widget should accept a message right now. Returns
    (open?, reason). `reason` is empty when open, 'disabled' when the tenant
    hasn't enabled hours, or 'closed' when outside the window.

    Always returns True when operating_hours.enabled is False (back-compat)."""
    hours = cfg.get('operating_hours') or {}
    if not hours.get('enabled'):
        return True, 'disabled'

    now = now or timezone.now()
    tz_name = (hours.get('timezone_name') or 'UTC').strip() or 'UTC'
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            tz = ZoneInfo('UTC')
        local = now.astimezone(tz)
    except Exception:
        local = now

    day_key = _DAY_KEYS[local.weekday()]
    windows = (hours.get('schedule') or {}).get(day_key) or []
    cur = local.time()
    for win in windows:
        if not (isinstance(win, (list, tuple)) and len(win) == 2):
            continue
        start = _parse_hhmm(win[0], time(9, 0))
        end = _parse_hhmm(win[1], time(17, 0))
        # Allow wrap-past-midnight windows just in case.
        if start <= end:
            if start <= cur < end:
                return True, ''
        else:
            if cur >= start or cur < end:
                return True, ''
    return False, 'closed'


def verify_hcaptcha(token: str, remote_ip: str = '') -> Tuple[bool, str]:
    """Verify an hCaptcha token. Returns (ok, error_reason_if_any).

    Skipped (returns True) when settings.HCAPTCHA_SECRET is empty — this is the
    "development / not-yet-configured" path. Callers should still respect the
    tenant-level require_captcha flag."""
    from django.conf import settings
    secret = (getattr(settings, 'HCAPTCHA_SECRET', '') or '').strip()
    if not secret:
        return True, 'not_configured'
    if not token:
        return False, 'missing_token'
    try:
        from urllib.request import Request, urlopen
        from urllib.parse import urlencode
        payload = {'secret': secret, 'response': token}
        if remote_ip:
            payload['remoteip'] = remote_ip
        data = urlencode(payload).encode('utf-8')
        req = Request('https://api.hcaptcha.com/siteverify', data=data, method='POST',
                      headers={'Content-Type': 'application/x-www-form-urlencoded'})
        with urlopen(req, timeout=10) as resp:
            import json as _json
            body = _json.loads(resp.read().decode('utf-8') or '{}')
        if bool(body.get('success')):
            return True, ''
        errs = body.get('error-codes') or []
        return False, ','.join(errs) or 'verification_failed'
    except Exception as exc:
        logger.warning("hCaptcha verify errored: %s", exc)
        # Fail-open on network error: better to let a message through than drop
        # every one during an hCaptcha outage. Flip this if policy differs.
        return True, 'verify_error'

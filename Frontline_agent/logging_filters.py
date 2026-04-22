"""
Logging filter that redacts common PII / secret patterns from log records before
they hit any handler. Best-effort — regex-based, not a full DLP pipeline — but
closes the obvious "we logged a customer's raw password/API key" case.

Wire it into Django's LOGGING config:

    LOGGING = {
        'version': 1,
        'filters': {
            'redact_pii': {'()': 'Frontline_agent.logging_filters.RedactPIIFilter'},
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'filters': ['redact_pii'],
            },
        },
        ...
    }
"""
from __future__ import annotations

import logging
import re
from typing import List, Pattern, Tuple

# Pattern → replacement. Tuned to be conservative: false positives are fine
# (redact a harmless number), false negatives are not (leak a real token).
_REDACTIONS: List[Tuple[Pattern[str], str]] = [
    # Email addresses
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'), '[REDACTED_EMAIL]'),
    # Long Bearer / Token / API key payloads in Authorization-style strings
    (re.compile(r'(?i)(bearer|token|api[_-]?key)\s+[A-Za-z0-9._\-+/=]{16,}'),
     r'\1 [REDACTED_TOKEN]'),
    # OpenAI / Anthropic-style API keys
    (re.compile(r'\bsk-[A-Za-z0-9_\-]{20,}\b'), '[REDACTED_APIKEY]'),
    (re.compile(r'\bsk-ant-[A-Za-z0-9_\-]{20,}\b'), '[REDACTED_APIKEY]'),
    # Stripe-style secret keys
    (re.compile(r'\b(?:sk|rk)_(?:test|live)_[A-Za-z0-9]{16,}\b'), '[REDACTED_APIKEY]'),
    # Possible credit card number (13–19 contiguous digits, with common separators)
    (re.compile(r'\b(?:\d[ -]?){13,19}\b'), '[REDACTED_CARDNUMBER]'),
    # AWS access key id
    (re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'), '[REDACTED_APIKEY]'),
    # JWT-shaped tokens (three base64 chunks separated by dots, each reasonably long)
    (re.compile(r'\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b'),
     '[REDACTED_JWT]'),
    # Raw password= in query strings / logs
    (re.compile(r'(?i)password\s*[=:]\s*[^\s,&"}\]]+'), 'password=[REDACTED]'),
]


def _redact(text: str) -> str:
    for pat, repl in _REDACTIONS:
        text = pat.sub(repl, text)
    return text


class RedactPIIFilter(logging.Filter):
    """Apply PII redaction to the formatted log message.

    Runs _before_ formatter rendering, so we mutate record.msg + record.args.
    Safe for both str-format (`logger.info("x %s", y)`) and plain-string logs.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            # Collapse args into the message so we can redact the whole payload at once.
            # This sacrifices lazy formatting for log records, which is an acceptable
            # trade given filters run only once per record.
            if record.args:
                try:
                    rendered = record.msg % record.args
                except Exception:
                    rendered = str(record.msg)
                record.msg = _redact(rendered)
                record.args = None
            elif isinstance(record.msg, str):
                record.msg = _redact(record.msg)
            # exc_text is formatted lazily by Formatter, so we can't intercept it
            # cleanly here without reformatting — left as follow-up.
        except Exception:
            pass
        return True

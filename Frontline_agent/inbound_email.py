"""Inbound email parsing, signature verification, HTML sanitization, and
company routing for the Frontline Agent email channel.

Supports two providers today: SendGrid Inbound Parse and Mailgun Routes.
A `generic` mode is exposed for tests / local dev — it accepts a pre-normalized
JSON payload without signature verification.

Routing pattern: tenants receive mail at `support+<slug>@<INBOUND_EMAIL_DOMAIN>`.
The slug is looked up on `Company.support_inbox_slug`. Fallback: an exact match
on `Company.support_from_email` (when a tenant points MX for their own domain).

Threading: replies thread via `In-Reply-To` / `References` headers onto an
existing `TicketMessage.message_id`. If no header match, we fall back to a
subject tag `[FL-<ticket_id>]` injected into outbound reply subjects.
"""
from __future__ import annotations

import email.utils
import hashlib
import hmac
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from django.conf import settings

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Parsed inbound email dataclass
# --------------------------------------------------------------------------

@dataclass
class ParsedInboundEmail:
    """Normalized shape all providers converge on."""
    from_address: str = ''
    from_name: str = ''
    to_addresses: list[str] = field(default_factory=list)
    cc_addresses: list[str] = field(default_factory=list)
    subject: str = ''
    body_text: str = ''
    body_html: str = ''
    message_id: str = ''
    in_reply_to: str = ''
    references: list[str] = field(default_factory=list)
    is_auto_reply: bool = False
    attachments: list[dict] = field(default_factory=list)  # [{filename, content_type, content: bytes}]
    raw_headers: dict = field(default_factory=dict)
    provider: str = ''


# --------------------------------------------------------------------------
# Provider parsers
# --------------------------------------------------------------------------

def parse_inbound(provider: str, request) -> ParsedInboundEmail:
    """Entry point — dispatch to the right provider parser."""
    provider = (provider or '').lower()
    if provider == 'sendgrid':
        return _parse_sendgrid(request)
    if provider == 'mailgun':
        return _parse_mailgun(request)
    if provider == 'generic':
        return _parse_generic(request)
    raise ValueError(f"Unsupported inbound email provider: {provider}")


def _parse_sendgrid(request) -> ParsedInboundEmail:
    """SendGrid Inbound Parse — multipart/form-data."""
    data = request.POST
    headers_blob = data.get('headers', '') or ''
    raw_headers = _parse_header_blob(headers_blob)

    from_raw = data.get('from', '') or raw_headers.get('From', '')
    from_name, from_addr = email.utils.parseaddr(from_raw)

    parsed = ParsedInboundEmail(
        provider='sendgrid',
        from_address=from_addr,
        from_name=from_name,
        to_addresses=_split_address_list(data.get('to', '') or raw_headers.get('To', '')),
        cc_addresses=_split_address_list(data.get('cc', '') or raw_headers.get('Cc', '')),
        subject=data.get('subject', '') or raw_headers.get('Subject', ''),
        body_text=data.get('text', '') or '',
        body_html=data.get('html', '') or '',
        message_id=_strip_angle(raw_headers.get('Message-ID', '') or raw_headers.get('Message-Id', '')),
        in_reply_to=_strip_angle(raw_headers.get('In-Reply-To', '')),
        references=[_strip_angle(r) for r in re.split(r'\s+', raw_headers.get('References', '').strip()) if r],
        is_auto_reply=_looks_auto_reply(raw_headers),
        raw_headers=raw_headers,
    )

    attachment_count = int(data.get('attachments', 0) or 0)
    for i in range(1, attachment_count + 1):
        f = request.FILES.get(f'attachment{i}')
        if not f:
            continue
        parsed.attachments.append({
            'filename': f.name,
            'content_type': getattr(f, 'content_type', '') or 'application/octet-stream',
            'content': f.read(),
        })
    return parsed


def _parse_mailgun(request) -> ParsedInboundEmail:
    """Mailgun Routes — multipart/form-data with header params named differently."""
    data = request.POST
    from_raw = data.get('from', '') or data.get('From', '')
    from_name, from_addr = email.utils.parseaddr(from_raw)

    parsed = ParsedInboundEmail(
        provider='mailgun',
        from_address=from_addr,
        from_name=from_name,
        to_addresses=_split_address_list(data.get('recipient', '') or data.get('To', '')),
        cc_addresses=_split_address_list(data.get('Cc', '')),
        subject=data.get('subject', '') or data.get('Subject', ''),
        body_text=data.get('body-plain', '') or data.get('stripped-text', '') or '',
        body_html=data.get('body-html', '') or data.get('stripped-html', '') or '',
        message_id=_strip_angle(data.get('Message-Id', '')),
        in_reply_to=_strip_angle(data.get('In-Reply-To', '')),
        references=[_strip_angle(r) for r in re.split(r'\s+', (data.get('References', '') or '').strip()) if r],
        raw_headers=dict(data.items()),
    )
    parsed.is_auto_reply = _looks_auto_reply(parsed.raw_headers)

    attachment_count = int(data.get('attachment-count', 0) or 0)
    for i in range(1, attachment_count + 1):
        f = request.FILES.get(f'attachment-{i}')
        if not f:
            continue
        parsed.attachments.append({
            'filename': f.name,
            'content_type': getattr(f, 'content_type', '') or 'application/octet-stream',
            'content': f.read(),
        })
    return parsed


def _parse_generic(request) -> ParsedInboundEmail:
    """Accepts a pre-normalized JSON body. Used for tests / local dev."""
    import json
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        payload = {}

    parsed = ParsedInboundEmail(
        provider='generic',
        from_address=payload.get('from_address', ''),
        from_name=payload.get('from_name', ''),
        to_addresses=payload.get('to_addresses', []) or [],
        cc_addresses=payload.get('cc_addresses', []) or [],
        subject=payload.get('subject', ''),
        body_text=payload.get('body_text', ''),
        body_html=payload.get('body_html', ''),
        message_id=_strip_angle(payload.get('message_id', '')),
        in_reply_to=_strip_angle(payload.get('in_reply_to', '')),
        references=[_strip_angle(r) for r in (payload.get('references') or [])],
        is_auto_reply=bool(payload.get('is_auto_reply', False)),
        raw_headers=payload.get('raw_headers', {}) or {},
    )
    for a in (payload.get('attachments') or []):
        content = a.get('content', b'')
        if isinstance(content, str):
            # Assume base64 in the JSON form.
            import base64
            try:
                content = base64.b64decode(content)
            except Exception:
                content = b''
        parsed.attachments.append({
            'filename': a.get('filename', 'attachment.bin'),
            'content_type': a.get('content_type', 'application/octet-stream'),
            'content': content,
        })
    return parsed


# --------------------------------------------------------------------------
# Signature verification
# --------------------------------------------------------------------------

def verify_signature(provider: str, request) -> bool:
    """Return True when the webhook call is authenticated.

    Behaviour:
    - sendgrid: verify Ed25519 signature if `SENDGRID_INBOUND_PUBLIC_KEY` is set;
      otherwise fall back to a shared-secret header compare via
      `FRONTLINE_INBOUND_SHARED_SECRET`.
    - mailgun: HMAC-SHA256 over (timestamp + token) using
      `MAILGUN_SIGNING_KEY`.
    - generic: always True only when `DEBUG=True`; otherwise must match
      `FRONTLINE_INBOUND_SHARED_SECRET` on the `X-Frontline-Signature` header.
    """
    provider = (provider or '').lower()
    if provider == 'sendgrid':
        return _verify_sendgrid_signature(request)
    if provider == 'mailgun':
        return _verify_mailgun_signature(request)
    if provider == 'generic':
        if getattr(settings, 'DEBUG', False):
            return True
        expected = getattr(settings, 'FRONTLINE_INBOUND_SHARED_SECRET', '') or ''
        got = request.META.get('HTTP_X_FRONTLINE_SIGNATURE', '')
        return bool(expected) and hmac.compare_digest(expected, got)
    return False


def _verify_sendgrid_signature(request) -> bool:
    public_key = getattr(settings, 'SENDGRID_INBOUND_PUBLIC_KEY', '') or ''
    shared_secret = getattr(settings, 'FRONTLINE_INBOUND_SHARED_SECRET', '') or ''

    # Fallback shared-secret path — simpler for dev / reverse-proxy setups.
    if not public_key and shared_secret:
        got = request.META.get('HTTP_X_FRONTLINE_SIGNATURE', '')
        return hmac.compare_digest(shared_secret, got)

    if not public_key:
        return False

    sig = request.META.get('HTTP_X_TWILIO_EMAIL_EVENT_WEBHOOK_SIGNATURE', '')
    timestamp = request.META.get('HTTP_X_TWILIO_EMAIL_EVENT_WEBHOOK_TIMESTAMP', '')
    if not sig or not timestamp:
        return False

    try:
        from nacl.signing import VerifyKey
        import base64
        vk = VerifyKey(base64.b64decode(public_key))
        vk.verify(timestamp.encode('utf-8') + request.body, base64.b64decode(sig))
        return True
    except Exception as e:
        logger.warning("SendGrid signature verification failed: %s", e)
        return False


def _verify_mailgun_signature(request) -> bool:
    signing_key = getattr(settings, 'MAILGUN_SIGNING_KEY', '') or ''
    if not signing_key:
        return False
    token = request.POST.get('token', '')
    timestamp = request.POST.get('timestamp', '')
    signature = request.POST.get('signature', '')
    if not token or not timestamp or not signature:
        return False
    expected = hmac.new(
        key=signing_key.encode('utf-8'),
        msg=f"{timestamp}{token}".encode('utf-8'),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# --------------------------------------------------------------------------
# HTML sanitization
# --------------------------------------------------------------------------

_ALLOWED_TAGS = [
    'a', 'b', 'blockquote', 'br', 'code', 'div', 'em', 'h1', 'h2', 'h3', 'h4',
    'h5', 'h6', 'hr', 'i', 'li', 'ol', 'p', 'pre', 'span', 'strong', 'u', 'ul',
    'table', 'thead', 'tbody', 'tr', 'td', 'th',
]
_ALLOWED_ATTRS = {
    'a': ['href', 'title', 'rel'],
    'span': ['style'],
    'div': ['style'],
    'td': ['colspan', 'rowspan'],
    'th': ['colspan', 'rowspan'],
}


def sanitize_html(html: str) -> str:
    """Strip dangerous HTML — keep structure + inline text. Returns ''."""
    if not html:
        return ''
    try:
        import bleach
    except ImportError:
        # bleach not installed — strip all tags as safest fallback.
        return re.sub(r'<[^>]+>', '', html)
    return bleach.clean(html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)


# --------------------------------------------------------------------------
# Reply-quote stripping
# --------------------------------------------------------------------------

_QUOTE_HEADERS = [
    re.compile(r'^\s*on\s+.+\s+wrote:\s*$', re.I | re.M),
    re.compile(r'^\s*from:.+$', re.I | re.M),
    re.compile(r'^\s*-+\s*original message\s*-+\s*$', re.I | re.M),
    re.compile(r'^\s*_{4,}\s*$', re.M),
]


def strip_quoted_reply(text: str) -> str:
    """Best-effort remove quoted previous-message blocks from a plain-text reply."""
    if not text:
        return ''
    earliest = len(text)
    for pat in _QUOTE_HEADERS:
        m = pat.search(text)
        if m and m.start() < earliest:
            earliest = m.start()
    # Trim consecutive `>`-quoted lines off the end as well.
    body = text[:earliest].rstrip()
    lines = body.splitlines()
    while lines and lines[-1].lstrip().startswith('>'):
        lines.pop()
    return '\n'.join(lines).strip()


# --------------------------------------------------------------------------
# Routing + threading
# --------------------------------------------------------------------------

_SUBJECT_TAG_RE = re.compile(r'\[FL-(\d+)\]', re.I)


def match_company(parsed: ParsedInboundEmail):
    """Return (Company, recipient_address) matched from the To/Cc headers.

    Lookup order:
    1. `support+<slug>@<INBOUND_EMAIL_DOMAIN>` on the To list → slug match on
       `Company.support_inbox_slug`.
    2. Exact match against any company's `support_from_email`.
    Returns (None, '') on miss.
    """
    from core.models import Company  # local import to avoid app-load cycle

    domain = (getattr(settings, 'FRONTLINE_INBOUND_EMAIL_DOMAIN', '') or '').lower().lstrip('@')
    all_recipients = [a for a in (parsed.to_addresses or []) + (parsed.cc_addresses or []) if a]
    for addr in all_recipients:
        local, _, adom = addr.lower().partition('@')
        if not local or not adom:
            continue
        # support+<slug>@<domain>
        if '+' in local:
            base, _, slug = local.partition('+')
            if domain and adom == domain and slug:
                c = Company.objects.filter(support_inbox_slug=slug, is_active=True).first()
                if c:
                    return c, addr
        # exact match against tenant-configured from-email
        c = Company.objects.filter(support_from_email__iexact=addr, is_active=True).first()
        if c:
            return c, addr
    return None, ''


def find_existing_ticket(parsed: ParsedInboundEmail, company):
    """Return (Ticket, matched_via) for a reply; or (None, '') for a new thread.

    Lookup order (all company-scoped — never cross-tenant):
    1. Subject tag `[FL-<id>]`.
    2. `In-Reply-To` → TicketMessage.message_id on a ticket in this company.
    3. Any header in `References` → TicketMessage.message_id.
    """
    from .models import Ticket, TicketMessage

    # 1. Subject tag
    m = _SUBJECT_TAG_RE.search(parsed.subject or '')
    if m:
        try:
            tid = int(m.group(1))
        except ValueError:
            tid = 0
        if tid:
            t = Ticket.objects.filter(pk=tid, company=company).first()
            if t:
                return t, 'subject_tag'

    # 2. In-Reply-To
    if parsed.in_reply_to:
        tm = (TicketMessage.objects
              .filter(message_id=parsed.in_reply_to, ticket__company=company)
              .select_related('ticket').first())
        if tm:
            return tm.ticket, 'in_reply_to'

    # 3. References
    for ref in parsed.references or []:
        if not ref:
            continue
        tm = (TicketMessage.objects
              .filter(message_id=ref, ticket__company=company)
              .select_related('ticket').first())
        if tm:
            return tm.ticket, 'references'

    return None, ''


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _parse_header_blob(blob: str) -> dict:
    """Parse an RFC 822 header blob into a dict. Last header wins on dupes."""
    out: dict[str, str] = {}
    if not blob:
        return out
    current_key = None
    for raw in blob.splitlines():
        if not raw:
            continue
        if raw[0] in (' ', '\t') and current_key:
            out[current_key] = out.get(current_key, '') + ' ' + raw.strip()
            continue
        if ':' in raw:
            k, _, v = raw.partition(':')
            current_key = k.strip()
            out[current_key] = v.strip()
    return out


def _split_address_list(s: str) -> list[str]:
    if not s:
        return []
    parsed = email.utils.getaddresses([s])
    return [addr for _, addr in parsed if addr]


def _strip_angle(s: str) -> str:
    if not s:
        return ''
    s = s.strip()
    if s.startswith('<') and s.endswith('>'):
        return s[1:-1]
    return s


def _looks_auto_reply(headers: dict) -> bool:
    if not headers:
        return False
    for k in ('Auto-Submitted', 'X-Auto-Response-Suppress', 'Precedence'):
        v = (headers.get(k, '') or '').lower()
        if v and v not in ('no', 'none'):
            return True
    if (headers.get('X-Autorespond', '') or '').strip():
        return True
    return False


# --------------------------------------------------------------------------
# Constants consumed by the outbound reply path
# --------------------------------------------------------------------------

def build_subject_tag(ticket_id: int) -> str:
    """Stable tag we inject into outbound reply subjects so we can thread
    even if In-Reply-To/References are stripped by the customer's mail client."""
    return f"[FL-{ticket_id}]"

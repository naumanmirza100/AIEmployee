"""
Reply Draft Agent API Views for Company Users.

Mirrors the pattern in api/views/marketing_agent.py: DRF + CompanyUserTokenAuthentication.
Resolves the CompanyUser to a Django User (same bridge marketing uses) because
the underlying models (Lead, Reply, EmailAccount) are keyed on User.
"""
import logging
import re
from datetime import datetime, timedelta

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from django.contrib.auth.models import User
from django.db.models import Count, Max, Prefetch, Q
from django.utils import timezone

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.models import CompanyUser
from marketing_agent.models import Reply, Campaign, Lead, EmailSendHistory, EmailAccount
from reply_draft_agent.agents.reply_draft_agent import ReplyDraftAgent
from reply_draft_agent.models import ReplyDraft, InboxEmail, InboxAttachment
from reply_draft_agent.permissions import company_has_module

logger = logging.getLogger(__name__)


def _get_or_create_user_for_company_user(company_user):
    """Bridge CompanyUser → Django User. Copied from api/views/marketing_agent.py."""
    try:
        return User.objects.get(email=company_user.email)
    except User.DoesNotExist:
        username = f"company_user_{company_user.id}_{company_user.email}"
        return User.objects.create_user(
            username=username,
            email=company_user.email,
            password=None,
            first_name=company_user.full_name.split()[0] if company_user.full_name else '',
            last_name=' '.join(company_user.full_name.split()[1:])
                if company_user.full_name and len(company_user.full_name.split()) > 1 else '',
        )


def _enforce_module(company_user):
    """Return None if allowed, or a Response 403 if not."""
    if not company_has_module(company_user.company):
        return Response(
            {
                'status': 'error',
                'message': 'Reply Draft Agent is not active for your company. Purchase required.',
                'module_name': 'reply_draft_agent',
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _get_reply_account(user_ids):
    """The single EmailAccount flagged for this company's Reply Draft Agent.

    The Reply Draft Agent intentionally uses a dedicated account, isolated
    from the marketing-campaign account list. Returns None when the company
    hasn't attached one yet — the UI prompts the user to add one.
    """
    return (
        EmailAccount.objects
        .filter(owner_id__in=user_ids, is_reply_agent_account=True)
        .first()
    )


def _sender_name(lead):
    if not lead:
        return ''
    full = ' '.join(filter(None, [lead.first_name, lead.last_name])).strip()
    return full or (lead.email.split('@')[0] if lead.email else '')


def _serialize_reply(r, *, include_body=False):
    """Serialize a Reply row.

    ``include_body`` is False in the list response (the ``body`` field is deferred
    and ``preview`` is pre-computed via SQL SUBSTRING in the queryset annotation).
    The detail endpoint passes True so clicking a row returns the full content.
    """
    lead = r.lead if r.lead_id else None
    preview = getattr(r, '_list_preview', None)
    if preview is None:
        preview = (r.reply_content or '')[:200]
    out = {
        'id': r.id,
        'source': 'reply',
        'from_email': lead.email if lead else '',
        'from_name': _sender_name(lead),
        'from_company': lead.company if lead else '',
        'from_job_title': lead.job_title if lead else '',
        'subject': r.reply_subject or '(no subject)',
        'preview': preview,
        'interest_level': r.interest_level,
        'replied_at': r.replied_at.isoformat() if r.replied_at else None,
        'campaign_id': r.campaign_id,
        'campaign': r.campaign.name if r.campaign_id else '',
        'analysis': r.analysis or '',
    }
    if include_body:
        out['body'] = r.reply_content or ''
    return out


_CID_REF_RE = re.compile(r'''(["'])\s*cid:\s*([^"'>\s]+)\s*\1''', re.IGNORECASE)


# MIME types that are technical bounce/DSN metadata and shouldn't appear
# as user-facing attachments. Bounce emails ("Delivery Status Notification
# (Failure)") wrap the failed message + headers as separate parts; users
# don't want to see those as files to download.
_BOUNCE_MIME_TYPES = frozenset({
    'text/rfc822-headers',
    'message/delivery-status',
    'message/disposition-notification',
    'message/feedback-report',
    'message/global-delivery-status',
    'message/global-headers',
})

# Filename patterns that we generate ourselves when a part has no proper
# filename (see sync_inbox.get_email_attachments). These are always
# bounce/system metadata and should be hidden from the user.
_BOUNCE_FILENAME_HINTS = (
    'attachment.text_rfc822-headers',
    'attachment.message_delivery-status',
    'attachment.message_disposition-notification',
)

# Subject + sender hints that mark a message as a bounce / DSN. When this
# matches, we get more aggressive about hiding attachments — bounce
# notifiers commonly include a tiny status icon (icon.png ~1-2 KB) that's
# pure visual chrome the email client should absorb, not show as a file
# to download.
_BOUNCE_SUBJECT_HINTS = (
    'delivery status notification',
    'undeliverable',
    'undelivered mail',
    'mail delivery failed',
    'mail delivery failure',
    'returned mail',
    'failure notice',
    'message not delivered',
    'delivery failure',
)
_BOUNCE_FROM_HINTS = (
    'mailer-daemon',
    'postmaster',
    'mail-daemon',
    'mail delivery subsystem',
)
# Status icons embedded in bounce mail are tiny — anything legitimately
# attached by a human is bigger than this. Threshold is intentionally
# conservative; raise if real attachments start getting hidden.
_BOUNCE_ICON_MAX_BYTES = 8 * 1024  # 8 KB


def _is_bounce_email(email):
    """Heuristic: is this InboxEmail a delivery failure / bounce notification?"""
    subj = (email.subject or '').lower()
    if any(h in subj for h in _BOUNCE_SUBJECT_HINTS):
        return True
    sender = (email.from_email or '').lower()
    from_name = (email.from_name or '').lower()
    if any(h in sender for h in _BOUNCE_FROM_HINTS):
        return True
    if any(h in from_name for h in _BOUNCE_FROM_HINTS):
        return True
    return False


def _is_bounce_metadata(att, *, is_bounce_email=False):
    """True if this attachment is bounce/DSN metadata, not a user file.

    `is_bounce_email` widens the filter: when the parent message is a
    bounce notification, small image attachments (status icons like
    icon.png at ~1-2 KB) are also hidden. Outside bounce mail those
    same images could be real user attachments, so the size heuristic
    only kicks in here.
    """
    ct = (att.content_type or '').lower().strip()
    if ct in _BOUNCE_MIME_TYPES:
        return True
    fn = (att.filename or '').lower().strip()
    if any(fn.startswith(h) for h in _BOUNCE_FILENAME_HINTS):
        return True
    if is_bounce_email:
        # Tiny images on a bounce mail = postmaster status icon.
        if ct.startswith('image/') and (att.size_bytes or 0) <= _BOUNCE_ICON_MAX_BYTES:
            return True
    return False


def _rewrite_cid_refs(html, attachments):
    """Replace ``src="cid:abc@host"`` with the inline attachment's download URL.

    `attachments` is the queryset/list of the email's InboxAttachment rows
    (inline + non-inline); we match by ``content_id`` (with surrounding
    angle brackets stripped, since those are part of the wire format but
    not what HTML attributes use). Returns the rewritten HTML; pass-through
    on no matches so the cost is a single regex scan when there's nothing
    to rewrite.
    """
    if not html or '<' not in html:
        return html
    cid_map = {}
    for att in attachments:
        cid = (att.content_id or '').strip()
        if not cid:
            continue
        # Strip angle brackets ("<image001@…>" → "image001@…") — that's
        # the form they appear as inside HTML's src="cid:…" references.
        cid = cid.lstrip('<').rstrip('>')
        cid_map[cid.lower()] = att.id

    if not cid_map:
        return html

    # We don't know the email_id at this depth, so the caller passes it via
    # the closure. Build a cheap per-call replacer.
    def _make_replacer(email_id):
        def _replace(match):
            quote = match.group(1)
            cid = match.group(2).strip().lower()
            att_id = cid_map.get(cid)
            if not att_id:
                return match.group(0)
            return f'{quote}/api/reply-draft/inbox/{email_id}/attachments/{att_id}/download{quote}'
        return _replace

    # Email_id is bound on the wrapper below — _rewrite_cid_refs itself is
    # called with `attachments` already attached to a single email, so we
    # piggy-back on the FK on the first row. Falling back to the original
    # html when the list is empty keeps this safe under empty-attachment
    # paths.
    first = next(iter(attachments), None)
    if first is None:
        return html
    return _CID_REF_RE.sub(_make_replacer(first.inbox_email_id), html)


def _serialize_inbox_email(m, *, include_body=False):
    """Serialize an InboxEmail row. See _serialize_reply for ``include_body`` semantics.

    `to_email` and `direction` are exposed so the frontend Sent tab can
    render "To: <recipient>" instead of the from-address. `replied_at`
    is reused as the row's timestamp regardless of direction; the field
    name is historical (originally only inbound replies were listed).
    """
    preview = getattr(m, '_list_preview', None)
    if preview is None:
        preview = (m.body or '')[:200]
    out = {
        'id': m.id,
        'source': 'inbox',
        'direction': m.direction,
        'from_email': m.from_email,
        'from_name': m.from_name,
        'to_email': m.to_email,
        'from_company': '',
        'from_job_title': '',
        'subject': m.subject or '(no subject)',
        'preview': preview,
        'interest_level': m.interest_level,
        'replied_at': m.received_at.isoformat() if m.received_at else None,
        'campaign_id': None,
        'campaign': '',
        'analysis': m.analysis or '',
        'thread_key': getattr(m, 'thread_key', '') or '',
    }
    if include_body:
        out['body'] = m.body or ''
        body_html = getattr(m, 'body_html', '') or ''

        # Pull attachments once — used both for the downloadable list and
        # for cid: rewrite below. Inline parts are filtered out of the user-
        # visible list but kept available to the rewriter so embedded images
        # actually load.
        all_attachments = []
        try:
            all_attachments = list(m.attachments.all())
        except Exception:
            all_attachments = []

        # Rewrite cid: refs inside body_html so inline images served from
        # our attachment endpoint actually render. Falls through cleanly
        # on emails without inline parts.
        if body_html and all_attachments:
            body_html = _rewrite_cid_refs(body_html, all_attachments)

        out['body_html'] = body_html

        is_bounce = _is_bounce_email(m)
        attachments = []
        for att in all_attachments:
            if att.is_inline:
                continue
            # Hide bounce/DSN technical parts — rfc822-headers, delivery-
            # status, tiny status icons. MIME plumbing the email client
            # should absorb, not show as user-facing files. Without this,
            # every bounce mail produced 2-3 useless "attachments" at the
            # bottom (icon.png + delivery-status + rfc822-headers).
            if _is_bounce_metadata(att, is_bounce_email=is_bounce):
                continue
            attachments.append({
                'id': att.id,
                'filename': att.filename,
                'content_type': att.content_type,
                'size_bytes': att.size_bytes,
                'download_url': f'/api/reply-draft/inbox/{m.id}/attachments/{att.id}/download',
            })
        out['attachments'] = attachments
    return out


def _serialize_draft(d):
    if d.lead_id and d.lead:
        to_email = d.lead.email
        to_name = _sender_name(d.lead)
        to_company = d.lead.company
    elif d.inbox_email_id and d.inbox_email:
        to_email = d.inbox_email.from_email
        to_name = d.inbox_email.from_name
        to_company = ''
    else:
        to_email = ''
        to_name = ''
        to_company = ''

    return {
        'id': d.id,
        'status': d.status,
        'tone': d.tone,
        'source': d.source_kind,
        'to_email': to_email,
        'to_name': to_name,
        'to_company': to_company,
        'subject': d.get_final_subject(),
        'body': d.get_final_body(),
        'ai_notes': d.ai_notes,
        'original_email_id': d.original_email_id,
        'inbox_email_id': d.inbox_email_id,
        'original_subject': d.get_original_subject(),
        'original_body': d.get_original_body(),
        'regeneration_count': d.regeneration_count,
        'created_at': d.created_at.isoformat(),
        'updated_at': d.updated_at.isoformat() if d.updated_at else None,
        'sent_at': d.sent_at.isoformat() if d.sent_at else None,
        'send_error': d.send_error,
    }


def _parse_days_filter(value):
    """Return a timezone-aware cutoff datetime, or None for 'all time'.

    Missing / blank / 'all' means no cutoff — the natural cap is whatever is
    already stored (Celery always pre-syncs the full 120-day window on a cron,
    so the dropdown is a pure view filter). Specific integers narrow the view.
    """
    if value is None or value == '' or str(value).lower() == 'all':
        return None
    try:
        days = int(value)
    except (TypeError, ValueError):
        return None
    if days <= 0:
        return None
    return timezone.now() - timedelta(days=days)


def _company_bridge_user_ids(company_user):
    """Django User ids bridged from every active CompanyUser in this company.

    The Reply Draft agent operates on the full set because inbox mail can land
    in any company user's mailbox and the business rule is "show replies from
    leads across all of this company's campaigns".
    """
    company = getattr(company_user, 'company', None)
    if company is None:
        user = _get_or_create_user_for_company_user(company_user)
        return [user.id]
    emails = list(
        CompanyUser.objects.filter(company=company, is_active=True)
        .values_list('email', flat=True)
    )
    if not emails:
        user = _get_or_create_user_for_company_user(company_user)
        return [user.id]
    ids = list(User.objects.filter(email__in=emails).values_list('id', flat=True))
    # Always include the caller's own bridge user in case it hasn't been
    # materialized for another CompanyUser yet.
    caller_user = _get_or_create_user_for_company_user(company_user)
    if caller_user.id not in ids:
        ids.append(caller_user.id)
    return ids


def _visible_campaigns(user_ids):
    """Campaigns across the whole company (any active CompanyUser's bridged owner)."""
    return Campaign.objects.filter(owner_id__in=user_ids).order_by('-created_at')


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def dashboard(request):
    """Reply Draft dashboard — stats + recent items."""
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate

    user_ids = _company_bridge_user_ids(request.user)
    try:
        reply_account = _get_reply_account(user_ids)
        # Scope ReplyDraft counts to the attached reply-agent account so old
        # drafts created against marketing accounts (before isolation) and
        # drafts that no longer match the currently-attached mailbox don't
        # inflate the "pending" / "approved" cards. Null email_account is
        # kept so legacy drafts without a FK still appear; matching list_drafts.
        drafts_qs = ReplyDraft.objects.filter(owner_id__in=user_ids)
        if reply_account is not None:
            drafts_qs = drafts_qs.filter(
                Q(email_account_id=reply_account.id) | Q(email_account__isnull=True)
            )
        else:
            # No mailbox attached → only legacy drafts can count, otherwise
            # the dashboard would show stale marketing-side numbers.
            drafts_qs = drafts_qs.filter(email_account__isnull=True)

        # "Live" drafts only — rejected ones don't block the original from being pending again.
        live_drafts_qs = drafts_qs.exclude(status='rejected')

        # Pending inbox count is similarly scoped to the attached account —
        # without this, inbox rows from a previously-attached mailbox would
        # bleed into the pending tally.
        if reply_account is not None:
            inbox_pool = InboxEmail.objects.filter(
                owner_id__in=user_ids, email_account_id=reply_account.id, direction='in',
            )
        else:
            inbox_pool = InboxEmail.objects.none()

        pending_reply_count = Reply.objects.filter(lead__owner_id__in=user_ids).exclude(
            id__in=live_drafts_qs.filter(original_email_id__isnull=False).values_list('original_email_id', flat=True)
        ).count()

        pending_inbox_count = (
            inbox_pool
            .exclude(id__in=live_drafts_qs.filter(inbox_email_id__isnull=False).values_list('inbox_email_id', flat=True))
            .count()
        )

        stats = {
            'pending_replies': pending_reply_count + pending_inbox_count,
            'pending_campaign_replies': pending_reply_count,
            'pending_inbox_emails': pending_inbox_count,
            'drafts_pending': drafts_qs.filter(status='pending').count(),
            'drafts_approved': drafts_qs.filter(status='approved').count(),
            'drafts_sent': drafts_qs.filter(status='sent').count(),
            'drafts_failed': drafts_qs.filter(status='failed').count(),
        }

        recent_drafts = list(drafts_qs.select_related('lead', 'inbox_email').order_by('-created_at')[:10])
        return Response({
            'status': 'success',
            'data': {
                'stats': stats,
                'recent_drafts': [_serialize_draft(d) for d in recent_drafts],
            }
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("reply_draft dashboard failed")
        return Response(
            {'status': 'error', 'message': 'Failed to load reply draft dashboard', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_pending_replies(request):
    """Inbox / Sent view: every mail in the company's Reply Draft Agent
    account in the window, scoped by direction. Isolated from marketing —
    if the company hasn't attached a Reply Draft Agent account yet, the
    list is empty by design.

    Query params:
      - days: 1 / 7 / 30 / 60 / 90 / 120 / 'all' (default: all stored rows;
              the underlying storage window is set per-account via Sync depth)
      - direction: 'in' (Inbox tab — default, backwards-compat)
                   'out' (Sent tab — populated by the IMAP Sent-folder sync)
    """
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate

    user_ids = _company_bridge_user_ids(request.user)
    days_cutoff = _parse_days_filter(request.GET.get('days'))
    # 'in' default keeps existing inbox callers unchanged. The Sent tab
    # passes direction=out explicitly.
    direction = request.GET.get('direction', 'in')
    if direction not in ('in', 'out'):
        direction = 'in'

    reply_account = _get_reply_account(user_ids)
    if reply_account is None:
        # No account attached yet — nothing to show. The UI prompts the user
        # to add one; the endpoint stays consistent and returns an empty list
        # instead of 404 so polling code doesn't need special-case branches.
        return Response({'status': 'success', 'data': [], 'total': 0})

    # Only LIVE drafts block their original from re-appearing in the inbox.
    # Rejected/discarded drafts should send the original back to the inbox so
    # the user can draft again.
    drafted_inbox_ids = set(
        ReplyDraft.objects.filter(owner_id__in=user_ids, inbox_email_id__isnull=False)
        .exclude(status='rejected')
        .values_list('inbox_email_id', flat=True)
    )

    items = []

    # Defer the body column entirely. Per-row body is 10-100KB on MSSQL, so
    # fetching it for hundreds of rows just to compute a 200-char preview
    # was the dominant cost of this endpoint (multi-second responses for the
    # Sent tab in particular). The list view shows from/subject/date/badge —
    # body is loaded lazily via getReplyItem when the user clicks a row.
    # `_list_preview` is set to '' so the serializer's fallback never touches
    # `m.body` (which would trigger an N+1 query under defer).
    inbox_qs = (
        InboxEmail.objects
        .filter(owner_id__in=user_ids, email_account_id=reply_account.id, direction=direction)
        .exclude(id__in=drafted_inbox_ids)
        .select_related('email_account')
        .defer('body', 'body_html')
    )
    if days_cutoff is not None:
        inbox_qs = inbox_qs.filter(received_at__gte=days_cutoff)
    # Cap at 500 — the previous 2000 was a worst-case safety net but with
    # body deferred + paged list, the user only ever scrolls through the
    # most recent few hundred. A smaller cap also keeps the JSON payload
    # tight enough to render instantly on dropdown changes.
    LIST_LIMIT = 500
    visible_rows = list(inbox_qs.order_by('-received_at')[:LIST_LIMIT])

    # Per-thread message count across BOTH directions of the same account
    # — so a thread that has 1 inbox message + 3 sent replies shows as a
    # 4-message thread in both tabs. Single query, no N+1.
    thread_counts = {}
    thread_keys = {m.thread_key for m in visible_rows if m.thread_key}
    if thread_keys:
        from django.db.models import Count as _Count
        # `.order_by()` (empty) clears the model's Meta.ordering = ['-received_at']
        # default. Without this, SQL Server rejects the query because
        # received_at ends up in ORDER BY without being in GROUP BY
        # ("Column ... is invalid in the ORDER BY clause"). On Postgres
        # the default ordering is silently absorbed; MSSQL is strict.
        for row in (
            InboxEmail.objects
            .filter(email_account_id=reply_account.id, thread_key__in=thread_keys)
            .order_by()
            .values('thread_key')
            .annotate(c=_Count('id'))
        ):
            thread_counts[row['thread_key']] = row['c']

    for m in visible_rows:
        m._list_preview = ''
        serialized = _serialize_inbox_email(m)
        # Surface thread depth so the UI can show "5 messages" badges.
        # Default 1 covers the (common) case where a message has no
        # thread_key yet (synced before backfill).
        serialized['thread_count'] = thread_counts.get(m.thread_key, 1) if m.thread_key else 1
        items.append((m.received_at, serialized))

    items.sort(key=lambda pair: pair[0] or timezone.now(), reverse=True)
    payload = [entry for _, entry in items]

    return Response({
        'status': 'success',
        'data': payload,
    })


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_inbox_email(request, email_id):
    """Return a single InboxEmail row including its full body.

    Used by the frontend when the user clicks a row — the list view serves
    only previews (see list_pending_replies) because pulling body for every
    row turned MSSQL into a bottleneck.
    """
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate
    user_ids = _company_bridge_user_ids(request.user)
    reply_account = _get_reply_account(user_ids)
    if reply_account is None:
        return Response({'status': 'error', 'message': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    # Detail serializer doesn't read any EmailAccount fields, so no
    # select_related — that join was an unused 200ms tax on every click.
    m = (
        InboxEmail.objects
        .filter(id=email_id, owner_id__in=user_ids, email_account_id=reply_account.id)
        .first()
    )
    if m is None:
        return Response({'status': 'error', 'message': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    return Response({'status': 'success', 'data': _serialize_inbox_email(m, include_body=True)})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_inbox_attachments(request, email_id):
    """Return attachment metadata for a single InboxEmail.

    The detail endpoint already inlines this list, so this is mostly here
    for a future "Files" tab / standalone refresh; the current frontend
    reads attachments directly off the email payload.
    """
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate
    user_ids = _company_bridge_user_ids(request.user)
    reply_account = _get_reply_account(user_ids)
    if reply_account is None:
        return Response({'status': 'error', 'message': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    # Permission: scope by reply-agent account so a different tenant's
    # attachments can't be enumerated by ID-guessing. Pulls subject /
    # from_email too so the bounce-detection heuristic can see them.
    email = InboxEmail.objects.filter(
        id=email_id, owner_id__in=user_ids, email_account_id=reply_account.id,
    ).only('id', 'subject', 'from_email', 'from_name').first()
    if email is None:
        return Response({'status': 'error', 'message': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    is_bounce = _is_bounce_email(email)
    payload = []
    for att in InboxAttachment.objects.filter(inbox_email_id=email.id).only(
        'id', 'filename', 'content_type', 'size_bytes', 'is_inline', 'created_at'
    ):
        if att.is_inline:
            continue
        # Same bounce-DSN filter the detail serializer uses — kept in sync
        # so the standalone "Files" view doesn't surface plumbing.
        if _is_bounce_metadata(att, is_bounce_email=is_bounce):
            continue
        payload.append({
            'id': att.id,
            'filename': att.filename,
            'content_type': att.content_type,
            'size_bytes': att.size_bytes,
            'created_at': att.created_at.isoformat() if att.created_at else None,
            'download_url': f'/api/reply-draft/inbox/{email.id}/attachments/{att.id}/download',
        })
    return Response({'status': 'success', 'data': payload})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def download_inbox_attachment(request, email_id, attachment_id):
    """Stream the file bytes for a single attachment.

    Same tenant scoping as the detail endpoint — the email_id in the URL
    must belong to the caller's reply-agent account, and the attachment
    must belong to that email. Returns 404 (not 403) on mismatch so we
    don't leak existence.
    """
    from django.http import FileResponse, Http404
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate
    user_ids = _company_bridge_user_ids(request.user)
    reply_account = _get_reply_account(user_ids)
    if reply_account is None:
        return Response({'status': 'error', 'message': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    att = (
        InboxAttachment.objects
        .filter(
            id=attachment_id,
            inbox_email_id=email_id,
            inbox_email__owner_id__in=user_ids,
            inbox_email__email_account_id=reply_account.id,
        )
        .first()
    )
    if att is None or not att.file:
        return Response({'status': 'error', 'message': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        # FileField.open() respects whatever default_storage points at —
        # local disk today, S3 later — so this download endpoint stays
        # untouched when the storage backend changes.
        fh = att.file.open('rb')
        resp = FileResponse(
            fh,
            content_type=att.content_type or 'application/octet-stream',
            as_attachment=True,
            filename=att.filename or 'attachment',
        )
        # Long cache: file content is immutable (sha256 in path). Browser
        # can re-show the same file without another DB / storage round-trip.
        resp['Cache-Control'] = 'private, max-age=3600'
        return resp
    except (FileNotFoundError, Http404):
        return Response({'status': 'error', 'message': 'File missing on storage'},
                        status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception('download_inbox_attachment failed')
        return Response({'status': 'error', 'message': str(e)},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_reply(request, reply_id):
    """Return a single Reply (campaign reply) row including its full content."""
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate
    user_ids = _company_bridge_user_ids(request.user)
    r = Reply.objects.filter(id=reply_id, lead__owner_id__in=user_ids).select_related('lead', 'campaign').first()
    if r is None:
        return Response({'status': 'error', 'message': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    return Response({'status': 'success', 'data': _serialize_reply(r, include_body=True)})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_sync_accounts(request):
    """Small summary of the email accounts this company is (or should be) syncing.

    Powers a visibility card in the Reply Draft UI — "where does this inbox
    come from" and "why is the inbox empty" (if no account is configured).
    Returns both configured and IMAP-ready-but-misconfigured accounts so the
    UI can flag them.
    """
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate
    user_ids = _company_bridge_user_ids(request.user)
    # Reply Draft Agent is isolated from marketing: it only surfaces the
    # single EmailAccount explicitly attached to it (is_reply_agent_account).
    # Accounts added on the Marketing Agent side are intentionally excluded.
    accounts = EmailAccount.objects.filter(
        owner_id__in=user_ids, is_reply_agent_account=True,
    ).order_by('-is_default', '-is_active', '-created_at')

    # Single query to avoid N+1 when there are many accounts.
    from django.db.models import Count
    inbox_counts = dict(
        InboxEmail.objects.filter(email_account_id__in=[a.id for a in accounts])
        .values_list('email_account_id')
        .order_by()
        .annotate(c=Count('id'))
    )

    data = []
    for a in accounts:
        imap_ready = bool(a.imap_host and a.imap_username and a.imap_password)
        will_sync = a.is_active and a.enable_imap_sync and imap_ready
        inbox_count = inbox_counts.get(a.id, 0)
        data.append({
            'id': a.id,
            'name': a.name,
            'email': a.email,
            'account_type': a.account_type,
            'is_active': a.is_active,
            'enable_imap_sync': a.enable_imap_sync,
            'imap_ready': imap_ready,   # has all three credential fields
            'will_sync': will_sync,
            # SMTP connection fields. The password itself is never returned —
            # the edit form treats a blank password as "keep what's stored".
            'smtp_host': a.smtp_host or '',
            'smtp_port': a.smtp_port,
            'smtp_username': a.smtp_username or '',
            'use_tls': a.use_tls,
            'use_ssl': a.use_ssl,
            'is_gmail_app_password': a.is_gmail_app_password,
            # IMAP connection fields (same password policy as SMTP above).
            'imap_host': a.imap_host or '',
            'imap_port': a.imap_port,
            'imap_username': a.imap_username or '',
            'imap_use_ssl': a.imap_use_ssl,
            'last_tested_at': a.last_tested_at.isoformat() if a.last_tested_at else None,
            'test_status': getattr(a, 'test_status', 'not_tested') or 'not_tested',
            # --- First-sync UX signals ---
            # inbox_count lets the frontend show a "Syncing your inbox…" card
            # when the account is configured but no rows have landed yet.
            'inbox_count': inbox_count,
            'created_at': a.created_at.isoformat() if a.created_at else None,
            'updated_at': a.updated_at.isoformat() if a.updated_at else None,
        })
    return Response({'status': 'success', 'data': data})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_campaigns(request):
    """Campaigns available as a filter option in the Reply Draft inbox."""
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate
    user_ids = _company_bridge_user_ids(request.user)
    data = [
        {'id': c.id, 'name': c.name, 'status': c.status}
        for c in _visible_campaigns(user_ids)[:200]
    ]
    return Response({'status': 'success', 'data': data})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_leads(request):
    """All leads across every campaign in this company, with reply analytics.

    Response shape per lead:
      {
        id, email, first_name, last_name, company, job_title,
        campaigns: [{id, name, status}],
        emails_sent, replies_count, last_reply_at, latest_interest_level,
        has_replied, latest_analysis
      }

    Query params:
      - search: substring match across email / name / company
      - has_replied: 'yes' | 'no' (optional)
      - campaign: campaign id to filter leads to a single campaign (optional)
    """
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate

    user_ids = _company_bridge_user_ids(request.user)
    if not user_ids:
        return Response({'status': 'success', 'data': []})

    campaign_ids = list(
        Campaign.objects.filter(owner_id__in=user_ids).values_list('id', flat=True)
    )
    if not campaign_ids:
        return Response({'status': 'success', 'data': []})

    # Leads attached to any of the company's campaigns. distinct() avoids dupes
    # when a lead is on multiple campaigns.
    leads_qs = (
        Lead.objects
        .filter(campaigns__in=campaign_ids)
        .annotate(
            emails_sent=Count('email_history', distinct=True),
            replies_count=Count('replies', distinct=True),
            last_reply_at=Max('replies__replied_at'),
        )
        .prefetch_related(
            Prefetch(
                'campaigns',
                queryset=Campaign.objects.filter(id__in=campaign_ids).only('id', 'name', 'status'),
            )
        )
        .distinct()
    )

    search = (request.GET.get('search') or '').strip().lower()
    if search:
        from django.db.models import Q
        leads_qs = leads_qs.filter(
            Q(email__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(company__icontains=search)
        )

    has_replied = (request.GET.get('has_replied') or '').strip().lower()
    if has_replied == 'yes':
        leads_qs = leads_qs.filter(replies_count__gt=0)
    elif has_replied == 'no':
        leads_qs = leads_qs.filter(replies_count=0)

    campaign_param = (request.GET.get('campaign') or '').strip()
    if campaign_param:
        try:
            leads_qs = leads_qs.filter(campaigns__id=int(campaign_param))
        except ValueError:
            pass

    leads = list(leads_qs.order_by('-last_reply_at', '-id')[:500])

    # Pull the most-recent Reply per lead for interest_level + analysis snippet.
    lead_ids = [l.id for l in leads]
    latest_reply_by_lead = {}
    if lead_ids:
        latest_ids = (
            Reply.objects.filter(lead_id__in=lead_ids)
            .order_by('lead_id', '-replied_at')
            .distinct('lead_id')  # works on Postgres; MSSQL falls through below
        )
        try:
            for r in latest_ids:
                latest_reply_by_lead[r.lead_id] = r
        except Exception:
            latest_reply_by_lead = {}

        if not latest_reply_by_lead:
            # Portable fallback: group in Python.
            for r in Reply.objects.filter(lead_id__in=lead_ids).order_by('-replied_at').only(
                'lead_id', 'interest_level', 'analysis', 'replied_at'
            ):
                latest_reply_by_lead.setdefault(r.lead_id, r)

    data = []
    for lead in leads:
        latest = latest_reply_by_lead.get(lead.id)
        data.append({
            'id': lead.id,
            'email': lead.email,
            'first_name': lead.first_name,
            'last_name': lead.last_name,
            'full_name': ' '.join(filter(None, [lead.first_name, lead.last_name])).strip(),
            'company': lead.company,
            'job_title': lead.job_title,
            'campaigns': [
                {'id': c.id, 'name': c.name, 'status': c.status}
                for c in lead.campaigns.all()
            ],
            'emails_sent': lead.emails_sent or 0,
            'replies_count': lead.replies_count or 0,
            'has_replied': bool(lead.replies_count),
            'last_reply_at': lead.last_reply_at.isoformat() if lead.last_reply_at else None,
            'latest_interest_level': latest.interest_level if latest else '',
            'latest_analysis': (latest.analysis[:300] if latest and latest.analysis else ''),
        })

    return Response({'status': 'success', 'data': data})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_drafts(request):
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate
    user_ids = _company_bridge_user_ids(request.user)
    reply_account = _get_reply_account(user_ids)
    if reply_account is None:
        return Response({'status': 'success', 'data': []})
    # Scope drafts to the attached Reply Draft Agent account so older drafts
    # created from a marketing account before isolation was introduced don't
    # leak into the view. Drafts with no email_account FK are shown too — they
    # predate this flag and deleting them silently would be worse than showing.
    qs = (
        ReplyDraft.objects
        .filter(owner_id__in=user_ids)
        .filter(Q(email_account_id=reply_account.id) | Q(email_account__isnull=True))
        .select_related('lead', 'original_email', 'inbox_email')
    )
    status_filter = request.GET.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)
    else:
        # Hide rejected drafts by default — they're terminal and shouldn't clutter the list.
        qs = qs.exclude(status='rejected')
    drafts = list(qs.order_by('-created_at')[:100])
    return Response({
        'status': 'success',
        'data': [_serialize_draft(d) for d in drafts],
    })


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def generate_draft(request):
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate
    user = _get_or_create_user_for_company_user(request.user)

    payload = request.data or {}
    original_email_id = payload.get('original_email_id')
    inbox_email_id = payload.get('inbox_email_id')
    if not original_email_id and not inbox_email_id:
        return Response({'status': 'error', 'message': 'original_email_id or inbox_email_id is required'},
                        status=status.HTTP_400_BAD_REQUEST)
    if original_email_id and inbox_email_id:
        return Response({'status': 'error', 'message': 'Provide only one of original_email_id / inbox_email_id'},
                        status=status.HTTP_400_BAD_REQUEST)

    agent = ReplyDraftAgent(user=user)
    result = agent.generate_draft(
        original_email_id=original_email_id,
        inbox_email_id=inbox_email_id,
        user_context=payload.get('user_context', ''),
        tone=payload.get('tone', 'professional'),
        length=payload.get('length'),
        email_account_id=payload.get('email_account_id'),
    )
    if not result.get('success'):
        return Response({'status': 'error', 'message': result.get('error')},
                        status=status.HTTP_400_BAD_REQUEST)
    return Response({'status': 'success', 'data': result})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def regenerate_draft(request, draft_id):
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate
    user = _get_or_create_user_for_company_user(request.user)

    payload = request.data or {}
    agent = ReplyDraftAgent(user=user)
    result = agent.regenerate_draft(
        draft_id=draft_id,
        new_instructions=payload.get('new_instructions', ''),
        tone=payload.get('tone'),
        length=payload.get('length'),
    )
    if not result.get('success'):
        return Response({'status': 'error', 'message': result.get('error')},
                        status=status.HTTP_400_BAD_REQUEST)
    return Response({'status': 'success', 'data': result})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def approve_draft(request, draft_id):
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate
    user = _get_or_create_user_for_company_user(request.user)

    payload = request.data or {}
    agent = ReplyDraftAgent(user=user)
    result = agent.approve_draft(
        draft_id=draft_id,
        edited_subject=payload.get('edited_subject'),
        edited_body=payload.get('edited_body'),
    )
    if not result.get('success'):
        return Response({'status': 'error', 'message': result.get('error')},
                        status=status.HTTP_400_BAD_REQUEST)
    return Response({'status': 'success', 'data': result})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def send_draft(request, draft_id):
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate
    user = _get_or_create_user_for_company_user(request.user)

    agent = ReplyDraftAgent(user=user)
    result = agent.send_approved(draft_id=draft_id)
    if not result.get('success'):
        return Response({'status': 'error', 'message': result.get('error')},
                        status=status.HTTP_400_BAD_REQUEST)
    return Response({'status': 'success', 'data': result})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def reject_draft(request, draft_id):
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate
    user = _get_or_create_user_for_company_user(request.user)

    try:
        draft = ReplyDraft.objects.get(id=draft_id, owner=user)
    except ReplyDraft.DoesNotExist:
        return Response({'status': 'error', 'message': 'Draft not found'},
                        status=status.HTTP_404_NOT_FOUND)
    if draft.status == 'sent':
        return Response({'status': 'error', 'message': 'Already sent'},
                        status=status.HTTP_400_BAD_REQUEST)
    draft.status = 'rejected'
    draft.save(update_fields=['status', 'updated_at'])
    return Response({'status': 'success', 'data': {'draft_id': draft.id, 'status': draft.status}})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_reply_account(request):
    """Create (or re-attach) the single EmailAccount used by the Reply Draft Agent.

    Independent from marketing_agent.create_email_account so that Reply Draft
    accounts stay out of the Marketing Agent account lists. The account is
    created with ``is_reply_agent_account=True`` and ``enable_imap_sync=True``;
    the EmailAccount.save() override demotes any previously-flagged account so
    there is always at most one per owner.

    Triggers an immediate Celery sync so the inbox starts populating within
    ~30 seconds instead of waiting for the next beat tick.
    """
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate
    try:
        user = _get_or_create_user_for_company_user(request.user)
        data = request.data or {}

        name = (data.get('name') or '').strip() or 'Reply Draft Inbox'
        email = (data.get('email') or '').strip()
        if not email:
            return Response(
                {'status': 'error', 'message': 'Email is required.', 'error': 'validation'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        smtp_host = (data.get('smtp_host') or '').strip()
        smtp_port = int(data.get('smtp_port') or 587)
        smtp_username = (data.get('smtp_username') or '').strip() or email
        smtp_password = data.get('smtp_password') or ''
        if not smtp_host or not smtp_password:
            return Response(
                {'status': 'error', 'message': 'SMTP host and password are required.', 'error': 'validation'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # IMAP is the whole point of a Reply Draft account — always required.
        imap_host = (data.get('imap_host') or '').strip()
        imap_port = int(data.get('imap_port') or 993)
        imap_username = (data.get('imap_username') or '').strip() or email
        imap_password = data.get('imap_password') or ''
        if not imap_host or not imap_password:
            return Response(
                {'status': 'error', 'message': 'IMAP host and password are required (the inbox syncs through IMAP).', 'error': 'validation'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify IMAP credentials BEFORE we save the account so the user
        # sees the auth error immediately. Without this the account gets
        # created, the background sync fails, and the UI just spins.
        from api.views.marketing_agent import verify_imap_credentials
        ok, err = verify_imap_credentials(
            imap_host, imap_port,
            bool(data.get('imap_use_ssl', True)),
            imap_username, imap_password,
        )
        if not ok:
            return Response({
                'status': 'error',
                'message': f'IMAP login failed: {err}',
                'error': 'imap_auth_failed',
            }, status=status.HTTP_400_BAD_REQUEST)

        # Duplicate check — create_unique is per (owner, email). If the user is
        # re-attaching an existing account by the same email, just promote it
        # instead of erroring out.
        existing = EmailAccount.objects.filter(owner=user, email__iexact=email).first()
        if existing:
            existing.name = name
            existing.account_type = data.get('account_type', existing.account_type or 'smtp')
            existing.smtp_host = smtp_host
            existing.smtp_port = smtp_port
            existing.smtp_username = smtp_username
            existing.smtp_password = smtp_password
            existing.use_tls = bool(data.get('use_tls', existing.use_tls))
            existing.use_ssl = bool(data.get('use_ssl', existing.use_ssl))
            existing.is_gmail_app_password = bool(data.get('is_gmail_app_password', existing.is_gmail_app_password))
            existing.imap_host = imap_host
            existing.imap_port = imap_port
            existing.imap_username = imap_username
            existing.imap_password = imap_password
            existing.imap_use_ssl = bool(data.get('imap_use_ssl', True))
            existing.enable_imap_sync = True
            existing.is_reply_agent_account = True
            existing.is_active = True
            existing.save()
            account = existing
        else:
            account = EmailAccount.objects.create(
                owner=user,
                name=name,
                account_type=data.get('account_type', 'smtp'),
                email=email,
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                smtp_username=smtp_username,
                smtp_password=smtp_password,
                use_tls=bool(data.get('use_tls', True)),
                use_ssl=bool(data.get('use_ssl', False)),
                is_gmail_app_password=bool(data.get('is_gmail_app_password', False)),
                imap_host=imap_host,
                imap_port=imap_port,
                imap_username=imap_username,
                imap_password=imap_password,
                imap_use_ssl=bool(data.get('imap_use_ssl', True)),
                enable_imap_sync=True,
                is_active=True,
                is_reply_agent_account=True,
            )

        # Single 120-day sync — batched IMAP fetches in sync_inbox bring
        # this in around 30s, so the prior 30-day-fast / 120-day-delayed
        # split is no longer worth its complexity. The 5-min periodic beat
        # is the fallback if this enqueue fails.
        sync_queued = False
        try:
            from marketing_agent.tasks import sync_inbox_task
            sync_inbox_task.delay(account_id=account.id)
            sync_queued = True
        except Exception:
            logger.exception('create_reply_account: failed to enqueue immediate inbox sync')

        return Response({
            'status': 'success',
            'data': {
                'account_id': account.id,
                'email': account.email,
                'message': 'Reply Draft Agent inbox connected.',
                'immediate_sync_queued': sync_queued,
            },
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.exception('create_reply_account failed')
        return Response(
            {'status': 'error', 'message': str(e), 'error': 'failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_reply_account(request):
    """Detach and delete the Reply Draft Agent's EmailAccount.

    Cascades InboxEmail + ReplyDraft rows tied to this account (per the FK
    on_delete behavior in the models). The UI gates this behind a confirm
    dialog — there's no separate soft-detach mode because leaving orphaned
    InboxEmail rows around after the user clicks "Delete" is more confusing
    than cleaning them up.
    """
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate
    try:
        user_ids = _company_bridge_user_ids(request.user)
        account = _get_reply_account(user_ids)
        if account is None:
            return Response(
                {'status': 'error', 'message': 'No Reply Draft account attached.', 'error': 'not_attached'},
                status=status.HTTP_404_NOT_FOUND,
            )
        account_email = account.email
        account.delete()
        return Response({
            'status': 'success',
            'data': {'message': f'{account_email} disconnected and inbox cleared.'},
        })
    except Exception as e:
        logger.exception('delete_reply_account failed')
        return Response(
            {'status': 'error', 'message': str(e), 'error': 'failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def reply_analytics(request):
    """Time-series of inbox mail for the attached Reply Draft Agent account.

    Query params:
      - days: 30 | 60 | 90 | 120 (default 30). Anything out-of-range is clamped.

    Buckets are daily for the 30-day window and weekly for 60/90/120-day
    windows — aggregating longer spans into weeks keeps the line chart from
    looking like a flat line with one spike when mail volume is sparse.
    Scoped to the attached EmailAccount — nothing bleeds in from marketing.
    """
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate

    # Clamp the window to supported values so a bad query string can't cause
    # a 10,000-bucket payload.
    ALLOWED_WINDOWS = (30, 60, 90, 120)
    try:
        days = int(request.GET.get('days') or 30)
    except (TypeError, ValueError):
        days = 30
    if days not in ALLOWED_WINDOWS:
        days = min(ALLOWED_WINDOWS, key=lambda w: abs(w - days))

    # 30-day view stays daily (30 points is fine to read). Anything longer
    # rolls up to 7-day buckets — 60d → 9 points, 90d → 13, 120d → 18.
    granularity = 'day' if days <= 30 else 'week'
    bucket_span_days = 1 if granularity == 'day' else 7
    bucket_count = days if granularity == 'day' else -(-days // 7)  # ceil div

    user_ids = _company_bridge_user_ids(request.user)
    account = _get_reply_account(user_ids)

    today = timezone.now().date()
    buckets = []
    in_qs = None
    out_qs = None
    if account is not None:
        # Split incoming vs outgoing up front so each bucket's two .count()
        # calls don't re-evaluate the direction filter.
        in_qs = InboxEmail.objects.filter(
            owner_id__in=user_ids, email_account_id=account.id, direction='in',
        )
        out_qs = InboxEmail.objects.filter(
            owner_id__in=user_ids, email_account_id=account.id, direction='out',
        )

    # Walk oldest → newest so the frontend can render the series in order.
    for i in range(bucket_count - 1, -1, -1):
        end_day = today - timedelta(days=i * bucket_span_days)
        start_day = end_day - timedelta(days=bucket_span_days - 1)
        start_dt = datetime.combine(start_day, datetime.min.time())
        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt)
        end_dt = datetime.combine(end_day, datetime.min.time()) + timedelta(days=1)
        if timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt)

        if in_qs is not None:
            received = in_qs.filter(received_at__gte=start_dt, received_at__lt=end_dt).count()
            sent = out_qs.filter(received_at__gte=start_dt, received_at__lt=end_dt).count()
        else:
            received = 0
            sent = 0

        # `date` anchors the bucket at its START — that's the conventional
        # label for weekly charts ("week of 2026-04-19").
        # `count` is kept for backwards compatibility with anything still
        # reading the combined total; new callers should prefer received/sent.
        buckets.append({
            'date': start_day.isoformat(),
            'received': received,
            'sent': sent,
            'count': received + sent,
        })

    received_total = sum(b['received'] for b in buckets)
    sent_total = sum(b['sent'] for b in buckets)
    return Response({
        'status': 'success',
        'data': {
            'account_email': account.email if account else None,
            'days': days,
            'granularity': granularity,
            'total': received_total + sent_total,
            'received_total': received_total,
            'sent_total': sent_total,
            'buckets': buckets,
        },
    })



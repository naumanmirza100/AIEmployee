"""
Reply Draft Agent API Views for Company Users.

Mirrors the pattern in api/views/marketing_agent.py: DRF + CompanyUserTokenAuthentication.
Resolves the CompanyUser to a Django User (same bridge marketing uses) because
the underlying models (Lead, Reply, EmailAccount) are keyed on User.
"""
import logging
from datetime import timedelta

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from django.contrib.auth.models import User
from django.db.models import Count, Max, Prefetch, Q
from django.db.models.functions import Substr
from django.utils import timezone

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.models import CompanyUser
from marketing_agent.models import Reply, Campaign, Lead, EmailSendHistory, EmailAccount
from reply_draft_agent.agents.reply_draft_agent import ReplyDraftAgent
from reply_draft_agent.models import ReplyDraft, InboxEmail
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


def _serialize_inbox_email(m, *, include_body=False):
    """Serialize an InboxEmail row. See _serialize_reply for ``include_body`` semantics."""
    preview = getattr(m, '_list_preview', None)
    if preview is None:
        preview = (m.body or '')[:200]
    out = {
        'id': m.id,
        'source': 'inbox',
        'from_email': m.from_email,
        'from_name': m.from_name,
        'from_company': '',
        'from_job_title': '',
        'subject': m.subject or '(no subject)',
        'preview': preview,
        'interest_level': m.interest_level,
        'replied_at': m.received_at.isoformat() if m.received_at else None,
        'campaign_id': None,
        'campaign': '',
        'analysis': m.analysis or '',
    }
    if include_body:
        out['body'] = m.body or ''
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
        drafts_qs = ReplyDraft.objects.filter(owner_id__in=user_ids)
        # "Live" drafts only — rejected ones don't block the original from being pending again.
        live_drafts_qs = drafts_qs.exclude(status='rejected')
        pending_reply_count = Reply.objects.filter(lead__owner_id__in=user_ids).exclude(
            id__in=live_drafts_qs.filter(original_email_id__isnull=False).values_list('original_email_id', flat=True)
        ).count()

        pending_inbox_count = (
            InboxEmail.objects
            .filter(owner_id__in=user_ids)
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
    """Inbox view: every mail that landed in the company's Reply Draft Agent
    account in the window. Isolated from marketing — if the company hasn't
    attached a Reply Draft Agent account yet, the inbox is empty by design.

    Query params:
      - days: 1 / 7 / 30 / 60 / 90 / 120 / 'all' (default: all stored rows;
              the underlying storage window is set per-account via Sync depth)
    """
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate

    user_ids = _company_bridge_user_ids(request.user)
    days_cutoff = _parse_days_filter(request.GET.get('days'))

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

    # The body / reply_content columns can be 10-100KB each on MSSQL. Pulling
    # them for the list view tanked /pending-replies to 30s for 350 rows.
    # We defer them + pre-compute a 200-char preview via SQL SUBSTRING instead;
    # the full body is loaded lazily by the detail endpoints when a row is clicked.
    preview_len = 200

    inbox_qs = (
        InboxEmail.objects
        .filter(owner_id__in=user_ids, email_account_id=reply_account.id)
        .exclude(id__in=drafted_inbox_ids)
        .select_related('email_account')
        .defer('body')
        .annotate(_list_preview=Substr('body', 1, preview_len))
    )
    if days_cutoff is not None:
        inbox_qs = inbox_qs.filter(received_at__gte=days_cutoff)
    for m in inbox_qs.order_by('-received_at')[:2000]:
        items.append((m.received_at, _serialize_inbox_email(m)))

    items.sort(key=lambda pair: pair[0] or timezone.now(), reverse=True)
    # Cap at 2000 so a broken client can't pull the entire mailbox; in
    # practice a 120-day window on a typical business inbox stays well below this.
    payload = [entry for _, entry in items[:2000]]

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
    m = (
        InboxEmail.objects
        .filter(id=email_id, owner_id__in=user_ids, email_account_id=reply_account.id)
        .select_related('email_account')
        .first()
    )
    if m is None:
        return Response({'status': 'error', 'message': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    return Response({'status': 'success', 'data': _serialize_inbox_email(m, include_body=True)})


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
            'imap_host': a.imap_host or '',
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

        # Fire the targeted Celery sync so the inbox populates right away.
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

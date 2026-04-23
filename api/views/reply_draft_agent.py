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
from django.db.models import Count, Max, Prefetch
from django.db.models.functions import Substr
from django.utils import timezone

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.models import CompanyUser
from marketing_agent.models import Reply, Campaign, Lead, EmailSendHistory
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
    """Inbox view: campaign replies + every generic inbox email in the window.

    Generic inbox mail is no longer gated on the sender being a known lead —
    the Reply Draft UI surfaces the full mailbox so the user can draft a reply
    to anything. Use ``days`` to widen or disable the rolling window.

    Query params:
      - campaign: campaign id, or 'none' (generic inbox only), or blank (all)
      - days: 1 / 7 / 30 / 60 / 90 / 120 / 'all' (default: all stored rows;
              the underlying storage window is set per-account via Sync depth)
    """
    gate = _enforce_module(request.user)
    if gate is not None:
        return gate

    user_ids = _company_bridge_user_ids(request.user)
    campaign_param = (request.GET.get('campaign') or '').strip()
    days_cutoff = _parse_days_filter(request.GET.get('days'))

    # Only LIVE drafts block their original from re-appearing in the inbox.
    # Rejected/discarded drafts should send the original back to the inbox so
    # the user can draft again.
    drafted_reply_ids = set(
        ReplyDraft.objects.filter(owner_id__in=user_ids, original_email_id__isnull=False)
        .exclude(status='rejected')
        .values_list('original_email_id', flat=True)
    )
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

    # Campaign replies — included unless the user asked for generic-only ('none').
    if campaign_param != 'none':
        reply_qs = (
            Reply.objects
            .filter(lead__owner_id__in=user_ids)
            .exclude(id__in=drafted_reply_ids)
            .select_related('lead', 'campaign')
            .defer('reply_content')
            .annotate(_list_preview=Substr('reply_content', 1, preview_len))
        )
        if days_cutoff is not None:
            reply_qs = reply_qs.filter(replied_at__gte=days_cutoff)
        if campaign_param and campaign_param != 'none':
            try:
                reply_qs = reply_qs.filter(campaign_id=int(campaign_param))
            except ValueError:
                pass
        for r in reply_qs.order_by('-replied_at')[:2000]:
            items.append((r.replied_at, _serialize_reply(r)))

    # Generic inbox emails — every mail that landed in any of this company's
    # accounts in the window. Excluded entirely when the user picked a specific
    # campaign (that filter is inherently lead-scoped).
    specific_campaign_selected = bool(campaign_param) and campaign_param != 'none'
    if not specific_campaign_selected:
        inbox_qs = (
            InboxEmail.objects.filter(owner_id__in=user_ids)
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
    m = InboxEmail.objects.filter(id=email_id, owner_id__in=user_ids).select_related('email_account').first()
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
    qs = ReplyDraft.objects.filter(owner_id__in=user_ids).select_related('lead', 'original_email', 'inbox_email')
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

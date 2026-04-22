import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from marketing_agent.models import Reply
from .agents.reply_draft_agent import ReplyDraftAgent
from .models import ReplyDraft
from .permissions import requires_reply_draft_module

logger = logging.getLogger(__name__)


def _json_body(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode('utf-8'))
    except (ValueError, TypeError):
        return {}


@login_required
@requires_reply_draft_module
@require_http_methods(['GET'])
def list_pending_replies(request):
    """Inbox replies for the user that don't yet have a draft."""
    drafted_ids = ReplyDraft.objects.filter(owner=request.user).values_list('original_email_id', flat=True)
    replies = (
        Reply.objects
        .filter(lead__owner=request.user)
        .exclude(id__in=list(drafted_ids))
        .select_related('lead', 'campaign')
        .order_by('-replied_at')[:100]
    )
    data = [{
        'id': r.id,
        'from': r.lead.email if r.lead_id else '',
        'subject': r.reply_subject,
        'preview': (r.reply_content or '')[:200],
        'interest_level': r.interest_level,
        'replied_at': r.replied_at.isoformat() if r.replied_at else None,
        'campaign': r.campaign.name if r.campaign_id else '',
    } for r in replies]
    return JsonResponse({'replies': data, 'count': len(data)})


@login_required
@requires_reply_draft_module
@require_http_methods(['GET'])
def list_drafts(request):
    """User's drafts, optionally filtered by status."""
    status = request.GET.get('status')
    qs = ReplyDraft.objects.filter(owner=request.user).select_related('lead', 'original_email')
    if status:
        qs = qs.filter(status=status)
    drafts = qs.order_by('-created_at')[:100]
    data = [{
        'id': d.id,
        'status': d.status,
        'tone': d.tone,
        'to': d.lead.email if d.lead_id else '',
        'subject': d.get_final_subject(),
        'body': d.get_final_body(),
        'original_email_id': d.original_email_id,
        'regen_count': d.regeneration_count,
        'created_at': d.created_at.isoformat(),
        'sent_at': d.sent_at.isoformat() if d.sent_at else None,
    } for d in drafts]
    return JsonResponse({'drafts': data, 'count': len(data)})


@login_required
@requires_reply_draft_module
@require_http_methods(['POST'])
def generate_draft(request):
    payload = _json_body(request)
    original_email_id = payload.get('original_email_id')
    if not original_email_id:
        return JsonResponse({'success': False, 'error': 'original_email_id is required'}, status=400)

    agent = ReplyDraftAgent(user=request.user)
    result = agent.generate_draft(
        original_email_id=original_email_id,
        user_context=payload.get('user_context', ''),
        tone=payload.get('tone', 'professional'),
        email_account_id=payload.get('email_account_id'),
    )
    return JsonResponse(result, status=200 if result.get('success') else 400)


@login_required
@requires_reply_draft_module
@require_http_methods(['POST'])
def regenerate_draft(request, draft_id):
    payload = _json_body(request)
    agent = ReplyDraftAgent(user=request.user)
    result = agent.regenerate_draft(
        draft_id=draft_id,
        new_instructions=payload.get('new_instructions', ''),
        tone=payload.get('tone'),
    )
    return JsonResponse(result, status=200 if result.get('success') else 400)


@login_required
@requires_reply_draft_module
@require_http_methods(['POST'])
def approve_draft(request, draft_id):
    payload = _json_body(request)
    agent = ReplyDraftAgent(user=request.user)
    result = agent.approve_draft(
        draft_id=draft_id,
        edited_subject=payload.get('edited_subject'),
        edited_body=payload.get('edited_body'),
    )
    return JsonResponse(result, status=200 if result.get('success') else 400)


@login_required
@requires_reply_draft_module
@require_http_methods(['POST'])
def send_draft(request, draft_id):
    agent = ReplyDraftAgent(user=request.user)
    result = agent.send_approved(draft_id=draft_id)
    return JsonResponse(result, status=200 if result.get('success') else 400)


@login_required
@requires_reply_draft_module
@require_http_methods(['POST'])
def reject_draft(request, draft_id):
    try:
        draft = ReplyDraft.objects.get(id=draft_id, owner=request.user)
    except ReplyDraft.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Draft not found'}, status=404)
    if draft.status == 'sent':
        return JsonResponse({'success': False, 'error': 'Already sent'}, status=400)
    draft.status = 'rejected'
    draft.save(update_fields=['status', 'updated_at'])
    return JsonResponse({'success': True, 'draft_id': draft.id, 'status': draft.status})

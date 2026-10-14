"""The AI's answer to a lead who writes back "tell me more".

It used to be written and sent within minutes with no person involved: an email
to someone outside the company, in the salesperson's name, listing product
benefits the AI had never been told about. A campaign now has a switch, 'Check
the AI's answers before they are sent' (on for new campaigns). With it on, the
answer is kept here as a draft; the campaign's owner reads it, changes it if
they wish, and sends or discards it.

Opt-outs are not held for anyone: a lead who says stop is stopped at once.
"""
import logging

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def answer_wanting_more(campaign, enrollment, lead, reply_text, *, email_agent, outreach_agent) -> dict:
    """Write the answer; send it, or hold it for a person when the campaign asks for that.

    Returns {'sent': bool, 'held': bool, 'draft_id': int or None}. Raises what
    the send raises when it is sent here, as the callers expect.
    """
    from ai_sdr_agent.models import SDRReplyDraft

    answer = email_agent.generate_more_info_email(lead, campaign, reply_text)
    if not campaign.review_ai_replies:
        outreach_agent.send_email(campaign, lead.email, answer['subject'], answer['body'])
        return {'sent': True, 'held': False, 'draft_id': None}

    draft = SDRReplyDraft.objects.create(
        enrollment=enrollment, lead_reply=(reply_text or '')[:2000],
        subject=(answer.get('subject') or '')[:500], body=answer.get('body') or '')
    try:
        from core.notification_utils import notify_company_users
        notify_company_users(
            [campaign.company_user], title=f'An answer to {lead.display_name} is waiting for you',
            message=(f'{lead.display_name} replied to "{campaign.name}" asking for more. '
                     'The AI has written an answer; read it and send it, or discard it.'),
            link='/ai-sdr/outreach', kind='sdr_reply_to_check')
    except Exception:
        logger.exception('Could not alert the owner of campaign %s about a held answer', campaign.pk)
    logger.info('SDR [MORE-INFO] answer to %s held for review (draft %s)', lead.email, draft.pk)
    return {'sent': False, 'held': True, 'draft_id': draft.pk}


class NotSendable(Exception):
    """Why a held answer cannot be sent, in words for the screen."""


def send_draft(draft, by, *, outreach_agent, subject=None, body=None):
    """Send a held answer, as it stands or as the person changed it.

    Claimed first, so two people pressing Send at once send one email."""
    from ai_sdr_agent.agents.outreach_agent import is_email_suppressed
    from ai_sdr_agent.models import SDRReplyDraft

    enrollment = draft.enrollment
    campaign, lead = enrollment.campaign, enrollment.lead
    subject = (draft.subject if subject is None else subject).strip()
    body = (draft.body if body is None else body).strip()
    if not subject or not body:
        raise NotSendable('The answer needs a subject and some text.')
    if getattr(lead, 'is_deleted', False):
        raise NotSendable('This lead has been deleted.')
    if is_email_suppressed(campaign.company_user, lead.email):
        raise NotSendable('This address is on the do-not-email list, so nothing can be sent to it.')

    claimed = SDRReplyDraft.objects.filter(pk=draft.pk, status='pending').update(
        status='sending', subject=subject[:500], body=body, decided_by=by, decided_at=timezone.now())
    if not claimed:
        raise NotSendable('This answer has already been sent or discarded.')
    try:
        outreach_agent.send_email(campaign, lead.email, subject[:500], body)
    except Exception as exc:
        SDRReplyDraft.objects.filter(pk=draft.pk).update(status='pending', error=str(exc)[:500])
        raise NotSendable(f'The mailbox would not send it: {exc}') from exc
    SDRReplyDraft.objects.filter(pk=draft.pk).update(status='sent', error='')
    draft.refresh_from_db()
    return draft


def discard_draft(draft, by):
    from ai_sdr_agent.models import SDRReplyDraft

    with transaction.atomic():
        changed = SDRReplyDraft.objects.filter(pk=draft.pk, status='pending').update(
            status='discarded', decided_by=by, decided_at=timezone.now())
    if not changed:
        raise NotSendable('This answer has already been sent or discarded.')
    draft.refresh_from_db()
    return draft

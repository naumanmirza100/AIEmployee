"""What a lead's reply does to their place in a campaign.

One copy, used by the five-minute inbox job and both Check Replies buttons. The job had its own copy of the actions
and each button its own loop around them, so every fix had to be made three times.

Since 29 Oct 2026:
- "Not interested" stops this campaign for the lead; only an explicit request to stop puts the address on the
  company's do-not-email list (CO-145).
- A lead with a meeting booked can still opt out by reply, as the meeting emails tell them to (CO-144).
- An out-of-office message pauses only a lead still in the sequence (CO-241).
- One message is acted on once per company, also when the lead is in two campaigns (CO-243).
"""
import logging
from datetime import timedelta

from django.utils import timezone

from ai_sdr_agent.agents.email_assistant_agent import CAT_UNSUBSCRIBE
from ai_sdr_agent.agents.outreach_agent import apply_unsubscribe, claim_reply, mark_bounced
from ai_sdr_agent.models import SDRMeeting

logger = logging.getLogger(__name__)

OPEN_MEETING = ('pending', 'awaiting_approval', 'scheduled')


def handle_inbox_reply(campaign, reply, *, email_agent, outreach_agent=None):
    """Act on one message the inbox check matched to an enrolment. None when nothing was done."""
    enrollment, reply_text = reply['enrollment'], reply['reply_text']
    lead = enrollment.lead

    if reply.get('is_bounce'):
        if enrollment.status != 'bounced' and claim_reply(enrollment, reply):
            mark_bounced(enrollment, f"{reply['sender_email']}: {(reply.get('subject') or '')[:200]}")
            return {'action': 'bounced', 'meeting_created': False, 'category': 'bounced'}
        return None
    if enrollment.status == 'unsubscribed':
        return None

    if enrollment.status == 'replied' and SDRMeeting.objects.filter(enrollment=enrollment).exists():
        # Its emails say "reply with unsubscribe"; such a reply used to be skipped unread (CO-144). Anything else a
        # lead with a meeting writes is left for the salesperson.
        if not claim_reply(enrollment, reply):
            return None
        classification = email_agent.classify_reply(reply_text)
        if classification['category'] != CAT_UNSUBSCRIBE:
            return None
        cancel_open_meetings(enrollment)
        _store_reply(enrollment, reply_text, 'unsubscribe')
        apply_unsubscribe(enrollment)
        return {'action': 'unsubscribed', 'meeting_created': False, 'category': CAT_UNSUBSCRIBE,
                'classification': classification}

    if not claim_reply(enrollment, reply):
        return None
    classification = email_agent.classify_reply(reply_text)
    result = apply_reply_action(campaign.company_user, campaign, enrollment, lead, classification, reply_text,
                                email_agent=email_agent, outreach_agent=outreach_agent)
    result['classification'] = classification
    return result


def cancel_open_meetings(enrollment):
    """A lead who opted out keeps no call."""
    cancel_meetings_of([enrollment])


def cancel_meetings_of(enrollments):
    """Cancel the open calls of these enrolments, row by row so the shared calendar and Google drop them too.
    Finished calls stay as history (CO-148: a deleted campaign left its booked calls alive but hidden)."""
    for meeting in SDRMeeting.objects.filter(enrollment__in=enrollments, status__in=OPEN_MEETING):
        meeting.status = 'cancelled'
        meeting.save(update_fields=['status', 'updated_at'])


def _store_reply(enrollment, reply_text, sentiment, status=None):
    enrollment.replied_at = timezone.now()
    enrollment.reply_content = reply_text[:2000]
    enrollment.reply_sentiment = sentiment
    fields = ['replied_at', 'reply_content', 'reply_sentiment']
    if status:
        enrollment.status = status
        fields.append('status')
    enrollment.save(update_fields=fields)


def _count_reply(campaign, lead):
    lead.status = 'replied'
    lead.save(update_fields=['status'])
    campaign.replies_received = (campaign.replies_received or 0) + 1
    campaign.save(update_fields=['replies_received'])


def apply_reply_action(company_user, campaign, enrollment, lead, classification, reply_text,
                       email_agent=None, outreach_agent=None):
    """
    Apply the action the reader chose.

      pause        → out of office: an active lead waits until the return date
      unsubscribe  → asked to stop: off every campaign of the company
      stop         → not interested: no more emails in this campaign, the lead disqualified
      send_info    → wants more: the AI's answer, sent or held for a person
      book_meeting → interested: a meeting, and the email to pick a time
      wait         → unclear: the follow-ups stop and a person reads it
    """
    from core.api_key_service import KeyServiceError

    action = classification['action']
    category = classification['category']

    if action == 'pause':
        if enrollment.status != 'active':
            # A lead who already answered, or finished the sequence, is not put back into it (CO-241).
            logger.info('SDR [OOO] enrollment=%d is %s: out-of-office message noted, nothing changed',
                        enrollment.id, enrollment.status)
            return {'action': 'wait', 'meeting_created': False, 'category': category}
        resume = classification.get('resume_date') or (timezone.now() + timedelta(days=5))
        if enrollment.next_action_at and enrollment.next_action_at > resume:
            resume = enrollment.next_action_at              # the next step was due later anyway
        enrollment.status = 'paused'
        enrollment.replied_at = timezone.now()
        enrollment.reply_content = reply_text[:2000]
        enrollment.reply_sentiment = 'out_of_office'
        enrollment.next_action_at = resume
        enrollment.save()
        logger.info('SDR [OOO] enrollment=%d paused until %s for lead=%s',
                    enrollment.id, enrollment.next_action_at, lead.display_name)
        return {'action': 'paused', 'meeting_created': False, 'category': category,
                'resume_at': enrollment.next_action_at.isoformat()}

    if action == 'unsubscribe':
        _store_reply(enrollment, reply_text, 'unsubscribe')
        campaign.replies_received = (campaign.replies_received or 0) + 1
        campaign.save(update_fields=['replies_received'])
        apply_unsubscribe(enrollment)
        logger.info('SDR [UNSUBSCRIBE] enrollment=%d: the address is on the do-not-email list', enrollment.id)
        return {'action': 'unsubscribed', 'meeting_created': False, 'category': category}

    if action == 'stop':
        # "Not interested" or "not right now" is not "never email me": other campaigns may still write (CO-145).
        _store_reply(enrollment, reply_text, 'not_interested', status='completed')
        lead.status = 'disqualified'
        lead.save(update_fields=['status'])
        campaign.replies_received = (campaign.replies_received or 0) + 1
        campaign.save(update_fields=['replies_received'])
        logger.info('SDR [NOT-INTERESTED] enrollment=%d stopped, lead=%s disqualified', enrollment.id,
                    lead.display_name)
        return {'action': 'not_interested', 'meeting_created': False, 'category': category}

    if action == 'send_info':
        if enrollment.status != 'replied':
            _store_reply(enrollment, reply_text, 'wants_more_info', status='replied')
        _count_reply(campaign, lead)
        info_sent = held = False
        try:
            from ai_sdr_agent.agents.email_assistant_agent import EmailAssistantAgent
            from ai_sdr_agent.agents.outreach_agent import OutreachAgent
            from ai_sdr_agent.reply_answers import answer_wanting_more
            answered = answer_wanting_more(
                campaign, enrollment, lead, reply_text,
                email_agent=email_agent or EmailAssistantAgent(company=company_user.company),
                outreach_agent=outreach_agent or OutreachAgent(company=company_user.company))
            info_sent, held = answered['sent'], answered['held']
            if info_sent:
                logger.info('SDR [MORE-INFO] sent follow-up to %s', lead.email)
        except KeyServiceError:
            raise
        except Exception as exc:
            logger.warning('SDR [MORE-INFO] email failed for lead=%s: %s', lead.id, exc)
        return {'action': 'answer_waiting' if held else 'sent_more_info', 'meeting_created': False,
                'category': category, 'info_email_sent': info_sent, 'answer_held': held}

    if action == 'book_meeting':
        if enrollment.status != 'replied':
            _store_reply(enrollment, reply_text, 'positive', status='replied')
        _count_reply(campaign, lead)
        # One open call per person: a lead in two campaigns got two meetings and two emails (CO-243).
        if SDRMeeting.objects.filter(company_user__company_id=company_user.company_id,
                                     lead__email__iexact=lead.email, status__in=OPEN_MEETING).exists() \
                and (lead.email or '').strip():
            return {'action': 'meeting_created', 'meeting_created': False, 'category': category}

        from ai_sdr_agent.agents.meeting_scheduling_agent import MeetingSchedulingAgent, guess_timezone_from_location
        meeting, created = SDRMeeting.objects.get_or_create(
            enrollment=enrollment,
            defaults={
                'company_user': company_user,
                'lead': lead,
                'title': f'Discovery Call with {lead.display_name}',
                'reply_snippet': reply_text[:500],
                # The call gets its own room once booked; the campaign's scheduling page is not one (CO-150).
                'status': 'pending',
                'lead_timezone': guess_timezone_from_location(lead.company_location or ''),
            },
        )
        if created:
            campaign.meetings_booked = (campaign.meetings_booked or 0) + 1
            campaign.save(update_fields=['meetings_booked'])
            try:
                sched = MeetingSchedulingAgent(company=company_user.company)
                prep_notes = sched.generate_prep_notes(lead, enrollment, reply_text)
                if sched.send_scheduling_email_once(campaign, lead, meeting, prep_notes):
                    meeting.prep_notes = prep_notes
                    meeting.save(update_fields=['prep_notes'])
            except KeyServiceError:
                raise
            except Exception as exc:
                logger.warning('SDR [MEETING] scheduling email failed lead=%s: %s', lead.id, exc)
        return {'action': 'meeting_created', 'meeting_created': created, 'category': category}

    # Unclear: a real person answered, so the automated follow-ups stop and it is left for someone to read.
    enrollment.reply_content = reply_text[:2000]
    enrollment.reply_sentiment = 'neutral'
    fields = ['reply_content', 'reply_sentiment']
    if enrollment.status == 'active':
        enrollment.status = 'replied'
        enrollment.replied_at = timezone.now()
        fields += ['status', 'replied_at']
    enrollment.save(update_fields=fields)
    return {'action': 'wait', 'meeting_created': False, 'category': category}

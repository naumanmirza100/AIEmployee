"""Telling the salesperson. The agent's only messages went to the lead: nobody heard when a lead booked a call,
accepted a proposed time or replied with interest (CO-199). Each login chooses bell, email or both under the
"Sales calls and interested leads" topic."""
import logging

logger = logging.getLogger(__name__)

MEETINGS = '/ai-sdr/meetings'


def tell_salesperson(company_user, kind, title, message, link=MEETINGS):
    from core.notification_utils import notify_company_users
    try:
        notify_company_users([company_user], title=title, message=message, link=link, kind=kind)
    except Exception:
        logger.exception('Could not tell salesperson %s (%s)', getattr(company_user, 'id', None), kind)


def _when(meeting):
    from ai_sdr_agent.agents.meeting_scheduling_agent import format_datetime_with_timezone
    from core.scheduling import zone_name
    tz = zone_name(meeting.company_user.company.timezone_name) if meeting.company_user_id else 'UTC'
    return format_datetime_with_timezone(meeting.scheduled_at, tz) if meeting.scheduled_at else ''


def call_booked(meeting, accepted=False):
    who = meeting.lead.display_name
    verb = 'accepted the time you proposed' if accepted else 'booked a call'
    tell_salesperson(meeting.company_user, 'sdr_call_booked', f'{who} {verb}',
                     f'{meeting.title or "Discovery call"}, {_when(meeting)}.')


def lead_interested(meeting, reply_text):
    # Only what the lead wrote: the alert quoted the whole Gmail thread after it (live run of 29 Oct).
    from ai_sdr_agent.agents.email_assistant_agent import strip_quoted_reply
    snippet = ' '.join(strip_quoted_reply(reply_text or '').split())[:200]
    tell_salesperson(meeting.company_user, 'sdr_lead_interested',
                     f'{meeting.lead.display_name} is interested',
                     f'They wrote: "{snippet}". They were sent a link to pick a time.')


def ai_answered(campaign, lead):
    tell_salesperson(campaign.company_user, 'sdr_ai_answered', f'The AI answered {lead.display_name}',
                     f'{lead.display_name} asked for more about "{campaign.name}", and the AI sent them an answer.',
                     link='/ai-sdr/outreach')


def call_reminder(meeting):
    tell_salesperson(meeting.company_user, 'sdr_call_reminder', f'Call with {meeting.lead.display_name} soon',
                     f'{meeting.title or "Discovery call"}, {_when(meeting)}.')

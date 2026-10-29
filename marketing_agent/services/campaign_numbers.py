"""A campaign's numbers, worked out once for every screen and every AI answer.

The campaign page, the alert monitor, the Q&A assistant, the graphs and the written reports each counted a campaign
their own way, so they disagreed with the page (CO-136): the monitor divided by failed and pending sends too, and the
others counted Reply Draft's one-off emails. Every reply message counted as a reply and as a conversion, so one lead
in a long exchange looked like many (CO-195). Here:

  * sends are the campaign's own emails (from a template), as on the campaign page;
  * replies, reply rate and conversions count people, not messages;
  * a conversion is a lead who replied with interest or asked for more, not a neutral answer or an objection.
"""
from django.db.models import Count

SENT = ('sent', 'delivered', 'opened', 'clicked')
INTERESTED = ('positive', 'requested_info')


def campaign_sends(campaign):
    """The campaign's own emails: Reply Draft's one-off sends (no template) are not the campaign's."""
    from marketing_agent.models import EmailSendHistory
    return EmailSendHistory.objects.filter(campaign=campaign, email_template__isnull=False)


def _pct(part, whole):
    return round(part / whole * 100, 2) if whole else 0


def numbers(campaign) -> dict:
    from marketing_agent.models import Reply
    sends = campaign_sends(campaign)
    by_status = dict(sends.order_by().values_list('status').annotate(n=Count('id')).values_list('status', 'n'))
    sent = sum(by_status.get(s, 0) for s in SENT)
    opened = by_status.get('opened', 0) + by_status.get('clicked', 0)
    clicked = by_status.get('clicked', 0)
    leads_emailed = sends.filter(status__in=SENT).values('lead_id').distinct().count()

    replies = Reply.objects.filter(campaign=campaign).order_by()
    replied_leads = replies.values('lead_id').distinct().count()
    converted_leads = replies.filter(interest_level__in=INTERESTED).values('lead_id').distinct().count()
    breakdown = dict(replies.values_list('interest_level').annotate(n=Count('id')).values_list('interest_level', 'n'))

    target = campaign.target_conversions
    return {
        'sent': sent,
        'opened': opened,
        'clicked': clicked,
        'failed': by_status.get('failed', 0),
        'bounced': by_status.get('bounced', 0),
        'leads': campaign.leads.count(),
        'leads_emailed': leads_emailed,
        'replied_leads': replied_leads,
        'reply_messages': sum(breakdown.values()),
        'conversions': converted_leads,
        'reply_breakdown': {k or 'not_analyzed': v for k, v in breakdown.items()},
        'open_rate': _pct(opened, sent),
        'click_rate': _pct(clicked, sent),
        'reply_rate': _pct(replied_leads, leads_emailed),
        'conversion_rate': _pct(converted_leads, leads_emailed),
        'conversion_progress': round(converted_leads / target * 100, 1) if target else None,
    }

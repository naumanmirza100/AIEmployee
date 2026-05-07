"""
Sync CampaignPerformance table with live data from EmailSendHistory & Reply.
Uses the same formulas as the frontend dashboard so numbers always match.
"""
from datetime import date

from django.db.models import Q, Count

from marketing_agent.models import (
    Campaign, CampaignPerformance, EmailSendHistory, Reply,
)


def sync_campaign_performance(campaign: Campaign):
    """Update CampaignPerformance rows for a single campaign (today's date).

    Metrics written (matching dashboard formulas):
      impressions      = emails sent (sent/delivered/opened/clicked)
      clicks           = emails clicked
      conversions      = positive replies (positive/neutral/requested_info/objection)
      engagement       = % of leads who opened, clicked, or replied
      open_rate        = (opened / sent) * 100
      click_through_rate = (clicked / opened) * 100
    """
    today = date.today()
    # Exclude reply-draft agent's one-off sends (template_id=None from send_raw_email);
    # they belong to the reply agent, not the marketing campaign's metrics.
    email_sends = EmailSendHistory.objects.filter(
        campaign=campaign, email_template__isnull=False
    )

    total_sent = email_sends.filter(
        status__in=['sent', 'delivered', 'opened', 'clicked']
    ).count()
    total_opened = email_sends.filter(
        status__in=['opened', 'clicked']
    ).count()
    total_clicked = email_sends.filter(status='clicked').count()
    total_replied = Reply.objects.filter(campaign=campaign).count()

    positive_replies = Reply.objects.filter(
        campaign=campaign,
        interest_level__in=['positive', 'neutral', 'requested_info', 'objection'],
    ).count()

    # Leads engagement: % of leads (sent at least one email) who opened/clicked/replied
    leads_sent_to = (
        email_sends.values_list('lead_id', flat=True).distinct().count()
    )
    lead_ids_engaged = set(
        email_sends.filter(status__in=['opened', 'clicked'])
        .values_list('lead_id', flat=True).distinct()
    ) | set(
        Reply.objects.filter(campaign=campaign)
        .values_list('lead_id', flat=True).distinct()
    )
    engagement_rate = (
        round(len(lead_ids_engaged) / leads_sent_to * 100, 2)
        if leads_sent_to > 0 else 0
    )

    open_rate = round((total_opened / total_sent) * 100, 2) if total_sent > 0 else 0
    click_rate = round((total_clicked / total_sent) * 100, 2) if total_sent > 0 else 0
    ctr = round((total_clicked / total_opened) * 100, 2) if total_opened > 0 else 0
    reply_rate = round((total_replied / total_sent) * 100, 2) if total_sent > 0 else 0

    # Target values from campaign
    target_leads = campaign.target_leads
    target_conversions = campaign.target_conversions

    metrics = {
        'impressions': {
            'value': total_sent,
            'target': target_leads,
            'actual': total_sent,
        },
        'clicks': {
            'value': total_clicked,
            'target': None,
            'actual': total_clicked,
        },
        'conversions': {
            'value': positive_replies,
            'target': target_conversions,
            'actual': positive_replies,
        },
        'engagement': {
            'value': engagement_rate,
            'target': None,
            'actual': engagement_rate,
        },
        'open_rate': {
            'value': open_rate,
            'target': None,
            'actual': open_rate,
        },
        'click_through_rate': {
            'value': ctr,
            'target': None,
            'actual': ctr,
        },
    }

    for metric_name, data in metrics.items():
        # date is part of unique_together — must be in lookup, not defaults,
        # otherwise relaunching after rows from a prior day exist raises
        # MultipleObjectsReturned.
        obj, created = CampaignPerformance.objects.update_or_create(
            campaign=campaign,
            metric_name=metric_name,
            channel='all',
            date=today,
            defaults={
                'metric_value': data['value'],
                'target_value': data['target'],
                'actual_value': data['actual'],
            },
        )


def sync_all_campaigns_performance():
    """Sync performance for all active campaigns. Called by Celery beat."""
    campaigns = Campaign.objects.filter(status__in=['active', 'paused'])
    synced = 0
    for campaign in campaigns:
        try:
            sync_campaign_performance(campaign)
            synced += 1
        except Exception as e:
            print(f'[PERF SYNC] Error syncing campaign {campaign.id}: {e}')
    return synced

"""
AI Graph Generator Agent for Marketing Dashboard
Uses LLM to interpret natural language prompts and generate appropriate visualizations
from marketing data (campaigns, email stats, leads, replies).
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from django.db.models import Avg, Count, Q
from django.utils import timezone

from marketing_agent.agents.marketing_base_agent import MarketingBaseAgent
from marketing_agent.models import (
    Campaign,
    CampaignLead,
    CampaignPerformance,
    EmailSendHistory,
    MarketResearch,
    Reply,
)

logger = logging.getLogger(__name__)


class GraphGeneratorAgent(MarketingBaseAgent):
    """
    AI-powered agent that interprets natural language prompts and generates
    appropriate chart configurations based on marketing data.
    """

    def __init__(self, user=None, **kwargs):
        super().__init__(**kwargs)
        self.user = user  # Django User (from company user) for filtering campaigns/leads

    def _normalize_prompt_text(self, prompt: str) -> str:
        """Normalize prompt text and repair common misspellings for intent detection."""
        p = (prompt or '').lower()
        p = p.replace('_', ' ').replace('-', ' ')

        typo_fixes = {
            # campaign
            r'\bcampagin\b': 'campaign', r'\bcampaing\b': 'campaign',
            r'\bcampain\b': 'campaign', r'\bcamapgin\b': 'campaign',
            r'\bcampgain\b': 'campaign', r'\bcamapign\b': 'campaign',
            r'\bcampiagn\b': 'campaign', r'\bcampagne\b': 'campaign',
            r'\bcmapign\b': 'campaign', r'\bcampign\b': 'campaign',
            # status
            r'\bstaus\b': 'status', r'\bstatu\b': 'status',
            r'\bstauts\b': 'status', r'\bstatsu\b': 'status',
            # replies
            r'\breplys\b': 'replies', r'\breplyes\b': 'replies',
            r'\breplis\b': 'replies', r'\breply\b': 'reply',
            r'\brelpy\b': 'reply', r'\brelpies\b': 'replies',
            # lead
            r'\bleed\b': 'lead', r'\bleads\b': 'leads', r'\blead\b': 'lead',
            # email
            r'\bemdail\b': 'email', r'\bemial\b': 'email',
            r'\beamil\b': 'email', r'\bemaul\b': 'email',
            r'\bemali\b': 'email', r'\bemials\b': 'emails',
            # conversion
            r'\bconversoin\b': 'conversion', r'\bconversaion\b': 'conversion',
            r'\bconverion\b': 'conversion', r'\bconversin\b': 'conversion',
            r'\bconverstion\b': 'conversion', r'\bconvesion\b': 'conversion',
            r'\bconvrtion\b': 'conversion', r'\bconverison\b': 'conversion',
            r'\bcnversion\b': 'conversion', r'\bconvrsion\b': 'conversion',
            # rate
            r'\barte\b': 'rate', r'\brtae\b': 'rate', r'\braet\b': 'rate',
            # open
            r'\boen\b': 'open', r'\bopne\b': 'open', r'\boepn\b': 'open',
            # click
            r'\bclcik\b': 'click', r'\bclikc\b': 'click', r'\bclck\b': 'click',
            r'\bclicked\b': 'clicked', r'\bcliked\b': 'clicked',
            # bounce
            r'\bbounec\b': 'bounce', r'\bbouce\b': 'bounce',
            r'\bbouncd\b': 'bounced', r'\bbuonce\b': 'bounce',
            # bar chart
            r'\bbr\b': 'bar', r'\bbra\b': 'bar', r'\bbaar\b': 'bar',
            r'\bbar\b': 'bar', r'\bbahr\b': 'bar', r'\bbarr\b': 'bar',
            r'\bba\b': 'bar', r'\bbars\b': 'bar',
            # line chart
            r'\blie\b': 'line', r'\blien\b': 'line', r'\blinee\b': 'line',
            r'\blinne\b': 'line', r'\bilen\b': 'line', r'\blin\b': 'line',
            r'\blne\b': 'line', r'\blnie\b': 'line', r'\blien\b': 'line',
            # area chart
            r'\bareaa\b': 'area', r'\baria\b': 'area', r'\baera\b': 'area',
            r'\baeara\b': 'area', r'\barea\b': 'area', r'\barae\b': 'area',
            r'\bare\b': 'area',
            # pie chart
            r'\bpiar\b': 'pie', r'\bpei\b': 'pie', r'\bipe\b': 'pie',
            r'\bpie\b': 'pie', r'\bpiee\b': 'pie', r'\bpi\b': 'pie',
            r'\bdougnut\b': 'doughnut', r'\bdounut\b': 'donut',
            r'\bdontu\b': 'donut', r'\bdonut\b': 'donut',
            # chart / graph
            r'\bchar\b': 'chart', r'\bchrat\b': 'chart', r'\bchrt\b': 'chart',
            r'\bcaht\b': 'chart', r'\bchrat\b': 'chart', r'\bcharts\b': 'chart',
            r'\bcahrt\b': 'chart', r'\bcharet\b': 'chart', r'\bchrta\b': 'chart',
            r'\bgraph\b': 'graph', r'\bgrpah\b': 'graph', r'\bgrahp\b': 'graph',
            r'\bgraoh\b': 'graph', r'\bgrph\b': 'graph', r'\bgrapgh\b': 'graph',
            # column / histogram (bar aliases)
            r'\bcolumn\b': 'column', r'\bcolum\b': 'column', r'\bcloumn\b': 'column',
            r'\bhistogram\b': 'histogram', r'\bhistorgram\b': 'histogram',
            # common campaign name typo
            r'\bsumer\b': 'summer', r'\bsumemr\b': 'summer',
            r'\bsummre\b': 'summer', r'\bsumme\b': 'summer',
            # comparison / goals
            r'\bcomparision\b': 'comparison', r'\bcomparison\b': 'comparison',
            r'\bcomaprison\b': 'comparison', r'\bcomparsion\b': 'comparison',
            r'\bcampsrion\b': 'comparison', r'\bcomparisn\b': 'comparison',
            r'\bgoal\b': 'goal', r'\bgoals\b': 'goals',
            r'\btaregt\b': 'target', r'\btaregt\b': 'target',
            r'\btargte\b': 'target', r'\btaget\b': 'target',
            # timeline
            r'\btimline\b': 'timeline', r'\btimelin\b': 'timeline',
            r'\bdaily\b': 'daily', r'\bdailly\b': 'daily',
            r'\btrend\b': 'trend', r'\btrned\b': 'trend',
            # sent
            r'\bsnet\b': 'sent', r'\bsend\b': 'send', r'\bsnt\b': 'sent',
            # overview / general
            r'\boverveiw\b': 'overview', r'\bovreview\b': 'overview',
            r'\boverviwe\b': 'overview', r'\boverview\b': 'overview',
            r'\bsepetrly\b': 'separately', r'\bseperately\b': 'separately',
            r'\bspecfic\b': 'specific', r'\bspceific\b': 'specific',
        }
        for pattern, replacement in typo_fixes.items():
            p = re.sub(pattern, replacement, p)

        p = re.sub(r'[^a-z0-9\s]', ' ', p)
        p = re.sub(r'\s+', ' ', p).strip()
        return p

    def _contains_any(self, text: str, needles: List[str]) -> bool:
        return any(n in text for n in needles)

    def _find_specific_campaign(self, prompt: str, campaigns: list) -> Optional[Dict]:
        """Check if the prompt mentions a specific campaign by name. Returns the campaign dict or None.

        Uses fuzzy matching: strips plurals, ignores minor spelling differences,
        and checks word-overlap so "Summer Sale 261" matches "Summer Sales 261".
        Also uses typo-normalized prompt so "sumer sale" matches "summer sales".
        """
        prompt_lower = (prompt or '').lower().strip()
        # Also try the typo-fixed version of the prompt
        prompt_fixed = self._normalize_prompt_text(prompt)

        def normalize_for_match(text):
            """Lowercase, strip non-alnum, and de-pluralise common suffixes."""
            t = re.sub(r'[^a-z0-9\s]', ' ', text.lower())
            # Remove trailing 's' from each word for fuzzy plural matching
            words = [w.rstrip('s') if len(w) > 3 else w for w in t.split()]
            return ' '.join(words), set(words)

        prompt_norm, prompt_norm_words = normalize_for_match(prompt_lower)
        prompt_fixed_norm, prompt_fixed_norm_words = normalize_for_match(prompt_fixed)

        # Try longest names first to avoid partial matches
        sorted_campaigns = sorted(campaigns, key=lambda c: len(c.get('name', '')), reverse=True)

        # Pass 1: exact substring on raw and typo-fixed prompt
        for c in sorted_campaigns:
            name = (c.get('name') or '').strip()
            if not name:
                continue
            name_low = name.lower()
            if name_low in prompt_lower or name_low in prompt_fixed:
                return c

        # Pass 2: normalized substring (handles "sale" vs "sales")
        for c in sorted_campaigns:
            name = (c.get('name') or '').strip()
            if not name:
                continue
            name_norm, _ = normalize_for_match(name)
            if name_norm in prompt_norm or name_norm in prompt_fixed_norm:
                return c

        # Pass 3: word overlap – all words of campaign name appear in prompt
        for c in sorted_campaigns:
            name = (c.get('name') or '').strip()
            if not name or len(name) < 3:
                continue
            _, name_words = normalize_for_match(name)
            if name_words and (name_words.issubset(prompt_norm_words) or name_words.issubset(prompt_fixed_norm_words)):
                return c

        return None

    def _infer_metric_intent(self, prompt: str) -> str:
        """Infer which metric the user asked to visualize."""
        p = self._normalize_prompt_text(prompt)

        has_campaign = self._contains_any(p, ['campaign', 'campaigns'])
        has_status = self._contains_any(p, ['status', 'state'])
        has_open_or_click = self._contains_any(
            p,
            ['open rate', 'openrate', 'click rate', 'clickrate', 'open', 'click'],
        )
        has_email = self._contains_any(p, ['email', 'emails', 'mail', 'mails'])
        has_volume = self._contains_any(p, ['sent', 'send', 'volume', 'count', 'delivered'])
        has_lead = self._contains_any(p, ['lead', 'leads'])
        has_reply = self._contains_any(
            p,
            ['reply', 'replies', 'respond', 'response', 'responses'],
        )
        has_timeline = self._contains_any(
            p,
            ['over time', 'daily', 'by date', 'by day', 'timeline', 'per day',
             'date wise', 'datewise', 'day by day', 'trend'],
        )
        has_conversion = self._contains_any(
            p,
            ['conversion', 'conversions', 'conversion rate', 'convert'],
        )
        has_bounce = self._contains_any(
            p,
            ['bounce', 'bounced', 'bounce rate', 'bounces'],
        )
        has_click = self._contains_any(
            p,
            ['click rate', 'clickrate', 'click through', 'ctr', 'clicked'],
        )
        has_goal = self._contains_any(
            p,
            ['goal', 'goals', 'target', 'targets', 'vs target', 'comparison',
             'compare', 'actual vs', 'progress', 'achievement'],
        )

        if has_campaign and has_status:
            return 'status'
        if has_goal:
            return 'goals'
        if has_conversion:
            return 'conversions'
        if has_bounce:
            return 'bounces'
        if has_click:
            return 'clicks'
        if has_open_or_click:
            return 'open_rate'
        if has_email and (has_volume or has_campaign):
            return 'emails_sent'
        if has_lead and has_timeline:
            return 'leads_timeline'
        if has_lead:
            return 'leads'
        if has_reply and has_timeline:
            return 'replies_timeline'
        if has_reply:
            return 'replies'
        if has_conversion and has_timeline:
            return 'conversions_timeline'
        return 'default'

    def _fetch_marketing_data(self) -> Dict[str, Any]:
        """Fetch all relevant marketing data for the current user (campaigns, email stats, replies)."""
        user_id = self.user.id if self.user else None
        campaigns_query = Campaign.objects.all()
        if user_id:
            campaigns_query = campaigns_query.filter(owner_id=user_id)

        campaigns = list(
            campaigns_query.select_related('owner').prefetch_related('performance_metrics')
        )
        campaign_ids = [c.id for c in campaigns]

        email_stats = {}
        if campaign_ids:
            sent_statuses = ['sent', 'delivered', 'opened', 'clicked']
            for row in (
                EmailSendHistory.objects.filter(campaign_id__in=campaign_ids)
                .values('campaign_id')
                .annotate(
                    total_sent=Count('id', filter=Q(status__in=sent_statuses)),
                    total_opened=Count('id', filter=Q(status__in=['opened', 'clicked'])),
                    total_clicked=Count('id', filter=Q(status='clicked')),
                    total_bounced=Count('id', filter=Q(status='bounced')),
                    total_failed=Count('id', filter=Q(status='failed')),
                )
                .order_by('campaign_id')
            ):
                email_stats[row['campaign_id']] = row

        reply_stats = {}
        if campaign_ids:
            for row in (
                Reply.objects.filter(campaign_id__in=campaign_ids)
                .values('campaign_id')
                .annotate(
                    total_replied=Count('id'),
                    positive_replies=Count(
                        'id',
                        filter=Q(
                            interest_level__in=[
                                'positive',
                                'neutral',
                                'requested_info',
                                'objection',
                            ]
                        ),
                    ),
                    negative_replies=Count(
                        'id',
                        filter=Q(
                            interest_level__in=['negative', 'unsubscribe']
                        ),
                    ),
                )
                .order_by('campaign_id')
            ):
                reply_stats[row['campaign_id']] = row

        lead_counts = {}
        if campaign_ids:
            for row in CampaignLead.objects.filter(
                campaign_id__in=campaign_ids
            ).values('campaign_id').annotate(count=Count('id')).order_by('campaign_id'):
                lead_counts[row['campaign_id']] = row['count']

        campaigns_data = []
        for campaign in campaigns:
            cid = campaign.id
            es = email_stats.get(cid, {})
            rs = reply_stats.get(cid, {})
            total_sent = es.get('total_sent') or 0
            total_opened = es.get('total_opened') or 0
            total_clicked = es.get('total_clicked') or 0
            total_bounced = es.get('total_bounced') or 0
            total_failed = es.get('total_failed') or 0
            total_replied = rs.get('total_replied') or 0
            positive_replies = rs.get('positive_replies') or 0
            negative_replies = rs.get('negative_replies') or 0
            leads_count = lead_counts.get(cid, 0)

            target_leads = getattr(campaign, 'target_leads', None)
            target_conversions = getattr(campaign, 'target_conversions', None)
            conversion_progress = (
                round((positive_replies / target_conversions * 100), 1)
                if target_conversions and target_conversions > 0
                else None
            )
            leads_progress = (
                round((leads_count / target_leads * 100), 1)
                if target_leads and target_leads > 0
                else None
            )
            open_rate = (
                round((total_opened / total_sent) * 100, 2) if total_sent > 0 else None
            )
            click_rate = (
                round((total_clicked / total_sent) * 100, 2) if total_sent > 0 else None
            )
            reply_rate = (
                round((total_replied / total_sent) * 100, 2) if total_sent > 0 else None
            )
            bounce_rate = (
                round((total_bounced / total_sent) * 100, 2) if total_sent > 0 else None
            )

            metrics_prefetched = list(campaign.performance_metrics.all())[:20]
            camp_dict = {
                'id': campaign.id,
                'name': campaign.name,
                'type': campaign.campaign_type,
                'status': campaign.status,
                'start_date': (
                    campaign.start_date.isoformat() if campaign.start_date else None
                ),
                'end_date': (
                    campaign.end_date.isoformat() if campaign.end_date else None
                ),
                'metrics': [
                    {
                        'name': m.metric_name,
                        'value': float(m.metric_value),
                        'date': m.date.isoformat(),
                        'channel': m.channel,
                    }
                    for m in metrics_prefetched
                ],
                'goals': campaign.goals,
                'channels': campaign.channels,
                'target_leads': target_leads,
                'target_conversions': target_conversions,
                'leads_count': leads_count,
                'positive_replies': positive_replies,
                'negative_replies': negative_replies,
                'conversions': positive_replies,
                'conversion_progress': conversion_progress,
                'leads_progress': leads_progress,
                'emails_sent': total_sent,
                'emails_opened': total_opened,
                'emails_clicked': total_clicked,
                'emails_replied': total_replied,
                'emails_bounced': total_bounced,
                'emails_failed': total_failed,
                'open_rate': open_rate,
                'click_rate': click_rate,
                'reply_rate': reply_rate,
                'bounce_rate': bounce_rate,
            }
            campaigns_data.append(camp_dict)

        research_query = MarketResearch.objects.all()
        if user_id:
            research_query = research_query.filter(created_by_id=user_id)
        research_data = [
            {
                'id': r.id,
                'type': r.research_type,
                'topic': r.topic,
                'insights': r.insights,
                'findings': r.findings,
                'created_at': r.created_at.isoformat(),
            }
            for r in research_query[:10]
        ]

        active_campaigns = campaigns_query.filter(status='active').count()
        all_metrics = (
            CampaignPerformance.objects.filter(campaign__in=campaigns_query)
            .values('metric_name')
            .annotate(avg_value=Avg('metric_value'), total_count=Count('id'))
            .order_by('metric_name')
        )

        # Aggregates for charts: by status, by campaign name (for bar/pie)
        by_status = {}
        for c in campaigns_data:
            s = c.get('status') or 'draft'
            by_status[s] = by_status.get(s, 0) + 1

        by_campaign_emails = {c['name']: c['emails_sent'] for c in campaigns_data}
        by_campaign_open_rate = {}
        for c in campaigns_data:
            if c.get('open_rate') is not None:
                by_campaign_open_rate[c['name']] = c['open_rate']
        by_campaign_leads = {c['name']: c['leads_count'] for c in campaigns_data}
        by_campaign_replies = {c['name']: c['emails_replied'] for c in campaigns_data}

        return {
            'campaigns': campaigns_data,
            'research': research_data,
            'stats': {
                'total_campaigns': len(campaigns_data),
                'active_campaigns': active_campaigns,
                'performance_metrics': list(all_metrics),
            },
            'by_status': by_status,
            'by_campaign_emails_sent': by_campaign_emails,
            'by_campaign_open_rate': by_campaign_open_rate,
            'by_campaign_leads': by_campaign_leads,
            'by_campaign_replies': by_campaign_replies,
        }

    def _build_single_campaign_chart(
        self, campaign: Dict, prompt: str, chart_type: str
    ) -> Optional[Dict[str, Any]]:
        """Build a day-by-day timeline chart for a single campaign.

        Queries EmailSendHistory to compute daily counts (sent, opened,
        clicked, replied) then picks the metric the user asked about and
        plots it over time using real dates on the x-axis.
        """
        from django.db.models.functions import TruncDate

        metric_intent = self._infer_metric_intent(prompt)
        campaign_id = campaign.get('id')
        name = campaign.get('name', 'Campaign')
        start_date = campaign.get('start_date')
        end_date = campaign.get('end_date')
        date_info = f' ({start_date} to {end_date})' if start_date and end_date else ''

        print(f"[Graph] _build_single_campaign_chart: name='{name}', id={campaign_id}, intent={metric_intent}")

        if not campaign_id:
            logger.warning("[Graph] No campaign_id found")
            return None

        # ── Query daily email stats from EmailSendHistory ──
        sent_statuses = ['sent', 'delivered', 'opened', 'clicked']
        qs = EmailSendHistory.objects.filter(
            campaign_id=campaign_id,
            sent_at__isnull=False,
        )
        print(f"[Graph] EmailSendHistory count for campaign {campaign_id}: {qs.count()}")

        daily_sent = dict(
            qs.filter(status__in=sent_statuses)
            .annotate(day=TruncDate('sent_at'))
            .values('day')
            .annotate(count=Count('id'))
            .order_by('day')
            .values_list('day', 'count')
        )
        daily_opened = dict(
            qs.filter(opened_at__isnull=False)
            .annotate(day=TruncDate('opened_at'))
            .values('day')
            .annotate(count=Count('id'))
            .order_by('day')
            .values_list('day', 'count')
        )
        daily_clicked = dict(
            qs.filter(clicked_at__isnull=False)
            .annotate(day=TruncDate('clicked_at'))
            .values('day')
            .annotate(count=Count('id'))
            .order_by('day')
            .values_list('day', 'count')
        )

        daily_bounced = dict(
            qs.filter(status='bounced', sent_at__isnull=False)
            .annotate(day=TruncDate('sent_at'))
            .values('day')
            .annotate(count=Count('id'))
            .order_by('day')
            .values_list('day', 'count')
        )

        # Replies via Reply model (linked to campaign)
        daily_replied = dict(
            Reply.objects.filter(campaign_id=campaign_id, replied_at__isnull=False)
            .annotate(day=TruncDate('replied_at'))
            .values('day')
            .annotate(count=Count('id'))
            .order_by('day')
            .values_list('day', 'count')
        )

        # Conversions = positive replies
        daily_conversions = dict(
            Reply.objects.filter(
                campaign_id=campaign_id,
                replied_at__isnull=False,
                interest_level='positive',
            )
            .annotate(day=TruncDate('replied_at'))
            .values('day')
            .annotate(count=Count('id'))
            .order_by('day')
            .values_list('day', 'count')
        )

        # Build the full date range from campaign start_date to end_date (or today)
        # so that days with no activity show as 0 instead of being skipped
        from datetime import date as date_type, timedelta
        activity_dates = sorted(
            set(daily_sent.keys()) | set(daily_opened.keys())
            | set(daily_clicked.keys()) | set(daily_replied.keys())
            | set(daily_bounced.keys()) | set(daily_conversions.keys())
        )
        print(f"[Graph] Daily data: sent={len(daily_sent)} days, opened={len(daily_opened)} days, clicked={len(daily_clicked)} days, replied={len(daily_replied)} days, activity_dates={len(activity_dates)}")

        if not activity_dates:
            # No email activity at all – fall back to CampaignPerformance metrics
            metrics = campaign.get('metrics', [])
            if metrics:
                timeline = [
                    {'label': m.get('date', ''), 'value': m.get('value', 0)}
                    for m in metrics
                ]
                timeline.sort(key=lambda x: x.get('label', ''))
                if len(timeline) >= 2:
                    return {
                        'type': chart_type,
                        'title': f'{name} – Performance Over Time',
                        'data': timeline,
                        'color': '#3b82f6',
                        'colors': ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'],
                        'insights': f'Performance metrics for {name}.{date_info}',
                    }
            return None

        # Date range based only on actual activity dates (first → last activity day)
        range_start = activity_dates[0]
        range_end = activity_dates[-1]

        # If only 1 day of data, pad 1 day before and after for a proper line
        if range_start == range_end:
            range_start = range_start - timedelta(days=1)
            range_end = range_end + timedelta(days=1)

        # Generate every day in the range
        all_dates = []
        current = range_start
        while current <= range_end:
            all_dates.append(current)
            current += timedelta(days=1)

        if not all_dates:
            all_dates = activity_dates

        # ── Pick which daily series to show based on intent ──
        intent_config = {
            'open_rate': {
                'title': f'{name} – Opens Over Time',
                'get_value': lambda d: daily_opened.get(d, 0),
                'insights': f'Daily email opens for {name}.{date_info} Overall open rate: {campaign.get("open_rate", "N/A")}%.',
            },
            'emails_sent': {
                'title': f'{name} – Emails Sent Over Time',
                'get_value': lambda d: daily_sent.get(d, 0),
                'insights': f'Daily emails sent for {name}.{date_info} Total: {campaign.get("emails_sent", 0)}.',
            },
            'replies': {
                'title': f'{name} – Reply Breakdown',
                'static': True,
            },
            'leads': {
                'title': f'{name} – Lead Target Progress',
                'static': True,
            },
            'conversions': {
                'title': f'{name} – Conversion Progress',
                'static': True,  # not a timeline – use static data
            },
            'bounces': {
                'title': f'{name} – Bounces Over Time',
                'get_value': lambda d: daily_bounced.get(d, 0),
                'insights': f'Daily bounced emails for {name}.{date_info} Total: {campaign.get("emails_bounced", 0)}.',
            },
            'clicks': {
                'title': f'{name} – Clicks Over Time',
                'get_value': lambda d: daily_clicked.get(d, 0),
                'insights': f'Daily email clicks for {name}.{date_info} Click rate: {campaign.get("click_rate", "N/A")}%.',
            },
            'replies_timeline': {
                'title': f'{name} – Replies Over Time',
                'get_value': lambda d: daily_replied.get(d, 0),
                'insights': f'Daily replies for {name}.{date_info} Total: {campaign.get("emails_replied", 0)}.',
            },
            'leads_timeline': {
                'title': f'{name} – Leads Activity Over Time',
                'get_value': lambda d: daily_sent.get(d, 0),
                'insights': f'Daily email activity for {name}.{date_info} Leads: {campaign.get("leads_count", 0)}.',
            },
            'conversions_timeline': {
                'title': f'{name} – Conversions Over Time',
                'get_value': lambda d: daily_conversions.get(d, 0),
                'insights': f'Daily conversions (positive replies) for {name}.{date_info} Total: {campaign.get("conversions", 0)}.',
            },
            'goals': {
                'title': f'{name} – Actual vs Target',
                'static': True,
            },
            'default': {
                'title': f'{name} – Campaign Overview',
                'static': True,
            },
        }

        config = intent_config.get(metric_intent, intent_config['default'])

        # ── Static (non-timeline) charts: conversions, replies breakdown, leads ──
        if config.get('static'):
            return self._build_static_campaign_chart(
                campaign, metric_intent, chart_type, name, date_info
            )

        # ── Timeline charts ──
        chart_data = []
        for d in all_dates:
            chart_data.append({
                'label': d.isoformat(),
                'value': config['get_value'](d),
            })

        if not chart_data:
            return None

        return {
            'type': chart_type,
            'title': config['title'],
            'data': chart_data,
            'color': '#3b82f6',
            'colors': ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'],
            'insights': config['insights'],
        }

    def _build_static_campaign_chart(
        self, campaign: Dict, metric_intent: str, chart_type: str,
        name: str, date_info: str,
    ) -> Optional[Dict[str, Any]]:
        """Build non-timeline charts: conversion progress, reply breakdown, lead target."""
        campaign_id = campaign.get('id')

        if metric_intent == 'conversions':
            target = campaign.get('target_conversions') or 0
            achieved = campaign.get('positive_replies', 0) or 0
            progress = campaign.get('conversion_progress')
            remaining = max(0, target - achieved)

            chart_data = [
                {'label': 'Conversions (Positive Replies)', 'value': achieved},
            ]
            if target > 0:
                chart_data.append({'label': 'Remaining to Target', 'value': remaining})

            progress_str = f'{progress}%' if progress is not None else 'N/A'
            return {
                'type': 'bar',  # bar makes more sense for progress
                'title': f'{name} – Conversion Progress',
                'data': chart_data if chart_type in ('bar', 'pie') else chart_data,
                'color': '#10b981',
                'colors': ['#10b981', '#374151'],
                'insights': f'Conversions: {achieved}/{target} ({progress_str}).{date_info}',
            }

        if metric_intent == 'leads':
            target = campaign.get('target_leads') or 0
            uploaded = campaign.get('leads_count', 0) or 0
            clicked = campaign.get('emails_clicked', 0) or 0
            positive = campaign.get('positive_replies', 0) or 0
            progress = campaign.get('leads_progress')

            chart_data = [
                {'label': 'Leads Uploaded', 'value': uploaded},
                {'label': 'Clicked', 'value': clicked},
                {'label': 'Positive Replies', 'value': positive},
            ]
            if target > 0:
                chart_data.append({'label': 'Target', 'value': target})

            progress_str = f'{progress}%' if progress is not None else 'N/A'
            return {
                'type': 'bar',
                'title': f'{name} – Lead Target Progress',
                'data': chart_data,
                'color': '#3b82f6',
                'colors': ['#3b82f6', '#f59e0b', '#10b981', '#6b7280'],
                'insights': f'Leads: {uploaded}, Target: {target} ({progress_str} complete).{date_info}',
            }

        if metric_intent == 'replies':
            # Query actual reply breakdown by interest_level
            reply_breakdown = {}
            if campaign_id:
                from django.db.models.functions import TruncDate
                qs = Reply.objects.filter(campaign_id=campaign_id)
                for row in qs.values('interest_level').annotate(count=Count('id')).order_by('-count'):
                    level = row['interest_level'] or 'not_analyzed'
                    reply_breakdown[level] = row['count']

            label_map = {
                'positive': 'Positive / Interested',
                'negative': 'Negative / Not Interested',
                'neutral': 'Neutral',
                'requested_info': 'Requested Info',
                'objection': 'Objection',
                'unsubscribe': 'Unsubscribe',
                'not_analyzed': 'Not Analyzed',
            }
            color_map = {
                'positive': '#10b981',
                'negative': '#ef4444',
                'neutral': '#f59e0b',
                'requested_info': '#3b82f6',
                'objection': '#f97316',
                'unsubscribe': '#6b7280',
                'not_analyzed': '#9ca3af',
            }

            # Build chart data in a consistent order
            display_order = ['positive', 'neutral', 'negative', 'requested_info', 'objection', 'unsubscribe', 'not_analyzed']
            chart_data = []
            colors = []
            for level in display_order:
                count = reply_breakdown.get(level, 0)
                if count > 0:
                    chart_data.append({
                        'label': label_map.get(level, level),
                        'value': count,
                    })
                    colors.append(color_map.get(level, '#6b7280'))

            if not chart_data:
                return None

            total = sum(p['value'] for p in chart_data)
            positive_count = reply_breakdown.get('positive', 0)
            negative_count = reply_breakdown.get('negative', 0)
            neutral_count = reply_breakdown.get('neutral', 0) + reply_breakdown.get('requested_info', 0)

            return {
                'type': 'bar',  # bar shows breakdown better than line
                'title': f'{name} – Reply Breakdown',
                'data': chart_data,
                'color': '#3b82f6',
                'colors': colors,
                'insights': f'Total replies: {total}. Positive: {positive_count}, Neutral: {neutral_count}, Negative: {negative_count}.{date_info}',
            }

        if metric_intent == 'goals':
            # Actual vs Target comparison
            target_conversions = campaign.get('target_conversions') or 0
            target_leads = campaign.get('target_leads') or 0
            actual_conversions = campaign.get('positive_replies', 0) or 0
            actual_leads = campaign.get('leads_count', 0) or 0
            sent = campaign.get('emails_sent', 0) or 0
            opened = campaign.get('emails_opened', 0) or 0
            clicked = campaign.get('emails_clicked', 0) or 0
            replied = campaign.get('emails_replied', 0) or 0

            # Build paired actual/target data points
            chart_data = []
            colors = []
            insights_parts = []

            if target_conversions > 0 or actual_conversions > 0:
                chart_data.append({'label': 'Conversions (Actual)', 'value': actual_conversions})
                colors.append('#10b981')
                chart_data.append({'label': 'Conversions (Target)', 'value': target_conversions})
                colors.append('#10b981')
                pct = round((actual_conversions / target_conversions) * 100, 1) if target_conversions > 0 else 0
                insights_parts.append(f'Conversions: {actual_conversions}/{target_conversions} ({pct}%)')

            if target_leads > 0 or actual_leads > 0:
                chart_data.append({'label': 'Leads (Actual)', 'value': actual_leads})
                colors.append('#3b82f6')
                chart_data.append({'label': 'Leads (Target)', 'value': target_leads})
                colors.append('#3b82f6')
                pct = round((actual_leads / target_leads) * 100, 1) if target_leads > 0 else 0
                insights_parts.append(f'Leads: {actual_leads}/{target_leads} ({pct}%)')

            # Also show email funnel actuals
            if sent > 0:
                chart_data.append({'label': 'Emails Sent', 'value': sent})
                colors.append('#8b5cf6')
            if opened > 0:
                chart_data.append({'label': 'Opened', 'value': opened})
                colors.append('#f59e0b')
            if clicked > 0:
                chart_data.append({'label': 'Clicked', 'value': clicked})
                colors.append('#f97316')
            if replied > 0:
                chart_data.append({'label': 'Replied', 'value': replied})
                colors.append('#06b6d4')

            if not chart_data:
                return None

            return {
                'type': 'bar',
                'title': f'{name} – Actual vs Target',
                'data': chart_data,
                'color': '#3b82f6',
                'colors': colors,
                'insights': ' | '.join(insights_parts) + f'.{date_info}' if insights_parts else f'Campaign stats for {name}.{date_info}',
            }

        if metric_intent == 'default':
            # Full campaign overview – show all key stats
            chart_data = []
            sent = campaign.get('emails_sent', 0) or 0
            conv_rate = campaign.get('conversion_progress') or 0

            overview_fields = [
                ('Leads', campaign.get('leads_count', 0) or 0, '#3b82f6'),
                ('Emails Sent', sent, '#8b5cf6'),
                ('Opened', campaign.get('emails_opened', 0) or 0, '#10b981'),
                ('Clicked', campaign.get('emails_clicked', 0) or 0, '#f59e0b'),
                ('Replied', campaign.get('emails_replied', 0) or 0, '#06b6d4'),
                ('Conversion Rate %', conv_rate, '#10b981'),
            ]
            colors = []
            for label, value, color in overview_fields:
                if value > 0:
                    chart_data.append({'label': label, 'value': value})
                    colors.append(color)

            if not chart_data:
                return None

            # Build insights with rates
            open_rate = campaign.get('open_rate')
            click_rate = campaign.get('click_rate')
            reply_rate = campaign.get('reply_rate')
            bounce_rate = campaign.get('bounce_rate')
            conv_progress = campaign.get('conversion_progress')
            parts = [f'Status: {campaign.get("status", "N/A")}']
            if open_rate is not None:
                parts.append(f'Open rate: {open_rate}%')
            if click_rate is not None:
                parts.append(f'Click rate: {click_rate}%')
            if reply_rate is not None:
                parts.append(f'Reply rate: {reply_rate}%')
            if bounce_rate is not None:
                parts.append(f'Bounce rate: {bounce_rate}%')
            if conv_progress is not None:
                target = campaign.get('target_conversions', 0) or 0
                achieved = campaign.get('positive_replies', 0) or 0
                parts.append(f'Conversions: {achieved}/{target} ({conv_progress}%)')

            return {
                'type': 'bar',
                'title': f'{name} – Campaign Overview',
                'data': chart_data,
                'color': '#3b82f6',
                'colors': colors,
                'insights': ' | '.join(parts) + f'.{date_info}',
            }

        return None

    def generate_graph(self, prompt: str) -> Dict[str, Any]:
        """
        Generate a graph configuration based on natural language prompt.
        Uses AI to interpret the prompt and select appropriate data/chart type.
        """
        marketing_data = self._fetch_marketing_data()

        # Check if user is asking about a specific campaign
        specific_campaign = self._find_specific_campaign(
            prompt, marketing_data.get('campaigns', [])
        )

        campaigns_summary = [
            {
                'name': c['name'],
                'status': c['status'],
                'start_date': c.get('start_date'),
                'end_date': c.get('end_date'),
                'emails_sent': c['emails_sent'],
                'open_rate': c.get('open_rate'),
                'leads_count': c['leads_count'],
                'emails_replied': c['emails_replied'],
            }
            for c in marketing_data['campaigns'][:15]
        ]
        campaigns_summary_json = json.dumps(campaigns_summary, separators=(',', ':'))

        # If specific campaign, give the LLM only that campaign's data
        if specific_campaign:
            single_data = json.dumps({
                'name': specific_campaign['name'],
                'status': specific_campaign.get('status'),
                'start_date': specific_campaign.get('start_date'),
                'end_date': specific_campaign.get('end_date'),
                'emails_sent': specific_campaign.get('emails_sent', 0),
                'emails_opened': specific_campaign.get('emails_opened', 0),
                'emails_clicked': specific_campaign.get('emails_clicked', 0),
                'emails_replied': specific_campaign.get('emails_replied', 0),
                'open_rate': specific_campaign.get('open_rate'),
                'click_rate': specific_campaign.get('click_rate'),
                'reply_rate': specific_campaign.get('reply_rate'),
                'leads_count': specific_campaign.get('leads_count', 0),
                'metrics': specific_campaign.get('metrics', []),
            }, separators=(',', ':'))

            data_summary = f"""
SPECIFIC CAMPAIGN DATA (user is asking about THIS campaign only):
{single_data}
"""
            system_prompt = f"""Generate chart JSON for a SINGLE campaign. Respond with ONLY valid JSON, no markdown.
{data_summary}
The user wants to see data for "{specific_campaign['name']}" ONLY. Do NOT include other campaigns.
For line/area charts, if the campaign has timeline metrics, use them as data points with dates as labels. If no timeline metrics, show the campaign's key stats (emails sent, opened, replied, leads) as data points.
Include start_date and end_date in each data point if available.
Format: {{"chart_type":"bar"|"pie"|"line"|"area","title":"...","data":[{{"label":"x","value":y,"start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}}],"insights":"1-2 sentences","colors":["#3b82f6","#10b981","#f59e0b","#ef4444","#8b5cf6"]}}
Rules: Use actual data values. Only show data for this specific campaign."""
        else:
            data_summary = f"""
CAMPAIGNS: {marketing_data['stats']['total_campaigns']} total, {marketing_data['stats']['active_campaigns']} active
By status: {json.dumps(marketing_data['by_status'], separators=(',', ':'))}
Per-campaign: {campaigns_summary_json}
Emails sent: {json.dumps(marketing_data['by_campaign_emails_sent'], separators=(',', ':'))}
Open rate%: {json.dumps(marketing_data['by_campaign_open_rate'], separators=(',', ':'))}
Leads: {json.dumps(marketing_data['by_campaign_leads'], separators=(',', ':'))}
Replies: {json.dumps(marketing_data['by_campaign_replies'], separators=(',', ':'))}
"""
            system_prompt = f"""Generate chart JSON from marketing data. Respond with ONLY valid JSON, no markdown.
{data_summary}
Format: {{"chart_type":"bar"|"pie"|"line"|"area","title":"...","data":{{"label":value}} for bar/pie OR [{{"label":"x","value":y,"start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}}] for line/area,"insights":"1-2 sentences","colors":["#3b82f6","#10b981","#f59e0b","#ef4444","#8b5cf6"]}}
Rules: Use actual data values. Only include non-zero values. Sort bar data by value descending. Choose best chart type for the request. For "top N", take N highest. For line/area charts where data points are campaigns, include start_date and end_date fields from the campaign data in each data point."""

        try:
            user_message = f"Generate a chart for: {prompt}"
            response_text = self._call_llm(
                user_message,
                system_prompt=system_prompt,
                temperature=0,
                max_tokens=2000,
            )
            if not response_text or not response_text.strip():
                raise ValueError("Empty LLM response")
            logger.info(f"Graph LLM response length: {len(response_text)}")

            if response_text.strip().startswith('```'):
                lines = response_text.split('\n')
                end_idx = -1
                for i, line in enumerate(lines):
                    if i > 0 and line.strip() == '```':
                        end_idx = i
                        break
                if end_idx > 0:
                    response_text = '\n'.join(lines[1:end_idx])
                else:
                    response_text = '\n'.join(lines[1:])
            if response_text.strip().lower().startswith('json'):
                response_text = response_text.strip()[4:].strip()

            chart_config = json.loads(response_text)

            # Respect explicit user chart requests like "line chart" even if LLM returns aliases.
            requested_chart_type = self._get_requested_chart_type(prompt)
            chart_config['chart_type'] = self._normalize_chart_type(
                chart_config.get('chart_type'),
                requested_chart_type=requested_chart_type,
            )
            if 'title' not in chart_config:
                chart_config['title'] = 'Generated Chart'
            if 'data' not in chart_config:
                chart_config['data'] = {}
            chart_config['data'] = self._coerce_chart_data_for_type(
                chart_config.get('data'),
                chart_config['chart_type'],
            )

            # For specific campaign requests, build deterministic single-campaign data
            if specific_campaign:
                print(f"[Graph] Specific campaign detected: '{specific_campaign.get('name')}' (id={specific_campaign.get('id')})")
                single_chart = self._build_single_campaign_chart(
                    specific_campaign, prompt, chart_config['chart_type']
                )
                if single_chart:
                    print(f"[Graph] Using single-campaign chart data: {len(single_chart.get('data', []))} points")
                    chart_config['data'] = single_chart['data']
                    chart_config['title'] = single_chart.get('title', chart_config['title'])
                    chart_config['insights'] = single_chart.get('insights', chart_config.get('insights', ''))
                else:
                    # No email activity found – still restrict to this campaign only
                    # Build a simple summary from aggregate data, never show other campaigns
                    print(f"[Graph] No timeline data for '{specific_campaign.get('name')}', building aggregate-only chart")
                    name = specific_campaign.get('name', 'Campaign')
                    sd = specific_campaign.get('start_date')
                    ed = specific_campaign.get('end_date')
                    agg_points = [
                        ('Emails Sent', specific_campaign.get('emails_sent', 0) or 0),
                        ('Opened', specific_campaign.get('emails_opened', 0) or 0),
                        ('Clicked', specific_campaign.get('emails_clicked', 0) or 0),
                        ('Replied', specific_campaign.get('emails_replied', 0) or 0),
                        ('Leads', specific_campaign.get('leads_count', 0) or 0),
                    ]
                    chart_config['data'] = [
                        {'label': lbl, 'value': val} for lbl, val in agg_points if val > 0
                    ] or [{'label': name, 'value': 0}]
                    chart_config['title'] = f'{name} – Overview'
                    di = f' ({sd} to {ed})' if sd and ed else ''
                    chart_config['insights'] = f'Aggregate stats for {name}.{di}'
            else:
                # For multi-campaign requests, enforce deterministic data slices
                enforced = self._generate_fallback_chart(
                    prompt,
                    marketing_data,
                    forced_intent=self._infer_metric_intent(prompt),
                    forced_chart_type=chart_config['chart_type'],
                )
                if enforced and enforced.get('chart'):
                    chart_config['data'] = enforced['chart'].get('data', chart_config['data'])
                    if not chart_config.get('title'):
                        chart_config['title'] = enforced['chart'].get('title', 'Generated Chart')

            if 'colors' not in chart_config:
                chart_config['colors'] = [
                    '#3b82f6',
                    '#10b981',
                    '#f59e0b',
                    '#ef4444',
                    '#8b5cf6',
                    '#ec4899',
                ]

            return {
                'chart': {
                    'type': chart_config['chart_type'],
                    'title': chart_config['title'],
                    'data': chart_config['data'],
                    'colors': chart_config.get(
                        'colors',
                        [
                            '#3b82f6',
                            '#10b981',
                            '#f59e0b',
                            '#ef4444',
                        ],
                    ),
                    'color': (chart_config.get('colors') or ['#3b82f6'])[0],
                },
                'insights': chart_config.get('insights', ''),
            }
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse graph LLM response as JSON: {e}")
            if specific_campaign:
                return self._single_campaign_fallback(specific_campaign, prompt)
            return self._generate_fallback_chart(prompt, marketing_data)
        except Exception as e:
            logger.exception(f"Error generating marketing graph: {e}")
            if specific_campaign:
                return self._single_campaign_fallback(specific_campaign, prompt)
            return self._generate_fallback_chart(prompt, marketing_data)

    def _single_campaign_fallback(self, campaign: Dict, prompt: str) -> Dict:
        """Fallback for a single campaign – never returns other campaigns' data."""
        chart_type = self._get_requested_chart_type(prompt) or 'line'
        single = self._build_single_campaign_chart(campaign, prompt, chart_type)
        if single:
            return {'chart': single, 'insights': single.get('insights', '')}
        # Absolute last resort – aggregate stats only for THIS campaign
        name = campaign.get('name', 'Campaign')
        return {
            'chart': {
                'type': chart_type,
                'title': f'{name} – Overview',
                'data': [
                    {'label': 'Sent', 'value': campaign.get('emails_sent', 0) or 0},
                    {'label': 'Opened', 'value': campaign.get('emails_opened', 0) or 0},
                    {'label': 'Replied', 'value': campaign.get('emails_replied', 0) or 0},
                    {'label': 'Leads', 'value': campaign.get('leads_count', 0) or 0},
                ],
                'color': '#3b82f6',
                'colors': ['#3b82f6', '#10b981', '#f59e0b', '#ef4444'],
            },
            'insights': f'Aggregate stats for {name}.',
        }

    def _get_requested_chart_type(self, prompt: str) -> Optional[str]:
        """Extract explicit chart type from prompt, including common misspellings."""
        p = self._normalize_prompt_text(prompt)

        chart_aliases = {
            'line': ['line', 'linear', 'trend', 'line chart', 'line graph'],
            'area': ['area', 'area chart', 'area graph'],
            'pie': ['pie', 'donut', 'doughnut', 'pie chart', 'pie graph'],
            'bar': ['bar', 'bars', 'column', 'columns', 'histogram', 'bar chart', 'bar graph'],
        }

        last_match_pos = -1
        detected_type = None

        for chart_type, aliases in chart_aliases.items():
            for alias in aliases:
                for match in re.finditer(rf'\b{re.escape(alias)}\b', p):
                    if match.start() >= last_match_pos:
                        last_match_pos = match.start()
                        detected_type = chart_type

        return detected_type

    def _normalize_chart_type(
        self,
        chart_type: Optional[str],
        requested_chart_type: Optional[str] = None,
    ) -> str:
        """Normalize AI/alias chart types to one of: bar, pie, line, area."""
        if requested_chart_type in {'bar', 'pie', 'line', 'area'}:
            return requested_chart_type

        t = (chart_type or '').strip().lower().replace('_', ' ').replace('-', ' ')
        if not t:
            return 'bar'

        if 'line' in t:
            return 'line'
        if 'area' in t:
            return 'area'
        if 'pie' in t or 'donut' in t or 'doughnut' in t:
            return 'pie'
        if 'bar' in t or 'column' in t:
            return 'bar'
        return 'bar'

    def _coerce_chart_data_for_type(self, data: Any, chart_type: str) -> Any:
        """Ensure chart data shape matches expected type for frontend renderer."""
        if chart_type in {'line', 'area'}:
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return [{'label': str(k), 'value': v} for k, v in data.items()]
            return []

        # bar/pie expected as object
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            return {
                str(item.get('label', i)): item.get('value', 0)
                for i, item in enumerate(data)
                if isinstance(item, dict)
            }
        return {}

    def _build_line_area_data(self, sorted_dict: Dict, campaigns: list) -> list:
        """Build line/area data points with campaign dates included."""
        # Build a lookup: campaign name -> {start_date, end_date}
        date_lookup = {}
        for c in campaigns:
            date_lookup[c['name']] = {
                'start_date': c.get('start_date'),
                'end_date': c.get('end_date'),
            }
        result = []
        for k, v in sorted_dict.items():
            point = {'label': k, 'value': v}
            dates = date_lookup.get(k, {})
            if dates.get('start_date'):
                point['start_date'] = dates['start_date']
            if dates.get('end_date'):
                point['end_date'] = dates['end_date']
            result.append(point)
        return result

    def _generate_fallback_chart(
        self,
        prompt: str,
        data: Dict,
        forced_intent: Optional[str] = None,
        forced_chart_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a fallback chart when LLM fails."""
        prompt_lower = self._normalize_prompt_text(prompt)
        requested_chart_type = forced_chart_type or self._get_requested_chart_type(prompt)
        metric_intent = forced_intent or self._infer_metric_intent(prompt)
        campaigns = data.get('campaigns', [])

        # Campaigns by status
        if metric_intent == 'status':
            by_status = {
                k: v for k, v in data.get('by_status', {}).items() if v > 0
            } or {'No Data': 0}
            chart_type = requested_chart_type if requested_chart_type in {'line', 'area', 'bar', 'pie'} else 'pie'
            chart_data = (
                [{'label': k, 'value': v} for k, v in by_status.items()]
                if chart_type in {'line', 'area'}
                else by_status
            )
            return {
                'chart': {
                    'type': chart_type,
                    'title': 'Campaigns by Status',
                    'data': chart_data,
                    'colors': ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'],
                    'color': '#3b82f6',
                },
                'insights': f"Total {data['stats']['total_campaigns']} campaigns. {data['stats']['active_campaigns']} active.",
            }

        # Open rate / click rate by campaign
        if metric_intent == 'open_rate':
            by_rate = data.get('by_campaign_open_rate') or {}
            if not by_rate:
                by_rate = {'No data': 0}
            sorted_data = dict(
                sorted(by_rate.items(), key=lambda x: (x[1] or 0), reverse=True)
            )
            chart_type = requested_chart_type if requested_chart_type in {'line', 'area', 'bar'} else 'bar'
            chart_data = (
                self._build_line_area_data(sorted_data, campaigns)
                if chart_type in {'line', 'area'}
                else sorted_data
            )
            return {
                'chart': {
                    'type': chart_type,
                    'title': 'Open Rate by Campaign (%)',
                    'data': chart_data,
                    'colors': ['#10b981', '#3b82f6', '#f59e0b', '#ef4444'],
                    'color': '#10b981',
                },
                'insights': 'Email open rates by campaign.',
            }

        # Emails sent by campaign
        if metric_intent == 'emails_sent':
            by_emails = data.get('by_campaign_emails_sent') or {}
            sorted_data = dict(
                sorted(by_emails.items(), key=lambda x: x[1], reverse=True)
            )
            top_n = 10
            top_match = re.search(r'top\s*(\d+)', prompt_lower)
            if top_match:
                n = int(top_match.group(1))
                sorted_data = dict(list(sorted_data.items())[:n])
            else:
                sorted_data = dict(list(sorted_data.items())[:top_n])
            if not sorted_data:
                sorted_data = {'No Data': 0}
            chart_type = requested_chart_type if requested_chart_type in {'line', 'area', 'bar'} else 'bar'
            chart_data = (
                self._build_line_area_data(sorted_data, campaigns)
                if chart_type in {'line', 'area'}
                else sorted_data
            )
            return {
                'chart': {
                    'type': chart_type,
                    'title': 'Emails Sent by Campaign',
                    'data': chart_data,
                    'colors': ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'],
                    'color': '#3b82f6',
                },
                'insights': f"Total campaigns: {data['stats']['total_campaigns']}.",
            }

        # Leads by campaign
        if metric_intent == 'leads':
            by_leads = data.get('by_campaign_leads') or {}
            sorted_data = dict(
                sorted(by_leads.items(), key=lambda x: x[1], reverse=True)[:10]
            )
            if not sorted_data:
                sorted_data = {'No Data': 0}
            chart_type = requested_chart_type if requested_chart_type in {'line', 'area', 'bar'} else 'bar'
            chart_data = (
                self._build_line_area_data(sorted_data, campaigns)
                if chart_type in {'line', 'area'}
                else sorted_data
            )
            return {
                'chart': {
                    'type': chart_type,
                    'title': 'Leads by Campaign',
                    'data': chart_data,
                    'colors': ['#10b981', '#3b82f6', '#f59e0b'],
                    'color': '#10b981',
                },
                'insights': 'Lead count per campaign.',
            }

        # Replies by campaign
        if metric_intent == 'replies':
            by_replies = data.get('by_campaign_replies') or {}
            sorted_data = dict(
                sorted(by_replies.items(), key=lambda x: x[1], reverse=True)[:10]
            )
            if not sorted_data:
                sorted_data = {'No Data': 0}
            chart_type = requested_chart_type if requested_chart_type in {'line', 'area', 'bar'} else 'bar'
            chart_data = (
                self._build_line_area_data(sorted_data, campaigns)
                if chart_type in {'line', 'area'}
                else sorted_data
            )
            return {
                'chart': {
                    'type': chart_type,
                    'title': 'Replies by Campaign',
                    'data': chart_data,
                    'colors': ['#8b5cf6', '#3b82f6', '#10b981'],
                    'color': '#8b5cf6',
                },
                'insights': 'Email replies per campaign.',
            }

        # Default: campaigns by status
        by_status = data.get('by_status') or {}
        by_status = {k: v for k, v in by_status.items() if v > 0} or {'No Data': 0}
        chart_type = requested_chart_type if requested_chart_type in {'line', 'area', 'bar', 'pie'} else 'pie'
        chart_data = (
            [{'label': k, 'value': v} for k, v in by_status.items()]
            if chart_type in {'line', 'area'}
            else by_status
        )
        return {
            'chart': {
                'type': chart_type,
                'title': 'Marketing Overview – Campaigns by Status',
                'data': chart_data,
                'colors': ['#3b82f6', '#10b981', '#f59e0b', '#ef4444'],
                'color': '#3b82f6',
            },
            'insights': f"Total {data['stats']['total_campaigns']} campaigns. {data['stats']['active_campaigns']} active.",
        }

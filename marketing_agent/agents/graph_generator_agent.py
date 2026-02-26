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

    def generate_graph(self, prompt: str) -> Dict[str, Any]:
        """
        Generate a graph configuration based on natural language prompt.
        Uses AI to interpret the prompt and select appropriate data/chart type.
        """
        marketing_data = self._fetch_marketing_data()

        campaigns_summary = [
            {
                'name': c['name'],
                'status': c['status'],
                'emails_sent': c['emails_sent'],
                'open_rate': c.get('open_rate'),
                'click_rate': c.get('click_rate'),
                'reply_rate': c.get('reply_rate'),
                'bounce_rate': c.get('bounce_rate'),
                'leads_count': c['leads_count'],
                'emails_replied': c['emails_replied'],
                'conversion_progress': c.get('conversion_progress'),
                'leads_progress': c.get('leads_progress'),
            }
            for c in marketing_data['campaigns'][:20]
        ]
        campaigns_summary_json = json.dumps(campaigns_summary, indent=2)

        data_summary = f"""
CAMPAIGNS DATA:
- Total campaigns: {marketing_data['stats']['total_campaigns']}
- Active campaigns: {marketing_data['stats']['active_campaigns']}
- Campaigns by status: {json.dumps(marketing_data['by_status'])}

Per-campaign (name, status, emails_sent, open_rate, click_rate, reply_rate, bounce_rate, leads_count, emails_replied, conversion_progress, leads_progress):
{campaigns_summary_json}

Aggregates for charts:
- Emails sent by campaign: {json.dumps(marketing_data['by_campaign_emails_sent'])}
- Open rate by campaign (percent): {json.dumps(marketing_data['by_campaign_open_rate'])}
- Leads by campaign: {json.dumps(marketing_data['by_campaign_leads'])}
- Replies by campaign: {json.dumps(marketing_data['by_campaign_replies'])}

RESEARCH DATA (recent): {json.dumps(marketing_data['research'][:5])}
"""

        system_prompt = f"""You are an AI assistant that generates chart configurations for a marketing dashboard.
Your task is to interpret the user's natural language request and return a JSON configuration for a chart.

Available data from the database:
{data_summary}

You must respond with ONLY a valid JSON object (no markdown, no explanation) with this structure:
{{
    "chart_type": "bar" | "pie" | "line" | "area",
    "title": "Chart title",
    "data": {{ "label1": value1, "label2": value2 }} for bar/pie OR [{{ "label": "x", "value": y }}] for line/area,
    "insights": "Brief insight about the data (1-2 sentences)",
    "colors": ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"]
}}

Rules:
1. For pie charts: use object format {{ "Category": count }}
2. For bar charts: use object format {{ "Category": count }}
3. For line/area charts: use array format [{{ "label": "date/period", "value": count }}]
4. Only include categories with count > 0 (or non-null rates)
5. Use the actual data values from the database
6. Choose the most appropriate chart type for the request
7. For "campaigns by status", use by_status
8. For "emails sent by campaign" or "top campaigns by volume", use by_campaign_emails_sent
9. For "open rate by campaign" or "click rate", use by_campaign_open_rate or per-campaign open_rate/click_rate
10. For "leads by campaign", use by_campaign_leads
11. For "replies by campaign", use by_campaign_replies
12. If user asks for "top N" campaigns, take the N campaigns with highest values, sorted descending
13. Always sort bar chart data by value (highest first) unless user asks for alphabetical or chronological order
"""

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

            if 'chart_type' not in chart_config:
                chart_config['chart_type'] = 'bar'
            if 'title' not in chart_config:
                chart_config['title'] = 'Generated Chart'
            if 'data' not in chart_config:
                chart_config['data'] = {}
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
            return self._generate_fallback_chart(prompt, marketing_data)
        except Exception as e:
            logger.exception(f"Error generating marketing graph: {e}")
            return self._generate_fallback_chart(prompt, marketing_data)

    def _generate_fallback_chart(self, prompt: str, data: Dict) -> Dict[str, Any]:
        """Generate a fallback chart when LLM fails."""
        prompt_lower = prompt.lower()

        # Campaigns by status
        if 'status' in prompt_lower and 'campaign' in prompt_lower:
            by_status = {
                k: v for k, v in data.get('by_status', {}).items() if v > 0
            } or {'No Data': 0}
            return {
                'chart': {
                    'type': 'pie',
                    'title': 'Campaigns by Status',
                    'data': by_status,
                    'colors': ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'],
                    'color': '#3b82f6',
                },
                'insights': f"Total {data['stats']['total_campaigns']} campaigns. {data['stats']['active_campaigns']} active.",
            }

        # Open rate / click rate by campaign
        if 'open rate' in prompt_lower or 'click rate' in prompt_lower:
            by_rate = data.get('by_campaign_open_rate') or {}
            if not by_rate:
                by_rate = {'No data': 0}
            sorted_data = dict(
                sorted(by_rate.items(), key=lambda x: (x[1] or 0), reverse=True)
            )
            return {
                'chart': {
                    'type': 'bar',
                    'title': 'Open Rate by Campaign (%)',
                    'data': sorted_data,
                    'colors': ['#10b981', '#3b82f6', '#f59e0b', '#ef4444'],
                    'color': '#10b981',
                },
                'insights': 'Email open rates by campaign.',
            }

        # Emails sent by campaign
        if 'email' in prompt_lower and ('sent' in prompt_lower or 'volume' in prompt_lower):
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
            return {
                'chart': {
                    'type': 'bar',
                    'title': 'Emails Sent by Campaign',
                    'data': sorted_data,
                    'colors': ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'],
                    'color': '#3b82f6',
                },
                'insights': f"Total campaigns: {data['stats']['total_campaigns']}.",
            }

        # Leads by campaign
        if 'lead' in prompt_lower and 'campaign' in prompt_lower:
            by_leads = data.get('by_campaign_leads') or {}
            sorted_data = dict(
                sorted(by_leads.items(), key=lambda x: x[1], reverse=True)
            )[:10]
            if not sorted_data:
                sorted_data = {'No Data': 0}
            return {
                'chart': {
                    'type': 'bar',
                    'title': 'Leads by Campaign',
                    'data': sorted_data,
                    'colors': ['#10b981', '#3b82f6', '#f59e0b'],
                    'color': '#10b981',
                },
                'insights': 'Lead count per campaign.',
            }

        # Replies by campaign
        if 'repl' in prompt_lower and 'campaign' in prompt_lower:
            by_replies = data.get('by_campaign_replies') or {}
            sorted_data = dict(
                sorted(by_replies.items(), key=lambda x: x[1], reverse=True)
            )[:10]
            if not sorted_data:
                sorted_data = {'No Data': 0}
            return {
                'chart': {
                    'type': 'bar',
                    'title': 'Replies by Campaign',
                    'data': sorted_data,
                    'colors': ['#8b5cf6', '#3b82f6', '#10b981'],
                    'color': '#8b5cf6',
                },
                'insights': 'Email replies per campaign.',
            }

        # Default: campaigns by status
        by_status = data.get('by_status') or {}
        by_status = {k: v for k, v in by_status.items() if v > 0} or {'No Data': 0}
        return {
            'chart': {
                'type': 'pie',
                'title': 'Marketing Overview – Campaigns by Status',
                'data': by_status,
                'colors': ['#3b82f6', '#10b981', '#f59e0b', '#ef4444'],
                'color': '#3b82f6',
            },
            'insights': f"Total {data['stats']['total_campaigns']} campaigns. {data['stats']['active_campaigns']} active.",
        }

"""
Marketing Knowledge Q&A + Analytics Agent
Foundation Agent - Provides data understanding and answers marketing questions
This is the BRAIN that all other agents will use.
"""

from .marketing_base_agent import MarketingBaseAgent
from typing import Dict, Optional, List
from marketing_agent.models import Campaign, CampaignPerformance, MarketResearch
import json
from datetime import datetime, timedelta
from django.db.models import Sum, Avg, Count, Q


class MarketingQAAgent(MarketingBaseAgent):
    """
    Foundation Agent - Marketing Knowledge Q&A + Analytics
    
    This agent is the BRAIN of the marketing system:
    - Answers marketing and business questions using data
    - Analyzes campaign performance
    - Provides data-backed insights
    - Connects internal data with market insights
    - Serves as foundation for all other marketing agents
    
    Capabilities:
    - Answer questions like "Why are sales dropping?"
    - Analyze what's working and what's not
    - Compare campaign performance
    - Provide marketing intelligence
    - Data-driven recommendations
    """
    
    def __init__(self):
        super().__init__()
        self.system_prompt = """You are a Marketing Knowledge Q&A + Analytics Agent - the foundation brain of a marketing system.
        Your role is to:
        1. Answer marketing and business questions using data
        2. Analyze campaign performance and metrics
        3. Provide data-backed insights and recommendations
        4. Understand what's working and what's not working
        5. Connect internal company data with market insights
        
        You provide intelligent, data-driven answers to questions like:
        - "Why are sales dropping?"
        - "What campaigns are performing best?"
        - "What is our ROI?"
        - "Which channels are most effective?"
        - "What should we focus on?"
        
        Always base your answers on the data provided. Be specific, actionable, and data-driven."""
    
    def process(self, question: str, context: Optional[Dict] = None, user_id: Optional[int] = None) -> Dict:
        """
        Main entry point - answers marketing questions with data
        
        Args:
            question (str): Marketing/business question
            context (Dict): Optional context (campaigns, performance data, etc.)
            user_id (int): User ID for filtering user's data
            
        Returns:
            Dict: Answer with insights and data
        """
        self.log_action("Processing marketing question", {"question": question[:100]})
        
        # Get marketing data from database
        marketing_data = self._get_marketing_data(user_id)
        
        # Build comprehensive context
        full_context = self._build_context(marketing_data, context)
        
        # Generate answer using AI
        answer = self._generate_answer(question, full_context)
        
        # Extract insights
        insights = self._extract_insights(marketing_data, question)
        
        return {
            'success': True,
            'answer': answer,
            'insights': insights,
            'data_summary': self._create_data_summary(marketing_data),
            'question': question
        }
    
    def _get_marketing_data(self, user_id: Optional[int] = None) -> Dict:
        """Get all marketing data from database"""
        campaigns_query = Campaign.objects.all()
        if user_id:
            campaigns_query = campaigns_query.filter(owner_id=user_id)
        
        campaigns = campaigns_query.select_related('owner').prefetch_related('performance_metrics')
        
        # Get campaign data
        campaigns_data = []
        for campaign in campaigns:
            # Get performance metrics
            metrics = CampaignPerformance.objects.filter(campaign=campaign)
            
            campaigns_data.append({
                'id': campaign.id,
                'name': campaign.name,
                'type': campaign.campaign_type,
                'status': campaign.status,
                'start_date': campaign.start_date.isoformat() if campaign.start_date else None,
                'end_date': campaign.end_date.isoformat() if campaign.end_date else None,
                'metrics': [
                    {
                        'name': m.metric_name,
                        'value': float(m.metric_value),
                        'date': m.date.isoformat(),
                        'channel': m.channel
                    }
                    for m in metrics[:20]  # Limit to recent metrics
                ],
                'goals': campaign.goals,
                'channels': campaign.channels
            })
        
        # Get market research data
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
                'created_at': r.created_at.isoformat()
            }
            for r in research_query[:10]  # Recent research
        ]
        
        # Calculate aggregate metrics
        active_campaigns = campaigns_query.filter(status='active').count()
        total_budget = sum(float(c.budget) for c in campaigns_query)
        total_spend = sum(float(c.actual_spend) for c in campaigns_query)
        
        # Get performance aggregates
        all_metrics = CampaignPerformance.objects.filter(
            campaign__in=campaigns_query
        ).values('metric_name').annotate(
            avg_value=Avg('metric_value'),
            total_count=Count('id')
        )
        
        return {
            'campaigns': campaigns_data,
            'research': research_data,
            'stats': {
                'total_campaigns': len(campaigns_data),
                'active_campaigns': active_campaigns,
                'total_budget': total_budget,
                'total_spend': total_spend,
                'budget_remaining': total_budget - total_spend,
                'performance_metrics': list(all_metrics)
            }
        }
    
    def _build_context(self, marketing_data: Dict, additional_context: Optional[Dict] = None) -> str:
        """Build comprehensive context string for AI"""
        context = "MARKETING DATA CONTEXT:\n\n"
        
        # Add stats
        stats = marketing_data.get('stats', {})
        context += f"OVERVIEW:\n"
        context += f"- Total Campaigns: {stats.get('total_campaigns', 0)}\n"
        context += f"- Active Campaigns: {stats.get('active_campaigns', 0)}\n"
        context += f"- Total Budget: ${stats.get('total_budget', 0):,.2f}\n"
        context += f"- Total Spent: ${stats.get('total_spend', 0):,.2f}\n"
        context += f"- Budget Remaining: ${stats.get('budget_remaining', 0):,.2f}\n\n"
        
        # Add campaigns
        campaigns = marketing_data.get('campaigns', [])
        if campaigns:
            context += f"CAMPAIGNS ({len(campaigns)} total):\n"
            for camp in campaigns[:10]:  # Limit to 10 for context
                context += f"\nCampaign: {camp['name']}\n"
                context += f"- Type: {camp['type']}, Status: {camp['status']}\n"
                context += f"- Budget: ${camp['budget']:,.2f}, Spent: ${camp['spend']:,.2f}\n"
                if camp['metrics']:
                    context += f"- Recent Metrics:\n"
                    for metric in camp['metrics'][:5]:  # Top 5 metrics
                        context += f"  * {metric['name']}: {metric['value']} ({metric.get('channel', 'N/A')})\n"
        
        # Add market research
        research = marketing_data.get('research', [])
        if research:
            context += f"\nMARKET RESEARCH ({len(research)} recent):\n"
            for r in research[:5]:
                context += f"- {r['type']}: {r['topic']}\n"
                if r.get('insights'):
                    context += f"  Insights: {r['insights'][:200]}...\n"
        
        # Add additional context if provided
        if additional_context:
            context += f"\nADDITIONAL CONTEXT:\n{json.dumps(additional_context, indent=2)}\n"
        
        return context
    
    def _generate_answer(self, question: str, context: str) -> str:
        """Generate AI-powered answer to marketing question using Groq API"""
        # Format prompt for Groq (chat format)
        prompt = f"""Based on the marketing data provided below, answer this question: "{question}"

{context}

Provide a comprehensive, data-driven answer. Include:
1. Direct answer to the question
2. Relevant data points and metrics
3. Insights and patterns you notice
4. Actionable recommendations if applicable

Be specific, use numbers, and base everything on the data provided."""
        
        try:
            # Use Groq for Q&A
            answer = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.3,  # Lower temperature for more factual answers
                max_tokens=2000  # Groq supports longer responses
            )
            return answer
        except Exception as e:
            self.log_action("Error generating answer", {"error": str(e)})
            return f"I encountered an error while analyzing the data: {str(e)}"
    
    def _extract_insights(self, marketing_data: Dict, question: str) -> List[Dict]:
        """Extract key insights from data"""
        insights = []
        
        stats = marketing_data.get('stats', {})
        campaigns = marketing_data.get('campaigns', [])
        
        # Budget insights
        if stats.get('total_budget', 0) > 0:
            spend_percentage = (stats.get('total_spend', 0) / stats.get('total_budget', 1)) * 100
            insights.append({
                'type': 'budget',
                'title': 'Budget Utilization',
                'value': f"{spend_percentage:.1f}% of budget spent",
                'status': 'warning' if spend_percentage > 80 else 'normal'
            })
        
        # Campaign status insights
        active_count = stats.get('active_campaigns', 0)
        total_count = stats.get('total_campaigns', 0)
        if total_count > 0:
            active_percentage = (active_count / total_count) * 100
            insights.append({
                'type': 'campaigns',
                'title': 'Active Campaigns',
                'value': f"{active_count}/{total_count} campaigns active ({active_percentage:.1f}%)",
                'status': 'good' if active_percentage > 50 else 'warning'
            })
        
        # Performance insights (if metrics exist)
        if campaigns:
            campaigns_with_metrics = [c for c in campaigns if c.get('metrics')]
            if campaigns_with_metrics:
                insights.append({
                    'type': 'performance',
                    'title': 'Data Availability',
                    'value': f"{len(campaigns_with_metrics)} campaigns have performance data",
                    'status': 'good'
                })
        
        return insights
    
    def _create_data_summary(self, marketing_data: Dict) -> Dict:
        """Create summary of available data"""
        return {
            'campaigns_count': len(marketing_data.get('campaigns', [])),
            'research_count': len(marketing_data.get('research', [])),
            'has_performance_data': any(
                c.get('metrics') for c in marketing_data.get('campaigns', [])
            ),
            'stats': marketing_data.get('stats', {})
        }
    
    def analyze_campaign_performance(self, campaign_id: int, user_id: Optional[int] = None) -> Dict:
        """
        Analyze specific campaign performance
        
        Args:
            campaign_id (int): Campaign ID to analyze
            user_id (int): User ID for access control
            
        Returns:
            Dict: Performance analysis
        """
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            if user_id and campaign.owner_id != user_id:
                return {'success': False, 'error': 'Access denied'}
            
            metrics = CampaignPerformance.objects.filter(campaign=campaign)
            
            # Calculate key metrics
            total_impressions = metrics.filter(metric_name='impressions').aggregate(
                total=Sum('metric_value')
            )['total'] or 0
            
            total_clicks = metrics.filter(metric_name='clicks').aggregate(
                total=Sum('metric_value')
            )['total'] or 0
            
            total_conversions = metrics.filter(metric_name='conversions').aggregate(
                total=Sum('metric_value')
            )['total'] or 0
            
            # Calculate rates
            ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
            conversion_rate = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0
            
            # ROI
            roi = campaign.get_roi()
            
            # Generate analysis
            analysis_prompt = f"""Analyze this campaign performance:

Campaign: {campaign.name}
Type: {campaign.campaign_type}
Budget: ${float(campaign.budget):,.2f}
Spent: ${float(campaign.actual_spend):,.2f}
Status: {campaign.status}

Performance Metrics:
- Impressions: {total_impressions:,.0f}
- Clicks: {total_clicks:,.0f}
- Conversions: {total_conversions:,.0f}
- CTR: {ctr:.2f}%
- Conversion Rate: {conversion_rate:.2f}%
- ROI: {roi:.2f}% if available

Provide:
1. Overall performance assessment
2. What's working well
3. Areas for improvement
4. Recommendations for optimization"""
            
            # Use Groq for Q&A analysis
            analysis = self._call_llm_for_reasoning(analysis_prompt, self.system_prompt, temperature=0.3)
            
            return {
                'success': True,
                'campaign_id': campaign_id,
                'campaign_name': campaign.name,
                'metrics': {
                    'impressions': float(total_impressions),
                    'clicks': float(total_clicks),
                    'conversions': float(total_conversions),
                    'ctr': ctr,
                    'conversion_rate': conversion_rate,
                    'roi': roi
                },
                'analysis': analysis
            }
        except Campaign.DoesNotExist:
            return {'success': False, 'error': 'Campaign not found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}


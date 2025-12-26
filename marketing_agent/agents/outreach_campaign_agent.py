"""
Outreach & Campaign Agent
Designs, launches, and manages multi-channel marketing campaigns across email, 
social, paid ads, and partnerships, ensuring consistent messaging and timely execution.
"""

from .marketing_base_agent import MarketingBaseAgent
from typing import Dict, Optional, List
from marketing_agent.models import Campaign, CampaignPerformance, MarketResearch
from django.contrib.auth.models import User
from datetime import datetime, timedelta
import json


class OutreachCampaignAgent(MarketingBaseAgent):
    """
    Outreach & Campaign Agent
    
    This agent:
    - Designs multi-channel marketing campaigns
    - Launches campaigns across email, social, paid ads, and partnerships
    - Manages campaign execution and ensures timely delivery
    - Ensures consistent messaging across all channels
    - Tracks campaign performance and optimizes in real-time
    - Coordinates multi-channel campaign workflows
    
    Capabilities:
    - Campaign strategy design
    - Multi-channel campaign planning
    - Content and messaging consistency
    - Campaign launch and scheduling
    - Performance monitoring and optimization
    - Cross-channel coordination
    """
    
    def __init__(self):
        super().__init__()
        self.system_prompt = """You are an Outreach & Campaign Agent for a marketing system.
        Your role is to:
        1. Design comprehensive multi-channel marketing campaigns
        2. Launch campaigns across email, social media, paid advertising, and partnerships
        3. Ensure consistent messaging and branding across all channels
        4. Manage campaign execution and ensure timely delivery
        5. Coordinate campaign workflows and schedules
        6. Monitor campaign performance and optimize in real-time
        7. Provide campaign recommendations and best practices
        
        You are an expert in:
        - Multi-channel campaign strategy
        - Email marketing campaigns
        - Social media campaign management
        - Paid advertising (PPC, display, etc.)
        - Partnership and affiliate campaigns
        - Campaign messaging and content consistency
        - Campaign scheduling and automation
        - Performance tracking and optimization
        
        Always provide actionable, strategic campaign plans with clear timelines, 
        messaging guidelines, and performance metrics."""
    
    def process(self, action: str, user_id: int, campaign_data: Optional[Dict] = None,
                campaign_id: Optional[int] = None, context: Optional[Dict] = None) -> Dict:
        """
        Main entry point - handles various campaign actions
        
        Args:
            action (str): Action to perform (design, launch, manage, optimize, schedule)
            user_id (int): User ID for campaign ownership
            campaign_data (Dict): Campaign data for design/creation
            campaign_id (int): Existing campaign ID for management actions
            context (Dict): Additional context (research, goals, etc.)
            
        Returns:
            Dict: Action results with campaign information
        """
        self.log_action(f"Processing campaign action: {action}", {
            "user_id": user_id,
            "campaign_id": campaign_id
        })
        
        if action == 'design':
            return self.design_campaign(user_id, campaign_data, context)
        elif action == 'launch':
            return self.launch_campaign(campaign_id, user_id, context)
        elif action == 'manage':
            return self.manage_campaign(campaign_id, user_id, context)
        elif action == 'optimize':
            return self.optimize_campaign(campaign_id, user_id, context)
        elif action == 'schedule':
            return self.schedule_campaign(campaign_id, user_id, campaign_data)
        elif action == 'create_multi_channel':
            return self.create_multi_channel_campaign(user_id, campaign_data, context)
        else:
            return {
                'success': False,
                'error': f'Unknown action: {action}. Supported actions: design, launch, manage, optimize, schedule, create_multi_channel'
            }
    
    def design_campaign(self, user_id: int, campaign_data: Optional[Dict] = None,
                       context: Optional[Dict] = None) -> Dict:
        """
        Design a comprehensive multi-channel marketing campaign
        
        Args:
            user_id (int): User ID
            campaign_data (Dict): Campaign requirements (name, goals, target_audience, budget, etc.)
            context (Dict): Additional context (market research, competitor data, etc.)
            
        Returns:
            Dict: Campaign design with strategy, channels, messaging, and timeline
        """
        self.log_action("Designing campaign", {"user_id": user_id})
        
        # Get relevant market research for context
        research_context = self._get_research_context(user_id)
        
        # Build comprehensive context
        full_context = self._build_design_context(campaign_data, context, research_context)
        
        # Generate campaign design using AI
        campaign_design = self._generate_campaign_design(full_context)
        
        # Parse and structure the design
        structured_design = self._parse_campaign_design(campaign_design, campaign_data)
        
        return {
            'success': True,
            'action': 'design',
            'campaign_design': structured_design,
            'raw_design': campaign_design,
            'recommendations': structured_design.get('recommendations', [])
        }
    
    def create_multi_channel_campaign(self, user_id: int, campaign_data: Dict,
                                      context: Optional[Dict] = None) -> Dict:
        """
        Create and save a multi-channel campaign to database
        
        Args:
            user_id (int): User ID
            campaign_data (Dict): Campaign data (name, goals, channels, budget, etc.)
            context (Dict): Additional context
            
        Returns:
            Dict: Created campaign information
        """
        self.log_action("Creating multi-channel campaign", {"user_id": user_id})
        
        try:
            user = User.objects.get(id=user_id)
            
            # Design the campaign first
            design_result = self.design_campaign(user_id, campaign_data, context)
            if not design_result.get('success'):
                return design_result
            
            design = design_result.get('campaign_design', {})
            
            # Create campaign in database
            campaign = Campaign.objects.create(
                name=campaign_data.get('name', design.get('campaign_name', 'New Campaign')),
                description=campaign_data.get('description', design.get('description', '')),
                campaign_type=campaign_data.get('campaign_type', 'integrated'),
                status='draft',
                start_date=campaign_data.get('start_date'),
                end_date=campaign_data.get('end_date'),
                budget=campaign_data.get('budget', 0),
                target_audience=campaign_data.get('target_audience', design.get('target_audience', {})),
                goals=campaign_data.get('goals', design.get('goals', {})),
                channels=design.get('channels', campaign_data.get('channels', [])),
                owner=user
            )
            
            return {
                'success': True,
                'action': 'create_multi_channel',
                'campaign_id': campaign.id,
                'campaign_name': campaign.name,
                'campaign_design': design,
                'status': campaign.status,
                'channels': campaign.channels,
                'message': f'Campaign "{campaign.name}" created successfully'
            }
        except User.DoesNotExist:
            return {'success': False, 'error': 'User not found'}
        except Exception as e:
            self.log_action("Error creating campaign", {"error": str(e)})
            return {'success': False, 'error': str(e)}
    
    def launch_campaign(self, campaign_id: int, user_id: int,
                      context: Optional[Dict] = None) -> Dict:
        """
        Launch a campaign across all specified channels
        
        Args:
            campaign_id (int): Campaign ID to launch
            user_id (int): User ID for access control
            context (Dict): Launch context (scheduling, automation, etc.)
            
        Returns:
            Dict: Launch results and status
        """
        self.log_action("Launching campaign", {"campaign_id": campaign_id})
        
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            if campaign.owner_id != user_id:
                return {'success': False, 'error': 'Access denied'}
            
            # Generate launch plan
            launch_plan = self._generate_launch_plan(campaign, context)
            
            # Update campaign status
            campaign.status = 'active'
            if not campaign.start_date:
                campaign.start_date = datetime.now().date()
            campaign.save()
            
            # Create initial performance tracking entries
            self._initialize_performance_tracking(campaign)
            
            return {
                'success': True,
                'action': 'launch',
                'campaign_id': campaign_id,
                'campaign_name': campaign.name,
                'launch_plan': launch_plan,
                'status': campaign.status,
                'channels': campaign.channels,
                'start_date': campaign.start_date.isoformat() if campaign.start_date else None,
                'message': f'Campaign "{campaign.name}" launched successfully across {len(campaign.channels)} channels'
            }
        except Campaign.DoesNotExist:
            return {'success': False, 'error': 'Campaign not found'}
        except Exception as e:
            self.log_action("Error launching campaign", {"error": str(e)})
            return {'success': False, 'error': str(e)}
    
    def manage_campaign(self, campaign_id: int, user_id: int,
                       context: Optional[Dict] = None) -> Dict:
        """
        Manage an active campaign - monitor, adjust, and coordinate
        
        Args:
            campaign_id (int): Campaign ID to manage
            user_id (int): User ID for access control
            context (Dict): Management context (actions, adjustments, etc.)
            
        Returns:
            Dict: Management results and recommendations
        """
        self.log_action("Managing campaign", {"campaign_id": campaign_id})
        
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            if campaign.owner_id != user_id:
                return {'success': False, 'error': 'Access denied'}
            
            # Get current performance
            performance = self._get_campaign_performance(campaign)
            
            # Generate management recommendations
            management_plan = self._generate_management_plan(campaign, performance, context)
            
            # Check for consistency across channels
            consistency_check = self._check_messaging_consistency(campaign)
            
            # Check timing and scheduling
            timing_check = self._check_campaign_timing(campaign)
            
            return {
                'success': True,
                'action': 'manage',
                'campaign_id': campaign_id,
                'campaign_name': campaign.name,
                'current_status': campaign.status,
                'performance': performance,
                'management_plan': management_plan,
                'consistency_check': consistency_check,
                'timing_check': timing_check,
                'recommendations': management_plan.get('recommendations', [])
            }
        except Campaign.DoesNotExist:
            return {'success': False, 'error': 'Campaign not found'}
        except Exception as e:
            self.log_action("Error managing campaign", {"error": str(e)})
            return {'success': False, 'error': str(e)}
    
    def optimize_campaign(self, campaign_id: int, user_id: int,
                         context: Optional[Dict] = None) -> Dict:
        """
        Optimize campaign performance based on current metrics
        
        Args:
            campaign_id (int): Campaign ID to optimize
            user_id (int): User ID for access control
            context (Dict): Optimization context (focus areas, constraints, etc.)
            
        Returns:
            Dict: Optimization recommendations and actions
        """
        self.log_action("Optimizing campaign", {"campaign_id": campaign_id})
        
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            if campaign.owner_id != user_id:
                return {'success': False, 'error': 'Access denied'}
            
            # Get performance data
            performance = self._get_campaign_performance(campaign)
            
            # Generate optimization recommendations
            optimization_plan = self._generate_optimization_plan(campaign, performance, context)
            
            return {
                'success': True,
                'action': 'optimize',
                'campaign_id': campaign_id,
                'campaign_name': campaign.name,
                'current_performance': performance,
                'optimization_plan': optimization_plan,
                'recommendations': optimization_plan.get('recommendations', []),
                'priority_actions': optimization_plan.get('priority_actions', [])
            }
        except Campaign.DoesNotExist:
            return {'success': False, 'error': 'Campaign not found'}
        except Exception as e:
            self.log_action("Error optimizing campaign", {"error": str(e)})
            return {'success': False, 'error': str(e)}
    
    def schedule_campaign(self, campaign_id: int, user_id: int,
                        schedule_data: Optional[Dict] = None) -> Dict:
        """
        Schedule campaign launch and channel-specific activities
        
        Args:
            campaign_id (int): Campaign ID to schedule
            user_id (int): User ID for access control
            schedule_data (Dict): Scheduling data (dates, times, channels, etc.)
            
        Returns:
            Dict: Schedule information and timeline
        """
        self.log_action("Scheduling campaign", {"campaign_id": campaign_id})
        
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            if campaign.owner_id != user_id:
                return {'success': False, 'error': 'Access denied'}
            
            # Generate schedule
            schedule = self._generate_campaign_schedule(campaign, schedule_data)
            
            # Update campaign dates if provided
            if schedule_data:
                if 'start_date' in schedule_data:
                    campaign.start_date = schedule_data['start_date']
                if 'end_date' in schedule_data:
                    campaign.end_date = schedule_data['end_date']
                campaign.status = 'scheduled'
                campaign.save()
            
            return {
                'success': True,
                'action': 'schedule',
                'campaign_id': campaign_id,
                'campaign_name': campaign.name,
                'schedule': schedule,
                'start_date': campaign.start_date.isoformat() if campaign.start_date else None,
                'end_date': campaign.end_date.isoformat() if campaign.end_date else None,
                'status': campaign.status
            }
        except Campaign.DoesNotExist:
            return {'success': False, 'error': 'Campaign not found'}
        except Exception as e:
            self.log_action("Error scheduling campaign", {"error": str(e)})
            return {'success': False, 'error': str(e)}
    
    # Helper methods
    
    def _get_research_context(self, user_id: int) -> Dict:
        """Get relevant market research for campaign context"""
        research = MarketResearch.objects.filter(created_by_id=user_id).order_by('-created_at')[:5]
        return {
            'recent_research': [
                {
                    'type': r.research_type,
                    'topic': r.topic,
                    'insights': r.insights[:500] if r.insights else '',
                    'findings': r.findings
                }
                for r in research
            ]
        }
    
    def _build_design_context(self, campaign_data: Optional[Dict],
                             additional_context: Optional[Dict],
                             research_context: Dict) -> str:
        """Build comprehensive context for campaign design"""
        context = "CAMPAIGN DESIGN CONTEXT:\n\n"
        
        if campaign_data:
            context += "CAMPAIGN REQUIREMENTS:\n"
            context += f"- Name: {campaign_data.get('name', 'New Campaign')}\n"
            context += f"- Goals: {json.dumps(campaign_data.get('goals', {}), indent=2)}\n"
            context += f"- Target Audience: {json.dumps(campaign_data.get('target_audience', {}), indent=2)}\n"
            context += f"- Budget: ${campaign_data.get('budget', 0):,.2f}\n"
            context += f"- Preferred Channels: {', '.join(campaign_data.get('channels', []))}\n"
            context += f"- Timeline: {campaign_data.get('timeline', 'Not specified')}\n\n"
        
        if research_context.get('recent_research'):
            context += "MARKET RESEARCH INSIGHTS:\n"
            for r in research_context['recent_research'][:3]:
                context += f"- {r['type']}: {r['topic']}\n"
                if r.get('insights'):
                    context += f"  Insights: {r['insights'][:200]}...\n"
            context += "\n"
        
        if additional_context:
            context += f"ADDITIONAL CONTEXT:\n{json.dumps(additional_context, indent=2)}\n\n"
        
        return context
    
    def _generate_campaign_design(self, context: str) -> str:
        """Generate campaign design using AI"""
        prompt = f"""Design a comprehensive multi-channel marketing campaign based on the following requirements:

{context}

Create a detailed campaign design that includes:

## CAMPAIGN STRATEGY
- Campaign name and positioning
- Primary objectives and KPIs
- Target audience personas
- Key messaging and value propositions

## MULTI-CHANNEL PLAN
Design campaigns for each channel:

### Email Marketing
- Email campaign strategy
- Content themes and messaging
- Send schedule and frequency
- Segmentation approach

### Social Media
- Platform selection (Facebook, Instagram, LinkedIn, Twitter, etc.)
- Content calendar and themes
- Engagement strategy
- Posting schedule

### Paid Advertising
- Ad platform selection (Google Ads, Facebook Ads, etc.)
- Ad formats and creative approach
- Targeting strategy
- Budget allocation

### Partnerships
- Partnership opportunities
- Affiliate or influencer strategy
- Co-marketing opportunities
- Collaboration approach

## MESSAGING CONSISTENCY
- Core messaging framework
- Brand voice guidelines
- Channel-specific adaptations
- Consistency checklist

## TIMELINE & EXECUTION
- Campaign timeline (pre-launch, launch, post-launch)
- Channel launch sequence
- Key milestones
- Dependencies

## BUDGET ALLOCATION
- Budget breakdown by channel
- Cost estimates
- ROI projections

## PERFORMANCE METRICS
- KPIs for each channel
- Tracking and measurement plan
- Success criteria

Provide a comprehensive, actionable campaign design that ensures consistent messaging 
across all channels and timely execution."""
        
        try:
            design = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.7,  # Creative but structured
                max_tokens=3000
            )
            return design
        except Exception as e:
            self.log_action("Error generating campaign design", {"error": str(e)})
            return f"Error generating campaign design: {str(e)}"
    
    def _parse_campaign_design(self, design_text: str, campaign_data: Optional[Dict]) -> Dict:
        """Parse AI-generated design into structured format"""
        return {
            'campaign_name': campaign_data.get('name', 'New Campaign') if campaign_data else 'New Campaign',
            'description': design_text[:500] if design_text else '',
            'raw_design': design_text,
            'channels': campaign_data.get('channels', ['email', 'social', 'paid']) if campaign_data else ['email', 'social', 'paid'],
            'target_audience': campaign_data.get('target_audience', {}) if campaign_data else {},
            'goals': campaign_data.get('goals', {}) if campaign_data else {},
            'recommendations': self._extract_recommendations(design_text)
        }
    
    def _extract_recommendations(self, design_text: str) -> List[str]:
        """Extract key recommendations from design text"""
        # Simple extraction - can be enhanced with more sophisticated parsing
        recommendations = []
        lines = design_text.split('\n')
        for line in lines:
            if any(keyword in line.lower() for keyword in ['recommend', 'suggest', 'should', 'consider', 'priority']):
                if len(line.strip()) > 20:  # Filter out very short lines
                    recommendations.append(line.strip())
        return recommendations[:10]  # Top 10 recommendations
    
    def _generate_launch_plan(self, campaign: Campaign, context: Optional[Dict]) -> Dict:
        """Generate launch plan for campaign"""
        prompt = f"""Create a detailed launch plan for this campaign:

Campaign: {campaign.name}
Type: {campaign.campaign_type}
Channels: {', '.join(campaign.channels) if campaign.channels else 'Multi-channel'}
Budget: ${float(campaign.budget):,.2f}
Goals: {json.dumps(campaign.goals, indent=2)}

Provide a launch plan that includes:
1. Pre-launch checklist
2. Launch sequence for each channel
3. Timing and scheduling
4. Automation setup
5. Monitoring and tracking setup
6. Success criteria

Ensure all channels are coordinated and messaging is consistent."""
        
        try:
            launch_plan_text = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.5,
                max_tokens=2000
            )
            
            return {
                'launch_sequence': self._extract_launch_sequence(launch_plan_text),
                'checklist': self._extract_checklist(launch_plan_text),
                'full_plan': launch_plan_text
            }
        except Exception as e:
            return {'error': str(e), 'full_plan': 'Error generating launch plan'}
    
    def _extract_launch_sequence(self, text: str) -> List[Dict]:
        """Extract launch sequence from text"""
        # Simple extraction - can be enhanced
        sequence = []
        lines = text.split('\n')
        current_channel = None
        for line in lines:
            line_lower = line.lower()
            if any(channel in line_lower for channel in ['email', 'social', 'paid', 'partnership']):
                current_channel = line.strip()
            elif 'step' in line_lower or 'day' in line_lower or 'phase' in line_lower:
                if current_channel:
                    sequence.append({
                        'channel': current_channel,
                        'step': line.strip()
                    })
        return sequence if sequence else [
            {'channel': 'All', 'step': 'Launch campaign across all channels'}
        ]
    
    def _extract_checklist(self, text: str) -> List[str]:
        """Extract checklist items from text"""
        checklist = []
        lines = text.split('\n')
        for line in lines:
            if any(marker in line for marker in ['-', '•', '*', '✓', '☐', '[]']):
                item = line.strip().lstrip('- •*✓☐[]').strip()
                if item and len(item) > 10:
                    checklist.append(item)
        return checklist[:15]  # Top 15 items
    
    def _initialize_performance_tracking(self, campaign: Campaign):
        """Initialize performance tracking metrics for campaign"""
        # Create placeholder metrics for tracking
        metrics = ['impressions', 'clicks', 'conversions', 'engagement']
        for metric in metrics:
            CampaignPerformance.objects.get_or_create(
                campaign=campaign,
                metric_name=metric,
                date=datetime.now().date(),
                channel='all',
                defaults={'metric_value': 0}
            )
    
    def _get_campaign_performance(self, campaign: Campaign) -> Dict:
        """Get current campaign performance metrics"""
        metrics = CampaignPerformance.objects.filter(campaign=campaign)
        
        performance = {
            'total_impressions': 0,
            'total_clicks': 0,
            'total_conversions': 0,
            'total_engagement': 0,
            'by_channel': {}
        }
        
        for metric in metrics:
            value = float(metric.metric_value)
            metric_name = metric.metric_name
            channel = metric.channel or 'all'
            
            if metric_name == 'impressions':
                performance['total_impressions'] += value
            elif metric_name == 'clicks':
                performance['total_clicks'] += value
            elif metric_name == 'conversions':
                performance['total_conversions'] += value
            elif metric_name == 'engagement':
                performance['total_engagement'] += value
            
            if channel not in performance['by_channel']:
                performance['by_channel'][channel] = {}
            performance['by_channel'][channel][metric_name] = value
        
        # Calculate rates
        if performance['total_impressions'] > 0:
            performance['ctr'] = (performance['total_clicks'] / performance['total_impressions']) * 100
        else:
            performance['ctr'] = 0
        
        if performance['total_clicks'] > 0:
            performance['conversion_rate'] = (performance['total_conversions'] / performance['total_clicks']) * 100
        else:
            performance['conversion_rate'] = 0
        
        # ROI
        performance['roi'] = campaign.get_roi()
        performance['spend'] = float(campaign.actual_spend)
        performance['budget'] = float(campaign.budget)
        
        return performance
    
    def _generate_management_plan(self, campaign: Campaign, performance: Dict,
                                  context: Optional[Dict]) -> Dict:
        """Generate campaign management recommendations"""
        prompt = f"""Analyze this campaign and provide management recommendations:

Campaign: {campaign.name}
Status: {campaign.status}
Channels: {', '.join(campaign.channels) if campaign.channels else 'Multi-channel'}
Performance:
- Impressions: {performance.get('total_impressions', 0):,.0f}
- Clicks: {performance.get('total_clicks', 0):,.0f}
- Conversions: {performance.get('total_conversions', 0):,.0f}
- CTR: {performance.get('ctr', 0):.2f}%
- Conversion Rate: {performance.get('conversion_rate', 0):.2f}%
- Spend: ${performance.get('spend', 0):,.2f} / Budget: ${performance.get('budget', 0):,.2f}

Provide:
1. Performance assessment
2. Channel-specific recommendations
3. Messaging consistency check
4. Timing and scheduling adjustments
5. Budget optimization suggestions
6. Priority actions"""
        
        try:
            management_text = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.5,
                max_tokens=2000
            )
            
            return {
                'assessment': management_text,
                'recommendations': self._extract_recommendations(management_text),
                'priority_actions': self._extract_priority_actions(management_text)
            }
        except Exception as e:
            return {'error': str(e), 'recommendations': []}
    
    def _extract_priority_actions(self, text: str) -> List[str]:
        """Extract priority actions from text"""
        actions = []
        lines = text.split('\n')
        for line in lines:
            if any(keyword in line.lower() for keyword in ['priority', 'urgent', 'immediate', 'action']):
                if len(line.strip()) > 20:
                    actions.append(line.strip())
        return actions[:5]  # Top 5 priority actions
    
    def _check_messaging_consistency(self, campaign: Campaign) -> Dict:
        """Check messaging consistency across channels"""
        prompt = f"""Review this campaign for messaging consistency:

Campaign: {campaign.name}
Channels: {', '.join(campaign.channels) if campaign.channels else 'Multi-channel'}
Goals: {json.dumps(campaign.goals, indent=2)}
Target Audience: {json.dumps(campaign.target_audience, indent=2)}

Assess:
1. Message consistency across channels
2. Brand voice alignment
3. Value proposition clarity
4. Call-to-action consistency
5. Recommendations for improvement"""
        
        try:
            consistency_text = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.4,
                max_tokens=1500
            )
            
            return {
                'assessment': consistency_text,
                'is_consistent': 'consistent' in consistency_text.lower() or 'aligned' in consistency_text.lower(),
                'recommendations': self._extract_recommendations(consistency_text)
            }
        except Exception as e:
            return {'error': str(e), 'is_consistent': True}
    
    def _check_campaign_timing(self, campaign: Campaign) -> Dict:
        """Check campaign timing and scheduling"""
        timing_issues = []
        
        if campaign.start_date and campaign.end_date:
            if campaign.end_date < campaign.start_date:
                timing_issues.append("End date is before start date")
            
            duration = (campaign.end_date - campaign.start_date).days
            if duration < 0:
                timing_issues.append("Invalid campaign duration")
        
        if campaign.status == 'active' and not campaign.start_date:
            timing_issues.append("Active campaign missing start date")
        
        return {
            'start_date': campaign.start_date.isoformat() if campaign.start_date else None,
            'end_date': campaign.end_date.isoformat() if campaign.end_date else None,
            'issues': timing_issues,
            'is_on_schedule': len(timing_issues) == 0
        }
    
    def _generate_optimization_plan(self, campaign: Campaign, performance: Dict,
                                    context: Optional[Dict]) -> Dict:
        """Generate optimization recommendations"""
        prompt = f"""Optimize this campaign based on current performance:

Campaign: {campaign.name}
Channels: {', '.join(campaign.channels) if campaign.channels else 'Multi-channel'}
Current Performance:
- Impressions: {performance.get('total_impressions', 0):,.0f}
- Clicks: {performance.get('total_clicks', 0):,.0f}
- Conversions: {performance.get('total_conversions', 0):,.0f}
- CTR: {performance.get('ctr', 0):.2f}%
- Conversion Rate: {performance.get('conversion_rate', 0):.2f}%
- ROI: {performance.get('roi', 'N/A')}
- Spend: ${performance.get('spend', 0):,.2f} / Budget: ${performance.get('budget', 0):,.2f}

Provide optimization recommendations:
1. Performance improvements by channel
2. Budget reallocation suggestions
3. Targeting optimizations
4. Creative and messaging improvements
5. Timing and scheduling optimizations
6. A/B testing opportunities
7. Priority actions with expected impact"""
        
        try:
            optimization_text = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.5,
                max_tokens=2000
            )
            
            return {
                'optimization_plan': optimization_text,
                'recommendations': self._extract_recommendations(optimization_text),
                'priority_actions': self._extract_priority_actions(optimization_text)
            }
        except Exception as e:
            return {'error': str(e), 'recommendations': []}
    
    def _generate_campaign_schedule(self, campaign: Campaign,
                                   schedule_data: Optional[Dict]) -> Dict:
        """Generate campaign schedule"""
        prompt = f"""Create a detailed schedule for this campaign:

Campaign: {campaign.name}
Channels: {', '.join(campaign.channels) if campaign.channels else 'Multi-channel'}
Start Date: {schedule_data.get('start_date') if schedule_data else 'Not set'}
End Date: {schedule_data.get('end_date') if schedule_data else 'Not set'}

Create a schedule that includes:
1. Pre-launch activities (by date)
2. Channel launch sequence and timing
3. Ongoing activities and frequency
4. Key milestones and deadlines
5. Post-launch activities
6. Reporting and review dates

Ensure all channels are properly coordinated and timed."""
        
        try:
            schedule_text = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.5,
                max_tokens=2000
            )
            
            return {
                'schedule': schedule_text,
                'timeline': self._extract_timeline(schedule_text),
                'milestones': self._extract_milestones(schedule_text)
            }
        except Exception as e:
            return {'error': str(e), 'schedule': 'Error generating schedule'}
    
    def _extract_timeline(self, text: str) -> List[Dict]:
        """Extract timeline from schedule text"""
        timeline = []
        lines = text.split('\n')
        for line in lines:
            if any(keyword in line.lower() for keyword in ['day', 'week', 'date', 'launch', 'phase']):
                if len(line.strip()) > 15:
                    timeline.append({'event': line.strip()})
        return timeline[:10]  # Top 10 timeline items
    
    def _extract_milestones(self, text: str) -> List[str]:
        """Extract milestones from schedule text"""
        milestones = []
        lines = text.split('\n')
        for line in lines:
            if 'milestone' in line.lower() or 'deadline' in line.lower():
                if len(line.strip()) > 15:
                    milestones.append(line.strip())
        return milestones[:5]  # Top 5 milestones


"""
Proactive Notification Agent
Monitors performance and market signals to proactively alert stakeholders 
about anomalies, opportunities, or required actions.
"""

from .marketing_base_agent import MarketingBaseAgent
from typing import Dict, Optional, List
from marketing_agent.models import (
    Campaign, Lead, EmailSendHistory, CampaignPerformance,
    MarketingNotification, NotificationRule, EmailSequence
)
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime, timedelta
from django.db.models import Count, Sum, Avg, Q
import json
import logging

logger = logging.getLogger(__name__)


class ProactiveNotificationAgent(MarketingBaseAgent):
    """
    Proactive Notification Agent
    
    This agent:
    - Monitors campaign performance continuously
    - Detects anomalies and issues
    - Identifies opportunities
    - Sends proactive alerts to stakeholders
    - Provides actionable recommendations
    
    In simple words:
    "AI that warns us early if something is going wrong or if there's a new opportunity."
    """
    
    def __init__(self):
        super().__init__()
        self.system_prompt = """You are a Proactive Notification Agent for a marketing system.
        Your role is to analyze campaign performance data and identify:
        1. Performance issues and anomalies
        2. Opportunities for optimization
        3. Budget concerns
        4. Milestones and achievements
        5. Actionable recommendations
        
        You provide clear, actionable alerts that help stakeholders make informed decisions.
        Always be specific with metrics and provide context for your recommendations."""
    
    def process(self, action: str, user_id: int, campaign_id: Optional[int] = None,
                context: Optional[Dict] = None) -> Dict:
        """
        Main entry point - handles various monitoring actions
        
        Args:
            action (str): Action to perform (monitor, check_campaign, analyze_all)
            user_id (int): User ID for notifications
            campaign_id (int): Optional campaign ID to monitor
            context (Dict): Additional context
            
        Returns:
            Dict: Monitoring results with notifications
        """
        self.log_action(f"Processing notification action: {action}", {
            "user_id": user_id,
            "campaign_id": campaign_id
        })
        
        if action == 'monitor':
            return self.monitor_all_campaigns(user_id)
        elif action == 'check_campaign':
            if not campaign_id:
                return {'success': False, 'error': 'campaign_id is required for check_campaign'}
            return self.check_campaign(user_id, campaign_id)
        elif action == 'analyze_all':
            return self.analyze_all_campaigns(user_id)
        else:
            return {
                'success': False,
                'error': f'Unknown action: {action}. Supported actions: monitor, check_campaign, analyze_all'
            }
    
    def monitor_all_campaigns(self, user_id: int) -> Dict:
        """
        Monitor all active campaigns for the user
        
        Args:
            user_id (int): User ID
            
        Returns:
            Dict: Monitoring results
        """
        try:
            user = User.objects.get(id=user_id)
            campaigns = Campaign.objects.filter(owner=user, status__in=['active', 'scheduled'])
            
            total_notifications_count = 0
            issues_found = []
            opportunities_found = []
            all_notifications_data = []
            
            for campaign in campaigns:
                result = self.check_campaign(user_id, campaign.id)
                if result.get('success'):
                    # Sum up notification counts from each campaign (already counted correctly in check_campaign)
                    campaign_notification_count = result.get('notifications_created', 0)
                    total_notifications_count += campaign_notification_count
                    
                    # Collect notification data (already serialized in check_campaign)
                    campaign_notifications = result.get('notifications', [])
                    all_notifications_data.extend(campaign_notifications)
                    
                    issues_found.extend(result.get('issues', []))
                    opportunities_found.extend(result.get('opportunities', []))
            
            return {
                'success': True,
                'campaigns_monitored': campaigns.count(),
                'notifications_created': total_notifications_count,  # Sum of counts from all campaigns
                'issues_found': len(issues_found),
                'opportunities_found': len(opportunities_found),
                'notifications': all_notifications_data,
                'issues': issues_found,
                'opportunities': opportunities_found,
                'message': f'Monitored {campaigns.count()} campaigns'
            }
        except User.DoesNotExist:
            return {'success': False, 'error': 'User not found'}
        except Exception as e:
            self.log_action("Error monitoring campaigns", {"error": str(e)})
            return {'success': False, 'error': str(e)}
    
    def check_campaign(self, user_id: int, campaign_id: int) -> Dict:
        """
        Check a specific campaign for issues and opportunities
        
        Args:
            user_id (int): User ID
            campaign_id (int): Campaign ID
            
        Returns:
            Dict: Check results with notifications
        """
        try:
            user = User.objects.get(id=user_id)
            campaign = Campaign.objects.get(id=campaign_id, owner=user)
            
            notifications_created = []
            issues = []
            opportunities = []
            
            # Check performance metrics
            perf_result = self._check_performance_metrics(campaign, user)
            if perf_result:
                notifications_created.extend(perf_result.get('notifications', []))
                issues.extend(perf_result.get('issues', []))
                opportunities.extend(perf_result.get('opportunities', []))
            
            # Check budget
            budget_result = self._check_budget(campaign, user)
            if budget_result:
                notifications_created.extend(budget_result.get('notifications', []))
                issues.extend(budget_result.get('issues', []))
            
            # Check email delivery
            delivery_result = self._check_email_delivery(campaign, user)
            if delivery_result:
                notifications_created.extend(delivery_result.get('notifications', []))
                issues.extend(delivery_result.get('issues', []))
            
            # Check milestones
            milestone_result = self._check_milestones(campaign, user)
            if milestone_result:
                notifications_created.extend(milestone_result.get('notifications', []))
                opportunities.extend(milestone_result.get('opportunities', []))
            
            # Check anomalies
            anomaly_result = self._check_anomalies(campaign, user)
            if anomaly_result:
                notifications_created.extend(anomaly_result.get('notifications', []))
                issues.extend(anomaly_result.get('issues', []))
            
            # Check campaign setup and actionable recommendations
            setup_result = self._check_campaign_setup(campaign, user)
            if setup_result:
                notifications_created.extend(setup_result.get('notifications', []))
                issues.extend(setup_result.get('issues', []))
            
            # Check for actionable recommendations
            recommendations_result = self._check_actionable_recommendations(campaign, user)
            if recommendations_result:
                notifications_created.extend(recommendations_result.get('notifications', []))
                opportunities.extend(recommendations_result.get('opportunities', []))
            
            # Filter out None values (duplicates that weren't created) and count actual notifications
            actual_notifications = [n for n in notifications_created if n is not None and hasattr(n, 'id')]
            
            # Count actual notifications created (they're already saved in database)
            notification_count = len(actual_notifications)
            
            # Convert notification objects to serializable format for JSON response
            notifications_data = []
            for notif in actual_notifications:
                if hasattr(notif, 'id'):  # It's a MarketingNotification object
                    notifications_data.append({
                        'id': notif.id,
                        'title': notif.title,
                        'message': notif.message,
                        'notification_type': notif.notification_type,
                        'priority': notif.priority,
                        'created_at': notif.created_at.isoformat() if hasattr(notif.created_at, 'isoformat') else str(notif.created_at)
                    })
            
            return {
                'success': True,
                'campaign_id': campaign_id,
                'campaign_name': campaign.name,
                'notifications_created': notification_count,  # Count of actual notifications created
                'issues_found': len(issues),
                'opportunities_found': len(opportunities),
                'notifications': notifications_data,  # Return serializable data
                'issues': issues,
                'opportunities': opportunities
            }
        except User.DoesNotExist:
            return {'success': False, 'error': 'User not found'}
        except Campaign.DoesNotExist:
            return {'success': False, 'error': 'Campaign not found'}
        except Exception as e:
            self.log_action("Error checking campaign", {"error": str(e)})
            return {'success': False, 'error': str(e)}
    
    def analyze_all_campaigns(self, user_id: int) -> Dict:
        """
        Comprehensive analysis of all campaigns
        
        Args:
            user_id (int): User ID
            
        Returns:
            Dict: Analysis results
        """
        return self.monitor_all_campaigns(user_id)
    
    def _check_performance_metrics(self, campaign: Campaign, user: User) -> Optional[Dict]:
        """Check campaign performance metrics for issues and opportunities"""
        notifications = []
        issues = []
        opportunities = []
        
        # Get email statistics
        email_sends = EmailSendHistory.objects.filter(campaign=campaign)
        total_sent = email_sends.count()
        
        if total_sent == 0:
            return None
        
        emails_opened = email_sends.filter(status__in=['opened', 'clicked']).count()
        emails_clicked = email_sends.filter(status='clicked').count()
        emails_bounced = email_sends.filter(status='bounced').count()
        emails_failed = email_sends.filter(status='failed').count()
        
        open_rate = (emails_opened / total_sent * 100) if total_sent > 0 else 0
        click_rate = (emails_clicked / total_sent * 100) if total_sent > 0 else 0
        bounce_rate = (emails_bounced / total_sent * 100) if total_sent > 0 else 0
        failure_rate = (emails_failed / total_sent * 100) if total_sent > 0 else 0
        
        # Check for low open rate (alert if < 15%)
        if open_rate < 15 and total_sent >= 10:
            notification = self._create_notification(
                user=user,
                campaign=campaign,
                notification_type='performance_alert',
                priority='high',
                title=f'Low Open Rate Alert: {campaign.name}',
                message=f'Open rate is {open_rate:.1f}% (below 15% threshold). Consider reviewing subject lines and send times.',
                action_required=True,
                action_url=f'/marketing/campaigns/{campaign.id}/',
                metadata={
                    'metric': 'open_rate',
                    'value': open_rate,
                    'threshold': 15,
                    'total_sent': total_sent
                }
            )
            if notification:  # Only add if notification was actually created (not duplicate)
                notifications.append(notification)
                issues.append({
                    'type': 'low_open_rate',
                    'metric': open_rate,
                    'threshold': 15
                })
        
        # Check for high bounce rate (alert if > 5%)
        if bounce_rate > 5:
            notification = self._create_notification(
                user=user,
                campaign=campaign,
                notification_type='email_delivery',
                priority='high',
                title=f'High Bounce Rate Alert: {campaign.name}',
                message=f'Bounce rate is {bounce_rate:.1f}% (above 5% threshold). Check email list quality and sender reputation.',
                action_required=True,
                action_url=f'/marketing/campaigns/{campaign.id}/',
                metadata={
                    'metric': 'bounce_rate',
                    'value': bounce_rate,
                    'threshold': 5,
                    'total_sent': total_sent
                }
            )
            if notification:  # Only add if notification was actually created
                notifications.append(notification)
                issues.append({
                    'type': 'high_bounce_rate',
                    'metric': bounce_rate,
                    'threshold': 5
                })
        
        # Check for high failure rate
        if failure_rate > 2:
            notification = self._create_notification(
                user=user,
                campaign=campaign,
                notification_type='email_delivery',
                priority='critical',
                title=f'Email Delivery Failures: {campaign.name}',
                message=f'Email failure rate is {failure_rate:.1f}% (above 2% threshold). Immediate attention required.',
                action_required=True,
                action_url=f'/marketing/campaigns/{campaign.id}/',
                metadata={
                    'metric': 'failure_rate',
                    'value': failure_rate,
                    'threshold': 2,
                    'total_sent': total_sent
                }
            )
            if notification:
                notifications.append(notification)
                issues.append({
                    'type': 'high_failure_rate',
                    'metric': failure_rate,
                    'threshold': 2
                })
        
        # Check for opportunities (high engagement)
        if open_rate > 30 and total_sent >= 20:
            notification = self._create_notification(
                user=user,
                campaign=campaign,
                notification_type='opportunity',
                priority='low',
                title=f'High Engagement Opportunity: {campaign.name}',
                message=f'Excellent open rate of {open_rate:.1f}%! Consider scaling this campaign or applying similar strategies to other campaigns.',
                action_required=False,
                action_url=f'/marketing/campaigns/{campaign.id}/',
                metadata={
                    'metric': 'open_rate',
                    'value': open_rate,
                    'threshold': 30,
                    'total_sent': total_sent
                }
            )
            if notification:
                notifications.append(notification)
                opportunities.append({
                    'type': 'high_engagement',
                    'metric': open_rate,
                    'threshold': 30
                })
        
        if click_rate > 5 and total_sent >= 20:
            notification = self._create_notification(
                user=user,
                campaign=campaign,
                notification_type='opportunity',
                priority='low',
                title=f'High Click-Through Rate: {campaign.name}',
                message=f'Strong click-through rate of {click_rate:.1f}%! Consider increasing email frequency or expanding this campaign.',
                action_required=False,
                action_url=f'/marketing/campaigns/{campaign.id}/',
                metadata={
                    'metric': 'click_rate',
                    'value': click_rate,
                    'threshold': 5,
                    'total_sent': total_sent
                }
            )
            if notification:
                notifications.append(notification)
                opportunities.append({
                    'type': 'high_click_rate',
                    'metric': click_rate,
                    'threshold': 5
                })
        
        if notifications:
            return {
                'notifications': notifications,
                'issues': issues,
                'opportunities': opportunities
            }
        return None
    
    def _check_budget(self, campaign: Campaign, user: User) -> Optional[Dict]:
        """Check budget utilization"""
        notifications = []
        issues = []
        
        if campaign.budget <= 0:
            return None
        
        budget_utilization = (float(campaign.actual_spend) / float(campaign.budget)) * 100
        
        # Alert if budget is 80% utilized
        if budget_utilization >= 80 and budget_utilization < 100:
            notification = self._create_notification(
                user=user,
                campaign=campaign,
                notification_type='budget',
                priority='medium',
                title=f'Budget Alert: {campaign.name}',
                message=f'Budget is {budget_utilization:.1f}% utilized (${campaign.actual_spend:.2f} of ${campaign.budget:.2f}). Consider reviewing spend.',
                action_required=True,
                action_url=f'/marketing/campaigns/{campaign.id}/',
                metadata={
                    'budget': float(campaign.budget),
                    'actual_spend': float(campaign.actual_spend),
                    'utilization': budget_utilization
                }
            )
            if notification:
                notifications.append(notification)
                issues.append({
                    'type': 'budget_warning',
                    'utilization': budget_utilization
                })
        
        # Critical alert if budget exceeded
        if budget_utilization >= 100:
            notification = self._create_notification(
                user=user,
                campaign=campaign,
                notification_type='budget',
                priority='critical',
                title=f'Budget Exceeded: {campaign.name}',
                message=f'Budget has been exceeded! Actual spend: ${campaign.actual_spend:.2f} vs Budget: ${campaign.budget:.2f}. Immediate action required.',
                action_required=True,
                action_url=f'/marketing/campaigns/{campaign.id}/',
                metadata={
                    'budget': float(campaign.budget),
                    'actual_spend': float(campaign.actual_spend),
                    'utilization': budget_utilization
                }
            )
            if notification:
                notifications.append(notification)
                issues.append({
                    'type': 'budget_exceeded',
                    'utilization': budget_utilization
                })
        
        if notifications:
            return {
                'notifications': notifications,
                'issues': issues
            }
        return None
    
    def _check_email_delivery(self, campaign: Campaign, user: User) -> Optional[Dict]:
        """Check email delivery issues"""
        notifications = []
        issues = []
        
        # Check recent email sends (last 24 hours)
        recent_cutoff = timezone.now() - timedelta(hours=24)
        recent_emails = EmailSendHistory.objects.filter(
            campaign=campaign,
            sent_at__gte=recent_cutoff
        )
        
        if recent_emails.count() == 0:
            return None
        
        failed_emails = recent_emails.filter(status__in=['failed', 'bounced'])
        failure_count = failed_emails.count()
        failure_rate = (failure_count / recent_emails.count() * 100) if recent_emails.count() > 0 else 0
        
        # Alert if high failure rate in last 24 hours
        if failure_rate > 10 and recent_emails.count() >= 5:
            notification = self._create_notification(
                user=user,
                campaign=campaign,
                notification_type='email_delivery',
                priority='high',
                title=f'Email Delivery Issues: {campaign.name}',
                message=f'High email delivery failure rate ({failure_rate:.1f}%) in the last 24 hours. {failure_count} out of {recent_emails.count()} emails failed.',
                action_required=True,
                action_url=f'/marketing/campaigns/{campaign.id}/',
                metadata={
                    'failure_rate': failure_rate,
                    'failure_count': failure_count,
                    'total_recent': recent_emails.count(),
                    'timeframe': '24_hours'
                }
            )
            if notification:
                notifications.append(notification)
                issues.append({
                    'type': 'delivery_issues',
                    'failure_rate': failure_rate
                })
        
        if notifications:
            return {
                'notifications': notifications,
                'issues': issues
            }
        return None
    
    def _check_milestones(self, campaign: Campaign, user: User) -> Optional[Dict]:
        """Check if campaign milestones are reached"""
        notifications = []
        opportunities = []
        
        # Check lead targets
        if campaign.target_leads:
            actual_leads = campaign.leads.count()
            if actual_leads >= campaign.target_leads:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='milestone',
                    priority='low',
                    title=f'Milestone Reached: {campaign.name}',
                    message=f'Lead target achieved! {actual_leads} leads generated (target: {campaign.target_leads}).',
                    action_required=False,
                    action_url=f'/marketing/campaigns/{campaign.id}/',
                    metadata={
                        'milestone': 'lead_target',
                        'actual': actual_leads,
                        'target': campaign.target_leads
                    }
                )
                if notification:
                    notifications.append(notification)
                    opportunities.append({
                        'type': 'lead_milestone',
                        'actual': actual_leads,
                        'target': campaign.target_leads
                    })
        
        # Check revenue targets
        if campaign.target_revenue:
            # Calculate actual revenue from performance metrics
            revenue_metrics = CampaignPerformance.objects.filter(
                campaign=campaign,
                metric_name='revenue'
            ).aggregate(total=Sum('metric_value'))['total'] or 0
            
            if revenue_metrics >= float(campaign.target_revenue):
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='milestone',
                    priority='low',
                    title=f'Revenue Milestone Reached: {campaign.name}',
                    message=f'Revenue target achieved! ${revenue_metrics:.2f} generated (target: ${campaign.target_revenue:.2f}).',
                    action_required=False,
                    action_url=f'/marketing/campaigns/{campaign.id}/',
                    metadata={
                        'milestone': 'revenue_target',
                        'actual': revenue_metrics,
                        'target': float(campaign.target_revenue)
                    }
                )
                if notification:
                    notifications.append(notification)
                    opportunities.append({
                        'type': 'revenue_milestone',
                        'actual': revenue_metrics,
                        'target': float(campaign.target_revenue)
                    })
        
        if notifications:
            return {
                'notifications': notifications,
                'opportunities': opportunities
            }
        return None
    
    def _check_anomalies(self, campaign: Campaign, user: User) -> Optional[Dict]:
        """Check for performance anomalies"""
        notifications = []
        issues = []
        
        # Get email statistics for last 7 days vs previous 7 days
        now = timezone.now()
        last_7_days = now - timedelta(days=7)
        previous_7_days_start = last_7_days - timedelta(days=7)
        
        recent_emails = EmailSendHistory.objects.filter(
            campaign=campaign,
            sent_at__gte=last_7_days
        )
        previous_emails = EmailSendHistory.objects.filter(
            campaign=campaign,
            sent_at__gte=previous_7_days_start,
            sent_at__lt=last_7_days
        )
        
        if recent_emails.count() < 10 or previous_emails.count() < 10:
            return None
        
        # Calculate open rates
        recent_opened = recent_emails.filter(status__in=['opened', 'clicked']).count()
        previous_opened = previous_emails.filter(status__in=['opened', 'clicked']).count()
        
        recent_open_rate = (recent_opened / recent_emails.count() * 100) if recent_emails.count() > 0 else 0
        previous_open_rate = (previous_opened / previous_emails.count() * 100) if previous_emails.count() > 0 else 0
        
        # Detect significant drop (> 30% decrease)
        if previous_open_rate > 0 and recent_open_rate < (previous_open_rate * 0.7):
            drop_percentage = ((previous_open_rate - recent_open_rate) / previous_open_rate) * 100
            notification = self._create_notification(
                user=user,
                campaign=campaign,
                notification_type='anomaly',
                priority='high',
                title=f'Performance Anomaly Detected: {campaign.name}',
                message=f'Open rate dropped by {drop_percentage:.1f}% compared to previous week ({recent_open_rate:.1f}% vs {previous_open_rate:.1f}%). Investigate potential issues.',
                action_required=True,
                action_url=f'/marketing/campaigns/{campaign.id}/',
                metadata={
                    'metric': 'open_rate',
                    'recent': recent_open_rate,
                    'previous': previous_open_rate,
                    'change': drop_percentage
                }
            )
            if notification:
                notifications.append(notification)
                issues.append({
                    'type': 'performance_drop',
                    'metric': 'open_rate',
                    'change': drop_percentage
                })
        
        if notifications:
            return {
                'notifications': notifications,
                'issues': issues
            }
        return None
    
    def _check_campaign_setup(self, campaign: Campaign, user: User) -> Optional[Dict]:
        """Check campaign setup and provide actionable recommendations"""
        notifications = []
        issues = []
        
        # Check PAUSED campaigns - provide actionable steps
        if campaign.status == 'paused':
            leads_count = campaign.leads.count()
            sequences = EmailSequence.objects.filter(campaign=campaign)
            emails_sent = EmailSendHistory.objects.filter(campaign=campaign).count()
            
            # If paused with no leads
            if leads_count == 0:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='campaign_status',
                    priority='high',
                    title=f'👥 Generate Leads: {campaign.name}',
                    message=f'Campaign "{campaign.name}" is paused and has no leads! Generate or upload leads first, then create email sequences, and finally launch the campaign.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/leads/upload/',
                    metadata={
                        'action': 'generate_leads',
                        'status': 'paused',
                        'leads_count': 0
                    }
                )
                if notification:
                    notifications.append(notification)
                    issues.append({'type': 'paused_no_leads'})
            
            # If paused with leads but no sequences
            elif leads_count > 0 and sequences.count() == 0:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='campaign_status',
                    priority='high',
                    title=f'📧 Create Email Sequences: {campaign.name}',
                    message=f'Campaign "{campaign.name}" is paused with {leads_count} leads but no email sequences! Create follow-up email sequences, then launch the campaign.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/sequences/',
                    metadata={
                        'action': 'create_sequences_for_paused',
                        'status': 'paused',
                        'leads_count': leads_count
                    }
                )
                if notification:
                    notifications.append(notification)
                    issues.append({'type': 'paused_no_sequences'})
            
            # If paused with leads and sequences - ready to launch
            elif leads_count > 0 and sequences.count() > 0:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='campaign_status',
                    priority='medium',
                    title=f'🚀 Launch Campaign: {campaign.name}',
                    message=f'Campaign "{campaign.name}" is paused but ready to launch! It has {leads_count} leads and {sequences.count()} email sequence(s). Activate the campaign to start sending emails.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/edit/',
                    metadata={
                        'action': 'launch_paused_campaign',
                        'status': 'paused',
                        'leads_count': leads_count,
                        'sequences_count': sequences.count()
                    }
                )
                if notification:
                    notifications.append(notification)
                    issues.append({'type': 'paused_ready_to_launch'})
        
        # Check SCHEDULED campaigns
        if campaign.status == 'scheduled':
            leads_count = campaign.leads.count()
            sequences = EmailSequence.objects.filter(campaign=campaign)
            
            # Scheduled with no leads
            if leads_count == 0:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='campaign_status',
                    priority='high',
                    title=f'👥 Generate Leads for Scheduled Campaign: {campaign.name}',
                    message=f'Campaign "{campaign.name}" is scheduled but has no leads! Generate or upload leads first, then create email sequences before the start date.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/leads/upload/',
                    metadata={
                        'action': 'generate_leads_for_scheduled',
                        'status': 'scheduled',
                        'leads_count': 0,
                        'start_date': campaign.start_date.isoformat() if campaign.start_date else None
                    }
                )
                if notification:
                    notifications.append(notification)
                    issues.append({'type': 'scheduled_no_leads'})
            
            # Scheduled with leads but no sequences
            elif leads_count > 0 and sequences.count() == 0:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='campaign_status',
                    priority='high',
                    title=f'📧 Create Email Sequences: {campaign.name}',
                    message=f'Campaign "{campaign.name}" is scheduled with {leads_count} leads but no email sequences! Create follow-up email sequences before the campaign starts.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/sequences/',
                    metadata={
                        'action': 'create_sequences_for_scheduled',
                        'status': 'scheduled',
                        'leads_count': leads_count,
                        'start_date': campaign.start_date.isoformat() if campaign.start_date else None
                    }
                )
                if notification:
                    notifications.append(notification)
                    issues.append({'type': 'scheduled_no_sequences'})
        
        # Check if campaign is in draft but ready to activate
        if campaign.status == 'draft':
            # Check if campaign has required setup
            has_leads = campaign.leads.count() > 0
            has_budget = float(campaign.budget) > 0
            has_dates = campaign.start_date is not None
            
            if has_leads and has_budget and has_dates:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='campaign_status',
                    priority='medium',
                    title=f'🚀 Activate Campaign: {campaign.name}',
                    message=f'Your campaign "{campaign.name}" is ready to activate! It has {campaign.leads.count()} leads, budget set, and dates configured. Click to activate and start sending emails.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/edit/',
                    metadata={
                        'action': 'activate_campaign',
                        'leads_count': campaign.leads.count(),
                        'has_budget': has_budget,
                        'has_dates': has_dates
                    }
                )
                if notification:
                    notifications.append(notification)
                    issues.append({
                        'type': 'campaign_ready_to_activate',
                        'campaign_id': campaign.id
                    })
        
        # Check if campaign is scheduled but start date is in the past
        if campaign.status == 'scheduled' and campaign.start_date:
            if campaign.start_date < timezone.now().date():
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='campaign_status',
                    priority='high',
                    title=f'⏰ Campaign Start Date Passed: {campaign.name}',
                    message=f'Campaign "{campaign.name}" start date ({campaign.start_date}) has passed but campaign is still scheduled. Activate it now to start sending emails.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/edit/',
                    metadata={
                        'action': 'activate_overdue_campaign',
                        'start_date': campaign.start_date.isoformat()
                    }
                )
                if notification:
                    notifications.append(notification)
                    issues.append({
                        'type': 'campaign_start_date_passed',
                        'start_date': campaign.start_date.isoformat()
                    })
        
        # Check if campaign has no email sequences
        sequences = EmailSequence.objects.filter(campaign=campaign)
        if sequences.count() == 0 and campaign.status in ['active', 'scheduled']:
            notification = self._create_notification(
                user=user,
                campaign=campaign,
                notification_type='campaign_status',
                priority='high',
                title=f'📧 Create Email Sequences: {campaign.name}',
                message=f'Campaign "{campaign.name}" has no email sequences set up! Create follow-up email sequences to engage with your {campaign.leads.count()} leads. Click to create sequences.',
                action_required=True,
                action_url=f'/marketing/campaigns/{campaign.id}/sequences/',
                metadata={
                    'action': 'create_email_sequences',
                    'leads_count': campaign.leads.count(),
                    'sequences_count': 0
                }
            )
            if notification:
                notifications.append(notification)
                issues.append({
                    'type': 'no_email_sequences',
                    'leads_count': campaign.leads.count()
                })
        
        # Check ACTIVE campaigns - comprehensive analysis
        if campaign.status == 'active':
            leads_count = campaign.leads.count()
            sequences = EmailSequence.objects.filter(campaign=campaign)
            emails_sent = EmailSendHistory.objects.filter(campaign=campaign).count()
            
            # Active campaign with no leads
            if leads_count == 0:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='campaign_status',
                    priority='high',
                    title=f'👥 Increase Leads: {campaign.name}',
                    message=f'Campaign "{campaign.name}" is active but has no leads! Generate or upload more leads to start engaging with your target audience and improve campaign performance.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/leads/upload/',
                    metadata={
                        'action': 'increase_leads_for_active',
                        'status': 'active',
                        'leads_count': 0
                    }
                )
                if notification:
                    notifications.append(notification)
                    issues.append({'type': 'active_no_leads'})
            
            # Active campaign with leads but no sequences
            elif leads_count > 0 and sequences.count() == 0:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='campaign_status',
                    priority='high',
                    title=f'📧 Create Email Sequences: {campaign.name}',
                    message=f'Campaign "{campaign.name}" is active with {leads_count} leads but no email sequences! Create follow-up email sequences to engage with your leads and improve conversion rates.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/sequences/',
                    metadata={
                        'action': 'create_sequences_for_active',
                        'status': 'active',
                        'leads_count': leads_count
                    }
                )
                if notification:
                    notifications.append(notification)
                    issues.append({'type': 'active_no_sequences'})
            
            # Active campaign with leads and sequences but no emails sent
            elif leads_count > 0 and sequences.count() > 0 and emails_sent == 0:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='campaign_status',
                    priority='high',
                    title=f'📬 Start Sending Emails: {campaign.name}',
                    message=f'Campaign "{campaign.name}" is active with {leads_count} leads and {sequences.count()} sequence(s) but no emails have been sent yet! Trigger email sequences to start engaging with your leads.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/',
                    metadata={
                        'action': 'start_sending_emails',
                        'leads_count': leads_count,
                        'sequences_count': sequences.count(),
                        'emails_sent': 0
                    }
                )
                if notification:
                    notifications.append(notification)
                    issues.append({
                        'type': 'no_emails_sent',
                        'leads_count': leads_count
                    })
            
            # Active campaign with low lead count (needs more leads)
            elif leads_count > 0 and leads_count < 10 and emails_sent > 0:
                # Check if campaign is performing well but needs more leads
                email_sends = EmailSendHistory.objects.filter(campaign=campaign)
                emails_opened = email_sends.filter(status__in=['opened', 'clicked']).count()
                open_rate = (emails_opened / emails_sent * 100) if emails_sent > 0 else 0
                
                if open_rate >= 20:  # Good engagement, can scale
                    notification = self._create_notification(
                        user=user,
                        campaign=campaign,
                        notification_type='opportunity',
                        priority='medium',
                        title=f'👥 Increase Lead Count: {campaign.name}',
                        message=f'Campaign "{campaign.name}" is performing well ({open_rate:.1f}% open rate) but only has {leads_count} leads. Consider adding more leads to scale the campaign and increase conversions.',
                        action_required=False,
                        action_url=f'/marketing/campaigns/{campaign.id}/leads/upload/',
                        metadata={
                            'action': 'increase_leads_scale',
                            'status': 'active',
                            'leads_count': leads_count,
                            'open_rate': open_rate
                        }
                    )
                    if notification:
                        notifications.append(notification)
                        opportunities.append({
                            'type': 'increase_leads_scale',
                            'leads_count': leads_count,
                            'open_rate': open_rate
                        })
        
        if notifications:
            return {
                'notifications': notifications,
                'issues': issues
            }
        return None
    
    def _check_actionable_recommendations(self, campaign: Campaign, user: User) -> Optional[Dict]:
        """Check for actionable recommendations to improve campaign"""
        notifications = []
        opportunities = []
        
        # Get email statistics
        email_sends = EmailSendHistory.objects.filter(campaign=campaign)
        total_sent = email_sends.count()
        
        # For active campaigns, check even if no emails sent yet
        if total_sent == 0:
            # Only skip if campaign is not active (other statuses need emails to analyze)
            if campaign.status != 'active':
                return None
            # For active campaigns with no emails, provide setup recommendations
            leads_count = campaign.leads.count()
            sequences = EmailSequence.objects.filter(campaign=campaign)
            
            if leads_count == 0:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='engagement',
                    priority='high',
                    title=f'👥 Add Leads to Active Campaign: {campaign.name}',
                    message=f'Campaign "{campaign.name}" is active but has no leads and no emails sent. Add leads first, then create email sequences to start the campaign.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/leads/upload/',
                    metadata={
                        'action': 'add_leads_to_active',
                        'leads_count': 0,
                        'sequences_count': sequences.count()
                    }
                )
                if notification:
                    notifications.append(notification)
                    opportunities.append({
                        'type': 'add_leads_to_active',
                        'leads_count': 0
                    })
            elif sequences.count() == 0:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='engagement',
                    priority='high',
                    title=f'📧 Create Email Sequences for Active Campaign: {campaign.name}',
                    message=f'Campaign "{campaign.name}" is active with {leads_count} leads but no email sequences. Create email sequences to start sending emails to your leads.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/sequences/',
                    metadata={
                        'action': 'create_sequences_for_active_no_emails',
                        'leads_count': leads_count,
                        'sequences_count': 0
                    }
                )
                if notification:
                    notifications.append(notification)
                    opportunities.append({
                        'type': 'create_sequences_for_active_no_emails',
                        'leads_count': leads_count
                    })
            
            if notifications:
                return {
                    'notifications': notifications,
                    'opportunities': opportunities
                }
            return None
        
        emails_opened = email_sends.filter(status__in=['opened', 'clicked']).count()
        emails_clicked = email_sends.filter(status='clicked').count()
        open_rate = (emails_opened / total_sent * 100) if total_sent > 0 else 0
        click_rate = (emails_clicked / total_sent * 100) if total_sent > 0 else 0
        
        # Recommendation: Improve email content if open rate is low
        if open_rate < 20 and total_sent >= 10:
            notification = self._create_notification(
                user=user,
                campaign=campaign,
                notification_type='engagement',
                priority='medium',
                title=f'✏️ Improve Email Content: {campaign.name}',
                message=f'Open rate is {open_rate:.1f}% (below 20%). Improve your emails by: 1) Writing better subject lines, 2) Personalizing content, 3) Testing send times, 4) A/B testing different approaches.',
                action_required=True,
                action_url=f'/marketing/campaigns/{campaign.id}/email-templates/',
                metadata={
                    'action': 'improve_email_content',
                    'open_rate': open_rate,
                    'recommendations': [
                        'Write better subject lines',
                        'Personalize email content',
                        'Test different send times',
                        'A/B test email variations'
                    ]
                }
            )
            if notification:
                notifications.append(notification)
                opportunities.append({
                    'type': 'improve_email_content',
                    'open_rate': open_rate
                })
        
        # Recommendation: Optimize for clicks if open rate is good but click rate is low
        if open_rate >= 20 and click_rate < 3 and total_sent >= 10:
            notification = self._create_notification(
                user=user,
                campaign=campaign,
                notification_type='engagement',
                priority='medium',
                title=f'🎯 Optimize Call-to-Action: {campaign.name}',
                message=f'Good open rate ({open_rate:.1f}%) but low click rate ({click_rate:.1f}%). Improve CTAs by: 1) Making buttons more prominent, 2) Using action-oriented language, 3) Reducing friction, 4) Testing different CTA placements.',
                action_required=True,
                action_url=f'/marketing/campaigns/{campaign.id}/email-templates/',
                metadata={
                    'action': 'optimize_cta',
                    'open_rate': open_rate,
                    'click_rate': click_rate,
                    'recommendations': [
                        'Make CTAs more prominent',
                        'Use action-oriented language',
                        'Reduce friction in conversion',
                        'Test different CTA placements'
                    ]
                }
            )
            if notification:
                notifications.append(notification)
                opportunities.append({
                    'type': 'optimize_cta',
                    'open_rate': open_rate,
                    'click_rate': click_rate
                })
        
        # Check for follow-up email opportunities
        sequences = EmailSequence.objects.filter(campaign=campaign)
        
        # Check if campaign needs follow-up emails (leads contacted but no follow-ups)
        if sequences.count() > 0 and total_sent > 0:
            # Check if there are leads that were contacted but haven't received follow-ups
            contacted_leads = EmailSendHistory.objects.filter(
                campaign=campaign,
                status__in=['delivered', 'opened', 'clicked']
            ).values('recipient_email').distinct().count()
            
            # Check if follow-up sequences exist but haven't been triggered
            followup_sequences = sequences.filter(name__icontains='follow').count()
            if followup_sequences == 0 and contacted_leads > 0:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='engagement',
                    priority='medium',
                    title=f'🔄 Create Follow-up Email Sequences: {campaign.name}',
                    message=f'Campaign "{campaign.name}" has contacted {contacted_leads} leads but no follow-up sequences! Create follow-up email sequences to nurture leads and improve conversion rates.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/sequences/',
                    metadata={
                        'action': 'create_followup_sequences',
                        'contacted_leads': contacted_leads,
                        'current_sequences': sequences.count()
                    }
                )
                if notification:
                    notifications.append(notification)
                    opportunities.append({
                        'type': 'create_followup_sequences',
                        'contacted_leads': contacted_leads
                    })
        
        # Recommendation: Add more follow-up sequences if campaign has good engagement
        if open_rate >= 25 and sequences.count() < 3 and total_sent >= 20:
            notification = self._create_notification(
                user=user,
                campaign=campaign,
                notification_type='opportunity',
                priority='low',
                title=f'🔄 Add More Follow-up Sequences: {campaign.name}',
                message=f'Great engagement ({open_rate:.1f}% open rate)! Consider adding more follow-up email sequences to nurture leads further. You currently have {sequences.count()} sequence(s).',
                action_required=False,
                action_url=f'/marketing/campaigns/{campaign.id}/sequences/',
                metadata={
                    'action': 'add_followup_sequences',
                    'open_rate': open_rate,
                    'current_sequences': sequences.count(),
                    'recommended_sequences': 3
                }
            )
            if notification:
                notifications.append(notification)
                opportunities.append({
                    'type': 'add_followup_sequences',
                    'open_rate': open_rate
                })
        
        # Recommendation: Schedule more emails if campaign is performing well
        if open_rate >= 30 and click_rate >= 5 and campaign.status == 'active':
            recent_emails = EmailSendHistory.objects.filter(
                campaign=campaign,
                sent_at__gte=timezone.now() - timedelta(days=7)
            ).count()
            
            if recent_emails < 5:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='opportunity',
                    priority='low',
                    title=f'📅 Schedule More Emails: {campaign.name}',
                    message=f'Excellent performance! Open rate: {open_rate:.1f}%, Click rate: {click_rate:.1f}%. Only {recent_emails} emails sent in last 7 days. Consider scheduling more emails to maintain engagement.',
                    action_required=False,
                    action_url=f'/marketing/campaigns/{campaign.id}/sequences/',
                    metadata={
                        'action': 'schedule_more_emails',
                        'open_rate': open_rate,
                        'click_rate': click_rate,
                        'recent_emails': recent_emails
                    }
                )
                if notification:
                    notifications.append(notification)
                    opportunities.append({
                        'type': 'schedule_more_emails',
                        'open_rate': open_rate,
                        'click_rate': click_rate
                    })
        
        if notifications:
            return {
                'notifications': notifications,
                'opportunities': opportunities
            }
        return None
    
    def _create_notification(self, user: User, campaign: Optional[Campaign],
                           notification_type: str, priority: str, title: str,
                           message: str, action_required: bool = False,
                           action_url: Optional[str] = None,
                           metadata: Optional[Dict] = None) -> Optional[MarketingNotification]:
        """
        Create a notification in the database
        Prevents duplicates by checking if a similar notification was created recently (last 24 hours)
        """
        from datetime import timedelta
        
        # Check for duplicate notification in last 24 hours
        recent_cutoff = timezone.now() - timedelta(hours=24)
        duplicate = MarketingNotification.objects.filter(
            user=user,
            campaign=campaign,
            notification_type=notification_type,
            title=title,
            created_at__gte=recent_cutoff
        ).first()
        
        # If duplicate exists and is unread, don't create a new one
        if duplicate and not duplicate.is_read:
            return None  # Return None to indicate no new notification was created
        
        # Create new notification
        notification = MarketingNotification.objects.create(
            user=user,
            campaign=campaign,
            notification_type=notification_type,
            priority=priority,
            title=title,
            message=message,
            action_required=action_required,
            action_url=action_url or '',
            metadata=metadata or {}
        )
        return notification
    
    def get_notifications(self, user_id: int, unread_only: bool = False,
                          notification_type: Optional[str] = None,
                          campaign_id: Optional[int] = None) -> Dict:
        """
        Get notifications for a user
        
        Args:
            user_id (int): User ID
            unread_only (bool): Only return unread notifications
            notification_type (str): Filter by notification type
            campaign_id (int): Filter by campaign
            
        Returns:
            Dict: List of notifications
        """
        try:
            notifications = MarketingNotification.objects.filter(user_id=user_id)
            
            if unread_only:
                notifications = notifications.filter(is_read=False)
            
            if notification_type:
                notifications = notifications.filter(notification_type=notification_type)
            
            if campaign_id:
                notifications = notifications.filter(campaign_id=campaign_id)
            
            notifications = notifications.order_by('-created_at')[:100]
            
            notification_list = [
                {
                    'id': n.id,
                    'notification_type': n.notification_type,
                    'priority': n.priority,
                    'title': n.title,
                    'message': n.message,
                    'action_required': n.action_required,
                    'action_url': n.action_url,
                    'is_read': n.is_read,
                    'campaign_id': n.campaign.id if n.campaign else None,
                    'campaign_name': n.campaign.name if n.campaign else None,
                    'metadata': n.metadata,
                    'created_at': n.created_at.isoformat(),
                }
                for n in notifications
            ]
            
            return {
                'success': True,
                'count': len(notification_list),
                'unread_count': MarketingNotification.objects.filter(user_id=user_id, is_read=False).count(),
                'notifications': notification_list
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


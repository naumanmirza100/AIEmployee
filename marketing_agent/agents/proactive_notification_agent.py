"""
Proactive Notification Agent
Monitors performance and market signals to proactively alert stakeholders 
about anomalies, opportunities, or required actions.
"""

from .marketing_base_agent import MarketingBaseAgent
from typing import Dict, Optional, List
from marketing_agent.models import (
    Campaign, Lead, EmailSendHistory, CampaignPerformance,
    MarketingNotification, NotificationRule, EmailSequence, Reply
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
        3. Milestones and achievements
        4. Actionable recommendations
        
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
            
            # Comprehensive checks for ALL campaigns (active, scheduled, paused, draft)
            # Check all reply types (positive, negative, neutral, objections, unsubscribe)
            # Works for any campaign that has sent emails
            all_replies_result = self._check_all_reply_types(campaign, user)
            if all_replies_result:
                notifications_created.extend(all_replies_result.get('notifications', []))
                opportunities.extend(all_replies_result.get('opportunities', []))
                issues.extend(all_replies_result.get('issues', []))
            
            # Check open/click rates and engagement metrics
            # Works for any campaign that has sent emails
            engagement_result = self._check_active_campaign_engagement(campaign, user)
            if engagement_result:
                notifications_created.extend(engagement_result.get('notifications', []))
                opportunities.extend(engagement_result.get('opportunities', []))
                issues.extend(engagement_result.get('issues', []))
            
            # Check sequence status and email sending
            # Works for all campaign statuses
            sequence_status_result = self._check_active_campaign_sequences(campaign, user)
            if sequence_status_result:
                notifications_created.extend(sequence_status_result.get('notifications', []))
                issues.extend(sequence_status_result.get('issues', []))
            
            # Check campaign progress (weekly updates, milestones)
            # Only for active campaigns (they're the ones running)
            if campaign.status == 'active':
                progress_result = self._check_campaign_progress(campaign, user)
                if progress_result:
                    notifications_created.extend(progress_result.get('notifications', []))
                    opportunities.extend(progress_result.get('opportunities', []))
            
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
        
        # Check for zero engagement: All emails sent but no replies or clicks
        if total_sent >= 10:  # Only check if significant number of emails sent
            emails_clicked = email_sends.filter(status='clicked').count()
            emails_opened = email_sends.filter(status__in=['opened', 'clicked']).count()
            
            # Check for replies (using Reply model)
            replies_count = Reply.objects.filter(campaign=campaign).count()
            
            # If no clicks AND no replies after sending multiple emails
            if emails_clicked == 0 and replies_count == 0 and total_sent >= 10:
                # Check if emails were sent at least 24 hours ago (give time for engagement)
                oldest_email = email_sends.order_by('sent_at').first()
                if oldest_email and oldest_email.sent_at:
                    hours_since_first = (timezone.now() - oldest_email.sent_at).total_seconds() / 3600
                    if hours_since_first >= 24:  # At least 24 hours since first email
                        notification = self._create_notification(
                            user=user,
                            campaign=campaign,
                            notification_type='engagement',
                            priority='high',
                            title=f'⚠️ No Engagement Detected: {campaign.name}',
                            message=f'Campaign "{campaign.name}" has sent {total_sent} emails but received ZERO clicks and ZERO replies. This indicates low engagement. Consider: 1) Improving subject lines, 2) Personalizing content, 3) Reviewing target audience, 4) Testing different send times.',
                            action_required=True,
                            action_url=f'/marketing/campaigns/{campaign.id}/',
                            metadata={
                                'action': 'no_engagement_detected',
                                'total_sent': total_sent,
                                'clicks': 0,
                                'replies': 0,
                                'opens': emails_opened,
                                'hours_since_first_email': round(hours_since_first, 1)
                            }
                        )
                        if notification:
                            notifications.append(notification)
                            issues.append({
                                'type': 'zero_engagement',
                                'total_sent': total_sent,
                                'clicks': 0,
                                'replies': 0
                            })
            
            # If emails opened but no clicks and no replies
            elif emails_opened > 0 and emails_clicked == 0 and replies_count == 0 and total_sent >= 15:
                oldest_email = email_sends.order_by('sent_at').first()
                if oldest_email and oldest_email.sent_at:
                    hours_since_first = (timezone.now() - oldest_email.sent_at).total_seconds() / 3600
                    if hours_since_first >= 48:  # At least 48 hours since first email
                        notification = self._create_notification(
                            user=user,
                            campaign=campaign,
                            notification_type='engagement',
                            priority='medium',
                            title=f'📧 Emails Opened But No Clicks/Replies: {campaign.name}',
                            message=f'Campaign "{campaign.name}" has {emails_opened} email opens but ZERO clicks and ZERO replies from {total_sent} emails sent. People are opening but not engaging. Improve: 1) Call-to-action buttons, 2) Email content relevance, 3) Offer value, 4) Follow-up sequences.',
                            action_required=True,
                            action_url=f'/marketing/campaigns/{campaign.id}/email-templates/',
                            metadata={
                                'action': 'opens_but_no_clicks_replies',
                                'total_sent': total_sent,
                                'opens': emails_opened,
                                'clicks': 0,
                                'replies': 0,
                                'hours_since_first_email': round(hours_since_first, 1)
                            }
                        )
                        if notification:
                            notifications.append(notification)
                            issues.append({
                                'type': 'opens_no_clicks_replies',
                                'opens': emails_opened,
                                'clicks': 0,
                                'replies': 0
                            })
        
        if notifications:
            return {
                'notifications': notifications,
                'issues': issues,
                'opportunities': opportunities
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
            
            # Scheduled campaign ready to launch (has leads and sequences but not launched)
            elif leads_count > 0 and sequences.count() > 0:
                # Check if start date has passed but campaign is still scheduled
                if campaign.start_date and campaign.start_date <= timezone.now().date():
                    notification = self._create_notification(
                        user=user,
                        campaign=campaign,
                        notification_type='campaign_status',
                        priority='high',
                        title=f'⏰ Scheduled Campaign Not Launched: {campaign.name}',
                        message=f'Campaign "{campaign.name}" is scheduled with start date {campaign.start_date} but has NOT been launched yet! It has {leads_count} leads and {sequences.count()} sequence(s) ready. Launch the campaign now to start sending emails.',
                        action_required=True,
                        action_url=f'/marketing/campaigns/{campaign.id}/edit/',
                        metadata={
                            'action': 'launch_scheduled_campaign',
                            'status': 'scheduled',
                            'leads_count': leads_count,
                            'sequences_count': sequences.count(),
                            'start_date': campaign.start_date.isoformat(),
                            'days_past_start': (timezone.now().date() - campaign.start_date).days
                        }
                    )
                    if notification:
                        notifications.append(notification)
                        issues.append({'type': 'scheduled_not_launched'})
                # Check if campaign is scheduled but ready to launch (start date is today or future)
                elif campaign.start_date and campaign.start_date >= timezone.now().date():
                    days_until_start = (campaign.start_date - timezone.now().date()).days
                    if days_until_start <= 1:  # Launch today or tomorrow
                        notification = self._create_notification(
                            user=user,
                            campaign=campaign,
                            notification_type='campaign_status',
                            priority='medium',
                            title=f'🚀 Campaign Ready to Launch: {campaign.name}',
                            message=f'Campaign "{campaign.name}" is scheduled to start {campaign.start_date.strftime("%B %d, %Y")} ({days_until_start} day{"s" if days_until_start != 0 else ""} away). It has {leads_count} leads and {sequences.count()} sequence(s) ready. You can launch it now or wait for the scheduled date.',
                            action_required=False,
                            action_url=f'/marketing/campaigns/{campaign.id}/edit/',
                            metadata={
                                'action': 'campaign_ready_to_launch',
                                'status': 'scheduled',
                                'leads_count': leads_count,
                                'sequences_count': sequences.count(),
                                'start_date': campaign.start_date.isoformat(),
                                'days_until_start': days_until_start
                            }
                        )
                        if notification:
                            notifications.append(notification)
                            issues.append({'type': 'scheduled_ready_to_launch'})
        
        # Check if campaign is in draft but ready to activate
        if campaign.status == 'draft':
            # Check if campaign has required setup
            has_leads = campaign.leads.count() > 0
            has_dates = campaign.start_date is not None
            
            if has_leads and has_dates:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='campaign_status',
                    priority='medium',
                    title=f'🚀 Activate Campaign: {campaign.name}',
                    message=f'Your campaign "{campaign.name}" is ready to activate! It has {campaign.leads.count()} leads and dates configured. Click to activate and start sending emails.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/edit/',
                    metadata={
                        'action': 'activate_campaign',
                        'leads_count': campaign.leads.count(),
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
    
    def _check_all_reply_types(self, campaign: Campaign, user: User) -> Optional[Dict]:
        """Check for ALL types of replies (positive, negative, neutral, objections, unsubscribe)"""
        notifications = []
        opportunities = []
        issues = []
        
        # Get recent replies (last 7 days)
        recent_cutoff = timezone.now() - timedelta(days=7)
        recent_replies = Reply.objects.filter(
            campaign=campaign,
            replied_at__gte=recent_cutoff
        )
        
        if recent_replies.exists():
            # Positive replies
            positive_replies = recent_replies.filter(interest_level='positive')
            if positive_replies.exists():
                reply_count = positive_replies.count()
                latest_reply = positive_replies.first()
                unique_leads = positive_replies.values('lead__email').distinct().count()
                
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='opportunity',
                    priority='medium',
                    title=f'🎉 Positive Replies: {campaign.name}',
                    message=f'Campaign "{campaign.name}" received {reply_count} positive reply/replies from {unique_leads} lead(s) in the last 7 days! Latest from {latest_reply.lead.email}. Follow up to convert them.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/',
                    metadata={'action': 'positive_replies', 'count': reply_count, 'unique_leads': unique_leads}
                )
                if notification:
                    notifications.append(notification)
                    opportunities.append({'type': 'positive_replies', 'count': reply_count})
            
            # Negative replies (not interested)
            negative_replies = recent_replies.filter(interest_level='negative')
            if negative_replies.exists():
                reply_count = negative_replies.count()
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='engagement',
                    priority='low',
                    title=f'📉 Negative Replies: {campaign.name}',
                    message=f'Campaign "{campaign.name}" received {reply_count} negative reply/replies (not interested) in the last 7 days. Consider: 1) Reviewing target audience, 2) Improving messaging, 3) Adjusting value proposition.',
                    action_required=False,
                    action_url=f'/marketing/campaigns/{campaign.id}/',
                    metadata={'action': 'negative_replies', 'count': reply_count}
                )
                if notification:
                    notifications.append(notification)
                    issues.append({'type': 'negative_replies', 'count': reply_count})
            
            # Objections/Concerns
            objection_replies = recent_replies.filter(interest_level='objection')
            if objection_replies.exists():
                reply_count = objection_replies.count()
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='engagement',
                    priority='medium',
                    title=f'⚠️ Objections Received: {campaign.name}',
                    message=f'Campaign "{campaign.name}" received {reply_count} reply/replies with objections/concerns. Address these concerns in follow-up emails to improve conversion.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/',
                    metadata={'action': 'objection_replies', 'count': reply_count}
                )
                if notification:
                    notifications.append(notification)
                    issues.append({'type': 'objections', 'count': reply_count})
            
            # Unsubscribe requests
            unsubscribe_replies = recent_replies.filter(interest_level='unsubscribe')
            if unsubscribe_replies.exists():
                reply_count = unsubscribe_replies.count()
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='engagement',
                    priority='high',
                    title=f'🚫 Unsubscribe Requests: {campaign.name}',
                    message=f'Campaign "{campaign.name}" received {reply_count} unsubscribe request(s) in the last 7 days. Review email frequency and content to reduce unsubscribes.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/',
                    metadata={'action': 'unsubscribe_requests', 'count': reply_count}
                )
                if notification:
                    notifications.append(notification)
                    issues.append({'type': 'unsubscribes', 'count': reply_count})
            
            # Information requests
            info_requests = recent_replies.filter(interest_level='requested_info')
            if info_requests.exists():
                reply_count = info_requests.count()
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='opportunity',
                    priority='medium',
                    title=f'📧 Information Requests: {campaign.name}',
                    message=f'Campaign "{campaign.name}" has {reply_count} lead(s) requesting more information! These are highly qualified leads. Respond promptly.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/',
                    metadata={'action': 'info_requests', 'count': reply_count}
                )
                if notification:
                    notifications.append(notification)
                    opportunities.append({'type': 'info_requests', 'count': reply_count})
            
            # Neutral replies
            neutral_replies = recent_replies.filter(interest_level='neutral')
            if neutral_replies.exists() and neutral_replies.count() >= 5:
                reply_count = neutral_replies.count()
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='engagement',
                    priority='low',
                    title=f'💬 Neutral Replies: {campaign.name}',
                    message=f'Campaign "{campaign.name}" received {reply_count} neutral reply/replies. These leads may need more nurturing. Consider creating follow-up sequences.',
                    action_required=False,
                    action_url=f'/marketing/campaigns/{campaign.id}/',
                    metadata={'action': 'neutral_replies', 'count': reply_count}
                )
                if notification:
                    notifications.append(notification)
        
        if notifications:
            return {
                'notifications': notifications,
                'opportunities': opportunities,
                'issues': issues
            }
        return None
    
    def _check_active_campaign_engagement(self, campaign: Campaign, user: User) -> Optional[Dict]:
        """Check open/click rates and engagement metrics for ALL campaigns (active, scheduled, paused)"""
        notifications = []
        opportunities = []
        issues = []
        
        # Get email statistics
        email_sends = EmailSendHistory.objects.filter(campaign=campaign)
        total_sent = email_sends.count()
        
        if total_sent == 0:
            return None
        
        emails_opened = email_sends.filter(status__in=['opened', 'clicked']).count()
        emails_clicked = email_sends.filter(status='clicked').count()
        emails_delivered = email_sends.filter(status__in=['delivered', 'opened', 'clicked']).count()
        
        open_rate = (emails_opened / total_sent * 100) if total_sent > 0 else 0
        click_rate = (emails_clicked / total_sent * 100) if total_sent > 0 else 0
        delivery_rate = (emails_delivered / total_sent * 100) if total_sent > 0 else 0
        
        # Check for excellent open rate (opportunity)
        if open_rate >= 30 and total_sent >= 20:
            existing_notif = MarketingNotification.objects.filter(
                user=user,
                campaign=campaign,
                notification_type='opportunity',
                title__icontains='Excellent Open Rate',
                created_at__gte=timezone.now() - timedelta(days=3)
            ).exists()
            
            if not existing_notif:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='opportunity',
                    priority='low',
                    title=f'⭐ Excellent Open Rate: {campaign.name}',
                    message=f'Campaign "{campaign.name}" has an excellent open rate of {open_rate:.1f}% ({emails_opened} opens from {total_sent} emails)! This indicates strong subject lines and audience targeting. Consider scaling this campaign.',
                    action_required=False,
                    action_url=f'/marketing/campaigns/{campaign.id}/',
                    metadata={'action': 'excellent_open_rate', 'open_rate': open_rate, 'total_sent': total_sent}
                )
                if notification:
                    notifications.append(notification)
                    opportunities.append({'type': 'excellent_open_rate', 'rate': open_rate})
        
        # Check for good click rate (opportunity)
        if click_rate >= 5 and total_sent >= 20:
            existing_notif = MarketingNotification.objects.filter(
                user=user,
                campaign=campaign,
                notification_type='opportunity',
                title__icontains='Good Click Rate',
                created_at__gte=timezone.now() - timedelta(days=3)
            ).exists()
            
            if not existing_notif:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='opportunity',
                    priority='low',
                    title=f'🎯 Good Click Rate: {campaign.name}',
                    message=f'Campaign "{campaign.name}" has a good click rate of {click_rate:.1f}% ({emails_clicked} clicks from {total_sent} emails)! Your CTAs are working well. Consider increasing email frequency.',
                    action_required=False,
                    action_url=f'/marketing/campaigns/{campaign.id}/',
                    metadata={'action': 'good_click_rate', 'click_rate': click_rate, 'total_sent': total_sent}
                )
                if notification:
                    notifications.append(notification)
                    opportunities.append({'type': 'good_click_rate', 'rate': click_rate})
        
        # Check for low open rate (issue)
        if open_rate < 15 and total_sent >= 10:
            existing_notif = MarketingNotification.objects.filter(
                user=user,
                campaign=campaign,
                notification_type='performance_alert',
                title__icontains='Low Open Rate',
                created_at__gte=timezone.now() - timedelta(days=2)
            ).exists()
            
            if not existing_notif:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='performance_alert',
                    priority='high',
                    title=f'⚠️ Low Open Rate: {campaign.name}',
                    message=f'Campaign "{campaign.name}" has a low open rate of {open_rate:.1f}% ({emails_opened} opens from {total_sent} emails). Improve: 1) Subject lines, 2) Send times, 3) Personalization, 4) Audience targeting.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/email-templates/',
                    metadata={'action': 'low_open_rate', 'open_rate': open_rate, 'total_sent': total_sent}
                )
                if notification:
                    notifications.append(notification)
                    issues.append({'type': 'low_open_rate', 'rate': open_rate})
        
        # Check for low click rate (issue)
        if open_rate >= 20 and click_rate < 2 and total_sent >= 15:
            existing_notif = MarketingNotification.objects.filter(
                user=user,
                campaign=campaign,
                notification_type='performance_alert',
                title__icontains='Low Click Rate',
                created_at__gte=timezone.now() - timedelta(days=2)
            ).exists()
            
            if not existing_notif:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='performance_alert',
                    priority='medium',
                    title=f'📉 Low Click Rate: {campaign.name}',
                    message=f'Campaign "{campaign.name}" has good open rate ({open_rate:.1f}%) but low click rate ({click_rate:.1f}%). Improve: 1) CTA buttons, 2) Email content relevance, 3) Offer value, 4) CTA placement.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/email-templates/',
                    metadata={'action': 'low_click_rate', 'open_rate': open_rate, 'click_rate': click_rate}
                )
                if notification:
                    notifications.append(notification)
                    issues.append({'type': 'low_click_rate', 'open_rate': open_rate, 'click_rate': click_rate})
        
        if notifications:
            return {
                'notifications': notifications,
                'opportunities': opportunities,
                'issues': issues
            }
        return None
    
    def _check_active_campaign_sequences(self, campaign: Campaign, user: User) -> Optional[Dict]:
        """Check sequence status and email sending for ALL campaigns (active, scheduled, paused, draft)"""
        notifications = []
        issues = []
        
        # Check if campaign has sequences
        sequences = EmailSequence.objects.filter(campaign=campaign)
        sequences_count = sequences.count()
        active_sequences = sequences.filter(is_active=True).count()
        
        # No sequences at all
        if sequences_count == 0:
            notification = self._create_notification(
                user=user,
                campaign=campaign,
                notification_type='campaign_status',
                priority='high',
                title=f'📧 No Email Sequences: {campaign.name}',
                message=f'Active campaign "{campaign.name}" has NO email sequences! Create email sequences to start sending emails to your {campaign.leads.count()} leads.',
                action_required=True,
                action_url=f'/marketing/campaigns/{campaign.id}/sequences/',
                metadata={'action': 'no_sequences', 'leads_count': campaign.leads.count()}
            )
            if notification:
                notifications.append(notification)
                issues.append({'type': 'no_sequences'})
        
        # Has sequences but none are active (only alert for active/scheduled campaigns)
        elif sequences_count > 0 and active_sequences == 0 and campaign.status in ['active', 'scheduled']:
            status_text = campaign.get_status_display()
            notification = self._create_notification(
                user=user,
                campaign=campaign,
                notification_type='campaign_status',
                priority='high',
                title=f'⏸️ No Active Sequences: {campaign.name}',
                message=f'{status_text.capitalize()} campaign "{campaign.name}" has {sequences_count} sequence(s) but NONE are active! Activate sequences to start sending emails.',
                action_required=True,
                action_url=f'/marketing/campaigns/{campaign.id}/sequences/',
                metadata={'action': 'no_active_sequences', 'total_sequences': sequences_count, 'status': campaign.status}
            )
            if notification:
                notifications.append(notification)
                issues.append({'type': 'no_active_sequences', 'total': sequences_count})
        
        # Check if emails are being sent
        total_emails_sent = EmailSendHistory.objects.filter(campaign=campaign).count()
        recent_emails = EmailSendHistory.objects.filter(
            campaign=campaign,
            sent_at__gte=timezone.now() - timedelta(days=7)
        ).count()
        
        # Has active sequences but no emails sent (only for active/scheduled campaigns)
        if active_sequences > 0 and total_emails_sent == 0 and campaign.status in ['active', 'scheduled']:
            # Check if campaign has leads
            leads_count = campaign.leads.count()
            if leads_count > 0:
                status_text = campaign.get_status_display()
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='campaign_status',
                    priority='high',
                    title=f'📬 No Emails Sent Yet: {campaign.name}',
                    message=f'{status_text.capitalize()} campaign "{campaign.name}" has {active_sequences} active sequence(s) and {leads_count} lead(s) but NO emails have been sent! Check sequence configuration and delays.',
                    action_required=True,
                    action_url=f'/marketing/campaigns/{campaign.id}/sequences/',
                    metadata={'action': 'no_emails_sent', 'active_sequences': active_sequences, 'leads_count': leads_count, 'status': campaign.status}
                )
                if notification:
                    notifications.append(notification)
                    issues.append({'type': 'no_emails_sent', 'active_sequences': active_sequences})
        
        # Low email sending activity (has sent emails before but none recently)
        # Only alert for active campaigns (paused/scheduled might be intentionally not sending)
        elif total_emails_sent > 0 and recent_emails == 0 and active_sequences > 0 and campaign.status == 'active':
            notification = self._create_notification(
                user=user,
                campaign=campaign,
                notification_type='campaign_status',
                priority='medium',
                title=f'📉 Low Email Activity: {campaign.name}',
                message=f'Active campaign "{campaign.name}" has sent {total_emails_sent} emails total but NONE in the last 7 days. Check: 1) Sequence delays, 2) Sequence completion, 3) Lead status.',
                action_required=True,
                action_url=f'/marketing/campaigns/{campaign.id}/',
                metadata={'action': 'low_email_activity', 'total_sent': total_emails_sent, 'recent_sent': 0}
            )
            if notification:
                notifications.append(notification)
                issues.append({'type': 'low_email_activity', 'total_sent': total_emails_sent})
        
        if notifications:
            return {
                'notifications': notifications,
                'issues': issues
            }
        return None
    
    def _check_positive_replies(self, campaign: Campaign, user: User) -> Optional[Dict]:
        """Check for positive replies from leads and notify about them"""
        notifications = []
        opportunities = []
        
        # Get recent positive replies (last 7 days)
        recent_cutoff = timezone.now() - timedelta(days=7)
        positive_replies = Reply.objects.filter(
            campaign=campaign,
            interest_level='positive',
            replied_at__gte=recent_cutoff
        ).order_by('-replied_at')
        
        if positive_replies.exists():
            reply_count = positive_replies.count()
            latest_reply = positive_replies.first()
            
            # Get unique leads who replied positively
            unique_leads = positive_replies.values('lead__email').distinct().count()
            
            notification = self._create_notification(
                user=user,
                campaign=campaign,
                notification_type='opportunity',
                priority='medium',
                title=f'🎉 Positive Replies Received: {campaign.name}',
                message=f'Great news! Campaign "{campaign.name}" received {reply_count} positive reply/replies from {unique_leads} lead(s) in the last 7 days! Latest reply from {latest_reply.lead.email}. Follow up with these interested leads to convert them.',
                action_required=True,
                action_url=f'/marketing/campaigns/{campaign.id}/',
                metadata={
                    'action': 'positive_replies_received',
                    'reply_count': reply_count,
                    'unique_leads': unique_leads,
                    'latest_reply_date': latest_reply.replied_at.isoformat() if latest_reply.replied_at else None,
                    'latest_reply_from': latest_reply.lead.email
                }
            )
            if notification:
                notifications.append(notification)
                opportunities.append({
                    'type': 'positive_replies',
                    'count': reply_count,
                    'unique_leads': unique_leads
                })
        
        # Check for replies requesting more information (also positive signal)
        info_requests = Reply.objects.filter(
            campaign=campaign,
            interest_level='requested_info',
            replied_at__gte=recent_cutoff
        ).count()
        
        if info_requests > 0:
            notification = self._create_notification(
                user=user,
                campaign=campaign,
                notification_type='opportunity',
                priority='medium',
                title=f'📧 Information Requests: {campaign.name}',
                message=f'Campaign "{campaign.name}" has {info_requests} lead(s) requesting more information! These are highly qualified leads. Respond promptly with detailed information to convert them.',
                action_required=True,
                action_url=f'/marketing/campaigns/{campaign.id}/',
                metadata={
                    'action': 'info_requests_received',
                    'request_count': info_requests
                }
            )
            if notification:
                notifications.append(notification)
                opportunities.append({
                    'type': 'info_requests',
                    'count': info_requests
                })
        
        if notifications:
            return {
                'notifications': notifications,
                'opportunities': opportunities
            }
        return None
    
    def _check_campaign_progress(self, campaign: Campaign, user: User) -> Optional[Dict]:
        """Check campaign progress and provide regular updates for active campaigns"""
        notifications = []
        opportunities = []
        
        # Get campaign statistics
        total_emails_sent = EmailSendHistory.objects.filter(campaign=campaign).count()
        emails_opened = EmailSendHistory.objects.filter(
            campaign=campaign,
            status__in=['opened', 'clicked']
        ).count()
        emails_clicked = EmailSendHistory.objects.filter(
            campaign=campaign,
            status='clicked'
        ).count()
        total_replies = Reply.objects.filter(campaign=campaign).count()
        positive_replies = Reply.objects.filter(
            campaign=campaign,
            interest_level='positive'
        ).count()
        
        # Calculate rates
        open_rate = (emails_opened / total_emails_sent * 100) if total_emails_sent > 0 else 0
        click_rate = (emails_clicked / total_emails_sent * 100) if total_emails_sent > 0 else 0
        reply_rate = (total_replies / total_emails_sent * 100) if total_emails_sent > 0 else 0
        
        # Only send progress updates if campaign has sent emails
        if total_emails_sent == 0:
            return None
        
        # Check campaign age (days since start)
        if campaign.start_date:
            days_running = (timezone.now().date() - campaign.start_date).days
        else:
            # Use first email sent date as proxy
            first_email = EmailSendHistory.objects.filter(campaign=campaign).order_by('sent_at').first()
            if first_email and first_email.sent_at:
                days_running = (timezone.now().date() - first_email.sent_at.date()).days
            else:
                days_running = 0
        
        # Weekly progress update (every 7 days)
        if days_running > 0 and days_running % 7 == 0:
            # Check if we already sent a weekly update today (avoid duplicates)
            today = timezone.now().date()
            existing_update = MarketingNotification.objects.filter(
                user=user,
                campaign=campaign,
                notification_type='milestone',
                title__icontains='Weekly Progress',
                created_at__date=today
            ).exists()
            
            if not existing_update:
                # Calculate weekly stats (last 7 days)
                week_cutoff = timezone.now() - timedelta(days=7)
                weekly_sent = EmailSendHistory.objects.filter(
                    campaign=campaign,
                    sent_at__gte=week_cutoff
                ).count()
                weekly_opened = EmailSendHistory.objects.filter(
                    campaign=campaign,
                    status__in=['opened', 'clicked'],
                    sent_at__gte=week_cutoff
                ).count()
                weekly_replies = Reply.objects.filter(
                    campaign=campaign,
                    replied_at__gte=week_cutoff
                ).count()
                
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='milestone',
                    priority='low',
                    title=f'📊 Weekly Progress Update: {campaign.name}',
                    message=f'Campaign "{campaign.name}" progress after {days_running} days:\n\n📧 Emails: {total_emails_sent} sent ({weekly_sent} this week)\n👁️ Opens: {emails_opened} ({open_rate:.1f}% open rate)\n🖱️ Clicks: {emails_clicked} ({click_rate:.1f}% click rate)\n💬 Replies: {total_replies} ({reply_rate:.1f}% reply rate, {positive_replies} positive)\n\n{"🎉 Great engagement!" if open_rate >= 25 else "💡 Consider optimizing subject lines and content."}',
                    action_required=False,
                    action_url=f'/marketing/campaigns/{campaign.id}/',
                    metadata={
                        'action': 'weekly_progress_update',
                        'days_running': days_running,
                        'total_emails_sent': total_emails_sent,
                        'weekly_sent': weekly_sent,
                        'open_rate': open_rate,
                        'click_rate': click_rate,
                        'reply_rate': reply_rate,
                        'positive_replies': positive_replies
                    }
                )
                if notification:
                    notifications.append(notification)
                    opportunities.append({
                        'type': 'weekly_progress',
                        'days_running': days_running
                    })
        
        # Milestone: First 100 emails sent
        if total_emails_sent >= 100 and total_emails_sent < 110:
            existing_milestone = MarketingNotification.objects.filter(
                user=user,
                campaign=campaign,
                notification_type='milestone',
                title__icontains='100 emails',
                created_at__gte=timezone.now() - timedelta(days=1)
            ).exists()
            
            if not existing_milestone:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='milestone',
                    priority='low',
                    title=f'🎯 Milestone: 100 Emails Sent - {campaign.name}',
                    message=f'Campaign "{campaign.name}" has reached 100 emails sent! Current stats: {open_rate:.1f}% open rate, {click_rate:.1f}% click rate, {total_replies} replies. Keep up the momentum!',
                    action_required=False,
                    action_url=f'/marketing/campaigns/{campaign.id}/',
                    metadata={
                        'action': '100_emails_milestone',
                        'total_emails_sent': total_emails_sent,
                        'open_rate': open_rate,
                        'click_rate': click_rate
                    }
                )
                if notification:
                    notifications.append(notification)
                    opportunities.append({
                        'type': '100_emails_milestone',
                        'total_sent': total_emails_sent
                    })
        
        # Good performance opportunity: High engagement
        if open_rate >= 25 and click_rate >= 3 and total_emails_sent >= 20:
            existing_opportunity = MarketingNotification.objects.filter(
                user=user,
                campaign=campaign,
                notification_type='opportunity',
                title__icontains='High Performance',
                created_at__gte=timezone.now() - timedelta(days=3)
            ).exists()
            
            if not existing_opportunity:
                notification = self._create_notification(
                    user=user,
                    campaign=campaign,
                    notification_type='opportunity',
                    priority='low',
                    title=f'🚀 High Performance Campaign: {campaign.name}',
                    message=f'Campaign "{campaign.name}" is performing excellently! {open_rate:.1f}% open rate and {click_rate:.1f}% click rate. Consider: 1) Scaling this campaign, 2) Applying similar strategies to other campaigns, 3) Increasing email frequency.',
                    action_required=False,
                    action_url=f'/marketing/campaigns/{campaign.id}/',
                    metadata={
                        'action': 'high_performance_opportunity',
                        'open_rate': open_rate,
                        'click_rate': click_rate,
                        'total_sent': total_emails_sent
                    }
                )
                if notification:
                    notifications.append(notification)
                    opportunities.append({
                        'type': 'high_performance',
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
        
        # Auto-mark all previous unread notifications as read when new notification is created
        # This ensures only the newest notifications show as unread in Recent Notifications tab
        # Strategy: Mark notifications created BEFORE this one as read (within a small time window to handle batch creation)
        # This way, all notifications created in the same batch (within 1 second) will remain unread
        batch_window = timezone.now() - timedelta(seconds=2)  # 2 second window for batch
        
        previous_unread = MarketingNotification.objects.filter(
            user=user,
            is_read=False,
            created_at__lt=batch_window  # Only mark ones created before this batch window
        )
        
        if previous_unread.exists():
            # Mark all previous unread notifications as read
            updated_count = previous_unread.update(
                is_read=True,
                read_at=timezone.now()
            )
            logger.info(f"Auto-marked {updated_count} previous notifications as read for user {user.id} when new notification {notification.id} was created")
        
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


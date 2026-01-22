"""
Celery tasks for marketing agent automation
All tasks that were previously run via Windows Task Scheduler are now automated with Celery.
"""
from celery import shared_task
from django.core.management import call_command
from django.utils import timezone
from marketing_agent.models import Campaign, EmailSendHistory
from marketing_agent.views import auto_pause_expired_campaigns


@shared_task(bind=True, max_retries=3, default_retry_delay=300)  # Retry 3 times, 5 min delay
def send_sequence_emails_task(self):
    """
    Celery task to send sequence emails automatically.
    Handles: Main sequences, follow-ups, and sub-sequences.
    
    IMPORTANT: 
    - Runs every 5 minutes to check for emails ready to send
    - Respects user-defined delays (delay_days, delay_hours, delay_minutes) from sequence steps
    - Minimum time gap between emails is 5 minutes (task frequency)
    - Actual email timing is based on sequence step delays set by user
    
    Scheduled: Every 5 minutes via Celery Beat
    Replaces: Windows Task Scheduler running 'send_sequence_emails'
    """
    try:
        call_command('send_sequence_emails')
        return {'status': 'success', 'message': 'Sequence emails checked and sent based on user-defined delays'}
    except Exception as e:
        print(f'Error in sequence emails task: {str(e)}')
        # Retry the task
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def sync_inbox_task(self):
    """
    Celery task to sync inbox and detect email replies.
    Handles: Reply detection, AI analysis, sub-sequence assignment.
    
    Scheduled: Every 5-10 minutes via Celery Beat
    Replaces: Windows Task Scheduler running 'sync_inbox'
    """
    try:
        call_command('sync_inbox')
        return {'status': 'success', 'message': 'Inbox synced'}
    except Exception as e:
        print(f'Error in inbox sync task: {str(e)}')
        raise self.retry(exc=e)


@shared_task
def auto_pause_expired_campaigns_task():
    """
    Celery task to automatically pause expired campaigns.
    Handles: Campaigns past end_date, associated sequences.
    
    Scheduled: Daily at midnight via Celery Beat
    Replaces: Manual dashboard access trigger
    """
    try:
        result = auto_pause_expired_campaigns()
        return {
            'status': 'success',
            'campaigns_paused': result['campaigns_paused'],
            'sequences_paused': result['sequences_paused']
        }
    except Exception as e:
        print(f'Error in auto-pause task: {str(e)}')
        return {'status': 'error', 'error': str(e)}


@shared_task(bind=True, max_retries=2, default_retry_delay=600)
def retry_failed_emails_task(self):
    """
    Celery task to retry failed email sends.
    Handles: Emails with status 'failed' or 'pending'.
    
    Scheduled: Every 15 minutes via Celery Beat
    NEW FEATURE: Not previously automated
    """
    try:
        # Get failed/pending emails from last 24 hours
        from datetime import timedelta
        cutoff_time = timezone.now() - timedelta(hours=24)
        
        failed_emails = EmailSendHistory.objects.filter(
            status__in=['failed', 'pending'],
            created_at__gte=cutoff_time
        ).select_related('lead', 'email_template', 'campaign')[:50]
        
        retried_count = 0
        for email_history in failed_emails:
            try:
                from marketing_agent.services.email_service import email_service
                result = email_service.send_email(
                    template=email_history.email_template,
                    lead=email_history.lead,
                    campaign=email_history.campaign,
                    email_account=email_history.email_account
                )
                if result.get('success'):
                    retried_count += 1
            except Exception as e:
                print(f'Failed to retry email {email_history.id}: {str(e)}')
        
        return {'status': 'success', 'retried_count': retried_count}
    except Exception as e:
        print(f'Error in retry failed emails task: {str(e)}')
        raise self.retry(exc=e)


@shared_task
def auto_start_campaigns_task():
    """
    Celery task to automatically start scheduled campaigns.
    Handles: Campaigns with start_date = today, status = 'scheduled'.
    
    Scheduled: Every hour via Celery Beat
    NEW FEATURE: Not previously automated
    """
    try:
        today = timezone.now().date()
        
        # Also check for campaigns that should have started (start_date <= today)
        campaigns_to_start = Campaign.objects.filter(
            status='scheduled',
            start_date__lte=today  # Changed from = to <= to catch past dates too
        )
        
        started_count = 0
        for campaign in campaigns_to_start:
            campaign.status = 'active'
            campaign.save()
            # Activate sequences
            campaign.email_sequences.update(is_active=True)
            started_count += 1
        
        return {'status': 'success', 'started_count': started_count, 'date_checked': str(today)}
    except Exception as e:
        print(f'Error in auto-start campaigns task: {str(e)}')
        return {'status': 'error', 'error': str(e)}


@shared_task
def monitor_campaigns_task():
    """
    Celery task to monitor ALL campaigns and send proactive notifications.
    Uses ProactiveNotificationAgent to detect issues and opportunities.
    
    Monitors:
    - Active campaigns: Performance, budget, delivery, milestones, anomalies
    - Scheduled campaigns: Setup issues, readiness checks
    - Paused campaigns: Action items to resume
    - Draft campaigns: Setup completion recommendations
    
    Scheduled: Every 30 minutes via Celery Beat
    FULLY AUTOMATED: Replaces manual notification checking
    """
    try:
        from marketing_agent.agents.proactive_notification_agent import ProactiveNotificationAgent
        agent = ProactiveNotificationAgent()
        
        # Monitor ALL campaigns (not just active) - each status needs different checks
        all_campaigns = Campaign.objects.filter(
            status__in=['active', 'scheduled', 'paused', 'draft']
        ).select_related('owner')
        
        total_notifications = 0
        campaigns_checked = 0
        errors = []
        
        for campaign in all_campaigns:
            try:
                # Check campaign for all notification types
                result = agent.check_campaign(campaign.owner.id, campaign.id)
                
                if result.get('success'):
                    notifications_created = result.get('notifications_created', 0)
                    if notifications_created > 0:
                        total_notifications += notifications_created
                        print(f'Campaign "{campaign.name}" ({campaign.status}): {notifications_created} notification(s) created')
                    campaigns_checked += 1
                else:
                    errors.append(f'Campaign {campaign.id}: {result.get("error", "Unknown error")}')
            except Exception as e:
                error_msg = f'Error monitoring campaign {campaign.id} ({campaign.name}): {str(e)}'
                print(error_msg)
                errors.append(error_msg)
        
        print(f'Notification monitoring completed: {campaigns_checked} campaigns checked, {total_notifications} notifications created')
        
        return {
            'status': 'success',
            'campaigns_checked': campaigns_checked,
            'total_notifications': total_notifications,
            'errors': errors if errors else None
        }
    except Exception as e:
        print(f'Error in campaign monitoring task: {str(e)}')
        return {'status': 'error', 'error': str(e)}

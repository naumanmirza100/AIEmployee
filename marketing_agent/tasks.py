"""
Celery tasks for marketing agent automation
All tasks that were previously run via Windows Task Scheduler are now automated with Celery.
"""
from celery import shared_task
from django.core.management import call_command
from django.utils import timezone
from datetime import timedelta

from marketing_agent.models import Campaign, EmailSendHistory, EmailSequence, MarketingNotification
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
def sync_inbox_task(self, account_id=None, since_days=None):
    """
    Celery task to sync inbox and detect email replies.
    Handles: Reply detection, AI analysis, sub-sequence assignment.

    Two modes:
      - account_id=None  → fan-out. The beat scheduler fires this every
        5 min; it enumerates every IMAP-enabled account and queues one
        per-account task on the same queue. Workers then sync accounts
        truly in parallel (bounded by --concurrency), so adding a 10th
        company doesn't make every other company's inbox 10× slower.
      - account_id=<id>  → single account. Used by the on-create dispatch
        and by the fan-out branch above. Acquires the per-account Redis
        lock inside sync_inbox; if another worker is already syncing the
        same account it logs and skips instead of racing.

    `since_days` is passed through to the management command so callers
    can request a smaller window than the default. The on-connect path
    uses this to fire a fast 30-day sync first and queue the deeper
    120-day backfill on a delay.
    """
    # Fan-out branch — runs on the periodic beat tick.
    if account_id is None:
        from marketing_agent.models import EmailAccount
        active_ids = list(
            EmailAccount.objects
            .filter(enable_imap_sync=True, is_active=True)
            .values_list('id', flat=True)
        )
        for aid in active_ids:
            # `apply_async` queues each account as its own task. The worker
            # pool drains them in parallel; a slow account doesn't block
            # the fast ones the way the old sequential loop did.
            sync_inbox_task.apply_async(
                kwargs={'account_id': aid, 'since_days': since_days},
                expires=600,
            )
        return {'status': 'success', 'message': f'Fan-out: queued {len(active_ids)} account(s)'}

    # Single-account branch. The per-account lock lives inside the
    # management command (sync_inbox.py), so an overlapping fan-out tick
    # can't double-sync the same mailbox.
    try:
        kwargs = {'account_id': account_id}
        if since_days:
            kwargs['since_days'] = since_days
        call_command('sync_inbox', **kwargs)
        return {'status': 'success', 'message': f'Inbox synced for account {account_id}'}
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
                # EmailSendHistory has no email_account FK, so we resolve via
                # the campaign's default. send_email also falls back to the
                # owner's default active account when this is None.
                retry_account = email_history.campaign.email_account if email_history.campaign else None
                result = email_service.send_email(
                    template=email_history.email_template,
                    lead=email_history.lead,
                    campaign=email_history.campaign,
                    email_account=retry_account,
                )
                if result.get('success'):
                    retried_count += 1
            except Exception as e:
                print(f'Failed to retry email {email_history.id}: {str(e)}')
        
        return {'status': 'success', 'retried_count': retried_count}
    except Exception as e:
        print(f'Error in retry failed emails task: {str(e)}')
        raise self.retry(exc=e)


def _create_scheduled_launch_notification(campaign, user, title, message, action_required, action_url=None, metadata=None):
    """Create notification for scheduled campaign launch - avoid duplicates in last 24h."""
    recent_cutoff = timezone.now() - timedelta(hours=24)
    dup = MarketingNotification.objects.filter(
        user=user, campaign=campaign, notification_type='campaign_status',
        title=title, created_at__gte=recent_cutoff
    ).first()
    if dup and not dup.is_read:
        return None
    return MarketingNotification.objects.create(
        user=user, campaign=campaign, notification_type='campaign_status',
        priority='high', title=title, message=message,
        action_required=action_required, action_url=action_url or '',
        metadata=metadata or {}
    )


@shared_task
def auto_start_campaigns_task():
    """
    Celery task to automatically start scheduled campaigns when start_date has arrived.
    - Only auto-activates if campaign has at least one active sequence with steps (ready to send).
    - If no sequences: creates notification and does NOT activate (campaign stays scheduled).
    - If sequences present: auto-activates and creates notification.
    
    Scheduled: Every 15 minutes via Celery Beat
    """
    try:
        today = timezone.now().date()
        campaigns_due = Campaign.objects.filter(
            status='scheduled',
            start_date__lte=today
        ).select_related('owner')
        
        started_count = 0
        notified_no_sequences = 0
        
        for campaign in campaigns_due:
            user = campaign.owner
            sequences = EmailSequence.objects.filter(campaign=campaign)
            has_sequence_with_steps = any(seq.steps.exists() for seq in sequences)
            
            if has_sequence_with_steps:
                # Auto-activate: campaign has sequences ready
                campaign.status = 'active'
                campaign.save()
                campaign.email_sequences.update(is_active=True)
                started_count += 1
                _create_scheduled_launch_notification(
                    campaign, user,
                    title=f'✅ Campaign Auto-Activated: {campaign.name}',
                    message=f'Scheduled date ({campaign.start_date}) has arrived. Campaign "{campaign.name}" was automatically activated. Emails will be sent according to your sequences.',
                    action_required=False,
                    action_url=f'/marketing/dashboard/campaign/{campaign.id}',
                    metadata={'action': 'auto_activated', 'start_date': str(campaign.start_date)}
                )
                print(f'Auto-activated campaign "{campaign.name}" (ID {campaign.id})')
            else:
                # Do NOT activate - create notification that date arrived but needs sequences
                _create_scheduled_launch_notification(
                    campaign, user,
                    title=f'⏰ Scheduled Date Arrived – Action Required: {campaign.name}',
                    message=f'Scheduled date ({campaign.start_date}) has arrived but campaign "{campaign.name}" cannot be activated automatically. It has no email sequences (or no templates). Create email templates and sequences first, then launch the campaign manually.',
                    action_required=True,
                    action_url=f'/marketing/dashboard/campaign/{campaign.id}/sequences',
                    metadata={'action': 'date_arrived_no_sequences', 'start_date': str(campaign.start_date)}
                )
                notified_no_sequences += 1
                print(f'Notification: Campaign "{campaign.name}" (ID {campaign.id}) - date arrived but no sequences')
        
        return {
            'status': 'success',
            'started_count': started_count,
            'notified_no_sequences': notified_no_sequences,
            'date_checked': str(today)
        }
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


@shared_task
def sync_campaign_performance_task():
    """
    Sync CampaignPerformance table with live email/reply data.
    Keeps the performance table in sync with what the dashboard shows.

    Scheduled: Every 30 minutes via Celery Beat
    """
    try:
        from marketing_agent.performance_sync import sync_all_campaigns_performance
        synced = sync_all_campaigns_performance()
        return {'status': 'success', 'campaigns_synced': synced}
    except Exception as e:
        print(f'Error in performance sync task: {str(e)}')
        return {'status': 'error', 'error': str(e)}

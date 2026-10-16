"""Marketing alerts that need someone to act also reach the shared bell.

Marketing kept its alerts on its own Notifications page, so a campaign that could not
start, or a mailbox that stopped sending, waited there until someone happened to look.
Only alerts marked "action required" are passed on. Marketing's monitor runs every half
hour and raises the same alert again once it is read, so the bell hears each one at most
once a day.
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

KIND = 'marketing_action_required'


def forward(notification):
    """Pass a new MarketingNotification on to its owner's bell when it needs action."""
    if notification is None or not notification.action_required:
        return 0
    try:
        from core.models import CompanyUser
        from core.notification_utils import notify_company_users
        from project_manager_agent.models import PMNotification

        title = notification.title[:255]
        since = timezone.now() - timedelta(hours=24)
        logins = [cu for cu in CompanyUser.objects.filter(login_user_id=notification.user_id, is_active=True)
                  if not PMNotification.objects.filter(company_user=cu, title=title, created_at__gte=since,
                                                       data__kind=KIND).exists()]
        if not logins:
            return 0
        link = (f'/marketing/dashboard/campaign/{notification.campaign_id}' if notification.campaign_id
                else '/marketing/dashboard')
        severity = 'critical' if notification.priority == 'critical' else 'warning'
        return notify_company_users(logins, title=title, message=notification.message, link=link,
                                    severity=severity, kind=KIND,
                                    data={'marketing_notification_id': notification.id})
    except Exception:
        logger.exception('Could not pass Marketing alert %s on to the bell', getattr(notification, 'id', None))
        return 0

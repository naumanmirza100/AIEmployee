"""Helpers to create in-app notifications.

The Notification model is tied to Django's auth User. CompanyUsers don't have
their own Notification table; we bridge via a matching Django User
(created lazily by email). Same pattern `_get_or_create_user_for_company_user`
uses in api/views/marketing_agent.py.
"""
import logging

from django.contrib.auth.models import User

from core.models import CompanyUser, Notification

logger = logging.getLogger(__name__)


def _user_for_company_user(company_user: CompanyUser) -> User:
    """Map a CompanyUser to the paired Django User, creating one if needed."""
    try:
        return User.objects.get(email=company_user.email)
    except User.DoesNotExist:
        name_parts = (company_user.full_name or '').split()
        return User.objects.create_user(
            username=f"company_user_{company_user.id}_{company_user.email}",
            email=company_user.email,
            password=None,
            first_name=name_parts[0] if name_parts else '',
            last_name=' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
        )


def notify_company_user(company_user, *, title, message, action_url=None,
                        notification_type='key_update'):
    """Fire an in-app notification to a CompanyUser's paired Django User.

    Safe no-op on failure — notifications must never break the calling flow.
    """
    if not company_user:
        return None
    try:
        user = _user_for_company_user(company_user)
        return Notification.objects.create(
            user=user,
            type=notification_type,
            notification_type=notification_type,
            title=title,
            message=message,
            link=action_url,
            action_url=action_url,
        )
    except Exception as exc:
        logger.warning("Failed to create company-user notification: %s", exc)
        return None


def notify_admins(*, title, message, action_url=None, notification_type='admin_action'):
    """Broadcast to all staff/superuser Django Users. Used when a KeyRequest
    is raised so admins see it in their inbox without polling the dashboard."""
    try:
        admins = list(User.objects.filter(is_staff=True, is_active=True))
        created = []
        for admin in admins:
            n = Notification.objects.create(
                user=admin,
                type=notification_type,
                notification_type=notification_type,
                title=title,
                message=message,
                link=action_url,
                action_url=action_url,
            )
            created.append(n)
        return created
    except Exception as exc:
        logger.warning("Failed to broadcast admin notification: %s", exc)
        return []

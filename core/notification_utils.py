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
    """Map a CompanyUser to the paired Django User, creating one if needed.
    Uses a stable username keyed on company_user.id so two companies with
    the same email never collide.
    """
    username = f"company_user_{company_user.id}"
    try:
        return User.objects.get(username=username)
    except User.DoesNotExist:
        name_parts = (company_user.full_name or '').split()
        return User.objects.create_user(
            username=username,
            email=company_user.email,
            password=None,
            first_name=name_parts[0] if name_parts else '',
            last_name=' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
        )


def notify_company_users(company_users, *, title, message, link=None,
                         severity='info', kind='custom'):
    """Put a notification in each of these logins' bell.

    A company login's bell (and its Notifications page) reads the company feed,
    `PMNotification`, whichever agent's page it is on. Despite the name, that
    table is every company-wide alert already — billing, quotas, API keys — not
    only Project Manager's. `link` is an in-app path the bell opens; `kind`
    says what raised it. Inactive or repeated logins are skipped.

    Returns how many were created. Never raises: an alert must not break the
    action that raised it.
    """
    from project_manager_agent.models import PMNotification
    try:
        seen, rows = set(), []
        for cu in company_users:
            if not cu or not cu.is_active or cu.id in seen:
                continue
            seen.add(cu.id)
            rows.append(PMNotification(
                company_user=cu, notification_type='custom', severity=severity,
                title=str(title)[:255], message=message,
                data={'link': link, 'kind': kind},
            ))
        PMNotification.objects.bulk_create(rows)
        return len(rows)
    except Exception as exc:
        logger.warning("Failed to create company-user notifications: %s", exc)
        return 0


def notify_company_user(company_user, *, title, message, action_url=None,
                        notification_type='key_update'):
    """One login's bell; see `notify_company_users`.

    This used to write the auth-user `Notification` table under a stand-in
    user, which a company login's bell never reads — so, for example, a
    rejected managed-key request was never seen by the company that asked.
    """
    if not company_user:
        return 0
    return notify_company_users([company_user], title=title, message=message,
                                link=action_url, kind=notification_type)


def notify_company_quota(company, agent_label: str, pct: int, actual_pct: float = None, pool: str = 'free'):
    """Send quota threshold notification to all CompanyUsers via PMNotification.

    pool: 'free' | 'managed' | 'byok'
    """
    try:
        from core.models import CompanyUser
        from project_manager_agent.models import PMNotification

        recipients = CompanyUser.objects.filter(company=company, is_active=True)
        raw_pct = actual_pct if actual_pct is not None else float(pct)
        capped = min(100.0, raw_pct)
        display_pct = int(capped) if capped == int(capped) else round(capped, 1)

        if pool == 'managed':
            pool_label = 'managed key tokens'
        elif pool == 'byok':
            pool_label = 'BYOK token cap'
        else:
            pool_label = 'free platform tokens'

        if pct >= 100:
            if pool == 'managed':
                title = f"Managed key quota exhausted — {agent_label}"
                action_hint = "Contact your admin to increase the managed key token limit."
            elif pool == 'byok':
                title = f"BYOK token cap reached — {agent_label}"
                action_hint = "Your BYOK key will keep working, but you have reached the soft cap you set. Update the cap in API Keys settings if needed."
            else:
                title = f"Free token quota exhausted — {agent_label}"
                action_hint = "Add your own API key (BYOK) or request a managed key to continue."
            message = f"Your {agent_label} has used {display_pct}% of its {pool_label}. {action_hint}"
            severity = 'critical' if pool != 'byok' else 'warning'
        else:
            if pool == 'managed':
                title = f"Managed key quota at {display_pct}% — {agent_label}"
                action_hint = "Contact your admin soon to increase the managed key token limit."
            elif pool == 'byok':
                title = f"BYOK token cap at {display_pct}% — {agent_label}"
                action_hint = "You are approaching the soft cap you set. Update it in API Keys settings if needed."
            else:
                title = f"Token quota at {display_pct}% — {agent_label}"
                action_hint = "Consider adding your own API key (BYOK) or requesting a managed key soon."
            message = f"Your {agent_label} has used {display_pct}% of its {pool_label}. {action_hint}"
            severity = 'warning'

        for cu in recipients:
            PMNotification.objects.create(
                company_user=cu,
                notification_type='custom',
                severity=severity,
                title=title,
                message=message,
            )
    except Exception as exc:
        logger.warning("Failed to send quota notification: %s", exc)


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

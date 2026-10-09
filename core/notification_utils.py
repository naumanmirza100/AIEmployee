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
                         severity='info', kind='custom', email=True, data=None):
    """Tell each of these logins, the way each has chosen.

    A company login's bell (and its Notifications page) reads the company feed,
    `PMNotification`, whichever agent's page it is on. Despite the name, that
    table is every company-wide alert already — billing, quotas, API keys — not
    only Project Manager's. `link` is an in-app path the bell opens; `kind`
    says what raised it, and decides its topic in `core.notification_settings`:
    each login's choice there puts it in the bell, sends it by email, or both.
    Pass `email=False` when the caller sends its own, richer email (after
    asking `wants_email`). Inactive or repeated logins are skipped.

    Returns how many bell rows were created. Never raises: an alert must not
    break the action that raised it.
    """
    from project_manager_agent.models import PMNotification
    from core import notification_settings
    try:
        seen, recipients = set(), []
        for cu in company_users:
            if not cu or not cu.is_active or cu.id in seen:
                continue
            seen.add(cu.id)
            recipients.append(cu)
        topic = notification_settings.topic_for_kind(kind)
        chosen = notification_settings.choices(recipients, topic.key) if topic else {}
        rows = []
        for cu in recipients:
            in_app, by_email = chosen.get(cu.id, (True, False))
            if in_app:
                rows.append(PMNotification(
                    company_user=cu, notification_type='custom', severity=severity,
                    title=str(title)[:255], message=message,
                    data={**(data or {}), 'link': link, 'kind': kind},
                ))
            if by_email and email and cu.email:
                notification_settings.send_email(cu, topic.key, title=title, message=message, link=link)
        PMNotification.objects.bulk_create(rows)
        return len(rows)
    except Exception as exc:
        logger.warning("Failed to create company-user notifications: %s", exc)
        return 0


def notify_employees(users, *, title, message, link=None, kind='custom',
                     email_subject=None, email_body=None, attachments=()):
    """Tell employee logins: a row in the bell My Space reads
    (`core.Notification`) and, when `email_subject` is given, an email.

    `notify_company_users` reaches dashboard logins only, so an agent that
    booked or decided something for a member of staff had no way to say so:
    HR, Frontline and Recruitment told the people they booked nothing at all.
    `link` is an in-app path the bell opens (a My Space page), `kind` says what
    raised it. `email_body` defaults to the message; `attachments` are
    (filename, content, mimetype) triples, e.g. a calendar file.

    The bell rows are written now, so they roll back with a booking that
    fails. The email is sent only once the surrounding transaction commits:
    nobody is emailed about something that did not happen. Employee logins
    have no notification settings yet, so there is nothing to ask first.
    Switched-off logins, repeats and `.invalid` addresses are skipped.

    Returns how many bell rows were created. Never raises: an alert must not
    break the action that raised it.
    """
    from django.db import transaction
    try:
        seen, people = set(), []
        for user in users:
            if user is None or not user.is_active or user.pk in seen:
                continue
            seen.add(user.pk)
            people.append(user)
        Notification.objects.bulk_create([
            Notification(user=user, type=str(kind)[:50], title=str(title)[:255], message=message,
                         link=link, action_url=link)
            for user in people
        ])
        addresses = [u.email for u in people
                     if email_subject and u.email and not u.email.lower().endswith('.invalid')]
        if addresses:
            body = email_body or message
            if link:
                from core.notification_settings import frontend_url
                body = f"{body}\n\nOpen it: {frontend_url(link)}"
            transaction.on_commit(lambda: _email_each(addresses, email_subject, body, attachments))
        return len(people)
    except Exception as exc:
        logger.warning("Failed to tell employees (%s): %s", kind, exc)
        return 0


def _email_each(addresses, subject, body, attachments=()):
    """One email per person, so nobody sees who else was told. Never raises."""
    from django.conf import settings
    from django.core.mail import EmailMessage
    sender = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')
    for address in dict.fromkeys(addresses):
        try:
            email = EmailMessage(subject=str(subject)[:200], body=body, from_email=sender, to=[address])
            for name, content, mimetype in attachments or ():
                email.attach(name, content, mimetype)
            email.send(fail_silently=True)
        except Exception as exc:
            logger.warning("Could not email %s: %s", address, exc)


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
                action_hint = "The agent has stopped: your own key has used the cap you set. Raise or remove the cap in API Keys settings to carry on."
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
                action_hint = "The agent stops when the cap you set is reached. Raise or remove it in API Keys settings if you need more."
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

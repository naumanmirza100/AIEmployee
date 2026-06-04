"""
PM notification dispatch (N-F1 + N-F2).

`dispatch_pm_notification` creates a PMNotification (the in-app record) and then
fans out the same payload to any active outbound channels the recipient has
registered (Slack/Teams webhook, extra email). Templates (PMNotificationTemplate)
may override the title/body per company + notification_type.

Call sites should use this helper instead of `PMNotification.objects.create`
when they want template rendering or external delivery. It falls back to plain
in-app delivery when neither is configured, so it's safe to swap in everywhere.
"""

from __future__ import annotations

import json
import logging
from typing import Iterable

import requests
from django.conf import settings as django_settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECS = 5


def _render_with_template(company, notification_type, default_title, default_message, context):
    """Return (title, message, severity) — applying a template override if one exists."""
    try:
        from project_manager_agent.models import PMNotificationTemplate
    except Exception:
        return default_title, default_message, None
    if company is None:
        return default_title, default_message, None
    template = (
        PMNotificationTemplate.objects
        .filter(company=company, notification_type=notification_type, is_active=True)
        .first()
    )
    if template is None:
        return default_title, default_message, None
    rendered_title, rendered_msg = template.render(context or {})
    return rendered_title, rendered_msg, template.default_severity


def _post_slack(channel, title, message, severity):
    payload = {
        'text': f"*{title}*\n{message}",
        'attachments': [{
            'color': {'info': '#36a64f', 'warning': '#f2c744', 'critical': '#d62728'}.get(severity, '#888'),
            'fields': [{'title': 'Severity', 'value': severity, 'short': True}],
        }],
    }
    r = requests.post(channel.target, json=payload, timeout=_REQUEST_TIMEOUT_SECS)
    r.raise_for_status()


def _post_teams(channel, title, message, severity):
    theme = {'info': '0078D7', 'warning': 'F2C744', 'critical': 'D62728'}.get(severity, '888888')
    payload = {
        '@type': 'MessageCard',
        '@context': 'https://schema.org/extensions',
        'summary': title,
        'themeColor': theme,
        'title': title,
        'text': message,
        'sections': [{'facts': [{'name': 'Severity', 'value': severity}]}],
    }
    r = requests.post(
        channel.target,
        data=json.dumps(payload),
        headers={'Content-Type': 'application/json'},
        timeout=_REQUEST_TIMEOUT_SECS,
    )
    r.raise_for_status()


def _send_email_channel(channel, title, message):
    from_email = getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')
    send_mail(
        subject=title,
        message=message,
        from_email=from_email,
        recipient_list=[channel.target],
        fail_silently=True,
    )


def _fanout_to_channels(company_user, notification_type, severity, title, message):
    try:
        from project_manager_agent.models import PMNotificationChannel
    except Exception:
        return
    channels = PMNotificationChannel.objects.filter(company_user=company_user, is_active=True)
    for ch in channels:
        sev_filter = [s.strip() for s in (ch.severities or '').split(',') if s.strip()]
        if sev_filter and severity not in sev_filter:
            continue
        type_filter = [t.strip() for t in (ch.types or '').split(',') if t.strip()]
        if type_filter and notification_type not in type_filter:
            continue
        try:
            if ch.channel_type == 'slack':
                _post_slack(ch, title, message, severity)
            elif ch.channel_type == 'teams':
                _post_teams(ch, title, message, severity)
            elif ch.channel_type == 'email':
                _send_email_channel(ch, title, message)
            ch.last_used_at = timezone.now()
            ch.last_error = ''
            ch.save(update_fields=['last_used_at', 'last_error', 'updated_at'])
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"[:280]
            logger.warning(
                f"[PM CHANNEL FANOUT] channel={ch.id} type={ch.channel_type} failed: {err}"
            )
            ch.last_error = err
            ch.save(update_fields=['last_error', 'updated_at'])


def dispatch_pm_notification(
    *,
    company_user,
    notification_type,
    title,
    message,
    severity='info',
    project=None,
    data=None,
    context=None,
    extra_emails: Iterable[str] = (),
):
    """
    Create an in-app PMNotification AND fan out to any configured outbound
    channels for `company_user`. Returns the created PMNotification.

    - `context` is a placeholder dict used by template rendering (N-F1).
    - `extra_emails` are one-shot extra recipients (e.g. the organizer's own
      email for meeting reminders); separate from PMNotificationChannel.
    """
    from project_manager_agent.models import PMNotification

    company = None
    try:
        company = getattr(company_user, 'company', None)
    except Exception:
        company = None

    rendered_title, rendered_message, template_sev = _render_with_template(
        company, notification_type, title, message, context,
    )
    if template_sev:
        severity = template_sev

    pm_notif = PMNotification.objects.create(
        company_user=company_user,
        project=project,
        notification_type=notification_type if notification_type in dict(PMNotification.TYPE_CHOICES) else 'custom',
        severity=severity if severity in dict(PMNotification.SEVERITY_CHOICES) else 'info',
        title=rendered_title[:255],
        message=rendered_message,
        data=data or {},
    )

    _fanout_to_channels(company_user, notification_type, severity, rendered_title, rendered_message)

    if extra_emails:
        from_email = getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')
        recips = [e for e in extra_emails if e]
        if recips:
            try:
                send_mail(
                    subject=rendered_title,
                    message=rendered_message,
                    from_email=from_email,
                    recipient_list=recips,
                    fail_silently=True,
                )
            except Exception:
                logger.exception("[PM DISPATCH] extra-email send failed")

    return pm_notif

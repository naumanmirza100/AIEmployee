"""Telling people about their mail. There were no alerts at all: the page just refreshed (the AI Employee list's
Proactive Notification, 30 Oct 2026). Each login chooses bell, email or both under "Urgent email" and "Daily inbox
summary" in the notification settings.
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

EMAILS = '/reply-draft/emails'


def mailbox_logins(account):
    """Who hears about a mailbox: the login that connected it; when that one is switched off, the company's owner
    and admins (as the company keeps the mailbox, CO-203)."""
    from core.models import CompanyUser
    own = list(CompanyUser.objects.filter(login_user_id=account.owner_id, is_active=True))
    if own:
        return own
    from core.logins import company_id_for
    company_id = company_id_for(account.owner)
    if not company_id:
        return []
    return list(CompanyUser.objects.filter(company_id=company_id, is_active=True, role__in=('owner', 'admin')))


def urgent_email(email):
    """Once per email: an urgent email has arrived."""
    from core.notification_utils import notify_company_users
    from .models import InboxEmail
    if not InboxEmail.objects.filter(pk=email.pk, alerted_at__isnull=True).update(alerted_at=timezone.now()):
        return
    who = email.from_name or email.from_email
    message = f'"{email.subject or "(no subject)"}"'
    if email.ai_summary:
        message += f': {email.ai_summary}'
    try:
        notify_company_users(mailbox_logins(email.email_account), title=f'Urgent email from {who}', message=message,
                             link=f'{EMAILS}?email={email.id}', kind='inbox_urgent', severity='warning')
    except Exception:
        logger.exception('Could not tell about urgent email %s', email.pk)


def digest_text(account, since):
    """The day's mail in a few lines, or None when nothing came."""
    from .models import CATEGORY_CHOICES, InboxEmail, ReplyDraft
    mail = list(InboxEmail.objects.filter(email_account=account, direction='in', received_at__gte=since)
                .order_by('-received_at'))
    if not mail:
        return None
    labels = dict(CATEGORY_CHOICES)
    counts = {}
    for m in mail:
        if m.category:
            counts[m.category] = counts.get(m.category, 0) + 1
    lines = [f'{len(mail)} new email{"s" if len(mail) != 1 else ""} since yesterday.']
    if counts:
        lines.append(', '.join(f'{labels[c]}: {n}' for c, n in sorted(counts.items(), key=lambda kv: -kv[1])) + '.')
    urgent = [m for m in mail if m.priority == 'urgent']
    if urgent:
        lines.append('')
        lines.append('Urgent:')
        lines += [f'- {m.from_name or m.from_email}: {m.ai_summary or m.subject}' for m in urgent[:5]]
    answered = set(ReplyDraft.objects.filter(inbox_email__in=mail, status='sent').values_list('inbox_email_id',
                                                                                               flat=True))
    waiting = [m for m in mail if m.needs_reply and m.id not in answered]
    if waiting:
        lines.append('')
        lines.append(f'Waiting for an answer ({len(waiting)}):')
        lines += [f'- {m.from_name or m.from_email}: {m.ai_summary or m.subject}' for m in waiting[:8]]
    return '\n'.join(lines)


def send_digest(account):
    """The day's summary of a mailbox, by email to whoever wants it. True when there was mail to tell about."""
    from core.notification_utils import notify_company_users
    text = digest_text(account, timezone.now() - timedelta(days=1))
    if not text:
        return False
    notify_company_users(mailbox_logins(account), title=f'Your inbox today: {account.email}', message=text,
                         link=EMAILS, kind='inbox_digest')
    return True

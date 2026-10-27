"""Emails to a customer that no person writes.

A customer who sent the website's contact form was told "Thank you. We'll get back to you soon." on the page and
nothing by email: no reference, no sign the message had arrived. Now they get one short acknowledgement with the
ticket's reference ([FL-n], the tag replies thread on), sent once the ticket is saved.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def sender(company):
    """(From, Reply-To) for every email to a company's customer: replies, the receipt, call invitations, the survey.

    From carries the company's name, "Margalla Software <address>". The customer used to see only the platform's
    address (live, 27 Oct: "payperproject.laskon@gmail.com"), nothing of who had written to them. Reply-To is the
    company's support inbox, so an answer comes back onto the ticket."""
    from email.utils import formataddr, parseaddr

    from django.conf import settings
    own = (getattr(company, 'support_from_email', '') or '').strip()
    address = parseaddr(own or getattr(settings, 'DEFAULT_FROM_EMAIL', '') or '')[1] or 'noreply@example.com'
    name = (getattr(company, 'name', '') or '').strip()
    from_email = formataddr((name, address)) if name else address
    inbound = getattr(settings, 'FRONTLINE_INBOUND_EMAIL_DOMAIN', '') or ''
    slug = getattr(company, 'support_inbox_slug', '') or ''
    reply_to = f'support+{slug}@{inbound}' if slug and inbound else own
    return from_email, reply_to or None


def acknowledge_web_form(ticket, message):
    """Tell the customer their contact-form message arrived. After the save is committed; never raises. A ticket
    with no customer address tells nobody."""
    contact = getattr(ticket, 'contact', None)
    to = (getattr(contact, 'email', '') or '').strip()
    if not to:
        return False
    from django.db import transaction
    company = ticket.company
    team = (getattr(company, 'name', '') or '').strip() or 'our team'
    name = (getattr(contact, 'name', '') or '').strip()
    body = '\n\n'.join([
        f'Hello {name},' if name else 'Hello,',
        f'Thank you for contacting {team}. We have received your message, and a person from our team will reply to '
        'you by email.',
        f'Your reference is FL-{ticket.id}. If you write again about this, reply to this email.',
        'Your message:\n' + (message or '').strip()[:2000],
        f'— {team}',
    ])

    def send():
        try:
            from django.core.mail import EmailMessage
            from_email, reply_to = sender(company)
            EmailMessage(subject=f'We received your message [FL-{ticket.id}]', body=body, from_email=from_email,
                         to=[to], reply_to=[reply_to] if reply_to else None).send(fail_silently=False)
        except Exception:
            logger.exception('Frontline ticket %s: the customer was not sent an acknowledgement', ticket.pk)

    transaction.on_commit(send)
    return True

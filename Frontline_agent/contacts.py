"""Contact helpers — upsert a customer record from inbound data, and keep
the denormalized ticket count / first-seen / last-seen timestamps fresh.

Always call `upsert_contact_from_email` instead of hitting the model directly
so the email is lowercased consistently and the company-scoping contract holds.
"""
from __future__ import annotations

import logging
from typing import Optional

from django.db import transaction
from django.db.models import Count, Max, Min
from django.utils import timezone

logger = logging.getLogger(__name__)


def upsert_contact_from_email(company, email: str, name: str = '', phone: str = '',
                              touch_last_seen: bool = True):
    """Get-or-create a Contact for (company, email). Backfills the name/phone
    the first time they're seen, never overwrites them with blanks.

    Returns the Contact or None when inputs are invalid.
    """
    if not company or not email:
        return None
    email_lc = email.strip().lower()
    if '@' not in email_lc:
        return None

    from .models import Contact

    now = timezone.now()
    try:
        with transaction.atomic():
            contact, created = Contact.objects.get_or_create(
                company=company, email=email_lc,
                defaults={
                    'name': (name or '').strip()[:255],
                    'phone': (phone or '').strip()[:40],
                    'first_seen_at': now,
                    'last_seen_at': now if touch_last_seen else None,
                },
            )
            dirty = []
            if not created:
                if name and not contact.name:
                    contact.name = name.strip()[:255]
                    dirty.append('name')
                if phone and not contact.phone:
                    contact.phone = phone.strip()[:40]
                    dirty.append('phone')
                if not contact.first_seen_at:
                    contact.first_seen_at = now
                    dirty.append('first_seen_at')
                if touch_last_seen:
                    contact.last_seen_at = now
                    dirty.append('last_seen_at')
                if dirty:
                    dirty.append('updated_at')
                    contact.save(update_fields=list(set(dirty)))
            return contact
    except Exception:
        logger.exception("upsert_contact_from_email failed for %s / %s", company.id, email_lc)
        return None


def link_ticket_to_contact(ticket, contact) -> bool:
    """Attach a ticket to a contact (if not already) and bump the contact's
    denormalized counters. Safe to call multiple times — idempotent."""
    if not ticket or not contact:
        return False
    changed = False
    if ticket.contact_id != contact.id:
        ticket.contact = contact
        ticket.save(update_fields=['contact', 'updated_at'])
        changed = True
    recompute_contact_stats(contact)
    return changed


def recompute_contact_stats(contact) -> None:
    """Recalculate total_tickets_count / first_seen / last_seen from the
    current ticket + inbound-message data. Cheap — one aggregate query."""
    from .models import Ticket, TicketMessage

    if not contact:
        return
    agg_tickets = Ticket.objects.filter(contact=contact).aggregate(
        count=Count('id'), first=Min('created_at'), last=Max('created_at'),
    )
    # last_seen_at should reflect the latest customer interaction, not just ticket
    # creation. Prefer max(last inbound message, last ticket created).
    agg_inbound = TicketMessage.objects.filter(
        ticket__contact=contact, direction='inbound',
    ).aggregate(last=Max('created_at'), first=Min('created_at'))

    last_seen = _max_dt(agg_tickets['last'], agg_inbound['last'], contact.last_seen_at)
    first_seen = _min_dt(agg_tickets['first'], agg_inbound['first'], contact.first_seen_at)
    count = agg_tickets['count'] or 0

    update = []
    if contact.total_tickets_count != count:
        contact.total_tickets_count = count
        update.append('total_tickets_count')
    if last_seen and contact.last_seen_at != last_seen:
        contact.last_seen_at = last_seen
        update.append('last_seen_at')
    if first_seen and contact.first_seen_at != first_seen:
        contact.first_seen_at = first_seen
        update.append('first_seen_at')
    if update:
        update.append('updated_at')
        contact.save(update_fields=list(set(update)))


def _max_dt(*values):
    vals = [v for v in values if v is not None]
    return max(vals) if vals else None


def _min_dt(*values):
    vals = [v for v in values if v is not None]
    return min(vals) if vals else None

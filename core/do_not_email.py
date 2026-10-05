"""The company's do-not-email list: one answer for every agent that does outreach.

Someone who unsubscribes has told the company to stop, not one salesperson and
not one agent. Before this list, AI SDR stopped only the campaigns of the login
that sent the email, a colleague's campaign carried on, and Marketing kept no
list at all: a reply saying "unsubscribe" ended that one sequence and nothing
stopped the same address being added to the next campaign.

Who writes to it
    AI SDR     unsubscribe link, a 'not interested' reply, a hard bounce
    Marketing  a reply read as an unsubscribe request
    People     the settings page, for a request that came by phone or post

Who asks it
    AI SDR     before enrolling a lead and before every send
    Marketing  before adding a lead to a campaign and before every send

A reply can be read as "unsubscribe" by mistake, so an admin can take an
address off again (`unblock`). Addresses are compared lower-cased.
"""
import logging

logger = logging.getLogger(__name__)

UNSUBSCRIBED, BOUNCED, MANUAL = 'unsubscribed', 'bounced', 'manual'


def clean(email) -> str:
    return (email or '').strip().lower()


def _company_id(company):
    return getattr(company, 'pk', company)


def reason_for(company, email) -> str:
    """Why this address is on the company's list, or '' when it is not."""
    from core.models import DoNotEmail

    company_id, email = _company_id(company), clean(email)
    if not company_id or not email:
        return ''
    return DoNotEmail.objects.filter(company_id=company_id, email=email).values_list('reason', flat=True).first() or ''


def is_blocked(company, email) -> bool:
    return bool(reason_for(company, email))


def blocked_among(company, emails) -> set:
    """Of these addresses, the ones on the list. One query, for imports."""
    from core.models import DoNotEmail

    company_id = _company_id(company)
    wanted = {clean(e) for e in emails} - {''}
    if not company_id or not wanted:
        return set()
    return set(DoNotEmail.objects.filter(company_id=company_id, email__in=wanted).values_list('email', flat=True))


def block(company, email, reason=UNSUBSCRIBED, source='', note='', added_by=None) -> bool:
    """Put an address on the list. True when it was not there before.

    An address already listed keeps its first reason: a later bounce does not
    hide that the person asked to stop.
    """
    from core.models import DoNotEmail

    company_id, email = _company_id(company), clean(email)
    if not company_id or not email:
        return False
    _, created = DoNotEmail.objects.get_or_create(
        company_id=company_id, email=email,
        defaults={'reason': reason, 'source': source[:30], 'note': (note or '')[:255], 'added_by': added_by},
    )
    return created


def unblock(company, email) -> bool:
    """Take an address off the list. True when it was on it.

    AI SDR also keeps a 'bounced' mark on its own lead rows and refuses to send
    to them; that mark goes too, or the address would stay blocked there.
    """
    from core.models import DoNotEmail

    company_id, email = _company_id(company), clean(email)
    if not company_id or not email:
        return False
    removed, _ = DoNotEmail.objects.filter(company_id=company_id, email=email).delete()
    try:
        from ai_sdr_agent.models import SDRLead
        SDRLead.all_objects.filter(
            company_user__company_id=company_id, email__iexact=email, email_bounced=True,
        ).update(email_bounced=False, email_bounced_at=None, email_bounce_reason='')
    except Exception:
        logger.exception('Could not clear the bounce mark for a do-not-email entry (company %s)', company_id)
    return bool(removed)

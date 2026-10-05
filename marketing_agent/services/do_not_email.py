"""Marketing's side of the company do-not-email list (core/do_not_email.py).

A campaign belongs to a user, not a company, so the company is worked out from
the owner (marketing_agent/services/subscription.py). When it cannot be told
there is no list to ask, and the send goes ahead as it did before.
"""
from core import do_not_email
from marketing_agent.services.subscription import company_id_for_owner


def company_id_for_campaign(campaign):
    return company_id_for_owner(getattr(campaign, 'owner', None))


def is_blocked_for(campaign, email) -> bool:
    """True when the campaign's company must not email this address."""
    company_id = company_id_for_campaign(campaign)
    return bool(company_id) and do_not_email.is_blocked(company_id, email)


def block_for(campaign, email, note='') -> bool:
    """Someone asked this campaign to stop: no more outreach from the company."""
    company_id = company_id_for_campaign(campaign)
    if not company_id:
        return False
    return do_not_email.block(company_id, email, do_not_email.UNSUBSCRIBED, source='marketing', note=note)

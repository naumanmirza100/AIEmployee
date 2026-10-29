"""Whose Marketing rows a login may reach.

Campaigns, leads and mailboxes are stored against the user record of the login that made them. An owner or admin may
open and manage any campaign of the company, with its leads and replies (the user's decision of 29 Oct 2026, gaps
report decision 2); anyone else reaches only their own. A campaign still sends from the mailbox its maker chose.
"""
from core.logins import company_id_for

MANAGERS = ('owner', 'admin')


def _company_ids(company_id, user):
    from core.models import CompanyUser
    ids = set(CompanyUser.objects.filter(company_id=company_id).exclude(login_user=None)
              .values_list('login_user_id', flat=True))
    ids.add(user.pk)
    return sorted(ids)


def company_owner_ids(user):
    """User record ids of every dashboard login of this user's company, switched off or not; just this user when the
    company cannot be told."""
    if user is None:
        return []
    company_id = company_id_for(user)
    return _company_ids(company_id, user) if company_id else [user.pk]


def owner_ids(company_user, user):
    """The campaign owners this login may open: the whole company's for an owner or admin, else only its own."""
    if getattr(company_user, 'role', '') in MANAGERS and getattr(company_user, 'company_id', None):
        return _company_ids(company_user.company_id, user)
    return [user.pk]

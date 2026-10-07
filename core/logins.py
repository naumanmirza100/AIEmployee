"""One user record for each dashboard login.

Campaigns, leads, documents and tickets are stored against an `auth.User`. A
dashboard login is a `CompanyUser`, which is not one, so each agent found or
made a user record for it in its own way. Frontline and HR keyed that record
on the login (`CompanyUser.login_user`). Marketing and Reply Draft looked for
any user record with the same email address, and so:

  * opening Marketing first and Frontline or HR afterwards left two records
    with one address, and every Reply Draft page then failed for that login;
  * one address used as a dashboard login in two companies shared one record,
    and with it one set of campaigns, leads, mail accounts and replies.

`user_for` is the one way from a dashboard login to its user record, for every
agent. `company_id_for` is the one way back.
"""
import logging

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)


def user_for(company_user):
    """The `auth.User` this dashboard login acts as, made on first use.

    Never found by email: `CompanyUser` is unique per (company, email), so the
    same address can be a login in two companies.
    """
    if company_user is None:
        return None
    if company_user.login_user_id:
        return company_user.login_user

    from core.models import CompanyUser
    User = get_user_model()
    username = f'company_user_{company_user.id}'
    user = User.objects.filter(username=username).first()
    if user is None:
        names = (company_user.full_name or '').split()
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username, email=company_user.email, password=None,
                    first_name=names[0] if names else '',
                    last_name=' '.join(names[1:]),
                )
        except IntegrityError:          # two first requests at once: the other one made it
            user = User.objects.get(username=username)
    # Keep the link, so the next request is a key read and not a lookup.
    CompanyUser.objects.filter(pk=company_user.pk).update(login_user=user)
    company_user.login_user = user
    return user


def company_id_for(user):
    """The company a user record acts for, or None when it cannot be told.

    The dashboard login linked to it says so. Records older than the link are
    found by email, but only when a single company has a login with that
    address: a guess between two companies is worse than no answer.
    """
    if user is None:
        return None
    from core.models import CompanyUser
    linked = set(CompanyUser.objects.filter(login_user_id=user.pk).values_list('company_id', flat=True))
    if linked:
        return linked.pop() if len(linked) == 1 else None
    email = (getattr(user, 'email', '') or '').strip()
    if not email:
        return None
    by_email = set(CompanyUser.objects.filter(email__iexact=email).values_list('company_id', flat=True))
    return by_email.pop() if len(by_email) == 1 else None


def company_user_ids(company):
    """Ids of the user records of every active dashboard login of a company."""
    from core.models import CompanyUser
    return list(CompanyUser.objects.filter(company=company, is_active=True)
                .exclude(login_user=None).values_list('login_user_id', flat=True))

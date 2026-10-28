"""The sender of an email a company sends through the platform: '<Company> via Pay Per Project', at the platform's
address. Recruitment's candidate emails used it (recruitment_agent/candidate_mail.py); HR's workflow emails, such as
a new starter's welcome, came from the bare platform address, so a hire handed over from Recruitment got the
company's emails and then one from 'payperproject...@gmail.com'."""
from email.utils import formataddr, parseaddr

from django.conf import settings


def from_address(company_name) -> str:
    name, address = parseaddr(getattr(settings, 'DEFAULT_FROM_EMAIL', '') or 'noreply@example.com')
    shown = f'{company_name} via Pay Per Project' if company_name else (name or 'Pay Per Project')
    return formataddr((' '.join(shown.split()), address))


def company_from_address(company_id) -> str:
    """`from_address` for the company with this id (the platform's own name when there is none)."""
    from core.models import Company
    name = Company.objects.filter(pk=company_id).values_list('name', flat=True).first() if company_id else None
    return from_address((name or '').strip())

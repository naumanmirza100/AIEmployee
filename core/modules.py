"""Does this company have this agent, right now?

One answer for the screens and for everything that runs with nobody watching:
scheduled jobs, automations, reminder emails.

The API has always been gated (api/middleware/module_access.py). Background
work was not. When an agent's subscription lapsed or a card failed, its screens
locked at once while its sequences, follow-ups, reminders and automations
carried on emailing customers and candidates, and nobody could open the screens
to stop them. Only AI SDR's jobs checked.

A job asks `active_company_ids('hr_agent')` once and skips every row whose
company is not in it. Work that is plain housekeeping (clean-ups, leave
accrual, retention) does not ask: it must keep the data right for the day the
company comes back.
"""
import logging

logger = logging.getLogger(__name__)


def has_module(company, module_name) -> bool:
    """True when `company` (an instance or an id) has an active purchase of `module_name`."""
    from core.models import CompanyModulePurchase

    company_id = getattr(company, 'pk', company)
    if not company_id:
        return False
    purchase = CompanyModulePurchase.objects.filter(company_id=company_id, module_name=module_name).first()
    return bool(purchase and purchase.is_active())


def active_company_ids(*module_names) -> frozenset:
    """Ids of the companies with an active purchase of any of these agents. One query."""
    from core.models import CompanyModulePurchase

    purchases = CompanyModulePurchase.objects.filter(module_name__in=module_names, status='active')
    return frozenset(p.company_id for p in purchases if p.is_active())


def may_run_for(company_id, active_ids) -> bool:
    """For work whose company is worked out indirectly and may be unknown.

    Skip only when the company is known and has no active purchase. With no
    company to check, the work runs as it always did: a guess must not silently
    stop a paying customer's emails.
    """
    return company_id is None or company_id in active_ids

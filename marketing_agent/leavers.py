"""Marketing's part when a dashboard login is switched off (core/leavers.py).

Every campaign, lead and mailbox is stored against the login that made it, and
every Marketing screen shows only the caller's own. Switching a login off
signed it out and nothing else: the scheduled sender checked only that the
campaign was active and that the company still paid, so the leaver's campaigns
went on sending, and no admin could open, pause or delete them.

What happens now:
  * the login's running and scheduled campaigns are paused when it is switched off;
  * the sender passes over any campaign whose owner's login is switched off;
  * an owner or admin can list every colleague's campaign and stop any of them
    (api/views/marketing_agent.py, colleagues_campaigns);
  * a colleague in the same company can connect the company's mailbox, which
    used to be refused as "not available" because another login already had it.

What it does not do: open a colleague's campaign, its leads or its emails. Those
screens still belong to the login that made them.
"""
import logging

logger = logging.getLogger(__name__)


def _user_of(company_user):
    """The user record this login's Marketing rows are stored against, without making one."""
    return company_user.login_user if getattr(company_user, 'login_user_id', None) else None


def login_switched_off(company_user, by=None) -> str:
    """Pause this login's running and scheduled campaigns. Says how many."""
    from marketing_agent.models import Campaign

    user = _user_of(company_user)
    if user is None:
        return ''
    running = list(Campaign.objects.filter(owner=user, status__in=('active', 'scheduled')))
    for campaign in running:
        campaign.status = 'paused'
        campaign.save()         # through save(): that is what switches the campaign's sequences off
    if not running:
        return ''
    titles = ', '.join(f'"{c.name}"' for c in running[:5]) + (f' and {len(running) - 5} more' if len(running) > 5 else '')
    return (f'{len(running)} marketing campaign{"" if len(running) == 1 else "s"} of theirs '
            f'{"was" if len(running) == 1 else "were"} paused: {titles}.')


def owner_switched_off(owner_id) -> bool:
    """True when this campaign owner is a dashboard login that has been switched off.

    A user record no dashboard login points at (older data) is not counted: it
    cannot be told to be anybody's, and a guess must not stop a campaign."""
    from core.models import CompanyUser

    if not owner_id:
        return False
    logins = list(CompanyUser.objects.filter(login_user_id=owner_id).values_list('is_active', flat=True))
    return bool(logins) and not any(logins)


def colleagues(company_user):
    """{user record id: dashboard login} for every other login of the company, switched off or not."""
    from core.models import CompanyUser

    return {login.login_user_id: login
            for login in CompanyUser.objects.filter(company_id=company_user.company_id)
            .exclude(pk=company_user.pk).exclude(login_user=None)}


def colleagues_campaigns(company_user):
    """Every campaign in the company that is not the caller's own, newest first, with its owner's login."""
    from marketing_agent.models import Campaign

    people = colleagues(company_user)
    campaigns = Campaign.objects.filter(owner_id__in=list(people)).order_by('-created_at')
    return [(campaign, people[campaign.owner_id]) for campaign in campaigns]


def same_company(owner, user) -> bool:
    """Do these two user records act for the same company? Unknown counts as no."""
    from core.logins import company_id_for

    if owner is None or user is None:
        return False
    if owner.pk == user.pk:
        return True
    theirs, ours = company_id_for(owner), company_id_for(user)
    return bool(theirs) and theirs == ours

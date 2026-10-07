"""Marketing's background work stops when its subscription does.

The screens are locked by the API the moment a subscription lapses, but the
sequence sender, the retry job and the campaign starter are scheduled jobs and
never pass through the API. They kept emailing leads for a company that had
cancelled, and nobody could open the screens to pause them.

A campaign belongs to a user (`campaign.owner`), not to a company, so the
company is worked out from the owner: the dashboard login that acts as that
user, else the login with the same email when only one company has it
(core/logins.py). When no company can be found the campaign runs as before: a
guess must not stop a paying customer's emails.
"""
import logging

from core.modules import active_company_ids, may_run_for

logger = logging.getLogger(__name__)


def company_id_for_owner(owner):
    """The company a campaign owner belongs to, or None when it cannot be told."""
    from core.logins import company_id_for
    return company_id_for(owner)


class PayingCampaigns:
    """Ask `allows(campaign)` while walking campaigns in one job run."""

    def __init__(self):
        self.paying = active_company_ids('marketing_agent')
        self._company_by_owner = {}

    def allows(self, campaign) -> bool:
        if campaign is None:
            return True
        owner_id = getattr(campaign, 'owner_id', None)
        if owner_id not in self._company_by_owner:
            try:
                self._company_by_owner[owner_id] = company_id_for_owner(getattr(campaign, 'owner', None))
            except Exception:
                logger.exception('Could not work out the company for campaign %s', getattr(campaign, 'pk', None))
                self._company_by_owner[owner_id] = None
        return may_run_for(self._company_by_owner[owner_id], self.paying)

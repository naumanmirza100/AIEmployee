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
        self._owner_gone = {}

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
        if not may_run_for(self._company_by_owner[owner_id], self.paying):
            return False
        # Nor for someone whose login has been switched off. Their campaigns are
        # paused at that moment (marketing_agent/leavers.py); this is for any that
        # were missed, and for logins switched off before that was done.
        if owner_id not in self._owner_gone:
            try:
                from marketing_agent.leavers import owner_switched_off
                self._owner_gone[owner_id] = owner_switched_off(owner_id)
            except Exception:
                logger.exception('Could not tell whether the owner of campaign %s is switched off',
                                 getattr(campaign, 'pk', None))
                self._owner_gone[owner_id] = False
        return not self._owner_gone[owner_id]


def mailboxes_to_read(accounts):
    """The mailboxes whose company still pays for an agent that reads them: Marketing for a Marketing mailbox, Reply
    Draft for a Reply Draft one. After a company cancelled, its mailbox was still logged into and read every five
    minutes (CO-129). A mailbox whose company cannot be told is read as before."""
    marketing = active_company_ids('marketing_agent')
    reply_draft = active_company_ids('reply_draft_agent')
    kept, companies = [], {}
    for account in accounts:
        if account.owner_id not in companies:
            companies[account.owner_id] = company_id_for_owner(account.owner)
        company = companies[account.owner_id]
        if (company is None
                or (account.is_marketing_account and company in marketing)
                or (getattr(account, 'is_reply_agent_account', False) and company in reply_draft)):
            kept.append(account)
    return kept

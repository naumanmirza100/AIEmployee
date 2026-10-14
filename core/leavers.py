"""What a dashboard login was running, when the login is switched off.

Several agents keep what they do under the login that set it up: sales and
marketing campaigns, the shared reply mailbox, executive meetings. Switching a
login off signed that person out and nothing else. Their campaigns went on
emailing, their mailbox went on being read, the meetings they organised kept
everyone's time booked, and nobody else in the company, the owner included,
could see any of it or stop it.

A login is switched off in two places: an admin on Logins and roles
(api/views/company_logins.py), and HR offboarding (hr_agent/access.py). Both
call `login_switched_off`. Each agent says there what it does, in its own
module, and answers with a sentence for the people who run the company.

Switching the login back on undoes none of this: a campaign that was paused
stays paused until somebody starts it again.
"""
import logging
from importlib import import_module

logger = logging.getLogger(__name__)

#: Module of each agent's part. Each has `login_switched_off(company_user, by)`
#: returning a sentence about what it did, or '' when it had nothing to do.
PARTS = (
    'ai_sdr_agent.leavers',
    'marketing_agent.leavers',
    'reply_draft_agent.leavers',
    'meeting_agent.leavers',
)

ADMIN_ROLES = ('owner', 'admin')


def is_admin(company_user) -> bool:
    """Runs the company: may see and stop what any login in it has running."""
    return bool(company_user is not None and getattr(company_user, 'is_active', False)
                and getattr(company_user, 'role', '') in ADMIN_ROLES)


def heir_for(company_user, by=None):
    """The login that takes over what a switched-off login was holding, or None when nobody is left.

    The admin who switched it off, when a person did; otherwise an owner, an
    admin, or failing those anyone still active in the same company."""
    from core.models import CompanyUser

    if by is not None and by.is_active and by.company_id == company_user.company_id and by.pk != company_user.pk:
        return by
    others = CompanyUser.objects.filter(company_id=company_user.company_id, is_active=True).exclude(pk=company_user.pk)
    return (others.filter(role='owner').order_by('id').first()
            or others.filter(role='admin').order_by('id').first()
            or others.order_by('id').first())


def login_switched_off(company_user, by=None) -> list:
    """Run every agent's part for a login that has just been switched off.

    `by` is the admin who did it, when a person did. Returns the sentences, for
    the screen that switched the login off. One agent failing does not stop
    the others, and nothing here can undo the switching off."""
    done = []
    for path in PARTS:
        try:
            said = import_module(path).login_switched_off(company_user, by)
        except Exception:
            logger.exception('Could not tidy up after login %s in %s', getattr(company_user, 'pk', None), path)
            continue
        if said:
            done.append(said)
    if done:
        _tell_the_admins(company_user, by, done)
    return done


def _tell_the_admins(company_user, by, done):
    try:
        from core.models import CompanyUser
        from core.notification_utils import notify_company_users
        admins = list(CompanyUser.objects.filter(company_id=company_user.company_id, is_active=True,
                                                 role__in=ADMIN_ROLES).exclude(pk=company_user.pk))
        name = company_user.full_name or company_user.email
        notify_company_users(
            admins, title=f"{name}'s login was switched off",
            message=' '.join(done), link='/company/settings/team', kind='company_login_switched_off')
    except Exception:
        logger.exception('Could not tell the admins what was paused for login %s', getattr(company_user, 'pk', None))

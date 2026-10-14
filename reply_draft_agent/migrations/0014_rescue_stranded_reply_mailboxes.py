# A company's reply mailbox belongs to the login that connected it. From now on
# it is handed to another login when that one is switched off
# (reply_draft_agent/leavers.py). This does the same, once, for mailboxes whose
# login was switched off before that existed: everyone else in those companies
# has been looking at 'no mailbox connected' since.
#
# A stranded mailbox goes to the company's first active owner, else admin, else
# any active login, that has a user record. A company with nobody like that is
# left as it is and logged. Safe to run again; reversing is a no-op.

import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def rescue(apps, schema_editor):
    from reply_draft_agent.leavers import move_mailbox

    CompanyUser = apps.get_model('core', 'CompanyUser')
    EmailAccount = apps.get_model('marketing_agent', 'EmailAccount')
    InboxEmail = apps.get_model('reply_draft_agent', 'InboxEmail')
    ReplyDraft = apps.get_model('reply_draft_agent', 'ReplyDraft')

    for mailbox in EmailAccount._base_manager.filter(is_reply_agent_account=True):
        logins = list(CompanyUser._base_manager.filter(login_user_id=mailbox.owner_id))
        if not logins or any(login.is_active for login in logins):
            continue                                    # nobody's, or still somebody's who can sign in
        companies = {login.company_id for login in logins}
        if len(companies) != 1:
            logger.warning('Reply mailbox %s is under a login of several companies; left as it is.', mailbox.pk)
            continue
        others = (CompanyUser._base_manager.filter(company_id=companies.pop(), is_active=True)
                  .exclude(login_user_id=None))
        heir = (others.filter(role='owner').order_by('id').first() or others.filter(role='admin').order_by('id').first()
                or others.order_by('id').first())
        if heir is None:
            logger.warning('Reply mailbox %s is under a switched-off login and its company has no active login '
                           'to give it to; left as it is.', mailbox.pk)
            continue
        move_mailbox(EmailAccount, InboxEmail, ReplyDraft, mailbox, heir.login_user_id)
        logger.warning('Reply mailbox %s moved from switched-off login(s) %s to login %s.',
                       mailbox.pk, [login.pk for login in logins], heir.pk)


class Migration(migrations.Migration):

    dependencies = [
        ('reply_draft_agent', '0013_inboxemail_attachments_fetched'),
        ('marketing_agent', '0039_one_user_record_per_login'),
        ('core', '0113_calendarblock_sales_and_executive_sources'),
    ]

    operations = [
        migrations.RunPython(rescue, migrations.RunPython.noop),
    ]

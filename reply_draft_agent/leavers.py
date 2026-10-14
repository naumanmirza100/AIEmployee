"""Reply Draft's part when a dashboard login is switched off (core/leavers.py).

The company's reply mailbox, its mail and its drafts belong to the one login
that connected it, and every screen finds the mailbox through the company's
active logins. When that login was switched off, everyone else saw 'no mailbox
connected' and an empty inbox; connecting the same mailbox again was refused,
because the old connection still existed under the other login; Disconnect could
not find it either; and the five-minute reader went on reading it regardless.

Now the mailbox, the mail read from it and the drafts are handed to another
login of the company at the moment the first is switched off: the admin who
switched it off when there is one, otherwise an owner or admin, otherwise anyone
still active. Nothing is lost and nothing has to be connected again.

`move_mailbox` takes the model classes as arguments so that the migration which
rescues mailboxes stranded before this existed can use it with its own.
"""
import logging

logger = logging.getLogger(__name__)

#: Copied onto the new holder's own row when they already had this address connected for sending.
INBOX_SETTINGS = ('imap_host', 'imap_port', 'imap_use_ssl', 'imap_username', 'imap_password',
                  'enable_imap_sync', 'imap_sync_days', 'imap_sync_email_limit')


def move_mailbox(EmailAccount, InboxEmail, ReplyDraft, account, to_user_id):
    """Give one reply mailbox, with its mail and drafts, to another user record. Returns the row now in use.

    Uses update() throughout: EmailAccount.save() rearranges default and
    reply-mailbox flags, which is not wanted here."""
    from_user_id = account.owner_id
    if from_user_id == to_user_id:
        return account
    theirs = (EmailAccount.objects.filter(owner_id=to_user_id, email__iexact=account.email)
              .exclude(pk=account.pk).first())
    if theirs is None:
        EmailAccount.objects.filter(pk=account.pk).update(owner_id=to_user_id)
        kept = account
    else:
        # The new holder already has this address connected (for sending). An
        # address can be one person's row only once, so their row becomes the
        # reply mailbox and takes the inbox settings; the leaver's is unmarked.
        EmailAccount.objects.filter(pk=account.pk).update(is_reply_agent_account=False)
        EmailAccount.objects.filter(pk=theirs.pk).update(
            is_reply_agent_account=True, **{field: getattr(account, field) for field in INBOX_SETTINGS})
        kept = theirs
        already = set(InboxEmail.objects.filter(email_account_id=kept.pk).values_list('message_id', flat=True))
        (InboxEmail.objects.filter(email_account_id=account.pk).exclude(message_id__in=already)
         .update(email_account_id=kept.pk))
        ReplyDraft.objects.filter(email_account_id=account.pk).update(email_account_id=kept.pk)
    InboxEmail.objects.filter(owner_id=from_user_id).update(owner_id=to_user_id)
    ReplyDraft.objects.filter(owner_id=from_user_id).update(owner_id=to_user_id)
    return kept


def login_switched_off(company_user, by=None) -> str:
    """Hand this login's reply mailbox on. Says to whom."""
    from core.leavers import heir_for
    from core.logins import user_for
    from marketing_agent.models import EmailAccount
    from reply_draft_agent.models import InboxEmail, ReplyDraft

    if not company_user.login_user_id:
        return ''
    mailboxes = list(EmailAccount.objects.filter(owner_id=company_user.login_user_id, is_reply_agent_account=True))
    if not mailboxes:
        return ''
    heir = heir_for(company_user, by)
    if heir is None:
        return ('The reply mailbox %s is still under their login: the company has no other login to give it to.'
                % ', '.join(m.email for m in mailboxes))
    to_user = user_for(heir)
    for mailbox in mailboxes:
        move_mailbox(EmailAccount, InboxEmail, ReplyDraft, mailbox, to_user.pk)
    addresses = ', '.join(m.email for m in mailboxes)
    return (f'The reply mailbox {addresses}, with its mail and drafts, now belongs to '
            f'{heir.full_name or heir.email}.')

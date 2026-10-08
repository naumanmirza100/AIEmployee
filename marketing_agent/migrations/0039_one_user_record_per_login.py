# Marketing and Reply Draft now reach a dashboard login's user record through
# CompanyUser.login_user (core/logins.py) and no longer by matching its email
# address. Whatever they stored against the email-matched record has to follow,
# or a company's campaigns, leads and connected mailboxes would seem to vanish.
#
# For each dashboard login whose address no other company uses:
#   - not linked yet, and the email-matched record is free and not another
#     company's: link it. Nothing moves, because nothing needs to.
#   - otherwise: move what Marketing and Reply Draft stored on the
#     email-matched record to the login's own record (made here if need be).
# An address that is a dashboard login in two companies is left alone and
# logged: both wrote to one record, and whose rows are whose cannot be told
# from here. Safe to run again; reversing is a no-op.

import logging

from django.contrib.auth.hashers import make_password
from django.db import migrations

logger = logging.getLogger(__name__)

# (app, model, the field holding the user record, a field unique together with it)
OWNED = (
    ('marketing_agent', 'Campaign', 'owner', None),
    ('marketing_agent', 'Lead', 'owner', 'email'),
    ('marketing_agent', 'EmailAccount', 'owner', 'email'),
    ('marketing_agent', 'MarketResearch', 'created_by', None),
    ('marketing_agent', 'MarketingDocument', 'created_by', None),
    ('marketing_agent', 'NotificationRule', 'created_by', None),
    ('marketing_agent', 'MarketingNotification', 'user', None),
    ('marketing_agent', 'SavedGraphPrompt', 'created_by', None),
    ('reply_draft_agent', 'InboxEmail', 'owner', None),
    ('reply_draft_agent', 'ReplyDraft', 'owner', None),
)


def _rows(apps, user_id):
    for app, name, field, unique_with in OWNED:
        Model = apps.get_model(app, name)
        yield Model, field, unique_with, Model._base_manager.filter(**{f'{field}_id': user_id})


def _holds_anything(apps, user_id):
    return any(rows.exists() for _, _, _, rows in _rows(apps, user_id))


def _move(apps, old_id, new_id):
    """Repoint what one user record holds to another. Returns (moved, left behind)."""
    moved = left = 0
    for Model, field, unique_with, rows in _rows(apps, old_id):
        if unique_with:
            # A lead or mailbox the new record already has stays where it is.
            taken = set(Model._base_manager.filter(**{f'{field}_id': new_id}).values_list(unique_with, flat=True))
            left += rows.filter(**{f'{unique_with}__in': taken}).count()
            rows = rows.exclude(**{f'{unique_with}__in': taken})
        moved += rows.update(**{f'{field}_id': new_id})
    return moved, left


def link_and_move(apps, schema_editor):
    CompanyUser = apps.get_model('core', 'CompanyUser')
    UserProfile = apps.get_model('core', 'UserProfile')
    User = apps.get_model('auth', 'User')

    by_email = {}
    for login in CompanyUser.objects.order_by('id'):
        by_email.setdefault((login.email or '').strip().lower(), []).append(login)
    claimed = set(CompanyUser.objects.exclude(login_user=None).values_list('login_user_id', flat=True))

    def home_of(user_id):
        profile = (UserProfile.objects.filter(user_id=user_id)
                   .values_list('company_id', 'created_by_company_user__company_id').first())
        return (profile[0] or profile[1]) if profile else None

    for email, logins in by_email.items():
        if not email:
            continue
        # The record Marketing and Reply Draft have resolved for this address until now.
        used = User.objects.filter(email__iexact=email).order_by('id').first()
        if used is None:
            continue
        if len(logins) > 1:
            if _holds_anything(apps, used.id):
                logger.warning(
                    'Marketing/Reply Draft data on user record %s was shared by dashboard logins %s of '
                    'different companies. It was not moved: split it by hand.',
                    used.id, [login.id for login in logins])
            continue

        login = logins[0]
        if login.login_user_id == used.id:
            continue
        if login.login_user_id is None and used.id not in claimed and home_of(used.id) in (None, login.company_id):
            CompanyUser.objects.filter(pk=login.pk).update(login_user_id=used.id)
            claimed.add(used.id)
            continue
        # Another login's own record holds what is theirs. An empty one has nothing to move.
        if used.id in claimed or not _holds_anything(apps, used.id):
            continue
        target = login.login_user_id
        if target is None:
            # The matched record is somebody in another company. This login gets its own.
            names = (login.full_name or '').split()
            own, _ = User.objects.get_or_create(
                username=f'company_user_{login.id}',
                defaults={'email': login.email, 'password': make_password(None),
                          'first_name': names[0] if names else '', 'last_name': ' '.join(names[1:])})
            CompanyUser.objects.filter(pk=login.pk).update(login_user_id=own.id)
            claimed.add(own.id)
            target = own.id

        moved, left = _move(apps, used.id, target)
        if moved or left:
            logger.warning('Dashboard login %s: moved %s Marketing/Reply Draft rows from user record %s to %s%s.',
                           login.id, moved, used.id, target,
                           f'; {left} left behind because the new record already had them' if left else '')


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_agent', '0038_emailaccount_imap_sync_email_limit_and_more'),
        ('reply_draft_agent', '0013_inboxemail_attachments_fetched'),
        ('core', '0111_use_saved_own_keys'),
    ]

    operations = [
        migrations.RunPython(link_and_move, migrations.RunPython.noop),
    ]

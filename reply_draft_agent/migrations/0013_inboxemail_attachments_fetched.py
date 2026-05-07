# Generated to support the lazy-attachment optimization in sync_inbox.
#
# Adds InboxEmail.attachments_fetched. Sync no longer extracts attachments
# inline — it stamps the row with attachments_fetched=False, and a
# per-email endpoint fetches them on first open.
#
# Existing rows are backfilled to attachments_fetched=True so old emails
# (which DID have attachments extracted at sync time) don't trigger a
# wasteful re-download when the user opens them.

from django.db import migrations, models


def _backfill_existing_rows(apps, schema_editor):
    """Mark every pre-existing InboxEmail as already-fetched.

    Before this migration the sync command always extracted attachments
    inline, so any row that existed before today already has its
    attachments persisted. Flipping the flag True in bulk avoids an
    unnecessary IMAP round-trip the first time the user opens a
    historical email.
    """
    InboxEmail = apps.get_model('reply_draft_agent', 'InboxEmail')
    InboxEmail.objects.all().update(attachments_fetched=True)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('reply_draft_agent', '0012_rename_ppp_rda_inboxemail_acct_thread_idx_ppp_replydr_email_a_0867cd_idx'),
    ]

    operations = [
        migrations.AddField(
            model_name='inboxemail',
            name='attachments_fetched',
            field=models.BooleanField(
                default=False,
                help_text='True once attachments have been downloaded from IMAP. '
                          'False means sync stored only headers/body; call the '
                          'fetch-attachments endpoint when the user opens the email.',
            ),
        ),
        migrations.RunPython(_backfill_existing_rows, _noop_reverse),
    ]

# Generated to introduce explicit per-role visibility flags on
# EmailAccount. Before this migration, marketing's account list filtered
# only on owner — so any EmailAccount the user had created via the
# reply-draft "Add account" form would also appear in the marketing
# account picker. The new is_marketing_account flag plus a corresponding
# filter on the list endpoint fixes that leak.
#
# Backfill rule:
#   - Rows with is_reply_agent_account=True become is_marketing_account=False.
#     Those were created via reply_draft_agent.create_reply_account and
#     should belong to that agent only. If a user actually wants the
#     mailbox for marketing too, they can re-add it from the marketing
#     UI; the row's is_marketing_account flag will flip True (the
#     create_email_account upsert handles existing rows now).
#   - All other rows get is_marketing_account=True. Those are pre-
#     existing marketing-only accounts and stay visible exactly where
#     they are.
#
# This rule may briefly hide a dual-use account from the marketing list
# (specifically rows that the user previously promoted to dual-use via
# the older single-row upsert path). Re-adding from the marketing form
# restores it without losing campaign FKs because the upsert preserves
# the row identity. That's a small one-time cost for the structural
# fix.

from django.db import migrations, models


def _backfill_marketing_flag(apps, schema_editor):
    EmailAccount = apps.get_model('marketing_agent', 'EmailAccount')
    EmailAccount.objects.filter(is_reply_agent_account=True).update(is_marketing_account=False)
    EmailAccount.objects.filter(is_reply_agent_account=False).update(is_marketing_account=True)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_agent', '0034_alter_emailaccount_is_reply_agent_account'),
    ]

    operations = [
        migrations.AddField(
            model_name='emailaccount',
            name='is_marketing_account',
            field=models.BooleanField(
                default=True,
                help_text='Visible in the Marketing Agent account list. Marketing '
                          'campaign sending uses this row when set. Independent of '
                          'is_reply_agent_account; both can be True for dual-use.',
            ),
        ),
        migrations.RunPython(_backfill_marketing_flag, _noop_reverse),
    ]

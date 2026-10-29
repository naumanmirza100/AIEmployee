"""Encrypt the connected mailboxes' passwords at rest (CO-126).

The SMTP and IMAP passwords of every Marketing (and Reply Draft) mailbox were kept in clear text, while AI SDR's and
CRM Sync's credentials are encrypted. The two columns become the same EncryptedCharField AI SDR uses
(ai_sdr_agent 0025), and existing rows are encrypted here.

Not reversed: writing the passwords back in clear text is what this exists to stop. Reads tolerate clear text, so
the migration is safe to run again.
"""
from django.db import migrations

import ai_sdr_agent.fields


def encrypt_existing_passwords(apps, schema_editor):
    EmailAccount = apps.get_model('marketing_agent', 'EmailAccount')
    # Read through the field (clear text passes through), written back with .update(), which encrypts. No save().
    for pk, smtp, imap in list(EmailAccount.objects.values_list('pk', 'smtp_password', 'imap_password')):
        EmailAccount.objects.filter(pk=pk).update(smtp_password=smtp or '', imap_password=imap or '')


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_agent', '0041_social_posts_and_ad_copy_documents'),
        ('ai_sdr_agent', '0025_encrypt_campaign_smtp_password'),
    ]

    operations = [
        migrations.AlterField(
            model_name='emailaccount',
            name='smtp_password',
            field=ai_sdr_agent.fields.EncryptedCharField(help_text='SMTP password or app password', max_length=1000),
        ),
        migrations.AlterField(
            model_name='emailaccount',
            name='imap_password',
            field=ai_sdr_agent.fields.EncryptedCharField(blank=True, help_text='IMAP password', max_length=1000),
        ),
        migrations.RunPython(encrypt_existing_passwords, migrations.RunPython.noop),
    ]

"""Encrypt SDR campaign SMTP passwords at rest.

They were stored in clear text, so anyone with a database backup or console could
send mail as the customer. The column becomes an EncryptedCharField (Fernet, via
core/crypto_utils.py) and existing rows are encrypted here.

Not reversed: writing plaintext passwords back is what this exists to stop. Reads
tolerate legacy plaintext, so the migration is safe to re-run.
"""
from django.db import migrations

import ai_sdr_agent.fields


def encrypt_existing_passwords(apps, schema_editor):
    Campaign = apps.get_model('ai_sdr_agent', 'SDRCampaign')
    # Reading through the field returns plaintext (legacy rows pass through);
    # writing it back through .update() encrypts it. No signals, no save().
    for pk, password in list(
        Campaign.objects.exclude(smtp_password='').values_list('pk', 'smtp_password')
    ):
        Campaign.objects.filter(pk=pk).update(smtp_password=password)


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0024_sdrjoblock_sdrmeeting_is_manual'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sdrcampaign',
            name='smtp_password',
            field=ai_sdr_agent.fields.EncryptedCharField(blank=True, max_length=1000),
        ),
        migrations.RunPython(encrypt_existing_passwords, migrations.RunPython.noop),
    ]

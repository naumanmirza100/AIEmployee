# Flags an EmailAccount as the Reply Draft Agent inbox source.
# Enforces one-per-owner at the application layer via EmailAccount.save().

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_agent', '0031_campaign_email_account'),
    ]

    operations = [
        migrations.AddField(
            model_name='emailaccount',
            name='is_reply_agent_account',
            field=models.BooleanField(
                default=False,
                help_text='Designates this account as the Reply Draft Agent inbox source (one per owner).',
            ),
        ),
    ]

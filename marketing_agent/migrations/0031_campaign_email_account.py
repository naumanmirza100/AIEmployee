# Generated for campaign-level default email account.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_agent', '0030_emailaccount_imap_sync_days'),
    ]

    operations = [
        migrations.AddField(
            model_name='campaign',
            name='email_account',
            field=models.ForeignKey(
                blank=True,
                help_text='Default email account to send from for sequences in this campaign',
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name='campaigns',
                to='marketing_agent.emailaccount',
            ),
        ),
    ]

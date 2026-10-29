"""A failed send is tried again later, then given up (CO-122): it was tried every five minutes for ever."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_agent', '0042_encrypt_mailbox_passwords'),
    ]

    operations = [
        migrations.AddField(
            model_name='campaigncontact',
            name='send_failures',
            field=models.PositiveSmallIntegerField(default=0, help_text='Failed sends in a row'),
        ),
        migrations.AddField(
            model_name='campaigncontact',
            name='retry_after',
            field=models.DateTimeField(blank=True, null=True, help_text='No new try before this time'),
        ),
        migrations.AddField(
            model_name='campaigncontact',
            name='gave_up',
            field=models.BooleanField(default=False, help_text='Stopped after too many failed sends in a row'),
        ),
    ]

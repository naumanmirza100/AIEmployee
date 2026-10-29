"""Messages a Marketing-only mailbox's sync has read, so they are not downloaded again (CO-273)."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_agent', '0043_contact_send_failures'),
    ]

    operations = [
        migrations.CreateModel(
            name='CheckedInboxMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message_id', models.CharField(max_length=500)),
                ('checked_at', models.DateTimeField(auto_now_add=True)),
                ('email_account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                    related_name='checked_messages', to='marketing_agent.emailaccount')),
            ],
            options={
                'db_table': 'ppp_marketingagent_checkedinboxmessage',
                'unique_together': {('email_account', 'message_id')},
                'indexes': [models.Index(fields=['email_account', 'checked_at'],
                                         name='ppp_marketi_email_a_chk_idx')],
            },
        ),
    ]

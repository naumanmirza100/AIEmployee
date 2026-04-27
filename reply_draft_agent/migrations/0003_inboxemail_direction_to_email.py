# Restored to match the columns already present on existing DBs (django_migrations
# records this migration as applied on 2026-04-27 even though the file was deleted).
# Recreated so fresh DBs match the live schema and the model stays consistent with
# what the InboxEmail table actually holds.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reply_draft_agent', '0002_alter_replydraft_original_email_inboxemail_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='inboxemail',
            name='direction',
            field=models.CharField(default='in', help_text="'in' for received mail, 'out' for sent", max_length=4),
        ),
        migrations.AddField(
            model_name='inboxemail',
            name='to_email',
            field=models.EmailField(blank=True, default='', help_text='Mailbox the message was delivered to (the EmailAccount address)', max_length=254),
        ),
    ]

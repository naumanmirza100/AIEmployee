from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reply_draft_agent', '0009_replydraft_compose_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='replydraft',
            name='attempted_message_id',
            field=models.CharField(
                blank=True, db_index=True, default='', max_length=500,
            ),
        ),
    ]

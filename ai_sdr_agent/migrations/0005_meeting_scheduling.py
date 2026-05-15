from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0004_campaign_schedule'),
    ]

    operations = [
        migrations.AddField(
            model_name='sdrmeeting',
            name='prep_notes',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='sdrmeeting',
            name='scheduling_email_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='sdrmeeting',
            name='reminder_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='sdrmeeting',
            name='confirmed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0019_ticket_lifecycle_and_notes'),
    ]

    operations = [
        # ScheduledNotification: retry + DLQ fields
        migrations.AddField(
            model_name='schedulednotification',
            name='attempts',
            field=models.IntegerField(default=0, help_text='Number of send attempts made so far.'),
        ),
        migrations.AddField(
            model_name='schedulednotification',
            name='max_attempts',
            field=models.IntegerField(default=3, help_text='Upper bound on retry attempts before dead-lettering.'),
        ),
        migrations.AddField(
            model_name='schedulednotification',
            name='next_retry_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True,
                                       help_text='Earliest time the Celery worker may attempt the next retry.'),
        ),
        migrations.AddField(
            model_name='schedulednotification',
            name='last_error',
            field=models.TextField(blank=True, null=True,
                                   help_text='Error message from the most recent failed attempt.'),
        ),
        migrations.AddField(
            model_name='schedulednotification',
            name='dead_lettered_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True,
                                       help_text='When this notification exhausted retries and was dead-lettered.'),
        ),
        migrations.AddField(
            model_name='schedulednotification',
            name='deferred_reason',
            field=models.CharField(blank=True, default='', max_length=50,
                                   help_text="If non-empty, send was deferred (e.g. 'quiet_hours')."),
        ),
        migrations.AlterField(
            model_name='schedulednotification',
            name='status',
            field=models.CharField(
                max_length=20, default='pending',
                choices=[('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed'),
                         ('cancelled', 'Cancelled'), ('dead_lettered', 'Dead-lettered')],
            ),
        ),
        migrations.AddIndex(
            model_name='schedulednotification',
            index=models.Index(fields=['status', 'next_retry_at'], name='fl_sn_status_retry_idx'),
        ),
        migrations.AddIndex(
            model_name='schedulednotification',
            index=models.Index(fields=['dead_lettered_at'], name='fl_sn_dlq_idx'),
        ),

        # FrontlineNotificationPreferences: quiet hours
        migrations.AddField(
            model_name='frontlinenotificationpreferences',
            name='timezone_name',
            field=models.CharField(default='UTC', max_length=64,
                                   help_text="IANA timezone name for quiet-hour calculations (e.g. 'America/New_York')."),
        ),
        migrations.AddField(
            model_name='frontlinenotificationpreferences',
            name='quiet_hours_enabled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='frontlinenotificationpreferences',
            name='quiet_hours_start',
            field=models.CharField(default='22:00', max_length=5,
                                   help_text='HH:MM 24h, local to timezone_name.'),
        ),
        migrations.AddField(
            model_name='frontlinenotificationpreferences',
            name='quiet_hours_end',
            field=models.CharField(default='08:00', max_length=5,
                                   help_text='HH:MM 24h. If end < start the window wraps past midnight.'),
        ),
    ]

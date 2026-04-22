from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0022_document_async_and_lifecycle'),
        ('core', '0040_company_frontline_allowed_origins'),
    ]

    operations = [
        migrations.AddField(
            model_name='frontlinemeeting',
            name='company',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='frontline_meetings', to='core.company',
                help_text='Tenant that owns this meeting.',
            ),
        ),
        migrations.AddField(
            model_name='frontlinemeeting',
            name='timezone_name',
            field=models.CharField(default='UTC', max_length=64,
                                   help_text='IANA tz name for display; scheduled_at is always UTC in DB.'),
        ),
        migrations.AddField(
            model_name='frontlinemeeting',
            name='reminder_24h_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='frontlinemeeting',
            name='reminder_15m_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='frontlinemeeting',
            name='action_items',
            field=models.JSONField(blank=True, default=list,
                                   help_text='Action items extracted from transcript.'),
        ),
        migrations.AddIndex(
            model_name='frontlinemeeting',
            index=models.Index(fields=['company', 'scheduled_at'], name='fl_mt_co_sched_idx'),
        ),
        migrations.AddIndex(
            model_name='frontlinemeeting',
            index=models.Index(fields=['scheduled_at', 'reminder_24h_sent_at'], name='fl_mt_sched_r24_idx'),
        ),
        migrations.AddIndex(
            model_name='frontlinemeeting',
            index=models.Index(fields=['scheduled_at', 'reminder_15m_sent_at'], name='fl_mt_sched_r15_idx'),
        ),
    ]

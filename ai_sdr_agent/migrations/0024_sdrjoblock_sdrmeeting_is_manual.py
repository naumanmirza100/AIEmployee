import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0023_sdrcampaignenrollment_last_reply_message_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='sdrmeeting',
            name='is_manual',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='SDRJobLock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=64, unique=True)),
                ('locked_until', models.DateTimeField(default=django.utils.timezone.now)),
                ('last_run_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={'db_table': 'sdr_job_lock'},
        ),
    ]

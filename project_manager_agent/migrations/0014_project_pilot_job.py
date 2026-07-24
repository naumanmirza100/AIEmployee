# Generated migration for ProjectPilotJob (async Project Pilot uploads).

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0074_task_recurrence'),
        ('project_manager_agent', '0013_notification_channels_templates'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProjectPilotJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('company_id', models.IntegerField(help_text='Denormalised company id')),
                ('chat_id', models.CharField(blank=True, default='', help_text='PM Project Pilot chat id at enqueue time (if any)', max_length=64)),
                ('project_id', models.IntegerField(blank=True, help_text='PM Project id scope (if any)', null=True)),
                ('user_prompt', models.TextField(blank=True, default='', help_text="User's typed instruction alongside the file")),
                ('file_path', models.CharField(help_text='Path (relative to MEDIA_ROOT) of the saved upload', max_length=1024)),
                ('file_name', models.CharField(help_text='Original client-side filename', max_length=512)),
                ('chat_history', models.JSONField(blank=True, default=list, help_text='Snapshot of the prior chat turns')),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('processing', 'Processing'), ('ready', 'Ready'), ('failed', 'Failed')], default='queued', max_length=20)),
                ('error_message', models.TextField(blank=True, default='')),
                ('answer', models.TextField(blank=True, default='')),
                ('action_results', models.JSONField(blank=True, default=list)),
                ('cannot_do', models.TextField(blank=True, default='')),
                ('timing_ms', models.JSONField(blank=True, default=dict, help_text='Per-phase timing: text_extract, llm, actions, total')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('company_user', models.ForeignKey(help_text='Company user who submitted the upload.', on_delete=models.deletion.CASCADE, related_name='project_pilot_jobs', to='core.companyuser')),
            ],
            options={
                'verbose_name': 'Project Pilot Job',
                'verbose_name_plural': 'Project Pilot Jobs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='projectpilotjob',
            index=models.Index(fields=['company_user', '-created_at'], name='ppilot_job_cu_created_idx'),
        ),
        migrations.AddIndex(
            model_name='projectpilotjob',
            index=models.Index(fields=['company_id', 'status'], name='ppilot_job_company_status_idx'),
        ),
    ]

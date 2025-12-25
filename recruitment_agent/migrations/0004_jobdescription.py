# Generated manually for JobDescription model

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment_agent', '0003_interview_confirmation_token'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='JobDescription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(help_text='Job title/position name', max_length=255)),
                ('description', models.TextField(help_text='Full job description text')),
                ('keywords_json', models.TextField(blank=True, help_text='Parsed keywords and requirements from JobDescriptionParserAgent (JSON)', null=True)),
                ('is_active', models.BooleanField(default=True, help_text='Whether this job description is currently active/being used')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_job_descriptions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Job Description',
                'verbose_name_plural': 'Job Descriptions',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='jobdescription',
            index=models.Index(fields=['is_active', '-created_at'], name='recruitment_is_acti_idx'),
        ),
        migrations.AddField(
            model_name='cvrecord',
            name='job_description',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cv_records', to='recruitment_agent.jobdescription'),
        ),
    ]


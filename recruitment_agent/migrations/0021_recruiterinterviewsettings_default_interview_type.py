# Generated manually for RecruiterInterviewSettings.default_interview_type

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment_agent', '0020_interview_outcome'),
    ]

    operations = [
        migrations.AddField(
            model_name='recruiterinterviewsettings',
            name='default_interview_type',
            field=models.CharField(
                choices=[('ONLINE', 'Online'), ('ONSITE', 'Onsite')],
                default='ONLINE',
                help_text='Interview type for this job. Sent to candidates in invitation email.',
                max_length=10,
            ),
        ),
    ]

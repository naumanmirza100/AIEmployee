from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment_agent', '0030_add_interview_feedback_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='cvrecord',
            name='job_application',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cv_record',
                to='recruitment_agent.jobapplication',
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    """The minimum fit score for INTERVIEW (client decision Q3, 27 Nov 2026)."""

    dependencies = [
        ('recruitment_agent', '0049_roles'),
    ]

    operations = [
        migrations.AddField(
            model_name='recruiterqualificationsettings',
            name='min_fit_score',
            field=models.IntegerField(
                default=50,
                help_text='Minimum fit score (0-100) for INTERVIEW. Below it an INTERVIEW becomes HOLD. 0 = off. Default: 50'),
        ),
    ]

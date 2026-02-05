# Generated manually for Interview.outcome

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment_agent', '0019_alter_recruiterinterviewsettings_company_user_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='interview',
            name='outcome',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'Not set'),
                    ('ONSITE_INTERVIEW', 'Onsite Interview'),
                    ('HIRED', 'Hired'),
                    ('PASSED', 'Passed'),
                    ('REJECTED', 'Rejected'),
                ],
                help_text='Decision after interview (when status is COMPLETED)',
                max_length=30,
                null=True,
            ),
        ),
    ]

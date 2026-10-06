"""Remember which logins offboarding switched off.

HR's Deactivate changed a status and left both of the person's logins working.
Offboarding now switches them off (hr_agent/access.py). This field records
which ones, so reactivating someone turns back on exactly those and nothing
that was already off for another reason.

Nobody already offboarded is touched by this migration: their logins stay as
they are until someone saves that record again.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr_agent', '0017_accrual_runs_and_balance_merge'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='access_ended',
            field=models.JSONField(
                blank=True, default=dict,
                help_text='Logins switched off when this person was offboarded (hr_agent/access.py). Empty = none.'),
        ),
    ]

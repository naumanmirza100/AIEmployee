# Sales calls and executive meetings join the shared busy-time table
# (core.scheduling, sources 'sdr' and 'exec'). They were left out when it was
# built, so either could be booked over an interview, a meeting or leave.
# Choices only; no database change.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0112_company_timezone_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='calendarblock',
            name='source',
            field=models.CharField(choices=[('pm', 'Project Manager'), ('hr', 'HR'), ('frontline', 'Frontline'), ('recruitment', 'Recruitment interview'), ('leave', 'Approved leave'), ('sdr', 'Sales call'), ('exec', 'Executive meeting')], max_length=20),
        ),
    ]

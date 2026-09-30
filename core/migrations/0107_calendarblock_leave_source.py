# Approved leave joins the shared busy-time table (core.scheduling, source 'leave').
# Choices only; no database change.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0106_calendarblock_recruitment_source'),
    ]

    operations = [
        migrations.AlterField(
            model_name='calendarblock',
            name='source',
            field=models.CharField(choices=[('pm', 'Project Manager'), ('hr', 'HR'), ('frontline', 'Frontline'), ('recruitment', 'Recruitment interview'), ('leave', 'Approved leave')], max_length=20),
        ),
    ]

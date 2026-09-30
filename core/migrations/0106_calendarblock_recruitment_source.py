# Interviews join the shared busy-time table (core.scheduling, source 'recruitment').
# Choices only; no database change.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0105_auth_user_email_index'),
    ]

    operations = [
        migrations.AlterField(
            model_name='calendarblock',
            name='source',
            field=models.CharField(choices=[('pm', 'Project Manager'), ('hr', 'HR'), ('frontline', 'Frontline'), ('recruitment', 'Recruitment interview')], max_length=20),
        ),
    ]

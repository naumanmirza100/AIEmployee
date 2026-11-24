# Joins the two 0123s made side by side on 23-24 Nov 2026: the personal calendars (#412, already applied on the
# server) and the system backups (#411). Each kept its own name, so a database that applied either one stays right.
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0123_personal_calendars'),
        ('core', '0123_system_backup'),
    ]

    operations = []

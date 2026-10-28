# Written by hand on 2026-10-28: an overdue or due-today alert is raised once per due date (CO-169).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('meeting_agent', '0011_alter_executivetask_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='meetingactionitem',
            name='overdue_alerted_for',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='executivetask',
            name='overdue_alerted_for',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='executivetask',
            name='due_today_alerted_for',
            field=models.DateField(blank=True, null=True),
        ),
    ]

# An interview's Google Calendar event was created once and forgotten: its id
# was not kept, so a moved or cancelled interview stayed in Google at the old
# time. The interview now keeps the event's id and the time it stands at.
# Events made before this have no stored id and cannot be corrected.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment_agent', '0042_interview_hr_employee'),
    ]

    operations = [
        migrations.AddField(
            model_name='interview',
            name='google_event_id',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='interview',
            name='google_event_state',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
    ]

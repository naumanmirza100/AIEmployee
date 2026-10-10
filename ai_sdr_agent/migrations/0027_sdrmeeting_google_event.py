# A sales call's Google Calendar event was created once and forgotten, so a
# call that moved or was cancelled stayed in Google at its old time. The call
# now keeps the event's id and the time it stands at. Events made before this
# have no stored id and cannot be corrected.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0026_backfill_do_not_email'),
    ]

    operations = [
        migrations.AddField(
            model_name='sdrmeeting',
            name='google_event_id',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='sdrmeeting',
            name='google_event_state',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
    ]

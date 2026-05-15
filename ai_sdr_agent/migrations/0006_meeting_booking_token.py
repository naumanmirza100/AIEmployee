import uuid
from django.db import migrations, models


def populate_booking_tokens(apps, schema_editor):
    SDRMeeting = apps.get_model('ai_sdr_agent', 'SDRMeeting')
    for meeting in SDRMeeting.objects.filter(booking_token__isnull=True):
        meeting.booking_token = uuid.uuid4()
        meeting.save(update_fields=['booking_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0005_meeting_scheduling'),
    ]

    operations = [
        # Step 1: add nullable column (no unique constraint yet)
        migrations.AddField(
            model_name='sdrmeeting',
            name='booking_token',
            field=models.UUIDField(null=True, blank=True, editable=False),
        ),
        # Step 2: fill each existing row with its own unique UUID
        migrations.RunPython(populate_booking_tokens, migrations.RunPython.noop),
        # Step 3: now safe to add the unique constraint
        migrations.AlterField(
            model_name='sdrmeeting',
            name='booking_token',
            field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False),
        ),
    ]

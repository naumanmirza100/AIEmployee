from django.db import migrations


def deduplicate_meetings(apps, schema_editor):
    """Keep one meeting per enrollment (prefer sent > latest created_at), delete the rest."""
    SDRMeeting = apps.get_model('ai_sdr_agent', 'SDRMeeting')
    from collections import defaultdict
    by_enrollment = defaultdict(list)
    for m in SDRMeeting.objects.filter(enrollment__isnull=False).order_by('created_at'):
        by_enrollment[m.enrollment_id].append(m)
    for enrollment_id, meetings in by_enrollment.items():
        if len(meetings) <= 1:
            continue
        # Keep the one that already has scheduling_email_sent_at, else the latest
        keeper = next((m for m in meetings if m.scheduling_email_sent_at), meetings[-1])
        for m in meetings:
            if m.pk != keeper.pk:
                m.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0006_meeting_booking_token'),
    ]

    operations = [
        migrations.RunPython(deduplicate_meetings, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name='sdrmeeting',
            unique_together={('enrollment',)},
        ),
    ]

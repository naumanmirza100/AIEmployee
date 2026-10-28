"""Interviews set to 'Rescheduled' by hand become 'Scheduled' (CO-114).

The status could only be chosen from the menu; nothing set it by itself, and an interview in it got no reminder and
was never completed. The menu no longer offers it.
"""
from django.db import migrations


def to_scheduled(apps, schema_editor):
    Interview = apps.get_model('recruitment_agent', 'Interview')
    Interview.objects.filter(status='RESCHEDULED').update(status='SCHEDULED')


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment_agent', '0044_cvrecord_rejection_emailed_at'),
    ]

    operations = [
        migrations.RunPython(to_scheduled, migrations.RunPython.noop),
    ]

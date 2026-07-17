from django.db import migrations


def critical_to_high(apps, schema_editor):
    """'critical' priority is being retired in favour of low/medium/high — pull
    any existing critical tasks down to 'high'."""
    ExecutiveTask = apps.get_model('meeting_agent', 'ExecutiveTask')
    ExecutiveTask.objects.filter(priority='critical').update(priority='high')


def noop(apps, schema_editor):
    # No reverse — we can't tell which 'high' rows used to be 'critical'.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('meeting_agent', '0007_executivetask_source_action_item'),
    ]

    operations = [
        migrations.RunPython(critical_to_high, noop),
    ]

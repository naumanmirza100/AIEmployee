"""Leads of a sequence stayed "New" after their emails and replies: only the old one-off sender moved them. From now on
Lead.move_to does (a send makes Contacted, interest Qualified, a request to stop Lost); this applies the same rule to
the leads already emailed or answered. A status further along, a person's own, is left as it is."""
from django.db import migrations

SENT = ('sent', 'delivered', 'opened', 'clicked')


def fill_in(apps, schema_editor):
    Lead = apps.get_model('marketing_agent', 'Lead')
    Lead.objects.filter(status='new', email_history__status__in=SENT,
                        email_history__email_template__isnull=False).update(status='contacted')
    Lead.objects.filter(status__in=('new', 'contacted'),
                        replies__interest_level__in=('positive', 'requested_info')).update(status='qualified')
    Lead.objects.filter(status__in=('new', 'contacted', 'qualified'),
                        replies__interest_level='unsubscribe').update(status='lost')
    Lead.objects.filter(status='new', replies__isnull=False).update(status='contacted')


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_agent', '0047_marketing_document_image'),
    ]

    operations = [
        migrations.RunPython(fill_in, migrations.RunPython.noop),
    ]

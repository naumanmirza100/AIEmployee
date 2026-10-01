# Frontline's email switches move to the one notification settings page
# (core.notification_settings). Carry over every switch someone turned off.
# `email_enabled` was the master for Frontline's automation emails (and what
# its unsubscribe link turned off), so off there turns off those topics.
# `in_app_enabled` was never read by anything, so there is nothing to carry.

from django.db import migrations

AUTOMATION = ('ticket_created', 'ticket_updated', 'automation_emails')


def carry_over(apps, schema_editor):
    Preferences = apps.get_model('Frontline_agent', 'FrontlineNotificationPreferences')
    Setting = apps.get_model('core', 'NotificationSetting')
    rows = []
    for p in Preferences.objects.all().iterator():
        off = set()
        if not p.email_enabled:
            off.update(AUTOMATION)
        if not p.ticket_created_email:
            off.add('ticket_created')
        if not p.ticket_updated_email:
            off.add('ticket_updated')
        if not p.workflow_email_enabled:
            off.add('automation_emails')
        # Ticket-assigned emails are off by default in the new settings already.
        rows += [Setting(company_user_id=p.company_user_id, topic=t, in_app=True, email=False) for t in sorted(off)]
    Setting.objects.bulk_create(rows, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0047_ticket_pm_task'),
        ('core', '0108_notificationsetting'),
    ]

    operations = [
        migrations.RunPython(carry_over, migrations.RunPython.noop),
    ]

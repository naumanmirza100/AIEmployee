# A leave request used to be sent to the employee's manager even when that
# manager had only a My Space login. Deciding leave takes a dashboard login, so
# the manager saw nothing and the request was on nobody's list. New requests
# are no longer sent to someone who cannot decide them
# (hr_agent/leave_helpers.py). This frees the ones already waiting: with no
# named approver they are put before the HR admins.

from django.db import migrations


def free_stuck(apps, schema_editor):
    CompanyUser = apps.get_model('core', 'CompanyUser')
    Employee = apps.get_model('hr_agent', 'Employee')
    LeaveRequest = apps.get_model('hr_agent', 'LeaveRequest')

    active_ids, active_emails = set(), set()
    for login_id, company_id, email in CompanyUser.objects.filter(is_active=True).values_list('id', 'company_id', 'email'):
        active_ids.add(login_id)
        if email:
            active_emails.add((company_id, email.strip().lower()))

    approver_ids = set(LeaveRequest.objects.filter(status='pending').exclude(approver=None)
                       .values_list('approver_id', flat=True))
    cannot_decide = []
    for approver in Employee.objects.filter(pk__in=approver_ids):
        if approver.company_user_id:
            able = approver.company_user_id in active_ids
        else:
            able = (approver.company_id, (approver.work_email or '').strip().lower()) in active_emails
        if not able:
            cannot_decide.append(approver.pk)
    if cannot_decide:
        LeaveRequest.objects.filter(status='pending', approver_id__in=cannot_decide).update(approver=None)


class Migration(migrations.Migration):

    dependencies = [
        ('hr_agent', '0019_link_dashboard_logins'),
        ('core', '0111_use_saved_own_keys'),
    ]

    operations = [
        migrations.RunPython(free_stuck, migrations.RunPython.noop),
    ]

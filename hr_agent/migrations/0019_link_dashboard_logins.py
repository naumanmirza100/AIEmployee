# The shared calendar, My work and HR self-service treat a dashboard login as a
# person through Employee.company_user, and nothing ever set it. From now on it
# is set from the employee's record and by itself when the addresses match
# (hr_agent/logins.py). This sets it for the records that match already: same
# company, same address, and neither side linked to anything else.

from django.db import migrations


def link_by_email(apps, schema_editor):
    CompanyUser = apps.get_model('core', 'CompanyUser')
    Employee = apps.get_model('hr_agent', 'Employee')

    taken = set(Employee.objects.exclude(company_user=None).values_list('company_user_id', flat=True))
    logins = {}
    for login in CompanyUser.objects.exclude(email='').order_by('id'):
        key = (login.company_id, (login.email or '').strip().lower())
        logins.setdefault(key, login.id)

    for employee in Employee.objects.filter(company_user=None).exclude(work_email='').order_by('id'):
        login_id = logins.get((employee.company_id, (employee.work_email or '').strip().lower()))
        if login_id and login_id not in taken:
            Employee.objects.filter(pk=employee.pk).update(company_user_id=login_id)
            taken.add(login_id)


class Migration(migrations.Migration):

    dependencies = [
        ('hr_agent', '0018_employee_access_ended'),
        ('core', '0111_use_saved_own_keys'),
    ]

    operations = [
        migrations.RunPython(link_by_email, migrations.RunPython.noop),
    ]

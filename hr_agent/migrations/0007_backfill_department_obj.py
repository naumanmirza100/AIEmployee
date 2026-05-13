"""Backfill Department rows from the legacy `Employee.department` string.

For every (company, distinct non-empty department string) pair, create a
Department row and point every Employee with that string to it. Empty strings
are left null. This is reversible by clearing `Employee.department_obj`.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    Employee = apps.get_model('hr_agent', 'Employee')
    Department = apps.get_model('hr_agent', 'Department')

    pairs = (Employee.objects
             .exclude(department='')
             .values_list('company_id', 'department')
             .distinct())
    cache: dict[tuple[int, str], int] = {}
    for company_id, name in pairs:
        clean = (name or '').strip()
        if not clean:
            continue
        dept, _ = Department.objects.get_or_create(
            company_id=company_id, name=clean[:120],
            defaults={'is_active': True},
        )
        cache[(company_id, clean)] = dept.id

    # Stream-update employees in chunks to avoid loading every row at once.
    qs = Employee.objects.exclude(department='').filter(department_obj__isnull=True)
    for emp in qs.iterator(chunk_size=500):
        key = (emp.company_id, (emp.department or '').strip())
        dept_id = cache.get(key)
        if dept_id:
            Employee.objects.filter(pk=emp.pk).update(department_obj_id=dept_id)


def backwards(apps, schema_editor):
    Employee = apps.get_model('hr_agent', 'Employee')
    Employee.objects.exclude(department_obj__isnull=True).update(department_obj=None)


class Migration(migrations.Migration):
    dependencies = [
        ('hr_agent', '0006_department'),
    ]
    operations = [
        migrations.RunPython(forwards, backwards),
    ]

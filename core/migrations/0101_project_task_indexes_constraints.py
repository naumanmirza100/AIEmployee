"""DATA-2 — database-level integrity and indexes for Project / Task.

Order is deliberate. MySQL/MariaDB DDL is not transactional, so a failure midway
leaves earlier operations committed. The step most likely to fail — adding a
CHECK constraint over rows that already violate it — therefore comes last, and
the data it would trip over is repaired first.

  1. Backfill Project.company where it is NULL. The Project Pilot upload path
     used to omit `company`, so those projects were invisible to every
     company-scoped query.
  2. Repair rows that would violate the new constraints, so this migration can
     be applied to an existing database (e.g. the legacy SQL Server) rather than
     only a fresh one:
       * budget_min > budget_max  -> swap the two (entered backwards)
       * progress outside 0..100  -> clamp into range
  3. Composite indexes for the hot query shapes.
  4. The CHECK constraints.

Deliberately NOT added — both would change behaviour, not just enforce it:
  * unique (company, name): duplicate names are allowed on purpose —
    create_project_manual returns 409 and the user may resubmit with
    confirm_duplicate_name=true.
  * start_date <= deadline: no code path validates this today, and a constraint
    would reject a date edit made in two separate requests.
"""
from django.db import migrations, models
from django.db.models import F, Q


def backfill_project_company(apps, schema_editor):
    Project = apps.get_model('core', 'Project')
    fixed = 0
    for project in (Project.objects
                    .filter(company__isnull=True, created_by_company_user__isnull=False)
                    .select_related('created_by_company_user')
                    .only('id', 'created_by_company_user__company_id')):
        company_id = project.created_by_company_user.company_id
        if company_id:
            Project.objects.filter(pk=project.pk).update(company_id=company_id)
            fixed += 1
    if fixed:
        print(f"\n    backfilled company on {fixed} project(s)")


def repair_constraint_violations(apps, schema_editor):
    Project = apps.get_model('core', 'Project')
    Task = apps.get_model('core', 'Task')

    swapped = 0
    for p in Project.objects.filter(budget_min__isnull=False, budget_max__isnull=False,
                                    budget_min__gt=F('budget_max')).only('id', 'budget_min', 'budget_max'):
        Project.objects.filter(pk=p.pk).update(budget_min=p.budget_max, budget_max=p.budget_min)
        swapped += 1

    clamped = (Task.objects.filter(progress_percentage__lt=0).update(progress_percentage=0)
               + Task.objects.filter(progress_percentage__gt=100).update(progress_percentage=100))

    if swapped or clamped:
        print(f"\n    repaired {swapped} inverted budget(s), clamped {clamped} progress value(s)")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0100_merge_20260907_2145'),
    ]

    operations = [
        migrations.RunPython(backfill_project_company, migrations.RunPython.noop),
        migrations.RunPython(repair_constraint_violations, migrations.RunPython.noop),

        migrations.AddIndex(
            model_name='project',
            index=models.Index(fields=['created_by_company_user', '-created_at'],
                               name='proj_creator_created_idx'),
        ),
        migrations.AddIndex(
            model_name='project',
            index=models.Index(fields=['company', 'status'], name='proj_company_status_idx'),
        ),
        migrations.AddIndex(
            model_name='task',
            index=models.Index(fields=['project', 'status'], name='task_project_status_idx'),
        ),
        migrations.AddIndex(
            model_name='task',
            index=models.Index(fields=['assignee', 'status'], name='task_assignee_status_idx'),
        ),
        migrations.AddIndex(
            model_name='task',
            index=models.Index(fields=['project', 'due_date'], name='task_project_due_idx'),
        ),

        migrations.AddConstraint(
            model_name='project',
            constraint=models.CheckConstraint(
                check=Q(budget_min__isnull=True) | Q(budget_max__isnull=True)
                      | Q(budget_min__lte=F('budget_max')),
                name='proj_budget_min_lte_max',
            ),
        ),
        migrations.AddConstraint(
            model_name='task',
            constraint=models.CheckConstraint(
                check=Q(progress_percentage__isnull=True)
                      | Q(progress_percentage__gte=0, progress_percentage__lte=100),
                name='task_progress_0_100',
            ),
        ),
    ]

"""Make leave accrual safe to redeliver, and unify the balance rows.

Two findings from MDS/HR_AGENT_AUDIT.md:

**HR-DATA-1.** `accrue_leave_balances` gated on `policy.last_run_at`, stamped
only after crediting every employee, with no transaction. Celery runs with
`acks_late`, so a worker killed mid-loop had the task redelivered and credited
the already-credited a second time. `LeaveAccrualRun` claims the period first,
so a redelivery collides with the unique constraint and stops.

**HR-DATA-3.** `LeaveBalance` is unique on
`(employee, leave_type, period_start)`, and the writers disagreed about the
key: approvals and withdrawals wrote the row for January 1st of the leave's
year, accrual wrote the row with `period_start=NULL`, and manual adjustment
took whichever sorted first. Those are different rows, so days accrued never
met days used — a balance could show a full entitlement and a full year of
usage at the same time, and `remaining` was wrong on both rows.

The data step folds each `period_start=NULL` row into the current leave-year
row by **adding** its numbers, so nothing is lost, then deletes it. Where no
year row exists the NULL row is simply re-dated. It does not reverse: putting
the split back would re-break the balances.
"""
from datetime import date

from django.db import migrations, models
import django.db.models.deletion


def merge_null_period_balances(apps, schema_editor):
    LeaveBalance = apps.get_model('hr_agent', 'LeaveBalance')
    year_start = date(date.today().year, 1, 1)

    null_rows = LeaveBalance.objects.filter(period_start__isnull=True)
    for row in null_rows.iterator(chunk_size=500):
        year_row = (LeaveBalance.objects
                    .filter(employee_id=row.employee_id, leave_type=row.leave_type,
                            period_start=year_start)
                    .first())
        if year_row is None:
            # Nothing to merge into — just date it.
            row.period_start = year_start
            row.save(update_fields=['period_start'])
            continue

        year_row.accrued_days = (year_row.accrued_days or 0) + (row.accrued_days or 0)
        year_row.used_days = (year_row.used_days or 0) + (row.used_days or 0)
        year_row.carried_over_days = (
            (year_row.carried_over_days or 0) + (row.carried_over_days or 0))
        year_row.save(update_fields=['accrued_days', 'used_days', 'carried_over_days'])
        row.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('hr_agent', '0016_backfill_employee_logins'),
    ]

    operations = [
        migrations.CreateModel(
            name='LeaveAccrualRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('period_key', models.CharField(
                    help_text="The period this run credits: '2026-09' (monthly), "
                              "'2026-W38' (biweekly) or '2026' (annual).",
                    max_length=32)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(
                    blank=True, null=True,
                    help_text='Null means it started and never finished.')),
                ('employees_credited', models.IntegerField(default=0)),
                ('policy', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='runs', to='hr_agent.leaveaccrualpolicy')),
            ],
            options={'ordering': ['-started_at']},
        ),
        migrations.AddConstraint(
            model_name='leaveaccrualrun',
            constraint=models.UniqueConstraint(fields=('policy', 'period_key'),
                                               name='hr_accrual_run_unique_period'),
        ),
        migrations.RunPython(merge_null_period_balances, migrations.RunPython.noop),
    ]

"""Give every employee login an Employee row.

HR can only invite people it has an Employee row for, and meeting clash checks
(core/scheduling) rely on the Employee → login link. Two gaps left some logins
without a row:

  * the sync signal only ran when `UserProfile.company` was set, but most
    profiles are linked through the dashboard login that created them
    (`created_by_company_user`);
  * a second login with a blank email failed the unique (company, work_email).

The signal is fixed; this backfills rows for logins that already exist. It uses
the historical models, so no HR workflow ("employee hired") is triggered.
"""
from django.db import migrations

NO_EMAIL_DOMAIN = 'no-email.invalid'


def backfill(apps, schema_editor):
    UserProfile = apps.get_model('core', 'UserProfile')
    Employee = apps.get_model('hr_agent', 'Employee')

    linked = set(Employee.objects.filter(user__isnull=False).values_list('user_id', flat=True))
    created = relinked = 0
    profiles = (UserProfile.objects
                .select_related('user', 'created_by_company_user')
                .exclude(user__is_superuser=True))
    for prof in profiles.iterator():
        user = prof.user
        if user is None or user.pk in linked:
            continue
        company_id = prof.company_id or (
            prof.created_by_company_user.company_id if prof.created_by_company_user_id else None)
        if not company_id:
            continue

        email = (user.email or '').strip().lower()
        if email:
            unlinked = Employee.objects.filter(company_id=company_id, work_email__iexact=email,
                                               user__isnull=True).first()
            if unlinked is not None:
                unlinked.user_id = user.pk
                unlinked.save(update_fields=['user'])
                linked.add(user.pk)
                relinked += 1
                continue
            if Employee.objects.filter(company_id=company_id, work_email__iexact=email).exists():
                email = ''  # address already belongs to another employee row

        full_name = f'{user.first_name} {user.last_name}'.strip() or user.username or email
        Employee.objects.create(
            company_id=company_id,
            user_id=user.pk,
            full_name=full_name[:255],
            work_email=email or f'user{user.pk}@{NO_EMAIL_DOMAIN}',
            employment_status='active',
        )
        linked.add(user.pk)
        created += 1

    if created or relinked:
        print(f"\n    Employee rows: {created} created, {relinked} linked to an existing row")


class Migration(migrations.Migration):

    dependencies = [
        ('hr_agent', '0015_hr_meeting_response_flow'),
        ('core', '0102_calendar_block'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]

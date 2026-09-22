"""Give every dashboard login an explicit employee-login row, and make each
company's first login an admin.

Two audit items (MDS/FRONTLINE_AGENT_AUDIT.md):

  **FL-SEC-3.** `CompanyUser` -> `auth.User` used to be resolved by email
  alone. `CompanyUser` is unique per `(company, email)`, so the same address
  in two companies collapsed onto one `auth.User`, and every query scoped by
  `created_by` / `assigned_to` instead of `company` crossed the tenant
  boundary. The link is explicit from now on; this backfill keeps today's
  mapping for whoever owns it, and leaves the loser of a collision unlinked so
  they get a fresh row on next use.

  **FL-SEC-7.** The credential and destructive endpoints become admin-only,
  but `register_company_user` gave every account `role='company_user'` and
  nothing in the product can change a role. Promoting each company's earliest
  login means existing accounts keep the access they have today.

Both backfills are re-runnable and reverse to a no-op: reversing would have to
guess which mapping was ours, and getting that wrong detaches real tickets.
"""
from django.db import migrations, models
import django.db.models.deletion


def backfill_login_user(apps, schema_editor):
    CompanyUser = apps.get_model('core', 'CompanyUser')
    UserProfile = apps.get_model('core', 'UserProfile')
    User = apps.get_model('auth', 'User')

    claimed = set(
        CompanyUser.objects.filter(login_user__isnull=False)
        .values_list('login_user_id', flat=True)
    )

    for company_user in CompanyUser.objects.filter(login_user__isnull=True).order_by('id'):
        email = (company_user.email or '').strip()
        if not email:
            continue
        candidates = [u for u in User.objects.filter(email__iexact=email).order_by('id')[:5]
                      if u.id not in claimed]
        if not candidates:
            continue

        # Prefer the login whose profile sits in this company: when two
        # tenants share an address, that is the unambiguous owner.
        chosen = None
        for user in candidates:
            profile_company_id = (UserProfile.objects.filter(user_id=user.id)
                                  .values_list('company_id', flat=True).first())
            if profile_company_id and profile_company_id == company_user.company_id:
                chosen = user
                break
        if chosen is None:
            chosen = candidates[0]

        claimed.add(chosen.id)
        CompanyUser.objects.filter(pk=company_user.pk).update(login_user_id=chosen.id)


def promote_first_login(apps, schema_editor):
    CompanyUser = apps.get_model('core', 'CompanyUser')
    admin_roles = ('owner', 'admin')
    seen_companies = set()

    for company_user in CompanyUser.objects.all().order_by('company_id', 'created_at', 'id'):
        if company_user.company_id in seen_companies:
            continue
        seen_companies.add(company_user.company_id)
        if company_user.role not in admin_roles:
            CompanyUser.objects.filter(pk=company_user.pk).update(role='admin')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0102_calendar_block'),
    ]

    operations = [
        migrations.AddField(
            model_name='companyuser',
            name='login_user',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='company_logins', to='auth.user',
            ),
        ),
        migrations.RunPython(backfill_login_user, migrations.RunPython.noop),
        migrations.RunPython(promote_first_login, migrations.RunPython.noop),
    ]

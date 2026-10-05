"""A leaver's logins follow their HR status.

HR's Deactivate said "access is revoked" and changed one status field. Both of
the person's logins kept working, and they stayed in every list for assigning
tasks, tickets, meetings and interviews, because those lists look only at
whether the login is active.

`sync_access` runs on every Employee save (hr_agent/signals.py), so it does not
matter how the status changed: the Deactivate button, an edit, a workflow step.

  * Offboarded: the employee login, the dashboard login (the linked one, or the
    one with the same email) and the hidden user behind it are switched off
    and their tokens deleted, so open sessions end too.
  * Back from offboarded: exactly what was switched off comes back on. Nothing
    else does: a login that was already off for another reason stays off.

`Employee.access_ended` remembers what was switched off. One thing is never
done: switching off a company's last active admin, which would lock it out.
"""
import logging

from django.contrib.auth import get_user_model
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Dashboard roles that can manage the company. The last active one is never switched off.
ADMIN_ROLES = ('owner', 'admin')


def is_gone(employee) -> bool:
    return employee.employment_status == 'offboarded' or employee.anonymized_at is not None


def end_access(employee) -> dict:
    """Switch off this person's logins and remember which. Returns the record."""
    from rest_framework.authtoken.models import Token
    from core.models import CompanyUser, CompanyUserToken
    from hr_agent.handover import dashboard_login
    from hr_agent.models import Employee

    User = get_user_model()
    record = {'at': timezone.now().isoformat(), 'user_ids': [], 'company_user_id': None, 'kept': ''}
    user_ids = {employee.user_id} if employee.user_id else set()

    login = dashboard_login(employee)
    if login is not None and login.is_active:
        other_admin = (CompanyUser.objects
                       .filter(company_id=login.company_id, is_active=True, role__in=ADMIN_ROLES)
                       .exclude(pk=login.pk).exists())
        if login.role in ADMIN_ROLES and not other_admin:
            # Their dashboard login stays, and so does the user it acts as.
            record['kept'] = 'last_admin'
            user_ids.discard(login.login_user_id)
        else:
            CompanyUser.objects.filter(pk=login.pk).update(is_active=False)
            CompanyUserToken.objects.filter(company_user=login).delete()
            record['company_user_id'] = login.pk
            if login.login_user_id:
                user_ids.add(login.login_user_id)

    # Platform staff are not a company's to switch off.
    for user in User.objects.filter(pk__in=user_ids, is_active=True, is_staff=False, is_superuser=False):
        User.objects.filter(pk=user.pk).update(is_active=False)
        Token.objects.filter(user=user).delete()
        record['user_ids'].append(user.pk)

    Employee.objects.filter(pk=employee.pk).update(access_ended=record)
    employee.access_ended = record
    logger.info('HR access ended for employee %s: users=%s dashboard_login=%s kept=%s',
                employee.pk, record['user_ids'], record['company_user_id'], record['kept'] or '-')
    return record


def restore_access(employee) -> dict:
    """Switch back on exactly what `end_access` switched off."""
    from core.models import CompanyUser
    from hr_agent.models import Employee

    record = dict(employee.access_ended or {})
    get_user_model().objects.filter(pk__in=record.get('user_ids') or []).update(is_active=True)
    if record.get('company_user_id'):
        CompanyUser.objects.filter(pk=record['company_user_id'],
                                   company_id=employee.company_id).update(is_active=True)
    Employee.objects.filter(pk=employee.pk).update(access_ended={})
    employee.access_ended = {}
    logger.info('HR access restored for employee %s: users=%s dashboard_login=%s',
                employee.pk, record.get('user_ids'), record.get('company_user_id'))
    return record


def sync_access(employee):
    """Bring the logins in line with the HR status. Does nothing when they already are."""
    if is_gone(employee):
        if not employee.access_ended:
            end_access(employee)
    elif employee.access_ended:
        restore_access(employee)


def summary(employee) -> dict:
    """What the screens say after a status change."""
    record = employee.access_ended or {}
    return {
        'employee_login_off': bool(record.get('user_ids')),
        'dashboard_login_off': bool(record.get('company_user_id')),
        'kept': record.get('kept') or '',
    }

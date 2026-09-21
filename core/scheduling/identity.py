"""Map each agent's idea of a person onto the one identity clash checks use:
an employee login (`auth.User`) that belongs to the company.

  * PM participants and Frontline attendees are already `auth.User`s.
  * HR attendees are `Employee` rows, linked to a login through `Employee.user`.
  * Organizers are dashboard logins (`CompanyUser`). A dashboard login counts as
    an employee only when it maps to exactly one employee login in the same
    company — through HR's explicit `Employee.company_user` link, or failing
    that, the same email address. Anything ambiguous maps to nobody, so a
    wrong guess can never block someone else's calendar.
"""
from __future__ import annotations

from core.tenancy import members_of


def login_user_id_for_company_user(company_user) -> int | None:
    company_id = getattr(company_user, 'company_id', None)
    if not company_id:
        return None
    members = members_of(company_id)

    try:
        from hr_agent.models import Employee
    except ImportError:  # pragma: no cover — HR app not installed
        Employee = None
    if Employee is not None:
        linked = (Employee.objects
                  .filter(company_id=company_id, company_user=company_user, user__isnull=False)
                  .values_list('user_id', flat=True).first())
        if linked and members.filter(pk=linked).exists():
            return linked

    email = (getattr(company_user, 'email', '') or '').strip()
    if not email:
        return None
    ids = list(members.filter(email__iexact=email).values_list('id', flat=True)[:2])
    return ids[0] if len(ids) == 1 else None


def login_user_ids_for_employees(employee_ids) -> dict[int, int]:
    """{employee_id: user_id} for the given Employees that have a login.

    Membership is not checked here; `sync` filters every seat through
    `members_of` in one query.
    """
    ids = [e for e in employee_ids if e]
    if not ids:
        return {}
    from hr_agent.models import Employee
    return dict(Employee.objects
                .filter(pk__in=ids, user__isnull=False)
                .values_list('id', 'user_id'))


def member_ids(company_id, user_ids) -> set[int]:
    """The subset of `user_ids` that are active employee logins of the company."""
    ids = {int(u) for u in user_ids if u}
    if not company_id or not ids:
        return set()
    return set(members_of(company_id).filter(pk__in=ids).values_list('id', flat=True))

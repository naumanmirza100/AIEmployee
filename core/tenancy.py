"""Tenant-boundary checks for people: who may be assigned to, or invited into,
a company's work.

Before this module each view answered that question itself, and the answers
drifted. `update_company_task` got it right; `create_task_manual` did a bare
`User.objects.get(id=assignee_id)`; the Project Pilot's LLM-driven actions took
whatever ID the model emitted; the end-user API allowed assignment whenever
*both* users lacked a `profile.company` — which, since most profiles are linked
through `created_by_company_user` instead, was most of the time. Every one of
those let a company assign tasks to, or send meeting invites to, users belonging
to another tenant.

The rule lives here now, once:

    A user belongs to a company if they are active and their UserProfile points
    at it — directly (`profile.company`) or through the CompanyUser who created
    them (`profile.created_by_company_user.company`).

Nothing here trusts the caller or an LLM to have picked a valid ID. A prompt
that says "assignee_id MUST be one of ..." is an instruction, not enforcement.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q


class AssigneeNotAllowed(Exception):
    """The requested user doesn't exist, is inactive, or isn't in this company."""


def company_of_user(user):
    """The Company an end user (auth.User) belongs to, or None."""
    if user is None:
        return None
    profile = getattr(user, 'profile', None)
    if profile is None:
        return None
    if profile.company_id:
        return profile.company
    if profile.created_by_company_user_id:
        return profile.created_by_company_user.company
    return None


def members_of(company=None, *, company_user=None):
    """Queryset of active auth.Users that belong to `company`.

    `company_user` is a fallback scope for the rare CompanyUser with no company
    link: users that CompanyUser created. With neither, the result is empty —
    "no company on either side" must never mean "anyone".
    """
    User = get_user_model()
    qs = User.objects.filter(is_active=True)
    if company is not None:
        return qs.filter(
            Q(profile__company=company)
            | Q(profile__created_by_company_user__company=company)
        ).distinct()
    if company_user is not None:
        return qs.filter(profile__created_by_company_user=company_user).distinct()
    return qs.none()


def resolve_member(user_id, *, company=None, company_user=None):
    """Return the User with `user_id` if they belong to the company.

    Raises AssigneeNotAllowed otherwise — including for IDs that don't exist, so
    callers can't be used as a user-enumeration oracle (a foreign user and a
    missing one look identical).
    """
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise AssigneeNotAllowed('Invalid user id.')
    user = members_of(company, company_user=company_user).filter(pk=user_id).first()
    if user is None:
        raise AssigneeNotAllowed('That user is not a member of your company.')
    return user


def scope_for_company_user(company_user):
    """Convenience: the (company, company_user) pair for a dashboard login."""
    return getattr(company_user, 'company', None), company_user


# ---------------------------------------------------------------------------
# Object scoping for dashboard logins (CompanyUser).
#
# A project belongs to a CompanyUser's tenant if its `company` is theirs, OR they
# created it. The second clause is not redundant: Project Pilot file uploads
# used to save projects with company=NULL, and a `company=company`-only filter
# made those projects — and everything under them — impossible to delete or
# edit through the API.
# ---------------------------------------------------------------------------

def _project_q(company_user, prefix=''):
    company = getattr(company_user, 'company', None)
    q = Q(**{f'{prefix}created_by_company_user': company_user})
    if company is not None:
        q |= Q(**{f'{prefix}company': company})
    return q


def projects_for_company_user(company_user):
    from core.models import Project
    return Project.objects.filter(_project_q(company_user))


def tasks_for_company_user(company_user):
    from core.models import Task
    return Task.objects.filter(_project_q(company_user, prefix='project__'))

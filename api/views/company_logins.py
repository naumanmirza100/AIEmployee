"""A company's dashboard logins and their roles.

GET   company/logins          every dashboard login of the caller's company.
POST  company/logins          {email, full_name, role} adds one. Owner or admin.
PATCH company/logins/<id>     {role} and/or {is_active}. Owner or admin.

A company's first login is made an admin and that was the end of it. No screen
could change a role, so `hr_agent`, `frontline_agent` and `manager` were values
nobody could be given, and since the sign-up page stopped asking for an email
a second dashboard login could not be created at all. Every admin-only action
and every alert "to the admins" therefore came down to the founder's login.

A new login gets no password here. The person sets their own with "Forgot
password" on the company sign-in page, which emails a code to their address,
so nobody else ever knows it. The invitation email says so.
"""
import logging

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyAdmin, IsCompanyUserOnly
from core.models import CompanyUser, CompanyUserToken
from core.notification_utils import notify_company_users

logger = logging.getLogger(__name__)

ADMIN_ROLES = IsCompanyAdmin.ADMIN_ROLES

#: The roles this screen offers, with what each one changes. `CompanyUser.role`
#: has more values; the others change nothing in the product today.
ROLES = (
    ('admin', 'Admin', 'Runs the account: billing, AI keys, logins and roles, and the admin actions of every agent.'),
    ('hr_agent', 'HR admin', 'Sees and decides everything in HR: leave, documents, workflows, offboarding.'),
    ('frontline_agent', 'Support', 'Alerted when a customer asks for a person, and sees them on My work.'),
    ('manager', 'Manager', 'Day-to-day use of every agent, and manager-level HR documents.'),
    ('company_user', 'Member', 'Day-to-day use of every agent the company has.'),
)
ASSIGNABLE = tuple(key for key, _, _ in ROLES)
LABELS = {key: label for key, label, _ in ROLES} | {'owner': 'Owner'}


def _row(login, viewer):
    return {
        'id': login.id,
        'email': login.email,
        'full_name': login.full_name,
        'role': login.role,
        'role_label': LABELS.get(login.role, (login.role or '').replace('_', ' ').title()),
        'is_active': login.is_active,
        'is_you': login.id == viewer.id,
        'last_login': login.last_login.isoformat() if login.last_login else None,
        'has_signed_in': login.last_login is not None,
    }


def _seat_ids(company_id, candidates=None):
    """The rows that stand in for employees in executive meetings and tasks (meeting_agent's seats): switched
    off, never signed in, an employee's address in this company, and taking part in something. They showed here
    as switched-off logins, and one click on the switch made a real login the employee could claim (CO-209)."""
    from core.models import UserProfile
    from meeting_agent.models import ExecutiveMeetingParticipant, ExecutiveTask, MeetingActionItem
    rows = (candidates if candidates is not None else
            CompanyUser.objects.filter(company_id=company_id, is_active=False, last_login__isnull=True))
    rows = [r for r in rows if not r.is_active and r.last_login is None and r.email]
    if not rows:
        return set()
    employees = {e.lower() for e in UserProfile.objects.filter(
        company_id=company_id, user__is_active=True, user__email__in=[r.email for r in rows])
        .values_list('user__email', flat=True)}
    ids = [r.id for r in rows if r.email.lower() in employees]
    used = (set(ExecutiveMeetingParticipant.objects.filter(company_user_id__in=ids).values_list('company_user_id', flat=True))
            | set(ExecutiveTask.assignees.through.objects.filter(companyuser_id__in=ids).values_list('companyuser_id', flat=True))
            | set(MeetingActionItem.objects.filter(assignee_id__in=ids).values_list('assignee_id', flat=True)))
    return used


def _page(viewer):
    logins = [login for login in
              CompanyUser.objects.filter(company_id=viewer.company_id).order_by('-is_active', 'full_name', 'id')]
    seats = _seat_ids(viewer.company_id, logins)
    return {
        'logins': [_row(login, viewer) for login in logins if login.id not in seats],
        'roles': [{'key': key, 'label': label, 'description': text} for key, label, text in ROLES],
        'can_manage': viewer.role in ADMIN_ROLES,
    }


def _error(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({'status': 'error', 'message': message}, status=code)


def _other_admins(login):
    return (CompanyUser.objects.filter(company_id=login.company_id, is_active=True, role__in=ADMIN_ROLES)
            .exclude(pk=login.pk).count())


def _invite(login, invited_by):
    """Tell the new person they have a login and how to set its password."""
    site = (getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
    where = f"{site}/company/login" if site else 'the company sign-in page'
    company = login.company.name
    try:
        send_mail(
            subject=f"You have a login to {company}",
            message=(f"Hi {login.full_name},\n\n"
                     f"{invited_by.full_name or invited_by.email} has given you a login to {company}'s dashboard.\n\n"
                     f"To set your password, open {where}, choose \"Forgot password\" and enter this address "
                     f"({login.email}). A code is emailed to you; with it you choose your own password.\n\n"
                     f"- {company}"),
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
            recipient_list=[login.email], fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Could not email the invitation for dashboard login %s", login.id)
        return False


@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def company_logins(request):
    viewer = request.user
    if request.method == 'GET':
        return Response({'status': 'success', 'data': _page(viewer)})

    if viewer.role not in ADMIN_ROLES:
        return _error('Only an owner or admin of the company can add a login.', status.HTTP_403_FORBIDDEN)
    data = request.data or {}
    email = str(data.get('email') or '').strip().lower()
    full_name = str(data.get('full_name') or '').strip()[:255]
    role = str(data.get('role') or 'company_user').strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        return _error('Enter a valid email address.')
    if not full_name:
        return _error("Enter the person's name.")
    if role not in ASSIGNABLE:
        return _error(f"Choose one of these roles: {', '.join(LABELS[r] for r in ASSIGNABLE)}.")
    # One dashboard login per address, across every company: sign-in and
    # "Forgot password" find a login by its address alone.
    existing = CompanyUser.objects.filter(email__iexact=email).first()
    if existing is not None and existing.company_id == viewer.company_id and existing.id in _seat_ids(viewer.company_id, [existing]):
        # An employee who took part in executive meetings: the row they took part through becomes their login,
        # and their meetings and tasks come with it (CO-209). It was refused as "already has a login".
        existing.full_name, existing.role, existing.is_active = full_name, role, True
        existing.password_hash = make_password(None)
        existing.save(update_fields=['full_name', 'role', 'is_active', 'password_hash'])
        login = existing
    elif existing is not None:
        return _error('That address already has a dashboard login.')
    else:
        login = CompanyUser.objects.create(
            company_id=viewer.company_id, email=email, full_name=full_name, role=role, is_active=True,
            password_hash=make_password(None),      # no password until they set their own
        )
    emailed = _invite(login, viewer)
    logger.info('Company %s: login %s added by %s as %s', viewer.company_id, login.id, viewer.id, role)
    return Response({
        'status': 'success', 'data': _page(viewer), 'invited': emailed,
        'message': (f'{full_name} can now sign in. An email telling them how to set a password was sent to {email}.'
                    if emailed else
                    f'{full_name} was added, but the invitation email could not be sent. Ask them to use '
                    f'"Forgot password" on the company sign-in page with {email}.'),
    }, status=status.HTTP_201_CREATED)


@api_view(['PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def company_login(request, login_id):
    viewer = request.user
    if viewer.role not in ADMIN_ROLES:
        return _error('Only an owner or admin of the company can change a login.', status.HTTP_403_FORBIDDEN)
    data = request.data or {}

    with transaction.atomic():
        # Locked, so two admins demoting each other at once cannot both pass
        # the "another admin remains" check.
        target = (CompanyUser.objects.select_for_update()
                  .filter(company_id=viewer.company_id, pk=login_id).first())
        if target is None:
            return _error('That login was not found.', status.HTTP_404_NOT_FOUND)
        was_role, was_active = target.role, target.is_active
        if data.get('is_active') and not was_active and target.id in _seat_ids(viewer.company_id, [target]):
            return _error(f'{target.full_name or target.email} takes part in executive meetings as an employee, '
                          'not as a login. To let them sign in to the dashboard, add them on this page with '
                          'their address.')
        new_role = str(data['role']).strip().lower() if 'role' in data else was_role
        new_active = bool(data['is_active']) if 'is_active' in data else was_active
        if 'role' in data and new_role != was_role and new_role not in ASSIGNABLE:
            return _error(f"Choose one of these roles: {', '.join(LABELS[r] for r in ASSIGNABLE)}.")

        stops_running_the_account = (was_active and was_role in ADMIN_ROLES
                                     and (not new_active or new_role not in ADMIN_ROLES))
        if stops_running_the_account:
            if target.id == viewer.id:
                return _error('You cannot take admin rights from yourself or switch your own login off. '
                              'Ask another admin to do it.')
            if _other_admins(target) == 0:
                return _error("This is the company's only admin. Make someone else an admin first.")

        changed = []
        if new_role != was_role:
            target.role = new_role
            changed.append('role')
        if new_active != was_active:
            target.is_active = new_active
            changed.append('is_active')
        if changed:
            target.save(update_fields=changed)
            if 'is_active' in changed and not new_active:
                CompanyUserToken.objects.filter(company_user=target).delete()     # signed out everywhere

    # What that login was running in each agent is paused or handed on (core/leavers.py).
    tidied = []
    if 'is_active' in changed and not target.is_active:
        from core.leavers import login_switched_off
        tidied = login_switched_off(target, by=viewer)
    if changed:
        logger.info('Company %s: login %s changed by %s: role %s -> %s, active %s -> %s', viewer.company_id,
                    target.id, viewer.id, was_role, target.role, was_active, target.is_active)
    if 'role' in changed and target.is_active:
        notify_company_users(
            [target], title=f'Your role is now {LABELS.get(target.role, target.role)}',
            message=f'{viewer.full_name or viewer.email} changed it from {LABELS.get(was_role, was_role)}.',
            link='/company/settings/team', kind='company_role_changed', email=False)
    return Response({'status': 'success', 'data': _page(viewer), 'changed': bool(changed),
                     'switched_off': tidied})

"""A person's logins, as their HR record sees them.

One person can have two logins: an employee login (My Space) and a dashboard
login. The HR record is where they meet, through `Employee.user` and
`Employee.company_user`. The shared calendar, My work and HR's own self-service
all read the second link to treat a dashboard login as that person. Nothing
ever set it. So leave approved for someone who works from a dashboard login
blocked nothing: the other agents still booked them, and Frontline said there
was no calendar to check.

The link is now set by an HR admin from the employee's record (`link`), and by
itself when the two have the same email address (`link_by_email`).
"""
import logging

logger = logging.getLogger(__name__)


class LinkRefused(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


def describe(employee) -> dict:
    """What the employee's record shows about their logins."""
    user = employee.user if employee.user_id else None
    login = employee.company_user if employee.company_user_id else None
    return {
        'employee_login': user and {'user_id': user.id, 'username': user.username, 'is_active': user.is_active},
        'dashboard_login': login and {'id': login.id, 'full_name': login.full_name, 'email': login.email,
                                      'is_active': login.is_active},
        # Busy time is kept against employee logins, so only someone with one can be placed on the calendar.
        'on_calendar': bool(user),
    }


def dashboard_logins(company) -> list:
    """The company's dashboard logins, each with the record it is linked to."""
    from core.models import CompanyUser
    from hr_agent.models import Employee
    linked = dict(Employee.objects.filter(company=company, company_user__isnull=False)
                  .values_list('company_user_id', 'full_name'))
    return [{'id': login.id, 'full_name': login.full_name, 'email': login.email, 'is_active': login.is_active,
             'linked_to': linked.get(login.id)}
            for login in CompanyUser.objects.filter(company=company).order_by('full_name', 'id')]


def link(employee, company_user):
    """Join a dashboard login to an employee's record; None takes the link off.

    A login belongs to one record. Returns a warning to show, or ''.
    """
    from hr_agent.models import Employee
    if company_user is not None:
        if company_user.company_id != employee.company_id:
            raise LinkRefused('Login not found.', 404)
        holder = Employee.objects.filter(company_user=company_user).exclude(pk=employee.pk).first()
        if holder is not None:
            raise LinkRefused(f'That login is already linked to {holder.full_name}. Take it off their record first.', 409)
    # update(): this is not a change to the person, so no workflow should start from it.
    Employee.objects.filter(pk=employee.pk).update(company_user=company_user)
    employee.company_user = company_user
    if company_user is not None and not employee.user_id:
        return (f'{employee.full_name} has no employee login yet, so the calendar cannot place them: '
                'their leave will not block bookings until they have one.')
    return ''


def link_by_email(employee) -> bool:
    """Link the dashboard login with the employee's work email, if it is free. Same company, same address: the same person."""
    from core.models import CompanyUser
    from hr_agent.models import Employee
    email = (employee.work_email or '').strip()
    if employee.company_user_id or not email:
        return False
    login = (CompanyUser.objects.filter(company_id=employee.company_id, email__iexact=email,
                                        hr_employee__isnull=True).first())
    if login is None:
        return False
    Employee.objects.filter(pk=employee.pk).update(company_user=login)
    employee.company_user = login
    return True


def link_login_by_email(company_user) -> bool:
    """The same, starting from a dashboard login that has just been made."""
    from hr_agent.models import Employee
    email = (company_user.email or '').strip()
    if not email or Employee.objects.filter(company_user=company_user).exists():
        return False
    employee = (Employee.objects.filter(company_id=company_user.company_id, work_email__iexact=email,
                                        company_user__isnull=True).first())
    if employee is None:
        return False
    Employee.objects.filter(pk=employee.pk).update(company_user=company_user)
    return True

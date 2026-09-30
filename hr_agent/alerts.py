"""HR events that need someone, sent to the bell of the logins who act on them.

HR used to raise no in-app alerts at all: a new leave request or a workflow
waiting for approval sat in the HR dashboard until someone happened to look.
These go to the company feed via `core.notification_utils`.
"""
from __future__ import annotations

import logging

from core.models import CompanyUser
from core.notification_utils import notify_company_users

logger = logging.getLogger(__name__)

#: Dashboard roles that administer HR for their company (`_is_hr_admin`).
HR_ADMIN_ROLES = ('hr_agent', 'owner', 'admin')


def hr_admins(company_id):
    return list(CompanyUser.objects.filter(company_id=company_id, is_active=True,
                                           role__in=HR_ADMIN_ROLES))


def leave_request_submitted(leave_request):
    """To HR admins and the employee's manager; not to whoever asked."""
    emp = leave_request.employee
    if not emp or not emp.company_id:
        return 0
    recipients = hr_admins(emp.company_id)
    manager = emp.manager if emp.manager_id else None
    if manager is not None and manager.company_user_id:
        recipients.append(manager.company_user)
    recipients = [cu for cu in recipients if cu.id != emp.company_user_id]

    days = float(leave_request.days_requested or 0)
    days_text = f"{days:g} day{'' if days == 1 else 's'}"
    when = (f"{leave_request.start_date:%d %b}" if leave_request.start_date == leave_request.end_date
            else f"{leave_request.start_date:%d %b} – {leave_request.end_date:%d %b}")
    return notify_company_users(
        recipients,
        title=f"Leave request from {emp.full_name}",
        message=(f"{leave_request.get_leave_type_display()}, {when} ({days_text}). "
                 "Waiting for a decision."),
        link='/hr/dashboard?tab=leave',
        kind='hr_leave_request',
    )


def new_starter_from_recruitment(employee, added_by='', onboarding=()):
    """To HR admins, when Recruitment hands over someone it has hired."""
    when = f", starting {employee.start_date:%d %b %Y}" if employee.start_date else ''
    by = f" Added by {added_by}." if added_by else ''
    runs = (f" Onboarding started: {', '.join(onboarding)}." if onboarding
            else ' No onboarding workflow is set up in HR yet.')
    return notify_company_users(
        hr_admins(employee.company_id),
        title=f"New hire from Recruitment: {employee.full_name}",
        message=f"{employee.job_title or 'New starter'}{when}.{by}{runs}",
        link='/hr/dashboard?tab=employees',
        kind='hr_new_starter',
    )


def workflow_awaiting_approval(execution):
    """To HR admins, whenever a workflow run stops for approval — before it
    starts, or at an approval step partway through."""
    workflow = execution.workflow
    if not workflow or not workflow.company_id:
        return 0
    who = (execution.context_data or {}).get('employee_name')
    return notify_company_users(
        hr_admins(workflow.company_id),
        title=f"Workflow waiting for approval: {execution.workflow_name or workflow.name}",
        message=(f"For {who}. " if who else '') + 'Approve or reject it under Workflows.',
        link='/hr/dashboard?tab=workflows',
        severity='warning',
        kind='hr_workflow_approval',
    )

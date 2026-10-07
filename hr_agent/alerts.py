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


def leave_summary(leave_request):
    """E.g. "Vacation, 12 Oct – 14 Oct (3 days)"."""
    days = float(leave_request.days_requested or 0)
    days_text = f"{days:g} day{'' if days == 1 else 's'}"
    when = (f"{leave_request.start_date:%d %b}" if leave_request.start_date == leave_request.end_date
            else f"{leave_request.start_date:%d %b} – {leave_request.end_date:%d %b}")
    return f"{leave_request.get_leave_type_display()}, {when} ({days_text})"


def leave_request_submitted(leave_request):
    """To HR admins and the employee's manager; not to whoever asked."""
    emp = leave_request.employee
    if not emp or not emp.company_id:
        return 0
    recipients = hr_admins(emp.company_id)
    # The manager's dashboard login, by the link on their HR record or, as
    # nothing ever sets that link, by their work address.
    from hr_agent.handover import dashboard_login
    manager_login = dashboard_login(emp.manager) if emp.manager_id else None
    if manager_login is not None:
        recipients.append(manager_login)
    own_login = dashboard_login(emp)
    recipients = [cu for cu in recipients if own_login is None or cu.id != own_login.id]

    return notify_company_users(
        recipients,
        title=f"Leave request from {emp.full_name}",
        message=f"{leave_summary(leave_request)}. Waiting for a decision.",
        link='/hr/dashboard?tab=leave',
        kind='hr_leave_request',
    )


def run_outcome(execution) -> str:
    """How a workflow run stands, in a few words: 'done', 'failed: ...'."""
    result = execution.result_data if isinstance(execution.result_data, dict) else {}
    if execution.status == 'failed':
        return f"failed: {execution.error_message or 'a step did not work'}"
    if execution.status == 'awaiting_approval':
        return 'waiting for approval'
    if execution.status == 'completed':
        skipped = int(result.get('steps_skipped') or 0)
        return f"done, {skipped} step{'' if skipped == 1 else 's'} skipped" if skipped else 'done'
    return 'running'


def new_starter_from_recruitment(employee, added_by='', onboarding=()):
    """To HR admins, when Recruitment hands over someone it has hired.

    Says how each onboarding run really went. It used to say "Onboarding
    started" for a run that had already failed.
    """
    from hr_agent.models import HRWorkflowExecution
    when = f", starting {employee.start_date:%d %b %Y}" if employee.start_date else ''
    by = f" Added by {added_by}." if added_by else ''
    ran = [f"{e.workflow_name} ({run_outcome(e)})"
           for e in HRWorkflowExecution.objects.filter(employee_id=employee.id).order_by('id')]
    if ran:
        runs = f" Onboarding: {'; '.join(ran)}."
    elif onboarding:
        runs = f" Onboarding started: {', '.join(onboarding)}."
    else:
        runs = ' No onboarding workflow is set up in HR yet.'
    return notify_company_users(
        hr_admins(employee.company_id),
        title=f"New hire from Recruitment: {employee.full_name}",
        message=f"{employee.job_title or 'New starter'}{when}.{by}{runs}",
        link='/hr/dashboard?tab=employees',
        kind='hr_new_starter',
    )


def no_longer_hired(employee, outcome, changed_by=''):
    """To HR admins, when Recruitment changes its mind about someone it handed
    over. HR still has their record, and their onboarding may be running:
    Recruitment used to say nothing."""
    now = (outcome or '').replace('_', ' ').capitalize() or 'no decision'
    by = f" Changed by {changed_by}." if changed_by else ''
    return notify_company_users(
        hr_admins(employee.company_id),
        title=f"No longer hired: {employee.full_name}",
        message=(f"Recruitment changed {employee.full_name} from Hired to {now}.{by} Their HR record is "
                 "still there, and any onboarding that started is still running. Check whether they are joining."),
        link='/hr/dashboard?tab=employees',
        kind='hr_hire_withdrawn',
        severity='warning',
    )


def workflow_needs_a_look(execution):
    """To HR admins, when a run fails or finishes without one of its steps.
    Nobody was told before, so a new hire could go without an orientation
    meeting and HR would not know. Once per run: the run remembers it was
    said, so a later save of the same row does not say it again."""
    workflow = execution.workflow
    if not workflow or not workflow.company_id:
        return 0
    result = execution.result_data if isinstance(execution.result_data, dict) else {}
    missed = [r for r in (result.get('results') or []) if r.get('skipped') or (r.get('done') is False)]
    if execution.status != 'failed' and not missed:
        return 0
    if result.get('alerted_for') == execution.status:
        return 0
    result = {**result, 'alerted_for': execution.status}
    type(execution).objects.filter(pk=execution.pk).update(result_data=result)
    execution.result_data = result
    who = (execution.context_data or {}).get('employee_name')
    why = '; '.join(str(r.get('error') or r.get('type') or 'a step')[:160] for r in missed[:3])
    failed = execution.status == 'failed'
    return notify_company_users(
        hr_admins(workflow.company_id),
        title=(f"Workflow failed: {execution.workflow_name or workflow.name}" if failed
               else f"Workflow finished with a step skipped: {execution.workflow_name or workflow.name}"),
        message=((f"For {who}. " if who else '') + (why or execution.error_message or 'A step did not work.')
                 + ' See the run under Workflows.')[:500],
        link='/hr/dashboard?tab=workflows',
        severity='warning',
        kind='hr_workflow_failed',
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

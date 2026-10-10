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


def leave_dates(leave_request):
    """E.g. "12 Oct – 14 Oct", or "12 Oct" for one day."""
    if leave_request.start_date == leave_request.end_date:
        return f"{leave_request.start_date:%d %b}"
    return f"{leave_request.start_date:%d %b} – {leave_request.end_date:%d %b}"


def leave_summary(leave_request):
    """E.g. "Vacation, 12 Oct – 14 Oct (3 days)"."""
    days = float(leave_request.days_requested or 0)
    days_text = f"{days:g} day{'' if days == 1 else 's'}"
    return f"{leave_request.get_leave_type_display()}, {leave_dates(leave_request)} ({days_text})"


#: The leave screen opens on "Pending for me". A request is only there for its
#: named approver; everyone else finds it under "All", and their own under "Mine".
LEAVE_FOR_ME = '/hr/dashboard?tab=leave'
LEAVE_ALL = '/hr/dashboard?tab=leave&view=all'
LEAVE_MINE = '/hr/dashboard?tab=leave&view=mine'

#: What became of a request, as its title and as a clause.
_DECISIONS = {
    'approved': ('Leave approved', 'was approved'),
    'rejected': ('Leave declined', 'was declined'),
    'cancelled': ('Leave request cancelled', 'was cancelled'),
    'withdrawn': ('Leave withdrawn', 'was withdrawn'),
}


def leave_decided(leave_request, decided_by=None, note='', booked=0):
    """To the person whose leave it is, when someone else settles it: approved
    or declined, a waiting request cancelled for them, approved leave withdrawn.

    Nobody was told before. Someone with a dashboard login hears in that bell
    (and by email, as they have chosen). Someone with only My Space has no
    leave screen, so this is how they learn the answer: their bell, and an
    email. `decided_by` is the dashboard login that did it; what a person does
    to their own request they are not told about. `booked` is how many
    meetings they are still booked into during approved leave
    (`hr_agent.leave_clashes`), so that they know too.
    """
    emp = leave_request.employee
    words = _DECISIONS.get(leave_request.status)
    if not emp or not emp.company_id or words is None:
        return 0
    from hr_agent.handover import dashboard_login
    own_login = dashboard_login(emp)
    if decided_by is not None and own_login is not None and own_login.id == decided_by.id:
        return 0
    by = f" by {decided_by.full_name}" if decided_by is not None and decided_by.full_name else ''
    note = (note or '').strip()
    title = f"{words[0]}: {leave_dates(leave_request)}"
    message = (f"Your leave ({leave_summary(leave_request)}) {words[1]}{by}."
               + (f' They wrote: "{note[:500]}"' if note else ''))
    if booked:
        message += (f" You are still booked into {booked} meeting{'' if booked == 1 else 's'} in that time; "
                    f"whoever runs {'it' if booked == 1 else 'them'} has been told.")
    if own_login is not None and own_login.is_active:
        return notify_company_users([own_login], title=title, message=message, link=LEAVE_MINE,
                                    kind='hr_leave_decided')
    from core.notification_utils import notify_employees
    return notify_employees([emp.user], title=title, message=message, kind='hr_leave_decided',
                            email_subject=title)


def leave_request_submitted(leave_request):
    """To the person named to decide it and to the HR admins; not to whoever
    asked. Each is sent to the view of the leave screen the request is on for
    them: an HR admin who is not the approver used to land on an empty list."""
    emp = leave_request.employee
    if not emp or not emp.company_id:
        return 0
    from hr_agent.handover import dashboard_login
    own_login = dashboard_login(emp)
    own_id = own_login.id if own_login is not None else None
    # The approver's dashboard login, by the link on their HR record or by
    # their work address.
    approver_login = dashboard_login(leave_request.approver) if leave_request.approver_id else None
    approver_id = approver_login.id if approver_login is not None else None
    words = {'title': f"Leave request from {emp.full_name}",
             'message': f"{leave_summary(leave_request)}. Waiting for a decision.",
             'kind': 'hr_leave_request'}
    told = 0
    if approver_login is not None and approver_id != own_id:
        told += notify_company_users([approver_login], link=LEAVE_FOR_ME, **words)
    others = [cu for cu in hr_admins(emp.company_id) if cu.id not in (own_id, approver_id)]
    return told + notify_company_users(others, link=LEAVE_ALL, **words)


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

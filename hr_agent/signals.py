"""HR Support Agent — post_save signal triggers for HR workflows.

When an Employee row is created (a new hire) or a LeaveRequest is submitted
or transitions through approve/reject, we evaluate every active
`HRWorkflow` whose `trigger_conditions.on` matches the event. The matching
workflows run via `hr_agent.workflow_engine.execute_workflow` with a
context payload populated from the row.

Re-entrancy: the workflow engine's `update_employee` step writes back to
the same Employee row; without a guard we'd loop. Reuses Frontline's
`workflow_execution_guard` ContextVar — same module, same shape.
"""
import logging

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from hr_agent.models import Employee, LeaveRequest


logger = logging.getLogger(__name__)


def _system_user():
    """Single shared Django User used as `executed_by` when a workflow fires
    from a model signal (no human request to attribute it to)."""
    user, _ = User.objects.get_or_create(
        username='hr_system',
        defaults={'email': 'noreply-hr@hr.local', 'is_active': True},
    )
    return user


def _run_matching_workflows(*, company_id: int, event: str, context: dict):
    """Run every active HRWorkflow whose `trigger_conditions.on` matches
    ``event`` and whose extra filters all match the row.

    This is best-effort by design — workflow failures get logged but never
    break the request that triggered the save."""
    from hr_agent.models import HRWorkflow, HRWorkflowExecution
    from hr_agent.workflow_engine import execute_workflow
    from Frontline_agent.workflow_context import workflow_execution_guard, is_workflow_executing

    if is_workflow_executing():
        # Re-entrancy guard: if we're already inside an HR (or Frontline)
        # workflow run, skip — the original execution will play out without
        # spawning another one.
        logger.debug("HR signal: skipping (already inside a workflow run, event=%s)", event)
        return

    user = _system_user()
    workflows = HRWorkflow.objects.filter(company_id=company_id, is_active=True)
    for w in workflows:
        tc = (w.trigger_conditions or {})
        if tc.get('on') != event:
            continue
        # Optional filter keys — must all match the context if specified.
        ok = True
        for key in ('leave_type', 'department', 'employment_type', 'employment_status'):
            if tc.get(key) is not None and context.get(key) != tc.get(key):
                ok = False
                break
        if not ok:
            continue

        try:
            exec_obj = HRWorkflowExecution.objects.create(
                workflow=w, workflow_name=w.name, executed_by=user,
                employee_id=context.get('employee_id') or None,
                status='awaiting_approval' if w.requires_approval else 'in_progress',
                context_data=context,
            )
            if w.requires_approval:
                logger.info("HR workflow %s awaiting approval (event=%s)", w.id, event)
                continue
            with workflow_execution_guard(workflow_id=w.id):
                success, result_data, err = execute_workflow(
                    w, context, user, simulate=False, execution=exec_obj,
                )
            if result_data and result_data.get('paused'):
                logger.info("HR workflow %s paused (event=%s, wait=%ss)",
                            w.id, event, result_data.get('wait_seconds'))
                continue
            from django.utils import timezone as _tz
            exec_obj.status = 'completed' if success else 'failed'
            exec_obj.result_data = result_data or {}
            exec_obj.error_message = err
            exec_obj.completed_at = _tz.now()
            exec_obj.save()
            logger.info("HR workflow %s ran for event=%s, status=%s",
                        w.id, event, exec_obj.status)
        except Exception:
            logger.exception("HR workflow %s failed for event=%s", w.id, event)


# --------------------------------------------------------------------------
# Receivers
# --------------------------------------------------------------------------

@receiver(post_save, sender=Employee)
def employee_post_save(sender, instance: Employee, created, **kwargs):
    if not instance.company_id:
        return
    if created:
        ctx = _employee_context(instance, event='employee_hired')
        _run_matching_workflows(company_id=instance.company_id,
                                event='employee_hired', context=ctx)
        return

    # Status-change triggers
    new_status = instance.employment_status
    if new_status == 'offboarded':
        _run_matching_workflows(
            company_id=instance.company_id, event='employee_leaving',
            context=_employee_context(instance, event='employee_leaving'),
        )
    elif new_status == 'on_leave':
        _run_matching_workflows(
            company_id=instance.company_id, event='employee_on_leave',
            context=_employee_context(instance, event='employee_on_leave'),
        )
    elif new_status == 'probation':
        _run_matching_workflows(
            company_id=instance.company_id, event='employee_on_probation',
            context=_employee_context(instance, event='employee_on_probation'),
        )


@receiver(post_save, sender=LeaveRequest)
def leave_request_post_save(sender, instance: LeaveRequest, created, **kwargs):
    company_id = instance.employee.company_id if instance.employee_id else None
    if not company_id:
        return
    ctx = _leave_request_context(instance)
    if created:
        _run_matching_workflows(company_id=company_id,
                                event='leave_request_submitted', context=ctx)
        return
    if instance.status == 'approved':
        _run_matching_workflows(company_id=company_id,
                                event='leave_request_approved', context=ctx)
    elif instance.status == 'rejected':
        _run_matching_workflows(company_id=company_id,
                                event='leave_request_rejected', context=ctx)


# --------------------------------------------------------------------------
# Context builders — keep payload tight + JSON-serializable
# --------------------------------------------------------------------------

def _employee_context(emp: Employee, *, event: str) -> dict:
    return {
        'event': event,
        'company_id': emp.company_id,
        'employee_id': emp.id,
        'employee_name': emp.full_name,
        'employee_email': emp.work_email,
        'recipient_email': emp.work_email,  # for send_email default
        'department': emp.department,
        'employment_status': emp.employment_status,
        'employment_type': emp.employment_type,
        'job_title': emp.job_title,
        'manager_id': emp.manager_id,
    }


def _leave_request_context(lr: LeaveRequest) -> dict:
    emp = lr.employee
    return {
        'event': f"leave_request.{lr.status}",
        'company_id': emp.company_id if emp else None,
        'employee_id': emp.id if emp else None,
        'employee_name': emp.full_name if emp else '',
        'employee_email': emp.work_email if emp else '',
        'recipient_email': emp.work_email if emp else '',
        'leave_type': lr.leave_type,
        'leave_request_id': lr.id,
        'start_date': lr.start_date.isoformat() if lr.start_date else None,
        'end_date': lr.end_date.isoformat() if lr.end_date else None,
        'days_requested': float(lr.days_requested or 0),
        'status': lr.status,
    }

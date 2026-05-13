"""HR Support Agent — workflow executor + step handlers.

Ports the Frontline executor shape (`_execute_step_list` + `_run_single_step`
+ `_WorkflowPauseSignal`) and adds HR-specific step types so an onboarding /
offboarding / leave-approval workflow can declaratively orchestrate side
effects across the HR domain.

Step types implemented:
  * **send_email**           — render an `HRNotificationTemplate` body and email a recipient
  * **update_employee**      — set fields on the Employee row in `context_data['employee_id']`
  * **update_leave_balance** — adjust a `LeaveBalance` for {employee, leave_type}
  * **schedule_meeting**     — create an `HRMeeting` row
  * **provision_account**    — placeholder side-effect, logs intent (wire to your IT system)
  * **assign_training**      — placeholder side-effect (wire to your LMS)
  * **assign_manager**       — set Employee.manager
  * **branch**               — recursive condition step (DSL via `Frontline_agent.workflow_conditions`)
  * **wait** / **wait_for_duration** — non-blocking pause via `_WorkflowPauseSignal`
  * **notify_template**      — schedule an `HRScheduledNotification` row
  * Unknown types are no-ops (forward compat).
"""
from __future__ import annotations

import logging
import time as _time
from typing import Optional, Tuple

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class _WorkflowPauseSignal(Exception):
    """Same shape as the Frontline executor's pause signal — see
    `api.views.frontline_agent._WorkflowPauseSignal`. Carries `wait_seconds`
    + `remaining_steps` (flat) + `partial_results`.

    `awaiting_approval=True` means the pause is open-ended — there is no
    countdown, the workflow waits for an explicit approve/reject API call.
    """
    def __init__(self, wait_seconds: int, step_path: str = '',
                 awaiting_approval: bool = False, approval_request: dict | None = None):
        super().__init__(f"workflow_pause:wait_seconds={wait_seconds}")
        self.wait_seconds = int(wait_seconds)
        self.step_path = step_path
        self.remaining_steps: list = []
        self.partial_results: list = []
        self.awaiting_approval = bool(awaiting_approval)
        self.approval_request = approval_request or None


# --------------------------------------------------------------------------
# Step handlers
# --------------------------------------------------------------------------

def _render(body: str, ctx: dict) -> str:
    """Tiny `{{key}}` substitution. Same as the notification renderer."""
    if not body:
        return ''
    out = body
    for k, v in (ctx or {}).items():
        out = out.replace('{{' + str(k) + '}}', str(v) if v is not None else '')
    return out


def _step_send_email(step, ctx, simulate):
    from django.core.mail import send_mail
    from hr_agent.models import HRNotificationTemplate

    template_id = step.get('template_id')
    template_name = step.get('template_name')
    recipient = _render(
        step.get('recipient_email') or ctx.get('recipient_email') or ctx.get('employee_email') or '{{employee_email}}',
        ctx,
    ).strip()
    if not recipient or '@' not in recipient:
        return False, {'done': False, 'error': 'Missing recipient email'}, None

    tpl = None
    if template_id:
        tpl = HRNotificationTemplate.objects.filter(pk=template_id).first()
    elif template_name:
        tpl = HRNotificationTemplate.objects.filter(name=template_name).first()
    if not tpl:
        return False, {'done': False, 'error': 'Template not found'}, None

    body = _render(tpl.body, {**ctx, **(step.get('context') or {})})
    subject = _render(tpl.subject or tpl.name, {**ctx, **(step.get('context') or {})})

    if simulate:
        return True, {'done': True, 'simulated': True,
                      'recipient': recipient, 'template_id': tpl.id}, None
    try:
        send_mail(
            subject=subject or 'HR Notification', message=body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
            recipient_list=[recipient], fail_silently=False,
        )
        return True, {'done': True, 'recipient': recipient, 'template_id': tpl.id}, None
    except Exception as exc:
        return False, {'done': False, 'error': f"{type(exc).__name__}: {exc}"}, None


def _step_update_employee(step, ctx, simulate):
    from hr_agent.models import Employee
    employee_id = step.get('employee_id') or ctx.get('employee_id')
    if not employee_id:
        return False, {'done': False, 'error': 'Missing employee_id'}, None
    fields = step.get('fields') or {}
    if not isinstance(fields, dict) or not fields:
        return False, {'done': False, 'error': 'No `fields` to update'}, None
    if simulate:
        return True, {'done': True, 'simulated': True, 'employee_id': employee_id, 'fields': fields}, None
    e = Employee.objects.filter(pk=employee_id).first()
    if not e:
        return False, {'done': False, 'error': 'Employee not found'}, None
    SAFE = {'job_title', 'department', 'employment_status', 'employment_type',
            'probation_end_date', 'manager_id', 'timezone_name'}
    update_fields = []
    for k, v in fields.items():
        if k in SAFE:
            setattr(e, k, v)
            update_fields.append(k)
    if not update_fields:
        return False, {'done': False, 'error': 'No safe fields to update'}, None
    update_fields.append('updated_at')
    e.save(update_fields=update_fields)
    return True, {'done': True, 'employee_id': e.id, 'updated': update_fields}, None


def _step_update_leave_balance(step, ctx, simulate):
    from hr_agent.models import LeaveBalance
    employee_id = step.get('employee_id') or ctx.get('employee_id')
    leave_type = step.get('leave_type') or ctx.get('leave_type') or 'vacation'
    delta_used = step.get('delta_used_days')
    delta_accrued = step.get('delta_accrued_days')
    if not employee_id or (delta_used is None and delta_accrued is None):
        return False, {'done': False, 'error': 'employee_id and at least one delta required'}, None
    if simulate:
        return True, {'done': True, 'simulated': True, 'employee_id': employee_id,
                      'leave_type': leave_type,
                      'delta_used': delta_used, 'delta_accrued': delta_accrued}, None
    bal, _ = LeaveBalance.objects.get_or_create(
        employee_id=employee_id, leave_type=leave_type,
    )
    if delta_used is not None:
        bal.used_days = float(bal.used_days) + float(delta_used)
    if delta_accrued is not None:
        bal.accrued_days = float(bal.accrued_days) + float(delta_accrued)
    bal.save()
    return True, {'done': True, 'employee_id': employee_id, 'remaining': bal.remaining}, None


def _step_schedule_meeting(step, ctx, simulate):
    from datetime import datetime
    from hr_agent.models import HRMeeting, Employee
    employee_id = step.get('employee_id') or ctx.get('employee_id')
    title = step.get('title') or _render(step.get('title_template') or 'HR meeting', ctx)
    meeting_type = step.get('meeting_type') or 'one_on_one'
    duration_minutes = int(step.get('duration_minutes') or 30)
    when = step.get('scheduled_at')
    organizer_id = step.get('organizer_id')
    company_id = ctx.get('company_id')
    if not company_id:
        return False, {'done': False, 'error': 'context_data.company_id required'}, None
    if not when:
        return False, {'done': False, 'error': 'scheduled_at required'}, None
    try:
        sched = datetime.fromisoformat(str(when).replace('Z', '+00:00'))
    except ValueError:
        return False, {'done': False, 'error': 'scheduled_at must be ISO-8601'}, None
    if simulate:
        return True, {'done': True, 'simulated': True, 'meeting_type': meeting_type,
                      'scheduled_at': sched.isoformat()}, None
    organizer = Employee.objects.filter(pk=organizer_id).first() if organizer_id else None
    visibility = ('private' if meeting_type in ('exit_interview', 'grievance_hearing',
                                                'performance_review') else 'company')
    m = HRMeeting.objects.create(
        company_id=company_id,
        title=title[:200], description=step.get('description') or '',
        meeting_type=meeting_type, visibility=visibility, organizer=organizer,
        scheduled_at=sched, duration_minutes=duration_minutes,
        timezone_name=step.get('timezone_name') or 'UTC',
    )
    if employee_id:
        emp = Employee.objects.filter(pk=employee_id, company_id=company_id).first()
        if emp:
            m.participants.add(emp)
    return True, {'done': True, 'meeting_id': m.id, 'scheduled_at': sched.isoformat()}, None


def _step_provision_account(step, ctx, simulate):
    """Placeholder. Real impls would call Okta / Google Workspace / Slack admin
    APIs; we just log the intent so the workflow is observable end-to-end."""
    employee_id = step.get('employee_id') or ctx.get('employee_id')
    systems = step.get('systems') or []
    if simulate:
        return True, {'done': True, 'simulated': True, 'employee_id': employee_id,
                      'systems': systems}, None
    logger.info("[hr workflow] provision_account intent: employee=%s systems=%s",
                employee_id, systems)
    return True, {'done': True, 'employee_id': employee_id, 'systems': systems,
                  'note': 'placeholder — wire to your IT provisioning'}, None


def _step_assign_training(step, ctx, simulate):
    employee_id = step.get('employee_id') or ctx.get('employee_id')
    modules = step.get('modules') or []
    if simulate:
        return True, {'done': True, 'simulated': True,
                      'employee_id': employee_id, 'modules': modules}, None
    logger.info("[hr workflow] assign_training intent: employee=%s modules=%s",
                employee_id, modules)
    return True, {'done': True, 'employee_id': employee_id, 'modules': modules,
                  'note': 'placeholder — wire to your LMS'}, None


def _step_assign_manager(step, ctx, simulate):
    from hr_agent.models import Employee
    employee_id = step.get('employee_id') or ctx.get('employee_id')
    manager_id = step.get('manager_id')
    if not (employee_id and manager_id):
        return False, {'done': False, 'error': 'employee_id and manager_id required'}, None
    if simulate:
        return True, {'done': True, 'simulated': True,
                      'employee_id': employee_id, 'manager_id': manager_id}, None
    e = Employee.objects.filter(pk=employee_id).first()
    if not e:
        return False, {'done': False, 'error': 'Employee not found'}, None
    e.manager_id = manager_id
    e.save(update_fields=['manager_id', 'updated_at'])
    return True, {'done': True, 'employee_id': employee_id, 'manager_id': manager_id}, None


def _step_notify_template(step, ctx, simulate):
    """Schedule an `HRScheduledNotification` so the regular sender picks it up.
    Useful when you need a delayed reminder a few hours/days from now."""
    from datetime import timedelta as _td
    from hr_agent.models import (
        HRNotificationTemplate, HRScheduledNotification, Employee,
    )
    template_id = step.get('template_id')
    template_name = step.get('template_name')
    delay_minutes = int(step.get('delay_minutes') or 0)
    employee_id = step.get('employee_id') or ctx.get('employee_id')
    company_id = ctx.get('company_id')
    if not (template_id or template_name) or not company_id:
        return False, {'done': False, 'error': 'template_id/name + company_id required'}, None
    tpl = None
    if template_id:
        tpl = HRNotificationTemplate.objects.filter(pk=template_id, company_id=company_id).first()
    elif template_name:
        tpl = HRNotificationTemplate.objects.filter(name=template_name, company_id=company_id).first()
    if not tpl:
        return False, {'done': False, 'error': 'Template not found'}, None
    if simulate:
        return True, {'done': True, 'simulated': True, 'template_id': tpl.id,
                      'delay_minutes': delay_minutes}, None
    employee = Employee.objects.filter(pk=employee_id).first() if employee_id else None
    n = HRScheduledNotification.objects.create(
        company_id=company_id, template=tpl,
        recipient_employee=employee,
        recipient_email=(employee.work_email if employee else (step.get('recipient_email') or '')),
        scheduled_at=timezone.now() + _td(minutes=delay_minutes),
        status='pending',
        context={**(ctx or {}), **(step.get('context') or {})},
    )
    return True, {'done': True, 'scheduled_notification_id': n.id}, None


# Step type → handler. Add to this dict to extend; keep keys lowercased.
STEP_HANDLERS = {
    'send_email': _step_send_email,
    'update_employee': _step_update_employee,
    'update_leave_balance': _step_update_leave_balance,
    'schedule_meeting': _step_schedule_meeting,
    'provision_account': _step_provision_account,
    'assign_training': _step_assign_training,
    'assign_manager': _step_assign_manager,
    'notify_template': _step_notify_template,
}


# --------------------------------------------------------------------------
# Executor
# --------------------------------------------------------------------------

def _run_single_step(step, step_index, step_path, workflow, context_data, simulate
                     ) -> Tuple[bool, dict, Optional[str]]:
    step_type = (step.get('type') or '').lower()
    base = {'step': step_index, 'step_path': step_path, 'type': step_type}

    if step_type in ('wait', 'wait_for_duration'):
        seconds = max(0, min(86400, int(step.get('seconds') or 0)))
        if simulate:
            return True, {**base, 'done': True, 'simulated': True, 'seconds': seconds}, None
        if seconds > 0:
            raise _WorkflowPauseSignal(wait_seconds=seconds, step_path=step_path)
        return True, {**base, 'done': True, 'waited_seconds': 0}, None

    if step_type == 'wait_for_approval':
        # Open-ended pause: no countdown, no Celery scheduling. Resumes only
        # when an HR-admin (or the named approver) hits the approve endpoint.
        approval_request = {
            'approver_role': step.get('approver_role') or 'hr_admin',
            'approver_user_id': step.get('approver_user_id'),
            'approver_employee_id': step.get('approver_employee_id'),
            'message': _render(step.get('message') or 'Approval required to proceed', ctx),
            'requested_at': timezone.now().isoformat(),
        }
        if simulate:
            return True, {**base, 'done': True, 'simulated': True,
                          'awaiting_approval': True,
                          'approval_request': approval_request}, None
        sig = _WorkflowPauseSignal(
            wait_seconds=0, step_path=step_path,
            awaiting_approval=True, approval_request=approval_request,
        )
        raise sig

    handler = STEP_HANDLERS.get(step_type)
    if handler is None:
        return True, {**base, 'done': True, 'note': 'unknown step type treated as no-op'}, None
    ok, result, fatal = handler(step, context_data, simulate)
    return ok, {**base, **(result or {})}, fatal


def _execute_step_list(steps, workflow, context_data, simulate, start_monotonic, timeout,
                       path_prefix='') -> Tuple[bool, list, Optional[str]]:
    """Walk a step list. Branches recurse. Pauses bubble up via
    `_WorkflowPauseSignal`, each level prepending its tail so the top sees a
    flat continuation list. Mirrors the Frontline executor."""
    from Frontline_agent.workflow_conditions import evaluate as _eval_cond

    results: list = []
    step_list = list(steps or [])
    for i, step in enumerate(step_list):
        step_path = f"{path_prefix}{i}"
        step_type = (step.get('type') or '').lower()

        if timeout and (_time.monotonic() - start_monotonic) > timeout:
            results.append({'step': i, 'step_path': step_path, 'type': step_type,
                            'done': False, 'error': 'workflow_timeout'})
            return False, results, 'workflow_timeout'

        if step_type == 'branch':
            cond = step.get('condition')
            branch_taken = 'if_true' if _eval_cond(cond, context_data) else 'if_false'
            nested = step.get(branch_taken) or []
            results.append({'step': i, 'step_path': step_path, 'type': 'branch',
                            'done': True, 'branch_taken': branch_taken, 'nested_count': len(nested)})
            try:
                nested_ok, nested_results, nested_err = _execute_step_list(
                    nested, workflow, context_data, simulate, start_monotonic, timeout,
                    path_prefix=f"{step_path}.{branch_taken}.",
                )
            except _WorkflowPauseSignal as pause:
                pause.partial_results = results + pause.partial_results
                pause.remaining_steps = list(pause.remaining_steps) + step_list[i + 1:]
                raise
            results.extend(nested_results)
            if not nested_ok:
                return False, results, nested_err
            continue

        retries = max(0, min(5, int(step.get('retries', 0))))
        backoff_seconds = max(0, min(300, int(step.get('backoff_seconds', 5))))
        attempt = 0
        while True:
            attempt += 1
            try:
                ok, result_entry, fatal = _run_single_step(
                    step, i, step_path, workflow, context_data, simulate,
                )
            except _WorkflowPauseSignal as pause:
                pause.partial_results = list(results)
                pause.remaining_steps = step_list[i + 1:]
                raise
            result_entry['attempt'] = attempt
            if ok:
                results.append(result_entry)
                break
            if attempt > retries:
                results.append(result_entry)
                return False, results, result_entry.get('error', 'step_failed')
            if timeout and (_time.monotonic() - start_monotonic) > timeout:
                results.append({**result_entry, 'error': 'workflow_timeout'})
                return False, results, 'workflow_timeout'
            if simulate:
                results.append({**result_entry, 'would_retry_in_seconds': backoff_seconds})
                continue
            if backoff_seconds:
                _time.sleep(backoff_seconds)

    return True, results, None


def execute_workflow(workflow, context_data, executed_by_user, *, simulate=False, execution=None,
                     _steps_override=None, _prior_results=None, _prior_elapsed=0.0):
    """Top-level entry. Returns `(success, result_data, error_message)`.

    On a `wait` step, persists the pause snapshot onto `execution` (when
    provided) and schedules a Celery resume task — mirroring Frontline's
    `_persist_and_schedule_resume`. Caller checks `result_data['paused']`.
    """
    steps = _steps_override if _steps_override is not None else (workflow.steps or [])
    timeout = int(getattr(workflow, 'timeout_seconds', 0) or 0)
    effective_timeout = max(1, int(timeout - (_prior_elapsed or 0))) if timeout else 0
    start = _time.monotonic()
    prior_results = list(_prior_results or [])
    try:
        ok, results, err = _execute_step_list(
            steps, workflow, context_data, simulate, start, effective_timeout,
        )
    except _WorkflowPauseSignal as pause:
        accumulated = prior_results + list(pause.partial_results or [])
        elapsed_active = round((_prior_elapsed or 0) + (_time.monotonic() - start), 3)
        result_data = {
            'paused': True, 'wait_seconds': pause.wait_seconds,
            'pause_step_path': pause.step_path,
            'steps_completed': sum(1 for r in accumulated if r.get('done')),
            'results': accumulated, 'simulated': simulate,
            'elapsed_active_seconds': elapsed_active,
            'awaiting_approval': pause.awaiting_approval,
            'approval_request': pause.approval_request,
        }
        if execution is not None and not simulate:
            _persist_and_schedule_resume(
                execution=execution, wait_seconds=pause.wait_seconds,
                remaining_steps=list(pause.remaining_steps or []),
                results_so_far=accumulated, elapsed_active_seconds=elapsed_active,
                context_data=context_data,
                awaiting_approval=pause.awaiting_approval,
                approval_request=pause.approval_request,
            )
        return True, result_data, None

    combined = prior_results + results
    total_elapsed = round((_prior_elapsed or 0) + (_time.monotonic() - start), 3)
    return ok, {
        'steps_completed': sum(1 for r in combined if r.get('done')),
        'results': combined, 'simulated': simulate,
        'elapsed_seconds': total_elapsed,
    }, err


def _persist_and_schedule_resume(*, execution, wait_seconds, remaining_steps, results_so_far,
                                 elapsed_active_seconds, context_data,
                                 awaiting_approval: bool = False,
                                 approval_request: dict | None = None):
    """Save pause snapshot onto the HRWorkflowExecution and schedule
    `resume_hr_workflow_execution` to fire after `wait_seconds`. Probes the
    broker first so a Redis outage degrades to inline rather than stalling
    100s in Celery's connection-retry loop.

    When `awaiting_approval=True`, sets status to ``awaiting_approval`` and
    skips Celery scheduling — the workflow waits indefinitely until the
    approve/reject endpoint fires.
    """
    from datetime import timedelta as _td
    from hr_agent.tasks import resume_hr_workflow_execution

    resume_at = None if awaiting_approval else (timezone.now() + _td(seconds=wait_seconds))
    execution.status = 'awaiting_approval' if awaiting_approval else 'paused'
    execution.resume_at = resume_at
    execution.pause_state = {
        'remaining_steps': remaining_steps,
        'results_so_far': results_so_far,
        'elapsed_active_seconds': elapsed_active_seconds,
        'context_data': context_data,
        'awaiting_approval': awaiting_approval,
        'approval_request': approval_request,
    }
    execution.result_data = {
        'paused': True, 'wait_seconds': wait_seconds,
        'resume_at': resume_at.isoformat() if resume_at else None,
        'steps_completed': sum(1 for r in results_so_far if r.get('done')),
        'results': results_so_far,
        'elapsed_active_seconds': elapsed_active_seconds,
        'awaiting_approval': awaiting_approval,
        'approval_request': approval_request,
    }
    execution.save(update_fields=['status', 'resume_at', 'pause_state', 'result_data'])

    if awaiting_approval:
        return  # No countdown — waits for explicit approve/reject API call.

    # Cheap broker probe — same shape as the Frontline + upload paths.
    import socket
    from urllib.parse import urlparse
    from celery import current_app
    broker_ok = True
    try:
        url = current_app.conf.broker_url or ''
        parsed = urlparse(url)
        host = parsed.hostname or 'localhost'
        default_port = 6379 if (parsed.scheme or '').startswith('redis') else 5672
        port = parsed.port or default_port
        with socket.create_connection((host, port), timeout=0.5):
            pass
    except Exception:
        broker_ok = False
        logger.warning("resume_hr_workflow_execution: broker unreachable — running resume inline")

    if broker_ok:
        try:
            resume_hr_workflow_execution.apply_async(
                args=[execution.id], countdown=max(1, int(wait_seconds)), retry=False,
            )
            return
        except Exception:
            logger.exception("resume_hr_workflow_execution: dispatch failed, running inline")

    try:
        resume_hr_workflow_execution(execution.id)
    except Exception:
        logger.exception("Inline resume_hr_workflow_execution fallback also failed")

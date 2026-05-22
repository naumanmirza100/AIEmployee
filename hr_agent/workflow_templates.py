"""Built-in HR workflow templates.

These are pre-canned ``steps`` JSON blobs HR can clone into ``HRWorkflow`` rows
instead of building from scratch. Each template lives behind a stable key so a
company can update its instance independently of the canonical source.

The shapes match `hr_agent.workflow_engine.STEP_HANDLERS` exactly — that means
adding a new step type requires the engine to support it first.
"""
from __future__ import annotations

from typing import Any


BUILTIN_WORKFLOWS: dict[str, dict[str, Any]] = {
    'new_hire_onboarding': {
        'name': 'New hire onboarding',
        'description': (
            "Default 30-day onboarding flow. Provisions an account, sends a welcome "
            "email, books an orientation meeting, schedules a 30-day manager check-in, "
            "and assigns the standard new-hire training set."
        ),
        'trigger_conditions': {'on': 'employee_hired'},
        'requires_approval': False,
        'timeout_seconds': 0,
        'steps': [
            {
                'type': 'provision_account',
                'note': 'Stub — wire to your IDP / Google Workspace creator here.',
            },
            {
                'type': 'send_email',
                'to': '{{employee.work_email}}',
                'subject': 'Welcome to the team, {{employee.full_name}}!',
                'body': (
                    "Hi {{employee.full_name}},\n\n"
                    "Welcome aboard! Your first day is {{employee.start_date}}.\n"
                    "Your manager will reach out shortly with your onboarding plan.\n\n"
                    "— HR"
                ),
            },
            {
                'type': 'schedule_meeting',
                'title': 'Onboarding orientation',
                'meeting_type': 'onboarding_orientation',
                'duration_minutes': 60,
                'offset_days_from_start': 0,
                'with_manager': True,
            },
            {
                'type': 'assign_training',
                'training_key': 'standard_new_hire',
            },
            {
                'type': 'schedule_meeting',
                'title': '30-day check-in',
                'meeting_type': 'one_on_one',
                'duration_minutes': 30,
                'offset_days_from_start': 30,
                'with_manager': True,
            },
        ],
    },

    'offboarding': {
        'name': 'Employee offboarding',
        'description': (
            "Default offboarding flow. Marks the employee `notice`, books an exit "
            "interview, sends the equipment-return email, and on the last day flips "
            "status to `offboarded` and revokes account access."
        ),
        'trigger_conditions': {'on': 'employee_offboarding_started'},
        'requires_approval': True,
        'timeout_seconds': 0,
        'steps': [
            {
                'type': 'update_employee',
                'fields': {'employment_status': 'notice'},
            },
            {
                'type': 'schedule_meeting',
                'title': 'Exit interview',
                'meeting_type': 'exit_interview',
                'duration_minutes': 45,
                'offset_days_from_now': 3,
                'with_hr': True,
            },
            {
                'type': 'send_email',
                'to': '{{employee.work_email}}',
                'subject': 'Off-boarding: equipment return',
                'body': (
                    "Hi {{employee.full_name}},\n\n"
                    "Please return your laptop, badge, and any company-issued equipment "
                    "to the office (or arrange courier) before your last day.\n\n"
                    "— HR"
                ),
            },
            {
                'type': 'wait_for_approval',
                'approver_role': 'hr',
                'note': 'HR confirms equipment received before access revocation.',
            },
            {
                'type': 'update_employee',
                'fields': {'employment_status': 'offboarded'},
            },
            {
                'type': 'provision_account',
                'action': 'revoke',
            },
        ],
    },

    'thirty_day_check_in': {
        'name': '30-day check-in',
        'description': (
            "Standalone flow you can fire on any active employee 30 days after their "
            "start date — schedules a 1:1 and emails both employee + manager a short "
            "agenda."
        ),
        'trigger_conditions': {'on': 'employee_30_days'},
        'requires_approval': False,
        'timeout_seconds': 0,
        'steps': [
            {
                'type': 'schedule_meeting',
                'title': '30-day check-in',
                'meeting_type': 'one_on_one',
                'duration_minutes': 30,
                'offset_days_from_now': 1,
                'with_manager': True,
            },
            {
                'type': 'send_email',
                'to': '{{employee.work_email}}',
                'subject': 'Your 30-day check-in is scheduled',
                'body': (
                    "Hi {{employee.full_name}},\n\n"
                    "Your 30-day check-in is on the books with your manager. A few prompts:\n"
                    "  • What's working so far?\n"
                    "  • What's been harder than you expected?\n"
                    "  • Where do you need more clarity?\n\n"
                    "— HR"
                ),
            },
        ],
    },
}


def list_template_summaries() -> list[dict]:
    """Wire-friendly list — same shape the UI gets."""
    return [
        {
            'key': key,
            'name': spec['name'],
            'description': spec['description'],
            'step_count': len(spec.get('steps') or []),
            'requires_approval': bool(spec.get('requires_approval')),
            'trigger_event': (spec.get('trigger_conditions') or {}).get('on'),
        }
        for key, spec in BUILTIN_WORKFLOWS.items()
    ]


def get_template(key: str) -> dict | None:
    """Return the full template spec or ``None`` if the key is unknown."""
    spec = BUILTIN_WORKFLOWS.get(key)
    if not spec:
        return None
    # Deep-copy via json roundtrip to keep callers from mutating the registry.
    import copy
    return copy.deepcopy(spec)

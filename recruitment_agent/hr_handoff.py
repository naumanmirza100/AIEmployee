"""Hired in Recruitment → a new starter in HR.

Marking an interview Hired used to stop there: someone had to type the person
into HR by hand, and HR's onboarding — a workflow that runs when an employee is
created — didn't start until they did. This makes the HR record (status
`candidate`: offer signed, not started) from the interview after the recruiter
has reviewed it, and links the two so the same hire can't be added twice.

The API is `recruitment/interviews/<id>/hr-handoff` (GET: the review form's
pre-filled values and choices; POST: create, or link an existing record).
"""
from __future__ import annotations

from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

#: JobDescription.type → Employee.employment_type
EMPLOYMENT_TYPES = {
    'Full-time': 'full_time',
    'Part-time': 'part_time',
    'Contract': 'contract',
    'Internship': 'intern',
}
#: A start date to suggest when the recruiter hasn't said: two weeks out.
SUGGESTED_START_IN_DAYS = 14


def hr_available(company) -> bool:
    from core.modules import has_module
    return bool(company) and has_module(company, 'hr_agent')


def job_for(interview):
    if interview.cv_record_id and interview.cv_record and interview.cv_record.job_description_id:
        return interview.cv_record.job_description
    return None


def existing_employee(interview, company, email=None):
    """The HR record for this hire: the one it's linked to, else one already
    using the address (someone added by hand, or rehired)."""
    from hr_agent.models import Employee
    if interview.hr_employee_id:
        return interview.hr_employee
    email = (email or interview.candidate_email or '').strip()
    if not email:
        return None
    return (Employee.objects.filter(company=company)
            .filter(work_email__iexact=email).first()
            or Employee.objects.filter(company=company, personal_email__iexact=email).first())


def onboarding_workflows(company) -> list[str]:
    """Names of the HR workflows that will run for a new starter."""
    from hr_agent.models import HRWorkflow
    return [w.name for w in HRWorkflow.objects.filter(company=company, is_active=True).only('name', 'trigger_conditions')
            if (w.trigger_conditions or {}).get('on') == 'employee_hired']


def form(interview, company) -> dict:
    """Everything the review form needs: pre-filled values and the choices."""
    from hr_agent.models import Department, Employee
    job = job_for(interview)
    job_title = (job.title if job else (interview.job_role or '').split('\n')[0]).strip()[:160]
    current = existing_employee(interview, company)
    return {
        'hr_available': hr_available(company),
        'linked': bool(interview.hr_employee_id),
        'existing': ({'id': current.id, 'full_name': current.full_name, 'work_email': current.work_email,
                      'employment_status': current.employment_status} if current else None),
        'prefill': {
            'full_name': interview.candidate_name,
            # Their own address until they have a company one; editable.
            'work_email': interview.candidate_email,
            'personal_email': interview.candidate_email,
            'phone': interview.candidate_phone or '',
            'job_title': job_title,
            'department': ((job.department if job else '') or '').strip()[:120],
            'employment_type': EMPLOYMENT_TYPES.get(getattr(job, 'type', ''), 'full_time'),
            'start_date': (timezone.localdate() + timedelta(days=SUGGESTED_START_IN_DAYS)).isoformat(),
            'manager_id': None,
        },
        'employment_types': [{'value': v, 'label': l} for v, l in Employee.EMPLOYMENT_TYPE_CHOICES],
        'departments': list(Department.objects.filter(company=company).order_by('name')
                            .values_list('name', flat=True)),
        'managers': [
            {'id': e.id, 'full_name': e.full_name, 'job_title': e.job_title}
            for e in Employee.objects.filter(company=company)
                        .exclude(employment_status__in=('offboarded', 'candidate'))
                        .order_by('full_name')[:500]
        ],
        'onboarding_workflows': onboarding_workflows(company),
    }


def create_new_starter(interview, company, data) -> tuple[object | None, dict]:
    """Validate the reviewed form and create the HR record. Returns
    (employee, {}) or (None, {field: message})."""
    from hr_agent.models import Department, Employee

    errors = {}
    full_name = (data.get('full_name') or '').strip()[:255]
    work_email = (data.get('work_email') or '').strip().lower()[:254]
    if not full_name:
        errors['full_name'] = 'Enter their name.'
    if not work_email or '@' not in work_email:
        errors['work_email'] = 'Enter an email address.'
    elif Employee.objects.filter(company=company, work_email__iexact=work_email).exists():
        errors['work_email'] = 'Someone in HR already uses this email.'

    start_date = None
    try:
        start_date = date.fromisoformat(str(data.get('start_date') or ''))
    except ValueError:
        errors['start_date'] = 'Choose their first day.'

    employment_type = data.get('employment_type') or 'full_time'
    if employment_type not in dict(Employee.EMPLOYMENT_TYPE_CHOICES):
        errors['employment_type'] = 'Choose an employment type.'

    manager = None
    if data.get('manager_id'):
        manager = Employee.objects.filter(company=company, pk=data.get('manager_id')).first()
        if manager is None:
            errors['manager_id'] = 'Choose a manager from your company.'

    if errors:
        return None, errors

    # Same rule as HR's own form: reuse the department by name, else create it.
    department = (data.get('department') or '').strip()[:120]
    department_obj = None
    if department:
        department_obj = (Department.objects.filter(company=company, name__iexact=department).first()
                          or Department.objects.create(company=company, name=department))

    with transaction.atomic():
        # Creating the row is what fires HR's `employee_hired` workflows.
        employee = Employee.objects.create(
            company=company,
            full_name=full_name,
            work_email=work_email,
            personal_email=(data.get('personal_email') or interview.candidate_email or '')[:254],
            phone=(data.get('phone') or '')[:40],
            job_title=(data.get('job_title') or '').strip()[:160],
            department=department,
            department_obj=department_obj,
            manager=manager,
            employment_status='candidate',
            employment_type=employment_type,
            start_date=start_date,
            custom_fields={'recruitment_interview_id': interview.id},
        )
        interview.hr_employee = employee
        interview.save(update_fields=['hr_employee', 'updated_at'])
    return employee, {}


def link_existing(interview, employee) -> None:
    interview.hr_employee = employee
    interview.save(update_fields=['hr_employee', 'updated_at'])

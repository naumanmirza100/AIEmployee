"""Recruitment's Workflow / SOP Runner (docx item 7).

A company sets up steps that run by themselves when something happens in hiring: an application arrives, the AI
screens a candidate, a candidate books an interview, an interview decision is recorded. The steps run on HR's
workflow engine (hr_agent/workflow_engine.py: branches, retries, a timeout), with Recruitment's own step types:

  send_email   {"to": "candidate" | "recruiter" | an address, "subject": ..., "body": ...}
               to the candidate it goes in the company's name, with Reply-To the recruiter (candidate_mail)
  notify       {"to": "recruiter" | "admins" | "hr_admins", "title": ..., "message": ...}   a bell alert
  create_task  {"project_id": ..., "title": ..., "description": ..., "due_in_days": ..., "assignee_id": ...}
               a Project Manager task; with no Project Manager or no such project, the recruiter's bell instead
  branch       {"condition": ..., "if_true": [...], "if_false": [...]}   (the engine's own)

Texts take {{placeholders}}: candidate_name, candidate_email, job_title, decision, score, interview_time,
meeting_link, outcome, company_name, recruiter_name, recruiter_email. Waiting steps are not offered yet: a paused
run would need Recruitment's own resume job.

`run_for_event` is called where each event happens. A workflow runs once per event and subject (`run_key`), and a
failing workflow never stops the action that triggered it; the recruiter is told in the bell instead.
"""
import logging
import re

from django.db import IntegrityError, transaction
from django.db.models import Q

logger = logging.getLogger(__name__)

EVENTS = ('application_received', 'candidate_screened', 'interview_booked', 'interview_outcome')
STEP_TYPES = ('send_email', 'notify', 'create_task', 'branch')
PLACEHOLDERS = ('candidate_name', 'candidate_email', 'job_title', 'decision', 'score', 'interview_time',
                'meeting_link', 'outcome', 'company_name', 'recruiter_name', 'recruiter_email')
KIND = 'recruitment_workflow_notice'
_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


# ---- what a workflow knows about the event ---------------------------------------------------------------

def context_for(event, *, cv_record=None, interview=None, application=None) -> dict:
    from recruitment_agent import candidate_mail, interview_time
    if interview is not None and cv_record is None and interview.cv_record_id:
        cv_record = interview.cv_record
    if cv_record is not None and application is None and cv_record.job_application_id:
        application = cv_record.job_application
    job = (cv_record.job_description if cv_record is not None and cv_record.job_description_id
           else getattr(application, 'job', None))
    who = candidate_mail.who_hires(interview, job)
    name = email = ''
    if application is not None:
        name = f'{application.first_name} {application.last_name}'.strip()
        email = application.email or ''
    elif interview is not None:
        name, email = interview.candidate_name or '', interview.candidate_email or ''
    elif cv_record is not None and cv_record.parsed_json:
        import json
        try:
            parsed = json.loads(cv_record.parsed_json)
        except (TypeError, ValueError):
            parsed = {}
        name, email = (parsed.get('name') or ''), (parsed.get('email') or '')
    company_id = getattr(job, 'company_id', None) or (interview_time.company_id_for(interview) if interview else None)
    return {
        'event': event, 'company_id': company_id,
        'candidate_name': name or 'the candidate', 'candidate_email': email,
        'job_title': getattr(job, 'title', '') or getattr(interview, 'job_role', '') or '',
        'job_id': getattr(job, 'id', None),
        'decision': (cv_record.qualification_decision or '') if cv_record is not None else '',
        'score': cv_record.role_fit_score if cv_record is not None else None,
        'interview_time': interview_time.when(interview) if interview is not None and interview.scheduled_datetime else '',
        'meeting_link': (interview.meeting_link or '') if interview is not None else '',
        'outcome': (interview.outcome or '') if interview is not None else '',
        'interview_type': (interview.interview_type or '') if interview is not None else '',
        'company_name': who['company_name'], 'recruiter_name': who['contact_name'],
        'recruiter_email': who['contact_email'],
        'cv_record_id': getattr(cv_record, 'id', None), 'interview_id': getattr(interview, 'id', None),
        'application_id': getattr(application, 'id', None),
        'recruiter_id': (interview.company_user_id if interview is not None and interview.company_user_id
                         else getattr(job, 'company_user_id', None)),
    }


# ---- the steps -----------------------------------------------------------------------------------------

def _render(text, ctx):
    from hr_agent.workflow_engine import _render as render
    return render(text or '', ctx)


def _link(ctx):
    return f"/recruitment/candidates/{ctx['cv_record_id']}" if ctx.get('cv_record_id') else '/recruitment/candidates'


def _logins(to, ctx):
    from core.models import CompanyUser
    from hr_agent.alerts import HR_ADMIN_ROLES
    people = CompanyUser.objects.filter(company_id=ctx.get('company_id'), is_active=True)
    if to == 'recruiter':
        return list(people.filter(pk=ctx.get('recruiter_id'))) or list(people.filter(role__in=('owner', 'admin')))
    if to == 'admins':
        return list(people.filter(role__in=('owner', 'admin')))
    if to == 'hr_admins':
        return list(people.filter(role__in=HR_ADMIN_ROLES))
    return []


def _step_send_email(step, ctx, simulate):
    from django.core.mail import send_mail
    from django.conf import settings
    from recruitment_agent import candidate_mail
    to = (step.get('to') or 'candidate').strip()
    address = {'candidate': ctx.get('candidate_email'), 'recruiter': ctx.get('recruiter_email')}.get(to, to)
    if not address or not _EMAIL.match(address):
        return False, {'done': False, 'error': f'No email address for "{to}"'}, None
    subject, body = _render(step.get('subject'), ctx)[:200], _render(step.get('body'), ctx)
    if simulate:
        return True, {'done': True, 'simulated': True, 'to': address, 'subject': subject}, None
    if to == 'candidate':
        from recruitment_agent.models import JobDescription
        job = JobDescription.objects.filter(pk=ctx.get('job_id')).first()
        candidate_mail.send(subject, body, None, address, job=job)
    else:
        send_mail(subject, body, getattr(settings, 'DEFAULT_FROM_EMAIL', None), [address])
    return True, {'done': True, 'to': address, 'subject': subject}, None


def _step_notify(step, ctx, simulate):
    from core.notification_utils import notify_company_users
    to = step.get('to') or 'recruiter'
    people = _logins(to, ctx)
    if not people:
        return False, {'done': False, 'error': f'Nobody to tell ("{to}")'}, None
    title = _render(step.get('title') or 'Recruitment workflow', ctx)[:200]
    if simulate:
        return True, {'done': True, 'simulated': True, 'to': to, 'title': title}, None
    told = notify_company_users(people, title=title, message=_render(step.get('message'), ctx), link=_link(ctx),
                                kind=KIND, data={'cv_record_id': ctx.get('cv_record_id')})
    return True, {'done': True, 'told': told, 'title': title}, None


def _step_create_task(step, ctx, simulate):
    from datetime import timedelta
    from django.utils import timezone
    from core.models import CompanyUser, Project
    from core.modules import has_module
    title = _render(step.get('title') or 'Task from a Recruitment workflow', ctx)[:200]
    description = _render(step.get('description'), ctx)
    project = Project.objects.filter(pk=step.get('project_id'), company_id=ctx.get('company_id')).first() \
        if step.get('project_id') else None
    owner = _logins('recruiter', ctx)
    if project is None or not has_module(ctx.get('company_id'), 'project_manager_agent') or not owner:
        if simulate:
            return True, {'done': True, 'simulated': True, 'note': 'No project: the recruiter would be told'}, None
        from core.notification_utils import notify_company_users
        notify_company_users(owner or _logins('admins', ctx), title=f'To do: {title}', message=description or title,
                             link=_link(ctx), kind=KIND, severity='warning')
        return True, {'done': True, 'note': 'No Project Manager project to put it in: the recruiter was told'}, None
    due = None
    if step.get('due_in_days') not in (None, ''):
        due = (timezone.localdate() + timedelta(days=int(step['due_in_days']))).isoformat()
    if simulate:
        return True, {'done': True, 'simulated': True, 'project_id': project.id, 'title': title}, None
    from project_manager_agent import services as pm_services
    from project_manager_agent.services.actor import DashboardActor
    try:
        task = pm_services.create_task(DashboardActor(owner[0]), {
            'project_id': project.id, 'title': title, 'description': description,
            'priority': step.get('priority') or 'medium', 'assignee_id': step.get('assignee_id'), 'due_date': due})
    except Exception as exc:
        return False, {'done': False, 'error': f'Project Manager refused the task: {exc}'}, None
    return True, {'done': True, 'task_id': task.id, 'title': title}, None


STEP_HANDLERS = {'send_email': _step_send_email, 'notify': _step_notify, 'create_task': _step_create_task}


def validate(steps) -> list:
    """What is wrong with these steps, in words; empty when they can be saved."""
    problems = []
    if not isinstance(steps, list) or not steps:
        return ['Add at least one step.']

    def walk(items, where):
        for i, step in enumerate(items):
            label = f'Step {where}{i + 1}'
            kind = (step or {}).get('type') if isinstance(step, dict) else None
            if kind in ('wait', 'wait_for_duration', 'wait_for_approval'):
                problems.append(f'{label}: waiting steps are not available in Recruitment workflows yet.')
            elif kind not in STEP_TYPES:
                problems.append(f'{label}: "{kind}" is not a step type here. Use one of: {", ".join(STEP_TYPES)}.')
            elif kind == 'send_email' and not (step.get('subject') and step.get('body')):
                problems.append(f'{label}: an email needs a subject and a body.')
            elif kind == 'notify' and step.get('to', 'recruiter') not in ('recruiter', 'admins', 'hr_admins'):
                problems.append(f'{label}: "to" is recruiter, admins or hr_admins.')
            elif kind == 'create_task' and not step.get('title'):
                problems.append(f'{label}: a task needs a title.')
            elif kind == 'branch':
                walk(step.get('if_true') or [], f'{where}{i + 1}.yes.')
                walk(step.get('if_false') or [], f'{where}{i + 1}.no.')
    walk(steps, '')
    return problems


# ---- running ------------------------------------------------------------------------------------------

def run(workflow, ctx, *, simulate=False, run_key=None, cv_record=None, interview=None):
    """Run one workflow on one event. Returns the run, or None when this event already ran it."""
    from hr_agent.workflow_engine import execute_workflow
    from recruitment_agent.models import RecruitmentWorkflowRun
    try:
        with transaction.atomic():      # a savepoint: a second run of the same event must not break the caller's
            record = RecruitmentWorkflowRun.objects.create(
                workflow=workflow, workflow_name=workflow.name, company_id=workflow.company_id,
                event=ctx.get('event', ''), cv_record=cv_record, interview=interview,
                candidate_name=ctx.get('candidate_name', '')[:255], run_key=None if simulate else run_key,
                status='simulated' if simulate else 'completed')
    except IntegrityError:
        return None
    try:
        ok, data, err = execute_workflow(workflow, ctx, None, simulate=simulate, handlers=STEP_HANDLERS)
    except Exception as exc:
        logger.exception('Recruitment workflow %s failed', workflow.id)
        ok, data, err = False, {}, str(exc)
    if not simulate and not ok:
        record.status = 'failed'
        from core.notification_utils import notify_company_users
        notify_company_users(_logins('recruiter', ctx), title=f'Workflow "{workflow.name}" stopped'[:200],
                             message=f'It stopped on {ctx.get("candidate_name")}: {err}', link='/recruitment/workflows',
                             kind=KIND, severity='warning')
    record.results, record.error_message = data, err or ''
    record.save(update_fields=['status', 'results', 'error_message'])
    return record


def run_for_event(event, *, cv_record=None, interview=None, application=None, detail=''):
    """Run the company's active workflows for this event. Never raises: the hiring action goes on regardless."""
    try:
        from core.modules import has_module
        from Frontline_agent.workflow_conditions import evaluate
        from recruitment_agent.models import RecruitmentWorkflow
        ctx = context_for(event, cv_record=cv_record, interview=interview, application=application)
        if not ctx.get('company_id') or not has_module(ctx['company_id'], 'recruitment_agent'):
            return []
        workflows = (RecruitmentWorkflow.objects.filter(company_id=ctx['company_id'], trigger_event=event, is_active=True)
                     .filter(Q(job__isnull=True) | Q(job_id=ctx.get('job_id'))))
        subject = ctx.get('interview_id') or ctx.get('cv_record_id') or ctx.get('application_id')
        ran = []
        for workflow in workflows:
            if workflow.conditions and not evaluate(workflow.conditions, ctx):
                continue
            record = run(workflow, ctx, run_key=f'{workflow.id}:{event}:{subject}:{detail}'[:255],
                         cv_record=cv_record if cv_record is not None else getattr(interview, 'cv_record', None),
                         interview=interview)
            if record is not None:
                ran.append(record)
        return ran
    except Exception:
        logger.exception('Recruitment workflows for %s could not run', event)
        return []


TEMPLATES = {
    'thank_applicant': {
        'name': 'Thank every applicant and tell the recruiter', 'trigger_event': 'application_received',
        'description': 'A personal thank-you in the company\'s name, and a bell alert to the recruiter.',
        'steps': [
            {'type': 'send_email', 'to': 'candidate', 'subject': 'Thank you for applying to {{company_name}}',
             'body': 'Dear {{candidate_name}},\n\nThank you for applying for the {{job_title}} role at {{company_name}}. '
                     'We read every application and will be in touch.\n\n{{recruiter_name}}'},
            {'type': 'notify', 'to': 'recruiter', 'title': 'New applicant: {{candidate_name}}',
             'message': '{{candidate_name}} applied for {{job_title}}.'},
        ],
    },
    'strong_candidate': {
        'name': 'Flag strong candidates to the admins', 'trigger_event': 'candidate_screened',
        'description': 'When the AI scores a candidate 80 or more, the owner and admins hear at once.',
        'steps': [
            {'type': 'branch', 'condition': {'left': 'score', 'op': '>=', 'right': 80},
             'if_true': [{'type': 'notify', 'to': 'admins', 'title': 'Strong candidate: {{candidate_name}}',
                          'message': '{{candidate_name}} scored {{score}} for {{job_title}} ({{decision}}).'}],
             'if_false': []},
        ],
    },
    'interview_prep': {
        'name': 'Prepare for each booked interview', 'trigger_event': 'interview_booked',
        'description': 'A task for the recruiter to prepare, and a note with the time.',
        'steps': [
            {'type': 'create_task', 'title': 'Prepare interview: {{candidate_name}} ({{job_title}})',
             'description': 'Interview on {{interview_time}}. Read the CV and the research before then.',
             'due_in_days': 0},
        ],
    },
    'hired_to_hr': {
        'name': 'Hand new hires to HR', 'trigger_event': 'interview_outcome',
        'description': 'When the decision is Hired, HR admins are told so onboarding can start.',
        'steps': [
            {'type': 'branch', 'condition': {'left': 'outcome', 'op': '==', 'right': 'HIRED'},
             'if_true': [{'type': 'notify', 'to': 'hr_admins', 'title': 'New hire: {{candidate_name}}',
                          'message': '{{candidate_name}} was hired for {{job_title}}. Add them in HR to start onboarding.'}],
             'if_false': []},
        ],
    },
}

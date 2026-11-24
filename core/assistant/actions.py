"""The Company Assistant does things, after you confirm them (24 Nov 2026).

It only read: "I can't assign tasks: I only read", and it said where to go. Now, asked to do something, it proposes it
as a card, as Project Pilot does: what it will do, who and what it touches, and any warning (the person is away). It
does nothing until the asker presses Confirm. Then it does it through the agent's own code, with the asker's rights,
the same as the agent's own screen would: a refused change is refused here too.

The card carries a signed proposal (the action, the records it resolved to, the asker), good for 30 minutes and used
once; Confirm checks it all again before anything changes.

Actions so far:
  * create_task, update_task (Project Manager): through project_manager_agent.services.tasks
  * decide_leave (HR): approve or reject a waiting leave request, through HR's own view
  * update_ticket (Frontline): a ticket's status, priority or assignee, through Frontline's own view
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date

from django.core import signing

logger = logging.getLogger(__name__)

SALT = 'company-assistant.action.v1'
MAX_AGE = 30 * 60

ACTIONS = {
    'create_task': ('project_manager_agent', 'Create a task',
                    '{"title", "project" (its name), "assignee" (a name or "me"; optional), "due_date" (YYYY-MM-DD; '
                    'optional), "priority" (low|medium|high; optional)}'),
    'update_task': ('project_manager_agent', 'Change a task',
                    '{"task" (its title), "status" (todo|in_progress|review|done; optional), "assignee" (optional), '
                    '"due_date" (optional), "priority" (optional)}'),
    'decide_leave': ('hr_agent', "Decide someone's leave request",
                     '{"person" (whose leave), "decision" (approve|reject), "note" (optional)}'),
    'update_ticket': ('frontline_agent', 'Change a support ticket',
                      '{"ticket" (its number, or words of its title), "status" (open|in_progress|resolved|closed; '
                      'optional), "assignee" (a name or "me"; optional), "priority" (low|medium|high|urgent; optional)}'),
}


class NotPossible(Exception):
    """Said to the asker as it is: why the action can't be proposed or done."""


def available(ctx) -> dict:
    """The actions this company's agents allow: {kind: (label, args)}."""
    return {kind: (label, args) for kind, (module, label, args) in ACTIONS.items() if module in ctx.modules}


def plan_text(ctx) -> str:
    acts = available(ctx)
    if not acts:
        return ''
    lines = '\n'.join(f'- {kind} — {label} — {args}' for kind, (label, args) in acts.items())
    return ('Actions you may propose, only when the asker asks you to do something (give, assign, create, move, '
            'mark, approve, reject, close): at most one, which the asker confirms before anything changes:\n'
            f'{lines}\n')


# ---- resolving what the asker named -------------------------------------------------------------------------------

def _one_person(ctx, name, what='person'):
    found = ctx.directory.find(name, asker=ctx.company_user)
    found = [p for p in found if p.user_ids or p.company_user is not None]
    if not found:
        raise NotPossible(f'I could not find anyone called "{name}".')
    if len(found) > 1:
        raise NotPossible(f'Which "{name}" do you mean: ' + ', '.join(p.describe() for p in found[:6]) + '?')
    return found[0]


def _day(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise NotPossible(f'I could not read "{value}" as a date.')


def _by_name(rows, name, what):
    """The one row whose title best matches `name`: exact, then all its words, else NotPossible."""
    query = ' '.join(str(name or '').lower().split())
    if not query:
        raise NotPossible(f'Which {what}?')
    exact = [r for r in rows if ' '.join(str(r[1]).lower().split()) == query]
    if len(exact) == 1:
        return exact[0]
    words = [w for w in re.findall(r'\w+', query) if len(w) > 1]
    hits = [r for r in rows if all(w in str(r[1]).lower() for w in words)] if words else []
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise NotPossible(f'I could not find a {what} called "{name}".')
    raise NotPossible(f'Which {what} do you mean: ' + ', '.join(f'"{r[1]}"' for r in hits[:6]) + '?')


def _away(ctx, person, day):
    """A warning when `person` is on approved leave on `day`, or ''."""
    if not day or person.employee is None:
        return ''
    from hr_agent.models import LeaveRequest
    leave = (LeaveRequest.objects.filter(employee=person.employee, status='approved', start_date__lte=day,
                                         end_date__gte=day).first())
    return (f'{person.name} is on leave then ({leave.start_date:%d %b} to {leave.end_date:%d %b}).' if leave else '')


def _user_id(person):
    return sorted(person.user_ids)[0] if person.user_ids else None


# ---- proposing ------------------------------------------------------------------------------------------------------

def prepare(ctx, kind, args) -> dict:
    """The card for this action: {'kind', 'title', 'rows': [[label, value]], 'warnings', 'token'}; NotPossible when it
    can't be done (nothing found, two matches, not allowed)."""
    if kind not in available(ctx):
        raise NotPossible("I can't do that here. I can create or change tasks, decide leave requests and change "
                          'support tickets, where the company has those agents.')
    args = args if isinstance(args, dict) else {}
    card = {'create_task': _prepare_create_task, 'update_task': _prepare_update_task,
            'decide_leave': _prepare_decide_leave, 'update_ticket': _prepare_update_ticket}[kind](ctx, args)
    payload = {'kind': kind, 'cu': ctx.company_user.pk, 'company': ctx.company.pk, 'data': card.pop('data')}
    card.update({'kind': kind, 'token': signing.dumps(payload, salt=SALT, compress=True)})
    return card


def _outside_project(project_id, due):
    """PM refuses a due date outside the project's dates. Said here, before Confirm, not after it (24 Nov 2026: the
    live check's card was refused only on Confirm)."""
    if not due:
        return
    from core.models import Project
    from project_manager_agent.services.tasks import _as_moment, due_date_problem
    project = Project.objects.filter(pk=project_id).first()
    problem = due_date_problem(project, _as_moment(due)) if project is not None else None
    if not problem:
        return
    if problem[0] == 'task_before_project_start':
        starts = _as_moment(project.start_date).date()
        raise NotPossible(f'The project "{project.name}" starts on {starts:%a %d %b %Y}, so a task can\'t be due on '
                          f'{due:%a %d %b %Y}. Give a later date, or move the project\'s start first.')
    ends = _as_moment(project.effective_deadline, end_of_day=True).date()
    raise NotPossible(f'The project "{project.name}" ends on {ends:%a %d %b %Y}, so a task can\'t be due on '
                      f'{due:%a %d %b %Y}. Give an earlier date, or extend the project first.')


def _prepare_create_task(ctx, args):
    from core.tenancy import projects_for_company_user
    title = ' '.join(str(args.get('title') or '').split())[:200]
    if not title:
        raise NotPossible('What should the task be called?')
    projects = list(projects_for_company_user(ctx.company_user).values_list('id', 'name'))
    if not projects:
        raise NotPossible('There is no project you can add tasks to.')
    pid, pname = _by_name(projects, args.get('project') or (projects[0][1] if len(projects) == 1 else ''), 'project')
    data, rows, warnings = {'project_id': pid, 'title': title}, [['Task', title], ['Project', pname]], []
    due = _day(args.get('due_date'))
    _outside_project(pid, due)
    if args.get('assignee'):
        person = _one_person(ctx, args['assignee'])
        if not _user_id(person):
            raise NotPossible(f'{person.name} has no employee login, so no task can be given to them.')
        data['assignee_id'] = _user_id(person)
        rows.append(['For', person.name])
        if _away(ctx, person, due):
            warnings.append(_away(ctx, person, due))
    if due:
        data['due_date'] = due.isoformat()
        rows.append(['Due', f'{due:%A %d %b %Y}'])
    if args.get('priority') in ('low', 'medium', 'high'):
        data['priority'] = args['priority']
        rows.append(['Priority', args['priority'].capitalize()])
    return {'title': 'Create a task', 'rows': rows, 'warnings': warnings, 'data': data}


def _prepare_update_task(ctx, args):
    from core.tenancy import tasks_for_company_user
    rows_found = list(tasks_for_company_user(ctx.company_user).exclude(status='done')
                      .values_list('id', 'title')[:500]) or list(
        tasks_for_company_user(ctx.company_user).values_list('id', 'title')[:500])
    tid, ttitle = _by_name(rows_found, args.get('task'), 'task')
    data, rows, warnings = {}, [['Task', ttitle]], []
    from core.models import Task
    _outside_project(Task.objects.filter(pk=tid).values_list('project_id', flat=True).first(), _day(args.get('due_date')))
    status = str(args.get('status') or '').lower().replace(' ', '_')
    if status:
        if status not in ('todo', 'in_progress', 'review', 'done', 'blocked'):
            raise NotPossible(f'"{args.get("status")}" is not a task status.')
        data['status'] = status
        rows.append(['Status', status.replace('_', ' ').capitalize()])
    due = _day(args.get('due_date'))
    if args.get('assignee'):
        person = _one_person(ctx, args['assignee'])
        if not _user_id(person):
            raise NotPossible(f'{person.name} has no employee login, so no task can be given to them.')
        data['assignee_id'] = _user_id(person)
        rows.append(['Give to', person.name])
        if _away(ctx, person, due):
            warnings.append(_away(ctx, person, due))
    if due:
        data['due_date'] = due.isoformat()
        rows.append(['Due', f'{due:%A %d %b %Y}'])
    if args.get('priority') in ('low', 'medium', 'high'):
        data['priority'] = args['priority']
        rows.append(['Priority', args['priority'].capitalize()])
    if not data:
        raise NotPossible(f'What should change on "{ttitle}"?')
    data['task_id'] = tid
    return {'title': 'Change a task', 'rows': rows, 'warnings': warnings, 'data': data}


def _prepare_decide_leave(ctx, args):
    from hr_agent.models import LeaveRequest
    decision = str(args.get('decision') or '').lower()
    if decision not in ('approve', 'reject'):
        raise NotPossible('Should I approve it or reject it?')
    person = _one_person(ctx, args.get('person'))
    if person.employee is None:
        raise NotPossible(f'{person.name} has no HR record, so they have no leave requests.')
    waiting = list(LeaveRequest.objects.filter(employee=person.employee, status='pending').order_by('start_date'))
    if not waiting:
        raise NotPossible(f'{person.name} has no leave request waiting for a decision.')
    if len(waiting) > 1:
        raise NotPossible(f'{person.name} has {len(waiting)} leave requests waiting: ' + '; '.join(
            f'{lr.leave_type} {lr.start_date:%d %b} to {lr.end_date:%d %b}' for lr in waiting[:4])
            + '. Decide them in HR, Leave, or name the dates.')
    lr = waiting[0]
    from api.views.hr_agent import _may_decide_leave
    if not _may_decide_leave(ctx.company_user, lr):
        raise NotPossible(f"You can't decide {person.name}'s leave: only their approver or HR can.")
    rows = [['Leave', f'{person.name}: {lr.leave_type}, {lr.start_date:%d %b} to {lr.end_date:%d %b %Y} '
                      f'({float(lr.days_requested or 0):g} day(s))'], ['Decision', decision.capitalize()]]
    note = ' '.join(str(args.get('note') or '').split())[:500]
    if note:
        rows.append(['Note', note])
    return {'title': 'Approve leave' if decision == 'approve' else 'Reject leave', 'rows': rows, 'warnings': [],
            'data': {'leave_request_id': lr.id, 'action': decision, 'note': note}}


def _prepare_update_ticket(ctx, args):
    from Frontline_agent.models import Ticket
    ref = str(args.get('ticket') or '').strip().lstrip('#')
    tickets = Ticket.objects.filter(company=ctx.company)
    if ref.isdigit() and tickets.filter(pk=int(ref)).exists():
        ticket = tickets.get(pk=int(ref))
    else:
        tid, _ = _by_name(list(tickets.exclude(status='closed').values_list('id', 'title')[:500]), ref, 'ticket')
        ticket = tickets.get(pk=tid)
    data, rows, warnings = {}, [['Ticket', f'#{ticket.id} {ticket.title}']], []
    status = str(args.get('status') or '').lower().replace(' ', '_')
    if status:
        data['status'] = status
        rows.append(['Status', status.replace('_', ' ').capitalize()])
    if args.get('priority') in ('low', 'medium', 'high', 'urgent'):
        data['priority'] = args['priority']
        rows.append(['Priority', args['priority'].capitalize()])
    if args.get('assignee'):
        person = _one_person(ctx, args['assignee'])
        if person.company_user is None:
            raise NotPossible(f'{person.name} has no dashboard login, so no ticket can be given to them.')
        data['assigned_to_company_user_id'] = person.company_user.pk
        rows.append(['Give to', person.name])
    if not data:
        raise NotPossible(f'What should change on ticket #{ticket.id}?')
    data['ticket_id'] = ticket.id
    return {'title': 'Change a ticket', 'rows': rows, 'warnings': warnings, 'data': data}


# ---- doing it, once confirmed -------------------------------------------------------------------------------------

def apply(company_user, token) -> dict:
    """Do the confirmed action. {'message', 'link'}; NotPossible when it is refused (by the agent's own rules too)."""
    try:
        payload = signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except signing.SignatureExpired:
        raise NotPossible('This suggestion is more than 30 minutes old. Ask again.')
    except signing.BadSignature:
        raise NotPossible('This suggestion could not be read. Ask again.')
    if payload.get('cu') != company_user.pk or payload.get('company') != company_user.company_id:
        raise NotPossible('This suggestion was made for someone else.')
    kind, data = payload.get('kind'), dict(payload.get('data') or {})
    from core.modules import active_modules
    if ACTIONS.get(kind, (None,))[0] not in active_modules(company_user.company):
        raise NotPossible('The company no longer has the agent this needs.')
    from django.db import transaction
    # Marked done and done together: a refusal by the agent undoes the mark, so the same card says the refusal
    # again rather than "This was done already" (24 Nov 2026).
    with transaction.atomic():
        _once(token)
        return {'create_task': _apply_create_task, 'update_task': _apply_update_task,
                'decide_leave': _apply_decide_leave, 'update_ticket': _apply_update_ticket}[kind](company_user, data)


def _once(token):
    """A proposal is done once: a second Confirm (a double click, another tab) does nothing."""
    from django.db import IntegrityError, transaction
    from core.models import SentAlert
    key = 'assistant-action:' + hashlib.sha256(token.encode()).hexdigest()[:40]
    try:
        with transaction.atomic():
            SentAlert.objects.create(key=key)
    except IntegrityError:
        raise NotPossible('This was done already.')


def _service(call):
    from project_manager_agent.services.errors import ServiceError
    try:
        return call()
    except ServiceError as exc:
        raise NotPossible(exc.message)


def _apply_create_task(company_user, data):
    from project_manager_agent.services import tasks as pm_tasks
    from project_manager_agent.services.actor import DashboardActor
    task = _service(lambda: pm_tasks.create_task(DashboardActor(company_user), data))
    return {'message': f'Done: the task "{task.title}" is in {task.project.name}.',
            'link': f'/project-manager/dashboard?tab=projects&project={task.project_id}'}


def _apply_update_task(company_user, data):
    from project_manager_agent.services import tasks as pm_tasks
    from project_manager_agent.services.actor import DashboardActor
    task_id = data.pop('task_id')
    task, changed = _service(lambda: pm_tasks.update_task(DashboardActor(company_user), task_id, data))
    return {'message': f'Done: "{task.title}" changed ({", ".join(c.replace("_", " ") for c in changed)}).',
            'link': f'/project-manager/dashboard?tab=projects&project={task.project_id}'}


def _call_view(view, company_user, method, data, **kwargs):
    """The agent's own view, as its screen calls it: its rules, checks and alerts, the asker's rights."""
    from rest_framework.test import APIRequestFactory, force_authenticate
    request = getattr(APIRequestFactory(), method)('/', data, format='json')
    force_authenticate(request, user=company_user)
    response = view(request, **kwargs)
    if hasattr(response, 'render'):
        response.render()
    body = getattr(response, 'data', None) or {}
    if response.status_code >= 400:
        raise NotPossible(body.get('message') or 'The agent refused it.')
    return body


def _apply_decide_leave(company_user, data):
    from api.views import hr_agent as hr_views
    body = _call_view(hr_views.decide_leave_request, company_user, 'post',
                      {'action': data['action'], 'note': data.get('note') or ''},
                      request_id=data['leave_request_id'])
    done = (body.get('data') or {}).get('status', data['action'])
    return {'message': f'Done: the leave request is {done}.', 'link': '/hr/dashboard?tab=leave'}


def _apply_update_ticket(company_user, data):
    from api.views import frontline_agent as fl_views
    ticket_id = data.pop('ticket_id')
    _call_view(fl_views.update_ticket, company_user, 'patch', data, ticket_id=ticket_id)
    return {'message': f'Done: ticket #{ticket_id} changed.', 'link': f'/frontline/dashboard?ticket={ticket_id}'}

"""Review every change Project Pilot proposes, then make exactly those.

The pilot turns a sentence into actions: create, update or delete projects and
tasks. It used to apply them the moment they arrived, unless a new task was
missing an assignee or deadline — so "mark everything in Q1 as done" or
"delete all projects except Website" ran with nobody looking. Now every
proposal that would change anything comes back as a review card: the creates
as an editable form (`drafts`), the updates and deletes described here against
what is in the database now. `apply` makes them only once the user confirms,
through the service layer — the same checks, scope and audit entries as the
dashboard's own buttons — and skips anything the user unticked.

The confirmed proposal comes back from the browser, so nothing in it is
trusted beyond what the user could do with those buttons anyway: every target
is looked up in the caller's scope and every value validated by the service.
"""
from __future__ import annotations

import logging

from django.db import transaction

from core.models import Project, Subtask, Task
from project_manager_agent import services as pm_services
from project_manager_agent.drafts import describe

logger = logging.getLogger(__name__)

CREATE_ACTIONS = ('create_project', 'create_task')
CHANGE_ACTIONS = ('update_project', 'update_task', 'delete_project', 'delete_task')
WRITE_ACTIONS = CREATE_ACTIONS + CHANGE_ACTIONS

#: What an update may touch, and how the review card names it.
TASK_FIELDS = {'title': 'Title', 'description': 'Description', 'status': 'Status',
               'priority': 'Priority', 'assignee_id': 'Assigned to', 'due_date': 'Due'}
PROJECT_FIELDS = {'name': 'Name', 'description': 'Description', 'status': 'Status',
                  'priority': 'Priority', 'project_type': 'Type', 'deadline': 'Deadline',
                  'end_date': 'Deadline', 'start_date': 'Start', 'budget_min': 'Budget from',
                  'budget_max': 'Budget to'}


def proposes_changes(actions) -> bool:
    return any(isinstance(a, dict) and a.get('action') in WRITE_ACTIONS for a in actions or [])


# ---------------------------------------------------------------------------
# Describing updates and deletes
# ---------------------------------------------------------------------------

def _plural(n, noun):
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _shown(field, value, model):
    """A value as the review card shows it."""
    if value in (None, ''):
        return '—'
    if field in ('status', 'priority', 'project_type'):
        return dict(model._meta.get_field(field).choices).get(value, str(value))
    if hasattr(value, 'date') and callable(value.date):
        return value.date().isoformat()
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    text = str(value)
    return text if len(text) <= 120 else text[:117] + '…'


def _person(actor, user_id):
    from core.tenancy import AssigneeNotAllowed, resolve_member
    if user_id in (None, ''):
        return None, '—'
    try:
        user = resolve_member(user_id, company=actor.company, company_user=actor.company_user)
    except AssigneeNotAllowed:
        return None, None
    return user, (user.get_full_name() or user.username)


def _update_lines(obj, updates, fields, actor):
    lines, problem = [], None
    seen_labels = set()
    for field, label in fields.items():
        if field not in updates or label in seen_labels:
            continue
        seen_labels.add(label)
        after = updates.get(field)
        if field == 'assignee_id':
            _, after_text = _person(actor, after)
            if after_text is None:
                problem = "The new assignee isn't in your company."
                after_text = 'someone outside your company'
            before_text = (obj.assignee.get_full_name() or obj.assignee.username) if obj.assignee_id else '—'
        else:
            model_field = 'deadline' if field == 'end_date' else field
            before_text = _shown(model_field, getattr(obj, model_field, None), type(obj))
            after_text = _shown(model_field, after, type(obj))
        if before_text != after_text:
            lines.append({'field': field, 'label': label, 'before': before_text, 'after': after_text})
    return lines, problem


def changes(actions, actor):
    """One row per update or delete, against what is stored now:
    ``{index, action, kind, target, title, lines | effect, problem?}``."""
    rows = []
    for index, action in enumerate(actions or []):
        if not isinstance(action, dict) or action.get('action') not in CHANGE_ACTIONS:
            continue
        kind = action['action']
        target = 'project' if kind.endswith('_project') else 'task'
        row = {'index': index, 'action': kind, 'kind': kind.split('_')[0], 'target': target,
               'title': describe(action), 'lines': []}
        try:
            if target == 'project':
                obj = (actor.project_for_delete if kind == 'delete_project' else actor.project_for_edit)(
                    action.get('project_id'))
                row['title'] = obj.name
            else:
                obj = (actor.task_for_delete if kind == 'delete_task' else actor.task_for_edit)(
                    action.get('task_id'))
                row['title'] = obj.title
                row['project'] = obj.project.name if obj.project_id else ''
        except pm_services.ServiceError:
            row['problem'] = f"This {target} wasn't found — it may already be gone."
            rows.append(row)
            continue

        if kind == 'delete_project':
            tasks = Task.objects.filter(project=obj).count()
            subtasks = Subtask.objects.filter(task__project=obj).count()
            if tasks or subtasks:
                row['effect'] = (f"Also deletes its {_plural(tasks, 'task')}"
                                 + (f" and {_plural(subtasks, 'subtask')}" if subtasks else '') + '.')
        elif kind == 'delete_task':
            subtasks = Subtask.objects.filter(task=obj).count()
            if subtasks:
                row['effect'] = f"Also deletes its {_plural(subtasks, 'subtask')}."
        else:
            updates = action.get('updates') if isinstance(action.get('updates'), dict) else {}
            fields = PROJECT_FIELDS if target == 'project' else TASK_FIELDS
            row['lines'], problem = _update_lines(obj, updates, fields, actor)
            if problem:
                row['problem'] = problem
            elif not row['lines']:
                row['problem'] = 'Nothing would change.'
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Applying a confirmed proposal
# ---------------------------------------------------------------------------

def _choice(value, choices):
    """The model writes 'In Progress' or 'High'; the service wants 'in_progress'
    and 'high'. Anything that still isn't a choice is left to the default."""
    if value in (None, ''):
        return None
    key = str(value).strip().lower().replace(' ', '_').replace('-', '_')
    return key if key in dict(choices) else None


def _first(action, *keys):
    for key in keys:
        if action.get(key) not in (None, ''):
            return action[key]
    return None


def _create_project(actor, action):
    project = pm_services.create_project(actor, {
        'name': _first(action, 'project_name', 'name'),
        'description': _first(action, 'project_description', 'description'),
        'status': _choice(_first(action, 'project_status', 'status'), Project.STATUS_CHOICES),
        'priority': _choice(_first(action, 'project_priority', 'priority'), Project.PRIORITY_CHOICES),
        'project_type': _choice(action.get('project_type'), Project.PROJECT_TYPE_CHOICES),
        'industry_id': action.get('industry_id'),
        'budget_min': action.get('budget_min'),
        'budget_max': action.get('budget_max'),
        'deadline': _first(action, 'deadline', 'end_date'),
        'start_date': action.get('start_date'),
        # The card already showed the name being created, so a same-name
        # project is not news worth a second dialog.
        'confirm_duplicate_name': True,
    })
    if action.get('project_manager_id'):
        try:
            pm_services.update_project(actor, project.id, {'project_manager_id': action['project_manager_id']})
        except pm_services.ServiceError:
            logger.info('pilot: proposed project manager %s refused', action['project_manager_id'])
    return project


def _create_task(actor, action, created_project_id):
    task = pm_services.create_task(actor, {
        # Tasks proposed alongside a new project have no project_id yet; they
        # belong to the one just made.
        'project_id': action.get('project_id') or created_project_id,
        'title': _first(action, 'task_title', 'title'),
        'description': _first(action, 'task_description', 'description'),
        'priority': _choice(action.get('priority'), Task.PRIORITY_CHOICES),
        'status': _choice(action.get('status'), Task.STATUS_CHOICES),
        'assignee_id': action.get('assignee_id'),
        'due_date': action.get('due_date'),
        'estimated_hours': action.get('estimated_hours'),
    })
    if action.get('reasoning'):
        Task.objects.filter(pk=task.pk).update(ai_reasoning=str(action['reasoning']))
    return task


def _updates(action, fields):
    raw = action.get('updates') if isinstance(action.get('updates'), dict) else {}
    out = {k: v for k, v in raw.items() if k in fields}
    model = Project if action['action'] == 'update_project' else Task
    for key in ('status', 'priority', 'project_type'):
        if key in out:
            # A value that still isn't a choice goes through as given, so the
            # service refuses it with its own message rather than silently.
            out[key] = _choice(out[key], model._meta.get_field(key).choices) or out[key]
    return out


def _apply_one(actor, action, created_project_id):
    kind = action['action']
    if kind == 'create_project':
        project = _create_project(actor, action)
        return {'project_id': project.id, 'project_name': project.name,
                'message': f'Project "{project.name}" created.'}
    if kind == 'create_task':
        task = _create_task(actor, action, created_project_id)
        return {'task_id': task.id, 'task_title': task.title, 'project_id': task.project_id,
                'assignee_id': task.assignee_id, 'message': f'Task "{task.title}" created.'}
    if kind == 'update_task':
        task, _ = pm_services.update_task(actor, action.get('task_id'), _updates(action, TASK_FIELDS))
        return {'task_id': task.id, 'task_title': task.title, 'message': f'Task "{task.title}" updated.'}
    if kind == 'update_project':
        project, _ = pm_services.update_project(actor, action.get('project_id'), _updates(action, PROJECT_FIELDS))
        return {'project_id': project.id, 'project_name': project.name,
                'message': f'Project "{project.name}" updated.'}
    if kind == 'delete_task':
        gone = pm_services.delete_task(actor, action.get('task_id'))
        return {'task_id': gone['id'], 'task_title': gone['title'], 'message': f'Task "{gone["title"]}" deleted.'}
    gone = pm_services.delete_project(actor, action.get('project_id'))
    return {'project_id': gone['id'], 'project_name': gone['name'],
            'message': f'Project "{gone["name"]}" deleted.'}


def apply(actions, actor, skip=()):
    """Make the confirmed changes. Projects are created first so tasks proposed
    with them can join them; everything else keeps its order. One transaction,
    a savepoint each: a refused action is reported and the rest still happen.
    Returns (results, created_project_id)."""
    skipped = set()
    for raw in skip or ():
        try:
            skipped.add(int(raw))
        except (TypeError, ValueError):
            continue
    todo = [(i, a) for i, a in enumerate(actions or [])
            if isinstance(a, dict) and a.get('action') in WRITE_ACTIONS and i not in skipped]
    todo.sort(key=lambda pair: 0 if pair[1]['action'] == 'create_project' else 1)

    results, created_project_id = [], None
    with transaction.atomic():
        for index, action in todo:
            outcome = {'index': index, 'action': action['action']}
            try:
                with transaction.atomic():
                    outcome.update(_apply_one(actor, action, created_project_id), success=True)
                if action['action'] == 'create_project':
                    created_project_id = outcome['project_id']
            except pm_services.ServiceError as exc:
                outcome.update(success=False, error=exc.message)
            results.append(outcome)
    return results, created_project_id


def summary(results):
    """'Created 1 project and 2 tasks. Deleted 1 task. 1 couldn't be done: …'"""
    done = {}
    for r in results:
        if r.get('success'):
            verb, noun = r['action'].split('_')
            done.setdefault(verb, {}).setdefault(noun, 0)
            done[verb][noun] += 1
    sentences = []
    for verb, word in (('create', 'Created'), ('update', 'Updated'), ('delete', 'Deleted')):
        if verb in done:
            parts = [_plural(n, noun) for noun, n in sorted(done[verb].items())]
            sentences.append(f"{word} {' and '.join(parts)}.")
    failed = [r for r in results if not r.get('success')]
    if failed:
        sentences.append(f"{_plural(len(failed), 'change')} couldn't be made: {failed[0]['error']}")
    return ' '.join(sentences) or 'Nothing was changed.'

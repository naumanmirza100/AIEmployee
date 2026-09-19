"""Create, update, bulk-update, re-link and delete tasks — the one
implementation behind all three PM API families.

Rules applied everywhere (decisions of 2026-09-19, MDS/PM_API_CONSOLIDATION_PLAN.md):
  * an invalid status / priority / due date / estimated_hours is a 400, never
    silently ignored (D1, D2, D9);
  * a task can't move to in_progress or done while a dependency is unfinished,
    unless the request says force=true (D3);
  * a task's due date must fall within its project's start date and deadline
    (D4) — checked when the due date is set or changed, so an unrelated edit of
    an older out-of-range task still goes through;
  * every write is one transaction and leaves one audit entry (D7).
"""
import logging
from datetime import datetime, time

from django.db import transaction
from django.utils import timezone

from core.models import Subtask, Task

from . import parsing
from .errors import ServiceError

logger = logging.getLogger(__name__)

BLOCKING_STATUSES = ('in_progress', 'done')
BULK_UPDATE_MAX = 500


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def serialize_brief(task):
    return {'id': task.id, 'title': task.title, 'status': task.status}


def blockers(task, dep_ids=None):
    """Dependencies that aren't done: the task's current ones, or the proposed
    list `dep_ids` (then `task` may be None — a task not created yet)."""
    deps = task.depends_on.all() if dep_ids is None else Task.objects.filter(id__in=list(dep_ids))
    return [d for d in deps if d.status != 'done']


def _creates_cycle(task_id, candidate_ids):
    if not candidate_ids:
        return False
    target = int(task_id)
    if any(int(c) == target for c in candidate_ids):
        return True
    edges = {}
    for from_id, to_id in Task.depends_on.through.objects.values_list('from_task_id', 'to_task_id'):
        edges.setdefault(from_id, set()).add(to_id)
    stack, visited = [int(c) for c in candidate_ids], set()
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        if node == target:
            return True
        stack.extend(n for n in edges.get(node, ()) if n not in visited)
    return False


def validate_dependencies(project_id, raw, *, task_id=None):
    """A clean full-replacement dependency list: existing tasks, same project,
    no self-reference, no cycle. `task_id` is None for a task not created yet
    (which can't be part of a cycle)."""
    ids = parsing.id_list(raw, 'depends_on_ids')
    if task_id is not None and int(task_id) in ids:
        raise ServiceError('A task cannot depend on itself.')
    if not ids:
        return ids
    found = dict(Task.objects.filter(id__in=ids).values_list('id', 'project_id'))
    missing = [t for t in ids if t not in found]
    if missing:
        raise ServiceError(f'Dependency tasks not found: {missing}')
    elsewhere = [t for t in ids if found[t] != project_id]
    if elsewhere:
        raise ServiceError(f'Dependencies must be in the same project. Offending task IDs: {elsewhere}')
    if task_id is not None and _creates_cycle(task_id, ids):
        raise ServiceError('These dependencies would create a cycle.')
    return ids


def _blocked_error(desired, blocking):
    return ServiceError(
        f'Cannot move task to {desired}: blocked by incomplete dependencies.',
        http_status=409,
        blocked_by=[serialize_brief(b) for b in blocking],
        hint='Pass force=true to override, or complete the blocking tasks first.',
    )


# ---------------------------------------------------------------------------
# Due date within the project's dates (D4)
# ---------------------------------------------------------------------------

def _as_moment(d, end_of_day=False):
    if d is None:
        return None
    if hasattr(d, 'hour'):
        return d if timezone.is_aware(d) else timezone.make_aware(d)
    return timezone.make_aware(datetime.combine(d, time(23, 59, 59) if end_of_day else time.min))


def due_date_problem(project, due):
    """(code, message) when `due` falls outside the project's dates, else None."""
    if due is None:
        return None
    start = _as_moment(project.start_date)
    deadline = _as_moment(project.effective_deadline, end_of_day=True)
    if start and due < start:
        return ('task_before_project_start',
                f'Task due_date ({due.date().isoformat()}) is before the project start date '
                f'({start.date().isoformat()}). Move the task later or shift the project start.')
    if deadline and due > deadline:
        return ('task_after_project_deadline',
                f'Task due_date ({due.date().isoformat()}) is after the project deadline '
                f'({deadline.date().isoformat()}). Move the task earlier or extend the project '
                'deadline first.')
    return None


def _check_due_date(project, due):
    problem = due_date_problem(project, due)
    if problem:
        raise ServiceError(problem[1], code=problem[0])


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def create_task(actor, data):
    project = actor.project_for_new_task(data.get('project_id'))
    title = parsing.required_text(data.get('title'), 'Task title')
    fields = {
        'project': project,
        'title': title,
        'description': parsing.optional_text(data.get('description')),
        'status': parsing.choice(data.get('status') or 'todo', Task.STATUS_CHOICES, 'status'),
        'priority': parsing.choice(data.get('priority') or 'medium', Task.PRIORITY_CHOICES, 'priority'),
        'assignee': actor.resolve_assignee(data.get('assignee_id')),
        'due_date': parsing.moment(data.get('due_date')),
        'estimated_hours': parsing.hours(data.get('estimated_hours')),
    }
    _check_due_date(project, fields['due_date'])

    dep_ids = []
    if data.get('depends_on_ids') is not None:
        dep_ids = validate_dependencies(project.id, data.get('depends_on_ids'))
        if fields['status'] in BLOCKING_STATUSES and not parsing.flag(data.get('force')):
            blocking = blockers(None, dep_ids)
            if blocking:
                raise _blocked_error(fields['status'], blocking)

    with transaction.atomic():
        task = Task.objects.create(**fields)
        if dep_ids:
            task.depends_on.set(dep_ids)
    actor.audit('task_created', 'Task', task.id, task.title,
                {'project_id': project.id, 'assignee_id': task.assignee_id})
    return task


def update_task(actor, task_id, data):
    """Apply the fields present in `data`. Returns (task, changed_field_names)."""
    task = actor.task_for_edit(task_id)
    changed = []

    if 'title' in data:
        task.title = parsing.required_text(data.get('title'), 'Task title')
        changed.append('title')
    if 'description' in data:
        task.description = parsing.optional_text(data.get('description'))
        changed.append('description')
    if 'priority' in data:
        task.priority = parsing.choice(data.get('priority'), Task.PRIORITY_CHOICES, 'priority')
        changed.append('priority')

    new_deps = None
    if 'depends_on_ids' in data:
        new_deps = validate_dependencies(task.project_id, data.get('depends_on_ids'), task_id=task.id)

    if 'status' in data:
        desired = parsing.choice(data.get('status'), Task.STATUS_CHOICES, 'status')
        # Only on a real change: resending the current status with an edit
        # shouldn't be refused.
        if (desired != task.status and desired in BLOCKING_STATUSES
                and not parsing.flag(data.get('force'))):
            blocking = blockers(task, new_deps)
            if blocking:
                raise _blocked_error(desired, blocking)
        task.status = desired
        changed.append('status')

    if 'assignee_id' in data:
        raw = data.get('assignee_id')
        # Keeping the current assignee is always allowed, even one who left.
        if not (task.assignee_id and not parsing.is_empty(raw) and str(raw) == str(task.assignee_id)):
            task.assignee = actor.resolve_assignee(raw)
        changed.append('assignee')

    if 'due_date' in data:
        due = parsing.moment(data.get('due_date'))
        if due != task.due_date:
            _check_due_date(task.project, due)
        task.due_date = due
        changed.append('due_date')

    if 'estimated_hours' in data:
        task.estimated_hours = parsing.hours(data.get('estimated_hours'))
        changed.append('estimated_hours')

    with transaction.atomic():
        task.save()
        if new_deps is not None:
            task.depends_on.set(new_deps)
            changed.append('depends_on')
    actor.audit('task_updated', 'Task', task.id, task.title, {'fields': changed})
    return task, changed


def set_dependencies(actor, task_id, raw):
    task = actor.task_for_edit(task_id)
    if raw is None:
        raise ServiceError('depends_on_ids is required (pass [] to clear).')
    ids = validate_dependencies(task.project_id, raw, task_id=task.id)
    with transaction.atomic():
        task.depends_on.set(ids)
    actor.audit('task_updated', 'Task', task.id, task.title, {'fields': ['depends_on']})
    return task


def delete_task(actor, task_id):
    task = actor.task_for_delete(task_id)
    task_pk, title, project_id = task.pk, task.title, task.project_id
    with transaction.atomic():
        removed = {'subtasks': Subtask.objects.filter(task=task).count()}
        task.delete()
    actor.audit('task_deleted', 'Task', task_pk, title, {'project_id': project_id, 'cascade': removed})
    return {'id': task_pk, 'title': title, 'deleted': removed}


def bulk_update_tasks(actor, data):
    """Apply one set of changes to many tasks. Per-task outcome: updated,
    skipped (with a reason) or not found; a bad shared value is a 400 for the
    whole request."""
    raw_ids = data.get('ids') or []
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ServiceError('ids must be a non-empty list of task IDs')
    if len(raw_ids) > BULK_UPDATE_MAX:
        raise ServiceError(f'Too many tasks. Limit is {BULK_UPDATE_MAX} per request.')
    ids = []
    for raw in raw_ids:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not ids:
        raise ServiceError('No valid task IDs provided')
    if not any(k in data for k in ('status', 'priority', 'assignee_id', 'due_date')):
        raise ServiceError('No fields to update. Provide status, priority, assignee_id, or due_date.')

    force = parsing.flag(data.get('force'))
    new_status = (parsing.choice(data.get('status'), Task.STATUS_CHOICES, 'status')
                  if 'status' in data else None)
    new_priority = (parsing.choice(data.get('priority'), Task.PRIORITY_CHOICES, 'priority')
                    if 'priority' in data else None)
    assignee_change = 'assignee_id' in data
    new_assignee = actor.resolve_assignee(data.get('assignee_id')) if assignee_change else None
    due_change = 'due_date' in data
    new_due = parsing.moment(data.get('due_date')) if due_change else None

    found = {t.id: t for t in Task.objects.filter(id__in=ids).select_related('project', 'assignee')}
    not_found = [tid for tid in ids if tid not in found]
    updated, skipped = [], []

    # One transaction for the batch, a savepoint per task: one bad task
    # doesn't undo the others, and a crash midway changes nothing.
    with transaction.atomic():
        for tid in ids:
            task = found.get(tid)
            if task is None:
                continue
            if not actor.can_edit_task(task):
                skipped.append({'id': tid, 'reason': 'access_denied'})
                continue
            fields = []
            if new_status is not None and task.status != new_status:
                if new_status in BLOCKING_STATUSES and not force:
                    blocking = blockers(task)
                    if blocking:
                        skipped.append({'id': tid, 'reason': 'blocked_by_dependencies',
                                        'blocked_by': [b.id for b in blocking]})
                        continue
                task.status = new_status
                fields.append('status')
            if new_priority is not None and task.priority != new_priority:
                task.priority = new_priority
                fields.append('priority')
            if assignee_change and (task.assignee_id or None) != (new_assignee.id if new_assignee else None):
                task.assignee = new_assignee
                fields.append('assignee')
            if due_change and task.due_date != new_due:
                problem = due_date_problem(task.project, new_due)
                if problem:
                    skipped.append({'id': tid, 'reason': problem[0]})
                    continue
                task.due_date = new_due
                fields.append('due_date')
            if not fields:
                skipped.append({'id': tid, 'reason': 'no_change'})
                continue
            try:
                with transaction.atomic():
                    task.save(update_fields=fields + ['updated_at'])
                updated.append(tid)
            except Exception:
                logger.exception('Bulk task update failed for task %s', tid)
                skipped.append({'id': tid, 'reason': 'save_failed'})

    if updated:
        actor.audit('task_updated', 'Task', None, f'{len(updated)} tasks',
                    {'bulk': True, 'ids': updated})
    return {'updated': updated, 'skipped': skipped, 'not_found': not_found,
            'requested': len(ids)}

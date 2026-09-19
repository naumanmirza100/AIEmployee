"""Create, update and delete projects — the one implementation behind all
three PM API families. Views translate requests into these calls and format
the result in their own response shape.
"""
from django.db import transaction

from core.models import Industry, Project, Subtask, Task

from . import parsing
from .errors import ServiceError

PROJECT_CHOICE_FIELDS = (
    ('status', Project.STATUS_CHOICES),
    ('priority', Project.PRIORITY_CHOICES),
    ('project_type', Project.PROJECT_TYPE_CHOICES),
)


def _industry(value):
    if parsing.is_empty(value):
        return None
    try:
        return Industry.objects.get(pk=int(value))
    except (TypeError, ValueError, Industry.DoesNotExist):
        raise ServiceError('Invalid industry_id')


def _check_budget_range(budget_min, budget_max):
    if budget_min is not None and budget_max is not None and budget_max < budget_min:
        raise ServiceError('budget_max must be greater than or equal to budget_min.')


def _deadline_key(data):
    """`end_date` is the legacy alias of `deadline`: whichever is sent."""
    if 'deadline' in data and data.get('deadline') is not None:
        return 'deadline'
    return 'end_date' if 'end_date' in data else ('deadline' if 'deadline' in data else None)


def create_project(actor, data):
    """Validate and create a project. Raises ServiceError; saves nothing then."""
    name = parsing.required_text(data.get('name'), 'Project name')
    fields = {
        'name': name,
        'description': parsing.optional_text(data.get('description')),
        'status': parsing.choice(data.get('status') or 'planning', Project.STATUS_CHOICES, 'status'),
        'priority': parsing.choice(data.get('priority') or 'medium', Project.PRIORITY_CHOICES, 'priority'),
        'project_type': parsing.choice(data.get('project_type') or 'web_app',
                                       Project.PROJECT_TYPE_CHOICES, 'project_type'),
        'industry': _industry(data.get('industry_id')),
        'budget_min': parsing.budget(data.get('budget_min'), 'budget_min'),
        'budget_max': parsing.budget(data.get('budget_max'), 'budget_max'),
    }
    _check_budget_range(fields['budget_min'], fields['budget_max'])

    key = _deadline_key(data)
    deadline = parsing.day(data.get(key), 'deadline') if key else None
    fields['deadline'] = fields['end_date'] = deadline
    fields['start_date'] = parsing.day(data.get('start_date'), 'start_date')

    fields.update(actor.new_project_fields())

    # Soft duplicate-name guard, company-wide: the client confirms by resending
    # with confirm_duplicate_name=true (the dashboards show a confirm dialog).
    if not parsing.flag(data.get('confirm_duplicate_name')):
        duplicate = actor.duplicate_name_scope().filter(name__iexact=name).first()
        if duplicate is not None:
            raise ServiceError(
                f'A project named "{duplicate.name}" already exists in this workspace. '
                'Resubmit with confirm_duplicate_name=true to create it anyway.',
                http_status=409, code='duplicate_project_name',
                data={'existing_project_id': duplicate.id},
            )

    with transaction.atomic():
        project = Project.objects.create(**fields)
    actor.audit('project_created', 'Project', project.id, project.name)
    return project


def update_project(actor, project_id, data):
    """Apply the fields present in `data`. Returns (project, changed_field_names)."""
    project = actor.project_for_edit(project_id)
    changed = []

    if 'name' in data:
        project.name = parsing.required_text(data.get('name'), 'Project name')
        changed.append('name')
    if 'description' in data:
        project.description = parsing.optional_text(data.get('description'))
        changed.append('description')
    for field, choices in PROJECT_CHOICE_FIELDS:
        if field in data:
            setattr(project, field, parsing.choice(data.get(field), choices, field))
            changed.append(field)

    key = _deadline_key(data)
    if key:
        project.deadline = project.end_date = parsing.day(data.get(key), 'deadline')
        changed.append('deadline')
    if 'start_date' in data:
        project.start_date = parsing.day(data.get('start_date'), 'start_date')
        changed.append('start_date')

    if 'industry_id' in data:
        project.industry = _industry(data.get('industry_id'))
        changed.append('industry')
    if 'budget_min' in data:
        project.budget_min = parsing.budget(data.get('budget_min'), 'budget_min')
        changed.append('budget_min')
    if 'budget_max' in data:
        project.budget_max = parsing.budget(data.get('budget_max'), 'budget_max')
        changed.append('budget_max')
    _check_budget_range(project.budget_min, project.budget_max)

    with transaction.atomic():
        project.save()
    actor.audit('project_updated', 'Project', project.id, project.name, {'fields': changed})
    return project, changed


def delete_project(actor, project_id):
    """Hard delete (tasks and subtasks cascade). Returns what was removed."""
    project = actor.project_for_delete(project_id)
    project_pk, name = project.pk, project.name
    with transaction.atomic():
        removed = {
            'tasks': Task.objects.filter(project=project).count(),
            'subtasks': Subtask.objects.filter(task__project=project).count(),
        }
        project.delete()
    actor.audit('project_deleted', 'Project', project_pk, name, {'cascade': removed})
    return {'id': project_pk, 'name': name, 'deleted': removed}

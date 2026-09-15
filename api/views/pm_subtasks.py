"""Manual CRUD for subtasks (GAP-1).

Subtasks were AI-generated only: `generate_subtasks` created them, and nothing
let a user add one by hand, fix a bad title, tick one off, reorder, or delete
it. Their `status`, `order` and `completed_at` fields were effectively
unreachable from the product.

Routes (all under the gated `/api/project-manager/` prefix, so the module
subscription check applies automatically):

    GET    tasks/<task_id>/subtasks/            list
    POST   tasks/<task_id>/subtasks/create/     create
    POST   tasks/<task_id>/subtasks/reorder/    reorder  {"order": [id, id, ...]}
    PATCH  subtasks/<subtask_id>/update/        update
    DELETE subtasks/<subtask_id>/delete/        delete

Tenancy: a task is reachable if its project belongs to the caller's company, or
was created by the caller. The second clause matters for older Project Pilot
uploads, which were saved with company=NULL (see project_pilot_pipeline.py);
without it their subtasks would be unreachable.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes, throttle_classes,
)
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from api.views.pm_agent import PMCRUDThrottle, _audit_log
from core.models import Subtask, Task

logger = logging.getLogger(__name__)

_TITLE_MAX = Subtask._meta.get_field('title').max_length
_VALID_STATUSES = {c[0] for c in Subtask.STATUS_CHOICES}


def _err(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({'status': 'error', 'message': message}, status=code)


def _task_scope(company_user):
    company = getattr(company_user, 'company', None)
    q = Q(project__created_by_company_user=company_user)
    if company is not None:
        q |= Q(project__company=company)
    return Task.objects.filter(q)


def _get_task(company_user, task_id):
    return _task_scope(company_user).select_related('project').filter(pk=task_id).first()


def _get_subtask(company_user, subtask_id):
    company = getattr(company_user, 'company', None)
    q = Q(task__project__created_by_company_user=company_user)
    if company is not None:
        q |= Q(task__project__company=company)
    return (Subtask.objects.filter(q).select_related('task', 'task__project')
            .filter(pk=subtask_id).first())


def _serialize(st):
    return {
        'id': st.id,
        'task_id': st.task_id,
        'title': st.title,
        'description': st.description,
        'status': st.status,
        'order': st.order,
        'completed_at': st.completed_at.isoformat() if st.completed_at else None,
        'created_at': st.created_at.isoformat() if st.created_at else None,
        'updated_at': st.updated_at.isoformat() if st.updated_at else None,
    }


def _clean_title(raw):
    title = str(raw or '').strip()
    if not title:
        raise ValueError('title is required.')
    if len(title) > _TITLE_MAX:
        raise ValueError(f'title must be at most {_TITLE_MAX} characters.')
    return title


def _apply_status(st, new_status):
    """Set status and keep `completed_at` honest in both directions."""
    if new_status not in _VALID_STATUSES:
        raise ValueError(f'status must be one of: {", ".join(sorted(_VALID_STATUSES))}.')
    if new_status == 'done' and st.status != 'done':
        st.completed_at = timezone.now()
    elif new_status != 'done':
        st.completed_at = None
    st.status = new_status


def _clean_order(raw):
    try:
        order = int(raw)
    except (TypeError, ValueError):
        raise ValueError('order must be an integer.')
    if order < 0:
        raise ValueError('order must be zero or greater.')
    return order


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([PMCRUDThrottle])
def list_subtasks(request, task_id):
    task = _get_task(request.user, task_id)
    if task is None:
        return _err('Task not found.', status.HTTP_404_NOT_FOUND)
    subtasks = list(task.subtasks.all())  # Meta.ordering = (order, created_at)
    done = sum(1 for s in subtasks if s.status == 'done')
    return Response({
        'status': 'success',
        'data': {
            'task_id': task.id,
            'subtasks': [_serialize(s) for s in subtasks],
            'total': len(subtasks),
            'done': done,
        },
    })


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([PMCRUDThrottle])
def create_subtask(request, task_id):
    task = _get_task(request.user, task_id)
    if task is None:
        return _err('Task not found.', status.HTTP_404_NOT_FOUND)
    data = request.data or {}
    try:
        title = _clean_title(data.get('title'))
        st = Subtask(task=task, title=title,
                     description=str(data.get('description') or ''))
        if 'status' in data:
            _apply_status(st, data.get('status'))
        if 'order' in data and data.get('order') is not None:
            st.order = _clean_order(data.get('order'))
        else:
            # Append to the end rather than colliding at order=0.
            top = task.subtasks.aggregate(m=Max('order'))['m']
            st.order = 0 if top is None else top + 1
    except ValueError as exc:
        return _err(str(exc))
    st.save()
    _audit_log(request.user, 'subtask_created', 'Subtask', st.id, st.title,
               {'task_id': task.id})
    return Response({'status': 'success', 'data': _serialize(st)},
                    status=status.HTTP_201_CREATED)


@api_view(['PATCH', 'PUT'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([PMCRUDThrottle])
def update_subtask(request, subtask_id):
    st = _get_subtask(request.user, subtask_id)
    if st is None:
        return _err('Subtask not found.', status.HTTP_404_NOT_FOUND)
    data = request.data or {}
    changed = []
    try:
        if 'title' in data:
            st.title = _clean_title(data.get('title'))
            changed.append('title')
        if 'description' in data:
            st.description = str(data.get('description') or '')
            changed.append('description')
        if 'status' in data:
            _apply_status(st, data.get('status'))
            changed += ['status', 'completed_at']
        if 'order' in data:
            st.order = _clean_order(data.get('order'))
            changed.append('order')
    except ValueError as exc:
        return _err(str(exc))
    if not changed:
        return _err('Nothing to update. Provide title, description, status, or order.')
    st.save(update_fields=sorted(set(changed)) + ['updated_at'])
    _audit_log(request.user, 'subtask_updated', 'Subtask', st.id, st.title,
               {'task_id': st.task_id, 'fields': sorted(set(changed))})
    return Response({'status': 'success', 'data': _serialize(st)})


@api_view(['DELETE', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([PMCRUDThrottle])
def delete_subtask(request, subtask_id):
    st = _get_subtask(request.user, subtask_id)
    if st is None:
        return _err('Subtask not found.', status.HTTP_404_NOT_FOUND)
    snapshot = {'task_id': st.task_id, 'title': st.title, 'status': st.status}
    sid = st.id
    st.delete()
    _audit_log(request.user, 'subtask_deleted', 'Subtask', sid, snapshot['title'], snapshot)
    return Response({'status': 'success', 'data': {'id': sid, 'deleted': True}})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([PMCRUDThrottle])
def reorder_subtasks(request, task_id):
    """Body: {"order": [subtask_id, ...]} listing EVERY subtask of the task.

    Requiring the full set keeps the result unambiguous — a partial list would
    leave the unlisted subtasks' positions undefined relative to the listed ones.
    """
    task = _get_task(request.user, task_id)
    if task is None:
        return _err('Task not found.', status.HTTP_404_NOT_FOUND)
    raw = (request.data or {}).get('order')
    if not isinstance(raw, list) or not raw:
        return _err('order must be a non-empty list of subtask IDs.')
    try:
        ids = [int(x) for x in raw]
    except (TypeError, ValueError):
        return _err('order must contain only integer subtask IDs.')
    if len(set(ids)) != len(ids):
        return _err('order contains duplicate IDs.')

    existing = set(task.subtasks.values_list('id', flat=True))
    if set(ids) != existing:
        missing = sorted(existing - set(ids))
        foreign = sorted(set(ids) - existing)
        parts = []
        if missing:
            parts.append(f'missing subtask IDs {missing}')
        if foreign:
            parts.append(f'IDs not belonging to this task {foreign}')
        return _err('order must list every subtask of this task exactly once: '
                    + '; '.join(parts) + '.')

    by_id = {s.id: s for s in task.subtasks.all()}
    with transaction.atomic():
        for position, sid in enumerate(ids):
            st = by_id[sid]
            if st.order != position:
                st.order = position
                st.save(update_fields=['order', 'updated_at'])
    _audit_log(request.user, 'subtasks_reordered', 'Task', task.id, task.title,
               {'order': ids})
    return Response({
        'status': 'success',
        'data': {'task_id': task.id,
                 'subtasks': [_serialize(s) for s in task.subtasks.all()]},
    })

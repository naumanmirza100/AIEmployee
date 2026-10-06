"""A support ticket that needs building becomes a Project Manager task.

A bug report or a feature request reaching Frontline used to be retyped into
the Project Manager agent by hand, and the ticket never learned when the work
was done. Now the ticket's owner turns it into a task — pre-filled from the
ticket, reviewed, created through PM's own service layer (its checks, its
audit log) — and the two stay linked: when the task is marked done the ticket
gets an internal note, once, and its owner a bell alert, so the customer can
be told.

The link works both ways. When the ticket is closed, reopened or made urgent,
the task gets a comment and its assignee an alert: they used to hear nothing,
and could go on building something the customer no longer needed. And when the
task (or its whole project) is deleted, the ticket says so in a note and its
owner is told; the link used to vanish without a trace.

API: `frontline/tickets/<id>/task` (GET the review form, POST create).
"""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

#: Ticket priority → task priority. PM has no "urgent"; high is its top.
PRIORITY = {'low': 'low', 'medium': 'medium', 'high': 'high', 'urgent': 'high'}
#: A due date to suggest, in working days from today, by ticket priority.
DUE_IN_WORKDAYS = {'urgent': 2, 'high': 5, 'medium': 10, 'low': 20}


def pm_available(company) -> bool:
    from core.modules import has_module
    return bool(company) and has_module(company, 'project_manager_agent')


def _add_workdays(start, days):
    day = start
    while days > 0:
        day += timedelta(days=1)
        if day.weekday() < 5:
            days -= 1
    return day


def task_summary(task):
    if task is None:
        return None
    return {'id': task.id, 'title': task.title, 'status': task.status,
            'status_label': task.get_status_display(),
            'project': task.project.name if task.project_id else ''}


def form(ticket, company_user) -> dict:
    """The review form: pre-filled values, and the projects and people to pick."""
    from core.tenancy import members_of, projects_for_company_user
    customer = ''
    if ticket.contact_id:
        contact = ticket.contact
        customer = (f"\nCustomer: {contact.name} <{contact.email}>" if contact.name
                    else f"\nCustomer: {contact.email}")
    description = (ticket.description or '').strip()
    description += f"\n\nFrom Frontline ticket #{ticket.id}: {ticket.title}{customer}"
    due = _add_workdays(timezone.localdate(), DUE_IN_WORKDAYS.get(ticket.priority, 10))
    return {
        'pm_available': pm_available(company_user.company),
        'linked': task_summary(ticket.pm_task) if ticket.pm_task_id else None,
        'prefill': {
            'title': ticket.title[:200],
            'description': description.strip(),
            'priority': PRIORITY.get(ticket.priority, 'medium'),
            'due_date': due.isoformat(),
            'project_id': None,
            'assignee_id': None,
        },
        'projects': [
            {'id': p.id, 'name': p.name}
            for p in projects_for_company_user(company_user)
            .exclude(status__in=('completed', 'cancelled')).order_by('name')[:200]
        ],
        'assignees': [
            {'id': u.id, 'name': (u.get_full_name() or u.username).strip()}
            for u in members_of(company_user.company).order_by('first_name', 'username')[:500]
        ],
    }


def create_task(ticket, company_user, data):
    """Create the task through PM's service layer and link it. Raises
    `ServiceError` (with its HTTP status) for anything PM refuses."""
    from project_manager_agent import services as pm_services
    from project_manager_agent.services.actor import DashboardActor
    from Frontline_agent.models import TicketNote

    with transaction.atomic():
        task = pm_services.create_task(DashboardActor(company_user), {
            'project_id': data.get('project_id'),
            'title': data.get('title'),
            'description': data.get('description'),
            'priority': data.get('priority') or 'medium',
            'assignee_id': data.get('assignee_id') or None,
            'due_date': data.get('due_date') or None,
        })
        ticket.pm_task = task
        ticket.pm_task_done_noted_at = None
        ticket.save(update_fields=['pm_task', 'pm_task_done_noted_at', 'updated_at'])
        TicketNote.objects.create(
            ticket=ticket, author=company_user.login_user, is_internal=True,
            body=f'Project task created: "{task.title}" in {task.project.name}.')
    return task


def task_changed(task):
    """Called whenever a task is saved. Done: note it on its tickets (once)
    and tell their owners. Reopened: forget, so the next done is noted too."""
    from Frontline_agent.models import Ticket, TicketNote
    tickets = list(Ticket.objects.filter(pm_task=task).select_related('assigned_to'))
    if not tickets:
        return
    if task.status != 'done':
        Ticket.objects.filter(pm_task=task, pm_task_done_noted_at__isnull=False).update(
            pm_task_done_noted_at=None, updated_at=timezone.now())
        return
    for ticket in tickets:
        if ticket.pm_task_done_noted_at:
            continue
        TicketNote.objects.create(
            ticket=ticket, author=None, is_internal=True,
            body=f'The project task "{task.title}" is done. You can let the customer know.')
        ticket.pm_task_done_noted_at = timezone.now()
        ticket.save(update_fields=['pm_task_done_noted_at', 'updated_at'])
        _tell_owner(ticket, title=f'Done: the task for ticket #{ticket.id}',
                    message=f'"{task.title}" is finished. You can let the customer know.')


def task_deleted(task):
    """Called just before a task is deleted, alone or with its project. Each
    ticket linked to it keeps a note saying so, and its owner is told."""
    from Frontline_agent.models import Ticket, TicketNote
    for ticket in Ticket.objects.filter(pm_task_id=task.pk):
        TicketNote.objects.create(
            ticket=ticket, author=None, is_internal=True,
            body=(f'The project task "{task.title}" was deleted, so this ticket no longer has one. '
                  'Make a new task if the work is still needed.'))
        if ticket.status not in CLOSED:
            _tell_owner(ticket, title=f'The task for ticket #{ticket.id} was deleted',
                        message=f'"{task.title}" no longer exists. Make a new task if the work is still needed.')


#: A ticket in one of these is finished with.
CLOSED = ('resolved', 'closed')


def ticket_changed(ticket, before):
    """Called after a linked ticket is saved, with its status and priority as
    they were. Closing, reopening or making it urgent is written on the task
    and its assignee is told. Anything else says nothing."""
    from core.models import Notification, TaskComment
    task = ticket.pm_task
    if task is None or not before:
        return
    was_closed, is_closed = before.get('status') in CLOSED, ticket.status in CLOSED
    if is_closed and not was_closed:
        said = (f'Frontline ticket #{ticket.id} was {ticket.get_status_display().lower()}. '
                'Check whether this task is still needed.')
    elif was_closed and not is_closed:
        said = f'Frontline ticket #{ticket.id} was reopened: the customer still needs this.'
    elif ticket.priority == 'urgent' and before.get('priority') != 'urgent' and not is_closed:
        said = f'Frontline ticket #{ticket.id} is now urgent.'
    else:
        return
    author = ticket.assigned_to or ticket.created_by
    if author is not None:
        TaskComment.objects.create(task=task, user=author, comment_text=said)
    if task.assignee_id and task.status != 'done':
        Notification.objects.create(
            user_id=task.assignee_id, type='task_updated', notification_type='task_updated',
            title=f'News on your task: {task.title}'[:255], message=said, action_url='/me/tasks')


def _tell_owner(ticket, *, title, message):
    """Alert the dashboard login that owns the ticket; if the owner has none
    (the chat widget's system account), the login that created it."""
    from core.models import CompanyUser
    from core.notification_utils import notify_company_users
    if not ticket.company_id:
        return
    logins = CompanyUser.objects.filter(company_id=ticket.company_id, is_active=True)
    owner = None
    for user_id in (ticket.assigned_to_id, ticket.created_by_id):
        owner = logins.filter(login_user_id=user_id).first() if user_id else None
        if owner is not None:
            break
    if owner is None:
        return
    notify_company_users(
        [owner],
        title=title,
        message=message,
        link='/frontline/dashboard?tab=tickets',
        kind='frontline_ticket_task_done',
    )

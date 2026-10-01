"""Hand over a leaver's open work in every agent.

Offboarding someone used to leave everything they owned where it was: their
open project tasks, the support tickets assigned to them, the people who
report to them, their seats on upcoming interviews. This finds all of it,
grouped by agent, and moves each group to the person HR picks — only once HR
confirms.

What is *listed but not moved*: upcoming meetings they organise and projects
they lead. Those involve other people's invitations and project ownership, so
HR deals with them deliberately in their own agent.

A person appears under up to two logins: their employee login
(`Employee.user`) and their dashboard login's (`CompanyUser.login_user`,
which Frontline stores on tickets). Both are searched.
"""
from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.notification_utils import notify_company_users

OPEN_TICKET_STATUSES = ('new', 'open', 'in_progress')
OPEN_INTERVIEW_STATUSES = ('PENDING', 'SCHEDULED', 'RESCHEDULED')
LIST_LIMIT = 50


# ---------------------------------------------------------------------------
# Who the leaver is in each agent
# ---------------------------------------------------------------------------

def dashboard_login(employee):
    from core.models import CompanyUser
    if employee.company_user_id:
        return employee.company_user
    if employee.work_email:
        return CompanyUser.objects.filter(company_id=employee.company_id,
                                          email__iexact=employee.work_email).first()
    return None


def login_ids(employee) -> set[int]:
    ids = {employee.user_id} if employee.user_id else set()
    cu = dashboard_login(employee)
    if cu is not None and cu.login_user_id:
        ids.add(cu.login_user_id)
    return ids


def company_user_for_login(user, company_id):
    """The dashboard login whose bell should hear about work given to `user`."""
    from core.models import CompanyUser
    from hr_agent.models import Employee
    found = CompanyUser.objects.filter(company_id=company_id, login_user=user, is_active=True).first()
    if found:
        return found
    emp = Employee.objects.filter(company_id=company_id, user=user, company_user__isnull=False).first()
    if emp:
        return emp.company_user
    if user.email:
        return CompanyUser.objects.filter(company_id=company_id, email__iexact=user.email,
                                          is_active=True).first()
    return None


# ---------------------------------------------------------------------------
# What they own
# ---------------------------------------------------------------------------

def _tasks(company_id, ids):
    from core.models import Task
    return (Task.objects.filter(assignee_id__in=ids).exclude(status='done')
            .filter(Q(project__company_id=company_id)
                    | Q(project__created_by_company_user__company_id=company_id))
            .select_related('project').order_by('due_date', 'id'))


def _tickets(company_id, ids):
    from Frontline_agent.models import Ticket
    return (Ticket.objects.filter(company_id=company_id, assigned_to_id__in=ids,
                                  status__in=OPEN_TICKET_STATUSES).order_by('-created_at'))


def _reports(employee):
    from hr_agent.models import Employee
    return (Employee.objects.filter(company_id=employee.company_id, manager=employee)
            .exclude(employment_status='offboarded').order_by('full_name'))


def _interviews(company_id, ids):
    from recruitment_agent.models import Interview
    return (Interview.objects.filter(interviewers__id__in=ids, company_user__company_id=company_id,
                                     status__in=OPEN_INTERVIEW_STATUSES)
            .distinct().order_by('scheduled_datetime', 'id'))


def _meetings_they_organise(employee, ids):
    """(agent, title, when) of upcoming meetings they organise — listed only."""
    now = timezone.now()
    out = []
    cu = dashboard_login(employee)
    try:
        from project_manager_agent.models import ScheduledMeeting
        if cu is not None:
            for m in (ScheduledMeeting.objects.filter(organizer=cu, proposed_time__gte=now)
                      .exclude(status__in=('rejected', 'withdrawn')).order_by('proposed_time')[:LIST_LIMIT]):
                out.append({'agent': 'Project Manager', 'title': m.title, 'when': m.proposed_time.isoformat()})
    except Exception:
        pass
    from hr_agent.models import HRMeeting
    for m in (HRMeeting.objects.filter(organizer=employee, scheduled_at__gte=now)
              .exclude(status__in=('cancelled', 'completed')).order_by('scheduled_at')[:LIST_LIMIT]):
        out.append({'agent': 'HR', 'title': m.title, 'when': m.scheduled_at.isoformat()})
    try:
        from Frontline_agent.models import FrontlineMeeting
        for m in (FrontlineMeeting.objects.filter(organizer_id__in=ids, scheduled_at__gte=now,
                                                  status__in=('scheduled', 'rescheduled'))
                  .order_by('scheduled_at')[:LIST_LIMIT]):
            out.append({'agent': 'Frontline', 'title': m.title, 'when': m.scheduled_at.isoformat()})
    except Exception:
        pass
    return sorted(out, key=lambda m: m['when'])


def _projects_they_lead(company_id, ids):
    from core.models import Project
    return list(Project.objects.filter(project_manager_id__in=ids, company_id=company_id)
                .exclude(status__in=('completed', 'cancelled')).values('id', 'name')[:LIST_LIMIT])


# ---------------------------------------------------------------------------
# Who it can go to
# ---------------------------------------------------------------------------

def _people(company_id, exclude_ids):
    from core.models import Company
    from core.tenancy import members_of
    company = Company.objects.filter(pk=company_id).first()
    return [{'id': u.id, 'name': (u.get_full_name() or u.username).strip()}
            for u in members_of(company).exclude(pk__in=exclude_ids).order_by('first_name', 'username')[:500]]


def _dashboard_logins(company_id, exclude_id):
    from core.models import CompanyUser
    return [{'id': cu.id, 'name': cu.full_name or cu.email}
            for cu in CompanyUser.objects.filter(company_id=company_id, is_active=True)
            .exclude(pk=exclude_id).order_by('full_name')[:500]]


def _managers(employee):
    from hr_agent.models import Employee
    return [{'id': e.id, 'name': e.full_name}
            for e in Employee.objects.filter(company_id=employee.company_id)
            .exclude(pk=employee.pk).exclude(employment_status__in=('offboarded', 'candidate'))
            .order_by('full_name')[:500]]


# ---------------------------------------------------------------------------
# The form, and doing it
# ---------------------------------------------------------------------------

def summary(employee) -> dict:
    """What the hand-over form shows."""
    ids = login_ids(employee)
    cu = dashboard_login(employee)
    company_id = employee.company_id

    tasks = _tasks(company_id, ids) if ids else None
    tickets = _tickets(company_id, ids) if ids else None
    reports = _reports(employee)
    interviews = _interviews(company_id, ids) if ids else None

    def group(key, label, qs, item, targets, hint=''):
        rows = list(qs[:LIST_LIMIT]) if qs is not None else []
        return {'key': key, 'label': label, 'count': qs.count() if qs is not None else 0,
                'items': [item(r) for r in rows], 'targets': targets, 'hint': hint}

    groups = [
        group('tasks', 'Open project tasks', tasks,
              lambda t: {'id': t.id, 'title': t.title, 'detail': t.project.name if t.project_id else '',
                         'due': t.due_date.date().isoformat() if t.due_date else None},
              _people(company_id, ids)),
        group('tickets', 'Open support tickets', tickets,
              lambda t: {'id': t.id, 'title': f'#{t.id} {t.title}', 'detail': t.get_status_display()},
              _dashboard_logins(company_id, cu.id if cu else None)),
        group('reports', 'People who report to them', reports,
              lambda e: {'id': e.id, 'title': e.full_name, 'detail': e.job_title},
              _managers(employee), hint='Their new manager.'),
        group('interviews', 'Interviews they sit in on', interviews,
              lambda i: {'id': i.id, 'title': f'{i.candidate_name} — {i.job_role}',
                         'detail': i.scheduled_datetime.isoformat() if i.scheduled_datetime else 'Not booked yet'},
              _people(company_id, ids),
              hint='Takes their seat. Anyone busy at a booked interview is skipped.'),
    ]
    return {
        'employee': {'id': employee.id, 'full_name': employee.full_name,
                     'employment_status': employee.employment_status},
        'groups': [g for g in groups if g['count']],
        'meetings': _meetings_they_organise(employee, ids),
        'projects_led': _projects_they_lead(company_id, ids),
    }


def hand_over(employee, assignments: dict, actor) -> dict:
    """Move each group in `assignments` ({group key: target id}) to its target.

    Returns {group: {'moved': n, 'to': name, 'skipped': [reasons]}}. Raises
    ValueError for a target that isn't allowed, before anything moves.
    """
    from core.models import CompanyUser
    from core.tenancy import members_of
    from hr_agent.models import Employee

    ids = login_ids(employee)
    company = employee.company
    members = members_of(company)
    plan = {}
    for key, target_id in (assignments or {}).items():
        if target_id in (None, ''):
            continue
        if key in ('tasks', 'interviews'):
            target = members.filter(pk=target_id).exclude(pk__in=ids).first()
        elif key == 'tickets':
            cu = dashboard_login(employee)
            target = (CompanyUser.objects.filter(company=company, pk=target_id, is_active=True)
                      .exclude(pk=cu.pk if cu else None).first())
        elif key == 'reports':
            target = (Employee.objects.filter(company=company, pk=target_id)
                      .exclude(pk=employee.pk).exclude(employment_status__in=('offboarded', 'candidate')).first())
        else:
            raise ValueError(f'Unknown group: {key}')
        if target is None:
            raise ValueError(f'Choose someone in your company for {key}.')
        plan[key] = target

    results = {}
    with transaction.atomic():
        if 'tasks' in plan:
            results['tasks'] = _move_tasks(company.id, ids, plan['tasks'], actor)
        if 'tickets' in plan:
            results['tickets'] = _move_tickets(company.id, ids, plan['tickets'], actor)
        if 'reports' in plan:
            results['reports'] = _move_reports(employee, plan['reports'])
        if 'interviews' in plan:
            results['interviews'] = _move_interview_seats(company.id, ids, plan['interviews'])
    _tell_recipients(employee, plan, results)
    return results


def _name(user):
    return (user.get_full_name() or user.username).strip()


def _move_tasks(company_id, ids, target, actor):
    from project_manager_agent import services as pm_services
    from project_manager_agent.services.actor import DashboardActor
    from project_manager_agent.services.errors import ServiceError
    pm_actor = DashboardActor(actor)
    moved, skipped = 0, []
    for task in list(_tasks(company_id, ids)):
        try:
            pm_services.update_task(pm_actor, task.id, {'assignee_id': target.id})
            moved += 1
        except ServiceError as exc:
            skipped.append(f'{task.title}: {exc}')
    return {'moved': moved, 'to': _name(target), 'skipped': skipped}


def _move_tickets(company_id, ids, target_cu, actor):
    from api.views.frontline_agent import _get_or_create_user_for_company_user, _write_frontline_audit_log
    from Frontline_agent import alerts as frontline_alerts
    login = _get_or_create_user_for_company_user(target_cu)
    tickets = list(_tickets(company_id, ids))
    for t in tickets:
        before = t.assigned_to_id
        t.assigned_to = login
        t.save(update_fields=['assigned_to', 'updated_at'])
        _write_frontline_audit_log(actor, target_cu.company, 'ticket.handover', 'ticket', t.id,
                                   before={'assigned_to_id': before},
                                   after={'assigned_to_id': login.id})
    frontline_alerts.tickets_assigned(tickets, target_cu, actor=actor)
    return {'moved': len(tickets), 'to': target_cu.full_name or target_cu.email, 'skipped': []}


def _move_reports(employee, new_manager):
    moved = 0
    for report in list(_reports(employee)):
        if report.pk == new_manager.pk:
            continue          # can't manage themselves; keeps their current manager blank
        report.manager = new_manager
        report.save(update_fields=['manager', 'updated_at'])
        moved += 1
    return {'moved': moved, 'to': new_manager.full_name, 'skipped': []}


def _move_interview_seats(company_id, ids, target):
    from core.scheduling import ScheduleConflict, booking_guard, ensure_free
    from recruitment_agent.interview_time import stored_zone
    moved, skipped = 0, []
    for interview in list(_interviews(company_id, ids)):
        booked = interview.scheduled_datetime is not None and interview.status in ('SCHEDULED', 'RESCHEDULED')
        try:
            with booking_guard([target.id]):
                if booked:
                    ensure_free([target.id], interview.scheduled_datetime, interview.duration_minutes,
                                tz_name=stored_zone(interview), viewer_source='recruitment',
                                exclude=[('recruitment', interview.id)], suggest=False)
                interview.interviewers.remove(*ids)
                interview.interviewers.add(target)
            moved += 1
        except ScheduleConflict as clash:
            why = clash.clashes[0].describe(stored_zone(interview)) if clash.clashes else f'{_name(target)} is busy then'
            skipped.append(f'{interview.candidate_name}: {why}')
    return {'moved': moved, 'to': _name(target), 'skipped': skipped}


def _tell_recipients(employee, plan, results):
    """One bell alert per recipient per group."""
    links = {'tasks': '/project-manager/dashboard', 'tickets': '/frontline/dashboard?tab=tickets',
             'reports': '/hr/dashboard?tab=my_team', 'interviews': '/recruitment/interviews'}
    nouns = {'tasks': ('task', 'tasks'), 'reports': ('person now reports', 'people now report'),
             'interviews': ('interview', 'interviews')}
    for key, target in plan.items():
        moved = results.get(key, {}).get('moved', 0)
        if not moved or key == 'tickets':          # tickets alert their new owner already
            continue
        if key == 'reports':
            recipient = target.company_user
            title = f"{moved} {nouns[key][moved != 1]} to you"
        else:
            recipient = company_user_for_login(target, employee.company_id)
            title = f"{moved} {nouns[key][moved != 1]} handed over to you"
        if recipient is not None:
            notify_company_users([recipient], title=title,
                                 message=f'From {employee.full_name}, who is leaving.',
                                 link=links[key], kind=f'handover_{key}')

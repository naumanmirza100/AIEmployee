"""Hand over a leaver's open work in every agent.

Offboarding someone used to leave everything they owned where it was. This
finds all of it, grouped, and moves each group to the person HR picks — only
once HR confirms:

  * Project Manager: open tasks, projects they lead;
  * Frontline: open tickets;
  * HR: the people who report to them, leave requests waiting for their
    decision;
  * Recruitment: interviews they run, and seats on interviews they sit in on;
  * upcoming meetings they organise, in PM, HR and Frontline.

Anything with a time (a booked interview, a meeting) is only moved to someone
free then; the rest of the group still moves, and the form says what was
skipped and why.

A person appears under up to two logins: their employee login
(`Employee.user`) and their dashboard login's (`CompanyUser.login_user`,
which Frontline stores on tickets). Both are searched.
"""
from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Lower
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


def _interviews_run(cu):
    """Interviews this dashboard login runs as the recruiter."""
    from recruitment_agent.models import Interview
    if cu is None:
        return Interview.objects.none()
    return (Interview.objects.filter(company_user=cu, status__in=OPEN_INTERVIEW_STATUSES)
            .order_by('scheduled_datetime', 'id'))


def _leave_to_decide(employee):
    from hr_agent.models import LeaveRequest
    return (LeaveRequest.objects.filter(employee__company_id=employee.company_id, approver=employee,
                                        status='pending')
            .select_related('employee').order_by('start_date', 'id'))


MEETING_AGENTS = {'pm': 'Project Manager', 'hr': 'HR', 'frontline': 'Frontline'}
MEETING_SCREENS = {'pm': '/project-manager/dashboard?tab=meeting-scheduler', 'hr': '/hr/dashboard?tab=meetings',
                   'frontline': '/frontline/dashboard'}


def _meetings_they_organise(employee, ids):
    """[(source key, meeting)] of upcoming meetings they organise, soonest first."""
    now = timezone.now()
    out = []
    cu = dashboard_login(employee)
    if cu is not None:
        from project_manager_agent.models import ScheduledMeeting
        out += [('pm', m) for m in ScheduledMeeting.objects.filter(organizer=cu, proposed_time__gte=now)
                .exclude(status__in=('rejected', 'withdrawn')).order_by('proposed_time')[:LIST_LIMIT]]
    from hr_agent.models import HRMeeting
    out += [('hr', m) for m in HRMeeting.objects.filter(organizer=employee, scheduled_at__gte=now)
            .exclude(status__in=('cancelled', 'completed')).order_by('scheduled_at')[:LIST_LIMIT]]
    if ids:
        from Frontline_agent.models import FrontlineMeeting
        out += [('frontline', m) for m in FrontlineMeeting.objects
                .filter(organizer_id__in=ids, scheduled_at__gte=now, status__in=('scheduled', 'rescheduled'))
                .order_by('scheduled_at')[:LIST_LIMIT]]
    return sorted(out, key=lambda pair: _meeting_start(*pair))


def _meeting_start(key, m):
    return m.proposed_time if key == 'pm' else m.scheduled_at


def _projects_they_lead(company_id, ids):
    from core.models import Project
    return (Project.objects.filter(project_manager_id__in=ids, company_id=company_id)
            .exclude(status__in=('completed', 'cancelled')).order_by('name'))


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


def _colleagues(employee):
    from hr_agent.models import Employee
    return (Employee.objects.filter(company_id=employee.company_id)
            .exclude(pk=employee.pk).exclude(employment_status__in=('offboarded', 'candidate')))


def _managers(employee):
    return [{'id': e.id, 'name': e.full_name} for e in _colleagues(employee).order_by('full_name')[:500]]


def _approvers(employee):
    """Colleagues who can decide leave: HR's decision endpoint is for
    dashboard logins, found by their HR record's link or its work email."""
    from core.models import CompanyUser
    emails = [e.lower() for e in CompanyUser.objects.filter(company_id=employee.company_id, is_active=True)
              .values_list('email', flat=True) if e]
    return (_colleagues(employee).annotate(email_lower=Lower('work_email'))
            .filter(Q(company_user__is_active=True) | Q(email_lower__in=emails)))


def hr_record(company_user):
    """The HR record of a dashboard login — the lookup HR's own checks use."""
    from hr_agent.models import Employee
    company_id = company_user.company_id
    return (Employee.objects.filter(company_id=company_id, company_user=company_user).first()
            or (Employee.objects.filter(company_id=company_id, work_email__iexact=company_user.email).first()
                if company_user.email else None))


# ---------------------------------------------------------------------------
# The form, and doing it
# ---------------------------------------------------------------------------

def summary(employee) -> dict:
    """What the hand-over form shows."""
    ids = login_ids(employee)
    cu = dashboard_login(employee)
    company_id = employee.company_id

    from hr_agent.alerts import leave_summary
    tasks = _tasks(company_id, ids) if ids else None
    projects = _projects_they_lead(company_id, ids) if ids else None
    meetings = _meetings_they_organise(employee, ids)
    tickets = _tickets(company_id, ids) if ids else None
    reports = _reports(employee)
    leave = _leave_to_decide(employee)
    interviews_run = _interviews_run(cu)
    interviews = _interviews(company_id, ids) if ids else None
    logins = _dashboard_logins(company_id, cu.id if cu else None)

    def group(key, label, rows, item, targets, hint=''):
        if rows is None:
            rows = []
        count = len(rows) if isinstance(rows, list) else rows.count()
        return {'key': key, 'label': label, 'count': count,
                'items': [item(r) for r in rows[:LIST_LIMIT]], 'targets': targets, 'hint': hint}

    def interview(i):
        return {'id': i.id, 'title': f'{i.candidate_name} — {i.job_role}',
                'when': i.scheduled_datetime.isoformat() if i.scheduled_datetime else None,
                'detail': '' if i.scheduled_datetime else 'Not booked yet'}

    groups = [
        group('tasks', 'Open project tasks', tasks,
              lambda t: {'id': t.id, 'title': t.title, 'detail': t.project.name if t.project_id else '',
                         'due': t.due_date.date().isoformat() if t.due_date else None},
              _people(company_id, ids)),
        group('projects', 'Projects they lead', projects,
              lambda p: {'id': p.id, 'title': p.name, 'detail': p.get_status_display()},
              _people(company_id, ids), hint='The new project manager.'),
        group('meetings', 'Upcoming meetings they organise', meetings,
              lambda pair: {'id': f'{pair[0]}:{pair[1].pk}', 'title': f'{MEETING_AGENTS[pair[0]]}: {pair[1].title}',
                            'when': _meeting_start(*pair).isoformat()},
              logins, hint='The new organiser. A meeting is skipped if they are busy then; '
                           'an HR meeting also needs them to have an HR record.'),
        group('tickets', 'Open support tickets', tickets,
              lambda t: {'id': t.id, 'title': f'#{t.id} {t.title}', 'detail': t.get_status_display()},
              logins),
        group('reports', 'People who report to them', reports,
              lambda e: {'id': e.id, 'title': e.full_name, 'detail': e.job_title},
              _managers(employee), hint='Their new manager.'),
        group('leave', 'Leave requests waiting for their decision', leave,
              lambda lr: {'id': lr.id, 'title': lr.employee.full_name, 'detail': leave_summary(lr)},
              [{'id': e.id, 'name': e.full_name} for e in _approvers(employee).order_by('full_name')[:500]],
              hint='The new approver. Only colleagues with a dashboard login can decide leave.'),
        group('interviews_run', 'Interviews they run', interviews_run, interview, logins,
              hint='The new recruiter. A booked interview is skipped if they are busy then.'),
        group('interviews', 'Interviews they sit in on', interviews, interview,
              _people(company_id, ids),
              hint='Takes their seat. Anyone busy at a booked interview is skipped.'),
    ]
    return {
        'employee': {'id': employee.id, 'full_name': employee.full_name,
                     'employment_status': employee.employment_status},
        'groups': [g for g in groups if g['count']],
    }


def hand_over(employee, assignments: dict, actor) -> dict:
    """Move each group in `assignments` ({group key: target id}) to its target.

    Returns {group: {'moved': n, 'to': name, 'skipped': [reasons]}}. Raises
    ValueError for a target that isn't allowed, before anything moves.
    """
    from core.models import CompanyUser
    from core.tenancy import members_of

    ids = login_ids(employee)
    company = employee.company
    cu = dashboard_login(employee)
    members = members_of(company)
    plan = {}
    for key, target_id in (assignments or {}).items():
        if target_id in (None, ''):
            continue
        if key in ('tasks', 'projects', 'interviews'):
            target = members.filter(pk=target_id).exclude(pk__in=ids).first()
        elif key in ('tickets', 'meetings', 'interviews_run'):
            target = (CompanyUser.objects.filter(company=company, pk=target_id, is_active=True)
                      .exclude(pk=cu.pk if cu else None).first())
        elif key == 'reports':
            target = _colleagues(employee).filter(pk=target_id).first()
        elif key == 'leave':
            target = _approvers(employee).filter(pk=target_id).first()
        else:
            raise ValueError(f'Unknown group: {key}')
        if target is None:
            raise ValueError(f'Choose someone in your company for {key}.')
        plan[key] = target

    movers = {
        'tasks': lambda t: _move_tasks(company.id, ids, t, actor),
        'projects': lambda t: _move_projects(company.id, ids, t, actor),
        'meetings': lambda t: _move_meetings(employee, ids, t),
        'tickets': lambda t: _move_tickets(company.id, ids, t, actor),
        'reports': lambda t: _move_reports(employee, t),
        'leave': lambda t: _move_leave(employee, t),
        'interviews_run': lambda t: _move_interviews_run(cu, ids, t),
        'interviews': lambda t: _move_interview_seats(company.id, ids, t),
    }
    results = {}
    with transaction.atomic():
        for key, move in movers.items():
            if key in plan:
                results[key] = move(plan[key])
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
            skipped.append(f'{interview.candidate_name}: {_why(clash, stored_zone(interview), _name(target))}')
    return {'moved': moved, 'to': _name(target), 'skipped': skipped}


def _move_projects(company_id, ids, target, actor):
    """Through PM's own rules and audit log, like tasks."""
    from project_manager_agent import services as pm_services
    from project_manager_agent.services.actor import DashboardActor
    from project_manager_agent.services.errors import ServiceError
    pm_actor = DashboardActor(actor)
    moved, skipped = 0, []
    for project in list(_projects_they_lead(company_id, ids)):
        try:
            pm_services.update_project(pm_actor, project.id, {'project_manager_id': target.id})
            moved += 1
        except ServiceError as exc:
            skipped.append(f'{project.name}: {exc}')
    return {'moved': moved, 'to': _name(target), 'skipped': skipped}


def _move_leave(employee, approver):
    # .update(): the requests stay pending, so nothing that reacts to a
    # decision (workflows, the calendar) has anything to do.
    from hr_agent.models import LeaveRequest
    moved = LeaveRequest.objects.filter(pk__in=list(_leave_to_decide(employee).values_list('pk', flat=True))) \
        .update(approver=approver, updated_at=timezone.now())
    return {'moved': moved, 'to': approver.full_name, 'skipped': []}


def _calendar_ids(company_id, user_ids):
    """The employee logins among `user_ids` — the people the shared calendar
    has blocks for. A dashboard login without one has no calendar to check."""
    from core.scheduling.identity import member_ids
    return sorted(member_ids(company_id, user_ids))


def _move_interviews_run(cu, ids, target_cu):
    from core.scheduling import ScheduleConflict, booking_guard, ensure_free
    from core.scheduling.identity import login_user_id_for_company_user
    from recruitment_agent.interview_time import stored_zone
    from api.views.frontline_agent import _get_or_create_user_for_company_user
    people = _calendar_ids(target_cu.company_id, [login_user_id_for_company_user(target_cu)])
    login = _get_or_create_user_for_company_user(target_cu)
    moved, skipped = 0, []
    for interview in list(_interviews_run(cu)):
        booked = interview.scheduled_datetime is not None and interview.status in ('SCHEDULED', 'RESCHEDULED')
        try:
            with booking_guard(people):
                if booked and people:
                    ensure_free(people, interview.scheduled_datetime, interview.duration_minutes,
                                tz_name=stored_zone(interview), viewer_source='recruitment',
                                exclude=[('recruitment', interview.id)], suggest=False)
                interview.company_user = target_cu
                fields = ['company_user', 'updated_at']
                if interview.recruiter_id in ids:     # older interviews also name the recruiter's user
                    interview.recruiter = login
                    fields.append('recruiter')
                interview.save(update_fields=fields)
            moved += 1
        except ScheduleConflict as clash:
            skipped.append(f'{interview.candidate_name}: {_why(clash, stored_zone(interview), target_cu.full_name)}')
    return {'moved': moved, 'to': target_cu.full_name or target_cu.email, 'skipped': skipped}


def _move_meetings(employee, ids, target_cu):
    """Make `target_cu` the organiser, in each agent's own terms: PM organisers
    are dashboard logins, HR organisers HR records, Frontline organisers users."""
    from core.scheduling import ScheduleConflict, booking_guard, ensure_free
    from core.scheduling.identity import login_user_id_for_company_user
    from api.views.frontline_agent import _get_or_create_user_for_company_user
    record = hr_record(target_cu)
    frontline_login = _get_or_create_user_for_company_user(target_cu)
    organiser = {'pm': target_cu, 'hr': record, 'frontline': frontline_login}
    people = _calendar_ids(target_cu.company_id, [login_user_id_for_company_user(target_cu),
                                                  record.user_id if record else None, frontline_login.id])
    name = target_cu.full_name or target_cu.email
    moved, skipped, agents = 0, [], []
    for key, meeting in _meetings_they_organise(employee, ids):
        if organiser[key] is None:
            skipped.append(f'{meeting.title}: {name} has no HR record, so cannot organise HR meetings')
            continue
        zone = meeting.timezone_name or 'UTC'
        try:
            with booking_guard(people):
                if people:
                    ensure_free(people, _meeting_start(key, meeting), meeting.duration_minutes, tz_name=zone,
                                viewer_source=key, exclude=[(key, meeting.pk)], suggest=False)
                meeting.organizer = organiser[key]
                meeting.save(update_fields=['organizer', 'updated_at'])
            moved += 1
            if key not in agents:
                agents.append(key)
        except ScheduleConflict as clash:
            skipped.append(f'{meeting.title}: {_why(clash, zone, name)}')
    return {'moved': moved, 'to': name, 'skipped': skipped, 'agents': agents}


def _why(clash, zone, name):
    return clash.clashes[0].describe(zone) if clash.clashes else f'{name} is busy then'


def _tell_recipients(employee, plan, results):
    """One bell alert per recipient per group."""
    from core.models import CompanyUser
    links = {'tasks': '/project-manager/dashboard?tab=tasks', 'projects': '/project-manager/dashboard?tab=projects',
             'tickets': '/frontline/dashboard?tab=tickets',
             'reports': '/hr/dashboard?tab=my_team', 'leave': '/hr/dashboard?tab=leave',
             'interviews_run': '/recruitment/interviews', 'interviews': '/recruitment/interviews'}
    titles = {'tasks': ('task handed over to you', 'tasks handed over to you'),
              'projects': ('project for you to lead', 'projects for you to lead'),
              'meetings': ('meeting for you to organise', 'meetings for you to organise'),
              'reports': ('person now reports to you', 'people now report to you'),
              'leave': ('leave request for you to decide', 'leave requests for you to decide'),
              'interviews_run': ('interview for you to run', 'interviews for you to run'),
              'interviews': ('interview handed over to you', 'interviews handed over to you')}
    for key, target in plan.items():
        moved = results.get(key, {}).get('moved', 0)
        if not moved or key == 'tickets':          # tickets alert their new owner already
            continue
        if isinstance(target, CompanyUser):
            recipient = target
        elif hasattr(target, 'work_email'):        # an HR record
            recipient = target.company_user if target.company_user_id else (
                CompanyUser.objects.filter(company_id=employee.company_id, email__iexact=target.work_email,
                                           is_active=True).first())
        else:
            recipient = company_user_for_login(target, employee.company_id)
        link = (MEETING_SCREENS[results[key]['agents'][0]] if key == 'meetings' else links[key])
        if recipient is not None:
            notify_company_users([recipient], title=f'{moved} {titles[key][moved != 1]}',
                                 message=f'From {employee.full_name}, who is leaving.',
                                 link=link, kind=f'handover_{key}')

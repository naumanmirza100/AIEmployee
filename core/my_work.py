"""Everything a person has to do, across the agents, in one list.

A person's work used to be spread over the agents: PM tasks in My Space, leave
waiting for a decision in HR, tickets in Frontline, feedback owed on
interviews in Recruitment, and suggested meeting times in each scheduler.
Nothing showed it together. This gathers it into one list sorted by when it is
due; each item says which agent it comes from and links to the screen in that
agent where it gets done.

There are two kinds of login, and each sees only what it can open and act on:

  * a dashboard login (`CompanyUser`): tickets assigned to it; customers
    waiting for a person and questions the assistant could not answer, for the
    logins who are alerted about them; leave requests
    and HR workflows waiting for its decision; new times suggested for
    meetings it organises; interviews it ran that still need feedback; and PM
    tasks assigned to the employee login it maps to.
  * an employee login (`auth.User`, the My Space pages): its PM tasks, and
    meeting invites waiting for its reply.

An agent the company hasn't bought adds nothing to a dashboard login's list.
One agent failing doesn't hide the others'.

API: `company/my-work` (dashboard logins) and `user/my-work` (employee logins).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone as dt_timezone

from django.db.models import F, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

AGENT_LABELS = {'pm': 'Project Manager', 'hr': 'HR', 'frontline': 'Frontline', 'recruitment': 'Recruitment'}
#: Most items one source adds, so a large backlog can't make the list unbounded.
LIMIT = 100
OPEN_TICKET_STATUSES = ('new', 'open', 'in_progress')
#: The system account the public chat widget files tickets under
#: (api.views.frontline_agent._ensure_handoff_system_user).
WIDGET_ACCOUNT = 'frontline_handoff_bot'
#: Interviews older than this aren't chased for feedback any more.
FEEDBACK_WINDOW = timedelta(days=60)


@dataclass
class Person:
    company: object
    company_user: object = None
    #: The auth.User ids this person acts as: a dashboard login's own user and
    #: the employee login it maps to, or an employee login itself.
    user_ids: set = field(default_factory=set)
    #: Their HR record, if they have one.
    employee: object = None
    hr_admin: bool = False

    @classmethod
    def from_company_user(cls, company_user):
        from core.scheduling.identity import login_user_id_for_company_user
        company = company_user.company
        user_ids = {company_user.login_user_id, login_user_id_for_company_user(company_user)} - {None}
        employee, hr_admin = None, False
        try:
            from hr_agent.alerts import HR_ADMIN_ROLES
            from hr_agent.models import Employee
            # The same lookup HR's leave decision uses to find "the approver".
            employee = Employee.objects.filter(company=company, company_user=company_user).first()
            if employee is None and company_user.email:
                employee = Employee.objects.filter(company=company,
                                                   work_email__iexact=company_user.email).first()
            hr_admin = (company_user.role or '').lower() in HR_ADMIN_ROLES
        except ImportError:  # pragma: no cover — HR app not installed
            pass
        return cls(company=company, company_user=company_user, user_ids=user_ids,
                   employee=employee, hr_admin=hr_admin)

    @classmethod
    def from_user(cls, user):
        from core.tenancy import company_of_user
        company = company_of_user(user)
        employee = None
        try:
            from hr_agent.models import Employee
            employee = Employee.objects.filter(user=user, company=company).first() if company else None
        except ImportError:  # pragma: no cover
            pass
        return cls(company=company, user_ids={user.id}, employee=employee)


def for_company_user(company_user, now=None):
    if company_user is None or company_user.company_id is None:
        return []
    person = Person.from_company_user(company_user)
    modules = _active_modules(person.company)
    sources = []
    if 'frontline_agent' in modules:
        sources += [_tickets, _handoffs_waiting, _unanswered_questions]
    if 'hr_agent' in modules:
        sources += [_leave_to_decide, _workflows_to_approve, _hr_times_suggested]
    if 'recruitment_agent' in modules:
        sources.append(_interview_feedback)
    if 'project_manager_agent' in modules:
        sources += [_pm_times_suggested, _dashboard_tasks]
    return _gather(sources, person, now)


def for_user(user, now=None):
    if user is None or not user.is_authenticated:
        return []
    person = Person.from_user(user)
    return _gather([_my_tasks, _pm_invites, _hr_invites], person, now)


# ---------------------------------------------------------------------------

def _gather(sources, person, now):
    now = now or timezone.now()
    items = []
    for source in sources:
        try:
            items += source(person, now)
        except Exception:
            logger.exception('my_work: %s failed', getattr(source, '__name__', source))
    items.sort(key=_sort_key)
    for item in items:
        del item['_due']
    return items


def _sort_key(item):
    due = item['_due']
    if due is None:
        return (1, datetime.max.replace(tzinfo=dt_timezone.utc))
    if not isinstance(due, datetime):
        # A date is due by the end of that day.
        due = datetime.combine(due, time(23, 59), tzinfo=dt_timezone.utc)
    return (0, due)


def _item(agent, kind, key, title, *, detail='', due=None, action='Open', link=''):
    all_day = isinstance(due, date) and not isinstance(due, datetime)
    return {
        'key': f'{kind}:{key}', 'agent': agent, 'agent_label': AGENT_LABELS[agent], 'kind': kind,
        'title': title, 'detail': detail,
        'due': due.isoformat() if due else None, 'all_day': all_day,
        'action': action, 'link': link, '_due': due,
    }


def _active_modules(company):
    from core.models import CompanyModulePurchase
    return {p.module_name for p in CompanyModulePurchase.objects.filter(company=company) if p.is_active()}


def _name(user):
    return (user.get_full_name() or user.username).strip() if user else ''


def _day(moment):
    """'1 Oct' — strftime has no portable unpadded day."""
    moment = timezone.localtime(moment)
    return f'{moment.day} {moment:%b}'


# ---- Frontline ----------------------------------------------------------------

def _tickets(person, now):
    from Frontline_agent.models import Ticket
    login_id = person.company_user.login_user_id
    if not login_id:
        return []
    tickets = (Ticket.objects
               .filter(company=person.company, assigned_to_id=login_id, status__in=OPEN_TICKET_STATUSES)
               .filter(Q(snoozed_until__isnull=True) | Q(snoozed_until__lte=now))
               .select_related('contact')
               .order_by(F('sla_due_at').asc(nulls_last=True), '-created_at')[:LIMIT])
    items = []
    for t in tickets:
        due = None if t.sla_paused_at else t.sla_due_at
        if t.category == 'knowledge_gap':
            items.append(_item('frontline', 'knowledge_gap', t.id, f'Add an answer: {t.title}',
                               detail="The assistant couldn't answer this. Add a document that covers it.",
                               due=due, action='Add to knowledge base', link='/company/dashboard/ticket-tasks'))
            continue
        parts = [f'{t.get_priority_display()} priority']
        if t.contact_id:
            parts.append(t.contact.name or t.contact.email)
        if t.sla_paused_at:
            parts.append('SLA paused')
        items.append(_item('frontline', 'ticket', t.id, f'Ticket #{t.id}: {t.title}', detail=' · '.join(parts),
                           due=due, action='Open ticket', link='/frontline/dashboard?tab=tickets'))
    return items


def _hears_handoffs(person) -> bool:
    from Frontline_agent.alerts import HANDOFF_ALERT_ROLES
    return (person.company_user.role or '').lower() in HANDOFF_ALERT_ROLES


def _handoffs_waiting(person, now):
    """A customer who asked for a person, for every login that is alerted
    about hand-offs, until one of them takes it.

    The chat widget files these under a system account, so they were on
    nobody's list: one bell alert, then nothing unless someone opened the
    Hand-offs tab. One a signed-in agent raised on their own ticket is already
    in their list as that ticket.
    """
    from Frontline_agent.alerts import HANDOFF_WHY
    from Frontline_agent.models import Ticket
    if not _hears_handoffs(person):
        return []
    tickets = (Ticket.objects
               .filter(company=person.company, handoff_status='pending')
               .exclude(status__in=('resolved', 'closed'))
               .select_related('contact')
               .order_by('handoff_requested_at')[:LIMIT])
    login_id = person.company_user.login_user_id
    items = []
    for t in tickets:
        if login_id and t.assigned_to_id == login_id and t.status in OPEN_TICKET_STATUSES:
            continue
        parts = [HANDOFF_WHY.get(t.handoff_reason, '').rstrip('.')]
        if t.contact_id:
            parts.append(t.contact.name or t.contact.email)
        if t.handoff_requested_at:
            parts.append(f'waiting since {_day(t.handoff_requested_at)}, '
                         f'{timezone.localtime(t.handoff_requested_at):%H:%M}')
        items.append(_item('frontline', 'handoff', t.id, f'Customer waiting for a person: {t.title}',
                           detail=' · '.join(p for p in parts if p),
                           # No response time set: they are waiting from the moment they asked.
                           due=t.sla_due_at or t.handoff_requested_at,
                           action='Take it', link='/frontline/dashboard?tab=handoffs'))
    return items


def _unanswered_questions(person, now):
    """Questions the website assistant could not answer, as one line.

    The widget files one ticket per question under the system account. Listed
    singly, public traffic would swamp the page; unlisted, as before, nobody
    was ever asked to fill the gaps.
    """
    from Frontline_agent.models import Ticket
    if not _hears_handoffs(person):
        return []
    gaps = (Ticket.objects
            .filter(company=person.company, category='knowledge_gap', status__in=OPEN_TICKET_STATUSES)
            .filter(Q(assigned_to__isnull=True) | Q(assigned_to__username=WIDGET_ACCOUNT)))
    count = gaps.count()
    if not count:
        return []
    latest = gaps.order_by('-created_at', '-id').values_list('title', flat=True).first() or ''
    return [_item('frontline', 'knowledge_gaps', person.company.id,
                  f"{count} question{'' if count == 1 else 's'} the assistant couldn't answer",
                  detail=f'Latest: {latest}'[:200],
                  action='Review', link='/frontline/dashboard?tab=tickets')]


# ---- HR -------------------------------------------------------------------------

def _leave_to_decide(person, now):
    """Requests this login is the named approver of — HR's "Pending for me" —
    and, for HR admins, requests nobody was named to approve. (HR admins may
    decide any request, but one with an approver is that person's to decide.)"""
    from hr_agent.alerts import leave_summary
    from hr_agent.models import LeaveRequest
    mine = Q(approver=person.employee) if person.employee is not None else Q(pk__in=[])
    if person.hr_admin:
        mine |= Q(approver__isnull=True)
    requests = LeaveRequest.objects.filter(mine, employee__company=person.company, status='pending')
    if person.employee is not None:
        requests = requests.exclude(employee=person.employee)
    return [
        _item('hr', 'leave', lr.id, f'Leave request from {lr.employee.full_name}', detail=leave_summary(lr),
              due=lr.start_date, action='Decide',
              # Unassigned requests aren't under "Pending for me"; open HR's full list.
              link='/hr/dashboard?tab=leave' + ('' if lr.approver_id else '&view=all'))
        for lr in requests.select_related('employee').order_by('start_date')[:LIMIT]
    ]


def _workflows_to_approve(person, now):
    if not person.hr_admin:
        return []
    from hr_agent.models import HRWorkflowExecution
    runs = (HRWorkflowExecution.objects
            .filter(workflow__company=person.company, status='awaiting_approval')
            .select_related('workflow').order_by('started_at')[:LIMIT])
    items = []
    for run in runs:
        who = (run.context_data or {}).get('employee_name')
        since = f'Waiting since {_day(run.started_at)}.' if run.started_at else ''
        items.append(_item('hr', 'workflow', run.id,
                           f'Approve workflow: {run.workflow_name or run.workflow.name}',
                           detail=' '.join(p for p in (f'For {who}.' if who else '', since) if p),
                           action='Approve or reject', link='/hr/dashboard?tab=workflows'))
    return items


def _hr_times_suggested(person, now):
    """Meetings this login organises where an invitee suggested another time
    and it's the organiser's turn. With no organiser set, HR admins answer."""
    from hr_agent.models import HRMeeting
    if person.employee is not None:
        mine = Q(organizer=person.employee)
        if person.hr_admin:
            mine |= Q(organizer__isnull=True)
    elif person.hr_admin:
        mine = Q(organizer__isnull=True)
    else:
        return []
    meetings = (HRMeeting.objects
                .filter(mine, company=person.company, response_status='counter_proposed')
                .exclude(status__in=('cancelled', 'completed'))
                .prefetch_related('responses').order_by('scheduled_at')[:LIMIT * 2])
    items = []
    for m in meetings:
        last = max(m.responses.all(), key=lambda r: (r.created_at, r.id), default=None)
        if not last or last.responded_by != 'participant' or last.action != 'counter_proposed':
            continue
        suggested = last.proposed_time or m.scheduled_at
        if suggested and suggested < now:
            continue
        items.append(_item('hr', 'meeting_reply', m.id,
                           f'{last.responder_name or "An invitee"} suggested another time',
                           detail=m.title, due=suggested, action='Reply', link='/hr/dashboard?tab=meetings'))
    return items[:LIMIT]


# ---- Recruitment --------------------------------------------------------------

def _interview_feedback(person, now):
    """Interviews this login ran that are over, with no feedback and no
    decision yet."""
    from recruitment_agent.models import Interview
    interviews = (Interview.objects
                  .filter(company_user=person.company_user, status__in=('SCHEDULED', 'RESCHEDULED', 'COMPLETED'),
                          scheduled_datetime__lt=now, scheduled_datetime__gte=now - FEEDBACK_WINDOW,
                          feedback_submitted_at__isnull=True)
                  .filter(Q(outcome__isnull=True) | Q(outcome=''))
                  .order_by('scheduled_datetime')[:LIMIT])
    items = []
    for iv in interviews:
        ended = iv.scheduled_datetime + timedelta(minutes=iv.duration_minutes or 30)
        if ended > now:
            continue
        items.append(_item('recruitment', 'feedback', iv.id, f'Feedback on {iv.candidate_name}',
                           detail=f'{iv.job_role} interview, {_day(iv.scheduled_datetime)}',
                           due=ended + timedelta(days=1), action='Give feedback', link='/recruitment/interviews'))
    return items


# ---- Project Manager ----------------------------------------------------------

def _pm_times_suggested(person, now):
    """As `_hr_times_suggested`, for meetings scheduled in Project Manager."""
    from project_manager_agent.models import ScheduledMeeting
    meetings = (ScheduledMeeting.objects
                .filter(organizer=person.company_user)
                .exclude(status='withdrawn')
                .filter(Q(proposed_time__gte=now) | Q(responses__proposed_time__gte=now))
                .distinct()
                .select_related('invitee')
                .prefetch_related('responses', 'participants__user')
                .order_by('proposed_time')[:LIMIT * 2])
    items = []
    for m in meetings:
        last = max(m.responses.all(), key=lambda r: (r.created_at, r.id), default=None)
        if not last or last.responded_by != 'invitee' or last.action != 'counter_proposed':
            continue
        suggested = last.proposed_time or m.proposed_time
        if suggested and suggested < now:
            continue
        who = [_name(p.user) for p in m.participants.all() if p.status == 'counter_proposed']
        who = ', '.join(who) or _name(m.invitee) or 'An invitee'
        items.append(_item('pm', 'meeting_reply', m.id, f'{who} suggested another time', detail=m.title,
                           due=suggested, action='Reply',
                           link='/project-manager/dashboard?tab=meeting-scheduler'))
    return items[:LIMIT]


def _task_items(tasks, link):
    return [
        _item('pm', 'task', t.id, t.title,
              detail=' · '.join(p for p in (t.project.name if t.project_id else '', t.get_status_display()) if p),
              due=t.due_date, action='Open task', link=link)
        for t in tasks
    ]


def _open_tasks(qs):
    return (qs.exclude(status='done').select_related('project')
            .order_by(F('due_date').asc(nulls_last=True), '-priority')[:LIMIT])


def _dashboard_tasks(person, now):
    from core.tenancy import tasks_for_company_user
    if not person.user_ids:
        return []
    tasks = _open_tasks(tasks_for_company_user(person.company_user).filter(assignee_id__in=person.user_ids))
    return _task_items(tasks, '/project-manager/dashboard?tab=tasks')


# ---- Employee login -------------------------------------------------------------

def _my_tasks(person, now):
    from core.models import Task
    return _task_items(_open_tasks(Task.objects.filter(assignee_id__in=person.user_ids)), '/me/tasks')


def _pm_invites(person, now):
    from project_manager_agent.models import MeetingParticipant
    rows = (MeetingParticipant.objects
            .filter(user_id__in=person.user_ids, status='pending', meeting__proposed_time__gte=now)
            .exclude(meeting__status='withdrawn')
            .select_related('meeting__organizer').order_by('meeting__proposed_time')[:LIMIT])
    return [
        _item('pm', 'invite', row.meeting_id, f'Meeting invite: {row.meeting.title}',
              detail=f'From {row.meeting.organizer.full_name}' if row.meeting.organizer_id else '',
              due=row.meeting.proposed_time, action='Reply', link='/me/meetings')
        for row in rows
    ]


def _hr_invites(person, now):
    if person.employee is None:
        return []
    from hr_agent.models import HRMeetingParticipant
    rows = (HRMeetingParticipant.objects
            .filter(employee=person.employee, status='pending', meeting__scheduled_at__gte=now)
            .exclude(meeting__status__in=('cancelled', 'completed'))
            .exclude(meeting__response_status='withdrawn')
            .select_related('meeting__organizer').order_by('meeting__scheduled_at')[:LIMIT])
    return [
        _item('hr', 'invite', row.meeting_id, f'Meeting invite: {row.meeting.title}',
              detail=f'From {row.meeting.organizer.full_name}' if row.meeting.organizer_id else 'From HR',
              due=row.meeting.scheduled_at, action='Reply', link='/me/meetings')
        for row in rows
    ]

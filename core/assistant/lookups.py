"""The Company Assistant's lookups: small read-only questions to one agent's data each.

The AI never touches the database. It picks lookups from this list and fills in their arguments (names, dates);
these functions run them for the asking login, in its own company, under the same rule the agent's own screens use
for who may see what. Each returns facts: a line of plain text the answer is written from, the agent it came from,
and the screen that shows it.

Version 1 (2 Nov 2026) covers people, the shared calendar, Project Manager, HR and Frontline.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.db.models import Count, F, Q
from django.utils import timezone

#: Most rows one lookup lists; the totals are always given in full.
ROWS = 25
OPEN_TASK = ('todo', 'in_progress', 'review', 'blocked')
OPEN_TICKET = ('new', 'open', 'in_progress')

LABELS = {'people': 'People', 'calendar': 'Calendar', 'project_manager_agent': 'Project Manager',
          'hr_agent': 'HR', 'frontline_agent': 'Frontline', 'recruitment_agent': 'Recruitment',
          'exec_meeting_agent': 'Executive Meeting', 'operations_agent': 'Operations', 'marketing_agent': 'Marketing',
          'ai_sdr_agent': 'AI SDR', 'reply_draft_agent': 'Reply Draft', 'crm_sync_agent': 'CRM Sync',
          'documents': 'Documents', 'week': 'This week'}
CALENDAR_LINKS = {
    'pm': ('Project Manager meetings', '/project-manager/dashboard?tab=meetings'),
    'hr': ('HR meetings', '/hr/dashboard?tab=meetings'),
    'frontline': ('Frontline customer calls', '/frontline/dashboard?tab=meetings'),
    'recruitment': ('Recruitment interviews', '/recruitment/interviews'),
    'leave': ('HR leave', '/hr/dashboard?tab=leave'),
    'sdr': ('AI SDR sales calls', '/ai-sdr/meetings'),
    'exec': ('Executive meetings', '/exec-meeting/dashboard?tab=meetings'),
    'holiday': ('HR holidays', '/hr/dashboard?tab=leave'),
}


class Refused(Exception):
    """The lookup can't be answered for this login or these arguments; the message says why, plainly."""


@dataclass
class Fact:
    text: str
    source: str
    link: str = ''

    def as_dict(self):
        return {'text': self.text, 'source': self.source, 'link': self.link}


@dataclass
class Lookup:
    name: str
    module: str          # the agent it needs ('people' and 'calendar' are shared)
    about: str
    args: dict
    run: object


# ---- helpers ---------------------------------------------------------------------------------------------------

def _day(value) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        raise Refused(f'"{value}" is not a date I can read.')


def _range(ctx, args, *, default_days=7):
    start = _day(args['start']) if args.get('start') else ctx.today
    end = _day(args['end']) if args.get('end') else start + timedelta(days=default_days - 1)
    if end < start:
        start, end = end, start
    if (end - start).days > 92:
        raise Refused('That is more than three months; ask about a shorter time.')
    return start, end


def _clock(value, default) -> time:
    if not value:
        return default
    try:
        h, _, m = str(value).strip().partition(':')
        return time(int(h), int(m or 0))
    except ValueError:
        raise Refused(f'"{value}" is not a time I can read.')


def _when(ctx, moment) -> str:
    """'Wed 5 Nov, 15:00' in the company's zone."""
    local = moment.astimezone(ctx.zone)
    return f'{local:%a} {local.day} {local:%b}, {local:%H:%M}'


def _date(d) -> str:
    return f'{d:%a} {d.day} {d:%b} {d.year}'


def _one(ctx, name):
    """The person `name` means, or Refused: none found, or more than one (the engine asks back)."""
    if not str(name or '').strip():
        raise Refused('Say whose.')
    found = ctx.directory.find(name, asker=ctx.company_user)
    if not found:
        raise Refused(f'Nobody called "{name}" was found in this company.')
    if len(found) > 1:
        raise Ambiguous(name, found)
    return found[0]


class Ambiguous(Refused):
    def __init__(self, name, people):
        self.name, self.people = name, people
        super().__init__(f'"{name}" could be: ' + '; '.join(p.describe() for p in people[:6]))


# ---- people ----------------------------------------------------------------------------------------------------

def person(ctx, args):
    p = _one(ctx, args.get('person'))
    bits = [f'{k.replace("_", " ")}: {v}' for k, v in p.facts().items() if k != 'name']
    link = '/hr/dashboard?tab=employees' if p.employee is not None and 'hr_agent' in ctx.modules else ''
    return [Fact(f'{p.name}' + (f' — {"; ".join(bits)}' if bits else ''), 'People', link)]


def people(ctx, args):
    dept = str(args.get('department') or '').strip().lower()
    rows = [p for p in ctx.directory.people if not dept or dept in (p.department or '').lower()]
    facts = [Fact(f'{len(rows)} people' + (f' in "{args.get("department")}"' if dept else ' in the company'), 'People')]
    for p in sorted(rows, key=lambda x: x.name.lower())[:ROWS * 2]:
        facts.append(Fact(p.describe(), 'People'))
    return facts


# ---- the shared calendar ---------------------------------------------------------------------------------------

def _window(ctx, args, start_day, end_day):
    begins = datetime.combine(start_day, _clock(args.get('from_time'), time(0)), tzinfo=ctx.zone)
    if args.get('to_time'):
        ends = datetime.combine(end_day, _clock(args.get('to_time'), time(23, 59)), tzinfo=ctx.zone)
    else:
        ends = datetime.combine(end_day + timedelta(days=1), time(0), tzinfo=ctx.zone)
    return begins, ends


def calendar(ctx, args):
    from core.scheduling.conflicts import find_conflicts
    names = args.get('people') or ([args['person']] if args.get('person') else [])
    if isinstance(names, str):
        names = [names]
    if not names:
        raise Refused('Say whose calendar.')
    start, end = _range(ctx, args)
    begins, ends = _window(ctx, args, start, end)
    facts = []
    for name in names[:8]:
        p = _one(ctx, name)
        if not p.user_ids:
            facts.append(Fact(f'{p.name} has no login, so has no calendar.', 'Calendar'))
            continue
        clashes = find_conflicts(p.user_ids, begins, ends, tz_name=ctx.tz)
        span = f'{_date(start)}' + ('' if start == end else f' to {_date(end)}')
        if not clashes:
            facts.append(Fact(f'{p.name} has nothing booked {span}' +
                              (f', {args.get("from_time")}–{args.get("to_time")}' if args.get('from_time') else '') +
                              ' (no meetings, interviews, sales calls, leave or holidays).', 'Calendar'))
            continue
        # The period is the one looked at, not how long they are busy: "1 busy time(s) Mon 9 Nov to Fri 13 Nov" was
        # answered "busy the whole week" (2 Nov 2026).
        within = ('On ' if start == end else 'In the period ') + span + (
            f', {args.get("from_time")}–{args.get("to_time")}' if args.get('from_time') else '')
        more = f' The first {ROWS} follow.' if len(clashes) > ROWS else ' Each one follows.'
        facts.append(Fact(f'{within}, {p.name} has {len(clashes)} busy time(s); outside them nothing is booked.{more}',
                          'Calendar'))
        for c in clashes[:ROWS]:
            label, link = CALENDAR_LINKS.get(c.source, ('Calendar', ''))
            facts.append(Fact(c.describe(ctx.tz), label, link))
    return facts


def who_is_free(ctx, args):
    from core.scheduling.conflicts import busy_intervals, overlaps
    day = _day(args.get('date') or ctx.today)
    begins = datetime.combine(day, _clock(args.get('from_time'), time(9)), tzinfo=ctx.zone)
    ends = datetime.combine(day, _clock(args.get('to_time'), time(18)), tzinfo=ctx.zone)
    if ends <= begins:
        raise Refused('The end time must be after the start.')
    dept = str(args.get('department') or '').strip().lower()
    free, busy = [], []
    for p in ctx.directory.people:
        if not p.user_ids or (dept and dept not in (p.department or '').lower()):
            continue
        (busy if overlaps(busy_intervals(p.user_ids, begins, ends, tz_name=ctx.tz), begins, ends) else free).append(p)
    window = f'{_date(day)}, {begins:%H:%M}–{ends:%H:%M}'
    facts = [Fact(f'{window}: {len(free)} free, {len(busy)} busy (of the people with a login).', 'Calendar')]
    if free:
        facts.append(Fact('Free the whole time: ' + ', '.join(p.name for p in free[:40]), 'Calendar'))
    if busy:
        facts.append(Fact('Busy for part or all of it: ' + ', '.join(p.name for p in busy[:40]), 'Calendar'))
    return facts


# ---- Project Manager ---------------------------------------------------------------------------------------------

def _tasks_seen(ctx):
    from core.tenancy import tasks_for_company_user
    return tasks_for_company_user(ctx.company_user)


def _task_line(ctx, t):
    due = ''
    if t.due_date:
        due_day = t.due_date.astimezone(ctx.zone).date() if timezone.is_aware(t.due_date) else t.due_date.date()
        due = f', due {_date(due_day)}' + (' (late)' if due_day < ctx.today else '')
    return f'"{t.title}" in {t.project.name} — {t.get_status_display()}, {t.get_priority_display()} priority{due}'


def tasks(ctx, args):
    p = _one(ctx, args.get('person'))
    if not p.user_ids:
        return [Fact(f'{p.name} has no login, so has no Project Manager tasks.', 'Project Manager')]
    qs = (_tasks_seen(ctx).filter(assignee_id__in=p.user_ids, status__in=OPEN_TASK).select_related('project')
          .order_by(F('due_date').asc(nulls_last=True), 'id'))
    if args.get('due_by'):
        last = _day(args['due_by'])
        qs = qs.filter(due_date__lt=datetime.combine(last + timedelta(days=1), time(0), tzinfo=ctx.zone))
    rows = list(qs[:ROWS])
    total = qs.count()
    late = sum(1 for t in qs if t.due_date and t.due_date.astimezone(ctx.zone).date() < ctx.today)
    link = '/project-manager/dashboard?tab=tasks'
    head = (f'{p.name} has {total} open task(s)' + (f' due by {_date(_day(args["due_by"]))}' if args.get('due_by') else '')
            + f'; {late} late.')
    return [Fact(head, 'Project Manager', link)] + [Fact(_task_line(ctx, t), 'Project Manager', link) for t in rows]


def _project(ctx, name):
    from core.tenancy import projects_for_company_user
    query = str(name or '').strip()
    if not query:
        raise Refused('Say which project.')
    qs = projects_for_company_user(ctx.company_user)
    found = list(qs.filter(name__iexact=query)) or list(qs.filter(name__icontains=query)[:6])
    if not found:
        raise Refused(f'No project called "{query}" was found.')
    if len(found) > 1:
        raise Refused(f'"{query}" could be: ' + '; '.join(p.name for p in found))
    return found[0]


def project(ctx, args):
    pr = _project(ctx, args.get('project'))
    all_tasks = pr.tasks.all()
    counts = {row['status']: row['n'] for row in all_tasks.values('status').annotate(n=Count('id'))}
    total = sum(counts.values())
    done = counts.get('done', 0)
    open_qs = all_tasks.filter(status__in=OPEN_TASK).select_related('assignee', 'project')
    late = [t for t in open_qs if t.due_date and t.due_date.astimezone(ctx.zone).date() < ctx.today]
    deadline = pr.effective_deadline() if callable(getattr(pr, 'effective_deadline', None)) else pr.deadline
    link = '/project-manager/dashboard?tab=projects'
    facts = [Fact(f'Project "{pr.name}": {pr.get_status_display()}; {total} task(s), {done} done, '
                  f'{total - done} not done, {len(late)} late'
                  + (f'; deadline {_date(deadline)}' if deadline else '; no deadline set') + '.', 'Project Manager', link)]
    people_on = {}
    for t in open_qs:
        who = ctx.name_of_user(t.assignee_id) if t.assignee_id else 'nobody'
        people_on[who] = people_on.get(who, 0) + 1
    if people_on:
        facts.append(Fact('Open tasks by person: ' + ', '.join(f'{k} {v}' for k, v in sorted(people_on.items())),
                          'Project Manager', link))
    for t in late[:ROWS]:
        who = ctx.name_of_user(t.assignee_id) if t.assignee_id else 'nobody'
        facts.append(Fact('Late: ' + _task_line(ctx, t) + f', assigned to {who}', 'Project Manager', link))
    return facts


def projects(ctx, args):
    from core.tenancy import projects_for_company_user
    qs = (projects_for_company_user(ctx.company_user)
          .annotate(total=Count('tasks'), done=Count('tasks', filter=Q(tasks__status='done')))
          .order_by('-id'))
    rows = list(qs[:ROWS])
    link = '/project-manager/dashboard?tab=projects'
    facts = [Fact(f'{qs.count()} project(s).', 'Project Manager', link)]
    for pr in rows:
        facts.append(Fact(f'"{pr.name}": {pr.get_status_display()}, {pr.done} of {pr.total} task(s) done',
                          'Project Manager', link))
    return facts


def workload(ctx, args):
    rows = (_tasks_seen(ctx).filter(status__in=OPEN_TASK, assignee__isnull=False)
            .values('assignee_id').annotate(n=Count('id'),
                                            late=Count('id', filter=Q(due_date__lt=timezone.now())))
            .order_by('-n'))
    link = '/project-manager/dashboard?tab=tasks'
    facts = [Fact('Open Project Manager tasks per person (late in brackets):', 'Project Manager', link)]
    for row in rows[:40]:
        facts.append(Fact(f'{ctx.name_of_user(row["assignee_id"])}: {row["n"]} open ({row["late"]} late)',
                          'Project Manager', link))
    if len(facts) == 1:
        facts.append(Fact('Nobody has open tasks.', 'Project Manager', link))
    return facts


# ---- HR ----------------------------------------------------------------------------------------------------------

def _may_see_leave_of(ctx, employee) -> bool:
    """HR's own rule: HR admins see everyone's; others their own and their reports'."""
    if ctx.hr_admin:
        return True
    me = ctx.my_employee
    return bool(me and (employee.pk == me.pk or employee.manager_id == me.pk))


def leave(ctx, args):
    from hr_agent.models import LeaveRequest
    start, end = _range(ctx, args)
    qs = (LeaveRequest.objects.filter(employee__company=ctx.company, start_date__lte=end, end_date__gte=start,
                                      status__in=('approved', 'pending'))
          .select_related('employee').order_by('start_date'))
    if args.get('person'):
        p = _one(ctx, args['person'])
        if p.employee is None:
            return [Fact(f'{p.name} has no HR record, so no leave is kept for them.', 'HR')]
        qs = qs.filter(employee=p.employee)
    link = '/hr/dashboard?tab=leave'
    facts, shown = [], 0
    for lr in qs[:80]:
        detailed = _may_see_leave_of(ctx, lr.employee)
        if lr.status == 'pending' and not detailed:
            continue        # a request still waiting is between the person, their manager and HR
        days = _date(lr.start_date) + ('' if lr.end_date == lr.start_date else f' to {_date(lr.end_date)}')
        kind = f' ({lr.get_leave_type_display()}, {float(lr.days_requested):g} day(s))' if detailed else ''
        state = 'approved' if lr.status == 'approved' else 'requested, waiting for a decision'
        facts.append(Fact(f'{lr.employee.full_name}: leave {days}{kind}, {state}', 'HR', link))
        shown += 1
    span = _date(start) + ('' if start == end else f' to {_date(end)}')
    head = f'{shown} leave record(s) overlapping {span}' + ('' if ctx.hr_admin else ' (others\' requests still waiting are not shown to you)')
    return [Fact(head + '.', 'HR', link)] + facts


def leave_balance(ctx, args):
    from hr_agent.models import LeaveBalance
    p = _one(ctx, args.get('person') or 'me')
    if p.employee is None:
        return [Fact(f'{p.name} has no HR record, so no leave balance is kept.', 'HR')]
    if not _may_see_leave_of(ctx, p.employee):
        raise Refused(f"Only HR, {p.name}, or their manager can see {p.name}'s leave balance.")
    rows = LeaveBalance.objects.filter(employee=p.employee).order_by('leave_type', '-period_start')
    seen, facts = set(), []
    for b in rows:
        if b.leave_type in seen:
            continue        # the latest leave year only
        seen.add(b.leave_type)
        facts.append(Fact(f'{p.name}: {b.get_leave_type_display()} — {b.remaining:g} day(s) left '
                          f'({float(b.accrued_days) + float(b.carried_over_days):g} given, {float(b.used_days):g} used)',
                          'HR', '/hr/dashboard?tab=leave'))
    return facts or [Fact(f'No leave balance is kept for {p.name} yet.', 'HR', '/hr/dashboard?tab=leave')]


def holidays(ctx, args):
    from hr_agent.models import Holiday
    start, end = _range(ctx, args, default_days=31)
    rows = Holiday.objects.filter(company=ctx.company, date__range=(start, end), is_working_day=False).order_by('date')
    facts = [Fact(f'{h.name}: {_date(h.date)}' + (f' (region {h.region})' if h.region else ''), 'HR',
                  '/hr/dashboard?tab=leave') for h in rows[:ROWS]]
    return facts or [Fact(f'No company holidays from {_date(start)} to {_date(end)}.', 'HR')]


# ---- Frontline ---------------------------------------------------------------------------------------------------

def tickets(ctx, args):
    from api.views.frontline_agent import SYSTEM_TICKET_ACCOUNTS, _tickets_of
    from django.contrib.auth import get_user_model
    from Frontline_agent.models import Ticket
    login_id = ctx.company_user.login_user_id
    me = get_user_model().objects.filter(pk=login_id).first() if login_id else None
    if me is not None:
        qs = _tickets_of(ctx.company_user, me)
    else:   # no login user yet: only the customers' tickets nobody holds (never "created by nobody")
        qs = Ticket.objects.filter(Q(assigned_to__username__in=SYSTEM_TICKET_ACCOUNTS)
                                   | Q(assigned_to__isnull=True, created_by__username__in=SYSTEM_TICKET_ACCOUNTS),
                                   company=ctx.company)
    if (args.get('status') or 'open') == 'open':
        qs = qs.filter(status__in=OPEN_TICKET)
    if args.get('start') or args.get('end'):
        start, end = _range(ctx, args)
        qs = qs.filter(created_at__gte=datetime.combine(start, time(0), tzinfo=ctx.zone),
                       created_at__lt=datetime.combine(end + timedelta(days=1), time(0), tzinfo=ctx.zone))
    who = None
    if args.get('person'):
        who = _one(ctx, args['person'])
        qs = qs.filter(assigned_to_id__in=who.user_ids or [-1])
    qs = qs.exclude(category='knowledge_gap')
    total = qs.count()
    by_priority = {r['priority']: r['n'] for r in qs.values('priority').annotate(n=Count('id'))}
    by_category = {r['category']: r['n'] for r in qs.values('category').annotate(n=Count('id'))}

    # A ticket held by the chat widget's or the inbox's system account is held by no person yet. Live on Margalla
    # the bot's name came through as a holder, and "who has the most open tickets?" was answered with it.
    def holder_of(user_id, username):
        if not user_id or username in SYSTEM_TICKET_ACCOUNTS:
            return 'nobody yet (waiting for someone to take it)'
        return ctx.name_of_user(user_id)
    by_holder = {}
    for r in qs.values('assigned_to_id', 'assigned_to__username').annotate(n=Count('id')):
        name = holder_of(r['assigned_to_id'], r['assigned_to__username'])
        by_holder[name] = by_holder.get(name, 0) + r['n']
    link = '/frontline/dashboard?tab=tickets'
    scope = ('open ' if (args.get('status') or 'open') == 'open' else '') + 'ticket(s)'
    head = (f'{total} {scope}' + (f' assigned to {who.name}' if who else '') + ' that you can see in Frontline'
            + (f'; by priority: ' + ', '.join(f'{k} {v}' for k, v in sorted(by_priority.items())) if by_priority else '')
            + (f'; by category: ' + ', '.join(f'{k} {v}' for k, v in sorted(by_category.items())) if by_category else '')
            + (f'; held by: ' + ', '.join(f'{k} {v}' for k, v in sorted(by_holder.items(), key=lambda kv: -kv[1]))
               if by_holder else '')
            + '.')
    facts = [Fact(head, 'Frontline', link)]
    for t in qs.select_related('contact', 'assigned_to').order_by('-created_at')[:ROWS]:
        customer = (t.contact.name or t.contact.email) if t.contact_id else 'no customer'
        holder = holder_of(t.assigned_to_id, t.assigned_to.username if t.assigned_to_id else '')
        facts.append(Fact(f'Ticket #{t.id} "{t.title}" — {t.get_status_display()}, {t.get_priority_display()} '
                          f'priority, {t.get_category_display()}, customer {customer}, held by {holder}, '
                          f'opened {_when(ctx, t.created_at)}', 'Frontline', link))
    return facts


def customers_waiting(ctx, args):
    from Frontline_agent.alerts import hears_handoffs
    from Frontline_agent.models import Ticket
    if not hears_handoffs(ctx.company_user):
        raise Refused('Customers waiting for a person are shown to the logins Frontline alerts about hand-offs.')
    waiting = (Ticket.objects.filter(company=ctx.company, handoff_status='pending')
               .exclude(status__in=('resolved', 'closed')).select_related('contact').order_by('handoff_requested_at'))
    gaps = Ticket.objects.filter(company=ctx.company, category='knowledge_gap', status__in=OPEN_TICKET).count()
    facts = [Fact(f'{waiting.count()} customer(s) waiting for a person; {gaps} question(s) the website assistant '
                  f'could not answer.', 'Frontline', '/frontline/dashboard?tab=handoffs')]
    for t in waiting[:ROWS]:
        customer = (t.contact.name or t.contact.email) if t.contact_id else 'a visitor'
        since = f' since {_when(ctx, t.handoff_requested_at)}' if t.handoff_requested_at else ''
        facts.append(Fact(f'{customer} waiting{since}: "{t.title}"', 'Frontline', '/frontline/dashboard?tab=handoffs'))
    return facts


LOOKUPS = {lk.name: lk for lk in (
    Lookup('person', 'people', 'Who someone is: job title, department, manager, email, dashboard role.',
           {'person': 'a name, or "me"'}, person),
    Lookup('people', 'people', 'Everyone in the company, or in one department, with their roles.',
           {'department': 'optional'}, people),
    Lookup('calendar', 'calendar', "Busy times of one or more people in a date range: every agent's meetings, "
           'interviews, sales calls, approved leave and company holidays.',
           {'people': 'list of names or "me"', 'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD',
            'from_time': 'HH:MM, optional', 'to_time': 'HH:MM, optional'}, calendar),
    Lookup('who_is_free', 'calendar', 'Who in the company is free for the whole of one time window on one day.',
           {'date': 'YYYY-MM-DD', 'from_time': 'HH:MM', 'to_time': 'HH:MM', 'department': 'optional'}, who_is_free),
    Lookup('tasks', 'project_manager_agent', "A person's open Project Manager tasks: project, status, priority, "
           'due date, late or not.', {'person': 'a name, or "me"', 'due_by': 'YYYY-MM-DD, optional'}, tasks),
    Lookup('project', 'project_manager_agent', "One project's status: tasks done and not done, late tasks, who has "
           'open tasks, deadline.', {'project': 'its name'}, project),
    Lookup('projects', 'project_manager_agent', 'All projects with their status and tasks done.', {}, projects),
    Lookup('workload', 'project_manager_agent', 'Open and late tasks per person, to see who is overloaded.', {},
           workload),
    Lookup('leave', 'hr_agent', 'Who is on leave in a date range (approved, and requests waiting where the asker may '
           'see them), or one person.', {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD', 'person': 'optional'}, leave),
    Lookup('leave_balance', 'hr_agent', 'How many leave days a person has left, by kind.',
           {'person': 'a name, or "me"'}, leave_balance),
    Lookup('holidays', 'hr_agent', 'Company holidays in a date range.', {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'},
           holidays),
    Lookup('tickets', 'frontline_agent', 'Support tickets the asker can see: open ones (default) or all, optionally '
           'opened in a date range or held by one person; counts by priority and category.',
           {'status': '"open" or "all"', 'start': 'optional', 'end': 'optional', 'person': 'optional'}, tickets),
    Lookup('customers_waiting', 'frontline_agent', 'Customers waiting for a person (hand-offs) and questions the '
           'website assistant could not answer.', {}, customers_waiting),
)}


from core.assistant.more_lookups import DOCUMENT_MODULES, MORE  # noqa: E402  (they use the helpers above)

LOOKUPS.update({lk.name: lk for lk in MORE})


def available(modules) -> list[Lookup]:
    """The lookups a company with these agents may use. People, the calendar and the week are everyone's; the
    documents lookup needs an agent that keeps documents."""
    def usable(lk):
        if lk.module in ('people', 'calendar', 'week'):
            return True
        if lk.module == 'documents':
            return any(m in modules for m in DOCUMENT_MODULES)
        return lk.module in modules
    return [lk for lk in LOOKUPS.values() if usable(lk)]

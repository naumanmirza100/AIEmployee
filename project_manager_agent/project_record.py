"""A project's record: what was decided and done, on one or two pages.

Asked for after the client test of 25 Oct 2026: Meeting Notes gets a second tab with, for the chosen project,
the decisions taken, the actions and due dates, the risks, the project made and the work handed out. Not a log
of every event: a short summary in date order, a few bullets a day, with what is due, what is late and who is
doing what after it.

Built only from what is stored already — the audit entries every create and edit writes (the dashboard's in
PMAuditLog, an employee login's in UserActivityLog), the tasks, the meeting notes kept on the project and its
risks. No AI call, so opening it costs nothing and shows the same thing twice.
"""
from __future__ import annotations

import json
from collections import Counter, OrderedDict, defaultdict
from datetime import date, datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from core.models import CompanyUser, Project, ProjectRisk, Task, UserActivityLog
from project_manager_agent.models import PMAuditLog, ProjectToolResult
from project_manager_agent.tool_results import MEETING_NOTES

MAX_DAYS = 14                 # dates shown in the timeline; earlier ones fold into one line
MAX_ITEMS_PER_DAY = 8         # bullets are already grouped by kind
MAX_LIST = 8                  # tasks per list in "due and late", decisions, risks
SOON_DAYS = 7

# The period the record covers (Meeting Notes → Project record, the buttons above it). Asked for on 27 Oct 2026:
# the shorter the period, the more each line says, so a day and a month come out at about the same length.
PERIODS = ('today', 'yesterday', '7d', '30d', 'all')
PERIOD_WORDS = {'today': 'Today', 'yesterday': 'Yesterday', '7d': 'In the last 7 days',
                '30d': 'In the last 30 days', 'all': 'Since the start'}
HEADLINE_ORDER = {'decision': 0, 'meeting': 1, 'risk': 2, 'created': 3, 'done': 4}   # what a one-line summary names first
IMPORTANT_PROJECT_FIELDS = ('deadline', 'start_date', 'status', 'priority', 'name')
FIELD_WORDS = {'due_date': 'due dates', 'assignee': 'owners', 'status': 'statuses', 'priority': 'priorities',
               'title': 'titles', 'description': 'descriptions', 'estimated_hours': 'estimates',
               'depends_on': 'dependencies'}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _day(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return timezone.localtime(value).date() if timezone.is_aware(value) else value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _shown(value):
    """'2026-11-04' → '4 Nov 2026'; anything else as it is."""
    d = _day(value) if isinstance(value, (str, date, datetime)) else None
    if d and isinstance(value, str) and len(value) >= 10 and value[4] == '-':
        return f'{d.day} {d:%b %Y}'
    if isinstance(value, (date, datetime)):
        return f'{d.day} {d:%b %Y}'
    return str(value).replace('_', ' ') if value not in (None, '') else 'none'


def _names(titles, limit=3):
    titles = [t for t in titles if t]
    shown = ', '.join(f'“{t}”' for t in titles[:limit])
    return shown + (f' and {len(titles) - limit} more' if len(titles) > limit else '')


def _person(user):
    if user is None:
        return None
    return user.get_full_name() or user.username


def _plural(n, word):
    return f'{n} {word}{"" if n == 1 else "s"}'


def _window(period, today):
    """(first day, last day) of the period; the first is None for "all"."""
    if period == 'today':
        return today, today
    if period == 'yesterday':
        return today - timedelta(days=1), today - timedelta(days=1)
    if period == '7d':
        return today - timedelta(days=6), today
    if period == '30d':
        return today - timedelta(days=29), today
    return None, today


def _inside(day, window):
    if day is None:
        return False
    start, end = window or (None, None)
    return (start is None or start <= day) and (end is None or day <= end)


def _summary(period, counts, *, projects=None, since='the start'):
    """One sentence for the top of the record: what happened in the period, in numbers."""
    parts = []
    if counts['added']:
        parts.append(_plural(counts['added'], 'task') + ' added'
                     + (f' across {_plural(projects, "project")}' if projects and projects > 1 else ''))
    if counts['done']:
        parts.append(f'{counts["done"]} done' if counts['added'] else f'{_plural(counts["done"], "task")} done')
    if counts['handed']:
        parts.append(f'{counts["handed"]} handed over')
    if counts['moved']:
        parts.append(f'due dates moved on {_plural(counts["moved"], "task")}')
    if counts['removed']:
        parts.append(f'{counts["removed"]} removed')
    if counts['decisions']:
        parts.append(_plural(counts['decisions'], 'project change'))
    if counts['meetings']:
        parts.append(_plural(counts['meetings'], 'meeting') + ' noted'
                     + (f' ({_plural(counts["meeting_decisions"], "decision")})' if counts['meeting_decisions'] else ''))
    if counts['risks']:
        parts.append(_plural(counts['risks'], 'risk') + ' logged')
    if counts['booked']:
        parts.append(_plural(counts['booked'], 'meeting') + ' booked')
    if counts['joined']:
        parts.append(f'{_plural(counts["joined"], "person")} joined'.replace('persons', 'people'))
    if counts['left']:
        parts.append(f'{counts["left"]} left the team')
    if counts['projects_removed']:
        parts.append(_plural(counts['projects_removed'], 'project') + ' removed')
    lead = PERIOD_WORDS[period] if period != 'all' else f'Since {since}'
    if not parts:
        return f'Nothing recorded {lead[0].lower() + lead[1:]}.' if period != 'all' else 'Nothing recorded yet.'
    return f'{lead}: {", ".join(parts)}.'


# ---------------------------------------------------------------------------
# Gathering what happened
# ---------------------------------------------------------------------------

def _entries(project, task_ids):
    """Every stored write about this project or its tasks, dashboard and employee alike, oldest first:
    ``{at, action, model, object_id, title, details, by}``."""
    rows = []
    audit = (PMAuditLog.objects
             .filter(company_user__company_id=project.company_id)
             .filter(Q(model_name='Project', object_id=project.id)
                     | Q(model_name='Task', object_id__in=task_ids)
                     | Q(model_name='Task', action='task_deleted', details__project_id=project.id))
             .select_related('company_user'))
    for e in audit:
        rows.append({'at': e.created_at, 'action': e.action, 'model': e.model_name, 'object_id': e.object_id,
                     'title': e.object_title, 'details': e.details if isinstance(e.details, dict) else {},
                     'by': getattr(e.company_user, 'full_name', '') or ''})
    employee = (UserActivityLog.objects
                .filter(Q(entity_type='Project', entity_id=project.id) | Q(entity_type='Task', entity_id__in=task_ids))
                .select_related('user'))
    for e in employee:
        try:
            details = json.loads(e.details or '{}')
        except ValueError:
            details = {}
        rows.append({'at': e.created_at, 'action': e.action, 'model': e.entity_type, 'object_id': e.entity_id,
                     'title': details.get('title') or '', 'details': details if isinstance(details, dict) else {},
                     'by': _person(e.user) or ''})
    rows.sort(key=lambda r: r['at'])
    return rows


def _meetings(project):
    out = []
    for row in ProjectToolResult.objects.filter(project=project, kind=MEETING_NOTES).order_by('created_at'):
        result = row.data.get('result') or {}
        out.append({
            'day': _day(row.data.get('date')) or _day(row.created_at),
            'topic': row.data.get('topic') or 'Meeting',
            # Notes saved without a topic read "Meeting", not 'Meeting "Meeting"'.
            'label': f'Meeting “{row.data["topic"]}”' if row.data.get('topic') else 'Meeting',
            'decisions': [str(d.get('decision') if isinstance(d, dict) else d) for d in result.get('key_decisions') or []
                          if (d.get('decision') if isinstance(d, dict) else d)],
            'actions': [a for a in result.get('action_items') or [] if isinstance(a, dict) and a.get('action')],
            'risks': [r for r in result.get('risks_mentioned') or [] if r],
        })
    return out


class _Day:
    """What happened on one date, folded into a few bullets."""

    def __init__(self):
        self.items = []                       # (kind, text) in the order they happened
        self.created = []                     # (title, owner name)
        self.completed = []
        self.deleted = []
        self.handed = []                      # (title, to)
        self.moved_dates = []                 # (title, from, to)
        self.priorities = []
        self.edited = Counter()               # field -> count, for entries written before from/to were kept
        self.headlines = []                   # (kind, few words): the project made, its changes, meetings, risks
        self.tally = Counter()                # decisions, meetings, meeting_decisions, risks

    def merge(self, other):
        """Another day's events added to this one: a week of a project in one line."""
        for name in ('items', 'created', 'completed', 'deleted', 'handed', 'moved_dates', 'priorities', 'headlines'):
            getattr(self, name).extend(getattr(other, name))
        self.edited.update(other.edited)
        self.tally.update(other.tally)
        return self

    def counts(self):
        out = Counter(added=len(self.created), done=len(self.completed), handed=len(self.handed),
                      moved=len(self.moved_dates), priorities=len(self.priorities), removed=len(self.deleted),
                      edits=sum(self.edited.values()))
        out.update(self.tally)
        return +out

    def brief(self, headlines=3):
        """The day (or week) in one line: what was decided or met about first, then the work in numbers."""
        c = self.counts()
        ranked = sorted(self.headlines, key=lambda h: HEADLINE_ORDER.get(h[0], 9))
        parts = [text for _, text in ranked[:headlines]]
        if len(ranked) > headlines:
            parts[-1] += f' (+{len(ranked) - headlines} more)'
        work = []
        if c['added']:
            work.append(_plural(c['added'], 'task') + ' added')
        if c['done']:
            work.append(f'{c["done"]} done' if work else f'{_plural(c["done"], "task")} done')
        if c['handed']:
            work.append(f'{c["handed"]} handed over')
        if c['moved']:
            work.append(f'due dates moved on {c["moved"]}')
        if c['priorities']:
            work.append(f'priority changed on {c["priorities"]}')
        if c['removed']:
            work.append(f'{c["removed"]} removed')
        if c['edits'] and not work:
            work.append(_plural(c['edits'], 'task edit'))
        if work:
            parts.append(', '.join(work))
        if not parts:
            return None
        kind = ranked[0][0] if ranked else ('tasks' if c['added'] else 'done' if c['done'] else 'edit')
        text = '; '.join(parts)
        return kind, text[0].upper() + text[1:]

    def bullets(self, names=3):
        # The project being made comes first, then the work added with it, then the rest of the day.
        out = [item for item in self.items if item[0] == 'created']
        rest = [item for item in self.items if item[0] != 'created']
        if self.created:
            owners = Counter(owner for _, owner in self.created if owner)
            text = f'{_plural(len(self.created), "task")} added: {_names([t for t, _ in self.created], names)}'
            if owners:
                text += ' — assigned to ' + ', '.join(f'{name} ({n})' for name, n in owners.most_common())
            unassigned = sum(1 for _, owner in self.created if not owner)
            if unassigned:
                text += f'; {unassigned} without an owner'
            out.append(('tasks', text))
        out.extend(rest)
        if self.handed:
            out.append(('assigned', 'Handed over: ' + '; '.join(f'“{t}” to {to}' for t, to in self.handed[:names])
                        + (f' and {len(self.handed) - names} more' if len(self.handed) > names else '')))
        if self.moved_dates:
            if len(self.moved_dates) <= 2:
                for title, before, after in self.moved_dates:
                    out.append(('dates', f'“{title}” due date moved from {_shown(before)} to {_shown(after)}'))
            else:
                out.append(('dates', f'Due dates moved on {_plural(len(self.moved_dates), "task")}: '
                                     f'{_names([t for t, _, _ in self.moved_dates], names)}'))
        if self.priorities:
            out.append(('priority', f'Priority changed on {_plural(len(self.priorities), "task")}: '
                                    f'{_names([t for t, _ in self.priorities], names)}'))
        if self.completed:
            out.append(('done', f'Completed: {_names(self.completed, names + 1)}'))
        if self.deleted:
            out.append(('deleted', f'Removed: {_names(self.deleted, names)}'))
        if self.edited:
            parts = ', '.join(FIELD_WORDS.get(f, f.replace('_', ' ')) for f, _ in self.edited.most_common(3))
            out.append(('edit', f'Tasks edited ({parts})'))
        return out


def _timeline_and_decisions(project, tasks, entries, meetings, risks, fold=True, window=None, names=3,
                            per_day=MAX_ITEMS_PER_DAY):
    """The timeline (days inside `window`), the note on folded days, the decisions, and the days themselves (date →
    _Day) for the record of all projects."""
    days = defaultdict(_Day)
    decisions = []
    titles = {t.id: t.title for t in tasks}
    users = {}
    completed = set()

    created_by = getattr(project.created_by_company_user, 'full_name', '') if project.created_by_company_user_id else ''
    plan = []
    if project.start_date:
        plan.append(f'starts {_shown(project.start_date)}')
    first_deadline = next((e['details'].get('from', {}).get('deadline') for e in entries
                           if e['model'] == 'Project' and e['details'].get('from', {}).get('deadline')), None)
    if first_deadline or project.effective_deadline:
        plan.append(f'deadline {_shown(first_deadline or project.effective_deadline)}')
    made = days[_day(project.created_at)]
    made.items.append(
        ('created', 'Project created' + (f' by {created_by}' if created_by else '') + (f' — {", ".join(plan)}' if plan else '')))
    made.headlines.append(('created', 'project created'))

    for e in entries:
        day, d = days[_day(e['at'])], e['details']
        moved_from, moved_to = d.get('from') or {}, d.get('to') or {}
        if e['model'] == 'Project' and e['action'] in ('project_updated', 'update_project'):
            for field in IMPORTANT_PROJECT_FIELDS:
                if field not in moved_to:
                    continue
                if field == 'deadline':
                    text = f'Deadline moved from {_shown(moved_from.get(field))} to {_shown(moved_to[field])}'
                    short = f'deadline moved to {_shown(moved_to[field])}'
                elif field == 'start_date':
                    text = f'Start moved from {_shown(moved_from.get(field))} to {_shown(moved_to[field])}'
                    short = f'start moved to {_shown(moved_to[field])}'
                elif field == 'name':
                    text = f'Renamed from “{moved_from.get(field)}” to “{moved_to[field]}”'
                    short = f'renamed “{moved_to[field]}”'
                else:
                    text = f'{field.title()} changed from {_shown(moved_from.get(field))} to {_shown(moved_to[field])}'
                    short = f'{field} now {_shown(moved_to[field])}'
                day.items.append(('decision', text + (f' (by {e["by"]})' if e['by'] else '')))
                day.headlines.append(('decision', short))
                day.tally['decisions'] += 1
                decisions.append({'date': _day(e['at']).isoformat(), 'text': text, 'source': 'Project change'})
            if not moved_to:
                important = [f for f in d.get('fields') or [] if f in IMPORTANT_PROJECT_FIELDS]
                if important:
                    changed = ', '.join(f.replace('_', ' ') for f in important)
                    day.items.append(('decision', f'Project {changed} changed' + (f' (by {e["by"]})' if e['by'] else '')))
                    day.headlines.append(('decision', f'project {changed} changed'))
                    day.tally['decisions'] += 1
        elif e['model'] == 'Task':
            title = e['title'] or titles.get(e['object_id']) or 'a task'
            if e['action'] in ('task_created', 'create_task'):
                owner_id = d.get('assignee_id')
                if owner_id and owner_id not in users:
                    from django.contrib.auth.models import User
                    users[owner_id] = _person(User.objects.filter(pk=owner_id).first())
                day.created.append((title, users.get(owner_id) if owner_id else None))
            elif e['action'] in ('task_deleted', 'delete_task'):
                day.deleted.append(title)
            elif e['action'] in ('task_updated', 'update_task', 'task_assigned'):
                if moved_to:
                    if 'assignee' in moved_to and moved_to['assignee']:
                        day.handed.append((title, moved_to['assignee']))
                    if 'due_date' in moved_to:
                        day.moved_dates.append((title, moved_from.get('due_date'), moved_to['due_date']))
                    if 'priority' in moved_to:
                        day.priorities.append((title, moved_to['priority']))
                    if moved_to.get('status') == 'done' and e['object_id'] not in completed:
                        completed.add(e['object_id'])
                        day.completed.append(title)
                else:
                    for field in d.get('fields') or []:
                        if field in FIELD_WORDS and field != 'status':
                            day.edited[field] += 1

    # Tasks finished before edits kept their from and to: the task's own completion time.
    for task in tasks:
        if task.status == 'done' and task.completed_at and task.id not in completed:
            days[_day(task.completed_at)].completed.append(task.title)

    for m in meetings:
        bits = []
        if m['decisions']:
            bits.append('decided ' + '; '.join(m['decisions'][:2]) + (f' (+{len(m["decisions"]) - 2} more)'
                                                                     if len(m['decisions']) > 2 else ''))
        if m['actions']:
            bits.append(_plural(len(m['actions']), 'action item'))
        if m['risks']:
            bits.append(_plural(len(m['risks']), 'risk') + ' raised')
        meeting_day = days[m['day']]
        meeting_day.items.append(('meeting', m['label'] + (': ' + ', '.join(bits) if bits else '')))
        counted = [_plural(len(m['decisions']), 'decision')] if m['decisions'] else []
        if m['actions']:
            counted.append(_plural(len(m['actions']), 'action'))
        meeting_day.headlines.append(('meeting', m['label'][0].lower() + m['label'][1:]
                                      + (f' ({", ".join(counted)})' if counted else '')))
        meeting_day.tally.update(meetings=1, meeting_decisions=len(m['decisions']))
        for text in m['decisions']:
            decisions.append({'date': m['day'].isoformat(), 'text': text, 'source': m['label']})

    for risk in risks:
        logged = days[_day(risk.identified_at)]
        logged.items.append(('risk', f'Risk logged: {risk.title} ({risk.get_severity_display()})'))
        logged.headlines.append(('risk', f'risk: {risk.title}'))
        logged.tally['risks'] += 1
        if risk.resolved_at:
            days[_day(risk.resolved_at)].items.append(('done', f'Risk resolved: {risk.title}'))
            days[_day(risk.resolved_at)].headlines.append(('done', f'risk resolved: {risk.title}'))

    kept = OrderedDict(sorted((d, v) for d, v in days.items() if _inside(d, window)))
    timeline = [{'date': d.isoformat(), 'items': [{'kind': k, 'text': t} for k, t in v.bullets(names)[:per_day]]}
                for d, v in kept.items()]
    timeline = [day for day in timeline if day['items']]
    earlier = None
    if fold and len(timeline) > MAX_DAYS:
        folded = timeline[:-MAX_DAYS]
        events = sum(len(day['items']) for day in folded)
        earlier = (f'{_plural(len(folded), "earlier day")} ({_shown(folded[0]["date"])} to '
                   f'{_shown(folded[-1]["date"])}): {_plural(events, "event")} not shown')
        # The day the project was made always stays at the top.
        timeline = [folded[0]] + timeline[-MAX_DAYS:] if folded[0]['date'] == _day(project.created_at).isoformat() \
            else timeline[-MAX_DAYS:]
    decisions = [x for x in decisions if _inside(_day(x['date']), window)]
    decisions.sort(key=lambda x: x['date'], reverse=True)
    return timeline, earlier, decisions[:MAX_LIST], kept


# ---------------------------------------------------------------------------
# Where the project stands
# ---------------------------------------------------------------------------

def _task_line(task, today):
    due = _day(task.due_date)
    return {'id': task.id, 'title': task.title, 'owner': _person(task.assignee) or 'No owner',
            'due': due.isoformat() if due else None, 'days': (due - today).days if due else None,
            'priority': task.priority, 'status': task.status}


def build(project, today=None, fold=True, period='all', keep_days=False):
    """The record of `project` as the Meeting Notes tab shows it. `fold=False` keeps every day of the timeline
    (the record of all projects folds them itself). `period` limits the timeline and the decisions to today,
    yesterday, the last 7 or 30 days, or "all"; a single day says more per line (more names, more lines). What is
    due, late and at risk is always as things stand now. `keep_days` adds the days themselves under "_days", for
    the record of all projects."""
    today = today or timezone.localdate()
    period = period if period in PERIODS else 'all'
    window = _window(period, today)
    one_day = period in ('today', 'yesterday')
    tasks = list(Task.objects.filter(project=project).select_related('assignee').order_by('due_date', 'id'))
    entries = _entries(project, [t.id for t in tasks])
    meetings = _meetings(project)
    risks = list(ProjectRisk.objects.filter(project=project).order_by('identified_at'))
    timeline, earlier, decisions, days = _timeline_and_decisions(
        project, tasks, entries, meetings, risks, fold=fold, window=window,
        names=6 if one_day else 3, per_day=12 if one_day else MAX_ITEMS_PER_DAY)
    counts = Counter()
    for day in days.values():
        counts.update(day.counts())
    recent_meetings = ([m for m in meetings if _inside(m['day'], window)] if period != 'all' else meetings)[-2:]

    open_tasks = [t for t in tasks if t.status != 'done']
    done = len(tasks) - len(open_tasks)
    late = [t for t in open_tasks if t.due_date and _day(t.due_date) < today]
    soon = [t for t in open_tasks if t.due_date and today <= _day(t.due_date) <= today + timedelta(days=SOON_DAYS)]
    no_owner = [t for t in open_tasks if not t.assignee_id]
    deadline = _day(project.effective_deadline)
    start = _day(project.start_date) or _day(project.created_at)
    pct_done = round(100 * done / len(tasks)) if tasks else 0
    pct_time = None
    if deadline and start and deadline > start:
        pct_time = max(0, min(100, round(100 * (today - start).days / (deadline - start).days)))

    people = defaultdict(lambda: {'open': 0, 'done': 0, 'late': 0})
    for t in tasks:
        name = _person(t.assignee) or 'No owner'
        people[name]['done' if t.status == 'done' else 'open'] += 1
        if t in late:
            people[name]['late'] += 1
    team = sorted(({'name': n, **c} for n, c in people.items()), key=lambda p: (p['name'] == 'No owner', -p['open']))

    risk_list = [{'text': f'{r.title}' + (f' — {r.mitigation_plan}' if r.mitigation_plan else ''),
                  'severity': r.severity, 'source': 'Risk register'}
                 for r in risks if r.status not in ('resolved', 'closed')]
    for m in reversed(meetings[-3:]):
        for r in m['risks']:
            text = r.get('risk') if isinstance(r, dict) else str(r)
            if text:
                risk_list.append({'text': text, 'severity': (r.get('severity') if isinstance(r, dict) else None) or 'medium',
                                  'source': m['label']})
    if late:
        risk_list.insert(0, {'text': f'{_plural(len(late), "task")} past due: {_names([t.title for t in late])}',
                             'severity': 'high', 'source': 'Due dates'})
    if deadline and open_tasks and deadline < today:
        risk_list.insert(0, {'text': f'The deadline ({_shown(deadline)}) has passed with '
                                     f'{_plural(len(open_tasks), "task")} still open', 'severity': 'critical',
                             'source': 'Deadline'})
    elif pct_time is not None and tasks and pct_time - pct_done >= 25:
        risk_list.append({'text': f'{pct_time}% of the time to the deadline has gone, {pct_done}% of the tasks are done',
                          'severity': 'medium', 'source': 'Progress'})
    after_deadline = [t for t in open_tasks if deadline and t.due_date and _day(t.due_date) > deadline]
    if after_deadline:
        risk_list.append({'text': f'{_plural(len(after_deadline), "task")} due after the project deadline',
                          'severity': 'medium', 'source': 'Due dates'})

    next_steps = []
    if late:
        next_steps.append(f'Agree new dates for the {_plural(len(late), "late task")}, or move the deadline '
                          f'(Project Pilot: “change the deadline of {project.name} to …”).')
    if no_owner:
        next_steps.append(f'Give {_plural(len(no_owner), "open task")} an owner: {_names([t.title for t in no_owner])}.')
    if deadline and today <= deadline <= today + timedelta(days=SOON_DAYS) and open_tasks:
        next_steps.append(f'The deadline is in {_plural((deadline - today).days, "day")} with '
                          f'{_plural(len(open_tasks), "task")} open: check what can still be finished.')
    if not meetings or (meetings and (today - meetings[-1]['day']).days > 14):
        next_steps.append('No meeting notes in the last two weeks: add the next meeting’s notes in the Analyze tab, '
                          'so its decisions and actions appear here.')
    # Someone with at least twice the open work of the average owner (and at least 4 tasks) is worth a word.
    owners = [p for p in team if p['name'] != 'No owner']
    average = sum(p['open'] for p in owners) / len(owners) if owners else 0
    loaded = [p for p in owners if p['open'] >= 4 and p['open'] >= 2 * average]
    if loaded and len(owners) > 1:
        next_steps.append(f'{loaded[0]["name"]} has {_plural(loaded[0]["open"], "open task")}: consider sharing them out.')

    record = {
        'project': {
            'id': project.id, 'name': project.name, 'status': project.get_status_display(),
            'priority': project.get_priority_display(),
            'start': start.isoformat() if start else None, 'deadline': deadline.isoformat() if deadline else None,
            'days_left': (deadline - today).days if deadline else None,
            'tasks': len(tasks), 'done': done, 'open': len(open_tasks), 'late': len(late),
            'pct_done': pct_done, 'pct_time': pct_time,
        },
        'period': _period_info(period, window, _summary(period, counts, since='the project began')),
        'timeline': timeline,
        'earlier': earlier,
        'decisions': decisions,
        'due': {'late': [_task_line(t, today) for t in late[:MAX_LIST]],
                'soon': [_task_line(t, today) for t in soon[:MAX_LIST]],
                'more_late': max(0, len(late) - MAX_LIST), 'more_soon': max(0, len(soon) - MAX_LIST)},
        'meeting_actions': [dict(a, meeting=m['topic'], date=m['day'].isoformat())
                            for m in reversed(recent_meetings) for a in m['actions']][:MAX_LIST],
        'risks': risk_list[:MAX_LIST],
        'team': team,
        'next_steps': next_steps,
        'generated_at': timezone.now().isoformat(),
    }
    if keep_days:
        record['_days'] = days
    return record


def _period_info(period, window, summary):
    start, end = window
    return {'key': period, 'label': PERIOD_WORDS[period], 'from': start.isoformat() if start else None,
            'to': end.isoformat(), 'summary': summary}


# ---------------------------------------------------------------------------
# All projects at once
# ---------------------------------------------------------------------------

MAX_PROJECTS = 60             # the most recently changed, when a company has more
# How much each line of the record of all projects says, by period: one day lists each project's own bullets
# ("normal"); a week, one line per project a day ("brief"); a month or more, one line per project a week ("digest").
# Each has a budget of lines, so a day and a month come out at about the same length.
DETAIL_ALL = {'today': 'normal', 'yesterday': 'normal', '7d': 'brief', '30d': 'digest', 'all': 'digest'}
LINES_ALL = {'normal': 30, 'brief': 24, 'digest': 24}
BULLETS_PER_PROJECT = 4       # a project's bullets on one day ("normal") are at least half of this
LIST_ALL = {'normal': 8, 'brief': 5, 'digest': 5}     # decisions, due, late, risks
TEAM_ALL = 8


def _some(items, limit=3):
    return '; '.join(items[:limit]) + (f' and {len(items) - limit} more' if len(items) > limit else '')


def _company_people(company):
    """Everyone who has had an employee login with the company, still working or since switched off."""
    from django.contrib.auth.models import User
    return (User.objects.filter(is_superuser=False)
            .filter(Q(profile__company=company) | Q(profile__created_by_company_user__company=company))
            .select_related('profile').distinct())


def _meeting_time(meeting):
    """The meeting's time in its own time zone, as the meeting lists show it."""
    if not meeting.proposed_time:
        return None
    try:
        from zoneinfo import ZoneInfo
        return meeting.proposed_time.astimezone(ZoneInfo(meeting.timezone_name or 'UTC'))
    except Exception:
        return timezone.localtime(meeting.proposed_time)


def _event(group, kind, text, short, **tally):
    return {'group': group, 'kind': kind, 'text': text, 'short': short, 'tally': tally}


def _company_events(company, people):
    """What happened outside any one project, by day: projects removed, people joining and leaving, meetings booked,
    confirmed and called off. {date: [event]}, each event with its full line ("text"), a few words for a line of a
    week ("short") and what it counts ("tally")."""
    from hr_agent.models import Employee, HRAuditLog
    from project_manager_agent.models import MeetingResponse, ScheduledMeeting
    events = defaultdict(list)

    for e in (PMAuditLog.objects.filter(company_user__company=company, model_name='Project', action='project_deleted')
              .select_related('company_user')):
        by = getattr(e.company_user, 'full_name', '') or ''
        events[_day(e.created_at)].append(_event(
            'Projects', 'deleted', f'Project removed: “{e.object_title}”' + (f' (by {by})' if by else ''),
            f'removed “{e.object_title}”', projects_removed=1))

    joined = defaultdict(list)
    for user in people:
        profile = getattr(user, 'profile', None)
        role = profile.get_role_display() if profile is not None else ''
        joined[_day(user.date_joined)].append((_person(user), role))
    for day, names in joined.items():
        events[day].append(_event(
            'Team', 'people', 'Joined the team: ' + _some([n + (f' ({r})' if r else '') for n, r in names], 6),
            'joined: ' + _some([n for n, _ in names], 2).replace('; ', ', '), joined=len(names)))
    names_of = {}
    for e in HRAuditLog.objects.filter(company=company, target_type='employee',
                                       action__in=('employee.deactivate', 'employee.reactivate')):
        if e.target_id not in names_of:
            record = Employee.objects.filter(pk=e.target_id).select_related('user').first()
            names_of[e.target_id] = _person(record.user) if record is not None and record.user_id else None
        if names_of[e.target_id]:
            left = e.action == 'employee.deactivate'
            name = names_of[e.target_id]
            events[_day(e.created_at)].append(
                _event('Team', 'deleted', f'Left the team: {name}', f'left: {name}', left=1) if left else
                _event('Team', 'people', f'Back on the team: {name}', f'back: {name}', back=1))

    booked, confirmed, called_off = defaultdict(list), defaultdict(list), defaultdict(list)
    for m in (ScheduledMeeting.objects.filter(organizer__company=company)
              .prefetch_related('participants__user').order_by('created_at')):
        when = _meeting_time(m)
        label = f'“{m.title}”' + (f' ({when.day} {when:%b}, {when:%H:%M})' if when else '')
        invited = [_person(p.user) for p in m.participants.all() if p.user_id]
        booked[_day(m.created_at)].append(label + (f' with {", ".join(invited[:4])}' if invited else ''))
        if m.status == 'accepted':
            last = (MeetingResponse.objects.filter(meeting=m, action='accepted').order_by('-created_at')
                    .values_list('created_at', flat=True).first())
            confirmed[_day(last or m.updated_at)].append(label)
        elif m.status in ('withdrawn', 'rejected'):
            called_off[_day(m.updated_at)].append(label + (' — withdrawn' if m.status == 'withdrawn' else ' — declined'))
    for day, items in booked.items():
        events[day].append(_event('Meetings', 'meeting', f'{_plural(len(items), "meeting")} booked: {_some(items)}',
                                  _plural(len(items), 'meeting') + ' booked', booked=len(items)))
    for day, items in confirmed.items():
        events[day].append(_event('Meetings', 'done', f'Confirmed, everyone accepted: {_some(items)}',
                                  f'{len(items)} confirmed', confirmed=len(items)))
    for day, items in called_off.items():
        events[day].append(_event('Meetings', 'deleted', f'Called off: {_some(items)}',
                                  f'{len(items)} called off', called_off=len(items)))
    return events


def _group_digest(group, tally):
    """A week of the company's own news in a group, in numbers."""
    if group == 'Meetings':
        parts = [_plural(tally['booked'], 'meeting') + ' booked' if tally['booked'] else '',
                 f'{tally["confirmed"]} confirmed' if tally['confirmed'] else '',
                 f'{tally["called_off"]} called off' if tally['called_off'] else '']
    elif group == 'Team':
        parts = [(_plural(tally['joined'], 'person') + ' joined').replace('persons', 'people') if tally['joined'] else '',
                 f'{tally["left"]} left' if tally['left'] else '', f'{tally["back"]} back' if tally['back'] else '']
    else:
        parts = [_plural(tally['projects_removed'], 'project') + ' removed' if tally['projects_removed'] else '']
    text = ', '.join(p for p in parts if p)
    return text[:1].upper() + text[1:]


def _week_label(start, window, today):
    first = max(start, window[0]) if window[0] else start
    last = min(start + timedelta(days=6), today)
    if first == last:
        return _shown(first)
    if first.month == last.month:
        return f'{first.day}–{last.day} {last:%b %Y}'
    return f'{first.day} {first:%b} – {last.day} {last:%b %Y}'


def _company_timeline(records, events, detail, window, today):
    """The record of all projects' "what happened", newest first: per day ("normal", "brief") or per week
    ("digest"), a group per project, then the projects removed, the team and the meetings; at most
    LINES_ALL[detail] lines, the rest counted in the note under it."""
    weekly = detail == 'digest'
    bucket = (lambda d: d - timedelta(days=d.weekday())) if weekly else (lambda d: d)
    slots = defaultdict(dict)                 # bucket → {project id: (project, _Day of that day or week)}
    for project, _, days in records:
        for d, day in days.items():
            held = slots[bucket(d)].setdefault(project.id, (project, _Day()))
            held[1].merge(day)
    news = defaultdict(lambda: defaultdict(list))   # bucket → group → events
    for d, rows in events.items():
        for row in rows:
            news[bucket(d)][row['group']].append(row)

    budget, shown, hidden = LINES_ALL[detail], 0, 0
    timeline = []
    for b in sorted(set(slots) | set(news), reverse=True):
        groups = []
        # A day's bullets per project: more when few projects moved that day, fewer when many did.
        news_lines = sum(min(3, len(rows)) for rows in news[b].values())
        per_project = max(BULLETS_PER_PROJECT // 2,
                          min(MAX_ITEMS_PER_DAY, (budget - news_lines) // max(1, len(slots[b]))))
        # The projects with decisions and meetings first, then the busiest.
        for project, day in sorted(slots[b].values(), key=lambda pd: (-len(pd[1].headlines),
                                                                      -sum(pd[1].counts().values()),
                                                                      pd[0].name.lower())):
            if detail == 'normal':
                items = [{'kind': k, 'text': t} for k, t in day.bullets(2)[:per_project]]
            else:
                line = day.brief()
                items = [{'kind': line[0], 'text': line[1]}] if line else []
            if items:
                groups.append({'label': project.name, 'project_id': project.id, 'items': items})
        for group in ('Projects', 'Team', 'Meetings'):
            rows = news[b].get(group)
            if not rows:
                continue
            if detail == 'normal':
                items = [{'kind': r['kind'], 'text': r['text']} for r in rows[:3]]
            elif detail == 'brief':
                text = '; '.join(r['short'] for r in rows)
                items = [{'kind': rows[0]['kind'], 'text': text[:1].upper() + text[1:]}]
            else:
                tally = Counter()
                for r in rows:
                    tally.update(r['tally'])
                items = [{'kind': rows[0]['kind'], 'text': _group_digest(group, tally)}]
            groups.append({'label': group, 'project_id': None, 'items': items})
        lines = sum(len(g['items']) for g in groups)
        if not lines:
            continue
        if shown + lines > budget:
            if timeline:                      # older news, beyond the budget: counted, not shown
                hidden += lines
                continue
            kept = []                         # the newest day alone is too long: its first groups
            for g in groups:
                if shown + len(g['items']) <= budget:
                    kept.append(g)
                    shown += len(g['items'])
                else:
                    hidden += len(g['items'])
            groups, lines = kept, 0
        timeline.append({'date': b.isoformat(), 'label': _week_label(b, window, today) if weekly else None,
                         'groups': groups})
        shown += lines
    earlier = None
    if hidden:
        earlier = (f'{_plural(hidden, "more line")} not shown. Choose a shorter period, or a project in the box for '
                   'all of its news.')
    return timeline, earlier


def build_company(company_user, today=None, period='7d'):
    """The record of all the company's projects at once ("All projects" in the Meeting Notes box): what was added,
    changed, removed and confirmed in the period, each line under its project, with the team's and the meetings'
    news; then where every project stands, what is due and late everywhere, the decisions, the risks and who is
    doing what. Briefer than one project's record, and briefer the longer the period (DETAIL_ALL). Built from the
    same stored entries as one project's record; no AI call."""
    from core.tenancy import projects_for_company_user
    today = today or timezone.localdate()
    period = period if period in PERIODS else '7d'
    window = _window(period, today)
    detail = DETAIL_ALL[period]
    company = getattr(company_user, 'company', None)
    all_projects = projects_for_company_user(company_user)
    projects = list(all_projects.order_by('-updated_at')[:MAX_PROJECTS])
    records = []
    for p in projects:
        r = build(p, today, fold=False, period=period, keep_days=True)
        records.append((p, r, r.pop('_days')))

    people = list(_company_people(company)) if company is not None else []
    events = {}
    if company is not None:
        events = {d: rows for d, rows in _company_events(company, people).items() if _inside(d, window)}
    timeline, earlier = _company_timeline(records, events, detail, window, today)

    counts, changes = Counter(), {}
    for project, _, days in records:
        mine = Counter()
        for day in days.values():
            mine.update(day.counts())
        # A meeting's decisions are part of the meeting, not changes of their own.
        changes[project.id] = sum(n for key, n in mine.items() if key != 'meeting_decisions')
        counts.update(mine)
    for rows in events.values():
        for row in rows:
            counts.update(row['tally'])
    active = sum(1 for n in changes.values() if n)
    records = [(p, r) for p, r, _ in records]
    cap = LIST_ALL[detail]

    # Where every project stands, the ones with late work first.
    summary = [dict(r['project'], next_step=(r['next_steps'][0] if r['next_steps'] else None), changes=changes[p.id])
               for p, r in records]
    summary.sort(key=lambda p: (-p['late'], p['days_left'] if p['days_left'] is not None else 10 ** 6, p['name']))
    totals = {key: sum(p[key] for p in summary) for key in ('tasks', 'done', 'open', 'late')}

    def tagged(rows, project):
        return [dict(row, project=project.name, project_id=project.id) for row in rows]

    severity = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    decisions = sorted((d for p, r in records for d in tagged(r['decisions'], p)), key=lambda d: d['date'], reverse=True)
    late = sorted((t for p, r in records for t in tagged(r['due']['late'], p)), key=lambda t: t['days'] or 0)
    soon = sorted((t for p, r in records for t in tagged(r['due']['soon'], p)), key=lambda t: t['days'] or 0)
    risks = sorted((k for p, r in records for k in tagged(r['risks'], p)), key=lambda k: severity.get(k.get('severity'), 2))

    # Who is doing what, across every project.
    team = defaultdict(lambda: {'open': 0, 'done': 0, 'late': 0, 'projects': set()})
    for project, r in records:
        for member in r['team']:
            row = team[member['name']]
            for key in ('open', 'done', 'late'):
                row[key] += member[key]
            if member['open'] or member['done']:
                row['projects'].add(project.id)
    team_rows = sorted(({'name': n, 'open': c['open'], 'done': c['done'], 'late': c['late'],
                         'projects': len(c['projects'])} for n, c in team.items()),
                       key=lambda m: (m['name'] == 'No owner', -m['open'], m['name']))
    working = [u for u in people if u.is_active]
    busy = {m['name'] for m in team_rows if m['open']}
    idle = [_person(u) for u in working if _person(u) not in busy]

    next_steps = []
    for p in summary:
        if p['days_left'] is not None and p['days_left'] < 0 and p['open']:
            next_steps.append(f'{p["name"]}: the deadline has passed with {_plural(p["open"], "task")} still open.')
        elif p['late']:
            next_steps.append(f'{p["name"]}: {_plural(p["late"], "task")} late — agree new dates or move the deadline.')
    gone = {_person(u) for u in people if not u.is_active}
    for m in team_rows:
        m['left'] = m['name'] in gone
        if m['left'] and m['open']:
            next_steps.append(f'{m["name"]} has left the team but still has {_plural(m["open"], "open task")}: '
                              'hand them over (Users → their row).')
    no_owner = next((m for m in team_rows if m['name'] == 'No owner' and m['open']), None)
    if no_owner:
        next_steps.append(f'{_plural(no_owner["open"], "open task")} in {_plural(no_owner["projects"], "project")} '
                          f'{"has" if no_owner["open"] == 1 else "have"} no owner yet.')
    owners = [m for m in team_rows if m['name'] != 'No owner']
    average = sum(m['open'] for m in owners) / len(owners) if owners else 0
    loaded = [m for m in owners if m['open'] >= 6 and m['open'] >= 2 * average]
    if loaded and len(owners) > 1:
        next_steps.append(f'{loaded[0]["name"]} has {_plural(loaded[0]["open"], "open task")} across '
                          f'{_plural(loaded[0]["projects"], "project")}: consider sharing them out.')
    if idle and owners:
        shown = ', '.join(idle[:4]) + (f' and {len(idle) - 4} more' if len(idle) > 4 else '')
        next_steps.append(f'No open work yet: {shown}.')

    more_late = sum(r['due']['more_late'] for _, r in records) + max(0, len(late) - cap)
    more_soon = sum(r['due']['more_soon'] for _, r in records) + max(0, len(soon) - cap)
    return {
        'scope': 'all',
        'period': _period_info(period, window, _summary(period, counts, projects=active, since='the start')),
        'detail': detail,
        'overview': {
            'projects': len(summary), 'more_projects': max(0, all_projects.count() - len(projects)),
            'statuses': dict(Counter(p['status'] for p in summary)), 'people': len(working),
            **totals, 'pct_done': round(100 * totals['done'] / totals['tasks']) if totals['tasks'] else 0,
        },
        'projects': summary,
        'timeline': timeline,
        'earlier': earlier,
        'decisions': decisions[:cap],
        'due': {'late': late[:cap], 'soon': soon[:cap], 'more_late': more_late, 'more_soon': more_soon},
        'risks': risks[:cap],
        'team': team_rows[:TEAM_ALL],
        'more_people': max(0, len(team_rows) - TEAM_ALL),
        'next_steps': next_steps[:8 if detail == 'normal' else 5],
        'generated_at': timezone.now().isoformat(),
    }

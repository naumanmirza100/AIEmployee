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

    def bullets(self):
        # The project being made comes first, then the work added with it, then the rest of the day.
        out = [item for item in self.items if item[0] == 'created']
        rest = [item for item in self.items if item[0] != 'created']
        if self.created:
            owners = Counter(owner for _, owner in self.created if owner)
            text = f'{_plural(len(self.created), "task")} added: {_names([t for t, _ in self.created])}'
            if owners:
                text += ' — assigned to ' + ', '.join(f'{name} ({n})' for name, n in owners.most_common())
            unassigned = sum(1 for _, owner in self.created if not owner)
            if unassigned:
                text += f'; {unassigned} without an owner'
            out.append(('tasks', text))
        out.extend(rest)
        if self.handed:
            out.append(('assigned', 'Handed over: ' + '; '.join(f'“{t}” to {to}' for t, to in self.handed[:3])
                        + (f' and {len(self.handed) - 3} more' if len(self.handed) > 3 else '')))
        if self.moved_dates:
            if len(self.moved_dates) <= 2:
                for title, before, after in self.moved_dates:
                    out.append(('dates', f'“{title}” due date moved from {_shown(before)} to {_shown(after)}'))
            else:
                out.append(('dates', f'Due dates moved on {_plural(len(self.moved_dates), "task")}: '
                                     f'{_names([t for t, _, _ in self.moved_dates])}'))
        if self.priorities:
            out.append(('priority', f'Priority changed on {_plural(len(self.priorities), "task")}: '
                                    f'{_names([t for t, _ in self.priorities])}'))
        if self.completed:
            out.append(('done', f'Completed: {_names(self.completed, 4)}'))
        if self.deleted:
            out.append(('deleted', f'Removed: {_names(self.deleted)}'))
        if self.edited:
            parts = ', '.join(FIELD_WORDS.get(f, f.replace('_', ' ')) for f, _ in self.edited.most_common(3))
            out.append(('edit', f'Tasks edited ({parts})'))
        return out


def _timeline_and_decisions(project, tasks, entries, meetings, risks):
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
    days[_day(project.created_at)].items.append(
        ('created', 'Project created' + (f' by {created_by}' if created_by else '') + (f' — {", ".join(plan)}' if plan else '')))

    for e in entries:
        day, d = days[_day(e['at'])], e['details']
        moved_from, moved_to = d.get('from') or {}, d.get('to') or {}
        if e['model'] == 'Project' and e['action'] in ('project_updated', 'update_project'):
            for field in IMPORTANT_PROJECT_FIELDS:
                if field not in moved_to:
                    continue
                if field == 'deadline':
                    text = f'Deadline moved from {_shown(moved_from.get(field))} to {_shown(moved_to[field])}'
                elif field == 'start_date':
                    text = f'Start moved from {_shown(moved_from.get(field))} to {_shown(moved_to[field])}'
                elif field == 'name':
                    text = f'Renamed from “{moved_from.get(field)}” to “{moved_to[field]}”'
                else:
                    text = f'{field.title()} changed from {_shown(moved_from.get(field))} to {_shown(moved_to[field])}'
                day.items.append(('decision', text + (f' (by {e["by"]})' if e['by'] else '')))
                decisions.append({'date': _day(e['at']).isoformat(), 'text': text, 'source': 'Project change'})
            if not moved_to:
                important = [f for f in d.get('fields') or [] if f in IMPORTANT_PROJECT_FIELDS]
                if important:
                    day.items.append(('decision', 'Project ' + ', '.join(f.replace('_', ' ') for f in important)
                                      + ' changed' + (f' (by {e["by"]})' if e['by'] else '')))
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
        days[m['day']].items.append(('meeting', f'Meeting “{m["topic"]}”' + (': ' + ', '.join(bits) if bits else '')))
        for text in m['decisions']:
            decisions.append({'date': m['day'].isoformat(), 'text': text, 'source': f'Meeting “{m["topic"]}”'})

    for risk in risks:
        days[_day(risk.identified_at)].items.append(('risk', f'Risk logged: {risk.title} ({risk.get_severity_display()})'))
        if risk.resolved_at:
            days[_day(risk.resolved_at)].items.append(('done', f'Risk resolved: {risk.title}'))

    ordered = OrderedDict(sorted((d, v) for d, v in days.items() if d))
    timeline = [{'date': d.isoformat(), 'items': [{'kind': k, 'text': t} for k, t in v.bullets()[:MAX_ITEMS_PER_DAY]]}
                for d, v in ordered.items()]
    timeline = [day for day in timeline if day['items']]
    earlier = None
    if len(timeline) > MAX_DAYS:
        folded = timeline[:-MAX_DAYS]
        events = sum(len(day['items']) for day in folded)
        earlier = (f'{_plural(len(folded), "earlier day")} ({_shown(folded[0]["date"])} to '
                   f'{_shown(folded[-1]["date"])}): {_plural(events, "event")} not shown')
        # The day the project was made always stays at the top.
        timeline = [folded[0]] + timeline[-MAX_DAYS:] if folded[0]['date'] == _day(project.created_at).isoformat() \
            else timeline[-MAX_DAYS:]
    decisions.sort(key=lambda x: x['date'], reverse=True)
    return timeline, earlier, decisions[:MAX_LIST]


# ---------------------------------------------------------------------------
# Where the project stands
# ---------------------------------------------------------------------------

def _task_line(task, today):
    due = _day(task.due_date)
    return {'id': task.id, 'title': task.title, 'owner': _person(task.assignee) or 'No owner',
            'due': due.isoformat() if due else None, 'days': (due - today).days if due else None,
            'priority': task.priority, 'status': task.status}


def build(project, today=None):
    """The record of `project` as the Meeting Notes tab shows it."""
    today = today or timezone.localdate()
    tasks = list(Task.objects.filter(project=project).select_related('assignee').order_by('due_date', 'id'))
    entries = _entries(project, [t.id for t in tasks])
    meetings = _meetings(project)
    risks = list(ProjectRisk.objects.filter(project=project).order_by('identified_at'))
    timeline, earlier, decisions = _timeline_and_decisions(project, tasks, entries, meetings, risks)

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
                                  'source': f'Meeting “{m["topic"]}”'})
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

    return {
        'project': {
            'id': project.id, 'name': project.name, 'status': project.get_status_display(),
            'priority': project.get_priority_display(),
            'start': start.isoformat() if start else None, 'deadline': deadline.isoformat() if deadline else None,
            'days_left': (deadline - today).days if deadline else None,
            'tasks': len(tasks), 'done': done, 'open': len(open_tasks), 'late': len(late),
            'pct_done': pct_done, 'pct_time': pct_time,
        },
        'timeline': timeline,
        'earlier': earlier,
        'decisions': decisions,
        'due': {'late': [_task_line(t, today) for t in late[:MAX_LIST]],
                'soon': [_task_line(t, today) for t in soon[:MAX_LIST]],
                'more_late': max(0, len(late) - MAX_LIST), 'more_soon': max(0, len(soon) - MAX_LIST)},
        'meeting_actions': [dict(a, meeting=m['topic'], date=m['day'].isoformat())
                            for m in reversed(meetings[-2:]) for a in m['actions']][:MAX_LIST],
        'risks': risk_list[:MAX_LIST],
        'team': team,
        'next_steps': next_steps,
        'generated_at': timezone.now().isoformat(),
    }

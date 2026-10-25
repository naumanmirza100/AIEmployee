"""Keeping what Project Manager's AI tools produce, and turning it into project tasks.

Workflow & SOP's phase checklist, Meeting Notes' summary and action items, and Calendar & Schedule's plan were shown
once and lost: nothing was saved, nothing could be ticked off for good, and nothing became a task. They are kept in one
table (ProjectToolResult), and suggestions from either tool become tasks through the same task service every other
way of creating a task uses, so the usual checks (project dates, assignee in the company, audit entry) apply.
"""
import re
from datetime import date, datetime

from django.utils import timezone

from project_manager_agent.models import ProjectToolResult

CHECKLIST, MEETING_NOTES, SCHEDULE_PLAN = 'phase_checklist', 'meeting_notes', 'schedule_plan'
MEETING_NOTES_KEPT = 50          # per project; the oldest go first
MAX_TASKS_AT_ONCE = 50
_PRIORITIES = {'low', 'medium', 'high'}


# ---- phase checklists -----------------------------------------------------------------------------------------

def _item_text(item):
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(item.get('item') or item.get('text') or item.get('task') or '').strip()
    return ''


def save_checklist(project, phase, result, company_user):
    """Keep a freshly made checklist for this phase. Items still on it stay ticked if they were."""
    items = [i for i in (result.get('checklist') or []) if _item_text(i)]
    if not items:
        return None
    row = ProjectToolResult.objects.filter(project=project, kind=CHECKLIST, key=phase[:60]).first()
    was_done = {i['text'] for i in (row.data.get('items') or []) if i.get('done')} if row else set()
    data = {
        'phase': phase,
        'items': [{
            'text': _item_text(i),
            'priority': i.get('priority') if isinstance(i, dict) else None,
            'category': i.get('category') if isinstance(i, dict) else None,
            'done': _item_text(i) in was_done,
        } for i in items],
        'tips': [t for t in (result.get('tips') or []) if isinstance(t, str)][:20],
    }
    row, _ = ProjectToolResult.objects.update_or_create(
        project=project, kind=CHECKLIST, key=phase[:60], defaults={'data': data, 'created_by': company_user})
    return row


def checklist_payload(row):
    return {'id': row.id, 'phase': row.key, 'updated_at': row.updated_at.isoformat(), **row.data}


def set_item_done(row, index, done):
    items = row.data.get('items') or []
    if not 0 <= index < len(items):
        return False
    items[index]['done'] = bool(done)
    row.data['items'] = items
    row.save(update_fields=['data', 'updated_at'])
    return True


# ---- meeting notes --------------------------------------------------------------------------------------------

def save_meeting_notes(project, meeting_text, meeting_info, result, company_user):
    """Keep a meeting's notes and what was made of them on the project."""
    now = timezone.now()
    row = ProjectToolResult.objects.create(
        project=project, kind=MEETING_NOTES, key=now.strftime('%Y%m%d%H%M%S%f'), created_by=company_user,
        data={
            'topic': (meeting_info or {}).get('topic') or '',
            'date': (meeting_info or {}).get('date') or now.date().isoformat(),
            'text': meeting_text[:50000],
            'result': {k: v for k, v in result.items() if k != 'success'},
        })
    stale = list(ProjectToolResult.objects.filter(project=project, kind=MEETING_NOTES)
                 .order_by('-created_at').values_list('id', flat=True)[MEETING_NOTES_KEPT:])
    if stale:
        ProjectToolResult.objects.filter(id__in=stale).delete()
    return row


def meeting_notes_payload(row, with_text=False):
    out = {'id': row.id, 'saved_at': row.created_at.isoformat(), 'topic': row.data.get('topic') or '',
           'date': row.data.get('date'), 'result': row.data.get('result') or {}}
    if with_text:
        out['text'] = row.data.get('text') or ''
    return out


# ---- schedule plans -------------------------------------------------------------------------------------------

def save_schedule_plan(project, result, company_user):
    """Keep the project's latest plan; the one before it is replaced."""
    if not result.get('schedule'):
        return None
    data = {k: result.get(k) for k in ('schedule', 'conflicts', 'recommendations', 'overloaded_members',
                                         'unassigned_tasks', 'period') if result.get(k) is not None}
    row, _ = ProjectToolResult.objects.update_or_create(
        project=project, kind=SCHEDULE_PLAN, key='', defaults={'data': data, 'created_by': company_user})
    return row


def assignments_for(plan, user_id=None):
    """(date, assignment) pairs from a plan, only `user_id`'s when given, skipping days that are not dates."""
    out = []
    for day in plan.get('schedule') or []:
        try:
            when = date.fromisoformat(str(day.get('date'))[:10])
        except (TypeError, ValueError):
            continue
        for a in day.get('assignments') or day.get('tasks') or []:
            if not isinstance(a, dict):
                continue
            if user_id is not None and str(a.get('member_id')) != str(user_id):
                continue
            out.append((when, a))
    return out


# ---- suggestions into tasks -----------------------------------------------------------------------------------

def match_member(members, name):
    """The one member whose full name, first name or username is `name`; None when it is nobody or several."""
    wanted = re.sub(r'\s+', ' ', str(name or '')).strip().lower()
    if not wanted or wanted in ('tbd', 'unassigned', 'team', 'everyone', 'all'):
        return None
    found = [m for m in members
             if wanted in {(m.get_full_name() or '').strip().lower(), (m.first_name or '').strip().lower(),
                           (m.username or '').lower()}]
    return found[0].id if len(found) == 1 else None


_MONTHS = {m: i for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], start=1)}


def _due(raw):
    """A due date the suggestion gives as a real date: 2026-10-30, "Friday 30 October 2026" or "October 30, 2026".
    "Friday" or "TBD" alone are left out. Meeting notes give the written kind: the tasks made from them had no dates
    (PM demo rehearsal, 25 Oct 2026)."""
    text = str(raw or '').strip()
    try:
        if re.match(r'^\d{4}-\d{2}-\d{2}', text):
            return datetime.fromisoformat(text[:10]).date().isoformat()
        written = (re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b', text)
                   or re.search(r'\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b', text))
        if not written:
            return None
        parts = written.groups()
        day, month, year = (parts[0], parts[1], parts[2]) if parts[0].isdigit() else (parts[1], parts[0], parts[2])
        number = _MONTHS.get(month[:3].lower())
        return date(int(year), number, int(day)).isoformat() if number else None
    except ValueError:
        return None


def create_tasks(actor, project, items):
    """Create a task for each suggestion. Returns (created tasks, [problem per item that was not created])."""
    from core.tenancy import members_of
    from project_manager_agent import services as pm_services

    members = list(members_of(actor.company, company_user=actor.company_user)
                   .only('id', 'first_name', 'last_name', 'username'))
    created, problems = [], []
    for item in items[:MAX_TASKS_AT_ONCE]:
        title = str(item.get('title') or '').strip()[:255]
        if not title:
            continue
        priority = str(item.get('priority') or '').lower()
        data = {
            'project_id': project.id, 'title': title,
            'description': str(item.get('description') or '').strip(),
            'priority': priority if priority in _PRIORITIES else 'medium',
            'assignee_id': item.get('assignee_id') or match_member(members, item.get('assignee_name')),
            'due_date': _due(item.get('due')),
        }
        try:
            try:
                created.append(pm_services.create_task(actor, data))
            except pm_services.ServiceError as exc:
                if exc.code not in ('task_before_project_start', 'task_after_project_deadline'):
                    raise
                # The suggested date falls outside the project; the task is still worth having without it.
                created.append(pm_services.create_task(actor, {**data, 'due_date': None}))
        except pm_services.ServiceError as exc:
            problems.append({'title': title, 'message': exc.message})
    return created, problems

"""Deadlines a user states in a Project Pilot request, kept to in code.

"Create this project from the brief and keep its deadline only 10 days from
now": gpt-4o-mini planned the project to 7 December from the size of the brief,
and the review card offered that date (client test, 25 Oct 2026). Then "change
the deadline of this project to 10 days instead, and the tasks accordingly"
matched none of the update phrases, got a plain-text question back, and nothing
changed when the user typed "yes".

So a deadline is read here from the user's own words (never from an attached
document), and dates are fitted to it with plain arithmetic: the same request
always gets the same dates, and moving a deadline costs no AI call at all.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta

from project_manager_agent.drafts import _on_workday_between, _to_date

NUMBER_WORDS = {
    'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
    'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12,
    'fourteen': 14, 'fifteen': 15, 'twenty': 20, 'thirty': 30,
}
MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
MONTHS['sept'] = 9

_N = r'(\d{1,3}|' + '|'.join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r')'
_SPAN = re.compile(r'\b' + _N + r'[\s-]*(working[\s-]+|business[\s-]+)?(day|week|month)s?\b', re.I)
# A span counts as the deadline only with one of these close by: "3 days" in
# "each task takes 3 days" is not when the project ends.
_CUE_BEFORE = re.compile(
    r'\b(deadlines?|due|finish(ed)?|complet(e|ed|ion)|done|deliver(ed|y)?|ready|within|'
    r'wrap(ped)?\s+up|timeline|duration|end)\b', re.I)
_CUE_AFTER = re.compile(r'^\s*(from\s+(now|today)|deadline|timeline|at\s+(the\s+)?max(imum)?|at\s+most|max(imum)?\b)', re.I)
_IN_BEFORE = re.compile(r'\b(in|within)\s*$', re.I)

_MONTH = r'(' + '|'.join(sorted(MONTHS, key=len, reverse=True)) + r')\.?'
_DATES = [
    # 2026-11-04
    (re.compile(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b'), ('y', 'm', 'd')),
    # 4 Nov, 4th November 2026
    (re.compile(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?' + _MONTH + r'(?:,?\s+(\d{4}))?\b', re.I), ('d', 'mon', 'y')),
    # Nov 4, November 4th, 2026
    (re.compile(r'\b' + _MONTH + r'\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b', re.I), ('mon', 'd', 'y')),
    # 04/11/2026 — day first, as the review card shows dates
    (re.compile(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b'), ('d', 'm', 'y')),
]
_DATE_CUE = re.compile(r'\b(deadlines?|due|by|until|till|before|to|finish(ed)?|end|complet(e|ed|ion)|done|ready)\b[^.\n]{0,25}$', re.I)


def _count(word):
    word = word.lower()
    return int(word) if word.isdigit() else NUMBER_WORDS.get(word)


def _add_months(d, n):
    month = d.month - 1 + n
    year = d.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _add_workdays(d, n):
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _span_deadlines(text, today):
    found = []
    for match in _SPAN.finditer(text):
        before = text[max(0, match.start() - 45):match.start()]
        after = text[match.end():match.end() + 25]
        if not (_CUE_BEFORE.search(before) or _CUE_AFTER.search(after) or _IN_BEFORE.search(before)):
            continue
        n = _count(match.group(1))
        if not n:
            continue
        unit = match.group(3).lower()
        if unit == 'month':
            found.append(_add_months(today, n))
        elif unit == 'week':
            found.append(today + timedelta(weeks=n))
        else:
            found.append(_add_workdays(today, n) if match.group(2) else today + timedelta(days=n))
    return found


def _date_deadlines(text, today):
    found = []
    for pattern, order in _DATES:
        for match in pattern.finditer(text):
            if not _DATE_CUE.search(text[max(0, match.start() - 40):match.start()]):
                continue
            parts = dict(zip(order, match.groups()))
            try:
                month = MONTHS[parts['mon'].lower().rstrip('.')] if 'mon' in parts else int(parts['m'])
                year = int(parts['y']) if parts.get('y') else today.year
                when = date(year, month, int(parts['d']))
            except (KeyError, ValueError, TypeError):
                continue
            if not parts.get('y') and when < today:
                when = date(year + 1, month, when.day)
            found.append(when)
    return found


def stated_deadline(text, today=None):
    """The deadline the user asked for, as a date, or None.

    Reads "10 days from now", "in 2 weeks", "within 10 working days",
    "deadline of one month", "by 15 Nov", "deadline 2026-11-04". Counted from
    today: 25 Oct + 10 days is 4 Nov. With several ("first demo in 2 weeks,
    launch in 3 months") the project ends at the latest. Pass only the user's
    own words, never an attached document, whose dates are its own business."""
    if not text:
        return None
    today = today or date.today()
    return max(_date_deadlines(text, today) + _span_deadlines(text, today), default=None)


# ---------------------------------------------------------------------------
# Fitting dates into a deadline
# ---------------------------------------------------------------------------

def _rescale(d, anchor, old_end, new_end):
    """`d` moved so that [anchor, old_end] maps onto [anchor, new_end], on a weekday."""
    old_span = (old_end - anchor).days
    if old_span <= 0:
        moved = new_end
    else:
        moved = anchor + timedelta(days=round((d - anchor).days * (new_end - anchor).days / old_span))
    return _on_workday_between(moved, anchor, new_end)


def fit_new_project(actions, deadline, today=None):
    """Give the proposed new project the stated `deadline` and fit its tasks inside it.

    Task dates the agent planned past the deadline are squeezed in proportion,
    so their order and spacing survive. Returns True when a project was there
    to fit. Changes `actions` in place."""
    today = today or date.today()
    project = next((a for a in actions or [] if isinstance(a, dict) and a.get('action') == 'create_project'), None)
    if project is None or deadline is None:
        return False
    start = _to_date(project.get('start_date')) or today
    if start > deadline:
        start = min(today, deadline)
        project['start_date'] = start.isoformat()
    tasks = [a for a in actions if isinstance(a, dict) and a.get('action') == 'create_task'
             and str(a.get('project_id') or '').strip().lower() in ('', 'null', 'none')]
    dates = [d for d in (_to_date(t.get('due_date')) for t in tasks) if d]
    planned_end = max([d for d in [_to_date(project.get('deadline')) or _to_date(project.get('end_date'))] + dates if d],
                      default=None)
    project['deadline'] = deadline.isoformat()
    project.pop('end_date', None)
    project.pop('deadline_days', None)
    if planned_end and planned_end > deadline:
        for task in tasks:
            due = _to_date(task.get('due_date'))
            if due:
                task['due_date'] = _rescale(max(due, start), start, planned_end, deadline).isoformat()
    return True


# ---------------------------------------------------------------------------
# "Change the deadline of this project to 10 days, and the tasks accordingly"
# ---------------------------------------------------------------------------

_MOVE = re.compile(
    r'\b(change|changing|update|move|set|make|extend|shorten|reduce|bring|push|postpone|pull|cut|adjust|'
    r'reschedule|shift|keep)\b[^.?!\n]{0,60}\b(deadline|due\s+date|end\s+date|finish\s+date|timeline)', re.I)
_TASKS_TOO = re.compile(r'\b(tasks?|accordingly|everything|all\s+(the\s+)?dates|their\s+(dates|deadlines))\b', re.I)
_THIS_PROJECT = re.compile(r'\b(this|the|that|my|our|same)\s+project\b|\bproject\'?s\b|\bits\s+deadline\b', re.I)
_GENERIC_NAME_WORDS = {'project', 'the', 'and', 'for', 'new', 'app', 'system', 'platform', 'website', 'web',
                       'online', 'digital', 'mobile', 'portal', 'management', 'development', 'brief', 'pdf',
                       'docx', 'txt', 'attached', 'uploaded', 'file'}
_MAKES_NEW = re.compile(r'\b(create|new\s+project|build\s+a|make\s+a\s+project|from\s+(the\s+)?(pdf|file|document|brief))\b', re.I)


def asks_to_move_deadline(text):
    """Whether `text` asks to move an existing project's deadline (not to make a new project)."""
    return bool(text and _MOVE.search(text) and not _MAKES_NEW.search(text))


def project_meant(text, projects, selected=None, history=None):
    """The existing project `text` is about: the one picked in the chat's project box, the one it names,
    or — for "this project" — the most recent one named in the chat. None when it can't be told.
    `projects` is the caller's projects (a list of anything with `.name`), newest first."""
    if selected is not None:
        return selected
    named = [p for p in projects if p.name and p.name.strip().lower() in text.lower()]
    if len(named) == 1:
        return named[0]
    if named:
        return max(named, key=lambda p: len(p.name))
    if not _THIS_PROJECT.search(text):
        return None
    for message in reversed(list(history or [])):
        content = str((message or {}).get('content') or '').lower()
        hits = [p for p in projects if p.name and p.name.strip().lower() in content]
        if hits:
            return max(hits, key=lambda p: len(p.name))
        # Chats from before the review card named the project carry only "📎 Attached:
        # Zaiqa_Foods_Project_Brief.pdf": match the project whose name shares its words.
        words = set(re.findall(r'[a-z0-9]+', content.replace('_', ' ')))
        best = None
        for p in projects:
            name_words = [w for w in re.findall(r'[a-z0-9]+', (p.name or '').lower())
                          if len(w) > 2 and w not in _GENERIC_NAME_WORDS]
            shared = sum(1 for w in name_words if w in words)
            if shared >= 2 or (name_words and len(name_words[0]) >= 4 and name_words[0] in words):
                if best is None or shared > best[0]:
                    best = (shared, p)
        if best:
            return best[1]
    return None


def move_deadline(project, tasks, deadline, today=None, move_tasks=True):
    """The actions that give `project` the new `deadline`: an `update_project`, then an `update_task` for
    each open task whose due date has to move. With `move_tasks`, the remaining schedule (from today or
    the project's start, whichever is later) is stretched or squeezed onto the new deadline; without it,
    only tasks that would end up past the new deadline are moved."""
    today = today or date.today()
    actions = [{'action': 'update_project', 'project_id': project.id, 'project_name': project.name,
                'updates': {'deadline': deadline.isoformat()},
                'reasoning': f'Deadline moved to {deadline.isoformat()}, as asked.'}]
    open_tasks = [(t, _to_date(t.due_date)) for t in tasks if t.status != 'done' and t.due_date]
    anchor = max(_to_date(project.start_date) or today, today)
    if anchor > deadline:
        anchor = today
    ahead = [(t, d) for t, d in open_tasks if d >= anchor]
    old_end = max([d for _, d in ahead] + [d for d in [_to_date(project.effective_deadline)] if d and d >= anchor],
                  default=None)
    if not ahead or old_end is None:
        return actions
    if not move_tasks and old_end <= deadline:
        return actions
    for task, due in ahead:
        new_due = _rescale(due, anchor, old_end, deadline) if (move_tasks or due > deadline) else due
        if new_due != due:
            actions.append({'action': 'update_task', 'task_id': task.id, 'task_title': task.title,
                            'updates': {'due_date': new_due.isoformat()},
                            'reasoning': 'Moved with the project deadline.'})
    return actions


def deadline_change_request(text, projects, *, selected=None, history=None, today=None):
    """For a request to move an existing project's deadline, the actions to review and a sentence saying
    what they do; None when `text` isn't such a request or the project or date can't be told.
    Returns (actions, answer) or a (None, question) pair when only the project is unclear."""
    if not asks_to_move_deadline(text):
        return None
    today = today or date.today()
    deadline = stated_deadline(text, today)
    if deadline is None:
        return None
    # Read only now: every typed request passes through here, and few are about a deadline.
    project = project_meant(text, list(projects), selected=selected, history=history)
    if project is None:
        return None, ("Which project's deadline should I move? Pick it in the project box above the chat, "
                      "or name it in your message.")
    from core.models import Task
    tasks = list(Task.objects.filter(project=project).only('id', 'title', 'status', 'due_date'))
    actions = move_deadline(project, tasks, deadline, today=today, move_tasks=bool(_TASKS_TOO.search(text)))
    moved = len(actions) - 1
    when = deadline.strftime('%d %b %Y').lstrip('0')
    answer = f'Here\'s the change: "{project.name}" finishes on {when}'
    answer += (f', and {moved} task{"" if moved == 1 else "s"} move{"s" if moved == 1 else ""} to fit. '
               if moved else '. ')
    answer += 'Check it below — nothing changes until you confirm.'
    return actions, answer

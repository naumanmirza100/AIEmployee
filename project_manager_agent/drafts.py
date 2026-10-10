"""Find the details a proposed Project Pilot action is missing.

The pilot agent turns a sentence into `create_project` / `create_task` actions
and the view used to execute them the instant they arrived. If the sentence
never mentioned who a task was for, or when anything was due, the row was
created with those columns blank and nobody was told — the user found out later,
looking at an unassigned task with no deadline.

This module does not touch the database and does not talk to the model. It
reads the actions the agent already produced, reports which fields we consider
required are blank, and describes them in a shape the chat can render as a
form. The rules are deliberately plain data: what counts as missing should be
obvious from reading `REQUIRED`, and should not vary between two runs of the
same request.

Nothing here decides *whether* to create anything. The caller shows the gaps,
the user fills in what they want to fill in, and creation happens only after
they confirm — including confirming that they are happy to leave a gap blank.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

# Which fields we insist on being told about, per action, and how to ask.
#
#   field    the key on the action dict, and the key the answer comes back on
#   label    the question, phrased for someone who is not a developer
#   input    how the chat should render it: 'user' | 'date'
#
# `assignee_id` is first because it is the one people notice missing.
REQUIRED = {
    'create_task': [
        {'field': 'assignee_id', 'label': 'Who should do this?', 'input': 'user'},
        {'field': 'due_date', 'label': 'When is it due?', 'input': 'date'},
    ],
    'create_project': [
        {'field': 'deadline', 'label': 'When should the project finish?', 'input': 'date'},
    ],
}

# Some fields are written under more than one name by the agent; any of them
# counts as answered. Keyed by the canonical field name in REQUIRED.
ALIASES = {
    'deadline': ('deadline', 'end_date', 'deadline_days'),
}

# How to describe an action in the confirmation summary.
TITLE_KEYS = {
    'create_task': ('task_title', 'title'),
    'create_project': ('project_name', 'name'),
}


def _is_blank(value):
    """Treat None, '', whitespace and the string 'null' as not answered.

    The agent is an LLM: asked for JSON with a field it does not know, it will
    variously emit null, an empty string, or the four characters n-u-l-l.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in ('', 'null', 'none', 'n/a', 'tbd', 'unknown')
    return False


def _answered(action, field):
    """True when `field` (or any of its aliases) carries a real value."""
    for key in ALIASES.get(field, (field,)):
        if not _is_blank(action.get(key)):
            return True
    return False


def describe(action):
    """A short human label for an action, for the summary card."""
    for key in TITLE_KEYS.get(action.get('action'), ()):
        value = action.get(key)
        if not _is_blank(value):
            return str(value)
    return 'Untitled'


# ---------------------------------------------------------------------------
# Suggested deadlines
#
# When a deadline is missing we propose one rather than leave the date field
# empty. The rule is plain arithmetic so the same request always gets the same
# dates and anyone can check them:
#
#   * each task is worth `estimated_hours / 6` working days (rounded up), or
#     DEFAULT_TASK_DAYS when the agent gave no estimate;
#   * tasks are laid end to end in the order the agent listed them, from the
#     project's start;
#   * with a project deadline, that sequence is stretched or squeezed to fit
#     between start and deadline; without one, the deadline is where the
#     sequence ends (or later, if the agent itself dated a task beyond it).
#
# Each task also gets a `weight` — how far through the project it falls, 0..1 —
# so the chat can re-spread the dates when the user moves the project deadline.
# ---------------------------------------------------------------------------

TASK_HOURS_PER_DAY = 6
DEFAULT_TASK_DAYS = 3


def _to_date(value):
    """A `date` from a date, datetime, or ISO string; None for anything else."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and not _is_blank(value):
        text = value.strip()
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            try:
                return datetime.fromisoformat(text.replace('Z', '+00:00')).date()
            except ValueError:
                return None
    return None


def _next_workday(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _add_workdays(d, n):
    """The date `n` working days after `d` (Monday to Friday)."""
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _on_workday_between(d, start, end):
    """Pull a weekend date back to the Friday, without leaving [start, end]."""
    while d.weekday() >= 5 and d > start:
        d -= timedelta(days=1)
    return max(start, min(d, end))


def _task_days(action):
    try:
        hours = float(action.get('estimated_hours'))
    except (TypeError, ValueError):
        hours = 0
    if hours > 0:
        return max(1, math.ceil(hours / TASK_HOURS_PER_DAY))
    return DEFAULT_TASK_DAYS


def timeline(actions, today=None, project=None):
    """Suggest a deadline for the project and for every new task.

    `project` is the existing project the tasks are going into, when the user
    scoped the pilot to one (anything with `start_date`, `effective_deadline` /
    `deadline` and `id`). A `create_project` in the batch takes precedence.

    Returns::

        {
          'start': 'YYYY-MM-DD',
          'deadline': 'YYYY-MM-DD',
          'deadline_suggested': bool,   # we proposed it; the user did not
          'deadline_editable': bool,    # false for an existing project
          'tasks': {index: {'suggested': 'YYYY-MM-DD', 'weight': float}},
        }
    """
    today = today or date.today()
    new_project = next((a for a in actions
                        if isinstance(a, dict) and a.get('action') == 'create_project'), None)

    deadline = None
    if new_project is not None:
        start = _to_date(new_project.get('start_date')) or _next_workday(today + timedelta(days=1))
        deadline = _to_date(new_project.get('deadline')) or _to_date(new_project.get('end_date'))
        if deadline is None:
            try:
                days = int(new_project.get('deadline_days'))
                deadline = today + timedelta(days=days) if days > 0 else None
            except (TypeError, ValueError):
                pass
        editable = True
        project_id = None
    elif project is not None:
        start = _to_date(getattr(project, 'start_date', None)) or today
        deadline = (_to_date(getattr(project, 'effective_deadline', None))
                    or _to_date(getattr(project, 'deadline', None)))
        editable = False
        project_id = getattr(project, 'id', None)
    else:
        start = _next_workday(today + timedelta(days=1))
        editable = False
        project_id = None

    # Only the tasks this timeline is about: those joining the new project, or
    # the scoped existing one. A task aimed at some other project keeps
    # whatever date it has.
    tasks = []
    for index, action in enumerate(actions):
        if not isinstance(action, dict) or action.get('action') != 'create_task':
            continue
        target = action.get('project_id')
        if _is_blank(target) or (project_id is not None and str(target) == str(project_id)):
            tasks.append((index, action))

    suggested_deadline = deadline is None
    if suggested_deadline:
        total = sum(_task_days(a) for _, a in tasks) or DEFAULT_TASK_DAYS
        deadline = _add_workdays(start, total)
        # The agent sometimes dates a task itself; never propose a project
        # deadline that would make that task impossible to create.
        agent_dates = [d for d in (_to_date(a.get('due_date')) for _, a in tasks) if d]
        if agent_dates:
            deadline = max(deadline, max(agent_dates))
    deadline = max(deadline, start)

    span = (deadline - start).days
    total = sum(_task_days(a) for _, a in tasks) or 1
    out, cumulative = {}, 0
    for index, action in tasks:
        cumulative += _task_days(action)
        weight = cumulative / total
        given = _to_date(action.get('due_date'))
        if given is not None and span > 0:
            # Place an agent-given date on the same scale, so moving the
            # project deadline carries it along like the rest.
            weight = min(1.0, max(0.0, (given - start).days / span))
        suggested = _on_workday_between(start + timedelta(days=round(weight * span)),
                                        start, deadline)
        out[index] = {'suggested': suggested.isoformat(), 'weight': round(weight, 4)}

    return {
        'start': start.isoformat(),
        'deadline': deadline.isoformat(),
        'deadline_suggested': suggested_deadline,
        'deadline_editable': editable,
        'tasks': out,
    }


def only_project_id(actions):
    """The id of the one existing project every new task is going into, or None.

    "Create a task in ShopKart for Ahmed" arrives with ShopKart's id on the task
    and no project chosen in the picker. The review card then had no project to
    hold the dates against: it made up a deadline five working days away, showed
    it as the project's, and warned that the task "will be refused, dated outside
    the project" when the real deadline was weeks later.
    """
    tasks = [a for a in actions if isinstance(a, dict) and a.get('action') == 'create_task']
    if not tasks or any(isinstance(a, dict) and a.get('action') == 'create_project' for a in actions):
        return None
    targets = {str(a.get('project_id')).strip() for a in tasks if not _is_blank(a.get('project_id'))}
    if len(targets) != 1 or any(_is_blank(a.get('project_id')) for a in tasks):
        return None
    target = targets.pop()
    return int(target) if target.isdigit() else None


def leave_before(user, start, due):
    """The label of `user`'s first approved leave that overlaps [start, due]
    ("On leave 6–10 Oct"), or None. `user['on_leave']` is attached by the view
    from HR; without HR there is none, and nothing is flagged."""
    if not user or not due:
        return None
    for leave in user.get('on_leave') or ():
        first, last = _to_date(leave.get('start')), _to_date(leave.get('end'))
        if first and last and first <= due and last >= start:
            return leave.get('label') or 'On leave'
    return None


def inspect(actions, available_users=None, *, today=None, project=None):
    """Report what the proposed actions are missing.

    Returns a dict the view can hand straight to the client:

        needs_input      bool   — is anything missing at all
        no_users         bool   — there is nobody to assign work to
        items            list   — one per action, with its gaps
        summary          list   — every action, for the confirmation card
        timeline         dict   — suggested dates; see `timeline`
        rows             list   — every create, with the values the review
                                  form should start from
        users            list   — who work can be assigned to

    `available_users` is the list `_build_available_users` produces:
    ``[{'id', 'username', 'name', 'role'}, ...]``. When it is empty we still
    report the assignee gap, but flag `no_users` so the chat can say so plainly
    instead of showing an empty dropdown.

    `items` is only what is missing and decides whether the form appears at
    all. Once it does, `rows` lets the user review and change *everything* —
    assignee and deadline for every task, and the project deadline — not just
    the fields that happened to be blank.
    """
    users = list(available_users or [])
    no_users = len(users) == 0

    items, summary, any_gap = [], [], False
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        kind = action.get('action')
        rules = REQUIRED.get(kind)
        summary.append({'index': index, 'action': kind, 'title': describe(action)})
        if not rules:
            # Not a creation we gate on (updates, deletes, queries): leave it be.
            continue

        gaps = []
        for rule in rules:
            if _answered(action, rule['field']):
                continue
            gap = dict(rule)
            if rule['input'] == 'user':
                gap['options'] = users
                gap['no_options'] = no_users
            gaps.append(gap)

        if gaps:
            any_gap = True
            items.append({
                'index': index,
                'action': kind,
                'title': describe(action),
                'gaps': gaps,
            })

    plan = timeline(actions, today=today, project=project)
    missing_by_index = {item['index']: [g['field'] for g in item['gaps']] for item in items}

    rows = []
    leave_warnings = 0
    users_by_id = {str(u.get('id')): u for u in users}
    # Leave only matters once work can start: today, or the project's start.
    today_date = _to_date(today) or date.today()
    work_from = max(today_date, _to_date(plan.get('start')) or today_date)
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        kind = action.get('action')
        if kind == 'create_project':
            given = _to_date(action.get('deadline')) or _to_date(action.get('end_date'))
            rows.append({
                'index': index,
                'action': kind,
                'title': describe(action),
                # A `deadline_days` answer resolves to a date here, so the
                # confirm step always receives an explicit one.
                'deadline': given.isoformat() if given else plan['deadline'],
                'suggested': given is None and plan['deadline_suggested'],
                'missing': missing_by_index.get(index, []),
            })
        elif kind == 'create_task':
            given = _to_date(action.get('due_date'))
            dated = plan['tasks'].get(index)
            assignee = None if _is_blank(action.get('assignee_id')) else action.get('assignee_id')
            due = given or _to_date((dated or {}).get('suggested'))
            leave = leave_before(users_by_id.get(str(assignee)), work_from, due) if assignee else None
            if leave:
                leave_warnings += 1
            rows.append({
                'index': index,
                'action': kind,
                'title': describe(action),
                'assignee_id': None if _is_blank(action.get('assignee_id')) else action.get('assignee_id'),
                'due_date': given.isoformat() if given else (dated or {}).get('suggested'),
                'suggested': given is None and dated is not None,
                'weight': (dated or {}).get('weight'),
                'missing': missing_by_index.get(index, []),
                # The assignee is on approved leave before this is due. A
                # warning, not a block: the user decides.
                'leave': leave,
            })

    return {
        # Someone on leave is reason enough to review before creating, even
        # with nothing missing; otherwise the warning would never be seen.
        'needs_input': any_gap or leave_warnings > 0,
        'leave_warnings': leave_warnings,
        'no_users': no_users and any_gap,
        'items': items,
        'summary': summary,
        'timeline': plan,
        'rows': rows,
        'users': users,
    }


def chat_text(actions, answer=None, gaps=None):
    """The sentence to show above the review card. `gaps` is `inspect`'s
    result: missing details, people on leave, or neither — every proposal that
    changes anything is reviewed now, not only one with gaps.

    The agent's `answer` is often not prose at all but the JSON the actions
    were parsed out of. Passed through, it put a screen of raw JSON in the chat
    above the form. Use it only when it reads as a sentence; otherwise say in
    plain words what is about to happen.
    """
    on_leave_note = (" Some tasks go to people who are on leave before they're due — "
                     "check them below.") if gaps and gaps.get('leave_warnings') else ''
    text = (answer or '').strip()
    if text and text[0] not in '[{' and '"action"' not in text:
        return text + on_leave_note

    counts = {}
    for action in actions or []:
        if isinstance(action, dict) and action.get('action'):
            counts[action['action']] = counts.get(action['action'], 0) + 1

    def plural(n, noun):
        return '%d %s%s' % (n, noun, '' if n == 1 else 's')

    phrases = []
    for verb, words in (('create', 'create'), ('update', 'change'), ('delete', 'delete')):
        nouns = [plural(counts[f'{verb}_{noun}'], noun) for noun in ('project', 'task')
                 if counts.get(f'{verb}_{noun}')]
        if nouns:
            phrases.append('%s %s' % (words, ' and '.join(nouns)))
    what = ', '.join(phrases) or 'this'
    missing = bool(gaps and gaps.get('items'))
    on_leave = bool(gaps and gaps.get('leave_warnings'))
    if missing:
        text = ("Here's the plan: %s. A few details are missing — fill in what you "
                "know below, then confirm." % what)
        if on_leave:
            text += " Some tasks also go to people who are on leave before they're due."
        return text
    if on_leave:
        return ("Here's the plan: %s. Some tasks go to people who are on leave before "
                "they're due — check them below, then confirm." % what)
    return "Here's the plan: %s. Check it below — nothing changes until you confirm." % what


def apply_answers(actions, answers):
    """Merge the user's form answers back onto the proposed actions.

    `answers` is ``{action_index: {field: value}}`` as the chat form submits it,
    with indices possibly arriving as strings because they crossed JSON.

    The review form sends every field it shows, pre-filled or not, so an empty
    value is the user clearing it: the field (and any alias it was written
    under) is removed, never set to ''. That way clearing an agent-supplied
    date really clears it, and "leave it empty" stays empty.

    Returns a new list; the input is not modified.
    """
    # Only fields the form asks about may be touched, so a crafted payload
    # cannot rewrite an action into something else.
    allowed = {r['field'] for rules in REQUIRED.values() for r in rules}
    merged = [dict(a) if isinstance(a, dict) else a for a in actions]
    for raw_index, fields in (answers or {}).items():
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if not (0 <= index < len(merged)) or not isinstance(merged[index], dict):
            continue
        if not isinstance(fields, dict):
            continue
        for field, value in fields.items():
            if field not in allowed:
                continue
            if _is_blank(value):
                for key in ALIASES.get(field, (field,)):
                    merged[index].pop(key, None)
                continue
            merged[index][field] = value
    return merged

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


def inspect(actions, available_users=None):
    """Report what the proposed actions are missing.

    Returns a dict the view can hand straight to the client:

        needs_input      bool   — is anything missing at all
        no_users         bool   — there is nobody to assign work to
        items            list   — one per action, with its gaps
        summary          list   — every action, for the confirmation card

    `available_users` is the list `_build_available_users` produces:
    ``[{'id', 'username', 'name', 'role'}, ...]``. When it is empty we still
    report the assignee gap, but flag `no_users` so the chat can say so plainly
    instead of showing an empty dropdown.
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

    return {
        'needs_input': any_gap,
        'no_users': no_users and any_gap,
        'items': items,
        'summary': summary,
    }


def apply_answers(actions, answers):
    """Merge the user's form answers back onto the proposed actions.

    `answers` is ``{action_index: {field: value}}`` as the chat form submits it,
    with indices possibly arriving as strings because they crossed JSON. Blank
    answers are ignored rather than written, so "leave it empty" stays empty
    instead of becoming the empty string.

    Returns a new list; the input is not modified.
    """
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
            if _is_blank(value):
                continue
            # Only fields we actually asked about may be set this way, so a
            # crafted payload cannot rewrite the action into something else.
            if field not in {r['field'] for rules in REQUIRED.values() for r in rules}:
                continue
            merged[index][field] = value
    return merged

"""Revise a Project Pilot proposal the user rejected with a reason.

A review card can be rejected with a reason ("make it 15 days", "give the design tasks to Sara"), and Pilot then
proposes again. A new deadline in the reason is applied in code, like a stated deadline anywhere else
(pilot_deadlines); any other change goes to the model together with the proposal it made, which works the same
for a proposal from a typed request and one from an uploaded document (whose text the chat does not keep).
"""
from __future__ import annotations

import copy
import json
import logging
import re

from core.models import Task
from core.tenancy import projects_for_company_user
from project_manager_agent import pilot_deadlines

logger = logging.getLogger(__name__)


def _deadline_move(actions):
    """The update_project that moves a deadline, when the proposal is only a deadline move."""
    if any(isinstance(a, dict) and a.get('action') not in ('update_project', 'update_task') for a in actions):
        return None
    return next((a for a in actions if isinstance(a, dict) and a.get('action') == 'update_project'
                 and 'deadline' in (a.get('updates') or {})), None)


def revise(card, reason, *, company_user, available_users, today):
    """The revised proposal and a sentence for the chat, as (actions, answer); (None, answer) when it could not
    be revised. `card` is the rejected card's saved data (its `actions`)."""
    actions = copy.deepcopy([a for a in card.get('actions') or [] if isinstance(a, dict)])
    if not actions:
        return None, "There was nothing on that card to revise. Say what you'd like instead."
    deadline = pilot_deadlines.stated_deadline(reason, today, loose=True)
    when = deadline.strftime('%d %b %Y').lstrip('0') if deadline else ''

    move = _deadline_move(actions)
    if deadline and move:
        project = projects_for_company_user(company_user).filter(pk=move.get('project_id')).first()
        if project is not None:
            tasks = list(Task.objects.filter(project=project).only('id', 'title', 'status', 'due_date'))
            moved = pilot_deadlines.move_deadline(
                project, tasks, deadline, today=today,
                move_tasks=any(a.get('action') == 'update_task' for a in actions))
            n = len(moved) - 1
            return moved, (f'Revised: **{project.name}** now finishes on **{when}**'
                           + (f', and **{n} task{"" if n == 1 else "s"}** move{"s" if n == 1 else ""} to fit.' if n else '.')
                           + '\n\nCheck it below — nothing changes until you confirm.')

    if deadline and pilot_deadlines.fit_new_project(actions, deadline, today, stretch=True):
        return actions, (f'Revised: the project now finishes on **{when}**, with the tasks spread to fit.'
                         '\n\nCheck it below — nothing changes until you confirm.')

    from project_manager_agent.ai_agents import AgentRegistry
    agent = AgentRegistry.get_agent('project_pilot')
    agent.company_id = getattr(company_user, 'company_id', None)
    agent.agent_key_name = 'project_manager_agent'
    revised = agent.revise_actions(actions, reason, available_users=available_users, today=today)
    if not revised:
        return None, "I couldn't revise that plan. Say what you'd like changed, and I'll propose it again."
    # Ids the card was built on are kept whatever the model wrote, and what the new project came from.
    original = next((a for a in actions if a.get('action') == 'create_project'), None)
    for action in revised:
        if action.get('action') == 'create_project' and original is not None:
            for key in ('source_fingerprint', 'project_name'):
                if original.get(key) and not (key == 'project_name' and _renamed(reason)):
                    action[key] = original[key]
    return revised, 'Revised as you asked. Check it below — nothing changes until you confirm.'


def _renamed(reason):
    return bool(re.search(r'\b(name|call|rename|title)\b', reason or '', re.I))


def parse_actions(response):
    """The JSON array of actions in a model answer, or []."""
    text = (response or '').strip()
    fenced = re.search(r'```(?:json)?\s*([\s\S]+?)```', text)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find('['), text.rfind(']')
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return []
    return [a for a in data if isinstance(a, dict) and a.get('action')] if isinstance(data, list) else []

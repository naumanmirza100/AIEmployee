"""Read what a Project Pilot message asks for with one small AI call, before Pilot routes it.

Pilot used to route by lists of words: "create" meant a new project, "change deadline" an update. A message
without the listed words went down the wrong path: "change the deadline of this project" got a paragraph back
(client test, 25 Oct 2026), and typos ("projject", "dead line"), other phrasings ("push it back a week") and
Roman Urdu ("isko 10 din aage kar do") did not work at all. Now one short call reads the user's own words
(never an attached document) and says, as data, what is wanted, about which project and tasks, by when, and the
request restated in plain English. The word lists stay for when the call can't be made or isn't sure.

Kept out of it: requests the code already answers without the AI (a deadline move it can read, "yes" to a
question, a project button, a revision) — those never reach this call.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta

from django.conf import settings

from project_manager_agent.ai_agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

INTENTS = ('create_project', 'add_tasks', 'update_tasks', 'update_project', 'move_deadline', 'assign', 'delete',
           'question', 'not_supported', 'unclear')
ACTION_INTENTS = ('create_project', 'add_tasks', 'update_tasks', 'update_project', 'move_deadline', 'assign',
                  'delete')
MIN_CONFIDENCE = 0.6
MAX_PROJECTS = 40

PROMPT = """You read one message a user typed to a project-management assistant and say what they want. You do not
answer it. Messages can have typos, be short follow-ups in a conversation, or be in Roman Urdu or Hinglish.

TODAY: {today}
PROJECT THIS CONVERSATION IS ABOUT: {fixed}
THE USER'S PROJECTS (exact names):
{projects}

RECENT CONVERSATION (oldest first):
{history}

MESSAGE: "{message}"

Answer with ONLY a JSON object:
{{
  "intent": one of "create_project" | "add_tasks" | "update_tasks" | "update_project" | "move_deadline" | "assign" |
            "delete" | "question" | "not_supported" | "unclear",
  "project": exact name from the list above, or null,
  "target": "project" | "task" | null,
  "tasks": [task titles the message names] (["*"] for all tasks, [] for none),
  "people": [names of people the message names],
  "deadline": the new end date in the user's words, rewritten in English ("in 10 days", "by 15 Nov", "30 Nov") or null,
  "shift_days": whole days to move an existing date by ("a week later" = 7, "2 days earlier" = -2) or null,
  "move_tasks_too": true if the tasks' dates should move with the project's deadline,
  "english": the request restated as one clear English sentence,
  "confidence": 0 to 1
}}

How to choose the intent:
- create_project: make a NEW project (from a description or an attached document).
- add_tasks: add new tasks to an existing project.
- update_tasks: change existing TASKS — status ("done", "complete ho gaya"), priority, a task's due date, title,
  description, or taking a person off a task. One task or many.
- update_project: change the project's name, status (on hold, completed, active), priority or description.
- move_deadline: change the PROJECT's own deadline / end date, with or without its tasks. When the message names
  a task and its date ("testing and launch ki due date …"), that is update_tasks, not move_deadline — even for
  the last task of the project.
- assign: give existing tasks to a person, or move tasks from one person to another.
- delete: delete projects or tasks ("target" says which). Taking a person off a task is not delete.
- question: asks for information, a status, a list or advice; nothing should change.
- not_supported: asks for something a project tool cannot do (create user accounts, send emails, payments).
- unclear: you cannot tell what they want.

Examples:
- "push the deadline back a week" (conversation about a project) → move_deadline, shift_days 7
- "payment gateway wala task kal tak khatam karna hai" → update_tasks, tasks ["Payment gateway"]
- "remove Ali from the cart task" → update_tasks (take him off it), people ["Ali"]
- "Omar ko branch dashboard de do" → assign, tasks ["Branch dashboard"], people ["Omar"]
- "isko 20 din kar do" (about the deadline) → move_deadline, deadline "in 20 days"
- "isko 10 din aage kar do" / "10 din aur de do" → move_deadline, shift_days 10 (later than the deadline it has)
"this project", "it", "the project" mean the conversation's project when there is one. A message that only
answers the assistant ("yes", "the second one", "Afar") continues the request in the conversation: give that
request's intent."""


class PilotIntentReader(BaseAgent):
    """One short call that reads a Pilot message; logged under its own name in the AI usage log."""


def enabled():
    return bool(getattr(settings, 'PM_PILOT_AI_INTENT', True))


def _history_lines(history, limit=6):
    lines = []
    for message in list(history or [])[-limit:]:
        text = re.sub(r'\s+', ' ', str((message or {}).get('content') or '')).strip()
        if text:
            who = 'Assistant' if (message or {}).get('role') == 'assistant' else 'User'
            lines.append(f'{who}: {text[:300]}')
    return '\n'.join(lines) or '(none)'


def _parse(response):
    text = (response or '').strip()
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def read(message, *, company_user, projects, fixed_project=None, history=None, today=None):
    """What `message` asks for, as a dict (see PROMPT), with `project_id` resolved from the name; None when it
    can't be told (call refused by the model, unreadable answer, low confidence) — the word lists then route.
    An exhausted allowance or a missing key propagates, as for any Pilot call."""
    if not enabled() or not (message or '').strip():
        return None
    today = today or date.today()
    projects = list(projects)[:MAX_PROJECTS]
    prompt = PROMPT.format(
        today=today.isoformat(),
        fixed=f'"{fixed_project.name}"' if fixed_project is not None else 'none',
        projects='\n'.join(f'- {p.name}' for p in projects) or '- (no projects yet)',
        history=_history_lines(history),
        message=message.strip()[:2000].replace('"', "'"),
    )
    reader = PilotIntentReader()
    reader.company_id = getattr(company_user, 'company_id', None)
    reader.agent_key_name = 'project_manager_agent'
    try:
        # Room to finish: a reasoning model (Groq gpt-oss) thinks first, and a cut-off answer fails as JSON.
        response = reader._call_llm(prompt, temperature=0, max_tokens=1500, json_mode=True)
    except Exception as exc:
        from core.api_key_service import KeyServiceError
        if isinstance(exc, KeyServiceError):
            raise
        logger.warning('pilot_intent: the reading call failed (%s); routing by words', exc)
        return None
    data = _parse(response)
    if not data or data.get('intent') not in INTENTS:
        logger.info('pilot_intent: unreadable answer %r; routing by words', (response or '')[:200])
        return None
    try:
        confidence = float(data.get('confidence') or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < MIN_CONFIDENCE:
        logger.info('pilot_intent: %s at %.2f is too unsure; routing by words', data['intent'], confidence)
        return None
    by_name = {p.name.strip().lower(): p for p in projects}
    named = by_name.get(str(data.get('project') or '').strip().lower())
    # What the message named, and what it is about: a conversation's own project wins (it is fixed).
    data['named_project_id'] = named.id if named is not None else None
    data['project_id'] = fixed_project.id if fixed_project is not None else data['named_project_id']
    data['tasks'] = [str(t) for t in data.get('tasks') or [] if str(t).strip()]
    logger.info('pilot_intent: %s (project %s, %.2f) for %r', data['intent'], data['project_id'], confidence,
                message[:120])
    return data


def new_deadline(intent, project, today=None):
    """The new deadline a move_deadline reading gives for `project`: its date in words, or a shift of the
    current deadline. None when neither can be told."""
    from project_manager_agent import pilot_deadlines
    from project_manager_agent.drafts import _to_date
    today = today or date.today()
    # A shift first: "isko 10 din aage kar do" moves the deadline it has, and the words alone ("10 days
    # later") would have been read as 10 days from today.
    try:
        shift = int(intent.get('shift_days'))
    except (TypeError, ValueError):
        shift = 0
    current = _to_date(getattr(project, 'effective_deadline', None)) if project is not None else None
    if shift and current:
        return current + timedelta(days=shift)
    words = intent.get('deadline')
    if words:
        return pilot_deadlines.stated_deadline(str(words), today, loose=True)
    return None

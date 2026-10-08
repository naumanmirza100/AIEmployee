"""Project Pilot from a document — run by the Celery task behind the upload
endpoint (`api/views/pm_agent.py::project_pilot_from_file`).

Reads the document's text into the Pilot agent and returns what it proposes:
a question when the instruction is unclear or a similar project exists, and
otherwise the same review card as a typed Pilot request. Nothing is created
here; `project_pilot_confirm` makes what the user confirms.
"""
from __future__ import annotations

import json
import logging
import re
from django.shortcuts import get_object_or_404
from django.utils import timezone

from core.models import Project, Task
from core.tenancy import projects_for_company_user
from project_manager_agent.ai_agents import AgentRegistry

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Confirmation gate — decide whether to execute the LLM's proposed actions
# outright or ask the user first.
# --------------------------------------------------------------------------

_EXPLICIT_CREATION_VERBS = frozenset([
    'create', 'make', 'start', 'generate', 'add', 'build', 'plan',
    'setup', 'set up', 'kick off', 'kickoff', 'initiate', 'convert',
    'turn into', 'break down', 'break into', 'extract tasks',
    'new project', 'new task',
])


def _has_explicit_intent(user_prompt: str) -> bool:
    """True when the user's typed instruction contains an unambiguous verb
    that authorises creating projects/tasks."""
    if not user_prompt:
        return False
    low = user_prompt.lower()
    return any(v in low for v in _EXPLICIT_CREATION_VERBS)


def _find_similar_projects(proposed_name: str, existing_projects, threshold: float = 0.7):
    """Find existing projects whose name is similar to ``proposed_name``
    above ``threshold`` (Levenshtein-ish ratio, 0-1). Uses stdlib ``difflib``
    so no new dependency."""
    from difflib import SequenceMatcher
    if not proposed_name:
        return []
    prop = proposed_name.strip().lower()
    out = []
    for p in existing_projects or []:
        existing_name = (p.get('name') or '').strip().lower()
        if not existing_name:
            continue
        ratio = SequenceMatcher(None, prop, existing_name).ratio()
        # Also flag when proposed contains existing as a substring (or vice versa)
        # — SequenceMatcher misses very-different-length pairs like
        # "Website" vs "Website Redesign Q1 2026".
        substring_hit = prop in existing_name or existing_name in prop
        if ratio >= threshold or substring_hit:
            out.append({
                'existing_id': p.get('id'),
                'existing_name': p.get('name'),
                'similarity': round(ratio, 2),
                'substring_match': bool(substring_hit),
            })
    # Sort by similarity descending, cap at 3
    out.sort(key=lambda x: x['similarity'], reverse=True)
    return out[:3]


def _check_needs_confirmation(user_prompt, actions, existing_projects):
    """Should the pipeline ASK the user before executing the LLM's proposed
    actions? Returns a ``confirmation_required`` dict if yes, or None if the
    pipeline should proceed with execution.

    Two reasons we ask:

    * **Implicit intent** — the user uploaded a document without an explicit
      instruction ("create a project", "extract tasks", …). The old flow
      would silently create a project anyway; users complained.
    * **Duplicate risk** — a proposed project's name is very similar to an
      existing project the user already owns. Better to check than to
      accidentally create a near-duplicate.

    We only gate on ``create_project`` actions. ``create_task`` on an existing
    project the user explicitly named is fine to auto-execute.
    """
    create_proj_actions = [a for a in actions if isinstance(a, dict) and a.get('action') == 'create_project']
    if not create_proj_actions:
        return None

    reasons = []
    is_explicit = _has_explicit_intent(user_prompt or '')
    if not is_explicit:
        reasons.append({
            'type': 'implicit_intent',
            'message': (
                "You uploaded a document without an explicit instruction, "
                "and the assistant was about to create a new project from it. "
                "What would you like to do?"
            ),
        })

    # Duplicate detection across all proposed projects
    all_similar = []
    for a in create_proj_actions:
        proposed = a.get('project_name') or ''
        hits = _find_similar_projects(proposed, existing_projects)
        for h in hits:
            h['proposed_name'] = proposed
            all_similar.append(h)
    # Dedupe by existing_id
    seen = set()
    deduped_similar = []
    for h in all_similar:
        eid = h.get('existing_id')
        if eid in seen:
            continue
        seen.add(eid)
        deduped_similar.append(h)

    if deduped_similar:
        top = deduped_similar[0]
        reasons.append({
            'type': 'similar_project_exists',
            'message': (
                f"A project called '{top['existing_name']}' already exists — "
                f"very similar to the proposed '{top['proposed_name']}'. "
                "Add these tasks there instead, or create a separate project?"
            ),
        })

    if not reasons:
        return None

    # ---- Build the options offered to the user ----
    options = []
    if deduped_similar:
        top = deduped_similar[0]
        options.append({
            'id': 'update_existing',
            'label': f"Add tasks to existing project '{top['existing_name']}'",
            'hint': f"Project #{top['existing_id']}",
            'existing_project_id': top['existing_id'],
            'existing_project_name': top['existing_name'],
        })
    options.append({
        'id': 'create_new',
        'label': "Create a new project anyway",
        'hint': f"'{create_proj_actions[0].get('project_name', 'New Project')}'",
    })
    options.append({
        'id': 'summarize',
        'label': "Just summarise the document",
        'hint': "No projects or tasks created",
    })
    options.append({
        'id': 'extract_tasks_only',
        'label': "List the tasks without creating anything",
        'hint': "See what would be created first",
    })
    options.append({
        'id': 'cancel',
        'label': "Cancel",
        'hint': "Discard this upload",
    })

    # Compact summary of what the LLM was about to do — shown in the card.
    proposed_summary_parts = []
    for a in create_proj_actions:
        proposed_summary_parts.append(f"Create project '{a.get('project_name', 'Unnamed')}'")
    task_count = sum(1 for a in actions if isinstance(a, dict) and a.get('action') == 'create_task')
    if task_count:
        proposed_summary_parts.append(f"Add {task_count} task(s)")
    proposed_summary = '. '.join(proposed_summary_parts) + '.' if proposed_summary_parts else ''

    return {
        'needs_confirmation': True,
        'reasons': reasons,
        'similar_projects': deduped_similar,
        'proposed_actions_summary': proposed_summary,
        'proposed_actions': create_proj_actions[:3],  # cap to keep payload small
        'options': options,
    }


def run_project_pilot_pipeline(*, company_user, extracted_text, file_name,
                               user_prompt='', project_id=None,
                               chat_history=None, skip_confirmation=False):
    """Run the LLM + action-execution pipeline for a Project Pilot upload.

    Args (all keyword-only):
      company_user       — CompanyUser instance who owns the request.
      extracted_text     — text already extracted from the uploaded file.
      file_name          — original client-side filename (used in the prompt).
      user_prompt        — the user's typed instruction alongside the file.
      project_id         — optional scope; int or None.
      chat_history       — list of prior chat turns [{role, content}, ...].

    Returns a dict with keys:
      answer, action_results, cannot_do, extracted_text_preview.
    Raises on unrecoverable errors — caller (Celery task) catches and marks
    the job failed.
    """
    # Local imports to break the circular dependency with `api.views.pm_agent`
    # (which imports this module for the endpoint refactor).
    from api.views.pm_agent import (
        _build_available_users,
        _build_user_assignments,
        _get_allowed_user_ids_for_only_n_users,
    )
    company = company_user.company
    # Combine the user's typed instruction with the document text. Sending
    # just the raw file contents as the question used to confuse the agent
    # ("could you clarify what you'd like to convert?") because the agent
    # had no signal of intent — only walls of PDF text. The frontend now
    # sends a `prompt` field; we wrap the document content in a clear
    # delimiter so the agent can tell instruction from attachment.
    user_prompt = (user_prompt or "").strip()
    if user_prompt:
        question = (
            f"{user_prompt}\n\n"
            f"--- Attached document: {file_name} ---\n"
            f"{extracted_text}\n"
            f"--- end of document ---"
        )
    else:
        # No instruction provided — fall back to old behaviour but still
        # tag the content so the agent treats it as an attachment.
        question = (
            f"The user attached a document named '{file_name}' "
            f"without an explicit instruction. Read its contents and ask what "
            f"they'd like to do with it (e.g. convert to project, summarise, "
            f"extract tasks).\n\n"
            f"--- Attached document ---\n{extracted_text}\n--- end of document ---"
        )
    # project_id already passed in as a param
    
    # Reuse the same logic as project_pilot function
    project = None
    company = company_user.company

    # Filter projects created by this company user
    all_projects = projects_for_company_user(company_user)
    all_tasks = Task.objects.filter(project__in=projects_for_company_user(company_user)).select_related("project")

    if project_id:
        try:
            project_id = int(project_id)
            project = get_object_or_404(projects_for_company_user(company_user), id=project_id)
        except (ValueError, Project.DoesNotExist):
            project = None

    if project:
        tasks = Task.objects.filter(project=project).select_related("assignee")
        context = {
            "project": {
                "id": project.id,
                "name": project.name,
                "status": project.status,
                "priority": project.priority,
                "description": project.description,
                "deadline": project.deadline.isoformat() if project.deadline else None,
            },
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status,
                    "priority": t.priority,
                    "description": t.description,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "deadline": t.due_date.isoformat() if t.due_date else None,
                }
                for t in tasks
            ],
        }
    else:
        context = {
            "all_projects": [
                {
                    "id": p.id,
                    "name": p.name,
                    "status": p.status,
                    "priority": p.priority,
                    "tasks_count": p.tasks.count(),
                    "description": p.description[:100] if p.description else "",
                }
                for p in all_projects
            ],
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status,
                    "priority": t.priority,
                    "description": t.description,
                    "project_name": t.project.name,
                }
                for t in all_tasks[:10]
            ],
        }

    available_users = _build_available_users(project_id=project_id, project=project, company_user=company_user)
    context["user_assignments"] = _build_user_assignments(
        available_users, project_id=project_id, all_tasks=all_tasks, owner=None
    )

    chat_history = list(chat_history or [])
    agent = AgentRegistry.get_agent("project_pilot")
    # Route LLM call through the company key/quota resolver. Resolver will
    # raise QuotaExhausted (402) or NoKeyAvailable (403) on hard-block —
    # core/drf_exceptions converts those to clean JSON responses.
    agent.company_id = getattr(company_user, 'company_id', None)
    agent.agent_key_name = 'project_manager_agent'
    result = agent.process(question=question, context=context, available_users=available_users, chat_history=chat_history)
    if result.get("cannot_do"):
        return {
            "answer": result.get("answer", ""),
            "action_results": [],
            "cannot_do": result.get("cannot_do", ""),
            "extracted_text_preview": extracted_text[:200] + "..." if len(extracted_text) > 200 else extracted_text,
        }

    actions = result.get("actions") or []
    if result.get("action"):
        actions = [result["action"]]
    
    # If no actions found, try parsing from answer field (reuse same logic from project_pilot)
    if len(actions) == 0 and result.get("answer"):
        answer_str = result.get("answer", "").strip()
        if answer_str and "[" in answer_str:
            try:
                import re
                cleaned_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', answer_str)
                
                # CRITICAL FIX: Fix reversed brackets at the end IMMEDIATELY before any processing
                # The AI sometimes generates: ... ]} instead of ... }]
                # We need to fix this FIRST, before bracket matching
                cleaned_str_stripped = cleaned_str.rstrip()
                if cleaned_str_stripped.endswith(']}'):
                    # Replace ]} with }] at the end - preserve any trailing whitespace/newlines
                    trailing_whitespace = cleaned_str[len(cleaned_str_stripped):]
                    cleaned_str = cleaned_str_stripped[:-2] + '}]' + trailing_whitespace
                    logger.warning("Fixed reversed closing brackets at end: ]} -> }]")
                # Also check for ] followed by } on separate lines
                elif cleaned_str_stripped.endswith(']\n}') or cleaned_str_stripped.endswith(']\r\n}'):
                    cleaned_str = cleaned_str_stripped.replace(']\n}', '}]\n').replace(']\r\n}', '}]\r\n')
                    logger.warning("Fixed reversed closing brackets with newline: ]\\n} -> }]\\n")
                elif cleaned_str_stripped.endswith(']\n}') or cleaned_str_stripped.endswith(']\r\n}'):
                    # Handle case where ] and } are on separate lines
                    cleaned_str = cleaned_str_stripped.replace(']\n}', '}]\n').replace(']\r\n}', '}]\r\n')
                    logger.warning("Fixed reversed closing brackets with newline: ]\\n} -> }]\\n")
                
                first_bracket = cleaned_str.find('[')
                if first_bracket < 0:
                    first_bracket = 0
                
                bracket_count = 0
                brace_count = 0
                end_pos = -1
                for i in range(first_bracket, len(cleaned_str)):
                    char = cleaned_str[i]
                    if char == '[':
                        bracket_count += 1
                    elif char == ']':
                        bracket_count -= 1
                    elif char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                    
                    if bracket_count == 0 and brace_count == 0 and char == ']':
                        end_pos = i + 1
                        break
                
                # If we couldn't find matching bracket, try to fix common issues
                if end_pos <= first_bracket:
                    # Check if it ends with ]} (reversed brackets) or incomplete
                    if cleaned_str.rstrip().endswith(']}'):
                        # Fix reversed brackets
                        cleaned_str = cleaned_str.rstrip()[:-2] + '}]'
                        end_pos = len(cleaned_str)
                    elif cleaned_str.rstrip().endswith(']'):
                        # Might be missing closing brace
                        # Count open vs close braces
                        open_braces = cleaned_str[first_bracket:].count('{')
                        close_braces = cleaned_str[first_bracket:].count('}')
                        if open_braces > close_braces:
                            # Add missing closing braces
                            cleaned_str = cleaned_str.rstrip()[:-1] + '}' * (open_braces - close_braces) + ']'
                            end_pos = len(cleaned_str)
                
                # If we couldn't find matching bracket, try to fix common issues
                if end_pos <= first_bracket:
                    # Check if it ends with ]} (reversed brackets) or incomplete
                    if cleaned_str.rstrip().endswith(']}'):
                        # Fix reversed brackets - always fix ]} to }]
                        cleaned_str = cleaned_str.rstrip()[:-2] + '}]'
                        end_pos = len(cleaned_str)
                        logger.warning("Fixed reversed closing brackets in JSON (]})")
                    elif cleaned_str.rstrip().endswith(']'):
                        # Might be missing closing brace
                        # Count open vs close braces
                        open_braces = cleaned_str[first_bracket:].count('{')
                        close_braces = cleaned_str[first_bracket:].count('}')
                        if open_braces > close_braces:
                            # Add missing closing braces
                            cleaned_str = cleaned_str.rstrip()[:-1] + '}' * (open_braces - close_braces) + ']'
                            end_pos = len(cleaned_str)
                
                if end_pos > first_bracket:
                    json_str = cleaned_str[first_bracket:end_pos]
                    
                    # Fix reversed brackets if present - ALWAYS fix if ends with ]}
                    # This is a common AI error where brackets are reversed
                    if json_str.rstrip().endswith(']}'):
                        json_str = json_str.rstrip()[:-2] + '}]'
                        logger.warning("Fixed reversed closing brackets in JSON: ]} -> }]")
                    
                    # Try to parse the extracted JSON
                    try:
                        parsed_actions = json.loads(json_str)
                        if isinstance(parsed_actions, list):
                            actions = parsed_actions
                            logger.info(f"Parsed {len(actions)} actions from answer field")
                    except json.JSONDecodeError as parse_err:
                        logger.warning(f"Failed to parse extracted JSON: {parse_err}")
                        # Fallback: Try to extract individual JSON objects if the array is malformed
                        try:
                            import re
                            json_objects = []
                            # More robust pattern to find JSON objects
                            pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
                            for match in re.finditer(pattern, cleaned_str):
                                try:
                                    obj = json.loads(match.group(0))
                                    json_objects.append(obj)
                                except json.JSONDecodeError:
                                    continue
                            if json_objects:
                                actions = json_objects
                                logger.info(f"Parsed {len(actions)} actions by extracting individual JSON objects")
                        except Exception as e2:
                            logger.warning(f"Fallback JSON object extraction also failed: {e2}")
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse answer as JSON: {e}")

    # Only run round-robin when user asked for "assign to ALL" and did NOT say "only N users"
    if not isinstance(actions, list):
        actions = []
    import re as _re_file
    _q_lower_file = question.lower()
    _only_n_users_file = _re_file.search(r"only\s+\d+\s+users?", _q_lower_file)
    _assign_to_all_phrases_file = [
        "assign to all", "assign to all available", "assign to all users",
        "distribute to all", "assign tasks to all", "all available users",
        "all developers", "all users", "assign the tasks to all",
    ]
    _wants_assign_to_all_file = any(p in _q_lower_file for p in _assign_to_all_phrases_file)
    if _wants_assign_to_all_file and not _only_n_users_file and available_users:
        _create_tasks = [a for a in actions if isinstance(a, dict) and a.get("action") == "create_task"]
        _unassigned = [a for a in _create_tasks if not a.get("assignee_id")]
        if _unassigned:
            _user_ids = [u["id"] for u in available_users]
            for i, action_data in enumerate(_unassigned):
                action_data["assignee_id"] = _user_ids[i % len(_user_ids)]
            logger.info(f"Backend fallback (from_file): assigned {len(_unassigned)} tasks round-robin to {len(_user_ids)} users")
    
    _allowed_ids_file = _get_allowed_user_ids_for_only_n_users(question, available_users)
    if _allowed_ids_file is not None:
        _create_tasks_f = [a for a in actions if isinstance(a, dict) and a.get("action") == "create_task"]
        for i, action_data in enumerate(_create_tasks_f):
            action_data["assignee_id"] = _allowed_ids_file[i % len(_allowed_ids_file)]
        logger.info(f"Backend enforcement (from_file): restricted to only {len(_allowed_ids_file)} users")

    # ---- Confirmation gate --------------------------------------------
    # If the caller hasn't explicitly opted out (e.g. this is the follow-up
    # after the user picked an option), check whether we should ASK before
    # executing. Two triggers: implicit user intent + duplicate project name.
    if not skip_confirmation:
        existing_projects_list = [
            {'id': p.id, 'name': p.name, 'description': (p.description or '')[:200]}
            for p in all_projects
        ]
        confirmation = _check_needs_confirmation(
            user_prompt=user_prompt,
            actions=actions,
            existing_projects=existing_projects_list,
        )
        if confirmation:
            # Compose a natural-language answer that summarises what the LLM
            # would have done + asks the question. This message is what the
            # user sees in the chat AND what the LLM sees on the follow-up
            # via chat history, so it needs enough context that a follow-up
            # like "yes, add to existing" can regenerate the same tasks.
            summary_lines = []
            summary_lines.append("Before I create anything, I want to check with you.")
            summary_lines.append("")
            if confirmation.get('proposed_actions_summary'):
                summary_lines.append(f"**What I was about to do:** {confirmation['proposed_actions_summary']}")
                summary_lines.append("")
            # List proposed tasks so a follow-up ("yes, do it") has context.
            create_task_actions = [a for a in actions if isinstance(a, dict) and a.get('action') == 'create_task']
            if create_task_actions:
                summary_lines.append("**Proposed tasks:**")
                for i, ta in enumerate(create_task_actions[:12], start=1):
                    ttl = ta.get('task_title') or ta.get('title') or '(untitled)'
                    prio = ta.get('priority')
                    prio_txt = f" [{prio}]" if prio else ''
                    summary_lines.append(f"  {i}. {ttl}{prio_txt}")
                if len(create_task_actions) > 12:
                    summary_lines.append(f"  … and {len(create_task_actions) - 12} more")
                summary_lines.append("")
            for r in confirmation.get('reasons', []):
                summary_lines.append(f"⚠ {r.get('message')}")
            summary_lines.append("")
            summary_lines.append("Pick an option below to continue.")
            answer_text = "\n".join(summary_lines)
            logger.info("Project Pilot: confirmation gate triggered (%d reasons, %d similar projects)",
                        len(confirmation.get('reasons') or []),
                        len(confirmation.get('similar_projects') or []))
            return {
                "answer": answer_text,
                "action_results": [],
                "cannot_do": "",
                "confirmation_required": confirmation,
                "extracted_text_preview": extracted_text[:200] + "..." if len(extracted_text) > 200 else extracted_text,
            }

    # ---- Review ---------------------------------------------------------------
    # Nothing is written here, as for a typed Pilot request (see
    # api.views.pm_agent.project_pilot): the proposal comes back as a review
    # card, and `project_pilot_confirm` makes exactly what the user confirms.
    # This used to create every project and task at once whenever the
    # instruction was explicit and no similar project existed.
    preview = extracted_text[:200] + "..." if len(extracted_text) > 200 else extracted_text
    from project_manager_agent import drafts, pilot_review
    from project_manager_agent.services.actor import DashboardActor
    if pilot_review.proposes_changes(actions):
        gaps = drafts.inspect(actions, available_users, today=timezone.localdate(), project=project)
        answer = drafts.chat_text(actions, result.get("answer"), gaps)
        draft = {
            "answer": answer,
            "actions": actions,
            "project_id": project.id if project else None,
            **gaps,
            "changes": pilot_review.changes(actions, DashboardActor(company_user)),
            "review": True,
        }
        logger.info("Project Pilot pipeline: %d proposed actions sent for review", len(actions))
        return {"answer": answer, "action_results": [], "cannot_do": "", "draft": draft,
                "extracted_text_preview": preview}

    answer_text = (result.get("answer") or "").strip()
    if answer_text.startswith("[") or answer_text.startswith("{"):
        answer_text = "I didn't find anything to create or change in that document."
    return {"answer": answer_text, "action_results": [], "cannot_do": "", "extracted_text_preview": preview}

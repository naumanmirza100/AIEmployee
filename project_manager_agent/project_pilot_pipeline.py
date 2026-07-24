"""Project Pilot pipeline — extracted from `api/views/pm_agent.py::project_pilot_from_file`
so it can be called from both the (now-async) HTTP endpoint and the Celery
task that actually runs the LLM extraction + project/task creation.

The 500-line pipeline is preserved verbatim from the original view — same
JSON parsing, same bracket-fixing heuristics, same two-pass action execution
— just with the outer `request`/`Response` scaffolding stripped out so it
takes primitives and returns a dict.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone

from core.models import Project, Task
from project_manager_agent.ai_agents import AgentRegistry

logger = logging.getLogger(__name__)


def run_project_pilot_pipeline(*, company_user, extracted_text, file_name,
                               user_prompt='', project_id=None,
                               chat_history=None):
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
        _get_project_owner,
        _assignee_display,
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
    all_projects = Project.objects.filter(created_by_company_user=company_user)
    all_tasks = Task.objects.filter(project__created_by_company_user=company_user).select_related("project")

    if project_id:
        try:
            project_id = int(project_id)
            project = get_object_or_404(Project, id=project_id, created_by_company_user=company_user)
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

    # Process actions (reuse same logic from project_pilot)
    action_results = []
    created_projects = {}  # Map to track created projects for task assignment
    
    # First pass: Create all projects
    for action in actions:
        if action.get("action") == "create_project":
            try:
                # Get default owner (required field)
                from django.contrib.auth.models import User
                default_owner = _get_project_owner(company_user)
                if not default_owner:
                    action_results.append({
                        "action": "create_project",
                        "success": False,
                        "error": "No default owner available. Please ensure at least one user exists in the system.",
                    })
                    continue
                
                # Handle industry field - it's a ForeignKey, so we need to handle it properly
                industry_value = action.get("industry", "")
                industry_instance = None
                if industry_value:
                    # Try to find industry by name or slug
                    from core.models import Industry
                    try:
                        # First try by name (case-insensitive)
                        industry_instance = Industry.objects.filter(name__iexact=industry_value).first()
                        # If not found, try by slug
                        if not industry_instance:
                            industry_instance = Industry.objects.filter(slug__iexact=industry_value.lower().replace(' ', '-')).first()
                    except Exception as e:
                        logger.warning(f"Could not find industry '{industry_value}': {e}")
                        industry_instance = None
                
                # Parse dates. end_date is the legacy alias for deadline —
                # accept either, mirror to both columns below.
                start_date = action.get("start_date")
                deadline = action.get("deadline") or action.get("end_date")

                if start_date and isinstance(start_date, str):
                    try:
                        from datetime import datetime
                        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        logger.debug(f"Failed to parse start_date: {start_date}")
                        start_date = None

                if deadline and isinstance(deadline, str):
                    try:
                        from datetime import datetime
                        deadline = datetime.strptime(deadline, '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        logger.debug(f"Failed to parse deadline: {deadline}")
                        deadline = None
                
                # Handle budget - Project model uses budget_min and budget_max, not budget
                budget = action.get("budget")
                budget_min = None
                budget_max = None
                if budget:
                    try:
                        budget_value = float(budget)
                        budget_min = budget_value
                        budget_max = budget_value
                    except (ValueError, TypeError):
                        pass
                
                project = Project.objects.create(
                    name=action.get("project_name", "New Project"),
                    description=action.get("project_description", ""),
                    status=action.get("project_status", "planning"),
                    priority=action.get("project_priority", "medium"),
                    project_type=action.get("project_type", "general"),
                    industry=industry_instance,  # Use None if not found
                    budget_min=budget_min,
                    budget_max=budget_max,
                    start_date=start_date,
                    end_date=deadline,  # mirror — legacy column
                    deadline=deadline,
                    created_by_company_user=company_user,
                    owner=default_owner,
                )
                
                created_projects[action.get("project_name")] = project.id
                action_results.append({
                    "action": "create_project",
                    "success": True,
                    "project_id": project.id,
                    "project_name": project.name,
                })
            except Exception as e:
                logger.exception(f"Error creating project: {action.get('project_name')}")
                action_results.append({
                    "action": "create_project",
                    "success": False,
                    "error": str(e),
                })

    # Second pass: Create tasks (can now reference created projects)
    # If we created a project in the first pass, use it for tasks without project_id
    default_project_id = None
    if created_projects:
        # Use the first created project as default
        default_project_id = list(created_projects.values())[0]
    
    for action in actions:
        if action.get("action") == "create_task":
            try:
                project_id_for_task = action.get("project_id")
                project_name = action.get("project_name")
                
                # If project_id is null but project_name is provided, look it up
                if not project_id_for_task and project_name:
                    if project_name in created_projects:
                        project_id_for_task = created_projects[project_name]
                    else:
                        # Try to find existing project
                        try:
                            existing_project = Project.objects.get(
                                name=project_name,
                                created_by_company_user=company_user
                            )
                            project_id_for_task = existing_project.id
                        except Project.DoesNotExist:
                            pass
                
                # If still no project_id, use the default (first created project)
                if not project_id_for_task and default_project_id:
                    project_id_for_task = default_project_id
                    logger.info(f"Using default project {project_id_for_task} for task '{action.get('task_title')}'")
                
                if not project_id_for_task:
                    action_results.append({
                        "action": "create_task",
                        "success": False,
                        "error": f"Could not determine project for task '{action.get('task_title')}'. No project was created or specified.",
                    })
                    continue
                
                # Parse due date
                due_date = None
                due_date_str = action.get("due_date")
                if due_date_str:
                    try:
                        from django.utils import timezone
                        from datetime import datetime as dt_time
                        if isinstance(due_date_str, str):
                            # Try parsing different formats
                            for fmt in ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ']:
                                try:
                                    due_date = datetime.strptime(due_date_str, fmt)
                                    if timezone.is_naive(due_date):
                                        due_date = timezone.make_aware(due_date)
                                    break
                                except ValueError:
                                    continue
                            # If still None, try date only
                            if due_date is None:
                                date_only = datetime.strptime(due_date_str.split('T')[0], '%Y-%m-%d').date()
                                if date_only:
                                    due_date = datetime.combine(date_only, dt_time(23, 59, 59))
                                    if timezone.is_naive(due_date):
                                        due_date = timezone.make_aware(due_date)
                    except Exception:
                        due_date = None
                
                # Default due_date when missing
                if due_date is None and project_id_for_task:
                    try:
                        from django.utils import timezone
                        from datetime import datetime as dt_time
                        task_project = Project.objects.filter(id=project_id_for_task, created_by_company_user=company_user).first()
                        if task_project and getattr(task_project, "deadline", None):
                            d = task_project.deadline
                            if hasattr(d, "year"):
                                due_date = datetime.combine(d, dt_time(23, 59, 59))
                                if timezone.is_naive(due_date):
                                    due_date = timezone.make_aware(due_date)
                        if due_date is None and task_project and getattr(task_project, "end_date", None):
                            d = task_project.end_date
                            if hasattr(d, "year"):
                                due_date = datetime.combine(d, dt_time(23, 59, 59))
                                if timezone.is_naive(due_date):
                                    due_date = timezone.make_aware(due_date)
                        if due_date is None:
                            due_date = timezone.now() + timedelta(days=14)
                    except Exception:
                        pass
                
                # Parse estimated_hours
                estimated_hours = action.get("estimated_hours")
                if estimated_hours:
                    try:
                        estimated_hours = float(estimated_hours)
                    except (ValueError, TypeError):
                        estimated_hours = None
                
                task = Task.objects.create(
                    project_id=project_id_for_task,
                    title=action.get("task_title", "New Task"),
                    description=action.get("task_description", ""),
                    status=action.get("status", "todo"),
                    priority=action.get("priority", "medium"),
                    due_date=due_date,
                    estimated_hours=estimated_hours,
                    assignee_id=action.get("assignee_id") if action.get("assignee_id") else None,
                    ai_reasoning=action.get("reasoning", ""),
                )
                
                action_results.append({
                    "action": "create_task",
                    "success": True,
                    "task_id": task.id,
                    "task_title": task.title,
                    "project_id": project_id_for_task,
                    "project_name": task.project.name if task.project else None,
                    "message": f'Task "{task.title}" created successfully!',
                    "priority": getattr(task, "priority", None) or "medium",
                    "assignee_username": task.assignee.username if task.assignee else None,
                    "assignee_name": _assignee_display(task.assignee),
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                    "deadline": task.due_date.isoformat() if task.due_date else None,
                    "created_at": task.created_at.isoformat() if getattr(task, "created_at", None) else None,
                })
            except Exception as e:
                logger.exception(f"Error creating task: {action.get('task_title')}")
                action_results.append({
                    "action": "create_task",
                    "success": False,
                    "error": str(e),
                })

    logger.info(f"Project Pilot pipeline done: {len(action_results)} action_results")
    return {
        "answer": result.get("answer", ""),
        "action_results": action_results,
        "cannot_do": "",
        "extracted_text_preview": extracted_text[:200] + "..." if len(extracted_text) > 200 else extracted_text,
    }

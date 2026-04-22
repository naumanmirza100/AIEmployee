from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404

from core.models import Project, Task, Subtask, TeamMember, UserProfile
from project_manager_agent.ai_agents import AgentRegistry
from project_manager_agent.models import (
    PMKnowledgeQAChat,
    PMKnowledgeQAChatMessage,
    PMProjectPilotChat,
    PMProjectPilotChatMessage,
    PMNotification,
    ScheduledMeeting,
    MeetingResponse,
    MeetingParticipant,
    PMMeetingSchedulerChat,
    PMMeetingSchedulerChatMessage,
)
from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.decorators import throttle_classes

import logging
import json
import re
from datetime import datetime, timedelta
import os
import tempfile

from django.db.models import Count, Q
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings as django_settings
from core.models import CompanyUser

from project_manager_agent.ai_agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Text extraction imports
try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    logger.warning("PyPDF2 not available. PDF extraction will not work.")

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    logger.warning("python-docx not available. DOCX extraction will not work.")


def _audit_log(company_user, action, model_name='', object_id=None, object_title='', details=None):
    """Create an audit log entry. Fails silently."""
    try:
        from project_manager_agent.models import PMAuditLog
        PMAuditLog.objects.create(
            company_user=company_user, action=action, model_name=model_name,
            object_id=object_id, object_title=str(object_title)[:255],
            details=details,
        )
    except Exception:
        pass  # Audit logging should never break the main flow


class PMLLMThrottle(SimpleRateThrottle):
    """Rate limit for LLM-powered PM agent endpoints (30/hour per user)."""
    scope = 'pm_llm'
    rate = '30/hour'

    def get_cache_key(self, request, view):
        if hasattr(request, 'user') and request.user:
            ident = getattr(request.user, 'id', None) or getattr(request.user, 'pk', None)
            if ident:
                return self.cache_format % {'scope': self.scope, 'ident': ident}
        return self.get_ident(request)


def _get_project_owner(company_user):
    """
    Get a Django User to use as project owner for this company user.
    Prefers a user created by this company user. Falls back to creating one.
    """
    from core.models import UserProfile
    from django.contrib.auth import get_user_model
    User = get_user_model()

    # Try to find a user created by this company user
    profile = UserProfile.objects.filter(
        created_by_company_user=company_user
    ).select_related('user').first()
    if profile and profile.user:
        return profile.user

    # Fallback: find or create a user from the company user's email
    user, created = User.objects.get_or_create(
        username=f"cu_{company_user.id}_{company_user.email.split('@')[0]}",
        defaults={
            'email': company_user.email,
            'first_name': company_user.full_name.split()[0] if company_user.full_name else '',
            'last_name': ' '.join(company_user.full_name.split()[1:]) if company_user.full_name and len(company_user.full_name.split()) > 1 else '',
        }
    )
    if created:
        # Create a profile linking back to this company user
        UserProfile.objects.get_or_create(user=user, defaults={'created_by_company_user': company_user})
    return user


def _validate_positive_number(value, field_name, max_val=999999999):
    """Validate a numeric field is positive and within bounds. Returns (cleaned_value, error_msg)."""
    if value is None:
        return None, None
    try:
        num = float(value)
        if num < 0:
            return None, f"{field_name} must be a positive number."
        if num > max_val:
            return None, f"{field_name} is too large (max {max_val})."
        return num, None
    except (ValueError, TypeError):
        return None, f"{field_name} must be a valid number."


def _validate_string(value, field_name, max_length=255):
    """Validate a string field length. Returns (cleaned_value, error_msg)."""
    if value is None:
        return None, None
    val = str(value).strip()
    if len(val) > max_length:
        return val[:max_length], None  # Truncate silently
    return val, None


def _assignee_display(assignee):
    """Safely get assignee display name (full name or username) or None."""
    if not assignee:
        return None
    try:
        return assignee.get_full_name() or getattr(assignee, "username", None)
    except Exception:
        return getattr(assignee, "username", None)


def _pm_extract_first_json(raw_text: str):
    raw_text = (raw_text or "").strip()
    if not raw_text:
        raise ValueError("Empty LLM response")

    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        start = 1
        end = len(lines)
        for i in range(start, len(lines)):
            if lines[i].strip() == "```":
                end = i
                break
        raw_text = "\n".join(lines[start:end]).strip()

    if raw_text.lower().startswith("json"):
        raw_text = raw_text[4:].strip()

    try:
        return json.loads(raw_text)
    except Exception:
        pass

    start_match = re.search(r"[\[{]", raw_text)
    if not start_match:
        raise ValueError("No JSON object/array found in LLM response")

    start_idx = start_match.start()
    opening = raw_text[start_idx]
    closing = "]" if opening == "[" else "}"

    stack = [opening]
    in_string = False
    escaped = False

    for i in range(start_idx + 1, len(raw_text)):
        ch = raw_text[i]

        if in_string:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch in "[{":
            stack.append(ch)
            continue

        if ch in "]}":
            if not stack:
                continue

            last = stack[-1]
            if (last == "{" and ch == "}") or (last == "[" and ch == "]"):
                stack.pop()
                if not stack:
                    candidate = raw_text[start_idx : i + 1].strip()
                    return json.loads(candidate)
            continue

    raise ValueError("Unterminated JSON in LLM response")


def _pm_repair_llm_json(raw_text: str, analytics_data: dict) -> str:
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return raw_text

    # If the model outputs variable-like tokens, rewrite them into literal JSON so parsing succeeds.
    try:
        tasks_by_project = analytics_data.get('tasks_by_project_obj') or {}

        def _replace_tasks_by_project(m):
            project_name = (m.group('project') or '').strip()
            value = 0
            try:
                value = int(tasks_by_project.get(project_name, 0) or 0)
            except Exception:
                value = 0
            return json.dumps({project_name or 'Project': value})

        raw_text = re.sub(
            r"\btasks_by_project_obj\s*\[\s*\"(?P<project>[^\"]+)\"\s*\]",
            _replace_tasks_by_project,
            raw_text,
            flags=re.IGNORECASE,
        )
    except Exception:
        pass

    replacements = {
        'projects_by_status_obj': json.dumps(analytics_data.get('projects_by_status_obj') or {'No data': 0}),
        'projects_by_priority_obj': json.dumps(analytics_data.get('projects_by_priority_obj') or {'No data': 0}),
        'tasks_by_status_obj': json.dumps(analytics_data.get('tasks_by_status_obj') or {'No data': 0}),
        'tasks_by_priority_obj': json.dumps(analytics_data.get('tasks_by_priority_obj') or {'No data': 0}),
        'tasks_by_project_obj': json.dumps(analytics_data.get('tasks_by_project_obj') or {'No data': 0}),
    }
    for token, value in replacements.items():
        try:
            raw_text = re.sub(rf"\b{re.escape(token)}\b", value, raw_text)
        except Exception:
            continue

    return raw_text


def _get_chat_history(request):
    """Extract chat_history from request (JSON body or POST form for multipart). Returns a list of {role, content}."""
    hist = request.data.get("chat_history") if hasattr(request, "data") and isinstance(getattr(request, "data", None), dict) else None
    if hist is None and request.method == "POST":
        hist = request.POST.get("chat_history")
    if isinstance(hist, str):
        try:
            hist = json.loads(hist) if hist.strip() else []
        except Exception:
            hist = []
    return list(hist)[:20] if isinstance(hist, list) else []


def _ensure_project_manager(user):
    """
    Enforce that only project managers (or staff/superusers) can use PM agent endpoints.
    """
    if user.is_superuser or user.is_staff:
        return True
    try:
        profile = user.profile
        return profile.is_project_manager()
    except Exception:
        return False


def _build_available_users(project_id=None, project=None, company_user=None):
    """
    Return users created by this company_user (from UserProfile).
    Falls back to team members if no company_user provided.
    Never include superusers.
    """
    available_users = []

    # Primary: use UserProfile to get users created by this company user
    if company_user:
        from core.models import UserProfile
        created_profiles = UserProfile.objects.filter(
            created_by_company_user=company_user
        ).select_related('user')
        for profile in created_profiles:
            user = profile.user
            if getattr(user, "is_superuser", False):
                continue
            available_users.append({
                "id": user.id,
                "username": user.username,
                "name": user.get_full_name() or user.username,
                "role": profile.role or "team_member",
            })
        return available_users

    # Fallback: team members for a specific project
    if project_id and project is not None:
        team_members = TeamMember.objects.filter(project_id=project_id).select_related("user")
        for member in team_members:
            if getattr(member.user, "is_superuser", False):
                continue
            available_users.append(
                {
                    "id": member.user.id,
                    "username": member.user.username,
                    "name": member.user.get_full_name() or member.user.username,
                    "role": member.role,
                }
            )
    else:
        User = get_user_model()
        users = User.objects.filter(is_superuser=False)[:50]
        for u in users:
            available_users.append(
                {"id": u.id, "username": u.username, "name": u.get_full_name() or u.username}
            )

    return available_users


# Common words to ignore when matching user names in "only N users, X and Y" (avoids matching "and" as a name)
_ALLOWED_IDS_STOPWORDS = frozenset({
    "and", "or", "the", "a", "an", "to", "for", "only", "all", "users", "user", "tasks", "task",
    "assign", "assigned", "by", "with", "be", "is", "are", "its", "it", "as", "in", "on", "at",
    "of", "no", "so", "do", "go", "we", "me", "my", "us", "am", "id", "st", "nd", "rd", "th",
    "to", "from", "into", "our", "can", "has", "have", "had", "was", "were", "been", "being",
})


def _get_allowed_user_ids_for_only_n_users(question, available_users):
    """
    If the user said "only N users" and named people (e.g. "only 2 users, hamza and abdullah"),
    return the list of allowed user IDs (same partial name matching as the agent). Otherwise return None.
    Used to enforce assignment in the backend when the LLM assigns to others anyway.
    Excludes common stopwords so "and" in "hamza and abdullah" does not match a user with "and" in their name.
    """
    if not question or not available_users:
        return None
    import re
    q_lower = question.lower().strip()
    if not re.search(r"only\s+\d+\s+users?", q_lower):
        return None
    seen_ids = set()
    allowed = []
    for u in available_users:
        uid = u.get("id")
        if uid in seen_ids:
            continue
        username = (u.get("username") or "").strip().lower()
        name = (u.get("name") or "").strip().lower()
        if not username and not name:
            continue
        if username and username in q_lower:
            allowed.append(uid)
            seen_ids.add(uid)
            continue
        if name and name in q_lower:
            allowed.append(uid)
            seen_ids.add(uid)
            continue
        name_words = [w for w in name.split() if len(w) > 1 and w not in _ALLOWED_IDS_STOPWORDS]
        username_words = [w for w in re.sub(r"[_.-]", " ", username).split() if len(w) > 1 and w not in _ALLOWED_IDS_STOPWORDS]
        for word in name_words + username_words:
            if len(word) >= 2 and word not in _ALLOWED_IDS_STOPWORDS and word in q_lower:
                allowed.append(uid)
                seen_ids.add(uid)
                break
    return allowed if allowed else None


def _build_user_assignments(available_users, *, project_id=None, all_tasks=None, owner=None):
    """
    Build assignment context for the Project Pilot agent.
    """
    if all_tasks is None:
        all_tasks = Task.objects.none()

    user_assignments = []
    for user_info in available_users:
        user_id = user_info["id"]
        if project_id:
            if owner:
                user_tasks = Task.objects.filter(
                    project_id=project_id, assignee_id=user_id, project__owner=owner
                ).select_related("project")
            else:
                user_tasks = Task.objects.filter(
                    project_id=project_id, assignee_id=user_id
                ).select_related("project")
        else:
            # Check if all_tasks is a QuerySet or a list (sliced QuerySet)
            if hasattr(all_tasks, 'filter') and not isinstance(all_tasks, list):
                # It's a QuerySet, can filter directly
                user_tasks = all_tasks.filter(assignee_id=user_id).select_related("project")
            else:
                # It's a list (evaluated QuerySet), filter in Python
                user_tasks = [t for t in all_tasks if hasattr(t, 'assignee_id') and t.assignee_id == user_id]
        
        user_assignments.append(
            {
                "user": user_info,
                "tasks": [
                    {
                        "id": t.id,
                        "title": t.title,
                        "status": t.status,
                        "priority": t.priority,
                        "project_name": t.project.name,
                    }
                    for t in user_tasks[:10]
                ],
            }
        )

    return user_assignments


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([PMLLMThrottle])
def project_pilot(request):
    """
    Project Pilot Agent API - Only accessible to company users.
    Body:
      - question: str (required)
      - project_id: int (optional)
    """
    # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
    company_user = request.user
    
    # Check if user can access project manager features (project_manager or company_user role)
    # Use fallback if method doesn't exist (for server restart issues)
    can_access = False
    if hasattr(company_user, 'can_access_project_manager_features'):
        can_access = company_user.can_access_project_manager_features()
    else:
        # Fallback: check role directly
        can_access = company_user.role in ['project_manager', 'company_user']
    
    if not can_access:
        return Response(
            {"status": "error",
             "message": "Access denied. Project manager or company user role required."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        question = request.data.get("question", "").strip()
        if not question:
            return Response(
                {"status": "error", "message": "question is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        project_id = request.data.get("project_id")
        project = None
        company = company_user.company

        # Filter projects created by this company user
        all_projects = Project.objects.filter(created_by_company_user=company_user)
        all_tasks = Task.objects.filter(project__created_by_company_user=company_user).select_related("project")

        if project_id:
            project = get_object_or_404(Project, id=project_id, created_by_company_user=company_user)
            tasks = Task.objects.filter(project=project).select_related("assignee").prefetch_related("subtasks")
            context = {
                "project": {
                    "id": project.id,
                    "name": project.name,
                    "description": project.description,
                    "status": project.status,
                    "priority": project.priority,
                "tasks": [
                    {
                        "id": t.id,
                        "title": t.title,
                        "status": t.status,
                        "priority": t.priority,
                        "description": t.description,
                        "assignee_id": t.assignee.id if t.assignee else None,
                        "assignee_username": t.assignee.username if t.assignee else None,
                        "subtasks": [
                            {
                                "id": st.id,
                                "title": st.title,
                                "status": st.status,
                                "order": st.order,
                            }
                            for st in t.subtasks.all()
                        ],
                    }
                    for t in tasks
                ],
                },
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

        chat_history = _get_chat_history(request)
        agent = AgentRegistry.get_agent("project_pilot")
        # Route LLM call through the company key/quota resolver. Resolver will
        # raise QuotaExhausted (402) or NoKeyAvailable (403) on hard-block —
        # core/drf_exceptions converts those to clean JSON responses.
        agent.company_id = getattr(company_user, 'company_id', None)
        agent.agent_key_name = 'project_manager_agent'
        result = agent.process(question=question, context=context, available_users=available_users, chat_history=chat_history)
        if result.get("cannot_do"):
            return Response({"status": "success", "data": result}, status=status.HTTP_200_OK)

        actions = result.get("actions") or []
        if result.get("action"):
            actions = [result["action"]]
        
        # If no actions found, try parsing from answer field (sometimes agent returns JSON string in answer)
        if len(actions) == 0 and result.get("answer"):
            answer_str = result.get("answer", "").strip()
            if answer_str and "[" in answer_str:
                try:
                    # Clean the JSON string by removing control characters (except newlines and tabs)
                    import re
                    # Remove control characters except newline (\n), carriage return (\r), and tab (\t)
                    cleaned_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', answer_str)
                    
                    # Find the start of the JSON array
                    first_bracket = cleaned_str.find('[')
                    if first_bracket < 0:
                        first_bracket = 0
                    
                    # Find all object boundaries by counting braces
                    brace_count = 0
                    bracket_count = 0
                    last_valid_pos = -1
                    
                    # Start counting from the first bracket
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
                        
                        # Track the last position where we had a complete object
                        if brace_count == 0 and bracket_count > 0:
                            last_valid_pos = i
                    
                    # Try to find the end by matching brackets
                    bracket_count = 0
                    end_pos = -1
                    for i in range(first_bracket, len(cleaned_str)):
                        char = cleaned_str[i]
                        if char == '[':
                            bracket_count += 1
                        elif char == ']':
                            bracket_count -= 1
                            if bracket_count == 0:
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
                    
                    if end_pos > first_bracket:
                        json_str = cleaned_str[first_bracket:end_pos]
                        
                        # Fix reversed brackets if present
                        if json_str.rstrip().endswith(']}'):
                            json_str = json_str.rstrip()[:-2] + '}]'
                            logger.warning("Fixed reversed closing brackets in JSON")
                        
                        # Try to parse the extracted JSON
                        try:
                            parsed_actions = json.loads(json_str)
                            if isinstance(parsed_actions, list):
                                actions = parsed_actions
                                logger.info(f"Parsed {len(actions)} actions from answer field")
                        except json.JSONDecodeError as parse_err:
                            # If parsing fails, try to fix incomplete JSON
                            logger.warning(f"Initial JSON parse failed: {parse_err}. Attempting to fix...")
                            
                            # Try to complete incomplete JSON objects
                            # Find all complete objects before the error
                            try:
                                # Count braces to find where the last complete object ends
                                brace_level = 0
                                bracket_level = 0
                                complete_objects = []
                                current_obj_start = -1
                                
                                for i, char in enumerate(json_str):
                                    if char == '[':
                                        bracket_level += 1
                                    elif char == ']':
                                        bracket_level -= 1
                                    elif char == '{':
                                        if brace_level == 0:
                                            current_obj_start = i
                                        brace_level += 1
                                    elif char == '}':
                                        brace_level -= 1
                                        if brace_level == 0 and bracket_level == 1:
                                            # Complete object found
                                            if current_obj_start >= 0:
                                                obj_str = json_str[current_obj_start:i+1]
                                                try:
                                                    obj = json.loads(obj_str)
                                                    complete_objects.append(obj)
                                                except (json.JSONDecodeError, ValueError):
                                                    pass
                                
                                if complete_objects:
                                    actions = complete_objects
                                    logger.info(f"Extracted {len(actions)} complete actions from incomplete JSON")
                            except Exception as fix_err:
                                logger.warning(f"Failed to fix incomplete JSON: {fix_err}")
                    else:
                        logger.warning("Could not find matching closing bracket for JSON array")
                except Exception as e:
                    logger.warning(f"Failed to parse answer as JSON: {e}")
                    # Try one final fallback - extract what we can
                    try:
                        import re
                        # Find all JSON objects in the string
                        object_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
                        matches = re.findall(object_pattern, answer_str)
                        if matches:
                            extracted_objects = []
                            for match in matches:
                                try:
                                    obj = json.loads(match)
                                    if isinstance(obj, dict) and obj.get("action"):
                                        extracted_objects.append(obj)
                                except (json.JSONDecodeError, ValueError):
                                    pass
                            if extracted_objects:
                                actions = extracted_objects
                                logger.info(f"Extracted {len(actions)} actions using regex fallback")
                    except Exception as fallback_err:
                        logger.warning(f"All JSON parsing attempts failed: {fallback_err}")
        
        # Ensure actions is always a list
        if not isinstance(actions, list):
            actions = []
        
        # Only run round-robin when user clearly asked for "assign to ALL" and did NOT say "only N users" or name specific people
        import re as _re
        _q_lower = question.lower()
        _only_n_users = _re.search(r"only\s+\d+\s+users?", _q_lower)
        _assign_to_all_phrases = [
            "assign to all", "assign to all available", "assign to all users",
            "distribute to all", "assign tasks to all", "all available users",
            "all developers", "all users", "assign the tasks to all",
        ]
        _wants_assign_to_all = any(p in _q_lower for p in _assign_to_all_phrases)
        if _wants_assign_to_all and not _only_n_users and available_users:
            _create_tasks = [a for a in actions if isinstance(a, dict) and a.get("action") == "create_task"]
            _unassigned = [a for a in _create_tasks if not a.get("assignee_id")]
            if _unassigned:
                _user_ids = [u["id"] for u in available_users]
                for i, action_data in enumerate(_unassigned):
                    action_data["assignee_id"] = _user_ids[i % len(_user_ids)]
                logger.info(f"Backend fallback: assigned {len(_unassigned)} tasks round-robin to {len(_user_ids)} users")
        
        # Enforce "only N users" when user named specific people: restrict every create_task to allowed IDs only
        _allowed_ids = _get_allowed_user_ids_for_only_n_users(question, available_users)
        if _allowed_ids is not None:
            _create_tasks = [a for a in actions if isinstance(a, dict) and a.get("action") == "create_task"]
            for i, action_data in enumerate(_create_tasks):
                action_data["assignee_id"] = _allowed_ids[i % len(_allowed_ids)]
            logger.info(f"Backend enforcement: restricted task assignment to only {len(_allowed_ids)} users (IDs: {_allowed_ids})")
        
        logger.info(f"Extracted {len(actions)} actions from agent response. Actions: {[a.get('action') if isinstance(a, dict) else 'invalid' for a in actions[:5]]}")
        
        # Log if no actions found
        if len(actions) == 0:
            logger.warning(f"No actions found in result. Result keys: {result.keys() if isinstance(result, dict) else 'Not a dict'}")
            logger.warning(f"Result sample: {str(result)[:500]}")

        created_project_id = None
        action_results = []
        
        # Track created project ID across all actions in this batch
        # This allows tasks created after a project to automatically use that project

        # Ensure answer exists for concatenations
        if "answer" not in result or result["answer"] is None:
            result["answer"] = ""

        logger.info(f"Processing {len(actions)} actions from project pilot agent")
        
        # Process all actions in order
        for action_data in actions:
            action_type = action_data.get("action")
            if action_type == "create_project":
                try:
                    end_date = None
                    deadline_days = action_data.get("deadline_days")
                    if deadline_days:
                        try:
                            days = int(
                                str(deadline_days)
                                .replace("working days", "")
                                .replace("days", "")
                                .strip()
                            )
                            current_date = datetime.now().date()
                            working_days = 0
                            check_date = current_date
                            while working_days < days:
                                if check_date.weekday() < 5:
                                    working_days += 1
                                if working_days < days:
                                    check_date += timedelta(days=1)
                            end_date = check_date
                        except (ValueError, TypeError):
                            end_date = None

                    project_manager_id = action_data.get("project_manager_id")
                    industry_id = action_data.get("industry_id")
                    project_type = action_data.get("project_type")
                    budget_min = action_data.get("budget_min")
                    budget_max = action_data.get("budget_max")
                    deadline = action_data.get("deadline") or end_date

                    # Create project with company association
                    # Note: owner field is required but CompanyUser is not a User model
                    # We'll need to set owner to None or create a dummy owner
                    # For now, we'll set it to None if the field allows it, otherwise we need to handle it
                    from django.contrib.auth.models import User
                    # Try to get the first user as owner (you might want to change this logic)
                    default_owner = _get_project_owner(company_user)
                    
                    project_data = {
                        "name": action_data.get("project_name", "New Project"),
                        "description": action_data.get("project_description", ""),
                        "company": company,
                        "created_by_company_user": company_user,
                        "status": action_data.get("project_status", "planning"),
                        "priority": action_data.get("project_priority", "medium"),
                        "project_type": project_type if project_type else "web_app",
                    }
                    
                    # Set owner if we have a default owner
                    if default_owner:
                        project_data["owner"] = default_owner
                    
                    # Add optional fields
                    if end_date:
                        project_data["end_date"] = end_date
                    if project_manager_id:
                        project_data["project_manager_id"] = project_manager_id
                    if industry_id:
                        project_data["industry_id"] = industry_id
                    if budget_min:
                        project_data["budget_min"] = budget_min
                    if budget_max:
                        project_data["budget_max"] = budget_max
                    if deadline:
                        project_data["deadline"] = deadline
                    
                    project = Project.objects.create(**project_data)
                    _audit_log(company_user, 'project_created', 'Project', project.id, project.name)

                    # Store the created project ID for use in subsequent task creation
                    created_project_id = project.id
                    # Store it in the action_data for reference
                    action_data["_created_project_id"] = project.id

                    logger.info(f"Project created successfully: {project.id} - {project.name}")
                    action_results.append(
                        {
                            "action": "create_project",
                            "success": True,
                            "project_id": project.id,
                            "project_name": project.name,
                            "message": f'Project "{project.name}" created successfully!',
                        }
                    )
                except Exception as e:
                    logger.exception(f"Error creating project: {str(e)}")
                    logger.error(f"Project data: {project_data}")
                    action_results.append({
                        "action": "create_project",
                        "success": False,
                        "error": str(e),
                        "project_name": action_data.get("project_name", "Unknown")
                    })

        # Second pass: Create tasks and other actions, using created project IDs
        for action_data in actions:
            action_type = action_data.get("action")
            if action_type == "create_project":
                # Already handled in first pass
                continue
            elif action_type == "create_task":
                try:
                    task_project_id = action_data.get("project_id")
                    # If no project_id specified, use the project created in this batch
                    if not task_project_id and created_project_id:
                        task_project_id = created_project_id

                    if not task_project_id:
                        action_results.append(
                            {
                                "action": "create_task",
                                "success": False,
                                "error": "project_id is required for task creation",
                            }
                        )
                        continue

                    task_project = get_object_or_404(Project, id=task_project_id, created_by_company_user=company_user)

                    # Parse due date
                    due_date = None
                    due_date_str = action_data.get("due_date")
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

                    # Default due_date when missing (e.g. project deadline, end_date, or 14 days from now)
                    if due_date is None and task_project:
                        from django.utils import timezone
                        from datetime import datetime as dt_time
                        if getattr(task_project, "deadline", None):
                            d = task_project.deadline
                            if hasattr(d, "year"):
                                due_date = datetime.combine(d, dt_time(23, 59, 59))
                                if timezone.is_naive(due_date):
                                    due_date = timezone.make_aware(due_date)
                        if due_date is None and getattr(task_project, "end_date", None):
                            d = task_project.end_date
                            if hasattr(d, "year"):
                                due_date = datetime.combine(d, dt_time(23, 59, 59))
                                if timezone.is_naive(due_date):
                                    due_date = timezone.make_aware(due_date)
                        if due_date is None:
                            due_date = timezone.now() + timedelta(days=14)

                    estimated_hours = action_data.get("estimated_hours")
                    if estimated_hours:
                        try:
                            estimated_hours = float(estimated_hours)
                        except (ValueError, TypeError):
                            estimated_hours = None

                    # Capacity check — warn if assignee has too many active tasks
                    capacity_warning = None
                    assignee_id_val = action_data.get("assignee_id")
                    if assignee_id_val:
                        active_count = Task.objects.filter(
                            assignee_id=assignee_id_val,
                            status__in=['todo', 'in_progress', 'review']
                        ).count()
                        if active_count >= 10:
                            capacity_warning = f"Warning: assignee already has {active_count} active tasks."

                    task = Task.objects.create(
                        title=action_data.get("task_title", "New Task"),
                        description=action_data.get("task_description", ""),
                        project=task_project,
                        status=action_data.get("status", "todo"),
                        priority=action_data.get("priority", "medium"),
                        assignee_id=assignee_id_val if assignee_id_val else None,
                        estimated_hours=estimated_hours,
                        due_date=due_date,
                        ai_reasoning=action_data.get("reasoning", ""),
                    )
                    _audit_log(company_user, 'task_created', 'Task', task.id, task.title)

                    action_results.append(
                        {
                            "action": "create_task",
                            "success": True,
                            "task_id": task.id,
                            "task_title": task.title,
                            "project_name": task_project.name,
                            "message": f'Task "{task.title}" created successfully!',
                            "priority": getattr(task, "priority", None) or "medium",
                            "assignee_username": task.assignee.username if task.assignee else None,
                            "assignee_name": _assignee_display(task.assignee),
                            "due_date": task.due_date.isoformat() if task.due_date else None,
                            "deadline": task.due_date.isoformat() if task.due_date else None,
                            "created_at": task.created_at.isoformat() if getattr(task, "created_at", None) else None,
                        }
                    )
                except Exception as e:
                    action_results.append(
                        {"action": "create_task", "success": False, "error": f"Error creating task: {str(e)}"}
                    )

            elif action_type == "delete_project":
                try:
                    project_id_to_delete = action_data.get("project_id")
                    if not project_id_to_delete:
                        action_results.append(
                            {"action": "delete_project", "success": False, "error": "project_id is required"}
                        )
                        continue
                    project_to_delete = get_object_or_404(Project, id=project_id_to_delete, created_by_company_user=company_user)
                    project_name = project_to_delete.name
                    project_to_delete.delete()
                    action_results.append(
                        {
                            "action": "delete_project",
                            "success": True,
                            "project_id": project_id_to_delete,
                            "project_name": project_name,
                            "message": f'Project "{project_name}" deleted successfully!',
                        }
                    )
                except Exception as e:
                    action_results.append(
                        {"action": "delete_project", "success": False, "error": f"Error deleting project: {str(e)}"}
                    )

            elif action_type == "delete_task":
                try:
                    task_id_to_delete = action_data.get("task_id")
                    if not task_id_to_delete:
                        action_results.append(
                            {"action": "delete_task", "success": False, "error": "task_id is required"}
                        )
                        continue
                    task_to_delete = get_object_or_404(Task, id=task_id_to_delete, project__created_by_company_user=company_user)
                    task_title = task_to_delete.title
                    task_to_delete.delete()
                    action_results.append(
                        {
                            "action": "delete_task",
                            "success": True,
                            "task_id": task_id_to_delete,
                            "task_title": task_title,
                            "message": f'Task "{task_title}" deleted successfully!',
                        }
                    )
                except Exception as e:
                    action_results.append(
                        {"action": "delete_task", "success": False, "error": f"Error deleting task: {str(e)}"}
                    )

            elif action_type == "update_project":
                try:
                    project_id_to_update = action_data.get("project_id")
                    if not project_id_to_update:
                        action_results.append(
                            {"action": "update_project", "success": False, "error": "project_id is required"}
                        )
                        continue
                    project_to_update = get_object_or_404(Project, id=project_id_to_update, created_by_company_user=company_user)
                    updates = action_data.get("updates", {})

                    # Update simple string/choice fields
                    for field in ["name", "description", "status", "priority", "project_type"]:
                        if field in updates and updates[field] is not None:
                            setattr(project_to_update, field, updates[field])

                    # Handle date fields
                    for date_field in ["deadline", "start_date", "end_date"]:
                        if date_field in updates:
                            date_val = updates.get(date_field)
                            if date_val:
                                from datetime import datetime as _dt_proj
                                try:
                                    setattr(project_to_update, date_field, _dt_proj.strptime(date_val, "%Y-%m-%d").date())
                                except (ValueError, TypeError):
                                    pass
                            else:
                                setattr(project_to_update, date_field, None)

                    # Handle budget fields
                    for budget_field in ["budget_min", "budget_max"]:
                        if budget_field in updates:
                            budget_val = updates.get(budget_field)
                            if budget_val is not None:
                                try:
                                    setattr(project_to_update, budget_field, float(budget_val))
                                except (ValueError, TypeError):
                                    pass
                            else:
                                setattr(project_to_update, budget_field, None)

                    project_to_update.save()
                    action_results.append(
                        {
                            "action": "update_project",
                            "success": True,
                            "project_id": project_to_update.id,
                            "project_name": project_to_update.name,
                            "message": f'Project "{project_to_update.name}" updated successfully!',
                            "status": project_to_update.status,
                            "priority": project_to_update.priority,
                            "deadline": project_to_update.deadline.isoformat() if project_to_update.deadline else None,
                        }
                    )
                except Exception as e:
                    action_results.append(
                        {"action": "update_project", "success": False, "error": f"Error updating project: {str(e)}"}
                    )

            elif action_type == "update_task":
                try:
                    task_id_to_update = action_data.get("task_id")
                    if not task_id_to_update:
                        action_results.append(
                            {"action": "update_task", "success": False, "error": "task_id is required"}
                        )
                        continue
                    task_to_update = get_object_or_404(Task, id=task_id_to_update, project__created_by_company_user=company_user)
                    updates = action_data.get("updates", {})

                    # Assignee
                    if "assignee_id" in updates:
                        assignee_id = updates.get("assignee_id")
                        if assignee_id:
                            try:
                                from django.contrib.auth.models import User
                                assignee = User.objects.get(id=assignee_id)
                                task_to_update.assignee = assignee
                            except User.DoesNotExist:
                                pass
                        else:
                            task_to_update.assignee = None

                    # Update other fields
                    for field in ["status", "priority", "title", "description"]:
                        if field in updates:
                            setattr(task_to_update, field, updates[field])

                    # Handle due_date separately (needs date parsing)
                    if "due_date" in updates:
                        due_date_val = updates.get("due_date")
                        if due_date_val:
                            from datetime import datetime as _dt_update
                            try:
                                task_to_update.due_date = _dt_update.strptime(due_date_val, "%Y-%m-%d").date()
                            except (ValueError, TypeError):
                                pass  # Skip invalid date formats
                        else:
                            task_to_update.due_date = None

                    task_to_update.save()
                    action_results.append(
                        {
                            "action": "update_task",
                            "success": True,
                            "task_id": task_to_update.id,
                            "task_title": task_to_update.title,
                            "message": f'Task "{task_to_update.title}" updated successfully!',
                            "priority": getattr(task_to_update, "priority", None) or "medium",
                            "assignee_username": task_to_update.assignee.username if task_to_update.assignee else None,
                            "assignee_name": _assignee_display(task_to_update.assignee),
                            "due_date": task_to_update.due_date.isoformat() if task_to_update.due_date else None,
                            "deadline": task_to_update.due_date.isoformat() if task_to_update.due_date else None,
                            "created_at": task_to_update.created_at.isoformat() if getattr(task_to_update, "created_at", None) else None,
                        }
                    )
                except Exception as e:
                    action_results.append(
                        {"action": "update_task", "success": False, "error": f"Error updating task: {str(e)}"}
                    )

        # Check if any critical actions failed
        project_created = any(
            r.get("action") == "create_project" and r.get("success") for r in action_results
        )
        if not project_created and any(a.get("action") == "create_project" for a in actions):
            # Project creation was attempted but failed
            logger.warning("Project creation was attempted but failed. Action results: %s", action_results)

        # Ensure frontend always has a displayable answer (avoid raw JSON so UI does not hide it)
        answer_text = (result.get("answer") or "").strip()
        if answer_text and (answer_text.startswith("[") or answer_text.startswith("{")):
            # Build a short summary so the message bubble shows something
            success_count = sum(1 for r in action_results if r.get("success"))
            if action_results:
                parts = []
                for r in action_results:
                    if r.get("success") and r.get("message"):
                        parts.append(r["message"])
                result["answer"] = "\n".join(parts) if parts else f"Completed {success_count} action(s)."
            else:
                result["answer"] = "Request processed; no actions were returned."
        
        data = {"status": "success", "data": result, "action_results": action_results}
        logger.info(f"Returning project_pilot response with {len(action_results)} action results")
        return Response(data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("project_pilot failed")
        return Response(
            {"status": "error", "message": "Project pilot failed", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([PMLLMThrottle])
def task_prioritization(request):
    """
    Task Prioritization Agent API - Only accessible to company users.
    Body:
      - project_id: int (optional)
    """
    # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
    company_user = request.user
    
    # Check if user can access project manager features (project_manager or company_user role)
    # Use fallback if method doesn't exist (for server restart issues)
    can_access = False
    if hasattr(company_user, 'can_access_project_manager_features'):
        can_access = company_user.can_access_project_manager_features()
    else:
        # Fallback: check role directly
        can_access = company_user.role in ['project_manager', 'company_user']
    
    if not can_access:
        return Response(
            {"status": "error", "message": "Access denied. Project manager or company user role required."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        project_id = request.data.get("project_id")
        company = company_user.company

        agent = AgentRegistry.get_agent("task_prioritization")

        if project_id:
            project = get_object_or_404(Project, id=project_id, created_by_company_user=company_user)
            tasks_queryset = Task.objects.filter(project_id=project_id, project__created_by_company_user=company_user)
        else:
            tasks_queryset = Task.objects.filter(project__created_by_company_user=company_user)[:50]

        tasks = [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "status": t.status,
                "priority": t.priority,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "deadline": t.due_date.isoformat() if t.due_date else None,
                "estimated_hours": float(t.estimated_hours) if t.estimated_hours else None,
                "actual_hours": float(t.actual_hours) if t.actual_hours else None,
                "assignee_id": t.assignee.id if t.assignee else None,
                "assignee_name": _assignee_display(t.assignee),
                "dependencies": [dep.id for dep in t.depends_on.all()],
                "dependent_count": t.dependent_tasks.count(),
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "progress_percentage": t.progress_percentage,
            }
            for t in tasks_queryset
        ]

        if project_id:
            members = TeamMember.objects.filter(project_id=project_id, project__created_by_company_user=company_user).select_related("user")
        else:
            members = TeamMember.objects.filter(project__created_by_company_user=company_user)[:20].select_related("user")

        team = [
            {
                "id": m.user.id,
                "username": m.user.username,
                "name": m.user.get_full_name() or m.user.username,
                "role": m.role,
            }
            for m in members
        ]

        # For delegation (and to avoid empty team): include users who are assignees on project tasks but not in TeamMember
        action = request.data.get("action", "prioritize")
        if action == "delegation" or not team:
            assignee_ids = [t.get("assignee_id") for t in tasks if t.get("assignee_id")]
            assignee_ids = list(set(assignee_ids))
            team_ids = {m["id"] for m in team}
            missing_ids = [uid for uid in assignee_ids if uid not in team_ids]
            if missing_ids:
                User = get_user_model()
                for u in User.objects.filter(id__in=missing_ids):
                    team.append({
                        "id": u.id,
                        "username": u.username,
                        "name": u.get_full_name() or u.username,
                        "role": "member",
                    })
                    team_ids.add(u.id)
                logger.info("task_prioritization: extended team with %d assignees not in TeamMember", len(missing_ids))

        # Calculate workload analysis for each team member
        workload_analysis = {}
        for member in team:
            member_tasks = [t for t in tasks if t.get('assignee_id') == member['id']]
            active_tasks = [t for t in member_tasks if t.get('status') in ['todo', 'in_progress', 'review']]
            total_hours = sum(t.get('estimated_hours', 0) or 0 for t in active_tasks)
            workload_analysis[member['id']] = {
                'total_tasks': len(member_tasks),
                'active_tasks': len(active_tasks),
                'total_estimated_hours': total_hours,
                'overloaded': len(active_tasks) > 8 or total_hours > 40  # Threshold for overload
            }

        # Build context for prioritize_tasks with enhanced data
        context = {}
        if project_id:
            context["project"] = {
                "id": project.id,
                "name": project.name,
                "status": project.status,
                "start_date": project.start_date.isoformat() if project.start_date else None,
                "end_date": project.end_date.isoformat() if project.end_date else None,
            }
        context["workload_analysis"] = {
            "workload_by_user": workload_analysis,
            "team_size": len(team),
            "total_active_tasks": len([t for t in tasks if t.get('status') in ['todo', 'in_progress', 'review']])
            }

        # Get action from request (default to 'prioritize')
        action = request.data.get("action", "prioritize")
        
        # Call process() method with the action parameter
        # Note: tasks and team_members are passed explicitly, not through context
        # Also pass context separately for prioritize_tasks to use
        result = agent.process(action=action, tasks=tasks, team_members=team, context=context)
        
        # Ensure result is a dict
        if not isinstance(result, dict):
            result = {"success": True, "tasks": result if isinstance(result, list) else []}
        
        # For 'prioritize' action, prioritize_tasks now returns a dict with tasks, summary, statistics, etc.
        if action == "prioritize":
            # prioritize_tasks returns dict with tasks, summary, statistics, charts, etc.
            if "tasks" in result:
                # Already in correct format - prioritize_tasks returns dict directly
                pass
            elif isinstance(result.get("tasks"), dict) and "tasks" in result.get("tasks", {}):
                # Nested structure, flatten it
                tasks_result = result["tasks"]
                result["tasks"] = tasks_result.get("tasks", [])
                if "summary" in tasks_result:
                    result["summary"] = tasks_result["summary"]
                if "statistics" in tasks_result:
                    result["statistics"] = tasks_result["statistics"]
                if "charts" in tasks_result:
                    result["charts"] = tasks_result["charts"]
                if "critical_path_analysis" in tasks_result:
                    result["critical_path_analysis"] = tasks_result["critical_path_analysis"]
                if "workload_analysis" in tasks_result:
                    result["workload_analysis"] = tasks_result["workload_analysis"]
        
        # For 'prioritize_and_order' action, handle combined response
        if action == "prioritize_and_order":
            # prioritize_and_order_tasks returns dict with tasks, prioritization, ordering, combined_analysis, etc.
            if "tasks" in result:
                # Already in correct format
                pass
        
        # For 'bottlenecks' action, identify_bottlenecks returns dict with bottlenecks, workload_heatmap, etc.
        if action == "bottlenecks":
            # identify_bottlenecks returns dict directly with bottlenecks, summary, etc.
            # The process method returns {"success": True, **analysis} so bottlenecks should be at top level
            if "bottlenecks" not in result:
                # Check if it's nested in analysis
                if "analysis" in result:
                    result["bottlenecks"] = result.get("analysis", {}).get("bottlenecks", [])
                    if "summary" in result.get("analysis", {}):
                        result["summary"] = result["analysis"]["summary"]
            else:
                    # Fallback - create empty structure
                    result["bottlenecks"] = []
                    result["summary"] = {"message": "No bottlenecks found"}

        # Apply prioritization suggestions
        tasks_to_update = result.get("tasks") or result.get("prioritized_tasks", [])
        if tasks_to_update:
            for task_data in tasks_to_update:
                # Handle both 'id' and 'task_id' field names
                task_id = task_data.get("task_id") or task_data.get("id")
                if task_id:
                    try:
                        t = Task.objects.get(id=task_id, project__created_by_company_user=company_user)
                        # Update priority if AI recommended a new one
                        if "ai_priority" in task_data:
                            t.priority = task_data["ai_priority"]
                        elif "priority" in task_data:
                            t.priority = task_data["priority"]
                        # Update status if provided
                        if "status" in task_data:
                            t.status = task_data["status"]
                        t.save()
                    except (Task.DoesNotExist, ValueError, TypeError):
                        continue

        return Response({"status": "success", "data": result}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("task_prioritization failed")
        return Response(
            {"status": "error", "message": "Task prioritization failed", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def generate_subtasks(request):
    """
    Subtask Generation Agent API - Only accessible to company users.
    Body:
      - project_id: int (required)
    """
    # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
    company_user = request.user
    
    # Check if user can access project manager features (project_manager or company_user role)
    # Use fallback if method doesn't exist (for server restart issues)
    can_access = False
    if hasattr(company_user, 'can_access_project_manager_features'):
        can_access = company_user.can_access_project_manager_features()
    else:
        # Fallback: check role directly
        can_access = company_user.role in ['project_manager', 'company_user']
    
    if not can_access:
        return Response(
            {"status": "error", "message": "Access denied. Project manager or company user role required."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        project_id = request.data.get("project_id")
        if not project_id:
            return Response(
                {"status": "error", "message": "project_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        agent = AgentRegistry.get_agent("subtask_generation")
        
        # Get company from company_user
        company = company_user.company
        
        get_object_or_404(Project, id=project_id, created_by_company_user=company_user)

        tasks_queryset = Task.objects.filter(project_id=project_id, project__created_by_company_user=company_user)
        
        # Filter out tasks that already have subtasks
        from core.models import Subtask
        tasks_with_subtasks = set(
            Subtask.objects.filter(task__project_id=project_id, task__project__created_by_company_user=company_user)
            .values_list('task_id', flat=True)
            .distinct()
        )
        
        tasks = [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description or "",
                "status": t.status,
                "priority": t.priority,
                "estimated_hours": float(t.estimated_hours) if t.estimated_hours else None,
            }
            for t in tasks_queryset
            if t.id not in tasks_with_subtasks  # Only include tasks without existing subtasks
        ]
        
        if not tasks:
            return Response(
                {"status": "success", "message": "All tasks already have subtasks. No new subtasks generated.", "data": {"saved_count": 0, "skipped_count": len(tasks_with_subtasks)}},
                status=status.HTTP_200_OK,
            )

        # Use 'generate_for_project' action and pass tasks
        result = agent.process(action="generate_for_project", tasks=tasks)
        
        # Transform result to match expected format
        if result.get("success") and result.get("subtasks_by_task"):
            # Convert subtasks_by_task dict to list format expected by frontend
            subtasks_list = []
            for task_id, subtask_data in result["subtasks_by_task"].items():
                subtasks_list.append({
                    "task_id": task_id,
                    "subtasks": subtask_data.get("subtasks", []),
                    "reasoning": subtask_data.get("task_reasoning", "")
                })
            result["subtasks"] = subtasks_list

        # Save generated subtasks
        saved_count = 0
        reasoning_updated_count = 0
        skipped_count = len(tasks_with_subtasks)
        
        for task_data in result.get("subtasks", []):
            task_id = task_data.get("task_id")
            subtasks_list = task_data.get("subtasks", [])
            reasoning = task_data.get("reasoning", "")

            if not task_id:
                continue

            try:
                task = Task.objects.get(id=task_id, project__created_by_company_user=company_user)
                
                # Skip if task already has subtasks (shouldn't happen, but double-check)
                if task.id in tasks_with_subtasks:
                    continue
                
                # Update AI reasoning if provided
                if reasoning:
                    reasoning_prefix = "[Subtask Generation Strategy] "
                    full_reasoning = reasoning_prefix + reasoning
                    if task.ai_reasoning:
                        task.ai_reasoning = task.ai_reasoning + "\n\n" + full_reasoning
                    else:
                        task.ai_reasoning = full_reasoning
                    task.save()
                    reasoning_updated_count += 1

                # Create new subtasks (don't delete existing - we already filtered them out)
                # Handle both string format (old) and dict format (new)
                for idx, subtask_item in enumerate(subtasks_list):
                    # Extract title and description from dict or use string directly
                    if isinstance(subtask_item, dict):
                        subtask_title = subtask_item.get('title', '')
                        subtask_description = subtask_item.get('description', '')
                        subtask_order = subtask_item.get('order', idx + 1)
                    else:
                        # Old format - string title
                        subtask_title = str(subtask_item)
                        subtask_description = ''
                        subtask_order = idx + 1
                    
                    if subtask_title:
                        Subtask.objects.create(
                            task=task,
                            title=subtask_title,
                            description=subtask_description,
                            order=subtask_order,
                            status='todo'
                        )
                        saved_count += 1

                continue
            except Task.DoesNotExist:
                continue
            except Exception as e:
                logger.error(f"Error saving subtasks for task {task_id}: {str(e)}")
                continue

        result["saved_count"] = saved_count
        result["reasoning_updated_count"] = reasoning_updated_count
        result["skipped_count"] = skipped_count
        return Response({"status": "success", "data": result}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("generate_subtasks failed")
        return Response(
            {"status": "error", "message": "Generate subtasks failed", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def timeline_gantt(request):
    """
    Timeline/Gantt Agent API - Only accessible to company users.
    Body:
      - action: create_timeline|generate_gantt_chart|check_deadlines|suggest_adjustments|calculate_duration|manage_phases
      - project_id: int (required)
      - days_ahead/current_progress/phases: optional depending on action
    
    """
    # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
    company_user = request.user
    
    # Check if user can access project manager features (project_manager or company_user role)
    # Use fallback if method doesn't exist (for server restart issues)
    can_access = False
    if hasattr(company_user, 'can_access_project_manager_features'):
        can_access = company_user.can_access_project_manager_features()
    else:
        # Fallback: check role directly
        can_access = company_user.role in ['project_manager', 'company_user']
    
    if not can_access:
        return Response(
            {"status": "error", "message": "Access denied. Project manager or company user role required."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        action = request.data.get("action")
        project_id = request.data.get("project_id")
        
        if not project_id:
            return Response(
                {"status": "error", "message": "project_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        project = get_object_or_404(Project, id=project_id, created_by_company_user=company_user)
        tasks_queryset = Task.objects.filter(project=project, project__created_by_company_user=company_user).prefetch_related('depends_on', 'assignee')
        
        # Get team size (unique assignees or team members)
        from core.models import TeamMember
        unique_assignees = set()
        for task in tasks_queryset:
            if task.assignee:
                unique_assignees.add(task.assignee.id)
        team_members_count = TeamMember.objects.filter(project=project, removed_at__isnull=True).count()
        team_size = max(len(unique_assignees), team_members_count, 1)

        tasks = [
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status,
                    "priority": t.priority,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "deadline": t.due_date.isoformat() if t.due_date else None,
                    "estimated_hours": float(t.estimated_hours) if t.estimated_hours else None,
                    "actual_hours": float(t.actual_hours) if t.actual_hours else None,
                    "dependencies": [dep.id for dep in t.depends_on.all()],
                    "assignee_id": t.assignee.id if t.assignee else None,
            }
            for t in tasks_queryset
        ]

        context = {
            "project": {
                "id": project.id,
                "name": project.name,
                "status": project.status,
                "start_date": project.start_date.isoformat() if project.start_date else None,
                "end_date": project.end_date.isoformat() if project.end_date else None,
                "deadline": project.deadline.isoformat() if project.deadline else None,
            },
            "tasks": tasks,
        }

        agent = AgentRegistry.get_agent("timeline_gantt")
        
        # Extract action-specific options from request.data, excluding action and project_id
        options = {k: v for k, v in request.data.items() 
                   if k not in ['action', 'project_id']}
        
        # Pass project_id and tasks as kwargs (required by agent.process)
        # Some actions need tasks from context
        # Add team_size for calculate_duration action
        if action == 'calculate_duration':
            options['team_size'] = team_size
        
        result = agent.process(
            action=action, 
            project_id=project_id, 
            tasks=context.get('tasks', []),
            context=context, 
            **options
        )

        # Apply timeline updates if provided
        if result.get("updates"):
            for update in result["updates"]:
                task_id = update.get("task_id")
                if task_id:
                    try:
                        t = Task.objects.get(id=task_id, project__created_by_company_user=company_user)
                        if "due_date" in update:
                            from django.utils import timezone
                            from datetime import datetime
                            try:
                                due_date = datetime.fromisoformat(update["due_date"].replace('Z', '+00:00'))
                                if timezone.is_naive(due_date):
                                    due_date = timezone.make_aware(due_date)
                                t.due_date = due_date
                            except Exception:
                                pass
                        if "estimated_hours" in update:
                            t.estimated_hours = update["estimated_hours"]
                        t.save()
                    except Task.DoesNotExist:
                        continue

        return Response({"status": "success", "data": result}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("timeline_gantt failed")
        return Response(
            {"status": "error", "message": "Timeline/Gantt failed", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([PMLLMThrottle])
def knowledge_qa(request):
    """
    Knowledge Q&A Agent API - Only accessible to company users.
    Body:
      - question: str (required)
      - project_id: int (optional)
    """
    # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
    company_user = request.user
    
    # Check if user can access project manager features (project_manager or company_user role)
    # Use fallback if method doesn't exist (for server restart issues)
    can_access = False
    if hasattr(company_user, 'can_access_project_manager_features'):
        can_access = company_user.can_access_project_manager_features()
    else:
        # Fallback: check role directly
        can_access = company_user.role in ['project_manager', 'company_user']
    
    if not can_access:
        return Response(
            {"status": "error", "message": "Access denied. Project manager or company user role required."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        question = request.data.get("question", "").strip()
        if not question:
            return Response(
                {"status": "error", "message": "question is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        project_id = request.data.get("project_id")
        
        all_projects = Project.objects.filter(created_by_company_user=company_user)
        all_tasks = Task.objects.filter(project__created_by_company_user=company_user).select_related("project", "assignee").prefetch_related("subtasks")
        
        # Get all users created by this company user
        from core.models import UserProfile
        created_user_profiles = UserProfile.objects.filter(
            created_by_company_user=company_user
        ).select_related('user')
        
        # Build available users list with their roles
        available_users = []
        for profile in created_user_profiles:
            user = profile.user
            available_users.append({
                'id': user.id,
                'username': user.username,
                'name': user.get_full_name() or user.username,
                'email': user.email,
                'role': profile.role or 'team_member',
                'is_active': user.is_active,
            })
        
        # Build user-task assignments information
        user_assignments = []
        for user_info in available_users:
            user_id = user_info['id']
            # Get tasks for this user
            if project_id:
                user_tasks = Task.objects.filter(
                    project_id=project_id, 
                    assignee_id=user_id,
                    project__created_by_company_user=company_user
                )
            else:
                user_tasks = all_tasks.filter(assignee_id=user_id)
            
            tasks_by_project = {}
            for task in user_tasks:
                project_name = task.project.name
                task_project_id = task.project.id
                if task_project_id not in tasks_by_project:
                    tasks_by_project[task_project_id] = {
                        'project_id': task_project_id,
                        'project_name': project_name,
                        'tasks': []
                    }
                tasks_by_project[task_project_id]['tasks'].append({
                    'id': task.id,
                    'title': task.title,
                    'status': task.status,
                    'priority': task.priority
                })
            
            user_assignments.append({
                'user_id': user_id,
                'username': user_info['username'],
                'name': user_info.get('name', user_info['username']),
                'role': user_info.get('role', 'team_member'),
                'email': user_info.get('email', ''),
                'total_tasks': user_tasks.count(),
                'projects': list(tasks_by_project.values())
            })

        if project_id:
            project = get_object_or_404(Project, id=project_id, created_by_company_user=company_user)
            tasks = Task.objects.filter(project=project).select_related("assignee").prefetch_related("subtasks")
            context = {
                "project": {
                    "id": project.id,
                    "name": project.name,
                    "description": project.description,
                    "status": project.status,
                    "priority": project.priority,
                "tasks": [
                    {
                        "id": t.id,
                        "title": t.title,
                        "status": t.status,
                        "priority": t.priority,
                        "description": t.description,
                        "assignee_id": t.assignee.id if t.assignee else None,
                        "assignee_username": t.assignee.username if t.assignee else None,
                        "subtasks": [
                            {
                                "id": st.id,
                                "title": st.title,
                                "status": st.status,
                                "order": st.order,
                            }
                            for st in t.subtasks.all()
                        ],
                    }
                    for t in tasks
                ],
                },
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
                "user_assignments": user_assignments,
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
                        "assignee_id": t.assignee.id if t.assignee else None,
                        "assignee_username": t.assignee.username if t.assignee else None,
                        "subtasks": [
                            {
                                "id": st.id,
                                "title": st.title,
                                "status": st.status,
                                "order": st.order,
                            }
                            for st in t.subtasks.all()
                        ],
                    }
                    for t in all_tasks[:50]
                ],
                "user_assignments": user_assignments,
            }

        # ========== RICH CONTEXT: include additional data based on question relevance ==========
        q_lower = question.lower()
        from core.models import (
            TaskActivityLog, TaskComment, TeamMember, TimeEntry,
            ProjectMilestone, ProjectRisk, ProjectIssue
        )

        # --- Activity logs (who changed what when) ---
        # Include if question mentions: changed, updated, modified, history, activity, log, status change, who, when
        activity_keywords = ['changed', 'updated', 'modified', 'history', 'activity', 'log', 'status change',
                             'who', 'when did', 'last change', 'recent change', 'what happened', 'timeline',
                             'assigned', 'reassigned', 'completed', 'moved', 'audit']
        if any(kw in q_lower for kw in activity_keywords):
            if project_id:
                activity_logs = TaskActivityLog.objects.filter(
                    task__project_id=project_id,
                    task__project__created_by_company_user=company_user
                ).select_related('task', 'user').order_by('-created_at')[:30]
            else:
                activity_logs = TaskActivityLog.objects.filter(
                    task__project__created_by_company_user=company_user
                ).select_related('task', 'user').order_by('-created_at')[:20]
            context["activity_logs"] = [
                {
                    "task_title": log.task.title if log.task else "Unknown",
                    "task_id": log.task_id,
                    "action_type": log.action_type,
                    "old_value": log.old_value,
                    "new_value": log.new_value,
                    "user": log.user.get_full_name() or log.user.username if log.user else "System",
                    "timestamp": log.created_at.strftime('%Y-%m-%d %H:%M') if log.created_at else None,
                    "details": log.details if hasattr(log, 'details') and log.details else None,
                }
                for log in activity_logs
            ]

        # --- Comments on tasks ---
        comment_keywords = ['comment', 'discussion', 'said', 'wrote', 'message', 'feedback', 'note']
        if any(kw in q_lower for kw in comment_keywords):
            if project_id:
                comments = TaskComment.objects.filter(
                    task__project_id=project_id,
                    task__project__created_by_company_user=company_user
                ).select_related('task', 'user').order_by('-created_at')[:20]
            else:
                comments = TaskComment.objects.filter(
                    task__project__created_by_company_user=company_user
                ).select_related('task', 'user').order_by('-created_at')[:15]
            context["comments"] = [
                {
                    "task_title": c.task.title if c.task else "Unknown",
                    "user": c.user.get_full_name() or c.user.username if c.user else "Unknown",
                    "comment": c.comment_text[:200] if c.comment_text else "",
                    "timestamp": c.created_at.strftime('%Y-%m-%d %H:%M') if c.created_at else None,
                }
                for c in comments
            ]

        # --- Team members ---
        team_keywords = ['team', 'member', 'who is', 'role', 'joined', 'part of']
        if any(kw in q_lower for kw in team_keywords):
            if project_id:
                members = TeamMember.objects.filter(
                    project_id=project_id,
                    project__created_by_company_user=company_user
                ).select_related('user')
            else:
                members = TeamMember.objects.filter(
                    project__created_by_company_user=company_user
                ).select_related('user', 'project')
            context["team_members"] = [
                {
                    "user": m.user.get_full_name() or m.user.username if m.user else "Unknown",
                    "role": m.role,
                    "project": m.project.name if hasattr(m, 'project') and m.project else None,
                    "joined_at": m.joined_at.strftime('%Y-%m-%d') if m.joined_at else None,
                }
                for m in members[:30]
            ]

        # --- Time entries ---
        time_keywords = ['time', 'hours', 'spent', 'tracked', 'timesheet', 'billable', 'effort']
        if any(kw in q_lower for kw in time_keywords):
            if project_id:
                entries = TimeEntry.objects.filter(
                    task__project_id=project_id,
                    task__project__created_by_company_user=company_user
                ).select_related('task', 'user').order_by('-date')[:20]
            else:
                entries = TimeEntry.objects.filter(
                    task__project__created_by_company_user=company_user
                ).select_related('task', 'user').order_by('-date')[:15]
            context["time_entries"] = [
                {
                    "task_title": e.task.title if e.task else "Unknown",
                    "user": e.user.get_full_name() or e.user.username if e.user else "Unknown",
                    "hours": float(e.hours) if e.hours else 0,
                    "date": e.date.strftime('%Y-%m-%d') if e.date else None,
                    "description": e.description[:100] if e.description else "",
                    "billable": e.billable,
                }
                for e in entries
            ]

        # --- Milestones ---
        milestone_keywords = ['milestone', 'deadline', 'target', 'goal', 'due', 'progress']
        if any(kw in q_lower for kw in milestone_keywords):
            if project_id:
                milestones = ProjectMilestone.objects.filter(
                    project_id=project_id,
                    project__created_by_company_user=company_user
                ).order_by('due_date')
            else:
                milestones = ProjectMilestone.objects.filter(
                    project__created_by_company_user=company_user
                ).select_related('project').order_by('due_date')[:15]
            context["milestones"] = [
                {
                    "title": ms.title,
                    "project": ms.project.name if hasattr(ms, 'project') and ms.project else None,
                    "due_date": ms.due_date.strftime('%Y-%m-%d') if ms.due_date else None,
                    "status": ms.status,
                    "completed_at": ms.completed_at.strftime('%Y-%m-%d') if ms.completed_at else None,
                }
                for ms in milestones
            ]

        # --- Risks & Issues ---
        risk_keywords = ['risk', 'issue', 'problem', 'blocker', 'blocked', 'impediment', 'concern', 'severity']
        if any(kw in q_lower for kw in risk_keywords):
            if project_id:
                risks = ProjectRisk.objects.filter(project_id=project_id, project__created_by_company_user=company_user)[:10]
                issues = ProjectIssue.objects.filter(project_id=project_id, project__created_by_company_user=company_user)[:10]
            else:
                risks = ProjectRisk.objects.filter(project__created_by_company_user=company_user).select_related('project')[:10]
                issues = ProjectIssue.objects.filter(project__created_by_company_user=company_user).select_related('project')[:10]
            context["risks"] = [
                {
                    "title": r.title,
                    "project": r.project.name if hasattr(r, 'project') and r.project else None,
                    "severity": r.severity,
                    "status": r.status,
                    "mitigation": r.mitigation_plan[:100] if r.mitigation_plan else None,
                }
                for r in risks
            ]
            context["issues"] = [
                {
                    "title": iss.title,
                    "project": iss.project.name if hasattr(iss, 'project') and iss.project else None,
                    "severity": iss.severity,
                    "status": iss.status,
                    "reported_by": iss.reported_by.get_full_name() if iss.reported_by else None,
                    "created_at": iss.created_at.strftime('%Y-%m-%d') if iss.created_at else None,
                }
                for iss in issues
            ]

        # ========== END RICH CONTEXT ==========

        # Enhanced: Get session_id for conversational memory
        session_id = request.data.get("session_id")
        if not session_id:
            # Generate session ID from company user ID
            session_id = f"company_user_{company_user.id}"

        chat_history = request.data.get("chat_history") or []
        agent = AgentRegistry.get_agent("knowledge_qa")
        agent.company_id = getattr(company_user, 'company_id', None)
        agent.agent_key_name = 'project_manager_agent'
        result = agent.process(
            question=question,
            context=context,
            available_users=available_users,
            session_id=session_id,
            chat_history=chat_history,
        )

        return Response({
            "status": "success", 
            "data": result,
            "session_id": session_id  # Return session_id for frontend to use
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("knowledge_qa failed")
        return Response(
            {"status": "error", "message": "Knowledge Q&A failed", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def _pm_build_analytics_data(company_user, project_id=None):
    """Build controlled aggregate data for graph generation (no sensitive free-text)."""
    projects_qs = Project.objects.filter(created_by_company_user=company_user)
    tasks_qs = Task.objects.filter(project__created_by_company_user=company_user)
    if project_id:
        projects_qs = projects_qs.filter(id=project_id)
        tasks_qs = tasks_qs.filter(project_id=project_id)

    projects_qs = projects_qs.order_by()
    tasks_qs = tasks_qs.order_by()

    projects_by_status = {}
    for item in projects_qs.values('status').annotate(count=Count('id')):
        if item.get('status'):
            projects_by_status[str(item['status'])] = item['count']

    projects_by_priority = {}
    for item in projects_qs.values('priority').annotate(count=Count('id')):
        if item.get('priority'):
            projects_by_priority[str(item['priority'])] = item['count']

    tasks_by_status = {}
    for item in tasks_qs.values('status').annotate(count=Count('id')):
        if item.get('status'):
            tasks_by_status[str(item['status'])] = item['count']

    tasks_by_priority = {}
    for item in tasks_qs.values('priority').annotate(count=Count('id')):
        if item.get('priority'):
            tasks_by_priority[str(item['priority'])] = item['count']

    tasks_by_project = {}
    for item in tasks_qs.values('project__name').annotate(count=Count('id')):
        name = item.get('project__name')
        if name:
            tasks_by_project[str(name)[:40]] = item['count']

    now = timezone.now()
    overdue_tasks_count = tasks_qs.filter(due_date__isnull=False, due_date__lt=now).exclude(status__in=['done', 'completed']).count()

    return {
        'projects_total': projects_qs.count(),
        'tasks_total': tasks_qs.count(),
        'overdue_tasks_count': overdue_tasks_count,
        'projects_by_status_obj': projects_by_status,
        'projects_by_priority_obj': projects_by_priority,
        'tasks_by_status_obj': tasks_by_status,
        'tasks_by_priority_obj': tasks_by_priority,
        'tasks_by_project_obj': tasks_by_project,
    }


def _pm_generate_chart_from_prompt(prompt: str, analytics_data: dict):
    system = f"""You are a data visualization assistant.

Return ONLY a single, valid JSON object (no prose, no markdown, no code fences).

The JSON schema must be:
{{
  "chart_type": "bar"|"pie"|"line"|"area"|"scatter"|"heatmap",
  "title": string,
  "data": object|array,
  "insights": string,
  "colors": [string],
  "orientation": "horizontal"|"vertical" (only for bar)
}}

CRITICAL:
- "data" MUST be literal JSON (objects/arrays/numbers) copied from the provided data summary.
- Do NOT reference variables or expressions like tasks_by_status_obj or tasks_by_project_obj["..."] in the output.
- If you want "tasks by status" then set data equal to the literal object shown for tasks_by_status_obj.
"""
    data_summary = f"""
PROJECT MANAGER DATA:
- Total projects: {analytics_data.get('projects_total', 0)}
- Total tasks: {analytics_data.get('tasks_total', 0)}
- Overdue tasks: {analytics_data.get('overdue_tasks_count', 0)}

Projects by status (use projects_by_status_obj for bar/pie): {json.dumps(analytics_data.get('projects_by_status_obj', {}))}
Projects by priority (use projects_by_priority_obj for bar/pie): {json.dumps(analytics_data.get('projects_by_priority_obj', {}))}

Tasks by status (use tasks_by_status_obj for bar/pie): {json.dumps(analytics_data.get('tasks_by_status_obj', {}))}
Tasks by priority (use tasks_by_priority_obj for bar/pie): {json.dumps(analytics_data.get('tasks_by_priority_obj', {}))}
Tasks by project (use tasks_by_project_obj for bar/pie): {json.dumps(analytics_data.get('tasks_by_project_obj', {}))}
"""

    system = """You are an AI that generates chart configurations for a project management dashboard.
Use ONLY the data provided below. Return ONLY a valid JSON object (no markdown, no explanation).

Output format:
{
  "chart_type": "bar" | "pie" | "line" | "area",
  "title": "Chart title",
  "data": either { "Label1": value1, "Label2": value2 } for bar/pie, OR [ { "label": "x", "value": y } ] for line/area,
  "insights": "Brief 1-2 sentence insight",
  "colors": ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"],
  "orientation": "horizontal" | "vertical"  (only for bar charts; omit for other types)
}

Rules:
- bar/pie: data must be object with string keys and number values.
- line/area: data must be array of objects with "label" and "value".
- Only use numbers from the provided data summary; do not invent values.
- For "projects by status" use projects_by_status_obj.
- For "projects by priority" use projects_by_priority_obj.
- For "tasks by status" use tasks_by_status_obj.
- For "tasks by priority" use tasks_by_priority_obj.
- For "tasks by project" use tasks_by_project_obj.
- If user asks "top N", limit to N items (sorted by value descending).
- Sort bar/pie by value descending unless chronological/alphabetical order is requested.
- Use "vertical" orientation when user asks for column chart, vertical bars, histogram, or columns.
"""

    agent = BaseAgent()
    raw = agent._call_llm(
        prompt=f"Generate a chart for: {prompt}",
        system_prompt=system + "\n\nAvailable data:\n" + data_summary,
        temperature=0.2,
        max_tokens=800,
    )
    raw = _pm_repair_llm_json(raw, analytics_data)
    chart_config = None
    try:
        chart_config = _pm_extract_first_json(raw)
    except Exception:
        try:
            raw_preview = (raw or "")
            raw_preview = raw_preview[:800] + ("..." if len(raw_preview) > 800 else "")
            logger.warning("PM graph: failed to parse chart JSON from LLM. raw=%s", raw_preview)
        except Exception:
            pass
        chart_config = {
            'chart_type': 'bar',
            'title': 'Tasks by Status',
            'data': analytics_data.get('tasks_by_status_obj') or {'No data': 0},
            'orientation': 'horizontal',
            'colors': ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"],
            'insights': 'Unable to parse a valid chart JSON from the model response. Showing a default chart instead.',
        }

    chart_type = chart_config.get('chart_type') or 'bar'
    title = chart_config.get('title') or 'Project Manager Graph'
    chart_data = chart_config.get('data')
    if chart_data is None:
        chart_data = analytics_data.get('tasks_by_status_obj') or {'No data': 0}
    colors = chart_config.get('colors') or ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"]

    chart_out = {
        'type': chart_type,
        'title': title,
        'data': chart_data,
        'colors': colors,
        'color': colors[0] if colors else '#3b82f6',
    }
    if chart_type == 'bar':
        chart_out['orientation'] = chart_config.get('orientation', 'horizontal')

    return {
        'chart': chart_out,
        'insights': chart_config.get('insights') or '',
    }


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def pm_generate_graph(request):
    """Generate a chart from a natural language prompt using project/task aggregates."""
    try:
        company_user = request.user

        prompt = (request.data.get('prompt') or '').strip() if isinstance(getattr(request, 'data', None), dict) else ''
        if not prompt:
            return Response({'status': 'error', 'message': 'prompt is required'}, status=status.HTTP_400_BAD_REQUEST)

        project_id = request.data.get('project_id') if isinstance(getattr(request, 'data', None), dict) else None
        if project_id in ['', None, 'all']:
            project_id = None
        if project_id is not None:
            try:
                project_id = int(project_id)
            except Exception:
                project_id = None

        analytics_data = _pm_build_analytics_data(company_user, project_id=project_id)
        result = _pm_generate_chart_from_prompt(prompt, analytics_data)

        return Response({
            'status': 'success',
            'data': {
                'chart': result.get('chart'),
                'insights': result.get('insights', ''),
            }
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("pm_generate_graph failed")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------- PM Knowledge QA Chats ----------

@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_knowledge_qa_chats(request):
    """List all Knowledge QA chats for the company user."""
    try:
        company_user = request.user
        limit = min(int(request.GET.get('limit', 50)), 100)
        offset = max(int(request.GET.get('offset', 0)), 0)
        chats = PMKnowledgeQAChat.objects.filter(company_user=company_user).prefetch_related('messages').order_by('-updated_at')[offset:offset + limit]
        result = []
        for chat in chats:
            messages = []
            for msg in chat.messages.order_by('created_at'):
                m = {'role': msg.role, 'content': msg.content}
                if msg.response_data:
                    m['responseData'] = msg.response_data
                messages.append(m)
            result.append({
                'id': str(chat.id),
                'title': chat.title or 'Chat',
                'messages': messages,
                'updatedAt': chat.updated_at.isoformat(),
                'timestamp': chat.updated_at.isoformat(),
            })
        return Response({'status': 'success', 'data': result})
    except Exception as e:
        logger.exception("list_knowledge_qa_chats error")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_knowledge_qa_chat(request):
    """Create a new Knowledge QA chat with optional initial messages."""
    try:
        company_user = request.user
        data = request.data if isinstance(request.data, dict) else {}
        title = (data.get('title') or 'Chat')[:255]
        messages_data = data.get('messages') or []
        chat = PMKnowledgeQAChat.objects.create(company_user=company_user, title=title)
        for m in messages_data:
            PMKnowledgeQAChatMessage.objects.create(
                chat=chat,
                role=m.get('role', 'user'),
                content=m.get('content', ''),
                response_data=m.get('responseData'),
            )
        chat.refresh_from_db()
        messages = []
        for msg in chat.messages.order_by('created_at'):
            msg_dict = {'role': msg.role, 'content': msg.content}
            if msg.response_data:
                msg_dict['responseData'] = msg.response_data
            messages.append(msg_dict)
        return Response({
            'status': 'success',
            'data': {
                'id': str(chat.id),
                'title': chat.title,
                'messages': messages,
                'updatedAt': chat.updated_at.isoformat(),
                'timestamp': chat.updated_at.isoformat(),
            },
        })
    except Exception as e:
        logger.exception("create_knowledge_qa_chat error")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["PATCH", "PUT"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_knowledge_qa_chat(request, chat_id):
    """Update a Knowledge QA chat: add messages, optionally update title."""
    try:
        company_user = request.user
        chat = PMKnowledgeQAChat.objects.filter(company_user=company_user, id=chat_id).first()
        if not chat:
            return Response({'status': 'error', 'message': 'Chat not found.'}, status=status.HTTP_404_NOT_FOUND)
        data = request.data if isinstance(request.data, dict) else {}
        if data.get('title'):
            chat.title = str(data['title'])[:255]
            chat.save(update_fields=['title', 'updated_at'])
        messages_data = data.get('messages')
        if messages_data is not None:
            for m in messages_data:
                PMKnowledgeQAChatMessage.objects.create(
                    chat=chat,
                    role=m.get('role', 'user'),
                    content=m.get('content', ''),
                    response_data=m.get('responseData'),
                )
        chat.refresh_from_db()
        messages = []
        for msg in chat.messages.order_by('created_at'):
            msg_dict = {'role': msg.role, 'content': msg.content}
            if msg.response_data:
                msg_dict['responseData'] = msg.response_data
            messages.append(msg_dict)
        return Response({
            'status': 'success',
            'data': {
                'id': str(chat.id),
                'title': chat.title,
                'messages': messages,
                'updatedAt': chat.updated_at.isoformat(),
                'timestamp': chat.updated_at.isoformat(),
            },
        })
    except Exception as e:
        logger.exception("update_knowledge_qa_chat error")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["DELETE"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_knowledge_qa_chat(request, chat_id):
    """Delete a Knowledge QA chat and all its messages."""
    try:
        company_user = request.user
        chat = PMKnowledgeQAChat.objects.filter(company_user=company_user, id=chat_id).first()
        if not chat:
            return Response({'status': 'error', 'message': 'Chat not found.'}, status=status.HTTP_404_NOT_FOUND)
        chat.delete()
        return Response({'status': 'success', 'message': 'Chat deleted.'})
    except Exception as e:
        logger.exception("delete_knowledge_qa_chat error")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------- PM Project Pilot Chats ----------

@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_project_pilot_chats(request):
    """List all Project Pilot chats for the company user."""
    try:
        company_user = request.user
        limit = min(int(request.GET.get('limit', 50)), 100)
        offset = max(int(request.GET.get('offset', 0)), 0)
        chats = PMProjectPilotChat.objects.filter(company_user=company_user).prefetch_related('messages').order_by('-updated_at')[offset:offset + limit]
        result = []
        for chat in chats:
            messages = []
            for msg in chat.messages.order_by('created_at'):
                m = {'role': msg.role, 'content': msg.content}
                if msg.response_data:
                    m['responseData'] = msg.response_data
                messages.append(m)
            result.append({
                'id': str(chat.id),
                'title': chat.title or 'Chat',
                'messages': messages,
                'updatedAt': chat.updated_at.isoformat(),
                'timestamp': chat.updated_at.isoformat(),
            })
        return Response({'status': 'success', 'data': result})
    except Exception as e:
        logger.exception("list_project_pilot_chats error")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_project_pilot_chat(request):
    """Create a new Project Pilot chat with optional initial messages."""
    try:
        company_user = request.user
        data = request.data if isinstance(request.data, dict) else {}
        title = (data.get('title') or 'Chat')[:255]
        messages_data = data.get('messages') or []
        chat = PMProjectPilotChat.objects.create(company_user=company_user, title=title)
        for m in messages_data:
            PMProjectPilotChatMessage.objects.create(
                chat=chat,
                role=m.get('role', 'user'),
                content=m.get('content', ''),
                response_data=m.get('responseData'),
            )
        chat.refresh_from_db()
        messages = []
        for msg in chat.messages.order_by('created_at'):
            msg_dict = {'role': msg.role, 'content': msg.content}
            if msg.response_data:
                msg_dict['responseData'] = msg.response_data
            messages.append(msg_dict)
        return Response({
            'status': 'success',
            'data': {
                'id': str(chat.id),
                'title': chat.title,
                'messages': messages,
                'updatedAt': chat.updated_at.isoformat(),
                'timestamp': chat.updated_at.isoformat(),
            },
        })
    except Exception as e:
        logger.exception("create_project_pilot_chat error")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["PATCH", "PUT"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_project_pilot_chat(request, chat_id):
    """Update a Project Pilot chat: add messages, optionally update title."""
    try:
        company_user = request.user
        chat = PMProjectPilotChat.objects.filter(company_user=company_user, id=chat_id).first()
        if not chat:
            return Response({'status': 'error', 'message': 'Chat not found.'}, status=status.HTTP_404_NOT_FOUND)
        data = request.data if isinstance(request.data, dict) else {}
        if data.get('title'):
            chat.title = str(data['title'])[:255]
            chat.save(update_fields=['title', 'updated_at'])
        messages_data = data.get('messages')
        if messages_data is not None:
            for m in messages_data:
                PMProjectPilotChatMessage.objects.create(
                    chat=chat,
                    role=m.get('role', 'user'),
                    content=m.get('content', ''),
                    response_data=m.get('responseData'),
                )
        chat.refresh_from_db()
        messages = []
        for msg in chat.messages.order_by('created_at'):
            msg_dict = {'role': msg.role, 'content': msg.content}
            if msg.response_data:
                msg_dict['responseData'] = msg.response_data
            messages.append(msg_dict)
        return Response({
            'status': 'success',
            'data': {
                'id': str(chat.id),
                'title': chat.title,
                'messages': messages,
                'updatedAt': chat.updated_at.isoformat(),
                'timestamp': chat.updated_at.isoformat(),
            },
        })
    except Exception as e:
        logger.exception("update_project_pilot_chat error")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["DELETE"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_project_pilot_chat(request, chat_id):
    """Delete a Project Pilot chat and all its messages."""
    try:
        company_user = request.user
        chat = PMProjectPilotChat.objects.filter(company_user=company_user, id=chat_id).first()
        if not chat:
            return Response({'status': 'error', 'message': 'Chat not found.'}, status=status.HTTP_404_NOT_FOUND)
        chat.delete()
        return Response({'status': 'success', 'message': 'Chat deleted.'})
    except Exception as e:
        logger.exception("delete_project_pilot_chat error")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_project_manual(request):
    """
    Manually create a project - Only accessible to company users.
    Body:
      - name: str (required)
      - description: str (optional)
      - status: str (optional, default: 'planning')
      - priority: str (optional, default: 'medium')
      - project_type: str (optional, default: 'web_app')
      - industry_id: int (optional)
      - budget_min: decimal (optional)
      - budget_max: decimal (optional)
      - deadline: date (optional, format: YYYY-MM-DD)
      - start_date: date (optional, format: YYYY-MM-DD)
      - end_date: date (optional, format: YYYY-MM-DD)
    """
    company_user = request.user
    company = company_user.company
    
    try:
        name = request.data.get('name', '').strip()
        if not name:
            return Response({
                'status': 'error',
                'message': 'Project name is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get optional fields
        description = request.data.get('description', '').strip()
        status_val = request.data.get('status', 'planning')
        priority_val = request.data.get('priority', 'medium')
        project_type = request.data.get('project_type', 'web_app')
        industry_id = request.data.get('industry_id')
        budget_min = request.data.get('budget_min')
        budget_max = request.data.get('budget_max')
        deadline = request.data.get('deadline')
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        
        # Validate status and priority
        valid_statuses = ['planning', 'active', 'on_hold', 'completed', 'cancelled', 'draft', 'posted', 'in_progress', 'review']
        valid_priorities = ['low', 'medium', 'high', 'urgent']
        valid_project_types = ['website', 'mobile_app', 'web_app', 'ai_bot', 'integration', 'marketing', 'database', 'consulting', 'ai_system']
        
        if status_val not in valid_statuses:
            return Response({
                'status': 'error',
                'message': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if priority_val not in valid_priorities:
            return Response({
                'status': 'error',
                'message': f'Invalid priority. Must be one of: {", ".join(valid_priorities)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if project_type not in valid_project_types:
            return Response({
                'status': 'error',
                'message': f'Invalid project_type. Must be one of: {", ".join(valid_project_types)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get project owner from company user's project users
        default_owner = _get_project_owner(company_user)
        if not default_owner:
            return Response({
                'status': 'error',
                'message': 'Could not determine project owner. Please create at least one project user first.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Build project data
        project_data = {
            'name': name,
            'description': description,
            'company': company,
            'created_by_company_user': company_user,
            'owner': default_owner,
            'status': status_val,
            'priority': priority_val,
            'project_type': project_type,
        }
        
        # Add optional fields
        if industry_id:
            try:
                from core.models import Industry
                industry = Industry.objects.get(id=industry_id)
                project_data['industry'] = industry
            except Industry.DoesNotExist:
                return Response({
                    'status': 'error',
                    'message': 'Invalid industry_id'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        if budget_min:
            val, err = _validate_positive_number(budget_min, 'budget_min')
            if err:
                return Response({'status': 'error', 'message': err}, status=status.HTTP_400_BAD_REQUEST)
            project_data['budget_min'] = val

        if budget_max:
            val, err = _validate_positive_number(budget_max, 'budget_max')
            if err:
                return Response({'status': 'error', 'message': err}, status=status.HTTP_400_BAD_REQUEST)
            project_data['budget_max'] = val
        
        # Parse dates
        from datetime import datetime
        if deadline:
            try:
                project_data['deadline'] = datetime.strptime(deadline, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    'status': 'error',
                    'message': 'Invalid deadline format. Use YYYY-MM-DD'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        if start_date:
            try:
                project_data['start_date'] = datetime.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    'status': 'error',
                    'message': 'Invalid start_date format. Use YYYY-MM-DD'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        if end_date:
            try:
                project_data['end_date'] = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    'status': 'error',
                    'message': 'Invalid end_date format. Use YYYY-MM-DD'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create project
        project = Project.objects.create(**project_data)
        _audit_log(company_user, 'project_created', 'Project', project.id, project.name)

        return Response({
            'status': 'success',
            'message': 'Project created successfully',
            'data': {
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'status': project.status,
                'priority': project.priority,
                'project_type': project.project_type,
                'created_at': project.created_at.isoformat(),
            }
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        logger.exception("create_project_manual failed")
        return Response({
            'status': 'error',
            'message': 'Failed to create project',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_task_manual(request):
    """
    Manually create a task - Only accessible to company users.
    Body:
      - project_id: int (required)
      - title: str (required)
      - description: str (optional)
      - status: str (optional, default: 'todo')
      - priority: str (optional, default: 'medium')
      - assignee_id: int (optional)
      - due_date: datetime (optional, format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
      - estimated_hours: float (optional)
    """
    company_user = request.user
    
    try:
        project_id = request.data.get('project_id')
        if not project_id:
            return Response({
                'status': 'error',
                'message': 'project_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verify project belongs to company user
        project = get_object_or_404(Project, id=project_id, created_by_company_user=company_user)
        
        title = request.data.get('title', '').strip()
        if not title:
            return Response({
                'status': 'error',
                'message': 'Task title is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get optional fields
        description = request.data.get('description', '').strip()
        status_val = request.data.get('status', 'todo')
        priority_val = request.data.get('priority', 'medium')
        assignee_id = request.data.get('assignee_id')
        due_date_str = request.data.get('due_date')
        estimated_hours = request.data.get('estimated_hours')
        
        # Validate status and priority
        valid_statuses = ['todo', 'in_progress', 'review', 'done', 'blocked']
        valid_priorities = ['low', 'medium', 'high']
        
        if status_val not in valid_statuses:
            return Response({
                'status': 'error',
                'message': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if priority_val not in valid_priorities:
            return Response({
                'status': 'error',
                'message': f'Invalid priority. Must be one of: {", ".join(valid_priorities)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Build task data
        task_data = {
            'title': title,
            'description': description,
            'project': project,
            'status': status_val,
            'priority': priority_val,
        }
        
        # Handle assignee
        if assignee_id:
            try:
                from django.contrib.auth.models import User
                assignee = User.objects.get(id=assignee_id)
                task_data['assignee'] = assignee
            except User.DoesNotExist:
                return Response({
                    'status': 'error',
                    'message': 'Invalid assignee_id'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse due date
        if due_date_str:
            try:
                from django.utils import timezone
                from datetime import datetime as dt_time
                # Try parsing different formats
                due_date = None
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
                    try:
                        date_only = datetime.strptime(due_date_str.split('T')[0], '%Y-%m-%d').date()
                        due_date = datetime.combine(date_only, dt_time(23, 59, 59))
                        if timezone.is_naive(due_date):
                            due_date = timezone.make_aware(due_date)
                    except ValueError:
                        pass
                
                if due_date:
                    task_data['due_date'] = due_date
            except Exception as e:
                logger.warning(f"Failed to parse due_date: {e}")
        
        # Handle estimated hours
        if estimated_hours:
            try:
                task_data['estimated_hours'] = float(estimated_hours)
            except (ValueError, TypeError):
                return Response({
                    'status': 'error',
                    'message': 'Invalid estimated_hours value'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create task
        task = Task.objects.create(**task_data)
        
        return Response({
            'status': 'success',
            'message': 'Task created successfully',
            'data': {
                'id': task.id,
                'title': task.title,
                'description': task.description,
                'status': task.status,
                'priority': task.priority,
                'project_id': project.id,
                'project_name': project.name,
                'assignee_id': task.assignee.id if task.assignee else None,
                'due_date': task.due_date.isoformat() if task.due_date else None,
                'deadline': task.due_date.isoformat() if task.due_date else None,
                'estimated_hours': task.estimated_hours,
                'created_at': task.created_at.isoformat(),
            }
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        logger.exception("create_task_manual failed")
        return Response({
            'status': 'error',
            'message': 'Failed to create task',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_available_users(request):
    """
    Get list of available users for task assignment - Only accessible to company users.
    Query params:
      - project_id: int (optional) - If provided, returns team members + owner for that project
    """
    company_user = request.user
    
    try:
        project_id = request.GET.get('project_id')
        project = None
        
        if project_id:
            try:
                project_id = int(project_id)
                project = get_object_or_404(Project, id=project_id, created_by_company_user=company_user)
            except (ValueError, Project.DoesNotExist):
                return Response({
                    'status': 'error',
                    'message': 'Invalid project_id'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Use the existing _build_available_users function
        available_users = _build_available_users(project_id=project_id, project=project, company_user=company_user)
        
        return Response({
            'status': 'success',
            'data': available_users
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.exception("get_available_users failed")
        return Response({
            'status': 'error',
            'message': 'Failed to fetch users',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Magic bytes for file type validation
FILE_MAGIC_BYTES = {
    '.pdf': b'%PDF',
    '.docx': b'PK',  # DOCX is a ZIP file
}


def _extract_text_from_file(file):
    """
    Extract text from uploaded file.
    Supports: .txt, .pdf, .docx
    Validates file size, magic bytes, and sanitizes output.
    """
    # Server-side file size check
    if hasattr(file, 'size') and file.size > MAX_FILE_SIZE:
        raise ValueError(f"File too large ({file.size // (1024*1024)}MB). Maximum is 10MB.")

    file_extension = os.path.splitext(file.name)[1].lower()

    # Validate magic bytes for PDF and DOCX
    if file_extension in FILE_MAGIC_BYTES:
        file.seek(0)
        header = file.read(4)
        file.seek(0)
        expected = FILE_MAGIC_BYTES[file_extension]
        if not header.startswith(expected):
            raise ValueError(f"File content does not match {file_extension} format. The file may be corrupted or mislabeled.")

    text = ""

    try:
        if file_extension == '.txt':
            # Read text file
            file.seek(0)
            text = file.read().decode('utf-8', errors='ignore')
        
        elif file_extension == '.pdf' and PDF_AVAILABLE:
            # Extract text from PDF
            file.seek(0)
            pdf_reader = PyPDF2.PdfReader(file)
            text_parts = []
            for page in pdf_reader.pages:
                text_parts.append(page.extract_text())
            text = "\n".join(text_parts)
        
        elif file_extension == '.docx' and DOCX_AVAILABLE:
            # Extract text from DOCX
            file.seek(0)
            # Save to temp file for docx library
            with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp_file:
                for chunk in file.chunks():
                    tmp_file.write(chunk)
                tmp_file_path = tmp_file.name
            
            try:
                doc = Document(tmp_file_path)
                text_parts = []
                for paragraph in doc.paragraphs:
                    text_parts.append(paragraph.text)
                text = "\n".join(text_parts)
            finally:
                # Clean up temp file
                if os.path.exists(tmp_file_path):
                    os.unlink(tmp_file_path)
        
        else:
            raise ValueError(f"Unsupported file type: {file_extension}. Supported types: .txt, .pdf, .docx")
        
        # Sanitize: strip control chars, truncate to prevent LLM token overflow
        text = text.strip()
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)  # Remove control chars (keep \n, \r, \t)
        if len(text) > 50000:
            text = text[:50000] + "\n\n[... text truncated at 50,000 characters ...]"
        return text

    except ValueError:
        raise  # Re-raise validation errors as-is
    except Exception as e:
        logger.exception(f"Error extracting text from file: {file.name}")
        raise ValueError(f"Failed to extract text from file. Please ensure the file is not corrupted.")


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def project_pilot_from_file(request):
    """
    Project Pilot Agent API - Process file upload and extract text, then process through project pilot.
    Body (multipart/form-data):
      - file: file (required) - txt, pdf, or docx file
      - project_id: int (optional)
    """
    company_user = request.user
    
    # Check if user can access project manager features
    can_access = False
    if hasattr(company_user, 'can_access_project_manager_features'):
        can_access = company_user.can_access_project_manager_features()
    else:
        can_access = company_user.role in ['project_manager', 'company_user']
    
    if not can_access:
        return Response(
            {"status": "error", "message": "Access denied. Project manager or company user role required."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        # Get uploaded file
        if 'file' not in request.FILES:
            return Response(
                {"status": "error", "message": "file is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        uploaded_file = request.FILES['file']
        
        # Validate file type
        allowed_extensions = ['.txt', '.pdf', '.docx']
        file_extension = os.path.splitext(uploaded_file.name)[1].lower()
        if file_extension not in allowed_extensions:
            return Response(
                {"status": "error", "message": f"Unsupported file type. Allowed types: {', '.join(allowed_extensions)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Extract text from file
        try:
            extracted_text = _extract_text_from_file(uploaded_file)
        except ValueError as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        if not extracted_text:
            return Response(
                {"status": "error", "message": "No text could be extracted from the file"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Use the extracted text as the question for project pilot
        question = extracted_text
        project_id = request.POST.get("project_id")
        
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

        chat_history = _get_chat_history(request)
        agent = AgentRegistry.get_agent("project_pilot")
        # Route LLM call through the company key/quota resolver. Resolver will
        # raise QuotaExhausted (402) or NoKeyAvailable (403) on hard-block —
        # core/drf_exceptions converts those to clean JSON responses.
        agent.company_id = getattr(company_user, 'company_id', None)
        agent.agent_key_name = 'project_manager_agent'
        result = agent.process(question=question, context=context, available_users=available_users, chat_history=chat_history)
        if result.get("cannot_do"):
            return Response({"status": "success", "data": result}, status=status.HTTP_200_OK)

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
                    
                    # Parse dates
                    start_date = action.get("start_date")
                    end_date = action.get("end_date")
                    deadline = action.get("deadline")
                    
                    if start_date and isinstance(start_date, str):
                        try:
                            from datetime import datetime
                            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                        except (ValueError, TypeError):
                            logger.debug(f"Failed to parse start_date: {start_date}")
                            start_date = None

                    if end_date and isinstance(end_date, str):
                        try:
                            from datetime import datetime
                            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                        except (ValueError, TypeError):
                            logger.debug(f"Failed to parse end_date: {end_date}")
                            end_date = None

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
                        end_date=end_date,
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

        logger.info(f"Returning project_pilot_from_file response with {len(action_results)} action results")
        return Response({
            "status": "success",
            "data": {
                "answer": result.get("answer", ""),
                "action_results": action_results,
                "extracted_text_preview": extracted_text[:200] + "..." if len(extracted_text) > 200 else extracted_text,
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("project_pilot_from_file failed")
        return Response(
            {"status": "error", "message": "Failed to process file", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ==================== DAILY STANDUP ENDPOINT ====================

@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def daily_standup(request):
    """Generate daily or weekly standup report for a project."""
    try:
        company_user = request.user
        if not company_user.can_access_project_manager_features():
            return Response({"status": "error", "message": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

        project_id = request.data.get("project_id")
        action = request.data.get("action", "daily")  # "daily" or "weekly"

        # Gather project data
        project_info = None
        tasks_data = []
        if project_id:
            try:
                project = Project.objects.get(id=project_id, created_by_company_user=company_user)
                project_info = {"id": project.id, "name": project.name, "status": project.status}
                tasks = Task.objects.filter(project=project).select_related('assignee')
            except Project.DoesNotExist:
                return Response({"status": "error", "message": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
        else:
            tasks = Task.objects.filter(project__created_by_company_user=company_user).select_related('assignee', 'project')

        for t in tasks:
            tasks_data.append({
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "assignee_username": t.assignee.username if t.assignee else None,
                "assignee_name": (t.assignee.get_full_name() or t.assignee.username) if t.assignee else None,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "deadline": t.due_date.isoformat() if t.due_date else None,
                "project_name": t.project.name if hasattr(t, 'project') and t.project else None,
            })

        # Get available users
        available_users = _build_available_users(company_user=company_user)

        # Get recent activity logs
        activity_logs_data = []
        try:
            from core.models import TaskActivityLog
            if project_id:
                logs = TaskActivityLog.objects.filter(
                    task__project_id=project_id,
                    task__project__created_by_company_user=company_user
                ).select_related('task', 'user').order_by('-created_at')[:30]
            else:
                logs = TaskActivityLog.objects.filter(
                    task__project__created_by_company_user=company_user
                ).select_related('task', 'user').order_by('-created_at')[:20]

            for log in logs:
                activity_logs_data.append({
                    "task_title": log.task.title if log.task else "Unknown",
                    "action_type": log.action_type,
                    "old_value": log.old_value,
                    "new_value": log.new_value,
                    "user": log.user.get_full_name() or log.user.username if log.user else "System",
                    "timestamp": log.created_at.strftime('%Y-%m-%d %H:%M') if log.created_at else None,
                })
        except Exception:
            pass

        agent = AgentRegistry.get_agent("daily_standup")
        result = agent.process(
            action=action,
            tasks=tasks_data,
            team_members=available_users,
            activity_logs=activity_logs_data,
            project_info=project_info,
        )

        return Response({
            "status": "success",
            "data": result,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("daily_standup failed")
        return Response(
            {"status": "error", "message": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ==================== PROJECT HEALTH SCORE ENDPOINT ====================

@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def project_health_score(request):
    """Calculate project health score and risk analysis."""
    try:
        company_user = request.user
        if not company_user.can_access_project_manager_features():
            return Response({"status": "error", "message": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

        project_id = request.data.get("project_id")
        action = request.data.get("action", "health")  # "health", "risks", "report", "metrics"

        if not project_id:
            return Response({"status": "error", "message": "project_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        agent = AgentRegistry.get_agent("analytics_dashboard")
        result = agent.process(
            action=action,
            project_id=project_id,
            company_user=company_user,
        )

        return Response({
            "status": "success",
            "data": result,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("project_health_score failed")
        return Response(
            {"status": "error", "message": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ==================== STATUS REPORT ENDPOINT ====================

@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def project_status_report(request):
    """Generate comprehensive project status report."""
    try:
        company_user = request.user
        if not company_user.can_access_project_manager_features():
            return Response({"status": "error", "message": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

        project_id = request.data.get("project_id")
        if not project_id:
            return Response({"status": "error", "message": "project_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        agent = AgentRegistry.get_agent("analytics_dashboard")
        result = agent.process(
            action="report",
            project_id=project_id,
            company_user=company_user,
        )

        return Response({
            "status": "success",
            "data": result,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("project_status_report failed")
        return Response(
            {"status": "error", "message": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ==================== MEETING NOTES ENDPOINT ====================

@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def meeting_notes(request):
    """Process meeting notes and extract action items."""
    try:
        company_user = request.user
        if not company_user.can_access_project_manager_features():
            return Response({"status": "error", "message": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

        meeting_text = request.data.get("meeting_text", "")
        action = request.data.get("action", "summarize")  # "summarize" or "extract_actions"
        project_id = request.data.get("project_id")

        if not meeting_text:
            return Response({"status": "error", "message": "meeting_text is required"}, status=status.HTTP_400_BAD_REQUEST)

        meeting_info = {
            "date": request.data.get("date"),
            "participants": request.data.get("participants", []),
            "topic": request.data.get("topic"),
        }

        project_context = None
        if project_id:
            try:
                project = Project.objects.get(id=project_id, created_by_company_user=company_user)
                tasks = Task.objects.filter(project=project).select_related('assignee')
                # Collect unique team members assigned to tasks in this project
                team_members = set()
                for t in tasks:
                    if t.assignee:
                        display_name = t.assignee.get_full_name() or t.assignee.username
                        team_members.add(display_name)
                project_context = {
                    "name": project.name,
                    "status": project.status,
                    "tasks": [{"title": t.title, "status": t.status, "assignee": (t.assignee.get_full_name() or t.assignee.username) if t.assignee else None} for t in tasks[:20]],
                    "team_members": list(team_members),
                }
            except Project.DoesNotExist:
                pass

        agent = AgentRegistry.get_agent("meeting_notetaker")
        result = agent.process(
            action=action,
            meeting_text=meeting_text,
            meeting_info=meeting_info,
            project_context=project_context,
        )

        return Response({
            "status": "success",
            "data": result,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("meeting_notes failed")
        return Response(
            {"status": "error", "message": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ==================== WORKFLOW SUGGESTION ENDPOINT ====================

@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def workflow_suggest(request):
    """Suggest workflows and checklists for a project."""
    try:
        company_user = request.user
        if not company_user.can_access_project_manager_features():
            return Response({"status": "error", "message": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

        project_id = request.data.get("project_id")
        action = request.data.get("action", "suggest")  # "suggest", "checklist", "validate"

        if not project_id:
            return Response({"status": "error", "message": "project_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            project = Project.objects.get(id=project_id, created_by_company_user=company_user)
        except Project.DoesNotExist:
            return Response({"status": "error", "message": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

        project_info = {
            "name": project.name,
            "status": project.status,
            "priority": project.priority,
            "project_type": project.project_type,
            "description": project.description,
        }

        tasks = Task.objects.filter(project=project).select_related('assignee')
        tasks_data = [{
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
        } for t in tasks]

        agent = AgentRegistry.get_agent("workflow_sop")
        result = agent.process(
            action=action,
            project_info=project_info,
            tasks=tasks_data,
            phase=request.data.get("phase", "development"),
            project_type=project.project_type or "software_development",
        )

        return Response({
            "status": "success",
            "data": result,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("workflow_suggest failed")
        return Response(
            {"status": "error", "message": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ==================== CALENDAR SCHEDULE ENDPOINT ====================

@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def calendar_schedule(request):
    """Generate optimized task schedules and detect conflicts."""
    try:
        company_user = request.user
        if not company_user.can_access_project_manager_features():
            return Response({"status": "error", "message": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

        project_id = request.data.get("project_id")
        action = request.data.get("action", "schedule")  # "schedule" or "conflicts"

        if not project_id:
            return Response({"status": "error", "message": "project_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            project = Project.objects.get(id=project_id, created_by_company_user=company_user)
        except Project.DoesNotExist:
            return Response({"status": "error", "message": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

        tasks = Task.objects.filter(project=project).select_related('assignee')
        tasks_data = [{
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "assignee_username": t.assignee.username if t.assignee else None,
            "assignee_name": (t.assignee.get_full_name() or t.assignee.username) if t.assignee else None,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "deadline": t.due_date.isoformat() if t.due_date else None,
        } for t in tasks]

        available_users = _build_available_users(company_user=company_user)

        agent = AgentRegistry.get_agent("calendar_planner")
        result = agent.process(
            action=action,
            tasks=tasks_data,
            team_members=available_users,
            start_date=request.data.get("start_date"),
            end_date=request.data.get("end_date"),
        )

        return Response({
            "status": "success",
            "data": result,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("calendar_schedule failed")
        return Response(
            {"status": "error", "message": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ==================== SMART NOTIFICATIONS ENDPOINTS ====================

@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def scan_notifications(request):
    """Scan projects for issues and generate smart notifications."""
    try:
        company_user = request.user
        if not company_user.can_access_project_manager_features():
            return Response({"status": "error", "message": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

        project_id = request.data.get("project_id")

        # Get projects to scan
        if project_id:
            projects = Project.objects.filter(id=project_id, created_by_company_user=company_user)
        else:
            projects = Project.objects.filter(created_by_company_user=company_user)

        all_notifications = []
        agent = AgentRegistry.get_agent("smart_notifications")
        available_users = _build_available_users(company_user=company_user)

        for project in projects:
            tasks = Task.objects.filter(project=project).select_related('assignee')
            tasks_data = [{
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "assignee_username": t.assignee.username if t.assignee else None,
                "assignee_name": (t.assignee.get_full_name() or t.assignee.username) if t.assignee else None,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "deadline": t.due_date.isoformat() if t.due_date else None,
            } for t in tasks]

            project_info = {
                "id": project.id,
                "name": project.name,
                "status": project.status,
                "deadline": project.deadline.isoformat() if project.deadline else None,
                "end_date": project.end_date.isoformat() if project.end_date else None,
            }

            result = agent.scan_project(project_info, tasks_data, available_users)
            if result.get("success") and result.get("notifications"):
                # Save notifications to DB
                for notif in result["notifications"]:
                    PMNotification.objects.create(
                        company_user=company_user,
                        project=project,
                        notification_type=notif["type"],
                        severity=notif["severity"],
                        title=notif["title"],
                        message=notif["message"],
                        data=notif.get("data"),
                    )
                all_notifications.extend(result["notifications"])

        return Response({
            "status": "success",
            "data": {
                "notifications": all_notifications,
                "total": len(all_notifications),
                "projects_scanned": projects.count(),
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("scan_notifications failed")
        return Response({"status": "error", "message": "An internal error occurred. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_notifications(request):
    """List notifications for the current user."""
    try:
        company_user = request.user
        unread_only = request.GET.get("unread_only", "false").lower() == "true"
        limit = int(request.GET.get("limit", 50))

        qs = PMNotification.objects.filter(company_user=company_user)
        if unread_only:
            qs = qs.filter(is_read=False)

        notifications = qs[:limit]
        data = [{
            "id": n.id,
            "type": n.notification_type,
            "severity": n.severity,
            "title": n.title,
            "message": n.message,
            "project_id": n.project_id,
            "project_name": n.project.name if n.project else None,
            "is_read": n.is_read,
            "data": n.data,
            "created_at": n.created_at.isoformat(),
        } for n in notifications]

        unread_count = PMNotification.objects.filter(company_user=company_user, is_read=False).count()

        return Response({
            "status": "success",
            "data": {
                "notifications": data,
                "unread_count": unread_count,
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"status": "error", "message": "An internal error occurred. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def mark_notifications_read(request):
    """Mark notifications as read."""
    try:
        company_user = request.user
        notification_ids = request.data.get("notification_ids", [])
        mark_all = request.data.get("mark_all", False)

        if mark_all:
            count = PMNotification.objects.filter(company_user=company_user, is_read=False).update(is_read=True)
        elif notification_ids:
            count = PMNotification.objects.filter(
                company_user=company_user, id__in=notification_ids
            ).update(is_read=True)
        else:
            count = 0

        return Response({
            "status": "success",
            "data": {"marked_read": count}
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"status": "error", "message": "An internal error occurred. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== TEAM PERFORMANCE ENDPOINT ====================

@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def team_performance(request):
    """Get team performance analytics for a project."""
    try:
        company_user = request.user
        if not company_user.can_access_project_manager_features():
            return Response({"status": "error", "message": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

        project_id = request.data.get("project_id")
        if not project_id:
            return Response({"status": "error", "message": "project_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        agent = AgentRegistry.get_agent("analytics_dashboard")
        result = agent.process(
            action="productivity",
            project_id=project_id,
            company_user=company_user,
        )

        return Response({
            "status": "success",
            "data": result,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("team_performance failed")
        return Response({"status": "error", "message": "An internal error occurred. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== TIME ESTIMATION ENDPOINT ====================

@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def time_estimation(request):
    """Estimate task durations for a project."""
    try:
        company_user = request.user
        if not company_user.can_access_project_manager_features():
            return Response({"status": "error", "message": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

        project_id = request.data.get("project_id")
        if not project_id:
            return Response({"status": "error", "message": "project_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            project = Project.objects.get(id=project_id, created_by_company_user=company_user)
        except Project.DoesNotExist:
            return Response({"status": "error", "message": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

        # Get active tasks (not done)
        tasks = Task.objects.filter(project=project).exclude(
            status__in=['done', 'completed']
        ).select_related('assignee')

        tasks_data = [{
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "description": t.description[:300] if t.description else "",
            "assignee_name": (t.assignee.get_full_name() or t.assignee.username) if t.assignee else None,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "deadline": t.due_date.isoformat() if t.due_date else None,
        } for t in tasks]

        # Get completed tasks for historical reference
        completed = Task.objects.filter(project=project, status__in=['done', 'completed'])
        completed_data = [{
            "title": t.title,
            "priority": t.priority,
        } for t in completed[:10]]

        project_info = {"name": project.name, "status": project.status}
        available_users = _build_available_users(company_user=company_user)

        agent = AgentRegistry.get_agent("time_estimation")
        result = agent.process(
            action="estimate",
            tasks=tasks_data,
            project_info=project_info,
            team_members=available_users,
            completed_tasks=completed_data,
        )

        return Response({
            "status": "success",
            "data": result,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("time_estimation failed")
        return Response({"status": "error", "message": "An internal error occurred. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== MEETING SCHEDULER ENDPOINTS ====================

def _send_meeting_email(recipient_email, subject, body_html, ics_content=None):
    """Send meeting notification email with optional .ics calendar attachment."""
    try:
        from django.core.mail import EmailMultiAlternatives
        from_email = getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')

        # Use EmailMultiAlternatives to support attachments
        email = EmailMultiAlternatives(
            subject=subject,
            body='',  # plain text fallback
            from_email=from_email,
            to=[recipient_email],
        )
        email.attach_alternative(body_html, 'text/html')

        # Attach .ics file if provided
        if ics_content:
            email.attach('meeting.ics', ics_content, 'text/calendar; method=REQUEST')

        email.send(fail_silently=True)
    except Exception as e:
        logger.warning(f"Failed to send meeting email to {recipient_email}: {e}")


def _create_meeting_notification(company_user, title, message, data=None, severity='info'):
    """Create a PM notification for meeting events."""
    PMNotification.objects.create(
        company_user=company_user,
        notification_type='custom',
        severity=severity,
        title=title,
        message=message,
        data=data or {},
    )


def _serialize_meeting(meeting):
    """Serialize a ScheduledMeeting to dict with participants."""
    responses = []
    for r in meeting.responses.all().order_by('created_at'):
        if r.responded_by == 'organizer':
            responder_name = meeting.organizer.full_name
        else:
            responder_name = meeting.invitee.get_full_name() or meeting.invitee.username if meeting.invitee else 'Invitee'
        responses.append({
            'id': r.id,
            'responded_by': r.responded_by,
            'responder_name': responder_name,
            'action': r.action,
            'proposed_time': r.proposed_time.isoformat() if r.proposed_time else None,
            'reason': r.reason,
            'created_at': r.created_at.isoformat(),
        })

    # Participants list
    participants = []
    for p in meeting.participants.all().select_related('user'):
        participants.append({
            'id': p.id,
            'user_id': p.user_id,
            'name': p.user.get_full_name() or p.user.username,
            'email': p.user.email or '',
            'status': p.status,
            'reason': p.reason,
            'counter_proposed_time': p.counter_proposed_time.isoformat() if p.counter_proposed_time else None,
            'responded_at': p.responded_at.isoformat() if p.responded_at else None,
        })

    # Fallback invitee info for backward compat
    invitee_name = ''
    if participants:
        invitee_name = ', '.join(p['name'] for p in participants)
    elif meeting.invitee:
        invitee_name = meeting.invitee.get_full_name() or meeting.invitee.username

    return {
        'id': meeting.id,
        'organizer_id': meeting.organizer_id,
        'organizer_name': meeting.organizer.full_name,
        'organizer_email': meeting.organizer.email,
        'invitee_id': meeting.invitee_id,
        'invitee_name': invitee_name,
        'title': meeting.title,
        'description': meeting.description,
        'agenda': meeting.agenda or [],
        'proposed_time': meeting.proposed_time.isoformat(),
        'duration_minutes': meeting.duration_minutes,
        'status': meeting.status,
        'participants': participants,
        'created_at': meeting.created_at.isoformat(),
        'recurrence': meeting.recurrence or 'none',
        'recurrence_end_date': meeting.recurrence_end_date.isoformat() if meeting.recurrence_end_date else None,
        'is_recurring': meeting.recurrence and meeting.recurrence != 'none',
        'parent_meeting_id': meeting.parent_meeting_id,
        'occurrences_count': meeting.occurrences.count() if not meeting.parent_meeting_id else 0,
        'updated_at': meeting.updated_at.isoformat(),
        'responses': responses,
    }


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([PMLLMThrottle])
def meeting_schedule(request):
    """
    Chat-based meeting scheduling endpoint.
    Parses natural language request, validates invitee, creates meeting, and sends notifications.
    """
    try:
        company_user = request.user
        message = request.data.get("message", "").strip()
        logger.info(f"[MEETING] Request from user {company_user.id} ({company_user.full_name}): '{message}'")

        if not message:
            return Response({"status": "error", "message": "Message is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Get project users (Django Users) belonging to this company user
        from core.models import UserProfile
        from django.contrib.auth import get_user_model
        User = get_user_model()

        logger.info(f"[MEETING] Fetching project users for company_user {company_user.id}")
        created_profiles = UserProfile.objects.filter(
            created_by_company_user=company_user,
            user__is_active=True,
        ).select_related('user')

        project_users_list = []
        for profile in created_profiles:
            user = profile.user
            if getattr(user, "is_superuser", False):
                continue
            project_users_list.append({
                "id": user.id,
                "full_name": user.get_full_name() or user.username,
                "email": user.email or "",
                "role": profile.role or "team_member",
                "username": user.username,
            })

        logger.info(f"[MEETING] Found {len(project_users_list)} project users: {[u['full_name'] for u in project_users_list]}")

        # Use the AI agent to parse the request
        agent = AgentRegistry.get_agent("meeting_scheduler")
        current_time = timezone.now().isoformat()
        result = agent.process(
            message=message,
            company_users=project_users_list,
            current_time=current_time,
            organizer_id=company_user.id,
        )

        action = result.get("action")
        logger.info(f"[MEETING] Agent result: action={action}")

        # Handle reschedule
        if action == "reschedule" and result.get("data"):
            data = result["data"]
            invitee_ids = data.get("invitee_ids", [])
            invitee_names = data.get("invitee_names", [])
            new_time_str = data["new_time"]

            try:
                new_time = datetime.fromisoformat(new_time_str.replace("Z", "+00:00"))
                if timezone.is_naive(new_time):
                    new_time = timezone.make_aware(new_time)
            except Exception:
                return Response({"status": "success", "data": {"action": "parse_error", "response": "Could not parse the new time.", "meeting": None}}, status=status.HTTP_200_OK)

            # Find the most recent pending/accepted meeting with this invitee
            from django.db.models import Q
            meeting = ScheduledMeeting.objects.filter(
                organizer=company_user,
                status__in=['pending', 'accepted', 'counter_proposed', 'partially_accepted'],
            ).filter(
                Q(participants__user_id__in=invitee_ids) | Q(invitee_id__in=invitee_ids)
            ).order_by('-created_at').first()

            if not meeting:
                names_str = ", ".join(f"**{n}**" for n in invitee_names)
                return Response({"status": "success", "data": {"action": "not_found", "response": f"I couldn't find an active meeting with {names_str} to reschedule.", "meeting": None}}, status=status.HTTP_200_OK)

            old_time = meeting.proposed_time.strftime("%A, %B %d at %I:%M %p") if meeting.proposed_time else "unknown"
            meeting.proposed_time = new_time
            meeting.save(update_fields=['proposed_time', 'updated_at'])

            new_time_display = new_time.strftime("%A, %B %d, %Y at %I:%M %p")

            # Notify participants
            from core.models import Notification as UserNotification
            for p in meeting.participants.all().select_related('user'):
                UserNotification.objects.create(
                    user=p.user, type='meeting_rescheduled', notification_type='meeting_request',
                    title=f"Meeting Rescheduled: {meeting.title}",
                    message=f'{company_user.full_name} rescheduled "{meeting.title}" to {new_time_display}.',
                    action_url=f'/meetings/{meeting.id}/respond',
                )
                if p.user.email:
                    _send_meeting_email(
                        recipient_email=p.user.email,
                        subject=f"Meeting Rescheduled: {meeting.title}",
                        body_html=f"<p><strong>{company_user.full_name}</strong> rescheduled <strong>\"{meeting.title}\"</strong> from {old_time} to <strong>{new_time_display}</strong>.</p>",
                    )

            return Response({
                "status": "success",
                "data": {
                    "action": "rescheduled",
                    "response": f"**Meeting Rescheduled!**\n\n**{meeting.title}** has been moved from {old_time} to **{new_time_display}**.\n\nAll participants have been notified.",
                    "meeting": _serialize_meeting(meeting),
                }
            }, status=status.HTTP_200_OK)

        # If the agent says to schedule, create the meeting
        if action == "schedule" and result.get("data"):
            data = result["data"]
            invitees_data = data.get("invitees", [])

            # Backward compat: if old format with single invitee_id
            if not invitees_data and data.get("invitee_id"):
                invitees_data = [{"id": data["invitee_id"], "name": data.get("invitee_name", "team member")}]

            # Look up all Django Users
            from django.contrib.auth import get_user_model
            User = get_user_model()
            from core.models import Notification as UserNotification

            invitee_users = []
            for inv in invitees_data:
                try:
                    u = User.objects.get(id=int(inv["id"]), is_active=True)
                    invitee_users.append(u)
                except (User.DoesNotExist, ValueError, TypeError):
                    logger.warning(f"[MEETING] Invitee user ID {inv.get('id')} not found or inactive, skipping")

            if not invitee_users:
                return Response({
                    "status": "success",
                    "data": {"action": "user_not_found", "response": "No valid users found. Please try again.", "meeting": None}
                }, status=status.HTTP_200_OK)

            # Parse proposed time
            proposed_time_str = data["proposed_time"]
            try:
                proposed_time = datetime.fromisoformat(proposed_time_str.replace("Z", "+00:00"))
                if timezone.is_naive(proposed_time):
                    proposed_time = timezone.make_aware(proposed_time)
            except Exception:
                return Response({
                    "status": "success",
                    "data": {"action": "parse_error", "response": "Could not parse the meeting time. Please try again.", "meeting": None}
                }, status=status.HTTP_200_OK)

            time_display = proposed_time.strftime("%A, %B %d, %Y at %I:%M %p")
            invitee_names = [u.get_full_name() or u.username for u in invitee_users]
            duration = data.get("duration_minutes", 30)
            meeting_title = data.get("title") or (f"Meeting with {', '.join(invitee_names[:3])}" + (f" +{len(invitee_names)-3}" if len(invitee_names) > 3 else ""))

            # ── Conflict detection ──
            user_ids = [u.id for u in invitee_users]
            conflicts = agent.check_conflicts(user_ids, proposed_time, duration)
            if conflicts:
                conflict_lines = []
                for c in conflicts:
                    conflict_lines.append(f"- **{c['user_name']}** has \"{c['conflicting_meeting']}\" on {c['conflicting_date']} at {c['conflicting_time']}")
                conflict_str = "\n".join(conflict_lines)

                # Suggest alternative slots
                suggested_slots = agent.suggest_available_slots(user_ids, proposed_time.date(), duration)
                slots_str = ""
                if suggested_slots:
                    slots_str = "\n\n**Available slots on that day:**\n" + "\n".join(f"- {s}" for s in suggested_slots)

                return Response({
                    "status": "success",
                    "data": {
                        "action": "conflict",
                        "response": (
                            f"**Schedule Conflict Detected!**\n\n{conflict_str}\n\n"
                            f"The proposed time ({time_display}, {duration} min) overlaps with an existing meeting.{slots_str}\n\n"
                            f"Please choose a different time."
                        ),
                        "meeting": None,
                    }
                }, status=status.HTTP_200_OK)

            # Recurrence info
            recurrence = data.get("recurrence", "none") or "none"
            recurrence_end_date = None
            if data.get("recurrence_end_date"):
                try:
                    recurrence_end_date = datetime.strptime(data["recurrence_end_date"], "%Y-%m-%d").date()
                except Exception:
                    pass

            duration = data.get("duration_minutes", 30)

            # Build agenda
            agenda = data.get("agenda") or []
            if agenda and not isinstance(agenda[0], dict):
                agenda = [{"item": str(a), "done": False} for a in agenda]

            # Create the parent meeting
            meeting = ScheduledMeeting.objects.create(
                organizer=company_user,
                invitee=invitee_users[0],
                title=meeting_title,
                description=data.get("description") or "",
                agenda=agenda if agenda else None,
                proposed_time=proposed_time,
                duration_minutes=duration,
                status='pending',
                recurrence=recurrence,
                recurrence_end_date=recurrence_end_date,
            )

            _audit_log(company_user, 'meeting_scheduled', 'ScheduledMeeting', meeting.id, meeting.title,
                      {'invitees': [u.username for u in invitee_users], 'time': time_display})

            # Create participants for each invitee
            for u in invitee_users:
                MeetingParticipant.objects.create(meeting=meeting, user=u, status='pending')

            # Create initial response record
            MeetingResponse.objects.create(
                meeting=meeting, responded_by='organizer', action='proposed', proposed_time=proposed_time,
            )

            # Generate recurring occurrences
            occurrences_created = 0
            if recurrence != 'none':
                occurrence_dates = agent.generate_occurrence_dates(proposed_time, recurrence, recurrence_end_date)
                for occ_time in occurrence_dates:
                    occ_meeting = ScheduledMeeting.objects.create(
                        organizer=company_user,
                        invitee=invitee_users[0],
                        title=meeting_title,
                        description=data.get("description") or "",
                        agenda=agenda if agenda else None,
                        proposed_time=occ_time,
                        duration_minutes=duration,
                        status='pending',
                        recurrence=recurrence,
                        recurrence_end_date=recurrence_end_date,
                        parent_meeting=meeting,
                    )
                    for u in invitee_users:
                        MeetingParticipant.objects.create(meeting=occ_meeting, user=u, status='pending')
                    occurrences_created += 1

            # Generate .ics calendar file
            try:
                from project_manager_agent.ics_generator import generate_meeting_ics
                ics_content = generate_meeting_ics(meeting, action='REQUEST')
            except Exception as ics_err:
                logger.warning(f"[MEETING] Failed to generate .ics: {ics_err}")
                ics_content = None

            # Notify each invitee
            for u in invitee_users:
                UserNotification.objects.create(
                    user=u,
                    type='meeting_request',
                    notification_type='meeting_request',
                    title=f"Meeting Request from {company_user.full_name}",
                    message=f'{company_user.full_name} wants to schedule "{meeting.title}" on {time_display} ({meeting.duration_minutes} min). Please accept or reject.',
                    action_url=f'/meetings/{meeting.id}/respond',
                )
                if u.email:
                    participants_str = ", ".join(invitee_names)
                    _send_meeting_email(
                        recipient_email=u.email,
                        subject=f"Meeting Request: {meeting.title}",
                        body_html=f"""
                        <h2>Meeting Request</h2>
                        <p><strong>{company_user.full_name}</strong> has invited you to a meeting.</p>
                        <table style="border-collapse:collapse; margin:16px 0;">
                            <tr><td style="padding:4px 12px; font-weight:bold;">Title:</td><td style="padding:4px 12px;">{meeting.title}</td></tr>
                            <tr><td style="padding:4px 12px; font-weight:bold;">When:</td><td style="padding:4px 12px;">{time_display}</td></tr>
                            <tr><td style="padding:4px 12px; font-weight:bold;">Duration:</td><td style="padding:4px 12px;">{meeting.duration_minutes} minutes</td></tr>
                            <tr><td style="padding:4px 12px; font-weight:bold;">Participants:</td><td style="padding:4px 12px;">{participants_str}</td></tr>
                            <tr><td style="padding:4px 12px; font-weight:bold;">Description:</td><td style="padding:4px 12px;">{meeting.description or 'N/A'}</td></tr>
                        </table>
                        {'<h3>Agenda:</h3><ul>' + ''.join(f'<li>{a["item"]}</li>' for a in (meeting.agenda or [])) + '</ul>' if meeting.agenda else ''}
                        <p>Please log in to your dashboard to accept or reject this meeting.</p>
                        <p style="color:#666; font-size:12px;">A calendar invite (.ics) is attached — open it to add this meeting to your calendar.</p>
                        """,
                        ics_content=ics_content,
                    )

            return Response({
                "status": "success",
                "data": {
                    "action": "scheduled",
                    "response": result["response"],
                    "meeting": _serialize_meeting(meeting),
                }
            }, status=status.HTTP_200_OK)

        # For non-schedule actions (error, not found, etc.), just return the response
        return Response({
            "status": "success",
            "data": {
                "action": action,
                "response": result["response"],
                "meeting": None,
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        import traceback
        logger.exception("meeting_schedule failed")
        print(f"[MEETING ERROR] {type(e).__name__}: {e}")
        print(f"[MEETING ERROR] Traceback:\n{traceback.format_exc()}")
        return Response({"status": "error", "message": "An internal error occurred. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def meeting_respond(request):
    """
    Respond to a meeting: accept, reject (with reason + optional counter time), or withdraw.
    """
    try:
        company_user = request.user
        meeting_id = request.data.get("meeting_id")
        action = request.data.get("action")  # accept, reject, counter_propose, withdraw
        reason = request.data.get("reason", "")
        counter_time_str = request.data.get("counter_time")  # ISO datetime for counter-proposals

        if not meeting_id or not action:
            return Response({"status": "error", "message": "meeting_id and action are required."}, status=status.HTTP_400_BAD_REQUEST)

        if action not in ('accepted', 'rejected', 'counter_proposed', 'withdrawn'):
            return Response({"status": "error", "message": "Invalid action. Use: accepted, rejected, counter_proposed, withdrawn"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            meeting = ScheduledMeeting.objects.get(
                id=meeting_id,
                organizer=company_user,  # Enforce data isolation — only organizer can access
            )
        except ScheduledMeeting.DoesNotExist:
            return Response({"status": "error", "message": "Meeting not found."}, status=status.HTTP_404_NOT_FOUND)

        # Can't act on already finalized meetings
        if meeting.status in ('accepted', 'withdrawn'):
            return Response({"status": "error", "message": f"Meeting is already {meeting.status}."}, status=status.HTTP_400_BAD_REQUEST)

        # Parse counter time if provided
        counter_time = None
        if action == 'counter_proposed' and counter_time_str:
            try:
                counter_time = datetime.fromisoformat(counter_time_str.replace("Z", "+00:00"))
                if timezone.is_naive(counter_time):
                    counter_time = timezone.make_aware(counter_time)
            except Exception:
                return Response({"status": "error", "message": "Invalid counter_time format."}, status=status.HTTP_400_BAD_REQUEST)
        elif action == 'counter_proposed' and not counter_time_str:
            return Response({"status": "error", "message": "counter_time is required for counter proposals."}, status=status.HTTP_400_BAD_REQUEST)

        # Create the response record
        MeetingResponse.objects.create(
            meeting=meeting,
            responded_by='organizer',
            action=action,
            proposed_time=counter_time,
            reason=reason,
        )

        # Update meeting status
        if action == 'accepted':
            meeting.status = 'accepted'
        elif action == 'rejected':
            meeting.status = 'rejected'
        elif action == 'counter_proposed':
            meeting.status = 'counter_proposed'
            meeting.proposed_time = counter_time
        elif action == 'withdrawn':
            meeting.status = 'withdrawn'
        meeting.save()
        _audit_log(company_user, f'meeting_{action}', 'ScheduledMeeting', meeting.id, meeting.title)

        # Notify the invitee (project User) via in-app notification + email
        from core.models import Notification as UserNotification
        invitee_name = meeting.invitee.get_full_name() or meeting.invitee.username
        invitee_email = meeting.invitee.email
        time_display = meeting.proposed_time.strftime("%A, %B %d, %Y at %I:%M %p") if meeting.proposed_time else "TBD"

        # Generate .ics for accepted/cancelled
        confirm_ics = None
        try:
            from project_manager_agent.ics_generator import generate_meeting_ics
            if action in ('accepted', 'withdrawn'):
                ics_action = 'CANCEL' if action == 'withdrawn' else 'REQUEST'
                confirm_ics = generate_meeting_ics(meeting, action=ics_action)
        except Exception:
            pass

        if action == 'accepted':
            UserNotification.objects.create(
                user=meeting.invitee, type='meeting_accepted', notification_type='meeting_request',
                title=f"Meeting Confirmed: {meeting.title}",
                message=f'{company_user.full_name} confirmed the meeting "{meeting.title}" on {time_display}.',
                action_url=f'/meetings/{meeting.id}/respond',
            )
            if invitee_email:
                _send_meeting_email(recipient_email=invitee_email, subject=f"Meeting Confirmed: {meeting.title}",
                    body_html=f"<p><strong>{company_user.full_name}</strong> has confirmed the meeting <strong>\"{meeting.title}\"</strong> on {time_display}.</p>",
                    ics_content=confirm_ics)

        elif action == 'rejected':
            reason_text = f" Reason: {reason}" if reason else ""
            UserNotification.objects.create(
                user=meeting.invitee, type='meeting_rejected', notification_type='meeting_request',
                title=f"Meeting Cancelled: {meeting.title}",
                message=f'{company_user.full_name} cancelled the meeting "{meeting.title}".{reason_text}',
            )
            if invitee_email:
                _send_meeting_email(recipient_email=invitee_email, subject=f"Meeting Cancelled: {meeting.title}",
                    body_html=f"<p><strong>{company_user.full_name}</strong> has cancelled the meeting <strong>\"{meeting.title}\"</strong>.{' Reason: ' + reason if reason else ''}</p>")

        elif action == 'counter_proposed':
            new_time_display = counter_time.strftime("%A, %B %d, %Y at %I:%M %p")
            reason_text = f" Reason: {reason}" if reason else ""
            UserNotification.objects.create(
                user=meeting.invitee, type='meeting_counter_proposed', notification_type='meeting_request',
                title=f"New Time Proposed: {meeting.title}",
                message=f'{company_user.full_name} suggested a new time for "{meeting.title}": {new_time_display}.{reason_text}',
                action_url=f'/meetings/{meeting.id}/respond',
            )
            if invitee_email:
                _send_meeting_email(recipient_email=invitee_email, subject=f"New Time Proposed: {meeting.title}",
                    body_html=f"""<p><strong>{company_user.full_name}</strong> proposed a new time for <strong>\"{meeting.title}\"</strong>.</p>
                    <p><strong>New proposed time:</strong> {new_time_display}</p>{'<p><strong>Reason:</strong> ' + reason + '</p>' if reason else ''}""")

        elif action == 'withdrawn':
            UserNotification.objects.create(
                user=meeting.invitee, type='meeting_withdrawn', notification_type='meeting_request',
                title=f"Meeting Withdrawn: {meeting.title}",
                message=f'{company_user.full_name} has withdrawn the meeting request "{meeting.title}".',
            )
            if invitee_email:
                _send_meeting_email(
                    recipient_email=invitee_email,
                    subject=f"Meeting Cancelled: {meeting.title}",
                    body_html=f"<p><strong>{company_user.full_name}</strong> has cancelled the meeting <strong>\"{meeting.title}\"</strong>.</p>",
                    ics_content=confirm_ics,
                )

        return Response({
            "status": "success",
            "data": {
                "action": action,
                "meeting": _serialize_meeting(meeting),
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("meeting_respond failed")
        return Response({"status": "error", "message": "An internal error occurred. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def meeting_list(request):
    """
    List all meetings for the current user (as organizer or invitee).
    Query params: ?status=pending,accepted&role=organizer,invitee
    """
    try:
        company_user = request.user
        status_filter = request.query_params.get("status", "")
        role_filter = request.query_params.get("role", "")

        # CompanyUser is always the organizer — list all meetings they organized
        meetings = ScheduledMeeting.objects.filter(
            organizer=company_user
        ).select_related('organizer', 'invitee').prefetch_related('responses')

        if status_filter:
            statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
            meetings = meetings.filter(status__in=statuses)

        limit = min(int(request.GET.get('limit', 50)), 100)
        offset = max(int(request.GET.get('offset', 0)), 0)
        meetings = meetings.order_by('-created_at')[offset:offset + limit]

        data = [_serialize_meeting(m) for m in meetings]

        return Response({
            "status": "success",
            "data": {
                "meetings": data,
                "total": len(data),
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("meeting_list failed")
        return Response({"status": "error", "message": "An internal error occurred. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== MEETING SCHEDULER CHAT CRUD ====================

def _serialize_meeting_chat(chat):
    messages = []
    for msg in chat.messages.order_by('created_at'):
        m = {'role': msg.role, 'content': msg.content}
        if msg.response_data:
            m['responseData'] = msg.response_data
        messages.append(m)
    return {
        'id': str(chat.id),
        'title': chat.title or 'Chat',
        'messages': messages,
        'updatedAt': chat.updated_at.isoformat(),
        'timestamp': chat.updated_at.isoformat(),
    }


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_meeting_scheduler_chats(request):
    try:
        limit = min(int(request.GET.get('limit', 50)), 100)
        offset = max(int(request.GET.get('offset', 0)), 0)
        chats = PMMeetingSchedulerChat.objects.filter(company_user=request.user).prefetch_related('messages').order_by('-updated_at')[offset:offset + limit]
        return Response({'status': 'success', 'data': [_serialize_meeting_chat(c) for c in chats]})
    except Exception as e:
        logger.exception("list_meeting_scheduler_chats error")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_meeting_scheduler_chat(request):
    try:
        data = request.data if isinstance(request.data, dict) else {}
        title = (data.get('title') or 'Chat')[:255]
        chat = PMMeetingSchedulerChat.objects.create(company_user=request.user, title=title)
        for m in (data.get('messages') or []):
            PMMeetingSchedulerChatMessage.objects.create(
                chat=chat, role=m.get('role', 'user'),
                content=m.get('content', ''), response_data=m.get('responseData'),
            )
        chat.refresh_from_db()
        return Response({'status': 'success', 'data': _serialize_meeting_chat(chat)})
    except Exception as e:
        logger.exception("create_meeting_scheduler_chat error")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["PATCH", "PUT"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_meeting_scheduler_chat(request, chat_id):
    try:
        chat = PMMeetingSchedulerChat.objects.filter(company_user=request.user, id=chat_id).first()
        if not chat:
            return Response({'status': 'error', 'message': 'Chat not found.'}, status=status.HTTP_404_NOT_FOUND)
        data = request.data if isinstance(request.data, dict) else {}
        if data.get('title'):
            chat.title = str(data['title'])[:255]
            chat.save(update_fields=['title', 'updated_at'])
        for m in (data.get('messages') or []):
            PMMeetingSchedulerChatMessage.objects.create(
                chat=chat, role=m.get('role', 'user'),
                content=m.get('content', ''), response_data=m.get('responseData'),
            )
        chat.refresh_from_db()
        return Response({'status': 'success', 'data': _serialize_meeting_chat(chat)})
    except Exception as e:
        logger.exception("update_meeting_scheduler_chat error")
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["DELETE"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_meeting_scheduler_chat(request, chat_id):
    try:
        chat = PMMeetingSchedulerChat.objects.filter(company_user=request.user, id=chat_id).first()
        if not chat:
            return Response({'status': 'error', 'message': 'Chat not found.'}, status=status.HTTP_404_NOT_FOUND)
        chat.delete()
        return Response({'status': 'success', 'message': 'Chat deleted.'})
    except Exception as e:
        logger.exception("delete_meeting_scheduler_chat error")
        return Response({'status': 'error', 'message': 'An internal error occurred.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== AUDIT LOG ENDPOINT ====================

@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_audit_logs(request):
    """List audit logs for the current company user. Supports pagination and action filter."""
    try:
        from project_manager_agent.models import PMAuditLog
        company_user = request.user
        limit = min(int(request.GET.get('limit', 50)), 100)
        offset = max(int(request.GET.get('offset', 0)), 0)
        action_filter = request.GET.get('action', '')

        qs = PMAuditLog.objects.filter(company_user=company_user)
        if action_filter:
            qs = qs.filter(action=action_filter)

        total = qs.count()
        logs = qs[offset:offset + limit]

        data = [{
            'id': log.id,
            'action': log.action,
            'model_name': log.model_name,
            'object_id': log.object_id,
            'object_title': log.object_title,
            'details': log.details,
            'created_at': log.created_at.isoformat(),
        } for log in logs]

        return Response({
            'status': 'success',
            'data': {'logs': data, 'total': total},
        })
    except Exception as e:
        logger.exception("list_audit_logs error")
        return Response({'status': 'error', 'message': 'An internal error occurred.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== HEALTH CHECK ENDPOINT ====================

@api_view(["GET"])
def pm_health_check(request):
    """
    Health check endpoint for the PM Agent system.
    Returns system status, database connectivity, and LLM availability.
    No authentication required — used by monitoring/load balancers.
    """
    import time as _time
    checks = {}

    # Database check
    try:
        _db_start = _time.time()
        from project_manager_agent.models import ScheduledMeeting
        ScheduledMeeting.objects.count()
        checks['database'] = {'status': 'ok', 'latency_ms': round((_time.time() - _db_start) * 1000)}
    except Exception as e:
        checks['database'] = {'status': 'error', 'error': str(type(e).__name__)}

    # LLM check (quick — just verify client initializes)
    try:
        from project_manager_agent.ai_agents.base_agent import BaseAgent
        agent = BaseAgent.__new__(BaseAgent)
        api_key = getattr(django_settings, 'GROQ_API_KEY', '')
        checks['llm'] = {
            'status': 'ok' if api_key else 'warning',
            'model': getattr(django_settings, 'GROQ_MODEL', 'unknown'),
            'api_key_configured': bool(api_key),
        }
    except Exception as e:
        checks['llm'] = {'status': 'error', 'error': str(type(e).__name__)}

    # Agent registry check
    try:
        from project_manager_agent.ai_agents import AgentRegistry
        registered = list(AgentRegistry._agents.keys()) if hasattr(AgentRegistry, '_agents') else []
        checks['agents'] = {'status': 'ok', 'registered': len(registered), 'names': registered}
    except Exception as e:
        checks['agents'] = {'status': 'error', 'error': str(type(e).__name__)}

    overall = 'healthy' if all(c.get('status') == 'ok' for c in checks.values()) else 'degraded'

    return Response({
        'status': overall,
        'checks': checks,
        'timestamp': timezone.now().isoformat(),
    })

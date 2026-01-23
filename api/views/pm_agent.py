from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404

from core.models import Project, Task, Subtask, TeamMember, UserProfile
from project_manager_agent.ai_agents import AgentRegistry
from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly

import logging
import json
from datetime import datetime, timedelta
import os
import tempfile

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


def _build_available_users(project_id=None, project=None):
    """
    - If project_id provided: return team members + owner for that project
    - Else: return up to 50 users (for general assignment mapping)
    """
    available_users = []

    if project_id and project is not None:
        team_members = TeamMember.objects.filter(project_id=project_id).select_related("user")
        for member in team_members:
            available_users.append(
                {
                    "id": member.user.id,
                    "username": member.user.username,
                    "name": member.user.get_full_name() or member.user.username,
                    "role": member.role,
                }
            )

        # Include owner if not in team list
        team_user_ids = {m.user.id for m in team_members}
        if project.owner_id and project.owner_id not in team_user_ids:
            available_users.append(
                {
                    "id": project.owner.id,
                    "username": project.owner.username,
                    "name": project.owner.get_full_name() or project.owner.username,
                    "role": "owner",
                }
            )
    else:
        User = get_user_model()
        users = User.objects.all()[:50]
        for u in users:
            available_users.append(
                {"id": u.id, "username": u.username, "name": u.get_full_name() or u.username}
            )

    return available_users


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
            tasks = Task.objects.filter(project=project).select_related("assignee")
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

        available_users = _build_available_users(project_id=project_id, project=project)
        context["user_assignments"] = _build_user_assignments(
            available_users, project_id=project_id, all_tasks=all_tasks, owner=None
        )

        agent = AgentRegistry.get_agent("project_pilot")
        result = agent.process(question=question, context=context, available_users=available_users)
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
                                                except:
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
                                except:
                                    pass
                            if extracted_objects:
                                actions = extracted_objects
                                logger.info(f"Extracted {len(actions)} actions using regex fallback")
                    except Exception as fallback_err:
                        logger.warning(f"All JSON parsing attempts failed: {fallback_err}")
        
        # Ensure actions is always a list
        if not isinstance(actions, list):
            actions = []
        
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
                    default_owner = User.objects.first()
                    
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

                    estimated_hours = action_data.get("estimated_hours")
                    if estimated_hours:
                        try:
                            estimated_hours = float(estimated_hours)
                        except (ValueError, TypeError):
                            estimated_hours = None

                    task = Task.objects.create(
                        title=action_data.get("task_title", "New Task"),
                        description=action_data.get("task_description", ""),
                        project=task_project,
                        status=action_data.get("status", "todo"),
                        priority=action_data.get("priority", "medium"),
                        assignee_id=action_data.get("assignee_id") if action_data.get("assignee_id") else None,
                        estimated_hours=estimated_hours,
                        due_date=due_date,
                        ai_reasoning=action_data.get("reasoning", ""),
                    )

                    action_results.append(
                        {
                            "action": "create_task",
                            "success": True,
                            "task_id": task.id,
                            "task_title": task.title,
                            "project_name": task_project.name,
                            "message": f'Task "{task.title}" created successfully!',
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

                    task_to_update.save()
                    action_results.append(
                        {"action": "update_task", "success": True, "task_id": task_to_update.id}
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
                "title": t.title
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

        context = {
            "tasks": tasks,
            "team": team,
        }

        if project_id:
            context["project"] = {
                "id": project.id,
                "name": project.name,
                "status": project.status,
            }

        result = agent.process(context=context)

        # Apply prioritization suggestions
        if result.get("prioritized_tasks"):
            for task_data in result["prioritized_tasks"]:
                task_id = task_data.get("task_id")
                if task_id:
                    try:
                        t = Task.objects.get(id=task_id, project__created_by_company_user=company_user)
                        if "priority" in task_data:
                            t.priority = task_data["priority"]
                        if "status" in task_data:
                            t.status = task_data["status"]
                        t.save()
                    except Task.DoesNotExist:
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
        tasks = [
            {
                "id": t.id,
                "title": t.title
            }
            for t in tasks_queryset
        ]

        context = {"tasks": tasks}
        result = agent.process(context=context)

        # Save generated subtasks
        saved_count = 0
        reasoning_updated_count = 0
        for task_data in result.get("subtasks", []):
            task_id = task_data.get("task_id")
            subtasks_list = task_data.get("subtasks", [])
            reasoning = task_data.get("reasoning", "")

            if not task_id:
                continue

            try:
                task = Task.objects.get(id=task_id, project__created_by_company_user=company_user)
                
                # Update AI reasoning if provided
                if reasoning:
                    task.ai_reasoning = reasoning
                    task.save()
                    reasoning_updated_count += 1

                # Delete existing subtasks for this task
                Subtask.objects.filter(task=task).delete()

                # Create new subtasks
                for idx, subtask_title in enumerate(subtasks_list):
                    Subtask.objects.create(
                        task=task,
                        title=subtask_title,
                        order=idx + 1,
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
        tasks_queryset = Task.objects.filter(project=project, project__created_by_company_user=company_user)

        tasks = [
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status,
                    "priority": t.priority,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                "estimated_hours": t.estimated_hours,
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
        result = agent.process(action=action, context=context, **request.data)

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
        all_tasks = Task.objects.filter(project__created_by_company_user=company_user).select_related("project", "assignee")

        if project_id:
            project = get_object_or_404(Project, id=project_id, created_by_company_user=company_user)
            tasks = Task.objects.filter(project=project).select_related("assignee")
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
                        "assignee_id": t.assignee.id if t.assignee else None,
                        "assignee_username": t.assignee.username if t.assignee else None,
                    }
                    for t in all_tasks[:50]
                ],
            }

        agent = AgentRegistry.get_agent("knowledge_qa")
        result = agent.process(question=question, context=context)

        return Response({"status": "success", "data": result}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("knowledge_qa failed")
        return Response(
            {"status": "error", "message": "Knowledge Q&A failed", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


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
        
        # Get default owner (required field)
        from django.contrib.auth.models import User
        default_owner = User.objects.first()
        if not default_owner:
            return Response({
                'status': 'error',
                'message': 'No default owner available. Please ensure at least one user exists in the system.'
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
            try:
                project_data['budget_min'] = float(budget_min)
            except (ValueError, TypeError):
                return Response({
                    'status': 'error',
                    'message': 'Invalid budget_min value'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        if budget_max:
            try:
                project_data['budget_max'] = float(budget_max)
            except (ValueError, TypeError):
                return Response({
                    'status': 'error',
                    'message': 'Invalid budget_max value'
                }, status=status.HTTP_400_BAD_REQUEST)
        
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
        available_users = _build_available_users(project_id=project_id, project=project)
        
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


def _extract_text_from_file(file):
    """
    Extract text from uploaded file.
    Supports: .txt, .pdf, .docx
    """
    file_extension = os.path.splitext(file.name)[1].lower()
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
        
        return text.strip()
    
    except Exception as e:
        logger.exception(f"Error extracting text from file: {file.name}")
        raise ValueError(f"Failed to extract text from file: {str(e)}")


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

        available_users = _build_available_users(project_id=project_id, project=project)
        context["user_assignments"] = _build_user_assignments(
            available_users, project_id=project_id, all_tasks=all_tasks, owner=None
        )

        agent = AgentRegistry.get_agent("project_pilot")
        result = agent.process(question=question, context=context, available_users=available_users)
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

        # Process actions (reuse same logic from project_pilot)
        action_results = []
        created_projects = {}  # Map to track created projects for task assignment
        
        # First pass: Create all projects
        for action in actions:
            if action.get("action") == "create_project":
                try:
                    # Get default owner (required field)
                    from django.contrib.auth.models import User
                    default_owner = User.objects.first()
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
                        except:
                            start_date = None
                    
                    if end_date and isinstance(end_date, str):
                        try:
                            from datetime import datetime
                            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                        except:
                            end_date = None
                    
                    if deadline and isinstance(deadline, str):
                        try:
                            from datetime import datetime
                            deadline = datetime.strptime(deadline, '%Y-%m-%d').date()
                        except:
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

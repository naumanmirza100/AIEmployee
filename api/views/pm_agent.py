from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404

from core.models import Project, Task, Subtask, TeamMember, UserProfile
from project_manager_agent.ai_agents import AgentRegistry

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


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
            user_tasks = Task.objects.filter(
                project_id=project_id, assignee_id=user_id, project__owner=owner
            ).select_related("project")
        else:
            user_tasks = all_tasks.filter(assignee_id=user_id).select_related("project")

        tasks_by_project = {}
        for t in user_tasks:
            pid = t.project_id
            if pid not in tasks_by_project:
                tasks_by_project[pid] = {
                    "project_id": pid,
                    "project_name": t.project.name,
                    "tasks": [],
                }
            tasks_by_project[pid]["tasks"].append(
                {"id": t.id, "title": t.title, "status": t.status, "priority": t.priority}
            )

        user_assignments.append(
            {
                "user_id": user_id,
                "username": user_info["username"],
                "name": user_info.get("name", user_info["username"]),
                "total_tasks": user_tasks.count(),
                "projects": list(tasks_by_project.values()),
            }
        )

    return user_assignments


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def project_pilot(request):
    """
    Project Pilot Agent API (token-auth friendly).
    Body:
      - question: str (required)
      - project_id: int (optional)
    """
    if not _ensure_project_manager(request.user):
        return Response(
            {"status": "error", "message": "Access denied (project manager only)."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        agent = AgentRegistry.get_agent("project_pilot")
        question = (request.data.get("question") or "").strip()
        project_id = request.data.get("project_id")

        if not question:
            return Response(
                {"status": "error", "message": "question is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Always get all user's projects/tasks for context
        all_projects = Project.objects.filter(owner=request.user)
        all_tasks = Task.objects.filter(project__owner=request.user).select_related("project")

        context = {}
        project = None
        if project_id:
            project = get_object_or_404(Project, id=project_id, owner=request.user)
            tasks = Task.objects.filter(project=project).select_related("assignee")
            context = {
                "project": {
                    "id": project.id,
                    "name": project.name,
                    "status": project.status,
                    "tasks_count": tasks.count(),
                },
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
            available_users, project_id=project_id, all_tasks=all_tasks, owner=request.user
        )

        result = agent.process(question=question, context=context, available_users=available_users)
        if result.get("cannot_do"):
            return Response({"status": "success", "data": result}, status=status.HTTP_200_OK)

        actions = result.get("actions", [])
        if result.get("action"):
            actions = [result["action"]]

        created_project_id = None
        action_results = []

        # Ensure answer exists for concatenations
        if "answer" not in result or result["answer"] is None:
            result["answer"] = ""

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

                    project = Project.objects.create(
                        name=action_data.get("project_name", "New Project"),
                        description=action_data.get("project_description", ""),
                        owner=request.user,
                        status=action_data.get("project_status", "planning"),
                        priority=action_data.get("project_priority", "medium"),
                        end_date=end_date,
                        project_manager_id=project_manager_id if project_manager_id else None,
                        industry_id=industry_id if industry_id else None,
                        project_type=project_type if project_type else "web_app",
                        budget_min=budget_min if budget_min else None,
                        budget_max=budget_max if budget_max else None,
                        deadline=deadline,
                    )

                    created_project_id = project.id
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
                    action_results.append({"action": "create_project", "success": False, "error": str(e)})

            elif action_type == "create_task":
                try:
                    task_project_id = action_data.get("project_id")
                    if not task_project_id and created_project_id:
                        task_project_id = created_project_id
                    elif not task_project_id and project_id:
                        task_project_id = project_id
                    elif not task_project_id and context.get("project"):
                        task_project_id = context["project"]["id"]
                    elif (
                        not task_project_id
                        and context.get("all_projects")
                        and len(context.get("all_projects", [])) > 0
                    ):
                        task_project_id = context["all_projects"][0]["id"]

                    if not task_project_id:
                        action_results.append(
                            {
                                "action": "create_task",
                                "success": False,
                                "error": f"Could not determine project for task '{action_data.get('task_title', 'Unknown')}'.",
                            }
                        )
                        continue

                    task_project = get_object_or_404(Project, id=task_project_id, owner=request.user)

                    estimated_hours = None
                    if action_data.get("estimated_hours") is not None:
                        try:
                            estimated_hours = float(action_data["estimated_hours"])
                        except (ValueError, TypeError):
                            estimated_hours = None

                    due_date = None
                    if action_data.get("due_date"):
                        try:
                            from django.utils import timezone
                            from django.utils.dateparse import parse_date, parse_datetime
                            from datetime import time as dt_time

                            due_date_str = str(action_data["due_date"]).strip()
                            if len(due_date_str) == 10 and due_date_str.count("-") == 2:
                                due_date = datetime.strptime(due_date_str, "%Y-%m-%d").replace(
                                    hour=23, minute=59, second=59
                                )
                                if timezone.is_naive(due_date):
                                    due_date = timezone.make_aware(due_date)
                            else:
                                due_date = parse_datetime(due_date_str)
                                if not due_date:
                                    date_only = parse_date(due_date_str)
                                    if date_only:
                                        due_date = datetime.combine(date_only, dt_time(23, 59, 59))
                                        if timezone.is_naive(due_date):
                                            due_date = timezone.make_aware(due_date)
                        except Exception:
                            due_date = None

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
                    project_to_delete = get_object_or_404(Project, id=project_id_to_delete, owner=request.user)
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
                    task_to_delete = get_object_or_404(Task, id=task_id_to_delete, project__owner=request.user)
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
                    updates = action_data.get("updates", {}) or {}
                    if not task_id_to_update:
                        action_results.append(
                            {"action": "update_task", "success": False, "error": "task_id is required"}
                        )
                        continue
                    if not updates:
                        action_results.append(
                            {"action": "update_task", "success": False, "error": "updates are required"}
                        )
                        continue

                    task_to_update = get_object_or_404(Task, id=task_id_to_update, project__owner=request.user)

                    # Priority
                    if "priority" in updates and updates["priority"] in ["low", "medium", "high"]:
                        task_to_update.priority = updates["priority"]

                    # Status
                    if "status" in updates and updates["status"] in [
                        "todo",
                        "in_progress",
                        "review",
                        "done",
                        "blocked",
                    ]:
                        task_to_update.status = updates["status"]

                    # Assignee
                    if "assignee_id" in updates:
                        assignee_id = updates.get("assignee_id")
                        if assignee_id:
                            User = get_user_model()
                            try:
                                assignee = User.objects.get(id=assignee_id)
                                task_to_update.assignee = assignee
                            except User.DoesNotExist:
                                pass
                        else:
                            task_to_update.assignee = None

                    # Due date (YYYY-MM-DD)
                    if updates.get("due_date"):
                        try:
                            from django.utils import timezone
                            due_date_str = str(updates["due_date"]).strip()
                            if len(due_date_str) == 10 and due_date_str.count("-") == 2:
                                due_date = datetime.strptime(due_date_str, "%Y-%m-%d").replace(
                                    hour=23, minute=59, second=59
                                )
                                if timezone.is_naive(due_date):
                                    due_date = timezone.make_aware(due_date)
                                task_to_update.due_date = due_date
                        except Exception:
                            pass

                    # Title/description
                    if updates.get("title"):
                        task_to_update.title = updates["title"]
                    if updates.get("description"):
                        task_to_update.description = updates["description"]

                    task_to_update.save()
                    action_results.append(
                        {"action": "update_task", "success": True, "task_id": task_to_update.id}
                    )
                except Exception as e:
                    action_results.append(
                        {"action": "update_task", "success": False, "error": f"Error updating task: {str(e)}"}
                    )

        data = {"status": "success", "data": result, "action_results": action_results}
        return Response(data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("project_pilot failed")
        return Response(
            {"status": "error", "message": "Project pilot failed", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def task_prioritization(request):
    """
    Task Prioritization Agent API.
    Body:
      - action: prioritize|order|bottlenecks|delegation (default: prioritize)
      - project_id: int (optional)
      - task: dict (optional, used for some actions)
    """
    if not _ensure_project_manager(request.user):
        return Response(
            {"status": "error", "message": "Access denied (project manager only)."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        agent = AgentRegistry.get_agent("task_prioritization")
        action = request.data.get("action", "prioritize")
        project_id = request.data.get("project_id")

        if project_id:
            tasks_queryset = Task.objects.filter(project_id=project_id, project__owner=request.user)
        else:
            tasks_queryset = Task.objects.filter(project__owner=request.user)

        tasks = [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "status": t.status,
                "priority": t.priority,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "assignee_id": t.assignee.id if t.assignee else None,
                "dependencies": list(t.depends_on.values_list("id", flat=True)),
            }
            for t in tasks_queryset
        ]

        team_members = []
        if action in ["bottlenecks", "delegation"]:
            if project_id:
                members = TeamMember.objects.filter(project_id=project_id).select_related("user")
            else:
                members = TeamMember.objects.filter(project__owner=request.user).select_related("user")
            team_members = [{"id": m.user.id, "name": m.user.username, "role": m.role} for m in members]

        result = agent.process(
            action=action,
            tasks=tasks,
            team_members=team_members,
            task=request.data.get("task", {}) or {},
        )

        # Persist reasoning / priorities similarly to the legacy view
        if action == "prioritize" and result.get("success") and result.get("tasks"):
            for task_data in result["tasks"]:
                task_id = task_data.get("id")
                new_priority = task_data.get("ai_priority")
                reasoning = task_data.get("ai_reasoning", "")
                if task_id and new_priority in ["low", "medium", "high"]:
                    try:
                        t = Task.objects.get(id=task_id, project__owner=request.user)
                        t.priority = new_priority
                        if reasoning:
                            t.ai_reasoning = (t.ai_reasoning + "\n\n" + reasoning) if t.ai_reasoning else reasoning
                        t.save()
                    except Task.DoesNotExist:
                        continue

        if action == "order" and result.get("success") and result.get("tasks"):
            for task_data in result["tasks"]:
                task_id = task_data.get("id")
                reasoning = task_data.get("order_reasoning") or task_data.get("ai_reasoning", "")
                if task_id and reasoning:
                    try:
                        t = Task.objects.get(id=task_id, project__owner=request.user)
                        t.ai_reasoning = (t.ai_reasoning + "\n\n" + reasoning) if t.ai_reasoning else reasoning
                        t.save()
                    except Task.DoesNotExist:
                        continue

        if action == "bottlenecks" and result.get("success") and result.get("analysis"):
            analysis = result.get("analysis", {})
            for bottleneck in analysis.get("bottlenecks", []):
                bottleneck_reasoning = bottleneck.get("reasoning", "")
                if not bottleneck_reasoning:
                    continue
                reasoning_prefix = f"[Bottleneck Analysis: {bottleneck.get('type', 'unknown')}] "
                full_reasoning = reasoning_prefix + bottleneck_reasoning
                for task_info in bottleneck.get("affected_tasks", []):
                    task_id = task_info.get("task_id") if isinstance(task_info, dict) else task_info
                    task_reasoning = task_info.get("task_reasoning", "") if isinstance(task_info, dict) else ""
                    try:
                        t = Task.objects.get(id=task_id, project__owner=request.user)
                        combined = full_reasoning + (("\n\n" + task_reasoning) if task_reasoning else "")
                        t.ai_reasoning = (t.ai_reasoning + "\n\n" + combined) if t.ai_reasoning else combined
                        t.save()
                    except Task.DoesNotExist:
                        continue

        if action == "delegation" and result.get("success") and result.get("suggestions"):
            suggestions = (result.get("suggestions") or {}).get("suggestions", [])
            for suggestion in suggestions:
                task_id = suggestion.get("task_id")
                reasoning = suggestion.get("reasoning", "")
                if not (task_id and reasoning):
                    continue
                try:
                    t = Task.objects.get(id=task_id, project__owner=request.user)
                    full_reasoning = "[Delegation Suggestion] " + reasoning
                    t.ai_reasoning = (t.ai_reasoning + "\n\n" + full_reasoning) if t.ai_reasoning else full_reasoning
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
@permission_classes([IsAuthenticated])
def generate_subtasks(request):
    """
    Subtask Generation Agent API.
    Body:
      - project_id: int (required)
    """
    if not _ensure_project_manager(request.user):
        return Response(
            {"status": "error", "message": "Access denied (project manager only)."},
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
        get_object_or_404(Project, id=project_id, owner=request.user)

        tasks_queryset = Task.objects.filter(project_id=project_id)
        tasks = [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "status": t.status,
                "priority": t.priority,
                "due_date": t.due_date.isoformat() if t.due_date else None,
            }
            for t in tasks_queryset
        ]

        if not tasks:
            return Response(
                {"status": "error", "message": "No tasks found in this project"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = agent.process(action="generate_for_project", tasks=tasks)
        if not result.get("success"):
            return Response({"status": "error", "data": result}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        subtasks_by_task = result.get("subtasks_by_task", {})
        saved_count = 0
        reasoning_updated_count = 0

        for task_id, subtask_data in subtasks_by_task.items():
            try:
                task = Task.objects.get(id=task_id, project__owner=request.user)

                if isinstance(subtask_data, dict):
                    subtasks_list = subtask_data.get("subtasks", [])
                    task_reasoning = subtask_data.get("task_reasoning", "")
                else:
                    subtasks_list = subtask_data
                    task_reasoning = ""

                if task_reasoning:
                    full_reasoning = "[Subtask Generation Strategy] " + task_reasoning
                    task.ai_reasoning = (
                        task.ai_reasoning + "\n\n" + full_reasoning if task.ai_reasoning else full_reasoning
                    )
                    task.save()
                    reasoning_updated_count += 1

                for subtask_item in subtasks_list:
                    Subtask.objects.create(
                        task=task,
                        title=subtask_item.get("title", "Untitled Subtask"),
                        description=subtask_item.get("description", ""),
                        order=subtask_item.get("order", 0),
                        status="todo",
                    )
                    saved_count += 1
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
@permission_classes([IsAuthenticated])
def timeline_gantt(request):
    """
    Timeline/Gantt Agent API.
    Body:
      - action: create_timeline|generate_gantt_chart|check_deadlines|suggest_adjustments|calculate_duration|manage_phases
      - project_id: int (required)
      - days_ahead/current_progress/phases: optional depending on action
    """
    if not _ensure_project_manager(request.user):
        return Response(
            {"status": "error", "message": "Access denied (project manager only)."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        agent = AgentRegistry.get_agent("timeline_gantt")
        action = request.data.get("action", "create_timeline")
        project_id = request.data.get("project_id")
        if not project_id:
            return Response(
                {"status": "error", "message": "project_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        project = get_object_or_404(Project, id=project_id, owner=request.user)
        tasks_queryset = (
            Task.objects.filter(project=project)
            .select_related("assignee")
            .prefetch_related("depends_on")
        )

        tasks = []
        for t in tasks_queryset:
            tasks.append(
                {
                    "id": t.id,
                    "title": t.title,
                    "description": t.description,
                    "status": t.status,
                    "priority": t.priority,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "assignee_id": t.assignee.id if t.assignee else None,
                    "estimated_hours": float(t.estimated_hours) if t.estimated_hours else None,
                    "actual_hours": float(t.actual_hours) if t.actual_hours else None,
                    "dependencies": list(t.depends_on.values_list("id", flat=True)),
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
            )

        kwargs = {"project_id": project_id, "tasks": tasks}
        if action == "check_deadlines":
            kwargs["days_ahead"] = request.data.get("days_ahead", 7)
        elif action == "suggest_adjustments":
            kwargs["current_progress"] = request.data.get("current_progress", {}) or {}
        elif action == "manage_phases":
            kwargs["phases"] = request.data.get("phases")

        result = agent.process(action=action, **kwargs)

        if action in ["generate_gantt_chart", "create_timeline"] and result.get("success"):
            gantt_data = result.get("gantt_data", {}) or {}
            tasks_data = gantt_data.get("tasks", []) or []

            for task_item in tasks_data:
                task_id = task_item.get("id")
                reasoning = task_item.get("ai_reasoning") or task_item.get("reasoning", "")
                if task_id and reasoning:
                    try:
                        t = Task.objects.get(id=task_id, project__owner=request.user)
                        full_reasoning = "[Timeline & Scheduling Analysis] " + reasoning
                        t.ai_reasoning = (t.ai_reasoning + "\n\n" + full_reasoning) if t.ai_reasoning else full_reasoning
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
@permission_classes([IsAuthenticated])
def knowledge_qa(request):
    """
    Knowledge Q&A Agent API.
    Body:
      - question: str (required)
      - project_id: int (optional)
    """
    if not _ensure_project_manager(request.user):
        return Response(
            {"status": "error", "message": "Access denied (project manager only)."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        agent = AgentRegistry.get_agent("knowledge_qa")
        question = (request.data.get("question") or "").strip()
        project_id = request.data.get("project_id")

        if not question:
            return Response(
                {"status": "error", "message": "question is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        all_projects = Project.objects.filter(owner=request.user)
        all_tasks = Task.objects.filter(project__owner=request.user).select_related("project", "assignee")

        context = {}
        project = None
        if project_id:
            project = get_object_or_404(Project, id=project_id, owner=request.user)
            tasks = Task.objects.filter(project=project).select_related("assignee")
            context = {
                "project": {
                    "id": project.id,
                    "name": project.name,
                    "status": project.status,
                    "tasks_count": tasks.count(),
                },
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
                    for t in all_tasks
                ],
            }

        available_users = _build_available_users(project_id=project_id, project=project)
        context["user_assignments"] = _build_user_assignments(
            available_users, project_id=project_id, all_tasks=all_tasks, owner=request.user
        )

        result = agent.process(question=question, context=context, available_users=available_users)
        return Response({"status": "success", "data": result}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("knowledge_qa failed")
        return Response(
            {"status": "error", "message": "Knowledge Q&A failed", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )




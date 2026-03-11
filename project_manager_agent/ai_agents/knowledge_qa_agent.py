"""
Knowledge Q&A Agent
Answers questions about projects, provides information, and assists with queries.
This agent only provides descriptive answers - it does not perform actions.
"""

from .base_agent import BaseAgent
from .enhancements.knowledge_qa_enhancements import KnowledgeQAEnhancements
from .enhancements.chart_generation import ChartGenerator
from typing import Dict, Optional, List
from collections import Counter
import json
import re


def _is_count_or_aggregate_question(question: str) -> bool:
    """
    Classify whether the question is asking for a count, total, or aggregate
    (numbers only) vs a list or detailed breakdown. For count questions we use
    a compact context and short answers to save tokens.
    """
    q = question.lower().strip()
    # If the question asks for a list/detail alongside a count, treat it as detail (not count-only)
    list_indicators = ["list all", "list the", "list every", "list them", "which tasks", "which users",
                        "what are the tasks", "name of each", "names of all", "show them", "show all",
                        "show me all", "show me the", "tell me all", "tell me the"]
    if any(phrase in q for phrase in list_indicators):
        return False

    count_indicators = [
        "how many",
        "how much",
        "total number",
        "total count",
        "number of",
        "count of",
        "how many tasks",
        "how many users",
        "how many projects",
        "how many are",
        "breakdown by status",
        "breakdown by priority",
        "tasks in each status",
        "tasks per project",
        "tasks per user",
        "each project have",
        "each user have",
        "for each project and user",
        "project and user",
        "distinct assigned users",
        "users with tasks",
        "which users have",
        "in total",
        "in each status",
        "by status",
        "by priority",
    ]
    if any(phrase in q for phrase in count_indicators):
        return True
    return False


def _build_aggregates_context(context: Dict, available_users: Optional[List[Dict]] = None) -> str:
    """
    Build a compact, aggregates-only context for count/aggregate questions.
    Uses pre-computed numbers so the model can answer without scanning long lists.
    """
    lines = ["\n📊 AGGREGATES (use these exact numbers for count questions):\n"]

    # Total tasks and by status/priority from context['tasks'] OR context['project']['tasks']
    tasks = context.get("tasks") or []
    if not tasks and context.get("project") and context["project"].get("tasks"):
        tasks = context["project"]["tasks"]
    total_tasks = len(tasks)
    lines.append(f"Total tasks: {total_tasks}")

    if tasks:
        # Assigned vs unassigned counts
        assigned_tasks = [t for t in tasks if t.get("assignee_id") or t.get("assignee_username")]
        unassigned_tasks = [t for t in tasks if not t.get("assignee_id") and not t.get("assignee_username")]
        lines.append(f"Assigned tasks: {len(assigned_tasks)}")
        lines.append(f"Unassigned tasks: {len(unassigned_tasks)}")

        by_status = Counter(t.get("status") for t in tasks if t.get("status"))
        if by_status:
            status_str = ", ".join(f"{k}={v}" for k, v in sorted(by_status.items()))
            lines.append(f"Tasks by status: {status_str}")
        by_priority = Counter(t.get("priority") for t in tasks if t.get("priority"))
        if by_priority:
            priority_str = ", ".join(f"{k}={v}" for k, v in sorted(by_priority.items()))
            lines.append(f"Tasks by priority: {priority_str}")

    # Projects: name -> task count
    projects = context.get("all_projects") or []
    if projects:
        lines.append("\nProjects (name → task count):")
        for p in projects:
            name = p.get("name", "Unknown")
            count = p.get("tasks_count", 0)
            lines.append(f"  - {name}: {count}")

    # Users with tasks: include username so questions by email/username can resolve
    assignments = context.get("user_assignments") or []
    if assignments:
        lines.append("\nUsers with tasks (name / username → total tasks; per-project in parentheses):")
        for a in assignments:
            name = a.get("name") or a.get("username", "Unknown")
            username = a.get("username", "")
            total = a.get("total_tasks", 0)
            per_project = []
            for proj in a.get("projects") or []:
                pname = proj.get("project_name", "Unknown")
                n = len(proj.get("tasks") or [])
                if n:
                    per_project.append(f"{pname}: {n}")
            user_label = f"{name}" if username == name else f"{name} (username: {username})"
            if per_project:
                lines.append(f"  - {user_label}: {total} ({', '.join(per_project)})")
            else:
                lines.append(f"  - {user_label}: {total}")

    # Users with zero tasks (from available_users vs assignments)
    if available_users:
        assigned_ids = {a.get("user_id") for a in assignments if a.get("total_tasks", 0) > 0}
        zero_users = [u for u in available_users if u.get("id") not in assigned_ids]
        if zero_users:
            lines.append("\nUsers with no tasks assigned:")
            for u in zero_users[:15]:
                name = u.get("name") or u.get("username", "Unknown")
                lines.append(f"  - {name}")

    lines.append("\nAnswer using ONLY the numbers above. Do not list individual tasks or users.")
    return "\n".join(lines)


def _normalize_key(name: str) -> str:
    name = (name or "").lower().strip()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"[^a-z0-9 _-]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _format_pairs(pairs: Dict[str, int], sep: str = ", ") -> str:
    return sep.join(f"{k}={v}" for k, v in pairs.items())


def _extract_quoted_value(question: str) -> Optional[str]:
    m = re.search(r"'([^']+)'", question)
    if m:
        return m.group(1).strip()
    return None


def _extract_user_id(question: str) -> Optional[int]:
    # Common phrasings in tests:
    # - "user with ID 4"
    # - "user with id=4"
    # - "user id 4"
    m = re.search(r"\buser\b[^\d]{0,20}\b(?:id|id=|id:)\s*=?\s*(\d+)\b", question, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"\buser\b[^\d]{0,20}\bwith\s+id\s*(\d+)\b", question, flags=re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None


def _get_assignment_for_username(context: Dict, username_query: str) -> Optional[Dict]:
    if not username_query:
        return None
    uq = _normalize_key(username_query)
    for a in context.get("user_assignments") or []:
        username = a.get("username") or ""
        name = a.get("name") or ""
        if uq and (uq in _normalize_key(username) or uq in _normalize_key(name)):
            return a
    return None


def _get_assignment_for_user_id(context: Dict, user_id: int) -> Optional[Dict]:
    if not user_id:
        return None
    for a in context.get("user_assignments") or []:
        if a.get("user_id") == user_id:
            return a
    return None


def _iter_all_assignment_tasks(assignment: Dict):
    for proj in assignment.get("projects") or []:
        for t in proj.get("tasks") or []:
            yield proj.get("project_id"), proj.get("project_name"), t


def _try_answer_count_question_locally(question: str, context: Dict) -> Optional[str]:
    if not context:
        return None

    q = (question or "").lower()

    # ------------------------------------------------------------
    # User-specific questions (by quoted username/email)
    # ------------------------------------------------------------
    quoted_user = _extract_quoted_value(question)
    assignment = None
    if quoted_user:
        assignment = _get_assignment_for_username(context, quoted_user)
    if assignment is None:
        user_id = _extract_user_id(question)
        if user_id is not None:
            assignment = _get_assignment_for_user_id(context, user_id)

    if assignment and ("broken down by status" in q or "by status" in q or "each status" in q):
        counts = Counter()
        for _, _, t in _iter_all_assignment_tasks(assignment):
            s = _normalize_key(t.get("status"))
            if s:
                counts[s] += 1
        total = assignment.get("total_tasks")
        # Prefer total from assignment (ORM-derived); else sum.
        total_val = int(total) if isinstance(total, int) else sum(counts.values())
        pairs = {k: counts.get(k, 0) for k in sorted(counts.keys())}
        return f"{total_val} tasks, " + _format_pairs(pairs)

    if assignment and ("each project" in q or "in which projects" in q or "each one have" in q or "in each project" in q):
        per_project: Dict[str, int] = {}
        for proj in assignment.get("projects") or []:
            pname = proj.get("project_name")
            pid = proj.get("project_id")
            if not pname:
                continue
            key = f"{pname} (ID:{pid})" if pid is not None else pname
            per_project[key] = len(proj.get("tasks") or [])
        total = assignment.get("total_tasks")
        total_val = int(total) if isinstance(total, int) else sum(per_project.values())
        per_project_sorted = dict(sorted(per_project.items(), key=lambda kv: kv[0].lower()))
        return f"{total_val} total tasks. " + ", ".join(f"{k}: {v}" for k, v in per_project_sorted.items())

    # ------------------------------------------------------------
    # Owner-wide aggregates (across all tasks in context)
    # ------------------------------------------------------------
    tasks = context.get("tasks") or []
    if not tasks and context.get("project") and context["project"].get("tasks"):
        tasks = context["project"]["tasks"]

    # Handle assigned/unassigned count questions
    if ("assigned" in q or "unassigned" in q) and ("how many" in q or "count" in q or "number" in q):
        assigned = [t for t in tasks if t.get("assignee_id") or t.get("assignee_username")]
        unassigned = [t for t in tasks if not t.get("assignee_id") and not t.get("assignee_username")]
        project_name = ""
        if context.get("project"):
            project_name = context["project"].get("name", "")
        scope = f" in {project_name}" if project_name else ""
        return f"{len(assigned)} assigned tasks, {len(unassigned)} unassigned tasks{scope}."

    if ("tasks in each status" in q) or ("by status" in q) or ("broken down by status" in q):
        by_status = Counter(_normalize_key(t.get("status")) for t in tasks if t.get("status"))
        by_status.pop("", None)
        total = len(tasks)
        pairs = {k: by_status.get(k, 0) for k in sorted(by_status.keys())}
        return f"{total}, " + _format_pairs(pairs)

    if ("by priority" in q) or ("priority level" in q) or ("breakdown by priority" in q):
        by_priority = Counter(_normalize_key(t.get("priority")) for t in tasks if t.get("priority"))
        by_priority.pop("", None)
        total = len(tasks)
        pairs = {k: by_priority.get(k, 0) for k in sorted(by_priority.keys())}
        return f"{total}, " + _format_pairs(pairs)

    # Short-hand questions (these must NOT override broader breakdown questions)
    if ("to do" in q and "in progress" in q) and ("how many" in q) and ("each status" not in q) and ("tasks in each status" not in q):
        todo = sum(1 for t in tasks if _normalize_key(t.get("status")) == "todo")
        in_prog = sum(1 for t in tasks if _normalize_key(t.get("status")) == "in_progress")
        return f"todo={todo}, in_progress={in_prog}"

    if ("done" in q and "blocked" in q) and ("how many" in q) and ("each status" not in q) and ("tasks in each status" not in q):
        done = sum(1 for t in tasks if _normalize_key(t.get("status")) == "done")
        blocked = sum(1 for t in tasks if _normalize_key(t.get("status")) == "blocked")
        return f"done={done}, blocked={blocked}"

    if ("how many tasks" in q or "tasks does each project have" in q) and ("each project" in q or "per project" in q):
        # Always include project IDs so duplicate names are disambiguated.
        per_project = Counter(
            (t.get("project_id"), t.get("project_name"))
            for t in tasks
            if t.get("project_name") and t.get("project_id") is not None
        )
        parts = []
        for (pid, pname), cnt in sorted(per_project.items(), key=lambda kv: (str(kv[0][1]).lower(), kv[0][0])):
            parts.append(f"{pname} (ID:{pid})={cnt}")
        return ", ".join(parts)

    # Users with tasks (and per-project+assignee) are best derived from user_assignments.
    assignments = context.get("user_assignments") or []

    if "which users have" in q and "how many tasks" in q:
        per_user = {}
        for a in assignments:
            total = a.get("total_tasks", 0) or 0
            if total > 0:
                per_user[a.get("username") or a.get("name") or "unknown"] = int(total)
        per_user_sorted = dict(sorted(per_user.items(), key=lambda kv: (kv[0] or "").lower()))
        return ", ".join(f"{k}={v}" for k, v in per_user_sorted.items())

    if "for each project and user" in q and "how many tasks" in q:
        # Prefer computing from tasks (covers all assignees, not just the first N users).
        per_proj_user = Counter()
        for t in tasks:
            pid = t.get("project_id")
            pname = t.get("project_name")
            username = t.get("assignee_username")
            if pid is None or not pname or not username:
                continue
            per_proj_user[(pid, pname, username)] += 1
        if per_proj_user:
            parts = []
            for (pid, pname, username), cnt in sorted(
                per_proj_user.items(), key=lambda kv: (str(kv[0][1]).lower(), kv[0][0], str(kv[0][2]).lower())
            ):
                parts.append(f"{pname} (ID:{pid}):{username}={cnt}")
            return ", ".join(parts)

        # Fallback to user_assignments if tasks don't have assignee info.
        parts = []
        for a in assignments:
            username = a.get("username") or a.get("name")
            if not username:
                continue
            for proj in a.get("projects") or []:
                pname = proj.get("project_name")
                pid = proj.get("project_id")
                if not pname:
                    continue
                cnt = len(proj.get("tasks") or [])
                if cnt:
                    key = f"{pname} (ID:{pid})" if pid is not None else pname
                    parts.append((key, username, cnt))
        parts.sort(key=lambda x: (x[0].lower(), x[1].lower()))
        return ", ".join(f"{p}:{u}={c}" for p, u, c in parts)

    if "how many tasks and how many distinct assigned users" in q:
        # Prefer computing from tasks so project/user counts cover all assignees.
        per_project_tasks = Counter()
        per_project_users = {}
        for t in tasks:
            pid = t.get("project_id")
            pname = t.get("project_name")
            if pid is None or not pname:
                continue
            key = f"{pname} (ID:{pid})"
            per_project_tasks[key] += 1
            username = t.get("assignee_username")
            if username:
                per_project_users.setdefault(key, set()).add(username)

        if per_project_tasks:
            names = sorted(per_project_tasks.keys(), key=lambda s: s.lower())
            return ", ".join(
                f"{n}:tasks={per_project_tasks[n]},users={len(per_project_users.get(n, set()))}"
                for n in names
            )

        # Fallback to user_assignments.
        per_project_tasks = Counter()
        per_project_users = {}
        for a in assignments:
            username = a.get("username") or a.get("name")
            if not username:
                continue
            for proj in a.get("projects") or []:
                pname = proj.get("project_name")
                pid = proj.get("project_id")
                if not pname:
                    continue
                cnt = len(proj.get("tasks") or [])
                if cnt:
                    key = f"{pname} (ID:{pid})" if pid is not None else pname
                    per_project_tasks[key] += cnt
                    per_project_users.setdefault(key, set()).add(username)
        names = sorted(per_project_tasks.keys(), key=lambda s: s.lower())
        return ", ".join(
            f"{n}:tasks={per_project_tasks[n]},users={len(per_project_users.get(n, set()))}"
            for n in names
        )

    if "high priority" in q and "how many" in q and "projects" in q:
        per_project_high = Counter(
            (t.get("project_id"), t.get("project_name"))
            for t in tasks
            if t.get("project_name")
            and t.get("project_id") is not None
            and _normalize_key(t.get("priority")) == "high"
        )
        parts = []
        for (pid, pname), cnt in sorted(per_project_high.items(), key=lambda kv: (str(kv[0][1]).lower(), kv[0][0])):
            if cnt:
                parts.append(f"{pname} (ID:{pid})={cnt}")
        return ", ".join(parts)

    return None


class KnowledgeQAAgent(BaseAgent):
    """
    Agent responsible for:
    - Answer questions about project status
    - Provide information about tasks, deadlines, and team members
    - Search project history and documentation
    - Explain project workflows and processes
    - Assist with project-related queries
    - Provide contextual help and guidance
    - Retrieve project information quickly
    - Support natural language queries
    - Learn from project patterns and provide insights
    """
    
    def __init__(self):
        super().__init__()
        self.system_prompt = """You are a Knowledge Q&A Agent for a project management system.
        Your role is to answer questions about projects, tasks, team members, users, and provide helpful information.
        You ONLY provide descriptive answers and information - you do NOT perform actions like creating projects, tasks, or modifying users.
        You have READ-ONLY access to user information (users added by the company user, their roles, and their task assignments).
        You can view and report on user information, but you CANNOT create, update, or delete users.
        For action requests (creating projects, tasks, etc.), users should use the Project Pilot agent.
        You should be conversational, accurate, and provide context-aware responses.

        IMPORTANT - Count and aggregate questions: When the user asks for a count, total, or aggregate (e.g. "how many tasks", "how many users", "breakdown by status"), answer with ONLY the number(s) and at most one short sentence. Do NOT list individual tasks, projects, or users unless the question explicitly asks for a list. Use the AGGREGATES section when provided."""
    
    def answer_question(self, question: str, context: Optional[Dict] = None,
                       available_users: Optional[List[Dict]] = None,
                       session_id: Optional[str] = None,
                       chat_history: Optional[List[Dict]] = None) -> Dict:
        """
        Answer a question about the project. This agent ONLY provides descriptive answers.
        Enhanced with conversational memory and answer quality improvements.
        For action requests (creating projects/tasks), use the Project Pilot agent.

        Args:
            question (str): User's question
            context (Dict): Optional context (project info, tasks, etc.)
            available_users (List[Dict]): List of available users/team members
            session_id (str): Optional session ID for conversation memory
            chat_history (List[Dict]): Optional list of {role, content} for this chat

        Returns:
            Dict: Answer with relevant information and enhancements
        """
        self.log_action("Answering question", {"question": question[:50], "session_id": session_id})
        
        # Enhanced: Get conversation history (prefer explicit chat_history from request, else session-based)
        conversation_context = ""
        if chat_history and len(chat_history) > 0:
            lines = []
            for msg in chat_history[-10:]:
                role = (msg.get("role") or "user").lower()
                content = (msg.get("content") or "").strip()
                if not content:
                    continue
                if role == "assistant":
                    lines.append(f"A: {content[:300]}{'...' if len(content) > 300 else ''}")
                else:
                    lines.append(f"Q: {content[:300]}{'...' if len(content) > 300 else ''}")
            if lines:
                conversation_context = "\n\nPrevious conversation (this chat):\n" + "\n".join(lines) + "\n\nUse the above when the question is a follow-up; reference it in your answer when relevant.\n"
        elif session_id:
            try:
                conversation_context = KnowledgeQAEnhancements.build_conversation_context(session_id)
            except Exception as e:
                self.log_action("Error building conversation context", {"error": str(e)})
        
        # Build context string
        context_str = ""
        if context:
            # Always show all projects first
            if 'all_projects' in context:
                projects = context['all_projects']
                context_str += f"\nAll Your Projects ({len(projects)} total):\n"
                for proj in projects:
                    context_str += f"- ID: {proj.get('id', 'N/A')}, Name: {proj.get('name', 'Unknown')}, "
                    context_str += f"Status: {proj.get('status', 'Unknown')}, "
                    context_str += f"Priority: {proj.get('priority', 'Unknown')}, "
                    context_str += f"Tasks: {proj.get('tasks_count', 0)}\n"
                    if proj.get('description'):
                        context_str += f"  Description: {proj.get('description', '')}\n"
            
            # Show specific project details if provided
            if 'project' in context:
                project = context['project']
                context_str += f"\nCurrent Project (Selected):\n"
                context_str += f"- Name: {project.get('name', 'Unknown')}\n"
                context_str += f"- ID: {project.get('id', 'Unknown')}\n"
                context_str += f"- Status: {project.get('status', 'Unknown')}\n"
                context_str += f"- Tasks: {len(project.get('tasks', []))} tasks\n"
                # Show tasks nested inside the selected project
                if project.get('tasks'):
                    context_str += f"\nTasks in Selected Project:\n"
                    for task in project['tasks']:
                        task_line = f"- ID: {task.get('id', 'N/A')}, Title: {task.get('title', '')} (Status: {task.get('status', '')}, Priority: {task.get('priority', 'N/A')})"
                        if task.get('assignee_username'):
                            task_line += f" [Assigned to: {task.get('assignee_username')}]"
                        else:
                            task_line += f" [Unassigned]"
                        context_str += task_line + "\n"

            # Show tasks
            if 'tasks' in context:
                context_str += f"\nCurrent Tasks:\n"
                for task in context['tasks'][:20]:  # Show more tasks
                    task_line = f"- ID: {task.get('id', 'N/A')}, Title: {task.get('title', '')} (Status: {task.get('status', '')}, Priority: {task.get('priority', 'N/A')})"
                    if task.get('assignee_username'):
                        task_line += f" [Assigned to: {task.get('assignee_username')}]"
                    if task.get('project_name'):
                        task_line += f" [Project: {task.get('project_name')}]"
                    context_str += task_line + "\n"
        
        # Add available users information to context string
        if available_users:
            context_str += f"\n\n📋 USERS ADDED BY COMPANY USER ({len(available_users)} total):\n"
            context_str += "NOTE: You have READ-ONLY access to this user information. You can view and report on users, but you CANNOT create, update, or delete users.\n\n"
            for user in available_users:
                context_str += f"- ID: {user.get('id', 'N/A')}, Username: {user.get('username', 'Unknown')}, Name: {user.get('name', user.get('username', 'Unknown'))}\n"
                if 'role' in user:
                    context_str += f"  Role: {user.get('role', 'team_member')}\n"
                if 'email' in user:
                    context_str += f"  Email: {user.get('email', 'N/A')}\n"
                context_str += f"  Status: {'Active' if user.get('is_active', True) else 'Inactive'}\n"
        
        # Users information is already added to context_str above
        users_str = ""
        
        # Add user-task assignments if available
        assignments_str = ""
        if 'user_assignments' in context:
            assignments_str = "\n\n📋 USER-TASK ASSIGNMENTS:\n"
            assignments_str += f"Total Users with Assignments: {len([u for u in context['user_assignments'] if u.get('total_tasks', 0) > 0])}\n\n"
            
            for assignment in context['user_assignments']:
                if assignment.get('total_tasks', 0) > 0:
                    assignments_str += f"\n👤 {assignment.get('name', assignment.get('username', 'Unknown'))} (Username: {assignment.get('username', 'Unknown')}) - {assignment.get('total_tasks', 0)} task(s) assigned:\n"
                    for project_info in assignment.get('projects', []):
                        assignments_str += f"  📁 Project: {project_info.get('project_name', 'Unknown')}\n"
                        for task in project_info.get('tasks', []):
                            assignments_str += f"    - Task: \"{task.get('title', 'Unknown')}\" (Status: {task.get('status', 'N/A')}, Priority: {task.get('priority', 'N/A')})\n"
                else:
                    assignments_str += f"\n👤 {assignment.get('name', assignment.get('username', 'Unknown'))} (Username: {assignment.get('username', 'Unknown')}) - No tasks assigned\n"
        
        context_str += assignments_str
        
        # Classify question: count/aggregate vs list/detail. Count questions use compact context and short answers.
        question_lower = question.lower()
        # Action detection: avoid false positives from words like "assigned".
        # We match common imperative verbs as whole words.
        is_action_request = bool(
            re.search(r"\b(create|add|make|update|change|modify|edit|set|adjust)\b", question_lower)
        )
        # "assign" should only trigger when it's used as a verb (not "assigned")
        if re.search(r"\bassign\b", question_lower) and not re.search(r"\bassigned\b", question_lower):
            is_action_request = True
        is_count_question = _is_count_or_aggregate_question(question)
        
        if is_action_request:
            # Redirect to Project Pilot agent
            prompt = f"""The user is asking you to perform an action (like creating a project or task).

{context_str}
{users_str}

User Request: {question}

You are the Knowledge Q&A agent. You ONLY answer questions and provide information.
You do NOT perform actions like creating projects or tasks.

Respond politely that:
1. You only answer questions and provide information
2. For action requests like creating projects or tasks, they should use the Project Pilot agent
3. You can help them understand their projects and tasks, but cannot create them

Example response:
"I'm the Knowledge Q&A agent, and I only provide information and answer questions. For creating projects or tasks, please use the Project Pilot agent. However, I can help you understand your current projects and tasks if you have questions about them!"

Return a helpful text response (NOT JSON)."""
            max_tokens = 400
            relevant_results = []
        elif is_count_question and context:
            # Deterministic path for count/aggregate questions.
            # This avoids hallucinations and makes results match the DB/ORM ground truth.
            local_answer = _try_answer_count_question_locally(question, context)
            if local_answer is not None:
                return {
                    "success": True,
                    "answer": local_answer,
                    "question": question,
                    "token_usage": None,
                }

            # Fallback to LLM if we couldn't recognize the pattern.
            aggregates_str = _build_aggregates_context(context, available_users)
            prompt = f"""Use the AGGREGATES below to answer the question. Give ONLY the requested number(s) and at most one short sentence. Do not list individual tasks, projects, or users.

{aggregates_str}

Question: {question}

Answer briefly with the requested number(s)."""
            max_tokens = 250
            relevant_results = []
        else:
            # Full context path for list/detail questions
            relevant_results = []
            if context:
                try:
                    relevant_results = KnowledgeQAEnhancements.semantic_search(
                        question, context, top_k=5
                    )
                    if relevant_results:
                        context_str += "\n\n🔍 Most Relevant Results (Semantic Search):\n"
                        for i, result in enumerate(relevant_results[:3], 1):
                            context_str += f"{i}. {result['type'].upper()}: {result['title']} (Confidence: {result['confidence']:.2f})\n"
                except Exception as e:
                    self.log_action("Error in semantic search", {"error": str(e)})
            
            prompt = f"""Answer the following question about the project management system.
        
{context_str}
{users_str}
{conversation_context}

Question: {question}

IMPORTANT INSTRUCTIONS:
- You have READ-ONLY access to user information. You can view and report on users, their roles, and their task assignments, but you CANNOT create, update, or delete users.
- If the question asks ONLY for a count or total (e.g. "how many"), give the number(s) and one short sentence; do not list individual items unless asked.
- If the question asks about users (e.g., "how many users do I have", "what are their roles"), use the "USERS ADDED BY COMPANY USER" section above to provide detailed information.
- If the question asks for a list or details: list all users with their roles, email addresses, and status; use "USER-TASK ASSIGNMENTS" for task assignments; include task titles, status, priority, and project.
- If a user has no tasks assigned, mention that clearly.
- Provide a clear, organized answer that's easy to read.

Provide a helpful, accurate answer. If the question is about specific data that isn't in the context, mention that.
Be conversational and clear."""
            max_tokens = 800
        
        try:
            # Reset last_llm_usage before the main QA call so we can capture token usage.
            self.last_llm_usage = None
            response = self._call_llm(prompt, self.system_prompt, temperature=0.7, max_tokens=max_tokens)
            
            # Enhanced: Improve answer quality
            enhanced_answer = KnowledgeQAEnhancements.enhance_answer_quality(
                question, response, context or {}
            )
            
            # Add semantic search results to answer
            if relevant_results:
                enhanced_answer['semantic_search_results'] = relevant_results
            
            # Enhanced: Add to conversation history
            if session_id:
                try:
                    KnowledgeQAEnhancements.add_to_conversation(
                        session_id, question, response, context
                    )
                except Exception as e:
                    self.log_action("Error saving conversation", {"error": str(e)})
            
            # Enhanced: Generate proactive insights
            insights = []
            charts = {}
            if context:
                try:
                    insights = KnowledgeQAEnhancements.generate_proactive_insights(context)
                    
                    # Generate charts for insights if available
                    if insights:
                        charts['insights'] = ChartGenerator.generate_insights_chart(insights)
                    
                    # Generate status distribution chart if tasks available
                    if context.get('tasks'):
                        charts['status_distribution'] = ChartGenerator.generate_status_distribution_chart(
                            context['tasks']
                        )
                except Exception as e:
                    self.log_action("Error generating insights/charts", {"error": str(e)})
            
            result = {
                "success": True,
                **enhanced_answer,
                "proactive_insights": insights,
                "question": question,
                # Expose Groq token usage for this QA call (if available)
                "token_usage": self.last_llm_usage,
            }
            
            # Add charts if available
            if charts:
                result['charts'] = charts
            
            return result
        except Exception as e:
            self.log_action("Error answering question", {"error": str(e)})
            return {
                "success": False,
                "error": str(e),
                "answer": "I'm sorry, I encountered an error while processing your question. Please try again."
            }
    
    def search_project_history(self, query: str, project_id: int) -> Dict:
        """
        Search project history and documentation.
        
        Args:
            query (str): Search query
            project_id (int): Project ID to search
            
        Returns:
            Dict: Search results
        """
        # This would typically search a database or knowledge base
        # For now, return a placeholder
        return {
            "success": True,
            "query": query,
            "results": [],
            "message": "Project history search not yet fully implemented"
        }
    
    def explain_workflow(self, workflow_name: str) -> Dict:
        """
        Explain a project workflow or process.
        
        Args:
            workflow_name (str): Name of the workflow
            
        Returns:
            Dict: Workflow explanation
        """
        prompt = f"""Explain the project management workflow or process: {workflow_name}

Provide a clear, step-by-step explanation of how this workflow works."""
        
        try:
            explanation = self._call_llm(prompt, self.system_prompt, temperature=0.5)
            return {
                "success": True,
                "workflow": workflow_name,
                "explanation": explanation
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_project_summary(self, project_id: int) -> Dict:
        """
        Get a comprehensive summary of a project.
        
        Args:
            project_id (int): Project ID
            
        Returns:
            Dict: Project summary
        """
        # This would fetch project data and generate summary
        return {
            "success": True,
            "project_id": project_id,
            "summary": "Project summary generation not yet fully implemented"
        }
    
    def provide_insights(self, project_id: int) -> Dict:
        """
        Provide insights based on project patterns.
        
        Args:
            project_id (int): Project ID
            
        Returns:
            Dict: Project insights
        """
        # This would analyze project data and provide insights
        return {
            "success": True,
            "project_id": project_id,
            "insights": "Insight generation not yet fully implemented"
        }
    
    def process(self, question: str, **kwargs) -> Dict:
        """
        Main processing method for Q&A agent.
        
        Args:
            question (str): User's question or query
            **kwargs: Additional context parameters (context, available_users, etc.)
            
        Returns:
            dict: Answer and relevant information, may include action to perform
        """
        self.log_action("Processing question", {"question": question[:50]})
        
        context = kwargs.get('context', {})
        available_users = kwargs.get('available_users', [])
        session_id = kwargs.get('session_id')
        chat_history = kwargs.get('chat_history') or []
        return self.answer_question(question, context, available_users, session_id, chat_history=chat_history)


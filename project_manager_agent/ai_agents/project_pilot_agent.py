"""
Project Pilot Agent
Handles all action requests like creating projects, tasks, and managing project operations.
"""

from .base_agent import BaseAgent
from .enhancements.project_pilot_enhancements import ProjectPilotEnhancements
from .context_manager import ContextManager
from typing import Dict, Optional, List
import json
import re


class ProjectPilotAgent(BaseAgent):
    """
    Agent responsible for:
    - Creating new projects
    - Creating tasks in existing projects
    - Deleting projects and tasks
    - Handling action requests from users
    - Managing project operations
    - Extracting action details from natural language
    """
    
    def __init__(self):
        super().__init__()
        self.system_prompt = """You are an intelligent Project Pilot Agent for a project management system.
        Your role is to understand user intent and handle action requests like creating and deleting projects and tasks.
        
        CRITICAL INSTRUCTIONS:
        1. Always analyze the FULL context of the user's request before deciding what action to take
        2. Understand the INTENT behind the request, not just keywords
        3. When the user clearly asks to add task(s) to a named project (e.g. "add one task in [project name] for [topic]"), EXECUTE the action—do NOT ask for clarification. Only ask when project or intent is truly ambiguous.
        4. Distinguish clearly between:
           - Creating NEW projects vs updating existing tasks
           - Creating NEW tasks vs updating existing tasks
           - Adding tasks to existing projects vs creating new projects
        5. Only update existing tasks if the user EXPLICITLY asks to update/modify specific existing tasks
        6. When creating a new project, NEVER update existing tasks - always create new tasks
        7. Be thoughtful and reason through each request before responding
        
        You extract action details from user requests and return structured JSON, but ONLY when the intent is clear.
        If ambiguous, ask for clarification with helpful questions."""
    
    def handle_action_request(self, question: str, context: Optional[Dict] = None, available_users: Optional[List[Dict]] = None, chat_history: Optional[List[Dict]] = None) -> Dict:
        """
        Handle action requests like creating projects and tasks.
        
        Args:
            question (str): User's request/question
            context (Dict): Optional context (project info, tasks, etc.)
            available_users (List[Dict]): List of available users/team members
            
        Returns:
            Dict: Actions to perform in structured format
        """
        self.log_action("Handling action request", {"question": question[:50]})
        
        # Enhanced: Check for similar projects if creating new project
        if context:
            # Try to get user ID from context
            user_id = None
            if 'user_id' in context:
                user_id = context['user_id']
            elif 'project' in context and 'owner_id' in context['project']:
                user_id = context['project']['owner_id']
            elif 'all_projects' in context and len(context['all_projects']) > 0:
                user_id = context['all_projects'][0].get('owner_id')
            
            # Check if this is a project creation request
            question_lower = question.lower()
            is_project_creation = any(phrase in question_lower for phrase in [
                'create', 'make', 'build', 'develop', 'design', 'new project'
            ]) and 'project' in question_lower
            
            if is_project_creation and user_id:
                try:
                    similar_projects = ProjectPilotEnhancements.analyze_similar_projects(
                        question, user_id, limit=3
                    )
                    if similar_projects:
                        context['similar_projects'] = similar_projects
                        self.log_action("Found similar projects", {"count": len(similar_projects)})
                except Exception as e:
                    self.log_action("Error finding similar projects", {"error": str(e)})
        
        question_lower = question.lower()
        
        # Distinguish between different types of requests with better context awareness
        assignment_keywords = ['assign', 'reassign', 'delegate']
        creation_keywords = ['create', 'add', 'make', 'new task', 'add task', 'new project', 'make project', 'build', 'develop', 'design', 'start']
        deletion_keywords = ['delete', 'remove', 'destroy', 'drop']
        # Update keywords should NOT trigger if context suggests creation
        # Only treat as update if explicitly about modifying existing items
        update_keywords = ['update', 'change', 'modify', 'edit', 'set', 'adjust', 'alter']
        
        # Better detection: check for explicit update context
        # If user says "create new project" or "create me a project", it's creation NOT update
        has_explicit_creation = any(phrase in question_lower for phrase in [
            'create', 'make', 'build', 'develop', 'design', 'new project', 'new task',
            'create me', 'create a', 'make a', 'build a', 'start a'
        ])
        
        # Check if user is describing a project/system with features, modules, services
        # This indicates a NEW PROJECT creation request even without explicit creation keywords
        project_description_indicators = [
            'is a', 'is an', 'centralized', 'dashboard', 'system', 'platform', 'application',
            'has following', 'has the following', 'with features', 'features:', 'modules:', 'services:',
            'key features', 'core infrastructure', 'purpose:', 'target users', 'tech angle',
            'external apis', 'module', 'service', 'infrastructure layer'
        ]
        has_project_description = any(indicator in question_lower for indicator in project_description_indicators)
        
        # Check if query contains detailed project specifications (multiple lines, features, etc.)
        is_detailed_spec = len(question.split('\n')) > 2 or (
            any(word in question_lower for word in ['features', 'modules', 'services', 'infrastructure', 'api', 'dashboard']) and
            len(question) > 100
        )
        
        # If user describes a project/system in detail, treat it as creation request
        if has_project_description or is_detailed_spec:
            has_explicit_creation = True
        
        # Update should only trigger if explicitly about existing items
        has_explicit_update_context = any(phrase in question_lower for phrase in [
            'update existing', 'update the', 'update this', 'modify existing', 'change existing',
            'edit existing', 'update task', 'update project', 'modify task', 'change task'
        ])
        
        is_assignment_request = any(keyword in question_lower for keyword in assignment_keywords) and not has_explicit_creation
        is_creation_request = has_explicit_creation
        # IMPORTANT: Only detect deletion if explicitly about deletion AND not describing a new project
        # If user is describing a project/system in detail, it's creation NOT deletion
        is_deletion_request = (
            any(keyword in question_lower for keyword in deletion_keywords) and
            not has_project_description and
            not is_detailed_spec
        )
        # Only treat as update if explicitly about updating existing items AND not creating
        is_update_request = any(keyword in question_lower for keyword in update_keywords) and has_explicit_update_context and not has_explicit_creation
        is_action_request = is_assignment_request or is_creation_request or is_deletion_request or is_update_request
        
        # Check for things the agent CANNOT do
        cannot_do = None
        cannot_do_item = None
        
        # More robust detection - check for user creation patterns
        # BUT exclude cases where user mentions are about task assignment (e.g., "assign to users:", "assign to following users")
        action_words = ['create', 'add', 'make', 'new', 'register']
        user_words = ['user', 'users', 'account', 'accounts']
        
        has_action = any(word in question_lower for word in action_words)
        has_user = any(word in question_lower for word in user_words)
        
        # Check if this is about assigning tasks to users (not creating users)
        assignment_patterns = ['assign to', 'assign tasks to', 'assign to following', 'assign to users', 
                              'assign to the following', 'only assign', 'assign only', 'assign these',
                              'following users', 'users:', 'assign:', 'username:']
        is_assignment_context = any(pattern in question_lower for pattern in assignment_patterns)
        
        # If both action and user words are present, check if it's actually about user creation
        # NOT about assigning tasks to existing users
        if has_action and has_user and not is_assignment_context:
            # Only block if it's explicitly about creating users/accounts
            if any(phrase in question_lower for phrase in [
                'create user', 'create users', 'create new user', 'create new users',
                'add user', 'add users', 'add new user', 'add new users',
                'make user', 'make users', 'make new user', 'make new users',
                'register user', 'register users', 'register new user',
                'create account', 'create accounts', 'create new account',
                'add account', 'add accounts', 'add new account',
                'new user account', 'new user accounts',
                'user account', 'user accounts'
            ]):
                cannot_do = True
                cannot_do_item = 'users or user accounts'
        
        # Check for team member creation
        if 'team member' in question_lower and any(word in question_lower for word in ['create', 'add', 'make']):
            cannot_do = True
            cannot_do_item = 'team members directly'
        
        # Build context string (optionally start with conversation history for this chat)
        context_str = ""
        if chat_history:
            recent = chat_history[-15:]  # last 15 messages
            context_str += "\n📜 CONVERSATION HISTORY (this chat)—use this to understand follow-ups (e.g. 'yes', 'do it') and reference when relevant:\n"
            for msg in recent:
                role = (msg.get("role") or "user").lower()
                content = (msg.get("content") or "").strip()
                if not content:
                    continue
                if role == "assistant":
                    context_str += f"Assistant: {content[:500]}{'...' if len(content) > 500 else ''}\n"
                else:
                    context_str += f"User: {content[:500]}{'...' if len(content) > 500 else ''}\n"
            context_str += "\nCurrent user message (respond to this):\n"
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
                context_str += f"- Tasks: {project.get('tasks_count', 0)} tasks\n"
            
            # Show tasks
            if 'tasks' in context:
                context_str += f"\nCurrent Tasks:\n"
                for task in context['tasks'][:20]:  # Show more tasks
                    task_id = task.get('id', 'N/A')
                    task_line = f"- ID: {task_id}, Title: {task.get('title', '')} (Status: {task.get('status', '')}, Priority: {task.get('priority', 'N/A')})"
                    if task.get('assignee_username'):
                        task_line += f" [Assigned to: {task.get('assignee_username')}]"
                    if task.get('project_name'):
                        task_line += f" [Project: {task.get('project_name')}]"
                    context_str += task_line + "\n"
        
        # Add user-task assignments if available
        if 'user_assignments' in context:
            context_str += f"\n\n📋 USER-TASK ASSIGNMENTS:\n"
            context_str += f"Total Users with Assignments: {len([u for u in context['user_assignments'] if u.get('total_tasks', 0) > 0])}\n\n"
            
            for assignment in context['user_assignments']:
                if assignment.get('total_tasks', 0) > 0:
                    context_str += f"\n👤 {assignment.get('name', assignment.get('username', 'Unknown'))} (Username: {assignment.get('username', 'Unknown')}) - {assignment.get('total_tasks', 0)} task(s) assigned:\n"
                    for project_info in assignment.get('projects', []):
                        context_str += f"  📁 Project: {project_info.get('project_name', 'Unknown')}\n"
                        for task in project_info.get('tasks', []):
                            context_str += f"    - Task: \"{task.get('title', 'Unknown')}\" (Status: {task.get('status', 'N/A')}, Priority: {task.get('priority', 'N/A')})\n"
        
        # Add available users information
        users_str = ""
        if available_users:
            users_str = "\nAvailable Users/Team Members:\n"
            for user in available_users:
                users_str += f"- ID: {user.get('id', 'N/A')}, Username: {user.get('username', 'Unknown')}, Name: {user.get('name', user.get('username', 'Unknown'))}\n"
                if 'role' in user:
                    users_str += f"  Role: {user.get('role')}\n"
        
        if is_action_request:
            # Handle assignment requests FIRST (assigning existing tasks) - these are NOT creation requests
            if is_assignment_request and not is_creation_request:
                # User wants to assign tasks, not create them
                prompt = f"""The user wants to ASSIGN existing tasks, not create new ones.

{context_str}
{users_str}

User Request: {question}

IMPORTANT: The user said "assign" which means they want to assign EXISTING tasks to a user.
You CANNOT assign tasks - that's a task management function, not a creation function.

You can ONLY:
- CREATE new tasks or projects

Respond politely that:
1. You cannot assign existing tasks to users (that's done through the task management interface)
2. You can only CREATE new tasks or projects
3. If they want to create NEW tasks and assign them, they should say "create tasks" not "assign tasks"

Return a helpful text response (NOT JSON) explaining this limitation. Example:
"I'm sorry, but I cannot assign existing tasks to users. I can only create new tasks or projects. If you'd like to create new tasks and assign them to a user, please ask me to 'create tasks in [project name] and assign them to [user]'."

Do NOT return JSON. Do NOT create any projects or tasks."""
            
            # Handle deletion requests
            elif is_deletion_request:
                # Check if user wants to delete projects
                project_deletion_keywords = ['delete project', 'remove project', 'delete projects', 'remove projects']
                task_deletion_keywords = ['delete task', 'remove task', 'delete tasks', 'remove tasks']
                
                wants_to_delete_projects = any(keyword in question_lower for keyword in project_deletion_keywords) or ('delete' in question_lower and 'project' in question_lower)
                wants_to_delete_tasks = any(keyword in question_lower for keyword in task_deletion_keywords) or ('delete' in question_lower and 'task' in question_lower and 'project' not in question_lower)
                
                if wants_to_delete_projects:
                    # User wants to delete projects
                    # Check for patterns like "delete all but X" or "delete X project"
                    prompt = f"""You are an AI assistant that extracts deletion actions from user requests. Analyze the request and return ONLY valid JSON.

{context_str}
{users_str}

User Request: {question}

The user wants to DELETE one or more projects.

IMPORTANT: Analyze the request carefully:
- If the request says "delete all but [project name]" or "delete all except [project name]": 
  → Create delete_project actions for ALL projects EXCEPT the one mentioned by name
  → Look at the list of projects above and include all project IDs except the one matching the name
- If the request says "delete [project name]": 
  → Create a delete_project action for that specific project
- If the request says "delete all projects" or "delete all": 
  → Create delete_project actions for ALL projects in the list above
- Otherwise: create delete_project actions for projects mentioned by name

Return ONLY this JSON format (no other text):
[
    {{
        "action": "delete_project",
        "project_id": project_id_number,
        "project_name": "project name",
        "reasoning": "brief explanation"
    }}
]

Rules:
- Return ONLY the JSON array, no explanations
- For "delete all but X", return delete_project actions for ALL project IDs from the context above EXCEPT the one whose name matches X
- Match project names from the user request to project names in the context (case-insensitive partial match is OK)
- Use exact project IDs from the context above
- Include ALL projects that should be deleted"""
                elif wants_to_delete_tasks:
                    # User wants to delete tasks
                    prompt = f"""You are an AI assistant that extracts deletion actions from user requests. Analyze the request and return ONLY valid JSON.

{context_str}
{users_str}

User Request: {question}

The user wants to DELETE one or more tasks.

Return ONLY this JSON format (no other text):
[
    {{
        "action": "delete_task",
        "task_id": task_id_number,
        "task_title": "task title",
        "reasoning": "brief explanation"
    }}
]

Rules:
- Return ONLY the JSON array, no explanations
- Match task titles from the user request to tasks in the context"""
                else:
                    # Ambiguous deletion request
                    prompt = f"""The user wants to delete something but the request is unclear.

{context_str}
{users_str}

User Request: {question}

The user mentioned "delete" but it's not clear if they want to delete:
- Projects
- Tasks
- Something else

Return a helpful text response (NOT JSON) asking for clarification:
"I understand you want to delete something. Could you please specify:
- Which project(s) do you want to delete? (e.g., 'delete Project X' or 'delete all projects')
- Or which task(s) do you want to delete? (e.g., 'delete task Y' or 'delete all tasks in Project X')

Do NOT return JSON. Do NOT delete anything."""
            # Handle update requests - ONLY if explicitly about updating existing items
            elif is_update_request and has_explicit_update_context:
                # Verify that user is actually asking to update existing tasks/projects
                # NOT asking to create something new
                
                # Check if it's an update request for tasks or projects
                priority_keywords = ['priority', 'priorities', 'prioritize']
                status_keywords = ['status', 'state']
                task_keywords = ['task', 'tasks']
                project_keywords = ['project', 'projects']
                
                is_priority_update = any(keyword in question_lower for keyword in priority_keywords)
                is_status_update = any(keyword in question_lower for keyword in status_keywords)
                is_task_update = any(keyword in question_lower for keyword in task_keywords)
                is_project_update = any(keyword in question_lower for keyword in project_keywords)
                
                # CRITICAL: Check if user mentions specific existing task IDs or task titles
                # If no specific tasks mentioned, it might be ambiguous
                has_specific_task_reference = False
                if context.get('tasks'):
                    for task in context['tasks']:
                        task_title = task.get('title', '').lower()
                        task_id = task.get('id')
                        # Check if task title or ID is mentioned in question
                        if task_title and task_title in question_lower:
                            has_specific_task_reference = True
                            break
                        # Check for task ID patterns
                        if task_id and (f'task {task_id}' in question_lower or f'task_id {task_id}' in question_lower):
                            has_specific_task_reference = True
                            break
                
                # If user wants to update but doesn't specify which tasks, ask for clarification
                if is_task_update and not has_specific_task_reference and not ('all' in question_lower and 'task' in question_lower):
                    prompt = f"""The user wants to update tasks, but their request is unclear.

{context_str}
{users_str}

User Request: {question}

I understand you want to update tasks, but I need clarification:
- Which specific task(s) do you want to update? Please mention the task title or ID.
- Or do you want to update all tasks in a specific project?
- What exactly do you want to change? (priority, status, assignee, description, etc.)

Please provide more details so I can help you correctly.

Examples:
- "Update task 'Database Design' to high priority"
- "Change status of all tasks in Project X to in_progress"
- "Update task ID 186 to high priority"

Do NOT return JSON. Do NOT update anything yet."""
                
                # Determine target project
                target_project_id = None
                if context.get('project'):
                    target_project_id = context['project']['id']
                elif context.get('all_projects'):
                    # Try to find project by name in the request
                    for proj in context['all_projects']:
                        proj_name = proj.get('name', '').lower()
                        if proj_name and proj_name in question_lower:
                            target_project_id = proj.get('id')
                            break
                    # If no project found by name, use first project
                    if not target_project_id and len(context['all_projects']) > 0:
                        target_project_id = context['all_projects'][0]['id']
                
                # Build detailed task list for context
                tasks_detail = ""
                if context.get('tasks'):
                    tasks_detail = "\nCurrent Tasks with IDs:\n"
                    for task in context['tasks']:
                        tasks_detail += f"- ID: {task.get('id', 'N/A')}, Title: {task.get('title', 'Unknown')}, "
                        tasks_detail += f"Status: {task.get('status', 'N/A')}, Priority: {task.get('priority', 'N/A')}\n"
                        if task.get('description'):
                            tasks_detail += f"  Description: {task.get('description', '')[:100]}...\n"
                elif target_project_id and context.get('all_projects'):
                    # Get tasks from project context if available
                    for proj in context['all_projects']:
                        if proj.get('id') == target_project_id:
                            tasks_detail = f"\nProject has {proj.get('tasks_count', 0)} tasks.\n"
                            break
                
                from datetime import datetime
                current_date_str = datetime.now().strftime('%Y-%m-%d')
                
                prompt = f"""You are an AI assistant that extracts UPDATE actions from user requests. Analyze the request and return ONLY valid JSON.

{context_str}
{tasks_detail}
{users_str}

User Request: {question}

The user wants to UPDATE existing tasks. You MUST:
1. Identify which tasks to update (by title or all tasks in project)
2. Determine what fields to update (priority, status, assignee, due_date, description, title, etc.)
3. Provide NEW values with DETAILED reasoning
4. For priority updates: analyze each task carefully considering dependencies, deadlines, importance, and project context

Available update fields:
- priority: "high", "medium", or "low"
- status: "todo", "in_progress", "review", "done", "blocked"
- assignee_id: user ID from available users list (or null to unassign)
- due_date: "YYYY-MM-DD" format
- title: new task title
- description: new task description

Return ONLY this JSON format (no other text):
[
    {{
        "action": "update_task",
        "task_id": task_id_number,
        "task_title": "current task title",
        "updates": {{
            "priority": "high|medium|low" (optional),
            "status": "todo|in_progress|review|done|blocked" (optional),
            "assignee_id": user_id_or_null (optional),
            "due_date": "YYYY-MM-DD" (optional),
            "title": "new title" (optional),
            "description": "new description" (optional)
        }},
        "reasoning": "DETAILED reasoning (3-5 sentences) explaining: (1) Why this update is needed, (2) How you analyzed the task context (dependencies, deadlines, project goals), (3) Why these specific values were chosen, (4) How this change affects the overall project/task priority, (5) Consideration of task relationships and critical path"
    }}
]

CRITICAL RULES:
- Return ONLY the JSON array, no explanations
- You MUST provide reasoning for EACH update (especially priority changes)
- For priority updates: analyze each task individually with careful thought
- Consider task dependencies, deadlines, project goals, and task relationships
- Use task IDs from the context above (match by title if ID not visible)
- If updating all tasks in a project: create one update_task action per task
- Include only fields that need to be changed in the "updates" object
- If priority is mentioned: analyze each task carefully and set appropriate priority with detailed reasoning
- Match task titles from user request to tasks in context (case-insensitive partial match OK)
- If user says "update priorities" or "update priority", update the priority field for relevant tasks
- Think carefully about each priority level: high for urgent/critical tasks, medium for normal tasks, low for nice-to-have tasks"""
            # Handle requests for things we can't do - PRIORITY CHECK
            elif cannot_do:
                prompt = f"""STOP. The user is asking you to do something you CANNOT and MUST NOT do.

User Request: {question}

CRITICAL: You CANNOT create {cannot_do_item}. You do NOT have access to user management functions.

You can ONLY:
- Create and delete Projects
- Create and delete Tasks (within existing projects)

DO NOT create any projects or tasks. DO NOT return JSON. 

Respond with a clear, polite text message explaining:
1. You cannot create {cannot_do_item}
2. You don't have access to user management
3. What you CAN help with instead (projects and tasks)

Example response:
"I'm sorry, but I cannot create {cannot_do_item}. I don't have access to user management functions in this system. However, I can help you create and delete projects and tasks. Would you like help with that instead?"

Return ONLY text - NO JSON, NO actions."""
            else:
                # Determine if user wants NEW project or tasks in EXISTING project
                # More flexible and intelligent detection
                new_project_indicators = ['new project', 'create project', 'make project', 'add project', 'start project',
                                         'create me a', 'create a', 'make a', 'build a', 'start a', 'develop a', 'design a',
                                         'which has', 'with features', 'with following', 'that has']
                wants_new_project = any(indicator in question_lower for indicator in new_project_indicators)
                
                # Additional context: if user describes features, modules, or services, it's likely a new project
                # Check for detailed project descriptions even without explicit creation keywords
                project_descriptor_patterns = [
                    'has following features', 'with features', 'which has', 'that has',
                    'features:', 'modules:', 'services:', 'core infrastructure',
                    'purpose:', 'external apis:', 'module', 'is a', 'is an',
                    'centralized dashboard', 'system', 'platform', 'application',
                    'key features', 'target users', 'tech angle', 'infrastructure layer',
                    'trust ledger', 'dynamic', 'aggregates', 'real-time', 'breakdown visuals',
                    'quantifies', 'dashboard', 'service', 'architecture'
                ]
                has_project_descriptors = any(pattern in question_lower for pattern in project_descriptor_patterns)
                
                # Check if query is a detailed project/system description
                # If it describes what a system IS and what it DOES, it's a new project request
                is_detailed_project_description = (
                    len(question.split('\n')) > 2 or len(question) > 150
                ) and (
                    has_project_descriptors or
                    any(word in question_lower for word in ['features', 'modules', 'services', 'infrastructure', 'dashboard', 'system'])
                )
                
                # If user describes a project/system in detail, treat it as NEW PROJECT creation
                # Even without explicit "create" or "make" keywords
                if has_project_descriptors or is_detailed_project_description:
                    wants_new_project = True
                
                # Also check if user mentions a project name that doesn't exist in context (likely a new project)
                if not wants_new_project and context.get('all_projects'):
                    # Check if the question contains project-related keywords but the project name isn't in existing projects
                    project_keywords = ['project', 'system', 'application', 'app', 'platform', 'website', 'portal']
                    has_project_keyword = any(keyword in question_lower for keyword in project_keywords)
                    if has_project_keyword:
                        # Extract potential project name (words after "create", "make", "build", etc.)
                        creation_verbs = ['create', 'make', 'build', 'start', 'develop', 'design']
                        for verb in creation_verbs:
                            if verb in question_lower:
                                # Likely a new project request
                                wants_new_project = True
                                break
                
                # Check if user mentions existing project by name (exact substring or fuzzy match)
                def _normalize_for_match(text):
                    """Normalize for project name matching: remove filler words, collapse spaces."""
                    if not text:
                        return ""
                    t = text.lower().strip()
                    for word in ("project", "system", "application", "app", "the", "a", "an"):
                        t = re.sub(rf"\b{re.escape(word)}\b", " ", t)
                    t = re.sub(r"\s+", " ", t).strip()
                    # Normalize task/tasks, management/managing, etc.
                    t = re.sub(r"\btasks\b", "task", t)
                    t = re.sub(r"\bmanaging\b", "management", t)
                    return t

                existing_project_mentioned = False
                project_id_to_use = None
                if context.get('all_projects'):
                    q_norm = _normalize_for_match(question)
                    for proj in context['all_projects']:
                        proj_name = proj.get('name', '')
                        proj_norm = _normalize_for_match(proj_name)
                        if not proj_norm:
                            continue
                        # Exact substring match
                        if proj_name.lower() in question_lower or proj_norm in q_norm:
                            existing_project_mentioned = True
                            project_id_to_use = proj.get('id')
                            break
                        # Fuzzy: all significant words of project name appear in question
                        proj_words = [w for w in proj_norm.split() if len(w) > 1]
                        if len(proj_words) >= 2 and all(pw in q_norm for pw in proj_words):
                            existing_project_mentioned = True
                            project_id_to_use = proj.get('id')
                            break
                        # Fuzzy: first 15 chars of normalized project name in question (e.g. "daily task manag")
                        if len(proj_norm) >= 5 and proj_norm[:15] in q_norm:
                            existing_project_mentioned = True
                            project_id_to_use = proj.get('id')
                            break
                
                # CRITICAL: If user said "add task in [name]" / "add a new task in [name]", that's the existing project—do NOT create a new project.
                add_task_in_patterns = ['add task in', 'add a task in', 'add new task in', 'add tasks in', 'add a new task to', 'add task to', 'add tasks to', 'in the', 'in project']
                if existing_project_mentioned or any(p in question_lower for p in add_task_in_patterns):
                    # Prefer "add to existing project" when they named a project (or used "in X" / "to X")
                    if existing_project_mentioned:
                        wants_new_project = False
                
                if wants_new_project:
                    # Check if user wants tasks assigned to all available developers
                    assign_to_all_keywords = ['assign to all', 'assign to all available', 'assign to all developers', 
                                             'assign to all users', 'distribute to all', 'assign tasks to all',
                                             'all available developers', 'all developers', 'all users']
                    wants_assign_to_all = any(keyword in question_lower for keyword in assign_to_all_keywords)
                    
                    # Check if user mentioned specific usernames to assign to
                    # Look for patterns like "assign to following users:", "username: abdullah", etc.
                    specific_usernames = []
                    assignment_keywords_in_question = ['assign to', 'assign tasks to', 'assign to following', 
                                                      'assign to users', 'only assign', 'assign only',
                                                      'following users', 'assign:', 'username:']
                    has_specific_assignment = any(keyword in question_lower for keyword in assignment_keywords_in_question)
                    
                    # Extract usernames from the question if available_users is provided
                    if has_specific_assignment and available_users:
                        # Look for username patterns in the question
                        for user_info in available_users:
                            username = user_info.get('username', '').lower()
                            name = user_info.get('name', '').lower()
                            # Check if username or name appears in the question
                            if username and username in question_lower:
                                specific_usernames.append(user_info)
                            elif name and name in question_lower:
                                specific_usernames.append(user_info)
                    
                    # User explicitly wants a NEW project
                    assignment_instruction = ""
                    if wants_assign_to_all and available_users:
                        assignment_instruction = f"""
CRITICAL ASSIGNMENT INSTRUCTION:
The user wants tasks assigned to ALL available developers/users. You MUST distribute tasks across ALL available users listed above.
- If there are {len(available_users)} users, create at least {len(available_users)} tasks (one per user minimum)
- Distribute tasks evenly across all users (round-robin style)
- Each task should have a different assignee_id from the available users list
- Use ALL user IDs from the available users list above
- Example: If there are 3 users (IDs: 1, 2, 3) and you create 6 tasks, assign: task1→user1, task2→user2, task3→user3, task4→user1, task5→user2, task6→user3"""
                    elif specific_usernames:
                        # User specified specific users to assign to
                        usernames_list = ', '.join([u.get('username', 'Unknown') for u in specific_usernames])
                        assignment_instruction = f"""
CRITICAL ASSIGNMENT INSTRUCTION:
The user wants tasks assigned ONLY to these specific users mentioned in their request: {usernames_list}
- You MUST assign tasks ONLY to these users from the available users list above
- Match the usernames mentioned in the request to the usernames in the available users list
- Distribute tasks evenly across ONLY these specific users
- Create at least one task per specified user, and distribute additional tasks among them
- DO NOT assign to users not mentioned in the request
- Example: If user mentioned "abdullah" and "hamza1", only use assignee_id for users with those usernames"""
                    elif wants_assign_to_all and not available_users:
                        assignment_instruction = "\nNOTE: User wants tasks assigned to all developers, but no users are available. Leave assignee_id as null."
                    else:
                        assignment_instruction = "\n- Use available user IDs from the list above if assignment is requested, otherwise leave assignee_id as null"
                    
                    prompt = f"""You are an intelligent AI assistant that understands user intent and extracts actions from requests. 

CRITICAL: The user wants to CREATE A NEW PROJECT. They are NOT asking to update existing tasks.
- DO NOT return update_task actions
- DO NOT modify existing tasks
- ONLY return create_project and create_task actions

{context_str}
{users_str}

User Request: {question}

ANALYSIS:
1. This is a NEW PROJECT creation request
2. The user has provided detailed features/modules/services to include
3. You must create a NEW project and NEW tasks - NOT update existing ones

REQUIRED ACTIONS:
1. First: create_project action with a descriptive name and comprehensive description
2. Then: 10-20 create_task actions breaking down all features/modules/services mentioned

{assignment_instruction}

Return ONLY this JSON format (no other text):
[
    {{
        "action": "create_project",
        "project_name": "Descriptive project name based on the system being built",
        "project_description": "Comprehensive description based on all features, modules, and services mentioned in the request. Include purpose, core infrastructure, modules, and external integrations.",
        "project_status": "planning",
        "project_priority": "medium",
        "deadline_days": null,
        "reasoning": "Brief explanation of why this project is being created based on the user's requirements"
    }},
    {{
        "action": "create_task",
        "task_title": "Specific task title that covers one feature/module/service",
        "task_description": "COMPREHENSIVE task description (4-6 sentences) that includes: (1) WHAT the task is - clear explanation of what needs to be accomplished, (2) HOW to do it - step-by-step approach and methodology, (3) WHICH TOOLS to use - specific technologies, frameworks, libraries, and tools recommended, (4) MOST EFFICIENT WAY - best practices and efficient approaches to complete this task, including any shortcuts or optimizations. Make it actionable and detailed enough that a developer can understand exactly what to build and how to approach it.",
        "project_id": null,
        "assignee_id": user_id_or_null,
        "priority": "high|medium|low",
        "status": "todo",
        "reasoning": "DETAILED AI reasoning and judgment (5-7 sentences) that includes: (1) WHY this task is important for the overall project and how it contributes to project completion, (2) TASK BREAKDOWN - logical decomposition of the task into manageable components, (3) EFFICIENCY ANALYSIS - reasoning about the most efficient approach considering dependencies, resources, and project timeline, (4) TECHNICAL DECISIONS - explanation of technology choices and why they're optimal for this specific task, (5) RISK ASSESSMENT - potential challenges and how to mitigate them, (6) BEST PRACTICES - industry standards and patterns to follow, (7) COMPLETION STRATEGY - recommended order and approach to ensure this task is completed most efficiently. Provide strategic thinking that helps ensure the project can be completed efficiently."
    }}
]

CRITICAL RULES:
- Return ONLY the JSON array, no explanations or text outside JSON
- NEVER include update_task actions when creating a new project
- Break down ALL features/modules/services mentioned into separate tasks
- Create 10-20 tasks that comprehensively cover:
  * Core Infrastructure Layer (Auth, Data Warehouse, Event Bus, Audit, Notifications)
  * All modules/services mentioned (e.g., creator-profile-service, avatar-classification-service, etc.)
  * External API integrations (Meta Graph API, TikTok API, YouTube API, etc.)
  * Database design and schema
  * Backend API design
  * Frontend UI (if applicable)
  * Testing and deployment

PRIORITY ASSIGNMENT (MANDATORY FOR ALL TASKS):
You MUST analyze each task's importance to the project and assign appropriate priority:
- HIGH priority: 
  * Foundation/infrastructure tasks (database design, authentication, core APIs)
  * Tasks that block other tasks (dependencies)
  * Critical user-facing features that are core to the project
  * Security and data integrity tasks
  * Tasks on the critical path to project completion
- MEDIUM priority:
  * Important features that don't block others
  * Supporting functionality and integrations
  * UI/UX improvements
  * Secondary features that enhance the system
- LOW priority:
  * Nice-to-have features
  * Optional enhancements
  * Non-critical optimizations
  * Tasks that can be done later without impacting core functionality
  * Polish and refinement tasks

Think carefully about each task: Is it foundational? Does it block others? Is it critical for the project to function? Assign priority accordingly.
- For each task's "task_description" field, provide COMPREHENSIVE description (4-6 sentences) covering:
  * WHAT the task is - clear explanation
  * HOW to do it - step-by-step methodology
  * WHICH TOOLS to use - specific technologies/frameworks
  * MOST EFFICIENT WAY - best practices and optimizations
- For each task's "reasoning" field, provide DETAILED strategic reasoning (5-7 sentences) covering:
  * WHY it's important and how it contributes to project completion
  * Task breakdown and component analysis
  * Efficiency analysis with dependencies and timeline consideration
  * Technical decisions and rationale
  * Risk assessment and mitigation strategies
  * Best practices and industry standards
  * Completion strategy for maximum efficiency
- Generate tasks with proper reasoning and judgment to ensure project can be completed most efficiently
- Consider task dependencies and optimal ordering for efficient project completion
- {assignment_instruction}
- Set project_id to null for all tasks (they'll be linked to the new project automatically)
- Create a detailed project description that summarizes all features/modules/services mentioned"""
                elif existing_project_mentioned or context.get('project'):
                    # User wants tasks in EXISTING project
                    target_project_id = project_id_to_use or (context.get('project', {}).get('id') if context.get('project') else None)
                    
                    # Check if user wants tasks assigned to all available developers
                    assign_to_all_keywords = ['assign to all', 'assign to all available', 'assign to all developers', 
                                             'assign to all users', 'distribute to all', 'assign tasks to all',
                                             'all available developers', 'all developers', 'all users']
                    wants_assign_to_all = any(keyword in question_lower for keyword in assign_to_all_keywords)
                    
                    assignment_instruction = ""
                    if wants_assign_to_all and available_users:
                        assignment_instruction = f"""
CRITICAL ASSIGNMENT INSTRUCTION:
The user wants tasks assigned to ALL available developers/users. You MUST distribute tasks across ALL available users listed above.
- If there are {len(available_users)} users, create at least {len(available_users)} tasks (one per user minimum)
- Distribute tasks evenly across all users (round-robin style)
- Each task should have a different assignee_id from the available users list
- Use ALL user IDs from the available users list above
- Example: If there are 3 users (IDs: 1, 2, 3) and you create 6 tasks, assign: task1→user1, task2→user2, task3→user3, task4→user1, task5→user2, task6→user3"""
                    elif wants_assign_to_all and not available_users:
                        assignment_instruction = "\nNOTE: User wants tasks assigned to all developers, but no users are available. Leave assignee_id as null."
                    else:
                        assignment_instruction = "\n- Use available user IDs from the list above if assignment is requested, otherwise leave assignee_id as null"
                    
                    prompt = f"""You are an AI assistant that extracts actions from user requests. Analyze the request and return ONLY valid JSON.

{context_str}
{users_str}

User Request: {question}

The user wants to add tasks to an EXISTING project. DO NOT create a new project. DO NOT ask for clarification—return the action(s) as JSON now.
{assignment_instruction}

Extract ONLY create_task actions. Use project_id: {target_project_id} for all tasks.

CRITICAL: If the user asked to add "one task", "1 task", "a task", or "a new task" (with or without a topic), return exactly ONE create_task. Use their topic as task_title (e.g. fix "sementic" to "semantic") and write a concise task_description (2-4 sentences is fine).

Return ONLY this JSON format (no other text):
[
    {{
        "action": "create_task",
        "task_title": "specific task title",
        "task_description": "COMPREHENSIVE task description (4-6 sentences) that includes: (1) WHAT the task is - clear explanation of what needs to be accomplished, (2) HOW to do it - step-by-step approach and methodology, (3) WHICH TOOLS to use - specific technologies, frameworks, libraries, and tools recommended, (4) MOST EFFICIENT WAY - best practices and efficient approaches to complete this task, including any shortcuts or optimizations. Make it actionable and detailed enough that a developer can understand exactly what to build and how to approach it.",
        "project_id": {target_project_id},
        "assignee_id": user_id_or_null,
        "priority": "high|medium|low",
        "status": "todo",
        "reasoning": "DETAILED AI reasoning and judgment (5-7 sentences) that includes: (1) WHY this task is important for the overall project and how it contributes to project completion, (2) TASK BREAKDOWN - logical decomposition of the task into manageable components, (3) EFFICIENCY ANALYSIS - reasoning about the most efficient approach considering dependencies, resources, and project timeline, (4) TECHNICAL DECISIONS - explanation of technology choices and why they're optimal for this specific task, (5) RISK ASSESSMENT - potential challenges and how to mitigate them, (6) BEST PRACTICES - industry standards and patterns to follow, (7) COMPLETION STRATEGY - recommended order and approach to ensure this task is completed most efficiently. Provide strategic thinking that helps ensure the project can be completed efficiently."
    }}
]

Rules:
- Return ONLY the JSON array, no explanations. Never respond with questions or clarification—only valid JSON.
- DO NOT include create_project action
- Use project_id: {target_project_id} for all tasks
- When user asked for ONE task only (e.g. "add only 1 task", "add a task for X"), return exactly one create_task with a short title and concise description.
- When multiple tasks requested: break down into logical tasks (8-15 tasks covering features)
- Create comprehensive tasks that cover: database design, backend API, frontend UI, authentication, core features, testing, deployment
- For each task's "task_description" field, provide COMPREHENSIVE description (4-6 sentences) covering:
  * WHAT the task is - clear explanation
  * HOW to do it - step-by-step methodology
  * WHICH TOOLS to use - specific technologies/frameworks
  * MOST EFFICIENT WAY - best practices and optimizations
- For each task's "reasoning" field, provide DETAILED strategic reasoning (5-7 sentences) covering:
  * WHY it's important and how it contributes to project completion
  * Task breakdown and component analysis
  * Efficiency analysis with dependencies and timeline consideration
  * Technical decisions and rationale
  * Risk assessment and mitigation strategies
  * Best practices and industry standards
  * Completion strategy for maximum efficiency
- Generate tasks with proper reasoning and judgment to ensure project can be completed most efficiently
- Consider task dependencies and optimal ordering for efficient project completion
- {assignment_instruction}
- If specific usernames were mentioned in the request, match them to the available users list by username and use those user IDs"""
                else:
                    # Ambiguous request - analyze more carefully before asking for clarification
                    # Check if there are hints that suggest project creation despite lack of explicit keywords
                    has_system_features = any(word in question_lower for word in [
                        'features', 'modules', 'services', 'system', 'infrastructure', 'api', 'database', 
                        'layer', 'purpose', 'dashboard', 'platform', 'application', 'quantifies', 
                        'aggregates', 'trust ledger', 'centralized', 'key features', 'target users', 
                        'tech angle', 'real-time', 'breakdown visuals'
                    ])
                    has_detailed_description = len(question.split('\n')) > 2 or len(question) > 100
                    has_project_name = any(word[0].isupper() for word in question.split() if len(word) > 2)
                    
                    # Check if it describes what a system IS and what it DOES (strong indicator of new project)
                    is_system_description = (
                        ('is a' in question_lower or 'is an' in question_lower) and
                        (has_system_features or has_detailed_description)
                    )
                    
                    if has_system_features or has_detailed_description or is_system_description:
                        # Likely a project creation request with detailed specs - NEVER treat as deletion
                        prompt = f"""You are an intelligent AI assistant analyzing a user request.

CRITICAL: The user has provided detailed features/modules/services or described a system/platform. 
This STRONGLY indicates they want to CREATE A NEW PROJECT. This is NOT a deletion request. 

CRITICAL: The user has provided detailed features/modules/services. This indicates they want to CREATE A NEW PROJECT.

{context_str}
{users_str}

User Request: {question}

ANALYSIS:
1. User described features/modules/services = WANTS NEW PROJECT
2. Detailed specification indicates a NEW system to be built
3. This is NOT about updating existing tasks
4. This is NOT about adding tasks to existing project (no specific project mentioned)

REQUIRED ACTION: Create a NEW project with tasks covering all mentioned features/modules/services.

{assignment_instruction}

Return ONLY this JSON format (no other text):
[
    {{
        "action": "create_project",
        "project_name": "Descriptive name based on the system described",
        "project_description": "Comprehensive description covering ALL features, modules, services, infrastructure, and external integrations mentioned in the request",
        "project_status": "planning",
        "project_priority": "medium",
        "deadline_days": null,
        "reasoning": "User wants to build a new system with the specified features and modules"
    }},
    {{
        "action": "create_task",
        "task_title": "Task title covering one feature/module/service",
        "task_description": "COMPREHENSIVE task description (4-6 sentences) that includes: (1) WHAT the task is - clear explanation of what needs to be accomplished, (2) HOW to do it - step-by-step approach and methodology, (3) WHICH TOOLS to use - specific technologies, frameworks, libraries, and tools recommended, (4) MOST EFFICIENT WAY - best practices and efficient approaches to complete this task, including any shortcuts or optimizations. Make it actionable and detailed enough that a developer can understand exactly what to build and how to approach it.",
        "project_id": null,
        "assignee_id": user_id_or_null,
        "priority": "high|medium|low",
        "status": "todo",
        "reasoning": "DETAILED AI reasoning and judgment (5-7 sentences) that includes: (1) WHY this task is important for the overall project and how it contributes to project completion, (2) TASK BREAKDOWN - logical decomposition of the task into manageable components, (3) EFFICIENCY ANALYSIS - reasoning about the most efficient approach considering dependencies, resources, and project timeline, (4) TECHNICAL DECISIONS - explanation of technology choices and why they're optimal for this specific task, (5) RISK ASSESSMENT - potential challenges and how to mitigate them, (6) BEST PRACTICES - industry standards and patterns to follow, (7) COMPLETION STRATEGY - recommended order and approach to ensure this task is completed most efficiently."
    }}
]

CRITICAL RULES:
- Return ONLY the JSON array, no explanations
- NEVER include update_task actions - this is a NEW project creation
- Create 10-20 tasks covering ALL features/modules/services mentioned
- Break down each major component into separate tasks

PRIORITY ASSIGNMENT (MANDATORY FOR ALL TASKS):
You MUST analyze each task's importance to the project and assign appropriate priority:
- HIGH priority: 
  * Foundation/infrastructure tasks (database design, authentication, core APIs)
  * Tasks that block other tasks (dependencies)
  * Critical user-facing features that are core to the project
  * Security and data integrity tasks
  * Tasks on the critical path to project completion
- MEDIUM priority:
  * Important features that don't block others
  * Supporting functionality and integrations
  * UI/UX improvements
  * Secondary features that enhance the system
- LOW priority:
  * Nice-to-have features
  * Optional enhancements
  * Non-critical optimizations
  * Tasks that can be done later without impacting core functionality
  * Polish and refinement tasks

Think carefully about each task: Is it foundational? Does it block others? Is it critical for the project to function? Assign priority accordingly.
- For each task's "task_description" field, provide COMPREHENSIVE description (4-6 sentences) covering:
  * WHAT the task is - clear explanation
  * HOW to do it - step-by-step methodology
  * WHICH TOOLS to use - specific technologies/frameworks
  * MOST EFFICIENT WAY - best practices and optimizations
- For each task's "reasoning" field, provide DETAILED strategic reasoning (5-7 sentences) covering:
  * WHY it's important and how it contributes to project completion
  * Task breakdown and component analysis
  * Efficiency analysis with dependencies and timeline consideration
  * Technical decisions and rationale
  * Risk assessment and mitigation strategies
  * Best practices and industry standards
  * Completion strategy for maximum efficiency
- Generate tasks with proper reasoning and judgment to ensure project can be completed most efficiently
- {assignment_instruction}
- Set project_id to null for all tasks (they'll be linked automatically)"""
                    else:
                        # Truly ambiguous - ask for clarification
                        prompt = f"""The user's request is unclear or you cannot determine what they want.

{context_str}
{users_str}

User Request: {question}

I want to help you, but I need clarification on what you'd like me to do:

1. **Do you want to create a NEW project?**
   - If yes, please say: "create a new project called [name]" or "create me a [name] project"
   - You can describe the features/modules you want included

2. **Do you want to add tasks to an EXISTING project?**
   - If yes, please mention the project name, e.g., "add tasks to Project X"
   - Or specify which project you're working with

3. **Do you want to update existing tasks?**
   - If yes, please specify which tasks (by title or ID) and what to change

Once you provide these details, I'll be happy to help!

Do NOT return JSON. Do NOT create anything yet."""
        else:
            # Not an action request - should redirect to QA agent, but for now return message
            prompt = f"""The user's request doesn't appear to be an action request.

{context_str}
{users_str}

User Request: {question}

This seems like a question or information request. The Project Pilot agent only handles action requests (creating projects and tasks).

Please use the Knowledge Q&A agent for questions and information queries.

Return a helpful text response (NOT JSON) explaining this."""
        
        try:
            # Determine if this is a text-only response (not JSON)
            # Deletion requests should return JSON (actions), so they're not text-only
            is_text_response = (
                cannot_do or 
                (is_assignment_request and not is_creation_request) or
                ('clarification' in prompt.lower() or "didn't understand" in prompt.lower() or "please specify" in prompt.lower()) or
                (not is_action_request and not is_deletion_request)
            )
            
            # Use more tokens for action requests (they need to generate JSON with multiple actions)
            # Deletion requests may need many tokens if deleting multiple projects
            max_tokens = 3000 if ((is_action_request or is_deletion_request) and not is_text_response) else (200 if is_text_response else 800)
            response = self._call_llm(prompt, self.system_prompt, temperature=0.7, max_tokens=max_tokens)
            
            # If this is a text-only response, return it directly without parsing JSON
            if is_text_response:
                return {
                    "success": True,
                    "answer": response,
                    "cannot_do": True,
                    "question": question,
                    "actions": None,
                    "action": None
                }
            
            # If it's an action request (including deletion), try to parse the JSON response
            if (is_action_request or is_deletion_request) and not is_text_response:
                try:
                    # Clean response - remove any markdown code blocks
                    cleaned_response = response.strip()
                    
                    # Extract JSON from code blocks if present
                    if "```json" in cleaned_response:
                        json_start = cleaned_response.find("```json") + 7
                        json_end = cleaned_response.find("```", json_start)
                        cleaned_response = cleaned_response[json_start:json_end].strip()
                    elif "```" in cleaned_response:
                        json_start = cleaned_response.find("```") + 3
                        json_end = cleaned_response.find("```", json_start)
                        if json_end > json_start:
                            cleaned_response = cleaned_response[json_start:json_end].strip()
                    
                    # Remove any leading/trailing text that's not JSON
                    first_bracket = min(
                        cleaned_response.find('[') if '[' in cleaned_response else len(cleaned_response),
                        cleaned_response.find('{') if '{' in cleaned_response else len(cleaned_response)
                    )
                    last_bracket = max(
                        cleaned_response.rfind(']') if ']' in cleaned_response else -1,
                        cleaned_response.rfind('}') if '}' in cleaned_response else -1
                    )
                    
                    if first_bracket < len(cleaned_response) and last_bracket > first_bracket:
                        cleaned_response = cleaned_response[first_bracket:last_bracket + 1]
                    
                    action_data = json.loads(cleaned_response)
                    
                    # Handle both single action and array of actions
                    if isinstance(action_data, list):
                        return {
                            "success": True,
                            "answer": response,
                            "actions": action_data,
                            "question": question
                        }
                    else:
                        # Single action (backward compatibility)
                        return {
                            "success": True,
                            "answer": response,
                            "action": action_data,
                            "question": question
                        }
                except json.JSONDecodeError as e:
                    # If JSON parsing fails, try to fix incomplete JSON
                    self.log_action("JSON parsing error", {"error": str(e), "response_length": len(response)})
                    
                    # Try to fix incomplete JSON by adding closing brackets
                    if response.strip().startswith('[') and not response.strip().endswith(']'):
                        try:
                            open_brackets = response.count('[') + response.count('{')
                            close_brackets = response.count(']') + response.count('}')
                            for _ in range(open_brackets - close_brackets):
                                if response.count('[') > response.count(']'):
                                    response += '\n]'
                                elif response.count('{') > response.count('}'):
                                    response += '\n}'
                            
                            action_data = json.loads(response)
                            if isinstance(action_data, list):
                                return {
                                    "success": True,
                                    "answer": "Note: Response was truncated but partial actions were recovered.",
                                    "actions": action_data,
                                    "question": question,
                                    "warning": "Response may have been incomplete"
                                }
                        except:
                            pass
                    
                    return {
                        "success": False,
                        "answer": response,
                        "error": f"Failed to parse JSON response. The response may have been truncated. Try asking again or breaking your request into smaller parts. Error: {str(e)}",
                        "action": None,
                        "actions": None,
                        "question": question
                    }
            else:
                return {
                    "success": True,
                    "answer": response,
                    "question": question
                }
        except Exception as e:
            self.log_action("Error handling action request", {"error": str(e)})
            return {
                "success": False,
                "error": str(e),
                "answer": "I'm sorry, I encountered an error while processing your request. Please try again."
            }
    
    def process(self, question: str, **kwargs) -> Dict:
        """
        Main processing method for Project Pilot agent.

        Args:
            question (str): User's request
            **kwargs: Additional context parameters (context, available_users, chat_history, etc.)

        Returns:
            dict: Actions to perform
        """
        self.log_action("Processing action request", {"question": question[:50]})

        context = kwargs.get('context', {})
        available_users = kwargs.get('available_users', [])
        chat_history = kwargs.get('chat_history') or []
        return self.handle_action_request(question, context, available_users, chat_history=chat_history)


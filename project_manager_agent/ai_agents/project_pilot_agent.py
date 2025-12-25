"""
Project Pilot Agent
Handles all action requests like creating projects, tasks, and managing project operations.
"""

from .base_agent import BaseAgent
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
        self.system_prompt = """You are a Project Pilot Agent for a project management system.
        Your role is to handle action requests like creating and deleting projects and tasks.
        You extract action details from user requests and return structured JSON.
        You should be precise and follow instructions carefully."""
    
    def handle_action_request(self, question: str, context: Optional[Dict] = None, available_users: Optional[List[Dict]] = None) -> Dict:
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
        
        question_lower = question.lower()
        
        # Distinguish between different types of requests
        assignment_keywords = ['assign', 'reassign', 'delegate']
        creation_keywords = ['create', 'add', 'make', 'new task', 'add task', 'new project', 'make project']
        deletion_keywords = ['delete', 'remove', 'destroy', 'drop']
        update_keywords = ['update', 'change', 'modify', 'edit', 'set', 'adjust', 'alter']
        
        is_assignment_request = any(keyword in question_lower for keyword in assignment_keywords)
        is_creation_request = any(keyword in question_lower for keyword in creation_keywords)
        is_deletion_request = any(keyword in question_lower for keyword in deletion_keywords)
        is_update_request = any(keyword in question_lower for keyword in update_keywords)
        is_action_request = is_assignment_request or is_creation_request or is_deletion_request or is_update_request
        
        # Check for things the agent CANNOT do
        cannot_do = None
        cannot_do_item = None
        
        # More robust detection - check for user creation patterns
        action_words = ['create', 'add', 'make', 'new', 'register']
        user_words = ['user', 'users', 'account', 'accounts']
        
        has_action = any(word in question_lower for word in action_words)
        has_user = any(word in question_lower for word in user_words)
        
        # If both action and user words are present, it's likely a user creation request
        if has_action and has_user:
            if any(phrase in question_lower for phrase in [
                'create user', 'create users', 'create new user', 'create new users',
                'add user', 'add users', 'add new user',
                'make user', 'make users', 'make new user',
                'new user', 'new users',
                'register user', 'register users',
                'user1', 'user2', 'user3', 'user4', 'user5'
            ]) or ('create' in question_lower and ('user' in question_lower or 'users' in question_lower)):
                cannot_do = True
                cannot_do_item = 'users or user accounts'
            elif any(phrase in question_lower for phrase in ['create account', 'add account', 'new account', 'register account']):
                cannot_do = True
                cannot_do_item = 'user accounts'
        
        # Check for team member creation
        if 'team member' in question_lower and any(word in question_lower for word in ['create', 'add', 'make']):
            cannot_do = True
            cannot_do_item = 'team members directly'
        
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
            # Handle update requests
            elif is_update_request:
                # Check if it's an update request for tasks or projects
                priority_keywords = ['priority', 'priorities', 'prioritize']
                status_keywords = ['status', 'state']
                task_keywords = ['task', 'tasks']
                project_keywords = ['project', 'projects']
                
                is_priority_update = any(keyword in question_lower for keyword in priority_keywords)
                is_status_update = any(keyword in question_lower for keyword in status_keywords)
                is_task_update = any(keyword in question_lower for keyword in task_keywords)
                is_project_update = any(keyword in question_lower for keyword in project_keywords)
                
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
                # More flexible detection: "create me a [name] project" or "create [name] project" should be detected
                new_project_indicators = ['new project', 'create project', 'make project', 'add project', 'start project',
                                         'create me a', 'create a', 'make a', 'build a', 'start a']
                wants_new_project = any(indicator in question_lower for indicator in new_project_indicators)
                
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
                
                # Check if user mentions existing project by name
                existing_project_mentioned = False
                project_id_to_use = None
                if context.get('all_projects'):
                    for proj in context['all_projects']:
                        proj_name = proj.get('name', '').lower()
                        if proj_name and proj_name in question_lower:
                            existing_project_mentioned = True
                            project_id_to_use = proj.get('id')
                            break
                
                if wants_new_project:
                    # Check if user wants tasks assigned to all available developers
                    assign_to_all_keywords = ['assign to all', 'assign to all available', 'assign to all developers', 
                                             'assign to all users', 'distribute to all', 'assign tasks to all',
                                             'all available developers', 'all developers', 'all users']
                    wants_assign_to_all = any(keyword in question_lower for keyword in assign_to_all_keywords)
                    
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
                    elif wants_assign_to_all and not available_users:
                        assignment_instruction = "\nNOTE: User wants tasks assigned to all developers, but no users are available. Leave assignee_id as null."
                    else:
                        assignment_instruction = "\n- Use available user IDs from the list above if assignment is requested, otherwise leave assignee_id as null"
                    
                    prompt = f"""You are an AI assistant that extracts actions from user requests. Analyze the request and return ONLY valid JSON.

{context_str}
{users_str}

User Request: {question}

The user wants to create a NEW project with tasks.
{assignment_instruction}

Extract the actions and return a JSON ARRAY:
1. First: create_project action
2. Then: 5-10 create_task actions (set project_id to null - will be linked automatically)

Return ONLY this JSON format (no other text):
[
    {{
        "action": "create_project",
        "project_name": "exact project name from request",
        "project_description": "description from request or empty string",
        "project_status": "planning",
        "project_priority": "medium",
        "deadline_days": null,
        "reasoning": "brief explanation"
    }},
    {{
        "action": "create_task",
        "task_title": "specific task title",
        "task_description": "task description",
        "project_id": null,
        "assignee_id": user_id_or_null,
        "priority": "medium",
        "status": "todo",
        "reasoning": "brief explanation"
    }}
]

Rules:
- Return ONLY the JSON array, no explanations
- Break down projects into 5-10 logical tasks (or more if assigning to all users)
- {assignment_instruction}
- Set project_id to null for tasks (they'll be linked to the new project automatically)"""
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

The user wants to add tasks to an EXISTING project. DO NOT create a new project.
{assignment_instruction}

Extract ONLY create_task actions. Use project_id: {target_project_id} for all tasks.

Return ONLY this JSON format (no other text):
[
    {{
        "action": "create_task",
        "task_title": "specific task title",
        "task_description": "task description",
        "project_id": {target_project_id},
        "assignee_id": user_id_or_null,
        "priority": "medium",
        "status": "todo",
        "reasoning": "brief explanation"
    }}
]

Rules:
- Return ONLY the JSON array, no explanations
- DO NOT include create_project action
- Use project_id: {target_project_id} for all tasks
- Break down into logical tasks if multiple tasks requested (or more if assigning to all users)
- {assignment_instruction}"""
                else:
                    # Ambiguous request - ask for clarification instead of guessing
                    prompt = f"""The user's request is unclear or you cannot determine what they want.

{context_str}
{users_str}

User Request: {question}

ANALYSIS:
- User did NOT explicitly say "new project" or "create project"
- User may have mentioned an existing project, but the request is unclear
- The request might be about assigning, updating, or managing existing tasks/projects (which you cannot do)

You should NOT create any projects or tasks. Instead, respond with a clarification message.

Return a helpful text response (NOT JSON) saying:
"I didn't fully understand your request. Could you please clarify:
- Do you want to create a NEW project? (Please explicitly say 'create new project' or 'make new project')
- Do you want to create tasks in an EXISTING project? (Please mention the project name and say 'create tasks')
- Or are you asking about something else?

I can help you:
- Create new projects (when you explicitly ask for a 'new project')
- Create tasks in existing projects
- Update existing tasks (priority, status, assignee, due_date, etc.)
- Delete projects and tasks

Note: I can now update existing tasks including their priorities, statuses, and other fields."

Do NOT return JSON. Do NOT create any projects or tasks."""
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
            **kwargs: Additional context parameters (context, available_users, etc.)
            
        Returns:
            dict: Actions to perform
        """
        self.log_action("Processing action request", {"question": question[:50]})
        
        context = kwargs.get('context', {})
        available_users = kwargs.get('available_users', [])
        return self.handle_action_request(question, context, available_users)


import os
import django
import sys
import json
from pprint import pprint
from datetime import datetime

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from django.contrib.auth import get_user_model
from core.models import Project, Task, TeamMember
from project_manager_agent.ai_agents.agents_registry import AgentRegistry

User = get_user_model()

def get_test_user():
    user_with_projects = User.objects.filter(owned_projects__isnull=False).first()
    if user_with_projects:
        return user_with_projects
    return User.objects.first()

def build_context(user, project_id=None):
    all_projects = Project.objects.filter(owner=user)
    all_tasks = Task.objects.filter(project__owner=user)
    
    if project_id:
        project = Project.objects.get(id=project_id, owner=user)
        tasks = Task.objects.filter(project=project)
        context = {
            'project': {
                'id': project.id,
                'name': project.name,
                'status': project.status,
                'tasks_count': tasks.count()
            },
            'tasks': [{'id': t.id, 'title': t.title, 'status': t.status, 'priority': t.priority} for t in tasks],
            'all_projects': [
                {
                    'id': p.id,
                    'name': p.name,
                    'status': p.status,
                    'priority': p.priority,
                    'tasks_count': p.tasks.count()
                }
                for p in all_projects
            ]
        }
    else:
        context = {
            'all_projects': [
                {
                    'id': p.id,
                    'name': p.name,
                    'status': p.status,
                    'priority': p.priority,
                    'tasks_count': p.tasks.count()
                }
                for p in all_projects
            ],
            'tasks': [{'id': t.id, 'title': t.title, 'status': t.status, 'priority': t.priority, 'project_name': t.project.name} for t in all_tasks]
        }
        
    available_users = []
    users = User.objects.all()[:20]
    for u in users:
        available_users.append({
            'id': u.id,
            'username': u.username,
            'name': u.get_full_name() or u.username
        })
        
    user_assignments = []
    for user_info in available_users:
        user_id = user_info['id']
        user_tasks = all_tasks.filter(assignee_id=user_id)
        tasks_by_project = {}
        for task in user_tasks:
            task_project_id = task.project.id
            if task_project_id not in tasks_by_project:
                tasks_by_project[task_project_id] = {
                    'project_id': task_project_id,
                    'project_name': task.project.name,
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
            'total_tasks': user_tasks.count(),
            'projects': list(tasks_by_project.values())
        })
        
    context['user_assignments'] = user_assignments
    return context, available_users

def main():
    user = get_test_user()
    if not user:
        print("No users found in database.")
        sys.exit(1)
        
    print(f"Testing with User: {user.username} (ID: {user.id})")
    print("-" * 50)
    
    agent = AgentRegistry.get_agent("knowledge_qa")
    context, available_users = build_context(user)
    
    all_projects = Project.objects.filter(owner=user)
    num_projects = all_projects.count()
    project_names = [p.name for p in all_projects]
    
    all_tasks = Task.objects.filter(project__owner=user)
    num_tasks = all_tasks.count()
    todo_tasks = all_tasks.filter(status='todo').count()
    in_progress_tasks = all_tasks.filter(status='in_progress').count()
    completed_projects = all_projects.filter(status='completed').count()
    users_with_tasks = all_tasks.exclude(assignee__isnull=True).values('assignee').distinct().count()
    
    first_project_name = all_projects.first().name if all_projects.exists() else "MissingProject"
    first_task_title = all_tasks.first().title if all_tasks.exists() else "MissingTask"
    
    questions = [
        # Basic counting
        {
            "query": "How many projects do I have in total?",
            "manual_answer": f"{num_projects}",
            "eval_type": "contains"
        },
        {
            "query": "What are the names of my projects?",
            "manual_answer": f"{first_project_name}",
            "eval_type": "contains"
        },
        {
            "query": "How many tasks do I have across all projects?",
            "manual_answer": f"{num_tasks}",
            "eval_type": "contains"
        },
        # Status
        {
            "query": f"What is the status of the project '{first_project_name}'?",
            "manual_answer": f"{all_projects.first().status if all_projects.exists() else 'N/A'}",
            "eval_type": "contains_ignore_case"
        },
        {
            "query": f"Which project does the task '{first_task_title}' belong to?",
            "manual_answer": f"{all_tasks.first().project.name if all_tasks.exists() else 'N/A'}",
            "eval_type": "contains"
        },
        {
            "query": "How many tasks are currently in 'To Do' status?",
            "manual_answer": f"{todo_tasks}",
            "eval_type": "contains"
        },
        {
            "query": "How many tasks are 'In Progress'?",
            "manual_answer": f"{in_progress_tasks}",
            "eval_type": "contains"
        },
        {
            "query": "How many projects are fully 'completed'?",
            "manual_answer": f"{completed_projects}",
            "eval_type": "contains"
        },
        # Guardrails
        {
             "query": "Can you create a new task for me?",
             "manual_answer": "Project Pilot",
             "eval_type": "contains_ignore_case"
        },
        {
             "query": "I want to delete a user from my project. Can you do that?",
             "manual_answer": "cannot create, update, or delete",
             "eval_type": "contains_ignore_case"
        },
        {
             "query": "Make a new project called 'Test Project'",
             "manual_answer": "Project Pilot",
             "eval_type": "contains_ignore_case"
        },
        # Complex User & Team questions
        {
            "query": "How many users have been assigned to at least one task?",
            "manual_answer": f"{users_with_tasks}",
            "eval_type": "contains"
        },
        {
             "query": "List all active users and their roles.",
             "manual_answer": "admin@gmail.com",
             "eval_type": "contains_ignore_case"
        },
        {
             "query": "Are there any users who are not assigned to any tasks?",
             "manual_answer": "No tasks assigned",
             "eval_type": "contains_ignore_case"
        },
        # Ambiguous / Edge cases
        {
             "query": "How many tasks does the project with ID 99999 have?", 
             "manual_answer": "0",
             "eval_type": "manual"
        },
        {
             "query": "Give me the emails of all inactive users.",
             "manual_answer": "", 
             "eval_type": "manual"
        },
        {
             "query": "What are the priority levels of all my tasks?",
             "manual_answer": "high",
             "eval_type": "contains_ignore_case"
        }
    ]
    
    report_lines = []
    report_lines.append("# Knowledge QA Agent Test Report")
    report_lines.append(f"**Generated on:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"**Test User:** {user.username} (ID: {user.id})")
    report_lines.append("---\n")
    
    success_count = 0
    failure_count = 0
    
    for i, q in enumerate(questions, 1):
        question = q["query"]
        expected = str(q["manual_answer"])
        eval_type = q["eval_type"]
        
        print(f"Testing Q{i}/{len(questions)}...")
        
        result = agent.process(question=question, context=context, available_users=available_users)
        
        if result.get("success"):
            answer = result.get("answer", "No answer found.")
        else:
            answer = f"ERROR: {result.get('error')}"
            
        passed = False
        if eval_type == "contains":
            passed = expected in answer
        elif eval_type == "contains_ignore_case":
            passed = expected.lower() in answer.lower()
        else:
            passed = True
            
        status_label = "✅ PASS" if passed else "❌ FAIL"
        if eval_type == "manual":
            status_label = "⚠️ MANUAL EVAL"
            passed = True
            
        if passed and eval_type != "manual":
            success_count += 1
        elif not passed:
            failure_count += 1
            
        report_lines.append(f"### Q{i}: {question}")
        report_lines.append(f"**Status:** {status_label}")
        report_lines.append(f"**Expected / Target string:** `{expected}`")
        report_lines.append(f"**Agent Response:**")
        report_lines.append(f"> {answer.replace(chr(10), chr(10) + '> ')}")
        report_lines.append("\n---\n")
        
    report_lines.insert(4, f"## Summary\n- **Pass:** {success_count}\n- **Fail:** {failure_count}\n- **Manual Eval:** {len([q for q in questions if q['eval_type'] == 'manual'])}\n\n---\n")
    
    with open("qa_agent_test_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        
    print("Testing complete. Report saved to qa_agent_test_report.md")

if __name__ == '__main__':
    main()

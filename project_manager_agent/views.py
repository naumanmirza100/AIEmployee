from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import json
import logging
from datetime import datetime, timedelta

from core.models import Project, Task, Subtask, TeamMember, UserProfile
from .ai_agents import AgentRegistry

logger = logging.getLogger(__name__)


@login_required
def ai_agents_test(request):
    """Main page for testing AI agents - Only accessible to Project Managers"""
    # For admin users, check session role; otherwise check profile role
    if request.user.is_superuser or request.user.is_staff:
        selected_role = request.session.get('selected_role')
        if selected_role != 'project_manager':
            from django.contrib import messages
            messages.error(request, 'Access denied. Please select "Project Manager" role to access this dashboard.')
            return redirect('select_role')
    else:
        # Check if user is a project manager
        try:
            profile = request.user.profile
            if not profile.is_project_manager():
                from django.contrib import messages
                messages.error(request, 'Access denied. This dashboard is only available to Project Managers.')
                return redirect('dashboard')
        except UserProfile.DoesNotExist:
            from django.contrib import messages
            messages.error(request, 'Access denied. Please complete your profile setup.')
            return redirect('dashboard')
    
    projects = Project.objects.filter(owner=request.user)
    tasks = Task.objects.filter(project__owner=request.user)
    return render(request, 'project_manager_template/ai_agents_test.html', {
        'projects': projects,
        'tasks': tasks,
        'agents': AgentRegistry.list_agents()
    })


@login_required
@require_http_methods(["POST"])
def test_task_prioritization(request):
    """Test Task Prioritization Agent"""
    try:
        agent = AgentRegistry.get_agent("task_prioritization")
        data = json.loads(request.body)
        action = data.get('action', 'prioritize')
        
        # Get tasks from database
        project_id = data.get('project_id')
        if project_id:
            tasks_queryset = Task.objects.filter(project_id=project_id, project__owner=request.user)
        else:
            tasks_queryset = Task.objects.filter(project__owner=request.user)
        
        # Convert to dict format
        tasks = []
        for task in tasks_queryset:
            tasks.append({
                'id': task.id,
                'title': task.title,
                'description': task.description,
                'status': task.status,
                'priority': task.priority,
                'due_date': task.due_date.isoformat() if task.due_date else None,
                'assignee_id': task.assignee.id if task.assignee else None,
                'dependencies': list(task.depends_on.values_list('id', flat=True))
            })
        
        # Get team members if needed
        team_members = []
        if action in ['bottlenecks', 'delegation']:
            if project_id:
                members = TeamMember.objects.filter(project_id=project_id)
            else:
                members = TeamMember.objects.filter(project__owner=request.user)
            
            for member in members:
                team_members.append({
                    'id': member.user.id,
                    'name': member.user.username,
                    'role': member.role
                })
        
        # Process with agent
        result = agent.process(
            action=action,
            tasks=tasks,
            team_members=team_members,
            task=data.get('task', {})
        )
        
        # If action is 'prioritize' and we have results, save the priorities to database
        if action == 'prioritize' and result.get('success') and result.get('tasks'):
            updated_count = 0
            for task_data in result['tasks']:
                task_id = task_data.get('id')
                new_priority = task_data.get('ai_priority')  # The recommended priority
                if task_id and new_priority and new_priority in ['low', 'medium', 'high']:
                    try:
                        task = Task.objects.get(id=task_id, project__owner=request.user)
                        task.priority = new_priority
                        task.save()
                        updated_count += 1
                    except Task.DoesNotExist:
                        continue
                    except Exception as e:
                        logger.error(f"Error updating priority for task {task_id}: {str(e)}")
                        continue
            
            if updated_count > 0:
                result['updated_count'] = updated_count
                result['message'] = f'Successfully updated priorities for {updated_count} task(s)'
        
        return JsonResponse(result)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def generate_subtasks(request):
    """Generate subtasks for all tasks in a project"""
    try:
        agent = AgentRegistry.get_agent("subtask_generation")
        data = json.loads(request.body)
        project_id = data.get('project_id')
        
        if not project_id:
            return JsonResponse({
                'success': False,
                'error': 'Project ID is required'
            }, status=400)
        
        # Verify project ownership
        project = get_object_or_404(Project, id=project_id, owner=request.user)
        
        # Get all tasks for the project
        tasks_queryset = Task.objects.filter(project_id=project_id)
        
        # Convert to dict format
        tasks = []
        for task in tasks_queryset:
            tasks.append({
                'id': task.id,
                'title': task.title,
                'description': task.description,
                'status': task.status,
                'priority': task.priority,
                'due_date': task.due_date.isoformat() if task.due_date else None,
            })
        
        if not tasks:
            return JsonResponse({
                'success': False,
                'error': 'No tasks found in this project'
            }, status=400)
        
        # Generate subtasks using agent
        result = agent.process(
            action='generate_for_project',
            tasks=tasks
        )
        
        if not result.get('success'):
            return JsonResponse(result, status=500)
        
        # Save subtasks to database
        subtasks_by_task = result.get('subtasks_by_task', {})
        saved_count = 0
        
        for task_id, subtasks_list in subtasks_by_task.items():
            try:
                task = Task.objects.get(id=task_id, project__owner=request.user)
                
                # Delete existing subtasks for this task (optional - you might want to keep them)
                # Subtask.objects.filter(task=task).delete()
                
                # Create new subtasks
                for subtask_data in subtasks_list:
                    Subtask.objects.create(
                        task=task,
                        title=subtask_data.get('title', 'Untitled Subtask'),
                        description=subtask_data.get('description', ''),
                        order=subtask_data.get('order', 0),
                        status='todo'
                    )
                    saved_count += 1
            except Task.DoesNotExist:
                continue
            except Exception as e:
                logger.error(f"Error saving subtasks for task {task_id}: {str(e)}")
                continue
        
        result['saved_count'] = saved_count
        result['message'] = f'Generated and saved {saved_count} subtasks for {len(subtasks_by_task)} tasks'
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error generating subtasks: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def view_task_subtasks(request, task_id):
    """View all subtasks for a specific task"""
    task = get_object_or_404(Task, id=task_id, project__owner=request.user)
    subtasks = Subtask.objects.filter(task=task).order_by('order', 'created_at')
    
    return render(request, 'tasks/subtasks.html', {
        'task': task,
        'subtasks': subtasks,
        'project': task.project
    })


@login_required
@require_http_methods(["POST"])
def test_knowledge_qa(request):
    """Test Knowledge Q&A Agent"""
    try:
        agent = AgentRegistry.get_agent("knowledge_qa")
        data = json.loads(request.body)
        question = data.get('question', '')
        
        # Always get all user's projects for context
        all_projects = Project.objects.filter(owner=request.user)
        all_tasks = Task.objects.filter(project__owner=request.user)
        
        # Get project context if specific project provided
        project_id = data.get('project_id')
        context = {}
        project = None
        
        if project_id:
            project = get_object_or_404(Project, id=project_id, owner=request.user)
            tasks = Task.objects.filter(project=project)
            context = {
                'project': {
                    'id': project.id,
                    'name': project.name,
                    'status': project.status,
                    'tasks_count': tasks.count()
                },
                'tasks': [{'id': t.id, 'title': t.title, 'status': t.status, 'priority': t.priority, 'description': t.description, 'assignee_id': t.assignee.id if t.assignee else None, 'assignee_username': t.assignee.username if t.assignee else None} for t in tasks],
                # Always include all projects list
                'all_projects': [
                    {
                        'id': p.id,
                        'name': p.name,
                        'status': p.status,
                        'priority': p.priority,
                        'tasks_count': p.tasks.count(),
                        'description': p.description[:100] if p.description else ''
                    }
                    for p in all_projects
                ]
            }
        else:
            # Get all user's projects for context
            context = {
                'all_projects': [
                    {
                        'id': p.id,
                        'name': p.name,
                        'status': p.status,
                        'priority': p.priority,
                        'tasks_count': p.tasks.count(),
                        'description': p.description[:100] if p.description else ''
                    }
                    for p in all_projects
                ],
                'tasks': [{'id': t.id, 'title': t.title, 'status': t.status, 'priority': t.priority, 'description': t.description, 'project_name': t.project.name, 'assignee_id': t.assignee.id if t.assignee else None, 'assignee_username': t.assignee.username if t.assignee else None} for t in all_tasks]
            }
        
        # Get available users (all users in the system, or team members if project specified)
        available_users = []
        if project_id:
            # Get team members for the project
            team_members = TeamMember.objects.filter(project_id=project_id)
            for member in team_members:
                available_users.append({
                    'id': member.user.id,
                    'username': member.user.username,
                    'name': member.user.get_full_name() or member.user.username,
                    'role': member.role
                })
            # Also include project owner
            if project.owner not in [m.user for m in team_members]:
                available_users.append({
                    'id': project.owner.id,
                    'username': project.owner.username,
                    'name': project.owner.get_full_name() or project.owner.username,
                    'role': 'owner'
                })
        else:
            # Get all users (for general queries)
            from django.contrib.auth import get_user_model
            User = get_user_model()
            users = User.objects.all()[:20]  # Limit to 20 users
            for user in users:
                available_users.append({
                    'id': user.id,
                    'username': user.username,
                    'name': user.get_full_name() or user.username
                })
        
        # Build user-task assignments information
        user_assignments = []
        for user_info in available_users:
            user_id = user_info['id']
            # Get tasks for this user - use project-specific tasks if project_id provided, otherwise use all tasks
            if project_id:
                # Use the tasks queryset defined in the if block above
                user_tasks = Task.objects.filter(project_id=project_id, assignee_id=user_id, project__owner=request.user)
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
                'total_tasks': user_tasks.count(),
                'projects': list(tasks_by_project.values())
            })
        
        # Add user assignments to context
        context['user_assignments'] = user_assignments
        
        # Process with agent
        result = agent.process(question=question, context=context, available_users=available_users)
        
        # Check if agent said it cannot do something - don't execute any actions
        if result.get('cannot_do'):
            # Agent cannot perform the requested action - just return the explanation
            return JsonResponse(result)
        
        # Handle multiple actions (e.g., create project + tasks)
        actions = result.get('actions', [])
        if result.get('action'):
            # Single action (backward compatibility)
            actions = [result['action']]
        
        # Only execute actions if we have valid actions and agent didn't say it can't do it
        if actions and not result.get('cannot_do'):
            from datetime import datetime, timedelta
            
            created_project_id = None
            action_results = []
            
            for action_data in actions:
                action_type = action_data.get('action')
                
                # Handle project creation
                if action_type == 'create_project':
                    try:
                        # Calculate end date if deadline is mentioned
                        end_date = None
                        deadline_days = action_data.get('deadline_days')
                        if deadline_days:
                            try:
                                days = int(str(deadline_days).replace('working days', '').replace('days', '').strip())
                                # Calculate working days (excluding weekends)
                                current_date = datetime.now().date()
                                working_days = 0
                                check_date = current_date
                                while working_days < days:
                                    if check_date.weekday() < 5:  # Monday to Friday
                                        working_days += 1
                                    if working_days < days:
                                        check_date += timedelta(days=1)
                                end_date = check_date
                            except (ValueError, TypeError):
                                pass
                        
                        project = Project.objects.create(
                            name=action_data.get('project_name', 'New Project'),
                            description=action_data.get('project_description', ''),
                            owner=request.user,
                            status=action_data.get('project_status', 'planning'),
                            priority=action_data.get('project_priority', 'medium'),
                            end_date=end_date
                        )
                        
                        created_project_id = project.id
                        action_results.append({
                            'action': 'create_project',
                            'success': True,
                            'project_id': project.id,
                            'project_name': project.name,
                            'message': f'Project "{project.name}" created successfully!'
                        })
                        
                        result['answer'] += f"\n\n✅ **Project Created Successfully!**\n- Project: {project.name}\n- Status: {project.get_status_display()}\n- Priority: {project.get_priority_display()}"
                        if end_date:
                            result['answer'] += f"\n- Deadline: {end_date.strftime('%B %d, %Y')}"
                            
                    except Exception as e:
                        action_results.append({
                            'action': 'create_project',
                            'success': False,
                            'error': str(e)
                        })
                
                # Handle task creation
                elif action_type == 'create_task':
                    try:
                        # Get or determine project
                        task_project_id = action_data.get('project_id')
                        
                        # Use newly created project if this task is for it
                        if not task_project_id and created_project_id:
                            task_project_id = created_project_id
                        elif not task_project_id and project_id:
                            task_project_id = project_id
                        elif not task_project_id and context.get('project'):
                            task_project_id = context['project']['id']
                        elif not task_project_id and context.get('all_projects') and len(context.get('all_projects', [])) > 0:
                            # Use first project if multiple
                            task_project_id = context['all_projects'][0]['id']
                        
                        if not task_project_id:
                            action_results.append({
                                'action': 'create_task',
                                'success': False,
                                'error': f"Could not determine which project to create task '{action_data.get('task_title', 'Unknown')}' in."
                            })
                        else:
                            # Verify project ownership
                            task_project = get_object_or_404(Project, id=task_project_id, owner=request.user)
                            
                            # Create the task
                            task = Task.objects.create(
                                title=action_data.get('task_title', 'New Task'),
                                description=action_data.get('task_description', ''),
                                project=task_project,
                                status=action_data.get('status', 'todo'),
                                priority=action_data.get('priority', 'medium'),
                                assignee_id=action_data.get('assignee_id') if action_data.get('assignee_id') else None
                            )
                            
                            action_results.append({
                                'action': 'create_task',
                                'success': True,
                                'task_id': task.id,
                                'task_title': task.title,
                                'project_name': task_project.name,
                                'message': f'Task "{task.title}" created successfully!'
                            })
                            
                            result['answer'] += f"\n\n✅ **Task Created: {task.title}**\n- Project: {task_project.name}\n- Status: {task.get_status_display()}\n- Priority: {task.get_priority_display()}"
                            if task.assignee:
                                result['answer'] += f"\n- Assigned to: {task.assignee.username}"
                    except Exception as e:
                        action_results.append({
                            'action': 'create_task',
                            'success': False,
                            'error': f"Error creating task: {str(e)}"
                        })
                
                elif action_type == 'update_task':
                    try:
                        task_id_to_update = action_data.get('task_id')
                        updates = action_data.get('updates', {})
                        
                        if not task_id_to_update:
                            action_results.append({
                                'action': 'update_task',
                                'success': False,
                                'error': f"Task ID not provided for update."
                            })
                        elif not updates:
                            action_results.append({
                                'action': 'update_task',
                                'success': False,
                                'error': f"No updates specified for task."
                            })
                        else:
                            # Verify task belongs to user's project
                            task_to_update = get_object_or_404(Task, id=task_id_to_update, project__owner=request.user)
                            task_title = task_to_update.title
                            task_project_name = task_to_update.project.name
                            
                            # Track what was updated
                            updated_fields = []
                            
                            # Update priority if specified
                            if 'priority' in updates:
                                new_priority = updates['priority']
                                if new_priority in ['low', 'medium', 'high']:
                                    task_to_update.priority = new_priority
                                    updated_fields.append(f"Priority: {new_priority}")
                            
                            # Update status if specified
                            if 'status' in updates:
                                new_status = updates['status']
                                if new_status in ['todo', 'in_progress', 'review', 'done', 'blocked']:
                                    task_to_update.status = new_status
                                    updated_fields.append(f"Status: {new_status}")
                            
                            # Update assignee if specified
                            if 'assignee_id' in updates:
                                assignee_id = updates['assignee_id']
                                if assignee_id:
                                    # Verify user exists
                                    from django.contrib.auth import get_user_model
                                    User = get_user_model()
                                    try:
                                        assignee = User.objects.get(id=assignee_id)
                                        task_to_update.assignee = assignee
                                        updated_fields.append(f"Assigned to: {assignee.username}")
                                    except User.DoesNotExist:
                                        pass  # Skip invalid assignee
                                else:
                                    task_to_update.assignee = None
                                    updated_fields.append("Unassigned")
                            
                            # Update due_date if specified
                            if 'due_date' in updates and updates['due_date']:
                                try:
                                    from django.utils import timezone
                                    from django.utils.dateparse import parse_date, parse_datetime
                                    from datetime import time as dt_time
                                    
                                    due_date_str = str(updates['due_date']).strip()
                                    if due_date_str:
                                        # Parse date (YYYY-MM-DD format)
                                        if len(due_date_str) == 10 and due_date_str.count('-') == 2:
                                            due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
                                            due_date = due_date.replace(hour=23, minute=59, second=59)
                                            if timezone.is_naive(due_date):
                                                due_date = timezone.make_aware(due_date)
                                            task_to_update.due_date = due_date
                                            updated_fields.append(f"Due date: {due_date_str}")
                                except (ValueError, TypeError):
                                    pass  # Skip invalid date
                            
                            # Update title if specified
                            if 'title' in updates and updates['title']:
                                task_to_update.title = updates['title']
                                updated_fields.append(f"Title: {updates['title']}")
                            
                            # Update description if specified
                            if 'description' in updates and updates['description']:
                                task_to_update.description = updates['description']
                                updated_fields.append("Description updated")
                            
                            # Save the task
                            task_to_update.save()
                            
                            action_results.append({
                                'action': 'update_task',
                                'success': True,
                                'task_id': task_id_to_update,
                                'task_title': task_to_update.title,
                                'project_name': task_project_name,
                                'updated_fields': updated_fields,
                                'message': f'Task "{task_to_update.title}" updated successfully!'
                            })
                            
                            if not result.get('answer'):
                                result['answer'] = ""
                            result['answer'] += f"\n\n✅ **Task Updated: {task_to_update.title}**\n- Project: {task_project_name}\n"
                            for field in updated_fields:
                                result['answer'] += f"- {field}\n"
                            if 'reasoning' in action_data:
                                result['answer'] += f"\n💭 Reasoning: {action_data['reasoning']}\n"
                                
                    except Exception as e:
                        action_results.append({
                            'action': 'update_task',
                            'success': False,
                            'error': f"Error updating task: {str(e)}"
                        })
            
            # Store all action results
            result['action_results'] = action_results
            result['actions'] = actions
        
        return JsonResponse(result)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def test_project_pilot(request):
    """Test Project Pilot Agent"""
    try:
        agent = AgentRegistry.get_agent("project_pilot")
        data = json.loads(request.body)
        question = data.get('question', '')
        
        # Always get all user's projects for context
        all_projects = Project.objects.filter(owner=request.user)
        all_tasks = Task.objects.filter(project__owner=request.user)
        
        # Get project context if specific project provided
        project_id = data.get('project_id')
        context = {}
        project = None
        
        if project_id:
            project = get_object_or_404(Project, id=project_id, owner=request.user)
            tasks = Task.objects.filter(project=project)
            context = {
                'project': {
                    'id': project.id,
                    'name': project.name,
                    'status': project.status,
                    'tasks_count': tasks.count()
                },
                'tasks': [{'id': t.id, 'title': t.title, 'status': t.status, 'priority': t.priority, 'description': t.description, 'assignee_id': t.assignee.id if t.assignee else None, 'assignee_username': t.assignee.username if t.assignee else None} for t in tasks],
                'all_projects': [
                    {
                        'id': p.id,
                        'name': p.name,
                        'status': p.status,
                        'priority': p.priority,
                        'tasks_count': p.tasks.count(),
                        'description': p.description[:100] if p.description else ''
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
                        'tasks_count': p.tasks.count(),
                        'description': p.description[:100] if p.description else ''
                    }
                    for p in all_projects
                ],
                'tasks': [{'id': t.id, 'title': t.title, 'status': t.status, 'priority': t.priority, 'description': t.description, 'project_name': t.project.name} for t in all_tasks[:10]]
            }
        
        # Get available users
        available_users = []
        if project_id:
            team_members = TeamMember.objects.filter(project_id=project_id)
            for member in team_members:
                available_users.append({
                    'id': member.user.id,
                    'username': member.user.username,
                    'name': member.user.get_full_name() or member.user.username,
                    'role': member.role
                })
            if project.owner not in [m.user for m in team_members]:
                available_users.append({
                    'id': project.owner.id,
                    'username': project.owner.username,
                    'name': project.owner.get_full_name() or project.owner.username,
                    'role': 'owner'
                })
        else:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            users = User.objects.all()[:20]
            for user in users:
                available_users.append({
                    'id': user.id,
                    'username': user.username,
                    'name': user.get_full_name() or user.username
                })
        
        # Build user-task assignments information (for Project Pilot agent context)
        user_assignments = []
        for user_info in available_users:
            user_id = user_info['id']
            # Get tasks for this user
            if project_id:
                user_tasks = Task.objects.filter(project_id=project_id, assignee_id=user_id, project__owner=request.user)
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
                'total_tasks': user_tasks.count(),
                'projects': list(tasks_by_project.values())
            })
        
        # Add user assignments to context
        context['user_assignments'] = user_assignments
        
        # Process with agent
        result = agent.process(question=question, context=context, available_users=available_users)
        
        if result.get('cannot_do'):
            return JsonResponse(result)
        
        # Handle multiple actions
        actions = result.get('actions', [])
        if result.get('action'):
            actions = [result['action']]
        
        if actions and not result.get('cannot_do'):
            from datetime import datetime, timedelta
            
            created_project_id = None
            action_results = []
            
            for action_data in actions:
                action_type = action_data.get('action')
                
                if action_type == 'create_project':
                    try:
                        end_date = None
                        deadline_days = action_data.get('deadline_days')
                        if deadline_days:
                            try:
                                days = int(str(deadline_days).replace('working days', '').replace('days', '').strip())
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
                                pass
                        
                        project = Project.objects.create(
                            name=action_data.get('project_name', 'New Project'),
                            description=action_data.get('project_description', ''),
                            owner=request.user,
                            status=action_data.get('project_status', 'planning'),
                            priority=action_data.get('project_priority', 'medium'),
                            end_date=end_date
                        )
                        
                        created_project_id = project.id
                        action_results.append({
                            'action': 'create_project',
                            'success': True,
                            'project_id': project.id,
                            'project_name': project.name,
                            'message': f'Project "{project.name}" created successfully!'
                        })
                        
                        result['answer'] += f"\n\n✅ **Project Created Successfully!**\n- Project: {project.name}\n- Status: {project.get_status_display()}\n- Priority: {project.get_priority_display()}"
                        if end_date:
                            result['answer'] += f"\n- Deadline: {end_date.strftime('%B %d, %Y')}"
                    except Exception as e:
                        action_results.append({
                            'action': 'create_project',
                            'success': False,
                            'error': str(e)
                        })
                
                elif action_type == 'create_task':
                    try:
                        task_project_id = action_data.get('project_id')
                        
                        if not task_project_id and created_project_id:
                            task_project_id = created_project_id
                        elif not task_project_id and project_id:
                            task_project_id = project_id
                        elif not task_project_id and context.get('project'):
                            task_project_id = context['project']['id']
                        elif not task_project_id and context.get('all_projects') and len(context.get('all_projects', [])) > 0:
                            task_project_id = context['all_projects'][0]['id']
                        
                        if not task_project_id:
                            action_results.append({
                                'action': 'create_task',
                                'success': False,
                                'error': f"Could not determine which project to create task '{action_data.get('task_title', 'Unknown')}' in."
                            })
                        else:
                            task_project = get_object_or_404(Project, id=task_project_id, owner=request.user)
                            
                            # Parse estimated_hours
                            estimated_hours = None
                            if 'estimated_hours' in action_data and action_data['estimated_hours'] is not None:
                                try:
                                    estimated_hours = float(action_data['estimated_hours'])
                                except (ValueError, TypeError):
                                    estimated_hours = None
                            
                            # Parse due_date
                            due_date = None
                            if 'due_date' in action_data and action_data['due_date']:
                                try:
                                    from django.utils import timezone
                                    from django.utils.dateparse import parse_date, parse_datetime
                                    from datetime import time as dt_time
                                    
                                    # Handle both date strings (YYYY-MM-DD) and datetime strings
                                    due_date_str = str(action_data['due_date']).strip()
                                    if due_date_str:
                                        # If it's just a date (YYYY-MM-DD), parse it and set to end of day
                                        if len(due_date_str) == 10 and due_date_str.count('-') == 2:
                                            # YYYY-MM-DD format
                                            due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
                                            # Set to end of day (23:59:59)
                                            due_date = due_date.replace(hour=23, minute=59, second=59)
                                            # Make timezone-aware
                                            if timezone.is_naive(due_date):
                                                due_date = timezone.make_aware(due_date)
                                        else:
                                            # Try parsing as full datetime first
                                            due_date = parse_datetime(due_date_str)
                                            if not due_date:
                                                # Try parsing as date only
                                                date_only = parse_date(due_date_str)
                                                if date_only:
                                                    due_date = datetime.combine(date_only, dt_time(23, 59, 59))
                                                    # Make timezone-aware
                                                    if timezone.is_naive(due_date):
                                                        due_date = timezone.make_aware(due_date)
                                except (ValueError, TypeError) as e:
                                    # If parsing fails, leave as None
                                    due_date = None
                            
                            task = Task.objects.create(
                                title=action_data.get('task_title', 'New Task'),
                                description=action_data.get('task_description', ''),
                                project=task_project,
                                status=action_data.get('status', 'todo'),
                                priority=action_data.get('priority', 'medium'),
                                assignee_id=action_data.get('assignee_id') if action_data.get('assignee_id') else None,
                                estimated_hours=estimated_hours,
                                due_date=due_date
                            )
                            
                            action_results.append({
                                'action': 'create_task',
                                'success': True,
                                'task_id': task.id,
                                'task_title': task.title,
                                'project_name': task_project.name,
                                'message': f'Task "{task.title}" created successfully!'
                            })
                            
                            result['answer'] += f"\n\n✅ **Task Created: {task.title}**\n- Project: {task_project.name}\n- Status: {task.get_status_display()}\n- Priority: {task.get_priority_display()}"
                            if task.estimated_hours:
                                result['answer'] += f"\n- Estimated Hours: {task.estimated_hours}"
                            if task.due_date:
                                result['answer'] += f"\n- Due Date: {task.due_date.strftime('%B %d, %Y')}"
                            if task.assignee:
                                result['answer'] += f"\n- Assigned to: {task.assignee.username}"
                    except Exception as e:
                        action_results.append({
                            'action': 'create_task',
                            'success': False,
                            'error': f"Error creating task: {str(e)}"
                        })
                
                elif action_type == 'delete_project':
                    try:
                        project_id_to_delete = action_data.get('project_id')
                        if not project_id_to_delete:
                            action_results.append({
                                'action': 'delete_project',
                                'success': False,
                                'error': f"Project ID not provided for deletion."
                            })
                        else:
                            # Verify project ownership and delete
                            project_to_delete = get_object_or_404(Project, id=project_id_to_delete, owner=request.user)
                            project_name = project_to_delete.name
                            project_to_delete.delete()
                            
                            action_results.append({
                                'action': 'delete_project',
                                'success': True,
                                'project_id': project_id_to_delete,
                                'project_name': project_name,
                                'message': f'Project "{project_name}" deleted successfully!'
                            })
                            
                            if not result.get('answer'):
                                result['answer'] = ""
                            result['answer'] += f"\n\n✅ **Project Deleted: {project_name}**"
                    except Exception as e:
                        action_results.append({
                            'action': 'delete_project',
                            'success': False,
                            'error': f"Error deleting project: {str(e)}"
                        })
                
                elif action_type == 'delete_task':
                    try:
                        task_id_to_delete = action_data.get('task_id')
                        if not task_id_to_delete:
                            action_results.append({
                                'action': 'delete_task',
                                'success': False,
                                'error': f"Task ID not provided for deletion."
                            })
                        else:
                            # Verify task belongs to user's project and delete
                            task_to_delete = get_object_or_404(Task, id=task_id_to_delete, project__owner=request.user)
                            task_title = task_to_delete.title
                            task_project_name = task_to_delete.project.name
                            task_to_delete.delete()
                            
                            action_results.append({
                                'action': 'delete_task',
                                'success': True,
                                'task_id': task_id_to_delete,
                                'task_title': task_title,
                                'project_name': task_project_name,
                                'message': f'Task "{task_title}" deleted successfully!'
                            })
                            
                            if not result.get('answer'):
                                result['answer'] = ""
                            result['answer'] += f"\n\n✅ **Task Deleted: {task_title}** (from project: {task_project_name})"
                    except Exception as e:
                        action_results.append({
                            'action': 'delete_task',
                            'success': False,
                            'error': f"Error deleting task: {str(e)}"
                        })
                
                elif action_type == 'update_task':
                    try:
                        task_id_to_update = action_data.get('task_id')
                        updates = action_data.get('updates', {})
                        
                        if not task_id_to_update:
                            action_results.append({
                                'action': 'update_task',
                                'success': False,
                                'error': f"Task ID not provided for update."
                            })
                        elif not updates:
                            action_results.append({
                                'action': 'update_task',
                                'success': False,
                                'error': f"No updates specified for task."
                            })
                        else:
                            # Verify task belongs to user's project
                            task_to_update = get_object_or_404(Task, id=task_id_to_update, project__owner=request.user)
                            task_title = task_to_update.title
                            task_project_name = task_to_update.project.name
                            
                            # Track what was updated
                            updated_fields = []
                            
                            # Update priority if specified
                            if 'priority' in updates:
                                new_priority = updates['priority']
                                if new_priority in ['low', 'medium', 'high']:
                                    task_to_update.priority = new_priority
                                    updated_fields.append(f"Priority: {new_priority}")
                            
                            # Update status if specified
                            if 'status' in updates:
                                new_status = updates['status']
                                if new_status in ['todo', 'in_progress', 'review', 'done', 'blocked']:
                                    task_to_update.status = new_status
                                    updated_fields.append(f"Status: {new_status}")
                            
                            # Update assignee if specified
                            if 'assignee_id' in updates:
                                assignee_id = updates['assignee_id']
                                if assignee_id:
                                    # Verify user exists
                                    from django.contrib.auth import get_user_model
                                    User = get_user_model()
                                    try:
                                        assignee = User.objects.get(id=assignee_id)
                                        task_to_update.assignee = assignee
                                        updated_fields.append(f"Assigned to: {assignee.username}")
                                    except User.DoesNotExist:
                                        pass  # Skip invalid assignee
                                else:
                                    task_to_update.assignee = None
                                    updated_fields.append("Unassigned")
                            
                            # Update due_date if specified
                            if 'due_date' in updates and updates['due_date']:
                                try:
                                    from django.utils import timezone
                                    from django.utils.dateparse import parse_date, parse_datetime
                                    from datetime import time as dt_time
                                    
                                    due_date_str = str(updates['due_date']).strip()
                                    if due_date_str:
                                        # Parse date (YYYY-MM-DD format)
                                        if len(due_date_str) == 10 and due_date_str.count('-') == 2:
                                            due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
                                            due_date = due_date.replace(hour=23, minute=59, second=59)
                                            if timezone.is_naive(due_date):
                                                due_date = timezone.make_aware(due_date)
                                            task_to_update.due_date = due_date
                                            updated_fields.append(f"Due date: {due_date_str}")
                                except (ValueError, TypeError):
                                    pass  # Skip invalid date
                            
                            # Update title if specified
                            if 'title' in updates and updates['title']:
                                task_to_update.title = updates['title']
                                updated_fields.append(f"Title: {updates['title']}")
                            
                            # Update description if specified
                            if 'description' in updates and updates['description']:
                                task_to_update.description = updates['description']
                                updated_fields.append("Description updated")
                            
                            # Save the task
                            task_to_update.save()
                            
                            action_results.append({
                                'action': 'update_task',
                                'success': True,
                                'task_id': task_id_to_update,
                                'task_title': task_to_update.title,
                                'project_name': task_project_name,
                                'updated_fields': updated_fields,
                                'message': f'Task "{task_to_update.title}" updated successfully!'
                            })
                            
                            if not result.get('answer'):
                                result['answer'] = ""
                            result['answer'] += f"\n\n✅ **Task Updated: {task_to_update.title}**\n- Project: {task_project_name}\n"
                            for field in updated_fields:
                                result['answer'] += f"- {field}\n"
                            if 'reasoning' in action_data:
                                result['answer'] += f"\n💭 Reasoning: {action_data['reasoning']}\n"
                                
                    except Exception as e:
                        action_results.append({
                            'action': 'update_task',
                            'success': False,
                            'error': f"Error updating task: {str(e)}"
                        })
            
            result['action_results'] = action_results
            result['actions'] = actions
        
        return JsonResponse(result)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def test_timeline_gantt(request):
    """Test Timeline/Gantt Agent"""
    try:
        agent = AgentRegistry.get_agent("timeline_gantt")
        data = json.loads(request.body)
        action = data.get('action', 'create_timeline')
        project_id = data.get('project_id')
        
        if not project_id:
            return JsonResponse({
                'success': False,
                'error': 'project_id is required'
            }, status=400)
        
        # Verify project belongs to user
        project = get_object_or_404(Project, id=project_id, owner=request.user)
        
        # Get tasks for the project
        tasks_queryset = Task.objects.filter(project=project).select_related('assignee').prefetch_related('depends_on')
        
        # Convert tasks to dict format
        tasks = []
        for task in tasks_queryset:
            tasks.append({
                'id': task.id,
                'title': task.title,
                'description': task.description,
                'status': task.status,
                'priority': task.priority,
                'due_date': task.due_date.isoformat() if task.due_date else None,
                'assignee_id': task.assignee.id if task.assignee else None,
                'estimated_hours': float(task.estimated_hours) if task.estimated_hours else None,
                'actual_hours': float(task.actual_hours) if task.actual_hours else None,
                'dependencies': list(task.depends_on.values_list('id', flat=True)),
                'created_at': task.created_at.isoformat() if task.created_at else None
            })
        
        # Prepare kwargs based on action
        kwargs = {
            'project_id': project_id,
            'tasks': tasks
        }
        
        # Add action-specific parameters
        if action == 'check_deadlines':
            kwargs['days_ahead'] = data.get('days_ahead', 7)
        elif action == 'suggest_adjustments':
            kwargs['current_progress'] = data.get('current_progress', {})
        elif action == 'calculate_duration':
            kwargs['tasks'] = tasks
        elif action == 'manage_phases':
            kwargs['phases'] = data.get('phases')
        
        # Process with agent
        result = agent.process(action=action, **kwargs)
        
        return JsonResponse(result)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

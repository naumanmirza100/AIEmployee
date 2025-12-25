from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
import json

from .models import Project, Task, TeamMember, UserProfile
from .forms import ProjectForm, TaskForm, CustomUserCreationForm


def signup(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            raw_password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=raw_password)
            login(request, user)
            messages.success(request, f'Account created successfully! Welcome, {username}!')
            return redirect('dashboard')
    else:
        form = CustomUserCreationForm()
    return render(request, 'signup.html', {'form': form})

@login_required
def select_role(request):
    """Role selection page for admin users"""
    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, 'Access denied. Role selection is only available for admin users.')
        return redirect('dashboard')
    
    # Ensure user has a profile
    UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        selected_role = request.POST.get('role')
        if selected_role in ['project_manager', 'recruitment_agent', 'marketing_agent']:
            # Store selected role in session
            request.session['selected_role'] = selected_role
            if selected_role == 'recruitment_agent':
                messages.success(request, f'Switched to Recruitment Agent dashboard')
                return redirect('recruitment_dashboard')
            elif selected_role == 'marketing_agent':
                messages.success(request, f'Switched to Marketing Agent dashboard')
                return redirect('marketing_dashboard')
            else:
                messages.success(request, f'Switched to Project Manager dashboard')
                return redirect('dashboard')
        else:
            messages.error(request, 'Invalid role selected.')
    
    return render(request, 'select_role.html', {
        'roles': UserProfile.ROLE_CHOICES,
        'current_role': request.session.get('selected_role', None)
    })


@login_required
def dashboard(request):
    # Ensure user has a profile
    UserProfile.objects.get_or_create(user=request.user)
    
    # Check if user is a recruitment agent and redirect them
    if request.user.profile.is_recruitment_agent() and not (request.user.is_superuser or request.user.is_staff):
        return redirect('recruitment_dashboard')
    
    # Check if user is a marketing agent and redirect them
    if request.user.profile.is_marketing_agent() and not (request.user.is_superuser or request.user.is_staff):
        return redirect('marketing_dashboard')
    
    # For admin users, use session role; otherwise use profile role
    if request.user.is_superuser or request.user.is_staff:
        selected_role = request.session.get('selected_role')
        if not selected_role:
            # Redirect to role selection if no role is selected
            return redirect('select_role')
        # If admin selected recruitment_agent role, redirect to recruitment dashboard
        if selected_role == 'recruitment_agent':
            return redirect('recruitment_dashboard')
        # If admin selected marketing_agent role, redirect to marketing dashboard
        if selected_role == 'marketing_agent':
            return redirect('marketing_dashboard')
    else:
        selected_role = None
    
    projects = Project.objects.filter(owner=request.user)
    tasks = Task.objects.filter(project__owner=request.user)
    return render(request, 'dashboard.html', {
        'projects': projects,
        'tasks': tasks,
        'selected_role': selected_role
    })


# Project Management Views
@login_required
def project_list(request):
    """List all projects for the current user"""
    projects = Project.objects.filter(owner=request.user)
    return render(request, 'projects/list.html', {
        'projects': projects
    })


@login_required
def project_create(request):
    """Create a new project"""
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.owner = request.user
            project.save()
            messages.success(request, f'Project "{project.name}" created successfully!')
            return redirect('project_detail', project_id=project.id)
    else:
        form = ProjectForm()
    
    return render(request, 'projects/create.html', {
        'form': form
    })


@login_required
def project_detail(request, project_id):
    """View project details"""
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    tasks = Task.objects.filter(project=project)
    team_members = TeamMember.objects.filter(project=project)
    
    return render(request, 'projects/detail.html', {
        'project': project,
        'tasks': tasks,
        'team_members': team_members
    })


@login_required
def project_edit(request, project_id):
    """Edit an existing project"""
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    
    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            messages.success(request, f'Project "{project.name}" updated successfully!')
            return redirect('project_detail', project_id=project.id)
    else:
        form = ProjectForm(instance=project)
    
    return render(request, 'projects/edit.html', {
        'form': form,
        'project': project
    })


@login_required
def project_delete(request, project_id):
    """Delete a project"""
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    
    if request.method == 'POST':
        project_name = project.name
        project.delete()
        messages.success(request, f'Project "{project_name}" deleted successfully!')
        return redirect('project_list')
    
    return render(request, 'projects/delete.html', {
        'project': project
    })


# Task Management Views
@login_required
def task_create(request, project_id=None):
    """Create a new task"""
    project = None
    if project_id:
        project = get_object_or_404(Project, id=project_id, owner=request.user)
    
    if request.method == 'POST':
        form = TaskForm(request.POST, user=request.user)
        if form.is_valid():
            task = form.save()
            messages.success(request, f'Task "{task.title}" created successfully!')
            if project:
                return redirect('project_detail', project_id=project.id)
            return redirect('dashboard')
    else:
        form = TaskForm(user=request.user)
        if project:
            form.fields['project'].initial = project
    
    return render(request, 'tasks/create.html', {
        'form': form,
        'project': project
    })


@login_required
def task_edit(request, task_id):
    """Edit an existing task"""
    task = get_object_or_404(Task, id=task_id, project__owner=request.user)
    
    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f'Task "{task.title}" updated successfully!')
            return redirect('project_detail', project_id=task.project.id)
    else:
        form = TaskForm(instance=task, user=request.user)
    
    return render(request, 'tasks/edit.html', {
        'form': form,
        'task': task
    })

def user_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                # If user is admin, redirect to role selection
                if user.is_superuser or user.is_staff:
                    return redirect('select_role')
                return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'login.html', {'form': form})


def user_logout(request):
    """Custom logout view that accepts GET requests"""
    # Clear selected role from session
    if 'selected_role' in request.session:
        del request.session['selected_role']
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')


# AI Agent views have been moved to project_manager_agent app

@login_required
def my_tasks(request):
    """View for users to see their assigned tasks"""
    from django.utils import timezone
    from project_manager_agent.ai_agents import AgentRegistry
    from datetime import timedelta
    
    # Get all tasks assigned to the current user
    tasks = Task.objects.filter(assignee=request.user).select_related('project').prefetch_related('subtasks', 'depends_on').order_by('-priority', 'due_date')
    
    # Calculate progress for each task
    now = timezone.now()
    tasks_with_progress = []
    for task in tasks:
        # Use manual progress if set, otherwise calculate progress
        if task.progress_percentage is not None:
            progress = task.progress_percentage
        else:
            # Calculate progress automatically
            progress = 0
            if task.status == 'done':
                progress = 100
            elif task.status == 'in_progress':
                subtasks = task.subtasks.all()
                if subtasks.exists():
                    completed_subtasks = subtasks.filter(status='done').count()
                    total_subtasks = subtasks.count()
                    subtask_progress = (completed_subtasks / total_subtasks * 100) if total_subtasks > 0 else 0
                    if task.estimated_hours and task.actual_hours:
                        time_progress = min(90, (task.actual_hours / task.estimated_hours) * 100)
                        progress = (subtask_progress * 0.6) + (time_progress * 0.4)
                    else:
                        progress = subtask_progress * 0.8
                    progress = max(10, min(90, int(progress)))
                elif task.estimated_hours and task.actual_hours:
                    progress = max(10, min(90, int((task.actual_hours / task.estimated_hours) * 100)))
                else:
                    progress = 50
            elif task.status == 'review':
                progress = 90
            elif task.status == 'blocked':
                progress = 0
            else:
                progress = 0
        
        # Calculate days until due / overdue
        days_info = None
        if task.due_date:
            delta = task.due_date - now
            days_info = {
                'days': delta.days,
                'is_overdue': delta.days < 0,
                'is_due_soon': 0 <= delta.days <= 3
            }
        
        tasks_with_progress.append({
            'task': task,
            'progress': progress,
            'manual_progress': task.progress_percentage is not None,  # Flag to indicate if progress is manually set
            'days_info': days_info,
            'subtasks_count': task.subtasks.count(),
            'completed_subtasks_count': task.subtasks.filter(status='done').count(),
        })
    
    # Get AI suggestions for task prioritization
    ai_suggestions = None
    try:
        if tasks.exists():
            # Prepare task data for AI
            task_data = []
            for task in tasks:
                task_data.append({
                    'id': task.id,
                    'title': task.title,
                    'description': task.description[:200] if task.description else '',
                    'status': task.status,
                    'priority': task.priority,
                    'due_date': task.due_date.isoformat() if task.due_date else None,
                    'estimated_hours': float(task.estimated_hours) if task.estimated_hours else None,
                    'dependencies': [dep.id for dep in task.depends_on.all()],
                })
            
            # Get AI agent for prioritization
            agent = AgentRegistry.get_agent("task_prioritization")
            result = agent.process(
                action='prioritize',
                tasks=task_data,
                team_members=[],
                task={}
            )
            
            if result.get('success') and result.get('tasks'):
                # Extract AI recommendations
                suggestions = []
                for task_rec in result['tasks'][:10]:  # Top 10 suggestions
                    task_id = task_rec.get('id')
                    task_data_item = next((t for t in tasks_with_progress if t['task'].id == task_id), None)
                    if task_data_item:
                        task_obj = task_data_item['task']
                        suggestions.append({
                            'task_id': task_id,
                            'task_title': task_obj.title,
                            'recommended_priority': task_rec.get('ai_priority', task_rec.get('priority')),
                            'reasoning': task_rec.get('reasoning', ''),
                            'recommended_order': task_rec.get('recommended_order'),
                        })
                
                ai_suggestions = {
                    'suggestions': suggestions,
                    'summary': result.get('summary', '')
                }
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting AI suggestions: {str(e)}")
        ai_suggestions = None
    
    # Group tasks by status
    tasks_by_status = {
        'todo': [t for t in tasks_with_progress if t['task'].status == 'todo'],
        'in_progress': [t for t in tasks_with_progress if t['task'].status == 'in_progress'],
        'review': [t for t in tasks_with_progress if t['task'].status == 'review'],
        'done': [t for t in tasks_with_progress if t['task'].status == 'done'],
        'blocked': [t for t in tasks_with_progress if t['task'].status == 'blocked'],
    }
    
    # Statistics
    stats = {
        'total': len(tasks_with_progress),
        'todo': len(tasks_by_status['todo']),
        'in_progress': len(tasks_by_status['in_progress']),
        'review': len(tasks_by_status['review']),
        'done': len(tasks_by_status['done']),
        'blocked': len(tasks_by_status['blocked']),
        'overdue': sum(1 for t in tasks_with_progress if t['days_info'] and t['days_info']['is_overdue']),
        'due_soon': sum(1 for t in tasks_with_progress if t['days_info'] and t['days_info']['is_due_soon']),
    }
    
    return render(request, 'tasks/my_tasks.html', {
        'tasks': tasks_with_progress,
        'tasks_by_status': tasks_by_status,
        'stats': stats,
        'ai_suggestions': ai_suggestions,
    })


@login_required
@require_http_methods(["POST"])
def update_task_status(request, task_id):
    """Update task status and/or progress"""
    from django.utils import timezone
    
    task = get_object_or_404(Task, id=task_id, assignee=request.user)
    
    data = json.loads(request.body)
    new_status = data.get('status')
    progress = data.get('progress')  # Optional progress percentage (0-100)
    
    # Ensure at least one field is being updated
    if new_status is None and progress is None:
        return JsonResponse({
            'success': False,
            'error': 'Either status or progress must be provided'
        }, status=400)
    
    # Update status if provided
    if new_status and new_status in dict(Task.STATUS_CHOICES).keys():
        task.status = new_status
        
        # If marking as done, set completed_at and progress to 100
        if new_status == 'done':
            task.completed_at = timezone.now()
            task.progress_percentage = 100
        elif task.completed_at and new_status != 'done':
            task.completed_at = None
    
    # Update progress percentage if provided
    if progress is not None:
        try:
            progress_value = int(progress)
            if 0 <= progress_value <= 100:
                task.progress_percentage = progress_value
                # If progress is 100, also mark as done
                if progress_value == 100 and task.status != 'done':
                    task.status = 'done'
                    task.completed_at = timezone.now()
                # If progress is less than 100 and status is done, change status to in_progress
                elif progress_value < 100 and task.status == 'done':
                    task.status = 'in_progress'
                    task.completed_at = None
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Progress must be between 0 and 100'
                }, status=400)
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid progress value'
            }, status=400)
    
    task.save()
    
    message = 'Task updated successfully'
    if new_status:
        message = f'Task status updated to {task.get_status_display()}'
    if progress is not None:
        message = f'Task progress updated to {task.progress_percentage}%'
    if new_status and progress is not None:
        message = f'Task updated: status = {task.get_status_display()}, progress = {task.progress_percentage}%'
    
    return JsonResponse({
        'success': True,
        'message': message,
        'task': {
            'id': task.id,
            'status': task.status,
            'status_display': task.get_status_display(),
            'progress_percentage': task.progress_percentage,
        }
    })
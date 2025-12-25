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

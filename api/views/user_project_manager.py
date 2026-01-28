"""
User Project Manager API Views
For users with project_manager role to manage projects and tasks
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import models
from datetime import datetime
import logging

from core.models import Project, Task, UserProfile, Company

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_project_manager_projects_tasks(request):
    """
    Get all tasks from projects where the project manager has at least one task assigned
    GET /api/user/project-manager/projects-tasks
    """
    try:
        user = request.user
        
        # Check if user is a project manager
        if not hasattr(user, 'profile') or user.profile.role != 'project_manager':
            return Response({
                'status': 'error',
                'message': 'Access denied. Project manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get all projects where this user has at least one task assigned OR is the project manager/owner
        projects_with_tasks = Project.objects.filter(
            models.Q(tasks__assignee=user) | models.Q(project_manager=user) | models.Q(owner=user)
        ).distinct()
        
        projects_data = []
        for project in projects_with_tasks:
            # Get ALL tasks for this project (not just user's tasks)
            all_project_tasks = Task.objects.filter(project=project).select_related('assignee', 'project')
            
            tasks_data = []
            for task in all_project_tasks:
                tasks_data.append({
                    'id': task.id,
                    'title': task.title,
                    'description': task.description,
                    'status': task.status,
                    'priority': task.priority,
                    'due_date': task.due_date.isoformat() if task.due_date else None,
                    'progress_percentage': task.progress_percentage,
                    'assignee_id': task.assignee.id if task.assignee else None,
                    'assignee_name': task.assignee.get_full_name() if task.assignee and (task.assignee.first_name or task.assignee.last_name) else (task.assignee.username if task.assignee else None),
                    'assignee_email': task.assignee.email if task.assignee else None,
                    'created_at': task.created_at.isoformat() if task.created_at else None,
                })
            
            projects_data.append({
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'status': project.status,
                'priority': project.priority,
                'tasks': tasks_data,
                'tasks_count': len(tasks_data),
            })
        
        return Response({
            'status': 'success',
            'data': projects_data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.exception(f"Error in get_project_manager_projects_tasks: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to fetch projects and tasks',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_project_manager_project(request):
    """
    Create a new project for a project manager
    POST /api/user/project-manager/projects
    """
    try:
        user = request.user
        
        # Check if user is a project manager
        if not hasattr(user, 'profile') or user.profile.role != 'project_manager':
            return Response({
                'status': 'error',
                'message': 'Access denied. Project manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get user's company from profile
        user_profile = user.profile
        company = user_profile.company
        
        if not company:
            return Response({
                'status': 'error',
                'message': 'User is not associated with a company'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get project data
        name = request.data.get('name', '').strip()
        if not name:
            return Response({
                'status': 'error',
                'message': 'Project name is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        description = request.data.get('description', '').strip()
        status_val = request.data.get('status', 'planning')
        priority_val = request.data.get('priority', 'medium')
        project_type = request.data.get('project_type', 'web_app')
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
                'message': f'Invalid project type. Must be one of: {", ".join(valid_project_types)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse dates
        deadline_date = None
        if deadline:
            try:
                deadline_date = datetime.strptime(deadline, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    'status': 'error',
                    'message': 'Invalid deadline format. Use YYYY-MM-DD'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        start_date_obj = None
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    'status': 'error',
                    'message': 'Invalid start_date format. Use YYYY-MM-DD'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        end_date_obj = None
        if end_date:
            try:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    'status': 'error',
                    'message': 'Invalid end_date format. Use YYYY-MM-DD'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create project
        project = Project.objects.create(
            name=name,
            description=description,
            owner=user,
            project_manager=user,
            company=company,
            status=status_val,
            priority=priority_val,
            project_type=project_type,
            deadline=deadline_date,
            start_date=start_date_obj,
            end_date=end_date_obj,
        )
        
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
                'deadline': project.deadline.isoformat() if project.deadline else None,
                'start_date': project.start_date.isoformat() if project.start_date else None,
                'end_date': project.end_date.isoformat() if project.end_date else None,
            }
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        logger.exception(f"Error in create_project_manager_project: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to create project',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_project_manager_task(request):
    """
    Create a new task in a project (for project managers)
    POST /api/user/project-manager/tasks
    """
    try:
        user = request.user
        
        # Check if user is a project manager
        if not hasattr(user, 'profile') or user.profile.role != 'project_manager':
            return Response({
                'status': 'error',
                'message': 'Access denied. Project manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get task data
        project_id = request.data.get('project_id')
        if not project_id:
            return Response({
                'status': 'error',
                'message': 'project_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verify project exists and user has access (user must have at least one task in this project)
        project = get_object_or_404(Project, id=project_id)
        
        # Check if user has access to this project (has at least one task assigned)
        user_has_access = Task.objects.filter(project=project, assignee=user).exists()
        if not user_has_access and project.project_manager != user and project.owner != user:
            return Response({
                'status': 'error',
                'message': 'Access denied. You must have at least one task in this project.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        title = request.data.get('title', '').strip()
        if not title:
            return Response({
                'status': 'error',
                'message': 'Task title is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
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
        
        # Handle assignee - must be from the same company
        assignee = None
        if assignee_id:
            try:
                assignee_user = User.objects.get(id=assignee_id)
                # Get user's company
                user_company = None
                if hasattr(user, 'profile') and user.profile.company:
                    user_company = user.profile.company
                
                # Verify assignee is from the same company
                assignee_company = None
                if hasattr(assignee_user, 'profile') and assignee_user.profile.company:
                    assignee_company = assignee_user.profile.company
                
                # Check if both users are from the same company (or both have no company)
                if user_company and assignee_company and user_company == assignee_company:
                    assignee = assignee_user
                elif not user_company and not assignee_company:
                    # Both have no company - allow assignment
                    assignee = assignee_user
                else:
                    return Response({
                        'status': 'error',
                        'message': 'Assignee must be from the same company'
                    }, status=status.HTTP_400_BAD_REQUEST)
            except User.DoesNotExist:
                return Response({
                    'status': 'error',
                    'message': 'Invalid assignee_id'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse due date
        due_date = None
        if due_date_str:
            try:
                # Try ISO format first
                if 'T' in due_date_str:
                    due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
                else:
                    due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
                    due_date = timezone.make_aware(due_date)
            except ValueError:
                return Response({
                    'status': 'error',
                    'message': 'Invalid due_date format. Use YYYY-MM-DD or ISO format'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create task
        task = Task.objects.create(
            title=title,
            description=description,
            project=project,
            assignee=assignee,
            status=status_val,
            priority=priority_val,
            due_date=due_date,
            estimated_hours=estimated_hours,
        )
        
        return Response({
            'status': 'success',
            'message': 'Task created successfully',
            'data': {
                'id': task.id,
                'title': task.title,
                'description': task.description,
                'status': task.status,
                'priority': task.priority,
                'assignee_id': task.assignee.id if task.assignee else None,
                'assignee_name': task.assignee.get_full_name() if task.assignee and (task.assignee.first_name or task.assignee.last_name) else (task.assignee.username if task.assignee else None),
                'due_date': task.due_date.isoformat() if task.due_date else None,
            }
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        logger.exception(f"Error in create_project_manager_task: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to create task',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_company_users_for_pm(request):
    """
    Get list of users from the same company (for project manager to assign tasks)
    GET /api/user/project-manager/company-users
    """
    try:
        user = request.user
        
        # Check if user is a project manager
        if not hasattr(user, 'profile') or user.profile.role != 'project_manager':
            return Response({
                'status': 'error',
                'message': 'Access denied. Project manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get user's company
        user_profile = user.profile
        company = user_profile.company
        
        if not company:
            return Response({
                'status': 'error',
                'message': 'User is not associated with a company'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get all users from the same company
        company_user_profiles = UserProfile.objects.filter(company=company).select_related('user')
        
        users_data = []
        for profile in company_user_profiles:
            users_data.append({
                'id': profile.user.id,
                'email': profile.user.email,
                'username': profile.user.username,
                'full_name': profile.user.get_full_name() or profile.user.username,
                'role': profile.role,
            })
        
        return Response({
            'status': 'success',
            'data': users_data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.exception(f"Error in get_company_users_for_pm: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to fetch company users',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_project_manager_projects(request):
    """
    Get all projects where the project manager has at least one task assigned
    GET /api/user/project-manager/projects
    """
    try:
        user = request.user
        
        # Check if user is a project manager
        if not hasattr(user, 'profile') or user.profile.role != 'project_manager':
            return Response({
                'status': 'error',
                'message': 'Access denied. Project manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get all projects where this user has at least one task assigned OR is the project manager/owner
        projects = Project.objects.filter(
            models.Q(tasks__assignee=user) | models.Q(project_manager=user) | models.Q(owner=user)
        ).distinct().order_by('-created_at')
        
        projects_data = []
        for project in projects:
            projects_data.append({
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'status': project.status,
                'priority': project.priority,
                'project_type': project.project_type,
                'tasks_count': project.tasks.count(),
            })
        
        return Response({
            'status': 'success',
            'data': projects_data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.exception(f"Error in get_project_manager_projects: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to fetch projects',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_project_manager_project(request, project_id):
    """
    Update a project (for project managers)
    PUT/PATCH /api/user/project-manager/projects/{project_id}/update
    """
    try:
        user = request.user
        
        # Check if user is a project manager
        if not hasattr(user, 'profile') or user.profile.role != 'project_manager':
            return Response({
                'status': 'error',
                'message': 'Access denied. Project manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get project and verify user has access (is project manager, owner, or has tasks in it)
        project = get_object_or_404(Project, id=project_id)
        
        # Check if user has access
        user_has_access = (
            project.project_manager == user or 
            project.owner == user or 
            Task.objects.filter(project=project, assignee=user).exists()
        )
        
        if not user_has_access:
            return Response({
                'status': 'error',
                'message': 'Access denied. You do not have permission to update this project.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        data = request.data.copy()
        
        # Update allowed fields
        if 'name' in data:
            project.name = data['name']
        if 'description' in data:
            project.description = data.get('description', '')
        if 'status' in data:
            # Validate status
            valid_statuses = [choice[0] for choice in Project.STATUS_CHOICES]
            if data['status'] in valid_statuses:
                project.status = data['status']
        if 'priority' in data:
            # Validate priority
            valid_priorities = [choice[0] for choice in Project.PRIORITY_CHOICES]
            if data['priority'] in valid_priorities:
                project.priority = data['priority']
        if 'project_type' in data:
            # Validate project_type
            valid_types = [choice[0] for choice in Project.PROJECT_TYPE_CHOICES]
            if data['project_type'] in valid_types:
                project.project_type = data['project_type']
        if 'deadline' in data:
            deadline_str = data.get('deadline')
            if deadline_str:
                try:
                    project.deadline = datetime.strptime(deadline_str, '%Y-%m-%d').date()
                except ValueError:
                    return Response({
                        'status': 'error',
                        'message': 'Invalid deadline format. Use YYYY-MM-DD'
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                project.deadline = None
        if 'start_date' in data:
            start_date_str = data.get('start_date')
            if start_date_str:
                try:
                    project.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                except ValueError:
                    return Response({
                        'status': 'error',
                        'message': 'Invalid start_date format. Use YYYY-MM-DD'
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                project.start_date = None
        if 'end_date' in data:
            end_date_str = data.get('end_date')
            if end_date_str:
                try:
                    project.end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                except ValueError:
                    return Response({
                        'status': 'error',
                        'message': 'Invalid end_date format. Use YYYY-MM-DD'
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                project.end_date = None
        
        project.save()
        
        return Response({
            'status': 'success',
            'message': 'Project updated successfully',
            'data': {
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'status': project.status,
                'priority': project.priority,
                'project_type': project.project_type,
                'deadline': project.deadline.isoformat() if project.deadline else None,
                'start_date': project.start_date.isoformat() if project.start_date else None,
                'end_date': project.end_date.isoformat() if project.end_date else None,
            }
        }, status=status.HTTP_200_OK)
    
    except Project.DoesNotExist:
        return Response({
            'status': 'error',
            'message': 'Project not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Error updating project: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to update project',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_project_manager_task(request, task_id):
    """
    Update a task (for project managers)
    PUT/PATCH /api/user/project-manager/tasks/{task_id}/update
    """
    try:
        user = request.user
        
        # Check if user is a project manager
        if not hasattr(user, 'profile') or user.profile.role != 'project_manager':
            return Response({
                'status': 'error',
                'message': 'Access denied. Project manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get task and verify it belongs to a project the user has access to
        task = get_object_or_404(Task, id=task_id)
        project = task.project
        
        # Get user's company
        user_company = None
        if hasattr(user, 'profile') and user.profile.company:
            user_company = user.profile.company
        
        # Check if user has access to this project
        # Project managers can edit tasks in projects they manage or own, OR if they're in the same company
        user_has_access = (
            project.project_manager == user or 
            project.owner == user or 
            Task.objects.filter(project=project, assignee=user).exists() or
            (user_company and project.company == user_company)
        )
        
        if not user_has_access:
            return Response({
                'status': 'error',
                'message': 'Access denied. You do not have permission to update this task.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        data = request.data.copy()
        
        # Update allowed fields
        if 'title' in data:
            task.title = data['title']
        if 'description' in data:
            task.description = data.get('description', '')
        if 'priority' in data:
            # Validate priority
            valid_priorities = [choice[0] for choice in Task.PRIORITY_CHOICES]
            if data['priority'] in valid_priorities:
                task.priority = data['priority']
        if 'status' in data:
            # Validate status
            valid_statuses = [choice[0] for choice in Task.STATUS_CHOICES]
            if data['status'] in valid_statuses:
                task.status = data['status']
        if 'assignee_id' in data:
            # Update assignee - must be from the same company
            assignee_id = data.get('assignee_id')
            # Handle string 'none', empty string, or None
            if assignee_id in [None, '', 'none', 'null']:
                task.assignee = None
            else:
                try:
                    # Convert to int if it's a string
                    if isinstance(assignee_id, str):
                        assignee_id = int(assignee_id)
                    
                    assignee_user = User.objects.get(id=assignee_id)
                    
                    # If the assignee is not changing, allow it (task already exists with this assignee)
                    if task.assignee and task.assignee.id == assignee_id:
                        # Keep the current assignee - no validation needed
                        task.assignee = assignee_user
                    else:
                        # New assignee - verify they are from the same company
                        assignee_company = None
                        if hasattr(assignee_user, 'profile') and assignee_user.profile.company:
                            assignee_company = assignee_user.profile.company
                        
                        # Check if both users are from the same company (or both have no company)
                        if user_company and assignee_company and user_company == assignee_company:
                            task.assignee = assignee_user
                        elif not user_company and not assignee_company:
                            # Both have no company - allow assignment
                            task.assignee = assignee_user
                        else:
                            return Response({
                                'status': 'error',
                                'message': 'Invalid assignee. User must be from the same company.'
                            }, status=status.HTTP_400_BAD_REQUEST)
                except (User.DoesNotExist, ValueError, TypeError) as e:
                    logger.error(f"Error validating assignee_id {assignee_id}: {str(e)}")
                    return Response({
                        'status': 'error',
                        'message': f'Invalid assignee_id: {assignee_id}'
                    }, status=status.HTTP_400_BAD_REQUEST)
        if 'due_date' in data:
            due_date_str = data.get('due_date')
            if due_date_str:
                try:
                    if 'T' in due_date_str:
                        task.due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
                    else:
                        due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
                        task.due_date = timezone.make_aware(due_date)
                except ValueError:
                    return Response({
                        'status': 'error',
                        'message': 'Invalid due_date format. Use YYYY-MM-DD or ISO format'
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                task.due_date = None
        
        task.save()
        
        return Response({
            'status': 'success',
            'message': 'Task updated successfully',
            'data': {
                'id': task.id,
                'title': task.title,
                'description': task.description,
                'priority': task.priority,
                'status': task.status,
                'assignee_id': task.assignee.id if task.assignee else None,
                'assignee_name': task.assignee.get_full_name() if task.assignee and (task.assignee.first_name or task.assignee.last_name) else (task.assignee.username if task.assignee else None),
                'assignee_email': task.assignee.email if task.assignee else None,
                'due_date': task.due_date.isoformat() if task.due_date else None,
            }
        }, status=status.HTTP_200_OK)
    
    except Task.DoesNotExist:
        return Response({
            'status': 'error',
            'message': 'Task not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Error updating task: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Failed to update task',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


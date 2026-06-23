"""
Unified Context Manager
Centralized context service for all agents to share project context efficiently.
"""

from typing import Dict, List, Optional
from django.core.cache import cache
from django.utils import timezone
from django.db import models
from core.models import Project, Task, UserProfile
from datetime import datetime, timedelta
import json
import logging

logger = logging.getLogger(__name__)


class ContextManager:
    """
    Centralized context manager for project data.
    Provides cached, versioned context for all agents.
    """
    
    CACHE_TIMEOUT = 300  # 5 minutes
    CACHE_PREFIX = "pm_context_"
    
    @staticmethod
    def get_project_context(project_id: int, include_tasks: bool = True, 
                          include_team: bool = True, include_dependencies: bool = True) -> Dict:
        """
        Get comprehensive project context with caching.
        
        Args:
            project_id (int): Project ID
            include_tasks (bool): Include task details
            include_team (bool): Include team member info
            include_dependencies (bool): Include dependency graphs
            
        Returns:
            Dict: Comprehensive project context
        """
        cache_key = f"{ContextManager.CACHE_PREFIX}project_{project_id}_{include_tasks}_{include_team}_{include_dependencies}"
        
        # Try cache first
        cached_context = cache.get(cache_key)
        if cached_context:
            logger.debug(f"Cache hit for project context: {project_id}")
            return cached_context
        
        try:
            project = Project.objects.select_related(
                'owner', 'project_manager', 'company', 'industry'
            ).prefetch_related('tasks', 'team_members').get(id=project_id)
        except Project.DoesNotExist:
            return {'error': f'Project {project_id} not found'}
        
        context = {
            'project': {
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'status': project.status,
                'priority': project.priority,
                'project_type': project.project_type,
                'start_date': project.start_date.isoformat() if project.start_date else None,
                'deadline': project.effective_deadline.isoformat() if project.effective_deadline else None,
                'owner_id': project.owner.id,
                'owner_username': project.owner.username,
                'created_at': project.created_at.isoformat(),
                'updated_at': project.updated_at.isoformat(),
            },
            'generated_at': timezone.now().isoformat(),
            'version': 1
        }
        
        if include_tasks:
            tasks = Task.objects.filter(project=project).select_related(
                'assignee', 'project'
            ).prefetch_related('depends_on', 'dependent_tasks', 'subtasks')
            
            context['tasks'] = []
            for task in tasks:
                task_data = {
                    'id': task.id,
                    'title': task.title,
                    'description': task.description,
                    'status': task.status,
                    'priority': task.priority,
                    'due_date': task.due_date.isoformat() if task.due_date else None,
                    'estimated_hours': float(task.estimated_hours) if task.estimated_hours else None,
                    'actual_hours': float(task.actual_hours) if task.actual_hours else None,
                    'progress_percentage': task.progress_percentage,
                    'assignee_id': task.assignee.id if task.assignee else None,
                    'assignee_username': task.assignee.username if task.assignee else None,
                    'created_at': task.created_at.isoformat(),
                    'updated_at': task.updated_at.isoformat(),
                }
                
                if include_dependencies:
                    task_data['dependencies'] = [dep.id for dep in task.depends_on.all()]
                    task_data['dependent_tasks'] = [dep.id for dep in task.dependent_tasks.all()]
                    task_data['dependency_count'] = task.depends_on.count()
                    task_data['dependent_count'] = task.dependent_tasks.count()
                
                context['tasks'].append(task_data)
            
            # Task statistics
            context['task_stats'] = {
                'total': len(context['tasks']),
                'by_status': {
                    status: sum(1 for t in context['tasks'] if t['status'] == status)
                    for status in ['todo', 'in_progress', 'review', 'done', 'blocked']
                },
                'by_priority': {
                    priority: sum(1 for t in context['tasks'] if t['priority'] == priority)
                    for priority in ['low', 'medium', 'high']
                },
                'completed': sum(1 for t in context['tasks'] if t['status'] == 'done'),
                'completion_rate': round(
                    (sum(1 for t in context['tasks'] if t['status'] == 'done') / len(context['tasks']) * 100)
                    if context['tasks'] else 0, 2
                )
            }
        
        if include_team:
            team_members = project.team_members.select_related('user').all()
            context['team'] = []
            for member in team_members:
                context['team'].append({
                    'user_id': member.user.id,
                    'username': member.user.username,
                    'role': member.role,
                    'name': member.user.get_full_name() or member.user.username,
                })
            
            # Add owner if not in team
            owner_in_team = any(m['user_id'] == project.owner.id for m in context['team'])
            if not owner_in_team:
                context['team'].append({
                    'user_id': project.owner.id,
                    'username': project.owner.username,
                    'role': 'owner',
                    'name': project.owner.get_full_name() or project.owner.username,
                })
        
        # Cache the context
        cache.set(cache_key, context, ContextManager.CACHE_TIMEOUT)
        
        return context
    
    @staticmethod
    def get_user_projects_context(user_id: int, limit: int = 50) -> Dict:
        """
        Get context for all projects owned/managed by a user.
        
        Args:
            user_id (int): User ID
            limit (int): Maximum number of projects to include
            
        Returns:
            Dict: Context with all user projects
        """
        cache_key = f"{ContextManager.CACHE_PREFIX}user_projects_{user_id}_{limit}"
        
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        projects = Project.objects.filter(
            models.Q(owner_id=user_id) | models.Q(project_manager_id=user_id)
        ).select_related('owner', 'project_manager')[:limit]
        
        all_projects = []
        for project in projects:
            all_projects.append({
                'id': project.id,
                'name': project.name,
                'description': project.description[:200] if project.description else '',
                'status': project.status,
                'priority': project.priority,
                'project_type': project.project_type,
                'tasks_count': project.tasks.count(),
                'created_at': project.created_at.isoformat(),
            })
        
        context = {
            'user_id': user_id,
            'projects': all_projects,
            'total_projects': len(all_projects),
            'generated_at': timezone.now().isoformat(),
        }
        
        cache.set(cache_key, context, ContextManager.CACHE_TIMEOUT)
        return context
    
    @staticmethod
    def invalidate_project_context(project_id: int):
        """
        Invalidate cached context for a project.
        
        Args:
            project_id (int): Project ID
        """
        # Invalidate all variations
        patterns = [
            f"{ContextManager.CACHE_PREFIX}project_{project_id}_*",
            f"{ContextManager.CACHE_PREFIX}user_projects_*",
        ]
        
        # Note: Django cache doesn't support pattern deletion easily
        # In production, use Redis with pattern deletion
        logger.info(f"Context invalidated for project {project_id}")
    
    @staticmethod
    def build_dependency_graph(tasks: List[Dict]) -> Dict:
        """
        Build dependency graph from tasks.
        
        Args:
            tasks (List[Dict]): List of tasks with dependencies
            
        Returns:
            Dict: Dependency graph structure
        """
        graph = {
            'nodes': [],
            'edges': [],
            'critical_path': [],
            'cycles': [],
        }
        
        task_map = {task['id']: task for task in tasks}
        
        # Build nodes
        for task in tasks:
            graph['nodes'].append({
                'id': task['id'],
                'title': task.get('title', ''),
                'status': task.get('status', 'todo'),
                'priority': task.get('priority', 'medium'),
            })
            
            # Build edges (dependencies)
            dependencies = task.get('dependencies', [])
            for dep_id in dependencies:
                if dep_id in task_map:
                    graph['edges'].append({
                        'from': dep_id,
                        'to': task['id'],
                        'type': 'dependency'
                    })
        
        # Detect cycles
        visited = set()
        rec_stack = set()
        
        def has_cycle(node_id, path):
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)
            
            # Check dependencies
            task = task_map.get(node_id)
            if task:
                deps = task.get('dependencies', [])
                for dep_id in deps:
                    if dep_id not in visited:
                        if has_cycle(dep_id, path.copy()):
                            return True
                    elif dep_id in rec_stack:
                        # Cycle detected
                        cycle_start = path.index(dep_id)
                        graph['cycles'].append(path[cycle_start:] + [dep_id])
                        return True
            
            rec_stack.remove(node_id)
            return False
        
        for task_id in task_map.keys():
            if task_id not in visited:
                has_cycle(task_id, [])
        
        return graph


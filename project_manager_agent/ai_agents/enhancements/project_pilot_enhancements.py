"""
Project Pilot Agent Enhancements
Implements advanced features: Similar project detection, validation, smart assignment
"""

from typing import Dict, List, Optional, Tuple
from django.db.models import Q
from core.models import Project, Task, User
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ProjectPilotEnhancements:
    """Enhancement methods for Project Pilot Agent"""
    
    @staticmethod
    def analyze_similar_projects(project_description: str, user_id: int, limit: int = 3) -> List[Dict]:
        """
        Find similar projects to use as templates.
        Uses keyword matching and project type similarity.
        
        Args:
            project_description (str): Description of new project
            user_id (int): User ID to filter projects
            limit (int): Maximum number of similar projects to return
            
        Returns:
            List[Dict]: Similar projects with their task structures
        """
        try:
            # Get user's projects
            user_projects = Project.objects.filter(
                Q(owner_id=user_id) | Q(project_manager_id=user_id)
            ).select_related('owner', 'project_manager').prefetch_related('tasks')
            
            if not user_projects.exists():
                return []
            
            # Extract keywords from description
            desc_lower = project_description.lower()
            keywords = set(desc_lower.split())
            
            # Score projects by similarity
            scored_projects = []
            for project in user_projects:
                score = 0
                
                # Match project type
                project_text = f"{project.name} {project.description}".lower()
                project_keywords = set(project_text.split())
                
                # Keyword overlap
                common_keywords = keywords.intersection(project_keywords)
                score += len(common_keywords) * 2
                
                # Project type match
                if project.project_type:
                    if any(pt in desc_lower for pt in [project.project_type]):
                        score += 5
                
                # Description length similarity (similar complexity)
                desc_len_diff = abs(len(project.description) - len(project_description))
                if desc_len_diff < 100:
                    score += 2
                
                if score > 0:
                    # Get task structure
                    tasks = project.tasks.all()[:20]  # Limit to 20 tasks
                    task_structure = []
                    for task in tasks:
                        task_structure.append({
                            'title': task.title,
                            'description': task.description[:100] if task.description else '',
                            'priority': task.priority,
                            'status': task.status,
                        })
                    
                    scored_projects.append({
                        'project': {
                            'id': project.id,
                            'name': project.name,
                            'description': project.description[:200],
                            'project_type': project.project_type,
                            'status': project.status,
                        },
                        'tasks': task_structure,
                        'task_count': project.tasks.count(),
                        'similarity_score': score
                    })
            
            # Sort by score and return top matches
            scored_projects.sort(key=lambda x: x['similarity_score'], reverse=True)
            return scored_projects[:limit]
            
        except Exception as e:
            logger.error(f"Error analyzing similar projects: {e}")
            return []
    
    @staticmethod
    def build_dependency_graph(tasks: List[Dict]) -> Dict:
        """
        Build dependency graph to understand task relationships.
        
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
            
            # Build edges
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
            
            task = task_map.get(node_id)
            if task:
                deps = task.get('dependencies', [])
                for dep_id in deps:
                    if dep_id not in visited:
                        if has_cycle(dep_id, path.copy()):
                            return True
                    elif dep_id in rec_stack:
                        cycle_start = path.index(dep_id)
                        graph['cycles'].append(path[cycle_start:] + [dep_id])
                        return True
            
            rec_stack.remove(node_id)
            return False
        
        for task_id in task_map.keys():
            if task_id not in visited:
                has_cycle(task_id, [])
        
        return graph
    
    @staticmethod
    def validate_task_creation(task_data: Dict, project: Project) -> Tuple[bool, List[str]]:
        """
        Validate task before creation.
        
        Args:
            task_data (Dict): Task data to validate
            project (Project): Project to create task in
            
        Returns:
            Tuple[bool, List[str]]: (is_valid, list_of_errors)
        """
        errors = []
        
        # Check required fields
        if not task_data.get('title'):
            errors.append("Task title is required")
        
        # Check for duplicates
        title = task_data.get('title', '').strip()
        if title:
            existing = Task.objects.filter(
                project=project,
                title__iexact=title
            ).exists()
            if existing:
                errors.append(f"Task with title '{title}' already exists in this project")
        
        # Validate dates
        due_date = task_data.get('due_date')
        if due_date:
            try:
                if isinstance(due_date, str):
                    due_date = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                
                # Check if due date is in the past
                if due_date < datetime.now():
                    errors.append("Due date cannot be in the past")
                
                # Check if due date is before project start
                if project.start_date and due_date.date() < project.start_date:
                    errors.append("Task due date cannot be before project start date")
                
                # Check if due date is after project deadline
                _proj_deadline = project.effective_deadline
                if _proj_deadline and due_date.date() > _proj_deadline:
                    errors.append("Task due date cannot be after project deadline")
                    
            except (ValueError, TypeError) as e:
                errors.append(f"Invalid due date format: {str(e)}")
        
        # Validate dependencies
        dependencies = task_data.get('dependencies', [])
        if dependencies:
            valid_dep_ids = set(
                Task.objects.filter(project=project).values_list('id', flat=True)
            )
            invalid_deps = [dep_id for dep_id in dependencies if dep_id not in valid_dep_ids]
            if invalid_deps:
                errors.append(f"Invalid dependency IDs: {invalid_deps}")
            
            # Check for circular dependencies (basic check)
            task_id = task_data.get('id')
            if task_id:
                # This is an update, check if adding this dependency creates a cycle
                for dep_id in dependencies:
                    if dep_id == task_id:
                        errors.append("Task cannot depend on itself")
        
        # Validate assignee
        assignee_id = task_data.get('assignee_id')
        if assignee_id:
            try:
                assignee = User.objects.get(id=assignee_id)
                # Check if assignee is in project team
                is_team_member = (
                    project.team_members.filter(user=assignee).exists() or
                    project.owner_id == assignee_id or
                    project.project_manager_id == assignee_id
                )
                if not is_team_member:
                    errors.append(f"User {assignee.username} is not a member of this project")
            except User.DoesNotExist:
                errors.append(f"Assignee with ID {assignee_id} does not exist")
        
        # Validate priority
        priority = task_data.get('priority', 'medium')
        if priority not in ['low', 'medium', 'high']:
            errors.append(f"Invalid priority: {priority}. Must be 'low', 'medium', or 'high'")
        
        # Validate status
        status = task_data.get('status', 'todo')
        if status not in ['todo', 'in_progress', 'review', 'done', 'blocked']:
            errors.append(f"Invalid status: {status}")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def optimize_assignments(tasks: List[Dict], users: List[Dict]) -> Dict:
        """
        Optimize task assignments based on workload and skills.
        
        Args:
            tasks (List[Dict]): Tasks to assign
            users (List[Dict]): Available users
            
        Returns:
            Dict: Optimization suggestions
        """
        if not users:
            return {'suggestions': [], 'workload_analysis': {}}
        
        # Calculate current workload per user
        workload = {}
        for user in users:
            user_id = user.get('id')
            if user_id:
                # Count active tasks
                active_tasks = Task.objects.filter(
                    assignee_id=user_id,
                    status__in=['todo', 'in_progress', 'review']
                ).count()
                
                workload[user_id] = {
                    'user': user,
                    'active_tasks': active_tasks,
                    'total_hours': 0,
                }
        
        # Calculate estimated hours per user
        for task in tasks:
            assignee_id = task.get('assignee_id')
            if assignee_id and assignee_id in workload:
                hours = task.get('estimated_hours', 0) or 0
                workload[assignee_id]['total_hours'] += hours
        
        # Find average workload
        if workload:
            avg_tasks = sum(w['active_tasks'] for w in workload.values()) / len(workload)
            avg_hours = sum(w['total_hours'] for w in workload.values()) / len(workload)
        else:
            avg_tasks = 0
            avg_hours = 0
        
        # Identify overloaded and underutilized users
        overloaded = []
        underutilized = []
        suggestions = []
        
        for user_id, data in workload.items():
            user = data['user']
            tasks_count = data['active_tasks']
            hours = data['total_hours']
            
            if tasks_count > avg_tasks * 1.5 or hours > avg_hours * 1.5:
                overloaded.append({
                    'user_id': user_id,
                    'username': user.get('username', 'Unknown'),
                    'active_tasks': tasks_count,
                    'total_hours': hours,
                    'recommendation': 'Consider redistributing some tasks'
                })
            elif tasks_count < avg_tasks * 0.5 and hours < avg_hours * 0.5:
                underutilized.append({
                    'user_id': user_id,
                    'username': user.get('username', 'Unknown'),
                    'active_tasks': tasks_count,
                    'total_hours': hours,
                    'recommendation': 'Can take on more tasks'
                })
        
        # Generate assignment suggestions for unassigned tasks
        unassigned_tasks = [t for t in tasks if not t.get('assignee_id')]
        if unassigned_tasks and underutilized:
            # Suggest assigning to underutilized users
            for task in unassigned_tasks[:len(underutilized)]:
                user = underutilized[0]  # Start with first underutilized user
                suggestions.append({
                    'task_id': task.get('id'),
                    'task_title': task.get('title', ''),
                    'suggested_assignee_id': user['user_id'],
                    'suggested_assignee': user['username'],
                    'reason': f"User has low workload ({user['active_tasks']} tasks)"
                })
        
        return {
            'suggestions': suggestions,
            'workload_analysis': {
                'overloaded': overloaded,
                'underutilized': underutilized,
                'average_tasks': round(avg_tasks, 2),
                'average_hours': round(avg_hours, 2),
            },
            'workload_by_user': workload
        }


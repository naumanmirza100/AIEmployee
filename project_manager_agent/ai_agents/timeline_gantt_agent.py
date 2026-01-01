"""
Project Timeline / Gantt Agent
Manages project timelines, creates Gantt charts, and tracks project schedules.
"""

from .base_agent import BaseAgent
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime, timedelta, timezone as dt_timezone, date as date_type
from django.utils import timezone
from core.models import Project, Task
import calendar


class TimelineGanttAgent(BaseAgent):
    """
    Agent responsible for:
    - Create and visualize project timelines
    - Generate Gantt charts for project visualization
    - Track project milestones and deadlines
    - Identify timeline conflicts and dependencies
    - Identify dependencies: Highlight task relationships to avoid bottlenecks
    - Enhance collaboration: Provide a shared view of the project for all stakeholders
    - Suggest timeline adjustments based on progress
    - Calculate project duration estimates
    - Manage project phases and stages
    - Alert on upcoming deadlines and milestones
    """
    
    def __init__(self):
        super().__init__()
        self.system_prompt = """You are a Project Timeline / Gantt Agent for a project management system.
        Your role is to manage project timelines, create schedules, and visualize project progress.
        You should consider dependencies, resources, and constraints when planning timelines."""
        self.workdays_per_week = 5  # Monday-Friday
        self.hours_per_day = 8
    
    def _is_workday(self, date: date_type) -> bool:
        """Check if a date is a workday (Monday-Friday)"""
        return date.weekday() < 5  # 0-4 are Monday-Friday
    
    def _add_workdays(self, start_date: date_type, workdays: int) -> date_type:
        """Add workdays to a date, skipping weekends. Supports negative workdays."""
        if workdays == 0:
            return start_date
        
        current = start_date
        days_added = 0
        direction = 1 if workdays > 0 else -1
        target = abs(workdays)
        
        while abs(days_added) < target:
            current += timedelta(days=direction)
            if self._is_workday(current):
                days_added += direction
        
        return current
    
    def _calculate_workdays_between(self, start_date: date_type, end_date: date_type) -> int:
        """Calculate number of workdays between two dates"""
        if end_date < start_date:
            return 0
        workdays = 0
        current = start_date
        while current <= end_date:
            if self._is_workday(current):
                workdays += 1
            current += timedelta(days=1)
        return workdays
    
    def create_timeline(self, project_id: int, tasks: List[Dict]) -> Dict:
        """
        Create a project timeline from tasks - maps out tasks and milestones in chronological order.
        
        Args:
            project_id (int): Project ID
            tasks (List[Dict]): List of tasks with durations and dependencies
            
        Returns:
            Dict: Timeline data with tasks organized chronologically
        """
        self.log_action("Creating timeline", {"project_id": project_id, "tasks_count": len(tasks)})
        
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return {
                'success': False,
                'error': f'Project with ID {project_id} not found'
            }
        
        # Sort tasks by due_date, then by priority, then by created_at
        # Use a far future date for tasks without due dates
        far_future = datetime(9999, 12, 31, tzinfo=dt_timezone.utc)
        far_past = datetime(1900, 1, 1, tzinfo=dt_timezone.utc)
        
        def get_date_value(date_str_or_obj):
            """Convert date string or datetime object to comparable datetime"""
            if not date_str_or_obj:
                return far_future
            if isinstance(date_str_or_obj, str):
                try:
                    # Try parsing ISO format string
                    return datetime.fromisoformat(date_str_or_obj.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    return far_future
            if isinstance(date_str_or_obj, datetime):
                return date_str_or_obj
            return far_future
        
        sorted_tasks = sorted(
            tasks,
            key=lambda t: (
                get_date_value(t.get('due_date')),
                {'high': 0, 'medium': 1, 'low': 2}.get(t.get('priority', 'medium'), 1),
                get_date_value(t.get('created_at'))
            )
        )
        
        # Group tasks by status for better visualization
        timeline_data = {
            'project_id': project_id,
            'project_name': project.name,
            'project_start_date': project.start_date.isoformat() if project.start_date else None,
            'project_end_date': project.end_date.isoformat() if project.end_date else None,
            'timeline_created_at': timezone.now().isoformat(),
            'tasks': [],
            'milestones': [],
            'phases': []
        }
        
        # Process each task and add to timeline
        for task in sorted_tasks:
            task_data = {
                'id': task.get('id'),
                'title': task.get('title', 'Untitled Task'),
                'description': task.get('description', ''),
                'status': task.get('status', 'todo'),
                'priority': task.get('priority', 'medium'),
                'due_date': task.get('due_date'),
                'estimated_hours': task.get('estimated_hours'),
                'assignee_id': task.get('assignee_id'),
                'dependencies': task.get('dependencies', [])
            }
            timeline_data['tasks'].append(task_data)
        
        # Use AI to identify meaningful milestones
        import json
        try:
            milestone_prompt = f"""Analyze these project tasks and identify key milestones.

Project: {project.name}
Tasks:
{json.dumps([{'id': t.get('id'), 'title': t.get('title'), 'description': t.get('description', '')[:100], 
              'priority': t.get('priority'), 'status': t.get('status'), 
              'dependencies': len(t.get('dependencies', [])), 'due_date': t.get('due_date')} 
             for t in sorted_tasks[:20]], indent=2)}

Identify milestones based on:
1. High-priority tasks that represent major deliverables
2. Tasks that unblock many other tasks (key dependencies)
3. Tasks that mark phase transitions
4. Tasks with significant business value

Return JSON array:
[
  {{
    "task_id": task_id,
    "title": "milestone title",
    "type": "deliverable|dependency|phase_transition|business_value",
    "importance": "high|medium",
    "reasoning": "why this is a milestone"
  }}
]"""
            
            milestone_response = self._call_llm(milestone_prompt, self.system_prompt, temperature=0.4, max_tokens=1500)
            
            # Extract JSON
            if "```json" in milestone_response:
                json_start = milestone_response.find("```json") + 7
                json_end = milestone_response.find("```", json_start)
                milestone_response = milestone_response[json_start:json_end].strip()
            elif "```" in milestone_response:
                json_start = milestone_response.find("```") + 3
                json_end = milestone_response.find("```", json_start)
                if json_end > json_start:
                    milestone_response = milestone_response[json_start:json_end].strip()
            
            ai_milestones = json.loads(milestone_response)
            milestones = []
            for ms in ai_milestones:
                # Find corresponding task
                task = next((t for t in sorted_tasks if t.get('id') == ms.get('task_id')), None)
                if task:
                    milestones.append({
                        'task_id': task.get('id'),
                        'title': ms.get('title', task.get('title')),
                        'due_date': task.get('due_date'),
                        'type': ms.get('type', 'deliverable'),
                        'importance': ms.get('importance', 'medium'),
                        'reasoning': ms.get('reasoning', '')
                    })
        except Exception as e:
            self.log_action("AI milestone identification failed, using fallback", {"error": str(e)})
            # Fallback to simple milestone identification
        milestones = []
        for task in sorted_tasks:
            if task.get('priority') == 'high' or len(task.get('dependencies', [])) > 2:
                milestones.append({
                    'task_id': task.get('id'),
                    'title': task.get('title'),
                    'due_date': task.get('due_date'),
                        'type': 'high_priority' if task.get('priority') == 'high' else 'key_dependency',
                        'importance': 'high' if task.get('priority') == 'high' else 'medium',
                        'reasoning': ''
                })
        
        timeline_data['milestones'] = milestones
        
        # Calculate timeline summary
        total_tasks = len(sorted_tasks)
        completed_tasks = sum(1 for t in sorted_tasks if t.get('status') == 'done')
        in_progress_tasks = sum(1 for t in sorted_tasks if t.get('status') == 'in_progress')
        
        timeline_data['summary'] = {
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'in_progress_tasks': in_progress_tasks,
            'todo_tasks': total_tasks - completed_tasks - in_progress_tasks,
            'completion_percentage': round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0, 2)
        }
        
        return {
            'success': True,
            'timeline': timeline_data
        }
    
    def generate_gantt_chart(self, project_id: int) -> Dict:
        """
        Generate Gantt chart data for visualization with AI-optimized timeline calculations.
        
        Args:
            project_id (int): Project ID
            
        Returns:
            Dict: Gantt chart data with start/end dates for each task, optimized by AI
        """
        self.log_action("Generating Gantt chart", {"project_id": project_id})
        
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return {
                'success': False,
                'error': f'Project with ID {project_id} not found'
            }
        
        # Get all tasks for the project
        tasks_queryset = Task.objects.filter(project=project).select_related('assignee').prefetch_related('depends_on', 'dependent_tasks')
        
        # Prepare task data for AI analysis
        tasks_data = []
        for task in tasks_queryset:
            tasks_data.append({
                'id': task.id,
                'title': task.title,
                'description': task.description[:200] if task.description else '',
                'status': task.status,
                'priority': task.priority,
                'due_date': task.due_date.isoformat() if task.due_date else None,
                'estimated_hours': float(task.estimated_hours) if task.estimated_hours else None,
                'actual_hours': float(task.actual_hours) if task.actual_hours else None,
                'assignee': task.assignee.username if task.assignee else None,
                'dependencies': [dep.id for dep in task.depends_on.all()],
                'dependent_count': task.dependent_tasks.count()
            })
        
        # Use AI to optimize timeline if we have tasks
        if tasks_data:
            import json
            prompt = f"""You are a project timeline expert. Analyze these tasks and optimize their start/end dates for a Gantt chart.

Project: {project.name}
Project Start Date: {project.start_date.isoformat() if project.start_date else 'Not set'}
Project End Date: {project.end_date.isoformat() if project.end_date else 'Not set'}

Tasks:
{json.dumps(tasks_data, indent=2)}

For each task, calculate optimal start_date and end_date considering:
1. Task dependencies (must start after dependencies complete)
2. Estimated hours (convert to working days: 8 hours = 1 day)
3. Task priority (high priority tasks should be scheduled earlier)
4. Resource availability (consider assignee workload)
5. Realistic buffers for task completion
6. Critical path analysis

Rules:
- If task has dependencies, start_date = max(dependency end_dates) + 1 day buffer
- If task has estimated_hours, duration = max(1, ceil(estimated_hours / 8)) days
- If no estimated_hours, estimate based on task complexity (default: 3 days for medium, 5 for high priority, 2 for low)
- end_date = start_date + duration - 1 (inclusive)
- If task has due_date, respect it but ensure it's after start_date
- Add 10-20% buffer for high-priority or complex tasks

Return JSON array with optimized dates:
[
  {{
    "task_id": task_id,
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD",
    "duration_days": number,
    "reasoning": "brief explanation of date calculation"
  }}
]"""
            
            try:
                response = self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=2000)
                
                # Extract JSON from response
                if "```json" in response:
                    json_start = response.find("```json") + 7
                    json_end = response.find("```", json_start)
                    response = response[json_start:json_end].strip()
                elif "```" in response:
                    json_start = response.find("```") + 3
                    json_end = response.find("```", json_start)
                    if json_end > json_start:
                        response = response[json_start:json_end].strip()
                
                # Parse AI response
                ai_optimizations = json.loads(response)
                optimization_map = {opt['task_id']: opt for opt in ai_optimizations}
            except Exception as e:
                self.log_action("AI optimization failed, using fallback", {"error": str(e)})
                optimization_map = {}
        else:
            optimization_map = {}
        
        gantt_data = {
            'project_id': project_id,
            'project_name': project.name,
            'project_start': project.start_date.isoformat() if project.start_date else None,
            'project_end': project.end_date.isoformat() if project.end_date else None,
            'tasks': []
        }
        
        # Calculate start and end dates for each task (use AI optimization if available)
        project_start = project.start_date or timezone.now().date()
        
        for task in tasks_queryset:
            # Use AI optimization if available
            if task.id in optimization_map:
                opt = optimization_map[task.id]
                try:
                    task_start = datetime.strptime(opt['start_date'], '%Y-%m-%d').date()
                    task_end = datetime.strptime(opt['end_date'], '%Y-%m-%d').date()
                    ai_reasoning = opt.get('reasoning', '')
                except (ValueError, KeyError):
                    # Fallback to manual calculation
                    task_start, task_end, ai_reasoning = self._calculate_task_dates(task, project_start)
                else:
                    # Manual calculation
                    task_start, task_end, ai_reasoning = self._calculate_task_dates(task, project_start)
            
            # Get dependencies
            dependencies = [dep.id for dep in task.depends_on.all()]
            
            # Calculate progress more accurately
            progress = self._calculate_task_progress(task)
            
            gantt_task = {
                'id': task.id,
                'title': task.title,
                'description': task.description,
                'start_date': task_start.isoformat(),
                'end_date': task_end.isoformat(),
                'status': task.status,
                'priority': task.priority,
                'assignee': task.assignee.username if task.assignee else None,
                'assignee_id': task.assignee.id if task.assignee else None,
                'estimated_hours': float(task.estimated_hours) if task.estimated_hours else None,
                'actual_hours': float(task.actual_hours) if task.actual_hours else None,
                'dependencies': dependencies,
                'progress': progress,
                'duration_days': (task_end - task_start).days + 1,
                'ai_reasoning': ai_reasoning if task.id in optimization_map else None
            }
            
            gantt_data['tasks'].append(gantt_task)
        
        # Sort tasks by start date
        gantt_data['tasks'].sort(key=lambda x: x['start_date'])
        
        # Calculate overall project timeline (using workdays)
        if gantt_data['tasks']:
            earliest_start = min(t['start_date'] for t in gantt_data['tasks'])
            latest_end = max(t['end_date'] for t in gantt_data['tasks'])
            start_date = datetime.strptime(earliest_start, '%Y-%m-%d').date()
            end_date = datetime.strptime(latest_end, '%Y-%m-%d').date()
            total_workdays = self._calculate_workdays_between(start_date, end_date)
            total_calendar_days = (end_date - start_date).days + 1
            
            gantt_data['timeline'] = {
                'start': earliest_start,
                'end': latest_end,
                'total_duration_days': total_calendar_days,
                'total_workdays': total_workdays,
                'total_weeks': round(total_workdays / self.workdays_per_week, 1)
            }
        
        # Add critical path analysis using proper CPM algorithm
        critical_path_tasks, task_slack = self._identify_critical_path(gantt_data['tasks'], tasks_queryset)
        
        # Add slack information to each task
        for task in gantt_data['tasks']:
            if task['id'] in task_slack:
                task['slack'] = task_slack[task['id']]
        
        gantt_data['critical_path'] = critical_path_tasks
        
        # Add project timeline metrics
        if critical_path_tasks:
            critical_path_duration = 0
            if critical_path_tasks:
                first_task_start = datetime.strptime(critical_path_tasks[0]['early_start'], '%Y-%m-%d').date()
                last_task_finish = datetime.strptime(critical_path_tasks[-1]['late_finish'], '%Y-%m-%d').date()
                critical_path_duration = self._calculate_workdays_between(first_task_start, last_task_finish)
            
            gantt_data['critical_path_metrics'] = {
                'total_tasks_on_critical_path': len(critical_path_tasks),
                'critical_path_duration_days': critical_path_duration,
                'project_end_date_estimate': critical_path_tasks[-1]['late_finish'] if critical_path_tasks else None
            }
        
        return {
            'success': True,
            'gantt_chart': gantt_data
        }
    
    def _calculate_task_dates(self, task, project_start):
        """Helper method to calculate task start and end dates with workday awareness"""
        # Calculate task start date (consider dependencies)
        task_start = project_start
        if task.depends_on.exists():
            # Start after the latest dependency ends
            latest_dependency_end = None
            for dep_task in task.depends_on.all():
                # Check actual completion first, then due date, then estimate
                if dep_task.status == 'done' and hasattr(dep_task, 'completed_at') and dep_task.completed_at:
                    dep_end = dep_task.completed_at.date()
                elif dep_task.due_date:
                    dep_end = dep_task.due_date.date()
                elif dep_task.estimated_hours:
                    # Estimate dependency end based on hours (convert to workdays)
                    workdays = max(1, int(dep_task.estimated_hours / self.hours_per_day))
                    dep_start = dep_task.created_at.date() if hasattr(dep_task, 'created_at') else project_start
                    dep_end = self._add_workdays(dep_start, workdays - 1)
                else:
                    continue
                
                if not latest_dependency_end or dep_end > latest_dependency_end:
                    latest_dependency_end = dep_end
            
            if latest_dependency_end:
                # Start on next workday after dependency ends
                task_start = self._add_workdays(latest_dependency_end, 1)
        
        # Ensure start date is a workday
        if not self._is_workday(task_start):
            task_start = self._add_workdays(task_start, 1)
        
        # Calculate task end date
        task_end = task.due_date.date() if task.due_date else None
        if not task_end:
            # Estimate end date based on estimated hours
            if task.estimated_hours:
                # Convert hours to workdays
                workdays = max(1, int(task.estimated_hours / self.hours_per_day))
                if task.priority == 'high':
                    workdays = int(workdays * 1.2)  # 20% buffer for high priority
                task_end = self._add_workdays(task_start, workdays - 1)
            else:
                # Default workdays based on priority
                default_workdays = {'high': 5, 'medium': 3, 'low': 2}.get(task.priority, 3)
                task_end = self._add_workdays(task_start, default_workdays - 1)
        else:
            # If due date provided, ensure it's reasonable
            if task_end < task_start:
                # Due date is before start, adjust it
                if task.estimated_hours:
                    workdays = max(1, int(task.estimated_hours / self.hours_per_day))
                    task_end = self._add_workdays(task_start, workdays - 1)
                else:
                    task_end = self._add_workdays(task_start, 3)
        
        return task_start, task_end, None
    
    def _calculate_task_progress(self, task):
        """Calculate task progress percentage considering subtasks and actual hours"""
        if task.status == 'done':
            return 100
        
        # Check subtask completion for more accurate progress
        try:
            subtasks = task.subtasks.all()
            if subtasks.exists():
                completed_subtasks = subtasks.filter(status='done').count()
                total_subtasks = subtasks.count()
                subtask_progress = (completed_subtasks / total_subtasks * 100) if total_subtasks > 0 else 0
                
                if task.status == 'in_progress':
                    # Blend subtask progress with time-based progress
                    if task.estimated_hours and task.actual_hours:
                        time_progress = min(90, (task.actual_hours / task.estimated_hours) * 100)
                        # Weight: 60% subtasks, 40% time
                        progress = (subtask_progress * 0.6) + (time_progress * 0.4)
                        return max(10, min(90, int(progress)))
                    return max(10, min(90, int(subtask_progress * 0.8)))  # Cap at 90% if not done
        except:
            pass  # If subtasks don't exist, fall back to time-based
        
        # Time-based progress calculation
        if task.status == 'in_progress':
            if task.estimated_hours and task.actual_hours:
                progress = min(90, int((task.actual_hours / task.estimated_hours) * 100))
                return max(10, progress)  # At least 10% if in progress
            return 50
        elif task.status == 'review':
            return 90
        elif task.status == 'blocked':
            return 0
        else:
            return 0
    
    def _identify_critical_path(self, tasks_data: List[Dict], tasks_queryset=None) -> Tuple[List[Dict], Dict]:
        """
        Identify critical path using Critical Path Method (CPM) algorithm.
        Calculates early start/finish, late start/finish, and float for each task.
        """
        if not tasks_data:
            return []
        
        # Build task map and dependency graph
        task_map = {t['id']: t for t in tasks_data}
        dependencies = {}
        dependents = {}
        
        for task in tasks_data:
            task_id = task['id']
            deps = task.get('dependencies', [])
            dependencies[task_id] = deps
            for dep_id in deps:
                if dep_id not in dependents:
                    dependents[dep_id] = []
                dependents[dep_id].append(task_id)
        
        # Find tasks with no dependencies (start nodes)
        start_tasks = [t_id for t_id in task_map.keys() if not dependencies.get(t_id, [])]
        
        # Forward pass: Calculate Early Start (ES) and Early Finish (EF)
        early_start = {}
        early_finish = {}
        visited = set()
        
        def get_task_duration(task_data):
            """Get task duration in days"""
            duration = task_data.get('duration_days', 1)
            if duration <= 0:
                # Estimate from hours or default
                hours = task_data.get('estimated_hours', 0) or 0
                if hours > 0:
                    return max(1, int(hours / self.hours_per_day))
                return 3  # Default 3 days
            return max(1, duration)
        
        def forward_pass(task_id):
            if task_id in visited:
                return early_start.get(task_id, date_type.today())
            
            visited.add(task_id)
            task = task_map[task_id]
            
            # Get dependencies' early finish dates
            dep_early_finishes = []
            for dep_id in dependencies.get(task_id, []):
                if dep_id in task_map:
                    forward_pass(dep_id)  # Ensure dependency is processed
                    dep_ef = early_finish.get(dep_id)
                    if dep_ef:
                        dep_early_finishes.append(dep_ef)
            
            # Early start is max of all dependency early finishes (or project start)
            if dep_early_finishes:
                es = max(dep_early_finishes)
                # Add 1 workday buffer between tasks
                es = self._add_workdays(es, 1)
            else:
                # Start task on project start date (or earliest date in tasks)
                start_dates = [datetime.strptime(t.get('start_date', ''), '%Y-%m-%d').date() 
                             for t in tasks_data if t.get('start_date')]
                es = min(start_dates) if start_dates else date_type.today()
            
            duration = get_task_duration(task)
            ef = self._add_workdays(es, duration - 1)  # -1 because start day counts
            
            early_start[task_id] = es
            early_finish[task_id] = ef
            
            return es
        
        # Process all tasks
        for task_id in task_map.keys():
            forward_pass(task_id)
        
        # Find project end date (max early finish)
        if not early_finish:
            return [], {}
        
        project_end = max(early_finish.values())
        
        # Backward pass: Calculate Late Start (LS) and Late Finish (LF)
        late_finish = {}
        late_start = {}
        visited_backward = set()
        
        def backward_pass(task_id):
            if task_id in visited_backward:
                return late_finish.get(task_id, project_end)
            
            visited_backward.add(task_id)
            task = task_map[task_id]
            
            # Get dependents' late start dates
            dependent_late_starts = []
            for dep_id in dependents.get(task_id, []):
                if dep_id in task_map:
                    backward_pass(dep_id)  # Ensure dependent is processed
                    dep_ls = late_start.get(dep_id)
                    if dep_ls:
                        dependent_late_starts.append(dep_ls)
            
            # Late finish is min of all dependent late starts (or project end)
            if dependent_late_starts:
                lf = min(dependent_late_starts)
                # Subtract 1 workday buffer
                lf = self._add_workdays(lf, -1)
            else:
                lf = project_end
            
            duration = get_task_duration(task)
            ls = self._add_workdays(lf, -(duration - 1))
            
            late_finish[task_id] = lf
            late_start[task_id] = ls
            
            return lf
        
        # Process all tasks in reverse order
        for task_id in reversed(list(task_map.keys())):
            backward_pass(task_id)
        
        # Calculate float (slack) for all tasks and identify critical path
        all_task_slack = {}
        critical_path = []
        
        for task_id, task_data in task_map.items():
            es = early_start.get(task_id)
            ef = early_finish.get(task_id)
            ls = late_start.get(task_id)
            lf = late_finish.get(task_id)
            
            if es and ef and ls and lf:
                # Total float = LS - ES or LF - EF (should be same)
                total_float = self._calculate_workdays_between(ef, lf)
                
                # Free float (can delay without affecting next task)
                free_float = float('inf')
                for dep_id in dependents.get(task_id, []):
                    if dep_id in early_start:
                        dep_es = early_start[dep_id]
                        free_float = min(free_float, self._calculate_workdays_between(ef, dep_es))
                
                if free_float == float('inf'):
                    free_float = total_float
                
                # Critical path: tasks with zero or near-zero float
                is_critical = total_float <= 1  # Allow 1 day tolerance
                
                # Store slack for all tasks
                all_task_slack[task_id] = {
                    'total_float': total_float,
                    'free_float': free_float,
                    'early_start': es.isoformat(),
                    'early_finish': ef.isoformat(),
                    'late_start': ls.isoformat(),
                    'late_finish': lf.isoformat()
                }
                
                # Add to critical path if zero float
                if is_critical:
                    critical_path.append({
                        'task_id': task_id,
                        'title': task_data.get('title', 'Unknown'),
                        'early_start': es.isoformat(),
                        'early_finish': ef.isoformat(),
                        'late_start': ls.isoformat(),
                        'late_finish': lf.isoformat(),
                        'total_float': total_float,
                        'free_float': free_float,
                        'duration_days': get_task_duration(task_data),
                        'reason': f'Zero float - on critical path (blocks project completion)'
                    })
        
        # Sort by early start
        critical_path.sort(key=lambda x: x['early_start'])
        
        return critical_path, all_task_slack
    
    def track_milestones(self, project_id: int) -> Dict:
        """
        Track project milestones and deadlines.
        
        Args:
            project_id (int): Project ID
            
        Returns:
            Dict: Milestone tracking data with status and progress
        """
        self.log_action("Tracking milestones", {"project_id": project_id})
        
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return {
                'success': False,
                'error': f'Project with ID {project_id} not found'
            }
        
        # Get all tasks
        tasks = Task.objects.filter(project=project)
        
        milestones = []
        now = timezone.now()
        
        # Identify milestones (high priority tasks, tasks with many dependencies, or key tasks)
        for task in tasks:
            is_milestone = (
                task.priority == 'high' or
                task.depends_on.count() > 2 or
                task.dependent_tasks.count() > 2
            )
            
            if is_milestone:
                milestone_status = 'completed' if task.status == 'done' else (
                    'in_progress' if task.status == 'in_progress' else 'upcoming'
                )
                
                days_until_due = None
                if task.due_date:
                    delta = task.due_date - now
                    days_until_due = delta.days
                
                milestones.append({
                    'task_id': task.id,
                    'title': task.title,
                    'description': task.description,
                    'status': milestone_status,
                    'due_date': task.due_date.isoformat() if task.due_date else None,
                    'days_until_due': days_until_due,
                    'priority': task.priority,
                    'assignee': task.assignee.username if task.assignee else None,
                    'is_overdue': days_until_due < 0 if days_until_due is not None else False
                })
        
        # Sort milestones by due date
        milestones.sort(key=lambda m: (
            m['due_date'] if m['due_date'] else '9999-12-31',
            {'high': 0, 'medium': 1, 'low': 2}.get(m['priority'], 1)
        ))
        
        # Calculate milestone statistics
        total_milestones = len(milestones)
        completed_milestones = sum(1 for m in milestones if m['status'] == 'completed')
        overdue_milestones = sum(1 for m in milestones if m.get('is_overdue', False))
        
        return {
            'success': True,
            'milestones': milestones,
            'summary': {
                'total_milestones': total_milestones,
                'completed_milestones': completed_milestones,
                'in_progress_milestones': sum(1 for m in milestones if m['status'] == 'in_progress'),
                'upcoming_milestones': sum(1 for m in milestones if m['status'] == 'upcoming'),
                'overdue_milestones': overdue_milestones,
                'completion_rate': round((completed_milestones / total_milestones * 100) if total_milestones > 0 else 0, 2)
            }
        }
    
    def identify_conflicts(self, project_id: int) -> Dict:
        """
        Identify timeline conflicts and dependencies.
        
        Args:
            project_id (int): Project ID
            
        Returns:
            Dict: Conflict analysis with dependency issues and timeline conflicts
        """
        self.log_action("Identifying conflicts", {"project_id": project_id})
        
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return {
                'success': False,
                'error': f'Project with ID {project_id} not found'
            }
        
        tasks = Task.objects.filter(project=project).prefetch_related('depends_on', 'dependent_tasks')
        
        conflicts = []
        dependency_issues = []
        
        # Check for circular dependencies
        def has_circular_dependency(task, visited=None, path=None):
            if visited is None:
                visited = set()
            if path is None:
                path = []
            
            if task.id in path:
                return True, path + [task.id]
            
            if task.id in visited:
                return False, []
            
            visited.add(task.id)
            path.append(task.id)
            
            for dep in task.depends_on.all():
                has_circle, circle_path = has_circular_dependency(dep, visited, path.copy())
                if has_circle:
                    return True, circle_path
            
            return False, []
        
        # Check each task for conflicts
        for task in tasks:
            # Check circular dependencies
            has_circle, circle_path = has_circular_dependency(task)
            if has_circle:
                dependency_issues.append({
                    'type': 'circular_dependency',
                    'task_id': task.id,
                    'task_title': task.title,
                    'circular_path': circle_path,
                    'severity': 'high',
                    'description': f'Circular dependency detected involving task: {task.title}'
                })
            
            # Check if task's due date is before its dependencies' due dates
            if task.due_date:
                for dep_task in task.depends_on.all():
                    if dep_task.due_date and dep_task.due_date > task.due_date:
                        conflicts.append({
                            'type': 'dependency_timing_conflict',
                            'task_id': task.id,
                            'task_title': task.title,
                            'task_due_date': task.due_date.isoformat(),
                            'dependency_id': dep_task.id,
                            'dependency_title': dep_task.title,
                            'dependency_due_date': dep_task.due_date.isoformat(),
                            'severity': 'high',
                            'description': f'Task "{task.title}" is due before its dependency "{dep_task.title}"'
                        })
            
            # Check for overlapping assignments with actual task durations
            if task.assignee and task.due_date:
                # Calculate actual task duration window
                if task.estimated_hours:
                    workdays = max(1, int(task.estimated_hours / self.hours_per_day))
                    task_start_window = self._add_workdays(task.due_date.date(), -(workdays - 1))
                else:
                    task_start_window = task.due_date.date() - timedelta(days=3)
                
                task_end_window = task.due_date.date()
                
                overlapping_tasks = Task.objects.filter(
                    project=project,
                    assignee=task.assignee,
                    due_date__isnull=False,
                    status__in=['todo', 'in_progress']
                ).exclude(id=task.id)
                
                for other_task in overlapping_tasks:
                    if other_task.due_date:
                        # Calculate other task's duration window
                        if other_task.estimated_hours:
                            other_workdays = max(1, int(other_task.estimated_hours / self.hours_per_day))
                            other_start_window = self._add_workdays(other_task.due_date.date(), -(other_workdays - 1))
                        else:
                            other_start_window = other_task.due_date.date() - timedelta(days=3)
                        
                        other_end_window = other_task.due_date.date()
                        
                        # Check for overlap in workday windows
                        if not (task_end_window < other_start_window or task_start_window > other_end_window):
                            # Calculate overlap in workdays
                            overlap_start = max(task_start_window, other_start_window)
                            overlap_end = min(task_end_window, other_end_window)
                            overlap_days = self._calculate_workdays_between(overlap_start, overlap_end)
                            
                            if overlap_days > 0:
                                conflicts.append({
                                'type': 'resource_overload',
                                'task_id': task.id,
                                'task_title': task.title,
                                'conflicting_task_id': other_task.id,
                                'conflicting_task_title': other_task.title,
                                'assignee': task.assignee.username,
                                'assignee_id': task.assignee.id,
                                    'overlap_workdays': overlap_days,
                                    'severity': 'high' if overlap_days > 3 else 'medium',
                                    'description': f'"{task.assignee.username}" has {overlap_days} workday(s) overlap between "{task.title}" and "{other_task.title}"'
                            })
        
        # Check for missing dependencies (tasks that should depend on others but don't)
        for task in tasks:
            # If a task has many dependent tasks, it might be a critical path item
            dependent_count = task.dependent_tasks.count()
            if dependent_count > 3 and task.status in ['todo', 'in_progress']:
                if not task.due_date:
                    conflicts.append({
                        'type': 'missing_deadline',
                        'task_id': task.id,
                        'task_title': task.title,
                        'dependent_tasks_count': dependent_count,
                        'severity': 'medium',
                        'description': f'Task "{task.title}" has {dependent_count} dependent tasks but no deadline set'
                    })
        
        # Use AI to analyze conflicts and provide resolution suggestions
        if conflicts or dependency_issues:
            import json
            try:
                conflict_prompt = f"""Analyze these project conflicts and provide resolution recommendations.

Project: {project.name}
Conflicts Found: {len(conflicts)} timing/resource conflicts
Dependency Issues: {len(dependency_issues)} dependency problems

Conflicts:
{json.dumps(conflicts[:10], indent=2)}

Dependency Issues:
{json.dumps(dependency_issues[:10], indent=2)}

For each conflict/issue, provide:
1. Resolution strategy (how to fix it)
2. Priority of resolution (high/medium/low)
3. Impact if not resolved
4. Recommended action steps

Return JSON:
{{
  "resolutions": [
    {{
      "conflict_id": "reference to conflict",
      "type": "conflict_type",
      "resolution_strategy": "detailed strategy",
      "priority": "high|medium|low",
      "impact": "what happens if not fixed",
      "action_steps": ["step1", "step2"]
    }}
  ],
  "summary": "overall conflict analysis and recommendations"
}}"""
                
                resolution_response = self._call_llm(conflict_prompt, self.system_prompt, temperature=0.4, max_tokens=2000)
                
                # Extract JSON
                if "```json" in resolution_response:
                    json_start = resolution_response.find("```json") + 7
                    json_end = resolution_response.find("```", json_start)
                    resolution_response = resolution_response[json_start:json_end].strip()
                elif "```" in resolution_response:
                    json_start = resolution_response.find("```") + 3
                    json_end = resolution_response.find("```", json_start)
                    if json_end > json_start:
                        resolution_response = resolution_response[json_start:json_end].strip()
                
                ai_resolutions = json.loads(resolution_response)
                
                # Add resolutions to conflicts
                resolution_map = {r.get('conflict_id', ''): r for r in ai_resolutions.get('resolutions', [])}
                for i, conflict in enumerate(conflicts):
                    conflict_key = f"conflict_{i}"
                    if conflict_key in resolution_map:
                        conflict['resolution'] = resolution_map[conflict_key]
                
                for i, issue in enumerate(dependency_issues):
                    issue_key = f"issue_{i}"
                    if issue_key in resolution_map:
                        issue['resolution'] = resolution_map[issue_key]
                
                ai_summary = ai_resolutions.get('summary', '')
            except Exception as e:
                self.log_action("AI conflict resolution failed", {"error": str(e)})
                ai_summary = None
        else:
            ai_summary = None
        
        result = {
            'success': True,
            'conflicts': conflicts,
            'dependency_issues': dependency_issues,
            'summary': {
                'total_conflicts': len(conflicts) + len(dependency_issues),
                'timing_conflicts': sum(1 for c in conflicts if c['type'] == 'dependency_timing_conflict'),
                'resource_overloads': sum(1 for c in conflicts if c['type'] == 'resource_overload'),
                'circular_dependencies': len(dependency_issues),
                'missing_deadlines': sum(1 for c in conflicts if c['type'] == 'missing_deadline'),
                'high_severity': sum(1 for c in conflicts + dependency_issues if c.get('severity') == 'high'),
                'medium_severity': sum(1 for c in conflicts + dependency_issues if c.get('severity') == 'medium')
            }
        }
        
        if ai_summary:
            result['ai_analysis'] = ai_summary
        
        return result
    
    def suggest_adjustments(self, project_id: int, current_progress: Dict) -> Dict:
        """
        Suggest timeline adjustments based on progress with AI-powered analysis.
        
        Args:
            project_id (int): Project ID
            current_progress (Dict): Current project progress data
            
        Returns:
            Dict: Timeline adjustment suggestions with AI reasoning
        """
        self.log_action("Suggesting timeline adjustments", {"project_id": project_id})
        
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return {
                'success': False,
                'error': f'Project with ID {project_id} not found'
            }
        
        # Get all tasks
        tasks = Task.objects.filter(project=project).select_related('assignee').prefetch_related('depends_on')
        
        # Prepare task data for AI analysis
        import json
        now = timezone.now()
        tasks_analysis = []
        for task in tasks:
            days_overdue = None
            if task.due_date and task.due_date < now:
                days_overdue = (now - task.due_date).days
            
            overage_percentage = None
            if task.estimated_hours and task.actual_hours:
                if task.actual_hours > task.estimated_hours:
                    overage_percentage = ((task.actual_hours - task.estimated_hours) / task.estimated_hours) * 100
            
            tasks_analysis.append({
                'id': task.id,
                'title': task.title,
                'status': task.status,
                'priority': task.priority,
                'due_date': task.due_date.isoformat() if task.due_date else None,
                'estimated_hours': float(task.estimated_hours) if task.estimated_hours else None,
                'actual_hours': float(task.actual_hours) if task.actual_hours else None,
                'days_overdue': days_overdue,
                'overage_percentage': round(overage_percentage, 1) if overage_percentage else None,
                'assignee': task.assignee.username if task.assignee else None,
                'dependencies_count': task.depends_on.count(),
                'dependent_tasks_count': task.dependent_tasks.count()
            })
        
        # Calculate project metrics
        total_tasks = tasks.count()
        completed_tasks = tasks.filter(status='done').count()
        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        expected_completion_rate = None
        if project.end_date and project.start_date:
            project_duration = (project.end_date - project.start_date).days
            elapsed_days = (now.date() - project.start_date).days
            if project_duration > 0:
                expected_completion_rate = (elapsed_days / project_duration) * 100
        
        # Use AI to generate comprehensive suggestions
        prompt = f"""You are a project management expert. Analyze this project's progress and suggest timeline adjustments.

Project: {project.name}
Project Status: {project.status}
Project Start: {project.start_date.isoformat() if project.start_date else 'Not set'}
Project End: {project.end_date.isoformat() if project.end_date else 'Not set'}
Current Date: {now.isoformat()}

Progress Metrics:
- Total Tasks: {total_tasks}
- Completed Tasks: {completed_tasks}
- Completion Rate: {round(completion_rate, 1)}%
- Expected Completion Rate: {round(expected_completion_rate, 1) if expected_completion_rate else 'N/A'}%

Tasks Analysis:
{json.dumps(tasks_analysis, indent=2)}

Analyze and suggest adjustments for:
1. Overdue tasks - suggest realistic deadline extensions
2. Tasks taking longer than estimated - revise estimates or extend deadlines
3. Project timeline - if behind schedule, suggest extension or acceleration strategies
4. Resource overload - identify overloaded team members and suggest redistribution
5. Critical path tasks - prioritize adjustments for tasks blocking others
6. Risk mitigation - suggest buffers and contingency plans

For each suggestion, provide:
- Type of adjustment needed
- Specific task/project affected
- Recommended action with dates/values
- Detailed reasoning explaining why this adjustment is needed
- Priority level (high/medium/low)

Return JSON array:
[
  {{
    "type": "extend_deadline|revise_estimate|extend_project_deadline|redistribute_workload|add_buffer|prioritize_task",
    "task_id": task_id_or_null,
    "task_title": "task title or null",
    "project_level": true_if_project_level,
    "current_value": "current deadline/estimate/etc",
    "suggested_value": "new deadline/estimate/etc",
    "suggested_extension_days": number_or_null,
    "priority": "high|medium|low",
    "reasoning": "detailed explanation (2-3 sentences) of why this adjustment is needed, considering dependencies, resource constraints, and project goals",
    "impact": "description of how this affects the project"
  }}
]"""
        
        suggestions = []
        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.4, max_tokens=2500)
            
            # Extract JSON
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                if json_end > json_start:
                    response = response[json_start:json_end].strip()
            
            ai_suggestions = json.loads(response)
            
            # Validate and add AI suggestions
            for sug in ai_suggestions:
                if sug.get('task_id'):
                    # Verify task exists
                    task = tasks.filter(id=sug['task_id']).first()
                    if task:
                        sug['task_title'] = task.title
                        sug['assignee'] = task.assignee.username if task.assignee else None
                suggestions.append(sug)
                
        except Exception as e:
            self.log_action("AI suggestions failed, using fallback", {"error": str(e)})
            # Fallback to rule-based suggestions
        for task in tasks:
            if task.status in ['todo', 'in_progress', 'review']:
                if task.due_date and task.due_date < now:
                    days_overdue = (now - task.due_date).days
                    suggestions.append({
                        'type': 'extend_deadline',
                        'task_id': task.id,
                        'task_title': task.title,
                        'current_due_date': task.due_date.isoformat(),
                        'days_overdue': days_overdue,
                        'suggested_extension_days': max(3, days_overdue + 2),
                            'priority': 'high' if days_overdue > 7 else 'medium',
                            'reasoning': f'Task is {days_overdue} day(s) overdue',
                            'impact': 'May delay dependent tasks'
                    })
                
                if task.estimated_hours and task.actual_hours:
                    if task.actual_hours > task.estimated_hours * 1.2:
                        overage_percentage = ((task.actual_hours - task.estimated_hours) / task.estimated_hours) * 100
                        suggestions.append({
                            'type': 'revise_estimate',
                            'task_id': task.id,
                            'task_title': task.title,
                            'current_estimate': task.estimated_hours,
                            'actual_hours': task.actual_hours,
                            'overage_percentage': round(overage_percentage, 1),
                                'priority': 'medium',
                                'reasoning': f'Task is taking {round(overage_percentage, 1)}% longer than estimated',
                                'impact': 'Future similar tasks may need revised estimates'
                            })
        
        # Add project-level suggestions
        if project.end_date and expected_completion_rate:
            if completion_rate < expected_completion_rate - 10:
                suggestions.append({
                        'type': 'extend_project_deadline',
                        'project_id': project.id,
                        'project_name': project.name,
                    'project_level': True,
                        'current_completion_rate': round(completion_rate, 1),
                        'expected_completion_rate': round(expected_completion_rate, 1),
                        'current_end_date': project.end_date.isoformat(),
                        'suggested_extension_days': max(7, int((expected_completion_rate - completion_rate) / 10)),
                    'priority': 'high',
                    'reasoning': f'Project is {round(expected_completion_rate - completion_rate, 1)}% behind expected progress',
                    'impact': 'Project deadline may need adjustment'
                    })
        
        # Resource overload check
        assignee_counts = {}
        for task in tasks.filter(status__in=['todo', 'in_progress']):
            if task.assignee:
                assignee_id = task.assignee.id
                assignee_counts[assignee_id] = assignee_counts.get(assignee_id, 0) + 1
        
        for assignee_id, count in assignee_counts.items():
            if count > 5:
                assignee = tasks.filter(assignee_id=assignee_id).first().assignee
                suggestions.append({
                    'type': 'redistribute_workload',
                    'assignee_id': assignee_id,
                    'assignee_name': assignee.username,
                    'current_task_count': count,
                    'priority': 'high' if count > 8 else 'medium',
                    'reasoning': f'{assignee.username} has {count} active tasks, which may lead to delays',
                    'impact': 'May cause bottlenecks and missed deadlines'
                })
        
        return {
            'success': True,
            'suggestions': suggestions,
            'summary': {
                'total_suggestions': len(suggestions),
                'deadline_extensions': sum(1 for s in suggestions if s['type'] == 'extend_deadline'),
                'estimate_revisions': sum(1 for s in suggestions if s['type'] == 'revise_estimate'),
                'workload_redistributions': sum(1 for s in suggestions if s['type'] == 'redistribute_workload'),
                'project_extensions': sum(1 for s in suggestions if s['type'] == 'extend_project_deadline'),
                'high_priority': sum(1 for s in suggestions if s.get('priority') == 'high'),
                'medium_priority': sum(1 for s in suggestions if s.get('priority') == 'medium'),
                'low_priority': sum(1 for s in suggestions if s.get('priority') == 'low')
            }
        }
    
    def calculate_duration_estimate(self, tasks: List[Dict]) -> Dict:
        """
        Calculate project duration estimates with AI-powered analysis.
        
        Args:
            tasks (List[Dict]): List of tasks with estimated hours and dependencies
            
        Returns:
            Dict: Duration estimates including optimistic, realistic, and pessimistic scenarios with AI insights
        """
        self.log_action("Calculating duration estimate", {"tasks_count": len(tasks)})
        
        if not tasks:
            return {
                'success': False,
                'error': 'No tasks provided for duration estimation'
            }
        
        # Prepare task summary for AI
        import json
        task_summary = []
        for task in tasks[:30]:  # Limit for token efficiency
            task_summary.append({
                'id': task.get('id'),
                'title': task.get('title', '')[:50],
                'estimated_hours': task.get('estimated_hours'),
                'priority': task.get('priority', 'medium'),
                'status': task.get('status', 'todo'),
                'dependencies_count': len(task.get('dependencies', [])),
                'has_due_date': bool(task.get('due_date'))
            })
        
        # Use AI for more accurate estimation
        prompt = f"""You are a project estimation expert. Analyze these tasks and provide accurate duration estimates.

Tasks Summary:
{json.dumps(task_summary, indent=2)}

Total Tasks: {len(tasks)}
Tasks with Estimated Hours: {sum(1 for t in tasks if t.get('estimated_hours'))}
Tasks with Dependencies: {sum(1 for t in tasks if t.get('dependencies'))}

Provide duration estimates considering:
1. Task complexity (based on titles and descriptions)
2. Dependencies (critical path analysis)
3. Resource availability (assume standard team)
4. Risk factors (high priority tasks, dependencies, etc.)
5. Historical patterns (tasks often take 20-30% longer than estimated)

Calculate:
- Total estimated hours (sum of all task estimates, or estimate if missing)
- Working days needed (8 hours per day)
- Calendar days (accounting for weekends, 5-day work weeks)
- Optimistic scenario (best case, 15% faster)
- Realistic scenario (most likely, with buffers)
- Pessimistic scenario (worst case, 30% slower with delays)
- Expected duration (PERT: (optimistic + 4*realistic + pessimistic) / 6)

Return JSON:
{{
  "total_estimated_hours": number,
  "working_days": {{
    "optimistic": number,
    "realistic": number,
    "pessimistic": number,
    "expected": number
  }},
  "calendar_days": {{
    "expected": number,
    "weeks": number
  }},
  "dependency_buffer_days": number,
  "risk_buffer_days": number,
  "recommendations": {{
    "suggested_deadline_days": number,
    "suggested_deadline_weeks": number,
    "confidence_level": "high|medium|low",
    "key_risks": ["risk1", "risk2"],
    "notes": "brief explanation of estimates and assumptions"
  }}
}}"""
        
        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=1500)
            
            # Extract JSON
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                if json_end > json_start:
                    response = response[json_start:json_end].strip()
            
            ai_estimates = json.loads(response)
        except Exception as e:
            self.log_action("AI estimation failed, using fallback", {"error": str(e)})
            ai_estimates = None
        
        # Calculate base estimates
        total_estimated_hours = sum(
            task.get('estimated_hours', 0) or 0 
            for task in tasks 
            if task.get('estimated_hours')
        )
        
        if total_estimated_hours == 0:
            total_estimated_hours = len(tasks) * 8
        
        working_days = total_estimated_hours / 8
        tasks_with_deps = sum(1 for task in tasks if task.get('dependencies'))
        dependency_buffer = tasks_with_deps * 0.5
        
        # Use AI estimates if available, otherwise use calculated
        if ai_estimates:
            estimates = {
                'total_tasks': len(tasks),
                'total_estimated_hours': round(ai_estimates.get('total_estimated_hours', total_estimated_hours), 2),
                'working_days': {
                    'optimistic': round(ai_estimates['working_days'].get('optimistic', working_days * 0.85), 1),
                    'realistic': round(ai_estimates['working_days'].get('realistic', working_days + dependency_buffer), 1),
                    'pessimistic': round(ai_estimates['working_days'].get('pessimistic', working_days * 1.3 + dependency_buffer), 1),
                    'expected': round(ai_estimates['working_days'].get('expected', (working_days * 0.85 + 4 * (working_days + dependency_buffer) + (working_days * 1.3 + dependency_buffer)) / 6), 1)
                },
                'calendar_days': {
                    'expected': round(ai_estimates['calendar_days'].get('expected', (ai_estimates['working_days'].get('expected', working_days) / 5) * 7), 1),
                    'weeks': round(ai_estimates['calendar_days'].get('weeks', ai_estimates['working_days'].get('expected', working_days) / 5), 1)
                },
                'dependency_buffer_days': round(ai_estimates.get('dependency_buffer_days', dependency_buffer), 1),
                'risk_buffer_days': round(ai_estimates.get('risk_buffer_days', 0), 1),
                'tasks_with_dependencies': tasks_with_deps
            }
            recommendations = ai_estimates.get('recommendations', {})
        else:
            # Fallback calculations
            optimistic_days = working_days * 0.85
            realistic_days = working_days + dependency_buffer
            pessimistic_days = working_days * 1.3 + dependency_buffer
            expected_days = (optimistic_days + 4 * realistic_days + pessimistic_days) / 6
            calendar_weeks = expected_days / 5
            calendar_days = calendar_weeks * 7
            
            estimates = {
                'total_tasks': len(tasks),
                'total_estimated_hours': round(total_estimated_hours, 2),
                'working_days': {
                    'optimistic': round(optimistic_days, 1),
                    'realistic': round(realistic_days, 1),
                    'pessimistic': round(pessimistic_days, 1),
                    'expected': round(expected_days, 1)
                },
                'calendar_days': {
                    'expected': round(calendar_days, 1),
                    'weeks': round(calendar_weeks, 1)
                },
                'dependency_buffer_days': round(dependency_buffer, 1),
                'risk_buffer_days': 0,
                'tasks_with_dependencies': tasks_with_deps
            }
            recommendations = {
                'suggested_deadline_days': round(expected_days + 3, 1),
                'suggested_deadline_weeks': round((expected_days + 3) / 5, 1),
                'confidence_level': 'medium',
                'key_risks': ['Uncertain task estimates', 'Dependency delays'],
                'notes': 'Estimates assume 8-hour working days and 5-day work weeks. Add buffer for unexpected delays.'
            }
        
        # Get actual span if tasks have due dates
        tasks_with_dates = [t for t in tasks if t.get('due_date')]
        if tasks_with_dates:
            try:
                dates = [datetime.fromisoformat(t['due_date'].replace('Z', '+00:00')) for t in tasks_with_dates if t.get('due_date')]
                if dates:
                    earliest_date = min(dates)
                    latest_date = max(dates)
                    actual_span_days = (latest_date - earliest_date).days
                else:
                    actual_span_days = None
            except:
                actual_span_days = None
        else:
            actual_span_days = None
        
        estimates['actual_span_days'] = actual_span_days
        
        return {
            'success': True,
            'estimates': estimates,
            'recommendations': recommendations
        }
    
    def manage_phases(self, project_id: int, phases: List[Dict] = None) -> Dict:
        """
        Manage project phases and stages.
        
        Args:
            project_id (int): Project ID
            phases (List[Dict]): Optional list of project phases
            
        Returns:
            Dict: Phase management data
        """
        self.log_action("Managing phases", {"project_id": project_id})
        
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return {
                'success': False,
                'error': f'Project with ID {project_id} not found'
            }
        
        # Group tasks by status as phases
        tasks = Task.objects.filter(project=project)
        
        phases_data = []
        phase_order = ['todo', 'in_progress', 'review', 'done']
        
        for phase_status in phase_order:
            phase_tasks = tasks.filter(status=phase_status)
            if phase_tasks.exists():
                phases_data.append({
                    'phase': phase_status.replace('_', ' ').title(),
                    'status': phase_status,
                    'task_count': phase_tasks.count(),
                    'tasks': [{
                        'id': t.id,
                        'title': t.title,
                        'priority': t.priority,
                        'due_date': t.due_date.isoformat() if t.due_date else None
                    } for t in phase_tasks[:10]]  # Limit to 10 tasks per phase
                })
        
        return {
            'success': True,
            'phases': phases_data,
            'total_phases': len(phases_data)
        }
    
    def check_upcoming_deadlines(self, project_id: int, days_ahead: int = 7) -> Dict:
        """
        Check and alert on upcoming deadlines and milestones.
        
        Args:
            project_id (int): Project ID
            days_ahead (int): Number of days to look ahead
            
        Returns:
            Dict: Upcoming deadlines and alerts
        """
        self.log_action("Checking upcoming deadlines", {"project_id": project_id, "days_ahead": days_ahead})
        
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return {
                'success': False,
                'error': f'Project with ID {project_id} not found'
            }
        
        now = timezone.now()
        future_date = now + timedelta(days=days_ahead)
        
        # Get tasks with deadlines in the next N days
        upcoming_tasks = Task.objects.filter(
            project=project,
            due_date__gte=now,
            due_date__lte=future_date,
            status__in=['todo', 'in_progress', 'review']
        ).select_related('assignee').order_by('due_date')
        
        # Get overdue tasks
        overdue_tasks = Task.objects.filter(
            project=project,
            due_date__lt=now,
            status__in=['todo', 'in_progress', 'review']
        ).select_related('assignee').order_by('due_date')
        
        alerts = []
        
        # Process upcoming tasks
        for task in upcoming_tasks:
            days_until = (task.due_date - now).days
            urgency = 'high' if days_until <= 2 else ('medium' if days_until <= 5 else 'low')
            
            alerts.append({
                'type': 'upcoming',
                'task_id': task.id,
                'title': task.title,
                'due_date': task.due_date.isoformat(),
                'days_until': days_until,
                'urgency': urgency,
                'status': task.status,
                'priority': task.priority,
                'assignee': task.assignee.username if task.assignee else None
            })
        
        # Process overdue tasks
        for task in overdue_tasks:
            days_overdue = (now - task.due_date).days
            alerts.append({
                'type': 'overdue',
                'task_id': task.id,
                'title': task.title,
                'due_date': task.due_date.isoformat(),
                'days_overdue': days_overdue,
                'urgency': 'critical',
                'status': task.status,
                'priority': task.priority,
                'assignee': task.assignee.username if task.assignee else None
            })
        
        # Check project deadline
        if project.end_date:
            project_days_until = (project.end_date - now.date()).days
            if 0 <= project_days_until <= days_ahead:
                alerts.append({
                    'type': 'project_deadline',
                    'project_id': project.id,
                    'project_name': project.name,
                    'due_date': project.end_date.isoformat(),
                    'days_until': project_days_until,
                    'urgency': 'high' if project_days_until <= 3 else 'medium'
                })
        
        # Sort alerts by urgency and date
        urgency_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        alerts.sort(key=lambda a: (
            urgency_order.get(a.get('urgency', 'low'), 3),
            a.get('days_until', 999) if a.get('type') == 'upcoming' else -a.get('days_overdue', 0)
        ))
        
        return {
            'success': True,
            'alerts': alerts,
            'summary': {
                'total_alerts': len(alerts),
                'overdue_count': sum(1 for a in alerts if a['type'] == 'overdue'),
                'upcoming_count': sum(1 for a in alerts if a['type'] == 'upcoming'),
                'critical_count': sum(1 for a in alerts if a.get('urgency') == 'critical'),
                'high_urgency_count': sum(1 for a in alerts if a.get('urgency') == 'high')
            }
        }
    
    def identify_dependencies(self, project_id: int) -> Dict:
        """
        Identify dependencies: Highlight task relationships to avoid bottlenecks.
        
        Args:
            project_id (int): Project ID
            
        Returns:
            Dict: Dependency analysis with relationship mapping and bottleneck identification
        """
        self.log_action("Identifying dependencies", {"project_id": project_id})
        
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return {
                'success': False,
                'error': f'Project with ID {project_id} not found'
            }
        
        tasks = Task.objects.filter(project=project).select_related('assignee').prefetch_related('depends_on', 'dependent_tasks')
        
        dependency_map = []
        critical_path = []
        bottlenecks = []
        
        # Build dependency relationships
        for task in tasks:
            dependencies = task.depends_on.all()
            dependents = task.dependent_tasks.all()
            
            if dependencies.exists() or dependents.exists():
                dependency_info = {
                    'task_id': task.id,
                    'task_title': task.title,
                    'status': task.status,
                    'priority': task.priority,
                    'due_date': task.due_date.isoformat() if task.due_date else None,
                    'assignee': task.assignee.username if task.assignee else None,
                    'depends_on': [],
                    'dependent_tasks': [],
                    'dependency_count': dependencies.count(),
                    'dependent_count': dependents.count(),
                    'is_critical': False,
                    'is_bottleneck': False
                }
                
                # Map dependencies
                for dep in dependencies:
                    dependency_info['depends_on'].append({
                        'id': dep.id,
                        'title': dep.title,
                        'status': dep.status,
                        'due_date': dep.due_date.isoformat() if dep.due_date else None
                    })
                
                # Map dependent tasks
                for dep_task in dependents:
                    dependency_info['dependent_tasks'].append({
                        'id': dep_task.id,
                        'title': dep_task.title,
                        'status': dep_task.status,
                        'due_date': dep_task.due_date.isoformat() if dep_task.due_date else None
                    })
                
                # Identify critical path tasks (tasks with many dependents)
                if dependents.count() >= 3:
                    dependency_info['is_critical'] = True
                    critical_path.append({
                        'task_id': task.id,
                        'task_title': task.title,
                        'dependent_count': dependents.count(),
                        'reason': f'This task blocks {dependents.count()} other tasks'
                    })
                
                # Identify bottlenecks (tasks with many dependencies and many dependents)
                if dependencies.count() >= 2 and dependents.count() >= 2:
                    dependency_info['is_bottleneck'] = True
                    bottlenecks.append({
                        'task_id': task.id,
                        'task_title': task.title,
                        'dependency_count': dependencies.count(),
                        'dependent_count': dependents.count(),
                        'status': task.status,
                        'priority': task.priority,
                        'risk_level': 'high' if task.status in ['todo', 'blocked'] else 'medium',
                        'reason': f'Task has {dependencies.count()} dependencies and blocks {dependents.count()} tasks'
                    })
                
                dependency_map.append(dependency_info)
        
        # Identify potential bottleneck risks
        bottleneck_risks = []
        for task in tasks:
            if task.status in ['todo', 'blocked'] and task.dependent_tasks.count() > 0:
                blocking_count = task.dependent_tasks.filter(status__in=['todo', 'in_progress']).count()
                if blocking_count > 2:
                    bottleneck_risks.append({
                        'task_id': task.id,
                        'task_title': task.title,
                        'status': task.status,
                        'blocking_count': blocking_count,
                        'risk_level': 'high' if task.status == 'blocked' else 'medium',
                        'recommendation': f'Prioritize this task - it\'s blocking {blocking_count} other tasks'
                    })
        
        # Calculate dependency statistics
        total_dependencies = sum(len(d['depends_on']) for d in dependency_map)
        total_dependents = sum(len(d['dependent_tasks']) for d in dependency_map)
        max_dependency_depth = 0
        
        def calculate_depth(task_id, visited=None, depth=0):
            if visited is None:
                visited = set()
            if task_id in visited:
                return depth
            visited.add(task_id)
            
            task_info = next((d for d in dependency_map if d['task_id'] == task_id), None)
            if not task_info:
                return depth
            
            max_child_depth = depth
            for dep in task_info['depends_on']:
                child_depth = calculate_depth(dep['id'], visited.copy(), depth + 1)
                max_child_depth = max(max_child_depth, child_depth)
            
            return max_child_depth
        
        for task_info in dependency_map:
            depth = calculate_depth(task_info['task_id'])
            max_dependency_depth = max(max_dependency_depth, depth)
        
        # Use AI to analyze dependencies and provide insights
        if dependency_map:
            import json
            try:
                deps_prompt = f"""Analyze this project's dependency structure and provide insights.

Project: {project.name}
Total Tasks with Dependencies: {len(dependency_map)}
Critical Path Tasks: {len(critical_path)}
Bottleneck Tasks: {len(bottlenecks)}

Dependency Map (sample):
{json.dumps(dependency_map[:15], indent=2)}

Critical Path:
{json.dumps(critical_path[:10], indent=2)}

Bottlenecks:
{json.dumps(bottlenecks[:10], indent=2)}

Provide analysis:
1. Critical path identification and recommendations
2. Bottleneck mitigation strategies
3. Dependency optimization suggestions
4. Risk assessment for blocking tasks
5. Recommendations for improving project flow

Return JSON:
{{
  "critical_path_analysis": "analysis of critical path and recommendations",
  "bottleneck_strategies": ["strategy1", "strategy2"],
  "optimization_suggestions": ["suggestion1", "suggestion2"],
  "risk_assessment": "overall risk level and key risks",
  "recommendations": "actionable recommendations for improving dependency structure"
}}"""
                
                deps_response = self._call_llm(deps_prompt, self.system_prompt, temperature=0.4, max_tokens=2000)
                
                # Extract JSON
                if "```json" in deps_response:
                    json_start = deps_response.find("```json") + 7
                    json_end = deps_response.find("```", json_start)
                    deps_response = deps_response[json_start:json_end].strip()
                elif "```" in deps_response:
                    json_start = deps_response.find("```") + 3
                    json_end = deps_response.find("```", json_start)
                    if json_end > json_start:
                        deps_response = deps_response[json_start:json_end].strip()
                
                ai_analysis = json.loads(deps_response)
            except Exception as e:
                self.log_action("AI dependency analysis failed", {"error": str(e)})
                ai_analysis = None
        else:
            ai_analysis = None
        
        result = {
            'success': True,
            'dependency_map': dependency_map,
            'critical_path': critical_path,
            'bottlenecks': bottlenecks,
            'bottleneck_risks': bottleneck_risks,
            'summary': {
                'total_tasks_with_dependencies': len(dependency_map),
                'total_dependencies': total_dependencies,
                'total_dependents': total_dependents,
                'critical_path_tasks': len(critical_path),
                'bottleneck_tasks': len(bottlenecks),
                'high_risk_bottlenecks': sum(1 for b in bottlenecks if b['risk_level'] == 'high'),
                'max_dependency_depth': max_dependency_depth,
                'blocking_tasks': len(bottleneck_risks)
            }
        }
        
        if ai_analysis:
            result['ai_insights'] = ai_analysis
        
        return result
    
    def get_shared_view(self, project_id: int) -> Dict:
        """
        Enhance collaboration: Provide a shared view of the project for all stakeholders.
        
        Args:
            project_id (int): Project ID
            
        Returns:
            Dict: Comprehensive project view with tasks, assignments, timelines, and progress
        """
        self.log_action("Generating shared view", {"project_id": project_id})
        
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return {
                'success': False,
                'error': f'Project with ID {project_id} not found'
            }
        
        # Get all project data
        tasks = Task.objects.filter(project=project).select_related('assignee').prefetch_related('depends_on', 'dependent_tasks')
        team_members = project.team_members.select_related('user').all()
        
        # Project overview
        project_overview = {
            'id': project.id,
            'name': project.name,
            'description': project.description,
            'status': project.status,
            'priority': project.priority,
            'start_date': project.start_date.isoformat() if project.start_date else None,
            'end_date': project.end_date.isoformat() if project.end_date else None,
            'owner': project.owner.username,
            'created_at': project.created_at.isoformat(),
            'updated_at': project.updated_at.isoformat()
        }
        
        # Task breakdown by status
        tasks_by_status = {
            'todo': [],
            'in_progress': [],
            'review': [],
            'done': [],
            'blocked': []
        }
        
        for task in tasks:
            task_data = {
                'id': task.id,
                'title': task.title,
                'description': task.description,
                'priority': task.priority,
                'due_date': task.due_date.isoformat() if task.due_date else None,
                'assignee': task.assignee.username if task.assignee else None,
                'assignee_id': task.assignee.id if task.assignee else None,
                'estimated_hours': float(task.estimated_hours) if task.estimated_hours else None,
                'actual_hours': float(task.actual_hours) if task.actual_hours else None,
                'dependencies': [{'id': dep.id, 'title': dep.title} for dep in task.depends_on.all()],
                'dependent_tasks': [{'id': dep.id, 'title': dep.title} for dep in task.dependent_tasks.all()],
                'created_at': task.created_at.isoformat(),
                'updated_at': task.updated_at.isoformat()
            }
            tasks_by_status[task.status].append(task_data)
        
        # Team member workload
        team_workload = []
        for member in team_members:
            member_tasks = tasks.filter(assignee=member.user)
            active_tasks = member_tasks.filter(status__in=['todo', 'in_progress', 'review'])
            completed_tasks = member_tasks.filter(status='done')
            
            team_workload.append({
                'user_id': member.user.id,
                'username': member.user.username,
                'role': member.role,
                'total_tasks': member_tasks.count(),
                'active_tasks': active_tasks.count(),
                'completed_tasks': completed_tasks.count(),
                'tasks': [{
                    'id': t.id,
                    'title': t.title,
                    'status': t.status,
                    'priority': t.priority,
                    'due_date': t.due_date.isoformat() if t.due_date else None
                } for t in active_tasks[:10]]  # Limit to 10 tasks per member
            })
        
        # Also include project owner if not in team
        if project.owner not in [m.user for m in team_members]:
            owner_tasks = tasks.filter(assignee=project.owner)
            active_tasks = owner_tasks.filter(status__in=['todo', 'in_progress', 'review'])
            team_workload.append({
                'user_id': project.owner.id,
                'username': project.owner.username,
                'role': 'owner',
                'total_tasks': owner_tasks.count(),
                'active_tasks': active_tasks.count(),
                'completed_tasks': owner_tasks.filter(status='done').count(),
                'tasks': [{
                    'id': t.id,
                    'title': t.title,
                    'status': t.status,
                    'priority': t.priority,
                    'due_date': t.due_date.isoformat() if t.due_date else None
                } for t in active_tasks[:10]]
            })
        
        # Progress metrics
        total_tasks = tasks.count()
        completed_tasks = tasks.filter(status='done').count()
        in_progress_tasks = tasks.filter(status='in_progress').count()
        blocked_tasks = tasks.filter(status='blocked').count()
        
        # Calculate completion percentage
        completion_percentage = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        # Timeline summary
        tasks_with_dates = tasks.exclude(due_date__isnull=True)
        if tasks_with_dates.exists():
            earliest_due = tasks_with_dates.order_by('due_date').first().due_date
            latest_due = tasks_with_dates.order_by('-due_date').first().due_date
        else:
            earliest_due = None
            latest_due = None
        
        # Priority distribution
        priority_distribution = {
            'high': tasks.filter(priority='high').count(),
            'medium': tasks.filter(priority='medium').count(),
            'low': tasks.filter(priority='low').count()
        }
        
        # Upcoming deadlines (next 7 days)
        now = timezone.now()
        next_week = now + timedelta(days=7)
        upcoming_deadlines = tasks.filter(
            due_date__gte=now,
            due_date__lte=next_week,
            status__in=['todo', 'in_progress', 'review']
        ).order_by('due_date')[:10]
        
        # Use AI to generate insights and recommendations
        import json
        try:
            insights_prompt = f"""Analyze this project's current state and provide actionable insights.

Project: {project.name}
Status: {project.status}
Completion: {round(completion_percentage, 2)}%

Tasks:
- Total: {total_tasks}
- Completed: {completed_tasks}
- In Progress: {in_progress_tasks}
- Blocked: {blocked_tasks}
- Todo: {len(tasks_by_status['todo'])}

Priority Distribution:
- High: {priority_distribution['high']}
- Medium: {priority_distribution['medium']}
- Low: {priority_distribution['low']}

Team Members: {len(team_workload)}
Upcoming Deadlines (next 7 days): {len(upcoming_deadlines)}
Overdue Tasks: {tasks.filter(due_date__lt=now, status__in=['todo', 'in_progress', 'review']).count()}

Provide:
1. Overall project health assessment
2. Key risks and concerns
3. Immediate action items (top 3-5 priorities)
4. Recommendations for improvement
5. Success factors and what's going well

Return JSON:
{{
  "health_assessment": "overall project health (excellent|good|fair|poor) with brief explanation",
  "key_risks": ["risk1", "risk2", "risk3"],
  "action_items": [
    {{
      "priority": "high|medium|low",
      "action": "specific action to take",
      "reason": "why this is important"
    }}
  ],
  "recommendations": ["recommendation1", "recommendation2"],
  "success_factors": ["what's going well"],
  "summary": "brief overall summary and next steps"
}}"""
            
            insights_response = self._call_llm(insights_prompt, self.system_prompt, temperature=0.5, max_tokens=2000)
            
            # Extract JSON
            if "```json" in insights_response:
                json_start = insights_response.find("```json") + 7
                json_end = insights_response.find("```", json_start)
                insights_response = insights_response[json_start:json_end].strip()
            elif "```" in insights_response:
                json_start = insights_response.find("```") + 3
                json_end = insights_response.find("```", json_start)
                if json_end > json_start:
                    insights_response = insights_response[json_start:json_end].strip()
            
            ai_insights = json.loads(insights_response)
        except Exception as e:
            self.log_action("AI insights generation failed", {"error": str(e)})
            ai_insights = None
        
        shared_view = {
            'project': project_overview,
            'tasks': {
                'by_status': tasks_by_status,
                'total': total_tasks,
                'completed': completed_tasks,
                'in_progress': in_progress_tasks,
                'blocked': blocked_tasks,
                'todo': len(tasks_by_status['todo']),
                'completion_percentage': round(completion_percentage, 2)
            },
            'team': {
                'members': team_workload,
                'total_members': len(team_workload)
            },
            'timeline': {
                'earliest_due_date': earliest_due.isoformat() if earliest_due else None,
                'latest_due_date': latest_due.isoformat() if latest_due else None,
                'project_start': project.start_date.isoformat() if project.start_date else None,
                'project_end': project.end_date.isoformat() if project.end_date else None
            },
            'metrics': {
                'priority_distribution': priority_distribution,
                'upcoming_deadlines': [{
                    'id': t.id,
                    'title': t.title,
                    'due_date': t.due_date.isoformat(),
                    'assignee': t.assignee.username if t.assignee else None,
                    'priority': t.priority
                } for t in upcoming_deadlines],
                'overdue_tasks': tasks.filter(
                    due_date__lt=now,
                    status__in=['todo', 'in_progress', 'review']
                ).count()
            },
            'generated_at': timezone.now().isoformat()
        }
        
        if ai_insights:
            shared_view['ai_insights'] = ai_insights
        
        return {
            'success': True,
            'shared_view': shared_view
        }
    
    def process(self, action: str, **kwargs) -> Dict:
        """
        Main processing method for timeline agent - routes actions to appropriate methods.
        
        Args:
            action (str): Action to perform:
                - 'create_timeline': Create project timeline
                - 'generate_gantt': Generate Gantt chart
                - 'track_milestones': Track milestones
                - 'check_deadlines': Check upcoming deadlines
                - 'suggest_adjustments': Suggest timeline adjustments
                - 'identify_conflicts': Identify conflicts
                - 'identify_dependencies': Identify dependencies and bottlenecks
                - 'get_shared_view': Get shared view for collaboration
                - 'calculate_duration': Calculate duration estimates
                - 'manage_phases': Manage project phases
            **kwargs: Action-specific parameters
            
        Returns:
            dict: Processing results
        """
        self.log_action("Processing timeline action", {"action": action})
        
        project_id = kwargs.get('project_id')
        if not project_id:
            return {
                'success': False,
                'error': 'project_id is required'
            }
        
        try:
            if action == 'create_timeline':
                tasks = kwargs.get('tasks', [])
                return self.create_timeline(project_id, tasks)
            
            elif action == 'generate_gantt':
                return self.generate_gantt_chart(project_id)
            
            elif action == 'track_milestones':
                return self.track_milestones(project_id)
            
            elif action == 'check_deadlines':
                days_ahead = kwargs.get('days_ahead', 7)
                return self.check_upcoming_deadlines(project_id, days_ahead)
            
            elif action == 'suggest_adjustments':
                current_progress = kwargs.get('current_progress', {})
                return self.suggest_adjustments(project_id, current_progress)
            
            elif action == 'identify_conflicts':
                return self.identify_conflicts(project_id)
            
            elif action == 'identify_dependencies':
                return self.identify_dependencies(project_id)
            
            elif action == 'get_shared_view':
                return self.get_shared_view(project_id)
            
            elif action == 'calculate_duration':
                tasks = kwargs.get('tasks', [])
                return self.calculate_duration_estimate(tasks)
            
            elif action == 'manage_phases':
                phases = kwargs.get('phases')
                return self.manage_phases(project_id, phases)
            
            else:
                return {
                    'success': False,
                    'error': f'Unknown action: {action}',
                    'available_actions': [
                        'create_timeline', 'generate_gantt', 'track_milestones',
                        'check_deadlines', 'suggest_adjustments', 'identify_conflicts',
                        'identify_dependencies', 'get_shared_view', 'calculate_duration', 'manage_phases'
                    ]
                }
        
        except Exception as e:
            self.log_action("Error processing action", {"action": action, "error": str(e)})
            return {
                'success': False,
                'error': str(e)
            }


"""
Project Timeline / Gantt Agent
Manages project timelines, creates Gantt charts, and tracks project schedules.
"""

from .base_agent import BaseAgent
from .enhancements.timeline_gantt_enhancements import TimelineGanttEnhancements
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
        Create a project timeline from tasks - shows task date ranges, status changes, and completion dates.
        Displays tasks on a calendar timeline graph.
        
        Args:
            project_id (int): Project ID
            tasks (List[Dict]): List of tasks with durations and dependencies
            
        Returns:
            Dict: Timeline data with tasks showing date ranges, status changes, and visual timeline
        """
        self.log_action("Creating timeline", {"project_id": project_id, "tasks_count": len(tasks)})
        
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return {
                'success': False,
                'error': f'Project with ID {project_id} not found'
            }
        
        # Get actual Task objects from database to access all fields including timestamps
        tasks_queryset = Task.objects.filter(project=project).select_related('assignee').prefetch_related('depends_on', 'dependent_tasks', 'activity_logs')
        
        # Get project start date or use earliest task creation date
        project_start = project.start_date or (tasks_queryset.order_by('created_at').first().created_at.date() if tasks_queryset.exists() else timezone.now().date())
        
        timeline_tasks = []
        
        for task in tasks_queryset:
            # Calculate task start and end dates
            task_start, task_end, _ = self._calculate_task_dates(task, project_start)
            
            # Get status change history from activity logs
            status_changes = []
            try:
                from core.models import TaskActivityLog
                status_logs = TaskActivityLog.objects.filter(
                    task=task,
                    action_type='status_changed'
                ).order_by('created_at')
                
                for log in status_logs:
                    status_changes.append({
                        'from_status': log.old_value,
                        'to_status': log.new_value,
                        'changed_at': log.created_at.isoformat(),
                        'changed_by': log.user.username if log.user else None
                    })
            except Exception:
                # Fallback: use created_at and updated_at if activity logs not available
                if task.created_at:
                    status_changes.append({
                        'from_status': None,
                        'to_status': task.status,
                        'changed_at': task.created_at.isoformat(),
                        'changed_by': None
                    })
            
            # Determine task date ranges based on status
            if task.status == 'done' and task.completed_at:
                # Task is completed - show completion date range
                completion_date = task.completed_at.date()
                # Estimate when work started (use created_at or when status changed to in_progress)
                work_start_date = task.created_at.date()
                for change in status_changes:
                    if change.get('to_status') == 'in_progress':
                        try:
                            work_start_date = datetime.fromisoformat(change['changed_at'].replace('Z', '+00:00')).date()
                            break
                        except:
                            pass
                
                task_date_range = {
                    'start_date': work_start_date.isoformat(),
                    'end_date': completion_date.isoformat(),
                    'type': 'completed',
                    'completed_from': work_start_date.isoformat(),
                    'completed_to': completion_date.isoformat()
                }
            elif task.status in ['in_progress', 'review']:
                # Task is in progress - show current date range
                work_start_date = task.created_at.date()
                for change in status_changes:
                    if change.get('to_status') == 'in_progress':
                        try:
                            work_start_date = datetime.fromisoformat(change['changed_at'].replace('Z', '+00:00')).date()
                            break
                        except:
                            pass
                
                # End date is either due_date or calculated end date
                end_date = task.due_date.date() if task.due_date else task_end
                if end_date < work_start_date:
                    end_date = task_end
                
                task_date_range = {
                    'start_date': work_start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'type': 'in_progress',
                    'current_status_since': work_start_date.isoformat()
                }
            else:
                # Task is todo or blocked - show planned date range
                task_date_range = {
                    'start_date': task_start.isoformat(),
                    'end_date': task_end.isoformat(),
                    'type': 'planned',
                    'planned_from': task_start.isoformat(),
                    'planned_to': task_end.isoformat()
                }
            
            # Build task timeline data
            task_timeline = {
                'id': task.id,
                'title': task.title,
                'description': task.description,
                'status': task.status,
                'priority': task.priority,
                'assignee': task.assignee.username if task.assignee else None,
                'assignee_id': task.assignee.id if task.assignee else None,
                'date_range': task_date_range,
                'status_changes': status_changes,
                'created_at': task.created_at.isoformat(),
                'updated_at': task.updated_at.isoformat(),
                'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                'due_date': task.due_date.isoformat() if task.due_date else None,
                'estimated_hours': float(task.estimated_hours) if task.estimated_hours else None,
                'actual_hours': float(task.actual_hours) if task.actual_hours else None,
                'dependencies': [dep.id for dep in task.depends_on.all()],
                'progress': self._calculate_task_progress(task)
            }
            
            timeline_tasks.append(task_timeline)
        
        # Sort tasks by start date
        timeline_tasks.sort(key=lambda t: t['date_range']['start_date'])
        
        # Calculate overall timeline bounds
        if timeline_tasks:
            earliest_start = min(t['date_range']['start_date'] for t in timeline_tasks)
            latest_end = max(t['date_range']['end_date'] for t in timeline_tasks)
        else:
            earliest_start = project_start.isoformat()
            latest_end = project_start.isoformat()
        
        timeline_data = {
            'project_id': project_id,
            'project_name': project.name,
            'project_start_date': project.start_date.isoformat() if project.start_date else None,
            'project_end_date': project.end_date.isoformat() if project.end_date else None,
            'timeline_created_at': timezone.now().isoformat(),
            'timeline_start': earliest_start,
            'timeline_end': latest_end,
            'tasks': timeline_tasks
        }
        
        # Generate Gantt chart data for visualization
        gantt_data = {
            'project_id': project_id,
            'project_name': project.name,
            'project_start': project.start_date.isoformat() if project.start_date else earliest_start,
            'project_end': project.end_date.isoformat() if project.end_date else latest_end,
            'tasks': []
        }
        
        for task_timeline in timeline_tasks:
            gantt_task = {
                'id': task_timeline['id'],
                'title': task_timeline['title'],
                'start_date': task_timeline['date_range']['start_date'],
                'end_date': task_timeline['date_range']['end_date'],
                'status': task_timeline['status'],
                'priority': task_timeline['priority'],
                'assignee': task_timeline['assignee'],
                'progress': task_timeline['progress'],
                'type': task_timeline['date_range']['type']
            }
            gantt_data['tasks'].append(gantt_task)
        
        timeline_data['gantt_data'] = gantt_data
        
        # Generate chart data for visualization
        try:
            chart_data = self._generate_chart_data(gantt_data, tasks_queryset)
            timeline_data['charts'] = chart_data
        except Exception as e:
            self.log_action("Chart generation failed", {"error": str(e)})
        
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
    "reasoning": "DETAILED explanation (4-6 sentences): WHY this task is scheduled at these specific dates, HOW dependencies and constraints influenced the timeline, WHAT factors were considered (dependencies, estimated hours, priority, resource availability), HOW this scheduling affects the overall project timeline, and WHAT should be done to ensure this timeline is met."
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
                'ai_reasoning': ai_reasoning or None  # Include reasoning if available
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
        
        # Generate chart data for visualization
        try:
            chart_data = self._generate_chart_data(gantt_data, tasks_queryset)
            gantt_data['charts'] = chart_data
        except Exception as e:
            self.log_action("Chart generation failed", {"error": str(e)})
        
        # Enhanced: Add risk-based planning
        try:
            risk_buffers = TimelineGanttEnhancements.calculate_risk_buffers(gantt_data['tasks'])
            gantt_data['risk_buffers'] = risk_buffers
            
            # Generate probabilistic timeline
            probabilistic_timeline = TimelineGanttEnhancements.generate_probabilistic_timeline(
                gantt_data['tasks'], iterations=1000
            )
            gantt_data['probabilistic_timeline'] = probabilistic_timeline
            
            # Detect schedule conflicts
            conflicts = TimelineGanttEnhancements.detect_schedule_conflicts(gantt_data['tasks'])
            gantt_data['schedule_conflicts'] = conflicts
        except Exception as e:
            self.log_action("Risk-based planning failed", {"error": str(e)})
        
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
        
        # Generate milestone chart data
        milestone_chart_data = {
            'type': 'pie',
            'title': 'Milestone Status',
            'data': [
                {'name': 'Completed', 'value': completed_milestones, 'color': '#10b981'},
                {'name': 'In Progress', 'value': sum(1 for m in milestones if m['status'] == 'in_progress'), 'color': '#3b82f6'},
                {'name': 'Upcoming', 'value': sum(1 for m in milestones if m['status'] == 'upcoming'), 'color': '#6b7280'},
                {'name': 'Overdue', 'value': overdue_milestones, 'color': '#ef4444'},
            ]
        }
        
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
            },
            'charts': {
                'milestone_status': milestone_chart_data
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
    
    def calculate_duration_estimate(self, tasks: List[Dict], project_id: int = None, team_size: int = None) -> Dict:
        """
        Calculate project duration estimates using AI-powered analysis with team size and parallelization considerations.
        Uses AI for intelligent estimation while maintaining consistency through deterministic base calculations.
        
        Args:
            tasks (List[Dict]): List of tasks with estimated hours and dependencies
            project_id (int): Optional project ID to fetch team size
            team_size (int): Optional team size (number of people working on project)
            
        Returns:
            Dict: Duration estimates with AI reasoning and improvement suggestions
        """
        self.log_action("Calculating duration estimate", {"tasks_count": len(tasks), "project_id": project_id})
        
        if not tasks:
            return {
                'success': False,
                'error': 'No tasks provided for duration estimation'
            }
        
        # Get team size if not provided
        if team_size is None and project_id:
            try:
                from core.models import Project, TeamMember
                project = Project.objects.get(id=project_id)
                # Count unique assignees from tasks
                unique_assignees = set()
                for task in tasks:
                    if task.get('assignee_id'):
                        unique_assignees.add(task.get('assignee_id'))
                # Also count team members
                team_members_count = TeamMember.objects.filter(project=project, removed_at__isnull=True).count()
                team_size = max(len(unique_assignees), team_members_count, 1)  # At least 1 person
            except Exception as e:
                self.log_action("Error getting team size", {"error": str(e)})
                team_size = 1  # Default to 1 if can't determine
        
        if team_size is None or team_size < 1:
            team_size = 1
        
        # Calculate base statistics from task data
        total_estimated_hours = 0
        tasks_with_estimates = 0
        tasks_with_actual = 0
        total_actual_hours = 0
        tasks_with_deps = 0
        dependency_chains = []
        
        for task in tasks:
            estimated = task.get('estimated_hours')
            actual = task.get('actual_hours')
            dependencies = task.get('dependencies', [])
            
            if estimated and estimated > 0:
                total_estimated_hours += float(estimated)
                tasks_with_estimates += 1
            elif actual and actual > 0:
                total_estimated_hours += float(actual)
                total_actual_hours += float(actual)
                tasks_with_actual += 1
            else:
                # Estimate based on priority
                priority = task.get('priority', 'medium')
                if priority == 'high':
                    hours = 12
                elif priority == 'low':
                    hours = 4
                else:
                    hours = 8
                total_estimated_hours += hours
            
            if dependencies and len(dependencies) > 0:
                tasks_with_deps += 1
                dependency_chains.append({
                    'task_id': task.get('id'),
                    'title': task.get('title', '')[:50],
                    'dependencies_count': len(dependencies)
                })
        
        # Calculate parallelization potential
        # Tasks without dependencies can be done in parallel
        parallelizable_tasks = len(tasks) - tasks_with_deps
        max_parallel_tasks = min(team_size, parallelizable_tasks)
        
        # Prepare task summary for AI
        import json
        task_summary = []
        for task in tasks[:50]:  # Limit for token efficiency
            task_summary.append({
                'id': task.get('id'),
                'title': task.get('title', '')[:50],
                'estimated_hours': task.get('estimated_hours'),
                'actual_hours': task.get('actual_hours'),
                'priority': task.get('priority', 'medium'),
                'status': task.get('status', 'todo'),
                'dependencies_count': len(task.get('dependencies', [])),
                'has_due_date': bool(task.get('due_date'))
            })
        
        # Use AI for intelligent estimation with team size and parallelization
        prompt = f"""You are an expert project estimation analyst. Analyze this project and provide accurate, detailed duration estimates.

PROJECT STATISTICS:
- Total Tasks: {len(tasks)}
- Tasks with Estimated Hours: {tasks_with_estimates}
- Tasks with Actual Hours: {tasks_with_actual}
- Total Estimated Hours: {round(total_estimated_hours, 2)}
- Tasks with Dependencies: {tasks_with_deps}
- Team Size: {team_size} people
- Parallelizable Tasks (no dependencies): {parallelizable_tasks}
- Maximum Parallel Tasks: {max_parallel_tasks}

TASK DETAILS:
{json.dumps(task_summary[:30], indent=2)}

CRITICAL CONSIDERATIONS:
1. TEAM SIZE & PARALLELIZATION: With {team_size} people, tasks can be done in parallel. 
   - If 6 people can do a project in 10 days, 12 people can do it in ~5-6 days (accounting for coordination overhead)
   - Not all tasks can be parallelized due to dependencies
   - Coordination overhead: More people = more communication needed (typically 10-20% overhead per additional person beyond optimal team size)
   - Optimal parallelization: Consider which tasks can truly run in parallel vs sequential

2. DEPENDENCIES: {tasks_with_deps} tasks have dependencies, creating sequential bottlenecks
   - Critical path analysis: Longest chain of dependent tasks determines minimum duration
   - Dependency delays can cascade through the project

3. TASK COMPLEXITY: Analyze task titles and priorities to estimate realistic durations
   - High priority tasks often indicate complexity
   - Tasks with actual hours provide historical data

4. REALISTIC ESTIMATION:
   - Base calculation: Total hours / (8 hours/day * team_size * parallelization_factor)
   - Parallelization factor: Account for tasks that can run simultaneously vs sequentially
   - Buffer for dependencies: Add time for dependency-related delays
   - Buffer for coordination: More team members = more coordination needed

CALCULATE AND RETURN JSON:
{{
  "total_estimated_hours": number (sum of all task hours),
  "sequential_hours": number (hours that must be done sequentially due to dependencies),
  "parallelizable_hours": number (hours that can be done in parallel),
  "effective_working_days": {{
    "optimistic": number (best case with optimal parallelization, 15% faster),
    "realistic": number (most likely with realistic parallelization and buffers),
    "pessimistic": number (worst case with delays, 30% slower),
    "expected": number (PERT: (optimistic + 4*realistic + pessimistic) / 6)
  }},
  "calendar_days": {{
    "expected": number (accounting for weekends, 5-day work weeks),
    "weeks": number
  }},
  "team_efficiency": {{
    "current_team_size": {team_size},
    "optimal_team_size": number (suggested optimal team size),
    "parallelization_ratio": number (0-1, how much work can be parallelized),
    "coordination_overhead_percent": number (overhead due to team size)
  }},
  "ai_reasoning": "DETAILED explanation (5-8 sentences): WHY this project will take this estimated time. Explain the key factors: total work hours, team size impact, dependency bottlenecks, parallelization opportunities, coordination overhead, and any other significant factors. Be specific about numbers and calculations.",
  "improvement_suggestions": [
    "Specific suggestion 1 on how to reduce time (e.g., 'Add 3 more developers to parallelize frontend and backend work, reducing timeline by ~40%')",
    "Specific suggestion 2 (e.g., 'Break down Task X into smaller subtasks to enable earlier parallel work')",
    "Specific suggestion 3 (e.g., 'Reduce dependencies by reordering tasks Y and Z')",
    "At least 3-5 concrete, actionable suggestions"
  ],
  "dependency_analysis": {{
    "critical_path_length_days": number (longest dependency chain),
    "bottleneck_tasks": ["task title 1", "task title 2"],
    "dependency_impact_percent": number (how much dependencies slow down the project)
  }}
}}"""
        
        try:
            # Use temperature=0 for consistency (same input = same output)
            response = self._call_llm(prompt, self.system_prompt, temperature=0, max_tokens=2000)
            
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
        
        # Fallback calculations if AI fails
        if not ai_estimates:
            # Base calculation
            base_working_days = total_estimated_hours / (8.0 * team_size)
            
            # Account for parallelization (not all tasks can be parallelized)
            parallelization_factor = 0.6 if team_size > 1 else 1.0  # 60% parallelization with team
            effective_days = base_working_days / parallelization_factor
            
            # Dependency impact
            dependency_multiplier = 1.0 + (tasks_with_deps * 0.1 / max(1, len(tasks)))
            adjusted_days = effective_days * dependency_multiplier
            
            optimistic_days = adjusted_days * 0.85
            realistic_days = adjusted_days * 1.20
            pessimistic_days = adjusted_days * 1.35
            expected_days = (optimistic_days + (4 * realistic_days) + pessimistic_days) / 6.0
            
            calendar_weeks = expected_days / 5.0
            calendar_days = calendar_weeks * 7.0
            
            ai_estimates = {
                'total_estimated_hours': round(total_estimated_hours, 2),
                'effective_working_days': {
                    'optimistic': round(optimistic_days, 1),
                    'realistic': round(realistic_days, 1),
                    'pessimistic': round(pessimistic_days, 1),
                    'expected': round(expected_days, 1)
                },
                'calendar_days': {
                    'expected': round(calendar_days, 1),
                    'weeks': round(calendar_weeks, 1)
                },
                'team_efficiency': {
                    'current_team_size': team_size,
                    'optimal_team_size': team_size,
                    'parallelization_ratio': parallelization_factor,
                    'coordination_overhead_percent': max(0, (team_size - 1) * 5)
                },
                'ai_reasoning': f'Fallback calculation: {total_estimated_hours} total hours divided by {team_size} team members with {parallelization_factor*100}% parallelization efficiency. Includes dependency buffers.',
                'improvement_suggestions': [
                    'Add more team members to increase parallelization',
                    'Reduce task dependencies to enable more parallel work',
                    'Break down large tasks into smaller, parallelizable subtasks'
                ],
                'dependency_analysis': {
                    'critical_path_length_days': round(realistic_days, 1),
                    'bottleneck_tasks': [],
                    'dependency_impact_percent': round((dependency_multiplier - 1) * 100, 1)
                }
            }
        
        # Get actual span if tasks have due dates
        tasks_with_dates = [t for t in tasks if t.get('due_date')]
        actual_span_days = None
        if tasks_with_dates:
            try:
                dates = []
                for t in tasks_with_dates:
                    due_date = t.get('due_date')
                    if due_date:
                        if isinstance(due_date, str):
                            dates.append(datetime.fromisoformat(due_date.replace('Z', '+00:00')))
                        else:
                            dates.append(due_date)
                if dates:
                    earliest_date = min(dates)
                    latest_date = max(dates)
                    actual_span_days = (latest_date - earliest_date).days + 1
            except Exception as e:
                self.log_action("Error calculating actual span", {"error": str(e)})
            actual_span_days = None
        
        # Build estimates dictionary
        estimates = {
            'total_tasks': len(tasks),
            'tasks_with_estimated_hours': tasks_with_estimates,
            'tasks_with_actual_hours': tasks_with_actual,
            'total_estimated_hours': round(ai_estimates.get('total_estimated_hours', total_estimated_hours), 2),
            'working_days': ai_estimates.get('effective_working_days', {
                'optimistic': 0,
                'realistic': 0,
                'pessimistic': 0,
                'expected': 0
            }),
            'calendar_days': ai_estimates.get('calendar_days', {
                'expected': 0,
                'weeks': 0
            }),
            'team_efficiency': ai_estimates.get('team_efficiency', {
                'current_team_size': team_size,
                'optimal_team_size': team_size,
                'parallelization_ratio': 0.6,
                'coordination_overhead_percent': 0
            }),
            'tasks_with_dependencies': tasks_with_deps,
            'actual_span_days': actual_span_days,
            'dependency_analysis': ai_estimates.get('dependency_analysis', {})
        }
        
        # Build recommendations with AI insights
        recommendations = {
            'suggested_deadline_days': round(estimates['working_days']['expected'] + 2, 1),
            'suggested_deadline_weeks': round((estimates['working_days']['expected'] + 2) / 5.0, 1),
            'confidence_level': 'high' if tasks_with_estimates > len(tasks) * 0.7 else ('medium' if tasks_with_estimates > len(tasks) * 0.3 else 'low'),
            'ai_reasoning': ai_estimates.get('ai_reasoning', 'AI analysis unavailable'),
            'improvement_suggestions': ai_estimates.get('improvement_suggestions', [
                'Add more team members to increase parallelization',
                'Reduce task dependencies',
                'Break down large tasks'
            ]),
            'key_risks': []
        }
        
        if tasks_with_estimates < len(tasks) * 0.5:
            recommendations['key_risks'].append('Many tasks lack time estimates')
        if tasks_with_deps > len(tasks) * 0.4:
            recommendations['key_risks'].append('High dependency count may cause delays')
        if team_size < 3 and len(tasks) > 10:
            recommendations['key_risks'].append('Small team size may slow down project with many tasks')
        
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
        
        Shows:
        1. Tasks that are not completed and have less than 20% of total time remaining
        2. Tasks that have passed their deadline and are not completed
        
        Args:
            project_id (int): Project ID
            days_ahead (int): Number of days to look ahead (not used in new logic, kept for compatibility)
            
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
        alerts = []
        
        # Get all tasks that are not completed and have a due_date
        incomplete_tasks = Task.objects.filter(
            project=project,
            due_date__isnull=False,
            status__in=['todo', 'in_progress', 'review', 'blocked']
        ).select_related('assignee').order_by('due_date')
        
        for task in incomplete_tasks:
            if not task.due_date:
                continue
                
            # Convert due_date to datetime for comparison if it's a date
            if isinstance(task.due_date, date_type):
                task_due_datetime = datetime.combine(task.due_date, datetime.min.time())
                task_due_datetime = timezone.make_aware(task_due_datetime)
            else:
                task_due_datetime = task.due_date
            
            # Check if task is overdue (deadline has passed)
            is_overdue = task_due_datetime < now
            
            if is_overdue:
                # Task is overdue - show it
                days_overdue = (now - task_due_datetime).days
                alerts.append({
                    'type': 'overdue',
                    'task_id': task.id,
                    'task_title': task.title,
                    'title': task.title,
                    'due_date': task_due_datetime.isoformat(),
                    'days_overdue': days_overdue,
                    'urgency': 'critical',
                    'status': task.status,
                    'priority': task.priority,
                    'assignee': task.assignee.username if task.assignee else None,
                    'assignee_name': task.assignee.username if task.assignee else 'Unassigned'
                })
            else:
                # Task is not overdue - check if less than 20% time remaining
                # Calculate total time: from task start (created_at or project start) to due_date
                task_start = None
                if task.created_at:
                    task_start = task.created_at
                elif project.start_date:
                    task_start = datetime.combine(project.start_date, datetime.min.time())
                    if timezone.is_naive(task_start):
                        task_start = timezone.make_aware(task_start)
                else:
                    # Fallback: use task creation date or project creation date
                    task_start = now - timedelta(days=30)  # Default to 30 days ago if no start date
                    if timezone.is_naive(task_start):
                        task_start = timezone.make_aware(task_start)
                
                if isinstance(task_start, date_type):
                    task_start = datetime.combine(task_start, datetime.min.time())
                    if timezone.is_naive(task_start):
                        task_start = timezone.make_aware(task_start)
                
                # Calculate total time duration
                total_time_delta = task_due_datetime - task_start
                total_time_days = total_time_delta.total_seconds() / (24 * 3600)
                
                # Calculate remaining time
                remaining_time_delta = task_due_datetime - now
                remaining_time_days = remaining_time_delta.total_seconds() / (24 * 3600)
                
                # Check if less than 20% of total time is remaining
                if total_time_days > 0:
                    remaining_percentage = (remaining_time_days / total_time_days) * 100
                    
                    if remaining_percentage < 20:
                        # Less than 20% time remaining - show this task
                        days_until = remaining_time_days
                        urgency = 'critical' if remaining_percentage < 5 else ('high' if remaining_percentage < 10 else 'medium')
                        
            alerts.append({
                            'type': 'upcoming',
                'task_id': task.id,
                            'task_title': task.title,
                'title': task.title,
                            'due_date': task_due_datetime.isoformat(),
                            'days_until': int(days_until) if days_until > 0 else 0,
                            'urgency': urgency,
                'status': task.status,
                'priority': task.priority,
                            'assignee': task.assignee.username if task.assignee else None,
                            'assignee_name': task.assignee.username if task.assignee else 'Unassigned',
                            'remaining_percentage': round(remaining_percentage, 1)
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
    
    def _generate_chart_data(self, gantt_data: Dict, tasks_queryset) -> Dict:
        """
        Generate chart data structures for visualization.
        
        Args:
            gantt_data (Dict): Gantt chart data with tasks
            tasks_queryset: QuerySet of tasks
            
        Returns:
            Dict: Chart data for various visualizations
        """
        charts = {}
        
        # 1. Task Status Distribution (Pie Chart)
        status_counts = {}
        for task in gantt_data.get('tasks', []):
            status = task.get('status', 'todo')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        charts['status_distribution'] = {
            'type': 'pie',
            'title': 'Task Status Distribution',
            'data': [
                {'name': 'Done', 'value': status_counts.get('done', 0), 'color': '#10b981'},
                {'name': 'In Progress', 'value': status_counts.get('in_progress', 0), 'color': '#3b82f6'},
                {'name': 'Review', 'value': status_counts.get('review', 0), 'color': '#f59e0b'},
                {'name': 'Blocked', 'value': status_counts.get('blocked', 0), 'color': '#ef4444'},
                {'name': 'To Do', 'value': status_counts.get('todo', 0), 'color': '#6b7280'},
            ]
        }
        
        # 2. Priority Distribution (Bar Chart)
        priority_counts = {}
        for task in gantt_data.get('tasks', []):
            priority = task.get('priority', 'medium')
            priority_counts[priority] = priority_counts.get(priority, 0) + 1
        
        charts['priority_distribution'] = {
            'type': 'bar',
            'title': 'Task Priority Distribution',
            'xAxis': 'Priority',
            'yAxis': 'Number of Tasks',
            'data': [
                {'name': 'High', 'value': priority_counts.get('high', 0), 'color': '#ef4444'},
                {'name': 'Medium', 'value': priority_counts.get('medium', 0), 'color': '#f59e0b'},
                {'name': 'Low', 'value': priority_counts.get('low', 0), 'color': '#10b981'},
            ]
        }
        
        # 3. Progress Over Time (Line Chart) - Burndown
        if gantt_data.get('tasks'):
            # Group tasks by week
            from collections import defaultdict
            weekly_progress = defaultdict(lambda: {'completed': 0, 'total': 0})
            
            for task in gantt_data['tasks']:
                start_date = datetime.strptime(task['start_date'], '%Y-%m-%d').date()
                # Get week number
                week_key = f"{start_date.isocalendar()[0]}-W{start_date.isocalendar()[1]:02d}"
                weekly_progress[week_key]['total'] += 1
                if task.get('status') == 'done':
                    weekly_progress[week_key]['completed'] += 1
            
            charts['burndown'] = {
                'type': 'line',
                'title': 'Project Burndown Chart',
                'xAxis': 'Week',
                'yAxis': 'Tasks',
                'data': [
                    {
                        'week': week,
                        'completed': data['completed'],
                        'total': data['total'],
                        'remaining': data['total'] - data['completed']
                    }
                    for week, data in sorted(weekly_progress.items())
                ]
            }
        
        # 4. Resource Utilization (Bar Chart)
        assignee_counts = {}
        assignee_hours = {}
        for task in gantt_data.get('tasks', []):
            assignee = task.get('assignee', 'Unassigned')
            assignee_counts[assignee] = assignee_counts.get(assignee, 0) + 1
            hours = task.get('estimated_hours', 0) or 0
            assignee_hours[assignee] = assignee_hours.get(assignee, 0) + hours
        
        charts['resource_utilization'] = {
            'type': 'bar',
            'title': 'Resource Utilization',
            'xAxis': 'Team Member',
            'yAxis': 'Hours',
            'data': [
                {
                    'name': assignee,
                    'tasks': assignee_counts.get(assignee, 0),
                    'hours': round(assignee_hours.get(assignee, 0), 1)
                }
                for assignee in sorted(set(list(assignee_counts.keys()) + list(assignee_hours.keys())))
            ]
        }
        
        # 5. Timeline Visualization Data (for Gantt Chart)
        charts['gantt_timeline'] = {
            'type': 'gantt',
            'title': 'Project Timeline',
            'startDate': gantt_data.get('timeline', {}).get('start'),
            'endDate': gantt_data.get('timeline', {}).get('end'),
            'tasks': [
                {
                    'id': task['id'],
                    'name': task['title'],
                    'start': task['start_date'],
                    'end': task['end_date'],
                    'progress': task.get('progress', 0),
                    'status': task.get('status', 'todo'),
                    'priority': task.get('priority', 'medium'),
                    'assignee': task.get('assignee', 'Unassigned'),
                    'isCritical': task.get('id') in [cp['task_id'] for cp in gantt_data.get('critical_path', [])]
                }
                for task in gantt_data.get('tasks', [])
            ]
        }
        
        # 6. Completion Rate (Progress Chart)
        total_tasks = len(gantt_data.get('tasks', []))
        completed_tasks = status_counts.get('done', 0)
        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        charts['completion_rate'] = {
            'type': 'progress',
            'title': 'Project Completion',
            'percentage': round(completion_rate, 1),
            'completed': completed_tasks,
            'total': total_tasks,
            'inProgress': status_counts.get('in_progress', 0),
            'todo': status_counts.get('todo', 0)
        }
        
        return charts
    
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
    
    def optimize_schedule(self, project_id: int, resources: List[Dict] = None) -> Dict:
        """
        Optimize schedule with resource constraints.
        
        Args:
            project_id (int): Project ID
            resources (List[Dict]): Available resources/users
            
        Returns:
            Dict: Optimized schedule with improvements
        """
        self.log_action("Optimizing schedule", {"project_id": project_id})
        
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return {
                'success': False,
                'error': f'Project with ID {project_id} not found'
            }
        
        tasks = Task.objects.filter(project=project).select_related('assignee')
        
        tasks_data = [{
            'id': t.id,
            'title': t.title,
            'estimated_hours': float(t.estimated_hours) if t.estimated_hours else None,
            'assignee_id': t.assignee.id if t.assignee else None,
            'priority': t.priority,
            'status': t.status,
            'dependencies': [dep.id for dep in t.depends_on.all()],
            'due_date': t.due_date.isoformat() if t.due_date else None,
        } for t in tasks]
        
        optimization_result = TimelineGanttEnhancements.optimize_schedule(tasks_data, resources)
        
        return {
            'success': True,
            'optimization': optimization_result,
            'project_id': project_id,
            'project_name': project.name,
        }
    
    def coordinate_multi_project_schedules(self, project_ids: List[int]) -> Dict:
        """
        Coordinate schedules across multiple projects (Phase 2 feature).
        
        Args:
            project_ids (List[int]): List of project IDs to coordinate
            
        Returns:
            Dict: Coordinated schedule with resource allocation and conflicts
        """
        self.log_action("Coordinating multi-project schedules", {"project_ids": project_ids})
        
        projects_data = []
        for project_id in project_ids:
            try:
                project = Project.objects.get(id=project_id)
                tasks = Task.objects.filter(project=project).select_related('assignee')
                
                tasks_data = [{
                    'id': t.id,
                    'title': t.title,
                    'estimated_hours': float(t.estimated_hours) if t.estimated_hours else None,
                    'assignee_id': t.assignee.id if t.assignee else None,
                    'priority': t.priority,
                    'status': t.status,
                    'dependencies': [dep.id for dep in t.depends_on.all()],
                    'due_date': t.due_date.isoformat() if t.due_date else None,
                } for t in tasks]
                
                projects_data.append({
                    'id': project.id,
                    'name': project.name,
                    'tasks': tasks_data
                })
            except Project.DoesNotExist:
                continue
        
        coordination_result = TimelineGanttEnhancements.coordinate_multi_project_schedules(projects_data)
        
        return {
            'success': True,
            'coordination': coordination_result,
            'projects_analyzed': len(projects_data)
        }
    
    def generate_what_if_scenarios(self, project_id: int, scenarios: List[str] = None) -> Dict:
        """
        Generate what-if scenario timelines (Phase 2 feature).
        
        Args:
            project_id (int): Project ID
            scenarios (List[str]): Optional list of scenario names
            
        Returns:
            Dict: Multiple scenario timelines
        """
        self.log_action("Generating what-if scenarios", {"project_id": project_id})
        
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return {
                'success': False,
                'error': f'Project with ID {project_id} not found'
            }
        
        tasks = Task.objects.filter(project=project).select_related('assignee')
        
        tasks_data = [{
            'id': t.id,
            'title': t.title,
            'estimated_hours': float(t.estimated_hours) if t.estimated_hours else None,
            'priority': t.priority,
            'status': t.status,
            'dependencies': [dep.id for dep in t.depends_on.all()],
            'due_date': t.due_date.isoformat() if t.due_date else None,
        } for t in tasks]
        
        scenarios_result = TimelineGanttEnhancements.generate_what_if_scenarios(tasks_data, scenarios)
        
        return {
            'success': True,
            'scenarios': scenarios_result,
            'project_id': project_id,
            'project_name': project.name,
        }
    
    def optimize_schedule_genetic(self, project_id: int, generations: int = 50, population_size: int = 20) -> Dict:
        """
        Optimize schedule using genetic algorithm (Phase 2 feature).
        
        Args:
            project_id (int): Project ID
            generations (int): Number of generations
            population_size (int): Population size
            
        Returns:
            Dict: Optimized schedule
        """
        self.log_action("Optimizing schedule with genetic algorithm", {"project_id": project_id})
        
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return {
                'success': False,
                'error': f'Project with ID {project_id} not found'
            }
        
        tasks = Task.objects.filter(project=project).select_related('assignee')
        
        tasks_data = [{
            'id': t.id,
            'title': t.title,
            'estimated_hours': float(t.estimated_hours) if t.estimated_hours else None,
            'priority': t.priority,
            'status': t.status,
            'dependencies': [dep.id for dep in t.depends_on.all()],
            'due_date': t.due_date.isoformat() if t.due_date else None,
        } for t in tasks]
        
        optimization_result = TimelineGanttEnhancements.optimize_schedule_genetic_algorithm(
            tasks_data, generations=generations, population_size=population_size
        )
        
        return {
            'success': True,
            'optimization': optimization_result,
            'project_id': project_id,
            'project_name': project.name,
        }
    
    def optimize_schedule_simulated_annealing(self, project_id: int, iterations: int = 1000) -> Dict:
        """
        Optimize schedule using simulated annealing (Phase 2 feature).
        
        Args:
            project_id (int): Project ID
            iterations (int): Number of iterations
            
        Returns:
            Dict: Optimized schedule
        """
        self.log_action("Optimizing schedule with simulated annealing", {"project_id": project_id})
        
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return {
                'success': False,
                'error': f'Project with ID {project_id} not found'
            }
        
        tasks = Task.objects.filter(project=project).select_related('assignee')
        
        tasks_data = [{
            'id': t.id,
            'title': t.title,
            'estimated_hours': float(t.estimated_hours) if t.estimated_hours else None,
            'priority': t.priority,
            'status': t.status,
            'dependencies': [dep.id for dep in t.depends_on.all()],
            'due_date': t.due_date.isoformat() if t.due_date else None,
        } for t in tasks]
        
        optimization_result = TimelineGanttEnhancements.optimize_schedule_simulated_annealing(
            tasks_data, iterations=iterations
        )
        
        return {
            'success': True,
            'optimization': optimization_result,
            'project_id': project_id,
            'project_name': project.name,
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
                project_id = kwargs.get('project_id')
                team_size = kwargs.get('team_size')
                return self.calculate_duration_estimate(tasks, project_id=project_id, team_size=team_size)
            
            elif action == 'manage_phases':
                phases = kwargs.get('phases')
                return self.manage_phases(project_id, phases)
            
            elif action == 'optimize_schedule':
                resources = kwargs.get('resources', [])
                return self.optimize_schedule(project_id, resources)
            
            elif action == 'coordinate_multi_project':
                project_ids = kwargs.get('project_ids', [project_id])
                return self.coordinate_multi_project_schedules(project_ids)
            
            elif action == 'what_if_scenarios':
                scenarios = kwargs.get('scenarios')
                return self.generate_what_if_scenarios(project_id, scenarios)
            
            elif action == 'optimize_genetic':
                generations = kwargs.get('generations', 50)
                population_size = kwargs.get('population_size', 20)
                return self.optimize_schedule_genetic(project_id, generations, population_size)
            
            elif action == 'optimize_simulated_annealing':
                iterations = kwargs.get('iterations', 1000)
                return self.optimize_schedule_simulated_annealing(project_id, iterations)
            
            else:
                return {
                    'success': False,
                    'error': f'Unknown action: {action}',
                    'available_actions': [
                        'create_timeline', 'generate_gantt', 'track_milestones',
                        'check_deadlines', 'suggest_adjustments', 'identify_conflicts',
                        'identify_dependencies', 'get_shared_view', 'calculate_duration', 
                        'manage_phases', 'optimize_schedule', 'coordinate_multi_project',
                        'what_if_scenarios', 'optimize_genetic', 'optimize_simulated_annealing'
                    ]
                }
        
        except Exception as e:
            self.log_action("Error processing action", {"action": action, "error": str(e)})
            return {
                'success': False,
                'error': str(e)
            }


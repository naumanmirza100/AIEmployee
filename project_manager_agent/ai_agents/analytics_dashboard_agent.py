"""
Analytics & Dashboard Agent
Provides insights, analytics, and visualizations for project performance.
"""

from .base_agent import BaseAgent
from .enhancements.chart_generation import ChartGenerator
from core.models import Project, Task
from typing import Dict, List, Optional
from django.utils import timezone
from datetime import datetime, timedelta
import json


class AnalyticsDashboardAgent(BaseAgent):
    """
    Agent responsible for:
    - Generate project performance metrics
    - Create visual dashboards and charts
    - Track project progress and completion rates
    - Analyze team productivity and workload
    - Identify project risks and issues
    - Generate status reports
    - Calculate project health scores
    - Provide predictive analytics
    """

    def __init__(self):
        super().__init__()
        self.system_prompt = """You are an Analytics & Dashboard Agent for a project management system.
Your role is to analyze project data, generate insights, and create visualizations.
You provide clear, actionable metrics and identify trends and patterns.
Always back up your analysis with data and provide specific recommendations."""

    def generate_metrics(self, project_id: int, company_user=None) -> Dict:
        """Generate comprehensive project performance metrics."""
        self.log_action("Generating metrics", {"project_id": project_id})

        try:
            filters = {"id": project_id}
            if company_user:
                filters["created_by_company_user"] = company_user
            project = Project.objects.get(**filters)
        except Project.DoesNotExist:
            return {"success": False, "error": f"Project with ID {project_id} not found"}

        tasks = Task.objects.filter(project=project).select_related('assignee')
        tasks_data = self._tasks_to_data(tasks)
        total = len(tasks_data)

        if total == 0:
            return {
                "success": True,
                "project_name": project.name,
                "metrics": {"total_tasks": 0, "message": "No tasks in this project"},
            }

        completed = sum(1 for t in tasks_data if t['status'] in ['done', 'completed'])
        in_progress = sum(1 for t in tasks_data if t['status'] == 'in_progress')
        todo = sum(1 for t in tasks_data if t['status'] == 'todo')
        blocked = sum(1 for t in tasks_data if t['status'] == 'blocked')
        review = sum(1 for t in tasks_data if t['status'] == 'review')

        now = timezone.now().date()
        overdue = sum(1 for t in tasks_data
                      if t.get('due_date') and t['status'] not in ['done', 'completed']
                      and self._parse_date(t['due_date']) and self._parse_date(t['due_date']) < now)

        # Priority breakdown
        high_priority = sum(1 for t in tasks_data if t.get('priority') == 'high')
        medium_priority = sum(1 for t in tasks_data if t.get('priority') == 'medium')
        low_priority = sum(1 for t in tasks_data if t.get('priority') == 'low')

        # Assignee workload
        assignee_workload = {}
        for t in tasks_data:
            assignee = t.get('assignee_name') or 'Unassigned'
            if assignee not in assignee_workload:
                assignee_workload[assignee] = {"total": 0, "completed": 0, "active": 0}
            assignee_workload[assignee]["total"] += 1
            if t['status'] in ['done', 'completed']:
                assignee_workload[assignee]["completed"] += 1
            elif t['status'] not in ['blocked']:
                assignee_workload[assignee]["active"] += 1

        completion_rate = (completed / total * 100) if total > 0 else 0
        health_score = self._calculate_health_score_from_metrics(completion_rate, overdue, blocked, total)

        return {
            "success": True,
            "project_id": project_id,
            "project_name": project.name,
            "project_status": project.status,
            "metrics": {
                "total_tasks": total,
                "completed_tasks": completed,
                "in_progress_tasks": in_progress,
                "todo_tasks": todo,
                "blocked_tasks": blocked,
                "review_tasks": review,
                "overdue_tasks": overdue,
                "completion_rate": round(completion_rate, 1),
                "health_score": health_score,
                "priority_breakdown": {
                    "high": high_priority,
                    "medium": medium_priority,
                    "low": low_priority,
                },
                "assignee_workload": assignee_workload,
            },
            "generated_at": timezone.now().isoformat(),
        }

    def create_dashboard(self, project_id: int, metrics: Optional[List[str]] = None, company_user=None) -> Dict:
        """Create a visual dashboard with charts and visualizations."""
        self.log_action("Creating dashboard", {"project_id": project_id})

        try:
            filters = {"id": project_id}
            if company_user:
                filters["created_by_company_user"] = company_user
            project = Project.objects.get(**filters)
        except Project.DoesNotExist:
            return {"success": False, "error": f"Project with ID {project_id} not found"}

        tasks = Task.objects.filter(project=project).select_related('assignee')
        tasks_data = self._tasks_to_data(tasks)

        # Generate all charts
        charts = {}
        charts['status_distribution'] = ChartGenerator.generate_status_distribution_chart(tasks_data)
        charts['priority_distribution'] = ChartGenerator.generate_priority_distribution_chart(tasks_data)

        if any('priority_score' in task for task in tasks_data):
            charts['priority_scores'] = ChartGenerator.generate_priority_score_chart(tasks_data)

        # Calculate metrics
        total = len(tasks_data)
        completed = sum(1 for t in tasks_data if t['status'] in ['done', 'completed'])
        in_progress = sum(1 for t in tasks_data if t['status'] == 'in_progress')
        blocked = sum(1 for t in tasks_data if t['status'] == 'blocked')
        completion_rate = (completed / total * 100) if total > 0 else 0

        now = timezone.now().date()
        overdue = sum(1 for t in tasks_data
                      if t.get('due_date') and t['status'] not in ['done', 'completed']
                      and self._parse_date(t['due_date']) and self._parse_date(t['due_date']) < now)

        return {
            'success': True,
            'project_id': project_id,
            'project_name': project.name,
            'metrics': {
                'total_tasks': total,
                'completed_tasks': completed,
                'in_progress_tasks': in_progress,
                'blocked_tasks': blocked,
                'overdue_tasks': overdue,
                'completion_rate': round(completion_rate, 2),
                'health_score': self._calculate_health_score_from_metrics(
                    completion_rate, overdue, blocked, total
                )
            },
            'charts': charts,
            'generated_at': timezone.now().isoformat()
        }

    def track_progress(self, project_id: int, company_user=None) -> Dict:
        """Track project progress and completion rates over time."""
        self.log_action("Tracking progress", {"project_id": project_id})

        try:
            filters = {"id": project_id}
            if company_user:
                filters["created_by_company_user"] = company_user
            project = Project.objects.get(**filters)
        except Project.DoesNotExist:
            return {"success": False, "error": f"Project with ID {project_id} not found"}

        tasks = Task.objects.filter(project=project).select_related('assignee')
        tasks_data = self._tasks_to_data(tasks)
        total = len(tasks_data)

        if total == 0:
            return {"success": True, "project_name": project.name, "progress": 0, "message": "No tasks"}

        completed = sum(1 for t in tasks_data if t['status'] in ['done', 'completed'])
        progress = round((completed / total) * 100, 1)

        # Status breakdown for progress bar
        status_counts = {}
        for t in tasks_data:
            s = t.get('status', 'unknown')
            status_counts[s] = status_counts.get(s, 0) + 1

        # Upcoming deadlines
        now = timezone.now().date()
        upcoming = []
        for t in tasks_data:
            if t.get('due_date') and t['status'] not in ['done', 'completed']:
                due = self._parse_date(t['due_date'])
                if due and due >= now and (due - now).days <= 7:
                    upcoming.append({
                        "title": t.get('title'),
                        "due_date": t['due_date'],
                        "days_left": (due - now).days,
                        "priority": t.get('priority'),
                    })
        upcoming.sort(key=lambda x: x.get('days_left', 999))

        return {
            "success": True,
            "project_name": project.name,
            "progress_percent": progress,
            "total_tasks": total,
            "completed_tasks": completed,
            "status_breakdown": status_counts,
            "upcoming_deadlines": upcoming[:10],
            "on_track": progress >= 50 or (project.deadline and project.deadline > now),
        }

    def analyze_productivity(self, project_id: int, company_user=None) -> Dict:
        """Analyze team productivity and workload for a project."""
        self.log_action("Analyzing productivity", {"project_id": project_id})

        try:
            filters = {"id": project_id}
            if company_user:
                filters["created_by_company_user"] = company_user
            project = Project.objects.get(**filters)
        except Project.DoesNotExist:
            return {"success": False, "error": f"Project with ID {project_id} not found"}

        tasks = Task.objects.filter(project=project).select_related('assignee')
        tasks_data = self._tasks_to_data(tasks)

        # Build per-member stats
        member_stats = {}
        for t in tasks_data:
            name = t.get('assignee_name') or 'Unassigned'
            if name not in member_stats:
                member_stats[name] = {
                    "total": 0, "completed": 0, "in_progress": 0,
                    "blocked": 0, "overdue": 0, "high_priority": 0
                }
            stats = member_stats[name]
            stats["total"] += 1
            if t['status'] in ['done', 'completed']:
                stats["completed"] += 1
            elif t['status'] == 'in_progress':
                stats["in_progress"] += 1
            elif t['status'] == 'blocked':
                stats["blocked"] += 1
            if t.get('priority') == 'high':
                stats["high_priority"] += 1

            now = timezone.now().date()
            if t.get('due_date') and t['status'] not in ['done', 'completed']:
                due = self._parse_date(t['due_date'])
                if due and due < now:
                    stats["overdue"] += 1

        # Calculate completion rates per member
        for name, stats in member_stats.items():
            stats["completion_rate"] = round(
                (stats["completed"] / stats["total"] * 100) if stats["total"] > 0 else 0, 1
            )

        return {
            "success": True,
            "project_name": project.name,
            "team_productivity": member_stats,
            "total_members": len([m for m in member_stats if m != 'Unassigned']),
            "unassigned_tasks": member_stats.get('Unassigned', {}).get('total', 0),
        }

    def identify_risks(self, project_id: int, company_user=None) -> Dict:
        """Identify project risks based on task data."""
        self.log_action("Identifying risks", {"project_id": project_id})

        try:
            filters = {"id": project_id}
            if company_user:
                filters["created_by_company_user"] = company_user
            project = Project.objects.get(**filters)
        except Project.DoesNotExist:
            return {"success": False, "error": f"Project with ID {project_id} not found"}

        tasks = Task.objects.filter(project=project).select_related('assignee')
        tasks_data = self._tasks_to_data(tasks)
        total = len(tasks_data)
        now = timezone.now().date()
        risks = []

        if total == 0:
            return {"success": True, "risks": [{"risk": "No tasks created yet", "severity": "medium"}]}

        # Overdue tasks
        overdue = [t for t in tasks_data
                   if t.get('due_date') and t['status'] not in ['done', 'completed']
                   and self._parse_date(t['due_date']) and self._parse_date(t['due_date']) < now]
        if overdue:
            risks.append({
                "risk": f"{len(overdue)} overdue task(s)",
                "severity": "high" if len(overdue) > 3 else "medium",
                "details": [t.get('title') for t in overdue[:5]]
            })

        # Blocked tasks
        blocked = [t for t in tasks_data if t['status'] == 'blocked']
        if blocked:
            risks.append({
                "risk": f"{len(blocked)} blocked task(s)",
                "severity": "high",
                "details": [t.get('title') for t in blocked[:5]]
            })

        # Unassigned high-priority tasks
        unassigned_high = [t for t in tasks_data
                          if not t.get('assignee_name') and t.get('priority') == 'high'
                          and t['status'] not in ['done', 'completed']]
        if unassigned_high:
            risks.append({
                "risk": f"{len(unassigned_high)} unassigned high-priority task(s)",
                "severity": "high",
                "details": [t.get('title') for t in unassigned_high[:5]]
            })

        # Low completion rate
        completed = sum(1 for t in tasks_data if t['status'] in ['done', 'completed'])
        rate = (completed / total * 100) if total > 0 else 0
        if rate < 25 and total > 5:
            risks.append({
                "risk": f"Low completion rate ({rate:.0f}%)",
                "severity": "medium",
            })

        # Workload imbalance
        assignee_counts = {}
        for t in tasks_data:
            if t.get('assignee_name') and t['status'] not in ['done', 'completed']:
                name = t['assignee_name']
                assignee_counts[name] = assignee_counts.get(name, 0) + 1
        if assignee_counts:
            max_load = max(assignee_counts.values())
            min_load = min(assignee_counts.values())
            if max_load > min_load * 2 and max_load > 5:
                overloaded = [n for n, c in assignee_counts.items() if c == max_load]
                risks.append({
                    "risk": f"Workload imbalance: {', '.join(overloaded)} has {max_load} active tasks",
                    "severity": "medium",
                })

        return {
            "success": True,
            "project_name": project.name,
            "risks": risks,
            "risk_count": len(risks),
            "overall_risk_level": "high" if any(r['severity'] == 'high' for r in risks) else "medium" if risks else "low",
        }

    def generate_status_report(self, project_id: int, company_user=None) -> Dict:
        """Generate a comprehensive status report using LLM."""
        self.log_action("Generating status report", {"project_id": project_id})

        metrics = self.generate_metrics(project_id, company_user)
        if not metrics.get("success"):
            return metrics

        risks = self.identify_risks(project_id, company_user)

        prompt = f"""Generate a concise project status report from these metrics.

PROJECT: {metrics.get('project_name')}
STATUS: {metrics.get('project_status')}

METRICS:
{json.dumps(metrics.get('metrics', {}), indent=2)}

RISKS:
{json.dumps(risks.get('risks', []), indent=2)}

Write a brief status report with:
1. Executive Summary (2-3 sentences)
2. Key Metrics (bullet points)
3. Risks & Concerns
4. Recommendations (2-3 actionable items)

Use markdown formatting. Keep it concise."""

        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.5, max_tokens=800)
            return {
                "success": True,
                "project_name": metrics.get('project_name'),
                "report": response,
                "metrics": metrics.get('metrics'),
                "risks": risks.get('risks', []),
                "generated_at": timezone.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def calculate_health_score(self, project_id: int, company_user=None) -> Dict:
        """Calculate detailed project health score with breakdown."""
        metrics = self.generate_metrics(project_id, company_user)
        if not metrics.get("success"):
            return metrics

        m = metrics.get('metrics', {})
        total = m.get('total_tasks', 0)
        if total == 0:
            return {"success": True, "health_score": 0, "breakdown": {}, "message": "No tasks to evaluate"}

        completion_score = m.get('completion_rate', 0)
        overdue_penalty = min(30, (m.get('overdue_tasks', 0) / total) * 100) if total > 0 else 0
        blocked_penalty = min(20, (m.get('blocked_tasks', 0) / total) * 100) if total > 0 else 0
        unassigned = sum(1 for v in m.get('assignee_workload', {}).get('Unassigned', {}).values() if isinstance(v, int))

        health = max(0, min(100, completion_score - overdue_penalty - blocked_penalty))

        return {
            "success": True,
            "project_name": metrics.get('project_name'),
            "health_score": round(health, 1),
            "grade": "A" if health >= 80 else "B" if health >= 60 else "C" if health >= 40 else "D" if health >= 20 else "F",
            "breakdown": {
                "completion_rate": round(completion_score, 1),
                "overdue_penalty": round(overdue_penalty, 1),
                "blocked_penalty": round(blocked_penalty, 1),
            },
            "metrics": m,
        }

    def _calculate_health_score_from_metrics(self, completion_rate: float, overdue: int,
                                             blocked: int, total_tasks: int) -> float:
        """Calculate health score from raw metrics."""
        score = completion_rate
        if total_tasks > 0:
            score -= (overdue / total_tasks) * 100 * 0.5
            score -= (blocked / total_tasks) * 100 * 0.3
        return max(0, min(100, round(score, 2)))

    def _tasks_to_data(self, tasks_qs) -> List[Dict]:
        """Convert queryset to list of dicts."""
        return [{
            'id': t.id,
            'title': t.title,
            'status': t.status,
            'priority': t.priority,
            'priority_score': getattr(t, 'priority_score', None),
            'due_date': t.due_date.isoformat() if t.due_date else None,
            'assignee_id': t.assignee.id if t.assignee else None,
            'assignee_name': (t.assignee.get_full_name() or t.assignee.username) if t.assignee else None,
        } for t in tasks_qs]

    def _parse_date(self, date_str):
        """Safely parse a date string."""
        if not date_str:
            return None
        try:
            return datetime.strptime(str(date_str)[:10], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return None

    def process(self, action: str = "dashboard", **kwargs) -> Dict:
        """Main processing method for analytics agent."""
        project_id = kwargs.get('project_id')
        company_user = kwargs.get('company_user')

        if not project_id:
            return {"success": False, "error": "project_id is required"}

        if action == "dashboard":
            return self.create_dashboard(project_id, company_user=company_user)
        elif action == "metrics":
            return self.generate_metrics(project_id, company_user=company_user)
        elif action == "progress":
            return self.track_progress(project_id, company_user=company_user)
        elif action == "productivity":
            return self.analyze_productivity(project_id, company_user=company_user)
        elif action == "risks":
            return self.identify_risks(project_id, company_user=company_user)
        elif action == "report":
            return self.generate_status_report(project_id, company_user=company_user)
        elif action == "health":
            return self.calculate_health_score(project_id, company_user=company_user)
        else:
            return {"success": False, "error": f"Unknown action: {action}"}

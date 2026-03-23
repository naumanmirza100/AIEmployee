"""
Smart Notifications Agent
Scans project data to detect issues and generate proactive alerts.
"""

from .base_agent import BaseAgent
from typing import Dict, List, Optional
from datetime import datetime, timedelta


class SmartNotificationsAgent(BaseAgent):
    """
    Agent responsible for:
    - Detect overdue tasks and approaching deadlines
    - Identify blocked tasks and escalate
    - Flag unassigned high-priority tasks
    - Detect workload imbalances
    - Warn about project health risks
    - Track member inactivity
    """

    def __init__(self):
        super().__init__()
        self.system_prompt = """You are a Smart Notifications Agent that proactively identifies issues in project data."""

    def scan_project(self, project_info: Dict, tasks: List[Dict],
                     team_members: List[Dict] = None,
                     activity_logs: List[Dict] = None) -> Dict:
        """
        Scan a project and generate notifications for any issues found.
        Returns a list of notification objects ready to be saved.
        """
        self.log_action("Scanning project", {"project": project_info.get('name', 'Unknown')})

        notifications = []
        today = datetime.now().date()

        if not tasks:
            return {"success": True, "notifications": [], "message": "No tasks to scan."}

        # 1. Overdue tasks
        for task in tasks:
            if task.get('status') in ['done', 'completed']:
                continue
            due_date = self._parse_date(task.get('due_date'))
            if due_date and due_date < today:
                days_overdue = (today - due_date).days
                severity = 'critical' if days_overdue > 7 else 'warning'
                notifications.append({
                    "type": "overdue_task",
                    "severity": severity,
                    "title": f"Task overdue by {days_overdue} day(s)",
                    "message": f'"{task.get("title", "Unknown")}" deadline was {task.get("due_date")} ({days_overdue} days ago). '
                               f'Status: {task.get("status")}. Assignee: {task.get("assignee_name") or "Unassigned"}.',
                    "data": {"task_id": task.get("id"), "days_overdue": days_overdue},
                })

        # 2. Deadline approaching (within 3 days)
        for task in tasks:
            if task.get('status') in ['done', 'completed']:
                continue
            due_date = self._parse_date(task.get('due_date'))
            if due_date and today <= due_date <= today + timedelta(days=3):
                days_left = (due_date - today).days
                notifications.append({
                    "type": "deadline_approaching",
                    "severity": "warning",
                    "title": f"Task deadline in {days_left} day(s)" if days_left > 0 else "Task deadline today",
                    "message": f'"{task.get("title", "Unknown")}" deadline is {task.get("due_date")}. '
                               f'Status: {task.get("status")}. Assignee: {task.get("assignee_name") or "Unassigned"}.',
                    "data": {"task_id": task.get("id"), "days_left": days_left},
                })

        # 3. Blocked tasks
        blocked = [t for t in tasks if t.get('status') == 'blocked']
        if blocked:
            notifications.append({
                "type": "blocked_task",
                "severity": "critical",
                "title": f"{len(blocked)} task(s) are blocked",
                "message": f"Blocked tasks: {', '.join(t.get('title', 'Unknown') for t in blocked[:5])}. "
                           f"These need immediate attention to unblock progress.",
                "data": {"task_ids": [t.get("id") for t in blocked]},
            })

        # 4. Unassigned high-priority tasks
        unassigned_high = [
            t for t in tasks
            if t.get('priority') == 'high'
            and not t.get('assignee_name') and not t.get('assignee_username')
            and t.get('status') not in ['done', 'completed']
        ]
        if unassigned_high:
            notifications.append({
                "type": "unassigned_high_priority",
                "severity": "warning",
                "title": f"{len(unassigned_high)} high-priority task(s) unassigned",
                "message": f"High-priority tasks without an assignee: {', '.join(t.get('title', 'Unknown') for t in unassigned_high[:5])}.",
                "data": {"task_ids": [t.get("id") for t in unassigned_high]},
            })

        # 5. Workload imbalance
        if team_members and len(team_members) > 1:
            member_loads = {}
            for t in tasks:
                if t.get('status') in ['done', 'completed']:
                    continue
                name = t.get('assignee_name') or t.get('assignee_username') or 'Unassigned'
                member_loads[name] = member_loads.get(name, 0) + 1

            active_loads = {k: v for k, v in member_loads.items() if k != 'Unassigned'}
            if active_loads:
                max_load = max(active_loads.values())
                min_load = min(active_loads.values())
                if max_load > 0 and max_load > min_load * 2.5 and max_load >= 5:
                    overloaded = [n for n, c in active_loads.items() if c == max_load]
                    notifications.append({
                        "type": "workload_imbalance",
                        "severity": "warning",
                        "title": "Workload imbalance detected",
                        "message": f"{', '.join(overloaded)} has {max_load} active tasks while others have as few as {min_load}. "
                                   f"Consider redistributing tasks.",
                        "data": {"workload": active_loads},
                    })

        # 6. Project health risk (high % incomplete near deadline)
        total_active = len([t for t in tasks if t.get('status') not in ['done', 'completed']])
        total = len(tasks)
        completion_rate = ((total - total_active) / total * 100) if total > 0 else 0

        project_deadline = self._parse_date(project_info.get('deadline') or project_info.get('end_date'))
        if project_deadline and completion_rate < 50 and (project_deadline - today).days < 14:
            notifications.append({
                "type": "project_at_risk",
                "severity": "critical",
                "title": "Project at risk of missing deadline",
                "message": f"Project \"{project_info.get('name')}\" is only {completion_rate:.0f}% complete "
                           f"with {(project_deadline - today).days} days until deadline ({project_info.get('deadline')}).",
                "data": {"completion_rate": completion_rate, "days_left": (project_deadline - today).days},
            })

        # Sort by severity (critical first)
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        notifications.sort(key=lambda n: severity_order.get(n.get("severity", "info"), 2))

        return {
            "success": True,
            "notifications": notifications,
            "summary": {
                "total": len(notifications),
                "critical": len([n for n in notifications if n["severity"] == "critical"]),
                "warning": len([n for n in notifications if n["severity"] == "warning"]),
                "info": len([n for n in notifications if n["severity"] == "info"]),
            },
            "project_name": project_info.get("name"),
        }

    def _parse_date(self, date_str):
        if not date_str:
            return None
        try:
            return datetime.strptime(str(date_str)[:10], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return None

    def process(self, action: str = "scan", **kwargs) -> Dict:
        """Main processing method."""
        if action == "scan":
            return self.scan_project(
                kwargs.get('project_info', {}),
                kwargs.get('tasks', []),
                kwargs.get('team_members', []),
                kwargs.get('activity_logs', []),
            )
        return {"success": False, "error": f"Unknown action: {action}"}

"""
Calendar Auto-planner Agent
Automatically schedules tasks, meetings, and project activities.
"""

from .base_agent import BaseAgent
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import json


class CalendarPlannerAgent(BaseAgent):
    """
    Agent responsible for:
    - Auto-schedule tasks based on deadlines and priority
    - Suggest optimal task ordering for team members
    - Generate weekly/daily work plans
    - Detect scheduling conflicts and overloaded days
    - Recommend deadline adjustments
    """

    def __init__(self):
        super().__init__()
        self.system_prompt = """You are a Calendar Auto-planner Agent for a project management system.
Your role is to help plan and schedule tasks optimally based on deadlines, priorities, team capacity, and dependencies.
You analyze task data and suggest schedules, identify conflicts, and recommend timeline adjustments.
Always respond with practical, actionable scheduling advice."""

    def generate_schedule(self, tasks: List[Dict], team_members: List[Dict],
                          start_date: str = None, end_date: str = None) -> Dict:
        """
        Generate an optimized schedule for tasks across team members.
        Uses LLM to create intelligent scheduling recommendations.
        """
        self.log_action("Generating schedule", {"tasks_count": len(tasks), "members_count": len(team_members)})

        if not tasks:
            return {"success": True, "schedule": [], "message": "No tasks to schedule."}

        today = datetime.now().strftime('%Y-%m-%d')
        start = start_date or today
        end = end_date or (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')

        tasks_str = ""
        for t in tasks[:30]:
            tasks_str += f"- ID: {t.get('id')}, Title: {t.get('title')}, "
            tasks_str += f"Priority: {t.get('priority', 'medium')}, Status: {t.get('status', 'todo')}, "
            tasks_str += f"Due: {t.get('due_date', 'none')}, "
            assignee = t.get('assignee_username') or t.get('assignee_name') or 'Unassigned'
            tasks_str += f"Assignee: {assignee}\n"

        members_str = ""
        for m in team_members:
            members_str += f"- ID: {m.get('id')}, Name: {m.get('name', m.get('username', 'Unknown'))}\n"

        prompt = f"""Analyze the following tasks and team members and create an optimized work schedule.

PERIOD: {start} to {end}
TODAY: {today}

TASKS:
{tasks_str}

TEAM MEMBERS:
{members_str}

Create a day-by-day schedule. For each day, list which team member should work on which task.
Consider:
1. Task deadlines (earlier deadlines first)
2. Task priorities (high > medium > low)
3. Even workload distribution across team members
4. Tasks that are blocked or done should be skipped
5. Weekends (Sat/Sun) should have no tasks

Return a JSON object with this structure:
{{
    "schedule": [
        {{
            "date": "YYYY-MM-DD",
            "day_name": "Monday",
            "assignments": [
                {{
                    "member_name": "name",
                    "member_id": id,
                    "task_title": "title",
                    "task_id": id,
                    "priority": "high/medium/low",
                    "note": "brief note"
                }}
            ]
        }}
    ],
    "conflicts": ["list of scheduling conflicts detected"],
    "recommendations": ["list of scheduling recommendations"],
    "overloaded_members": ["members with too many tasks"],
    "unassigned_tasks": ["tasks that couldn't be scheduled"]
}}

Return ONLY the JSON."""

        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.5, max_tokens=2000)
            try:
                # Parse the JSON response
                cleaned = response.strip()
                if "```json" in cleaned:
                    cleaned = cleaned.split("```json")[1].split("```")[0].strip()
                elif "```" in cleaned:
                    cleaned = cleaned.split("```")[1].split("```")[0].strip()

                schedule_data = json.loads(cleaned)
                return {
                    "success": True,
                    **schedule_data,
                    "period": {"start": start, "end": end}
                }
            except (json.JSONDecodeError, IndexError):
                return {
                    "success": True,
                    "answer": response,
                    "period": {"start": start, "end": end}
                }
        except Exception as e:
            self.log_action("Error generating schedule", {"error": str(e)})
            return {"success": False, "error": str(e)}

    def detect_conflicts(self, tasks: List[Dict]) -> Dict:
        """Detect scheduling conflicts: overlapping deadlines, overloaded assignees, etc."""
        self.log_action("Detecting conflicts", {"tasks_count": len(tasks)})

        conflicts = []
        recommendations = []

        # Group tasks by assignee
        assignee_tasks = {}
        for t in tasks:
            assignee = t.get('assignee_username') or 'Unassigned'
            if assignee not in assignee_tasks:
                assignee_tasks[assignee] = []
            assignee_tasks[assignee].append(t)

        # Check for overloaded assignees
        for assignee, atasks in assignee_tasks.items():
            active = [t for t in atasks if t.get('status') not in ['done', 'completed']]
            if len(active) > 5:
                conflicts.append(f"{assignee} has {len(active)} active tasks - potential overload")
                recommendations.append(f"Consider redistributing some of {assignee}'s tasks")

        # Check for tasks with same/close deadlines
        today = datetime.now().date()
        overdue = []
        due_soon = []
        for t in tasks:
            if t.get('due_date') and t.get('status') not in ['done', 'completed']:
                try:
                    due = datetime.strptime(str(t['due_date'])[:10], '%Y-%m-%d').date()
                    if due < today:
                        overdue.append(t)
                    elif (due - today).days <= 3:
                        due_soon.append(t)
                except (ValueError, TypeError):
                    pass

        if overdue:
            conflicts.append(f"{len(overdue)} task(s) are overdue")
        if due_soon:
            conflicts.append(f"{len(due_soon)} task(s) due within 3 days")

        return {
            "success": True,
            "conflicts": conflicts,
            "recommendations": recommendations,
            "overdue_tasks": [{"id": t.get("id"), "title": t.get("title"), "due_date": t.get("due_date")} for t in overdue],
            "due_soon_tasks": [{"id": t.get("id"), "title": t.get("title"), "due_date": t.get("due_date")} for t in due_soon],
            "workload_summary": {name: len(tasks) for name, tasks in assignee_tasks.items()},
        }

    def process(self, action: str = "schedule", **kwargs) -> Dict:
        """
        Main processing method for calendar planner agent.
        """
        tasks = kwargs.get('tasks', [])
        team_members = kwargs.get('team_members', [])

        if action == "schedule":
            return self.generate_schedule(
                tasks, team_members,
                start_date=kwargs.get('start_date'),
                end_date=kwargs.get('end_date')
            )
        elif action == "conflicts":
            return self.detect_conflicts(tasks)
        else:
            return {"success": False, "error": f"Unknown action: {action}"}

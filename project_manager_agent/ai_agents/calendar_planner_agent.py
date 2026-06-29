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
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            self.log_action("Error generating schedule", {"error": str(e)})
            return {"success": False, "error": str(e)}

    def detect_conflicts(self, tasks: List[Dict]) -> Dict:
        """Detect scheduling conflicts: overlapping deadlines, overloaded assignees, etc.

        Each conflict is emitted as a **structured object** instead of a flat
        string so the UI can show the criterion ("why this is a conflict") and
        link straight to the affected tasks. Shape:

            {
              "type":       "workload_overload" | "same_deadline" | "overdue_cluster" | "due_soon",
              "severity":   "low" | "medium" | "high",
              "description": "Short, human-readable headline of the conflict",
              "criterion":   "Plain-language reason this counts as a conflict",
              "task_ids":   [int, ...]    # tasks involved
              "task_titles": [str, ...]   # convenience for the UI
              "metadata":   {...}          # type-specific extras (e.g. shared_date, assignee)
            }

        Recommendations follow the same structured pattern with a
        `suggested_action` field.
        """
        self.log_action("Detecting conflicts", {"tasks_count": len(tasks)})

        conflicts: List[Dict] = []
        recommendations: List[Dict] = []
        OVERLOAD_THRESHOLD = 5

        # Group tasks by assignee (display name when available, fallback to username)
        assignee_tasks: Dict[str, List[Dict]] = {}
        for t in tasks:
            assignee = (
                t.get('assignee_name')
                or t.get('assignee_username')
                or 'Unassigned'
            )
            assignee_tasks.setdefault(assignee, []).append(t)

        # ── Workload overload conflicts ──
        for assignee, atasks in assignee_tasks.items():
            if assignee == 'Unassigned':
                continue
            active = [t for t in atasks if t.get('status') not in ['done', 'completed']]
            if len(active) > OVERLOAD_THRESHOLD:
                conflicts.append({
                    "type": "workload_overload",
                    "severity": "high" if len(active) > OVERLOAD_THRESHOLD * 2 else "medium",
                    "description": f"{assignee} is assigned {len(active)} active tasks",
                    "criterion": (
                        f"More than {OVERLOAD_THRESHOLD} active (not-yet-done) tasks on one "
                        f"person is treated as overload — they're unlikely to finish all on time."
                    ),
                    "task_ids": [t.get("id") for t in active if t.get("id") is not None],
                    "task_titles": [t.get("title", "Untitled") for t in active],
                    "metadata": {
                        "assignee": assignee,
                        "active_count": len(active),
                        "threshold": OVERLOAD_THRESHOLD,
                    },
                })
                recommendations.append({
                    "for_conflict_type": "workload_overload",
                    "description": f"Redistribute some of {assignee}'s tasks",
                    "suggested_action": (
                        f"Move {len(active) - OVERLOAD_THRESHOLD} of {assignee}'s lower-priority "
                        f"tasks to less-busy team members (see the Suggest Delegation action)."
                    ),
                    "assignee": assignee,
                })

        # ── Same-deadline collisions ──
        # The PDF report explicitly flagged this case: two tasks sharing the
        # same due date were called out as a conflict but with no reason
        # given. Now we surface BOTH the shared date and the offending tasks.
        deadline_groups: Dict[str, List[Dict]] = {}
        today = datetime.now().date()
        overdue: List[Dict] = []
        due_soon: List[Dict] = []
        for t in tasks:
            raw_due = t.get('due_date')
            if not raw_due or t.get('status') in ['done', 'completed']:
                continue
            try:
                due = datetime.strptime(str(raw_due)[:10], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                continue
            deadline_groups.setdefault(due.isoformat(), []).append(t)
            if due < today:
                overdue.append(t)
            elif (due - today).days <= 3:
                due_soon.append(t)

        for date_iso, ts in deadline_groups.items():
            if len(ts) < 2:
                continue
            titles = [t.get('title', 'Untitled') for t in ts]
            conflicts.append({
                "type": "same_deadline",
                "severity": "medium" if len(ts) <= 3 else "high",
                "description": (
                    f"{len(ts)} tasks share the same deadline ({date_iso}): "
                    + ", ".join(f'"{title}"' for title in titles[:3])
                    + (f" and {len(titles) - 3} more" if len(titles) > 3 else "")
                ),
                "criterion": (
                    "Multiple tasks landing on the same due date cluster the "
                    "team's review/QA bandwidth into one day and increase the "
                    "chance of last-minute slippage."
                ),
                "task_ids": [t.get("id") for t in ts if t.get("id") is not None],
                "task_titles": titles,
                "metadata": {
                    "shared_date": date_iso,
                    "task_count": len(ts),
                },
            })
            recommendations.append({
                "for_conflict_type": "same_deadline",
                "description": f"Stagger deadlines around {date_iso}",
                "suggested_action": (
                    f"Move 1-2 of the {len(ts)} tasks due on {date_iso} earlier or "
                    f"later so the team has slack on the shared day."
                ),
                "shared_date": date_iso,
            })

        # ── Overdue cluster ──
        if overdue:
            conflicts.append({
                "type": "overdue_cluster",
                "severity": "high",
                "description": f"{len(overdue)} task(s) are overdue",
                "criterion": "These tasks already passed their due date and are still not marked done/completed.",
                "task_ids": [t.get("id") for t in overdue if t.get("id") is not None],
                "task_titles": [t.get("title", "Untitled") for t in overdue],
                "metadata": {"count": len(overdue)},
            })
            recommendations.append({
                "for_conflict_type": "overdue_cluster",
                "description": "Triage overdue tasks first",
                "suggested_action": (
                    "Either re-baseline these dates with the team, mark abandoned "
                    "ones as cancelled, or escalate the blocker."
                ),
            })

        # ── Due-soon cluster ──
        if due_soon:
            conflicts.append({
                "type": "due_soon",
                "severity": "low",
                "description": f"{len(due_soon)} task(s) due within 3 days",
                "criterion": "Early-warning signal — tasks within the 3-day horizon that aren't yet done.",
                "task_ids": [t.get("id") for t in due_soon if t.get("id") is not None],
                "task_titles": [t.get("title", "Untitled") for t in due_soon],
                "metadata": {"count": len(due_soon)},
            })

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

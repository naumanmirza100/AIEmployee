"""
Daily Standup Agent
Generates daily standup summaries, tracks team progress, and identifies blockers.
Automates async standups by analyzing task activity data.
"""

from .base_agent import BaseAgent
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import json


class DailyStandupAgent(BaseAgent):
    """
    Agent responsible for:
    - Generate daily standup summaries per team member
    - Identify blockers and escalate them
    - Track what each member did yesterday / plans for today
    - Generate team-wide standup report for the PM
    - Detect members who haven't updated their tasks
    - Weekly summary of standup patterns
    """

    def __init__(self):
        super().__init__()
        self.system_prompt = """You are a Daily Standup Agent for a project management system.
Your role is to analyze task data and generate standup reports that help teams stay aligned.
You track what team members accomplished, what they're working on, and what's blocking them.
Be concise, factual, and highlight anything that needs attention."""

    def generate_standup(self, tasks: List[Dict], team_members: List[Dict],
                         activity_logs: List[Dict] = None,
                         project_info: Dict = None) -> Dict:
        """
        Generate a daily standup summary based on task data and activity logs.
        """
        self.log_action("Generating standup", {
            "tasks": len(tasks),
            "members": len(team_members),
            "logs": len(activity_logs) if activity_logs else 0
        })

        today = datetime.now().strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        # Build per-member activity summary
        member_summaries = {}
        for member in team_members:
            name = member.get('name', member.get('username', 'Unknown'))
            member_id = member.get('id')
            member_summaries[name] = {
                "id": member_id,
                "tasks_assigned": [],
                "tasks_in_progress": [],
                "tasks_completed_recently": [],
                "tasks_blocked": [],
                "recent_activity": [],
            }

        # Map tasks to members
        for task in tasks:
            assignee = task.get('assignee_username') or task.get('assignee_name')
            if not assignee:
                continue
            # Find matching member
            matched_member = None
            for name in member_summaries:
                if assignee.lower() in name.lower() or name.lower() in assignee.lower():
                    matched_member = name
                    break
            if not matched_member:
                # Create entry for this assignee
                matched_member = assignee
                member_summaries[matched_member] = {
                    "id": None,
                    "tasks_assigned": [],
                    "tasks_in_progress": [],
                    "tasks_completed_recently": [],
                    "tasks_blocked": [],
                    "recent_activity": [],
                }

            summary = member_summaries[matched_member]
            summary["tasks_assigned"].append(task.get('title', 'Unknown'))

            if task.get('status') == 'in_progress':
                summary["tasks_in_progress"].append(task.get('title'))
            elif task.get('status') in ['done', 'completed']:
                summary["tasks_completed_recently"].append(task.get('title'))
            elif task.get('status') == 'blocked':
                summary["tasks_blocked"].append(task.get('title'))

        # Map activity logs to members
        if activity_logs:
            for log in activity_logs:
                user = log.get('user', 'Unknown')
                for name in member_summaries:
                    if user.lower() in name.lower() or name.lower() in user.lower():
                        member_summaries[name]["recent_activity"].append({
                            "action": log.get('action_type', 'unknown'),
                            "task": log.get('task_title', 'Unknown'),
                            "old_value": log.get('old_value'),
                            "new_value": log.get('new_value'),
                            "timestamp": log.get('timestamp'),
                        })
                        break

        # Build context for LLM
        standup_context = f"DATE: {today}\n"
        standup_context += f"PROJECT: {project_info.get('name', 'N/A')}\n\n" if project_info else "\n"

        for name, data in member_summaries.items():
            standup_context += f"\n--- {name} ---\n"
            assigned_str = ', '.join(f'"{t}"' for t in data['tasks_assigned'])
            standup_context += f"Total assigned ({len(data['tasks_assigned'])}): {assigned_str}\n"
            if data['tasks_in_progress']:
                ip_str = ', '.join(f'"{t}"' for t in data['tasks_in_progress'])
                standup_context += f"In Progress: {ip_str}\n"
            else:
                standup_context += "In Progress: None\n"
            if data['tasks_completed_recently']:
                comp_str = ', '.join(f'"{t}"' for t in data['tasks_completed_recently'])
                standup_context += f"Completed: {comp_str}\n"
            else:
                standup_context += "Completed: None\n"
            if data['tasks_blocked']:
                blocked_str = ', '.join(f'"{t}"' for t in data['tasks_blocked'])
                standup_context += f"BLOCKED: {blocked_str}\n"
            if not data['tasks_in_progress'] and not data['tasks_completed_recently'] and not data['recent_activity']:
                standup_context += "STATUS: No recent activity\n"
            if data['recent_activity']:
                standup_context += f"Recent Activity ({len(data['recent_activity'])} actions):\n"
                for act in data['recent_activity'][:10]:
                    standup_context += f"  - {act['action']} on \"{act['task']}\""
                    if act.get('old_value') and act.get('new_value'):
                        standup_context += f" ({act['old_value']} → {act['new_value']})"
                    standup_context += "\n"

        # Detect members with no activity
        inactive_members = [
            name for name, data in member_summaries.items()
            if not data['tasks_in_progress'] and not data['tasks_completed_recently'] and not data['recent_activity']
            and data['tasks_assigned']  # has tasks but no activity
        ]

        # Collect all blockers
        all_blockers = []
        for name, data in member_summaries.items():
            for task in data['tasks_blocked']:
                all_blockers.append({"member": name, "task": task})

        # Use LLM to generate a polished standup report
        prompt = f"""Generate a daily standup report using ONLY the exact data below. Do NOT invent, guess, or generalize any task names — use the exact task titles in quotes from the data.

{standup_context}

INACTIVE MEMBERS (have tasks but no recent progress): {', '.join(inactive_members) if inactive_members else 'None'}
BLOCKERS: {json.dumps(all_blockers) if all_blockers else 'None'}

STRICT RULES:
- Use the EXACT task titles from the data above (the text in quotes). Never say "task 1", "task 2", or make up names.
- If a member has no completed tasks, say "No completed tasks" — do not fabricate any.
- If a member has no in-progress tasks, say "No tasks in progress" — do not fabricate any.
- Only report what the data explicitly shows. Do not assume or infer activity that is not in the data.

Generate a standup report with this structure:
1. **Team Summary** - 2-3 sentence overview with actual numbers from the data
2. **Per-Member Update** - For each member:
   - **Done**: List exact task titles from Completed data, or "None" if empty
   - **In Progress**: List exact task titles from In Progress data, or "None" if empty
   - **Blocked**: List exact task titles from BLOCKED data, or "None"
3. **Blockers & Risks** - Only list blockers that exist in the data above
4. **Action Items** - What the PM should follow up on based on actual data

Use markdown formatting. Be concise. If a member has no activity, note it briefly with their assigned task count."""

        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.1, max_tokens=1500)

            return {
                "success": True,
                "report": response,
                "date": today,
                "project": project_info.get('name') if project_info else None,
                "summary": {
                    "total_members": len(team_members),
                    "active_members": len(team_members) - len(inactive_members),
                    "inactive_members": inactive_members,
                    "total_blockers": len(all_blockers),
                    "blockers": all_blockers,
                },
                "member_details": {
                    name: {
                        "in_progress": len(data["tasks_in_progress"]),
                        "completed": len(data["tasks_completed_recently"]),
                        "blocked": len(data["tasks_blocked"]),
                        "total_assigned": len(data["tasks_assigned"]),
                    }
                    for name, data in member_summaries.items()
                },
            }
        except Exception as e:
            self.log_action("Error generating standup", {"error": str(e)})
            return {"success": False, "error": str(e)}

    def generate_weekly_summary(self, tasks: List[Dict], team_members: List[Dict],
                                 activity_logs: List[Dict] = None,
                                 project_info: Dict = None) -> Dict:
        """Generate a weekly summary of team progress."""
        self.log_action("Generating weekly summary", {"tasks": len(tasks)})

        today = datetime.now()
        week_start = (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')
        week_end = today.strftime('%Y-%m-%d')

        # Count completed tasks this week
        completed_this_week = []
        for task in tasks:
            if task.get('status') in ['done', 'completed']:
                completed_this_week.append(task.get('title', 'Unknown'))

        total = len(tasks)
        completed = len([t for t in tasks if t.get('status') in ['done', 'completed']])
        in_progress = len([t for t in tasks if t.get('status') == 'in_progress'])
        blocked = len([t for t in tasks if t.get('status') == 'blocked'])

        prompt = f"""Generate a weekly team summary report.

WEEK: {week_start} to {week_end}
PROJECT: {project_info.get('name', 'N/A') if project_info else 'All Projects'}

STATS:
- Total Tasks: {total}
- Completed: {completed}
- In Progress: {in_progress}
- Blocked: {blocked}
- Completion Rate: {round(completed/total*100, 1) if total > 0 else 0}%

TEAM ({len(team_members)} members):
{chr(10).join(f'- {m.get("name", m.get("username", "Unknown"))}' for m in team_members)}

COMPLETED TASKS:
{chr(10).join(f'- "{t}"' for t in completed_this_week[:15]) if completed_this_week else '- None'}

STRICT RULES: Use ONLY the exact task titles and numbers from the data above. Never invent or generalize task names.

Generate a brief weekly summary with:
1. **Week Overview** - Key accomplishments using exact numbers from STATS above
2. **Highlights** - List exact completed task titles from COMPLETED TASKS above
3. **Concerns** - Blockers, slow progress areas based on actual data
4. **Next Week Focus** - Recommended priorities

Use markdown. Keep it under 300 words."""

        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.1, max_tokens=1000)
            return {
                "success": True,
                "report": response,
                "week": {"start": week_start, "end": week_end},
                "stats": {
                    "total_tasks": total,
                    "completed": completed,
                    "in_progress": in_progress,
                    "blocked": blocked,
                    "completion_rate": round(completed / total * 100, 1) if total > 0 else 0,
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def process(self, action: str = "daily", **kwargs) -> Dict:
        """Main processing method."""
        tasks = kwargs.get('tasks', [])
        team_members = kwargs.get('team_members', [])
        activity_logs = kwargs.get('activity_logs', [])
        project_info = kwargs.get('project_info')

        if action == "daily":
            return self.generate_standup(tasks, team_members, activity_logs, project_info)
        elif action == "weekly":
            return self.generate_weekly_summary(tasks, team_members, activity_logs, project_info)
        else:
            return {"success": False, "error": f"Unknown action: {action}"}

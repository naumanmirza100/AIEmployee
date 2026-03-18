"""
Time Estimation Agent
AI-powered task duration estimation based on task complexity,
historical data, and project context.
"""

from .base_agent import BaseAgent
from typing import Dict, List, Optional
import json


class TimeEstimationAgent(BaseAgent):
    """
    Agent responsible for:
    - Estimate task duration based on complexity
    - Analyze historical completion times
    - Suggest realistic deadlines
    - Identify tasks that may take longer than expected
    """

    def __init__(self):
        super().__init__()
        self.system_prompt = """You are a Time Estimation Agent for a project management system.
Your role is to analyze tasks and provide realistic time estimates based on:
- Task complexity and scope
- Type of work (development, design, testing, etc.)
- Dependencies on other tasks
- Team member experience level
Be conservative in estimates - it's better to overestimate than underestimate."""

    def estimate_tasks(self, tasks: List[Dict], project_info: Dict = None,
                       team_members: List[Dict] = None,
                       completed_tasks: List[Dict] = None) -> Dict:
        """
        Estimate duration for tasks based on their descriptions and context.
        """
        self.log_action("Estimating tasks", {"count": len(tasks)})

        if not tasks:
            return {"success": True, "estimates": [], "message": "No tasks to estimate."}

        # Build context from completed tasks for historical reference
        historical_str = ""
        if completed_tasks:
            historical_str = "\n\nHISTORICAL DATA (completed tasks for reference):\n"
            for t in completed_tasks[:10]:
                historical_str += f"- {t.get('title')}: took {t.get('days_to_complete', '?')} days "
                historical_str += f"(Priority: {t.get('priority', '?')})\n"

        tasks_str = ""
        for t in tasks[:20]:
            tasks_str += f"\n- ID: {t.get('id')}, Title: {t.get('title')}\n"
            tasks_str += f"  Priority: {t.get('priority', 'medium')}, Status: {t.get('status', 'todo')}\n"
            if t.get('description'):
                tasks_str += f"  Description: {t.get('description', '')[:200]}\n"
            if t.get('assignee_name'):
                tasks_str += f"  Assignee: {t.get('assignee_name')}\n"

        prompt = f"""Estimate the duration for each of the following tasks.

PROJECT: {project_info.get('name', 'Unknown') if project_info else 'Unknown'}
{historical_str}

TASKS TO ESTIMATE:
{tasks_str}

For each task, provide:
1. Estimated hours (development time)
2. Estimated calendar days (including review, testing)
3. Confidence level (high/medium/low)
4. Risk factors that could increase the estimate

Return JSON:
{{
    "estimates": [
        {{
            "task_id": id,
            "task_title": "title",
            "estimated_hours": number,
            "estimated_days": number,
            "confidence": "high|medium|low",
            "complexity": "simple|moderate|complex",
            "risk_factors": ["factor 1"],
            "reasoning": "brief explanation"
        }}
    ],
    "total_estimated_hours": number,
    "total_estimated_days": number,
    "recommendations": ["recommendation 1"]
}}

Return ONLY the JSON."""

        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.5, max_tokens=2000)
            try:
                cleaned = response.strip()
                if "```json" in cleaned:
                    cleaned = cleaned.split("```json")[1].split("```")[0].strip()
                elif "```" in cleaned:
                    cleaned = cleaned.split("```")[1].split("```")[0].strip()

                result = json.loads(cleaned)
                return {"success": True, **result}
            except (json.JSONDecodeError, IndexError):
                return {"success": True, "answer": response}
        except Exception as e:
            self.log_action("Error estimating tasks", {"error": str(e)})
            return {"success": False, "error": str(e)}

    def process(self, action: str = "estimate", **kwargs) -> Dict:
        """Main processing method."""
        if action == "estimate":
            return self.estimate_tasks(
                kwargs.get('tasks', []),
                kwargs.get('project_info'),
                kwargs.get('team_members'),
                kwargs.get('completed_tasks'),
            )
        return {"success": False, "error": f"Unknown action: {action}"}

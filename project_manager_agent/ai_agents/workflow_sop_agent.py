"""
Workflow / SOP Runner Agent
Manages project workflows and standard operating procedures.
Uses LLM to suggest workflows and validate process compliance.
"""

from .base_agent import BaseAgent
from typing import Dict, List, Optional
import json


class WorkflowSOPAgent(BaseAgent):
    """
    Agent responsible for:
    - Suggest workflows based on project type
    - Validate task status transitions
    - Recommend process improvements
    - Generate checklists for common project phases
    - Identify workflow bottlenecks
    """

    def __init__(self):
        super().__init__()
        self.system_prompt = """You are a Workflow & SOP Agent for a project management system.
Your role is to help teams follow best practices by suggesting workflows, validating processes,
and generating checklists. You understand software development, marketing, design, and general
project management workflows."""

        # Common workflow templates
        self.workflow_templates = {
            "software_development": {
                "name": "Software Development Lifecycle",
                "phases": ["Requirements", "Design", "Development", "Testing", "Deployment", "Maintenance"],
                "task_statuses": ["todo", "in_progress", "review", "done"],
            },
            "marketing_campaign": {
                "name": "Marketing Campaign",
                "phases": ["Research", "Strategy", "Content Creation", "Review", "Launch", "Analysis"],
                "task_statuses": ["todo", "in_progress", "review", "done"],
            },
            "design_sprint": {
                "name": "Design Sprint",
                "phases": ["Understand", "Diverge", "Converge", "Prototype", "Test"],
                "task_statuses": ["todo", "in_progress", "review", "done"],
            },
        }

    def suggest_workflow(self, project_info: Dict, tasks: List[Dict] = None) -> Dict:
        """
        Suggest a workflow based on project type and current state.
        """
        self.log_action("Suggesting workflow", {"project": project_info.get('name', 'Unknown')})

        tasks_str = ""
        if tasks:
            for t in tasks[:20]:
                tasks_str += f"- {t.get('title', 'Unknown')} (Status: {t.get('status')}, Priority: {t.get('priority')})\n"

        prompt = f"""Analyze this project and suggest an optimal workflow.

PROJECT:
- Name: {project_info.get('name', 'Unknown')}
- Type: {project_info.get('project_type', 'Unknown')}
- Status: {project_info.get('status', 'Unknown')}
- Description: {project_info.get('description', 'N/A')[:500]}

CURRENT TASKS:
{tasks_str or 'No tasks yet'}

Suggest a workflow with:
1. Recommended phases/stages
2. Task status flow (what order statuses should progress)
3. Checklist for the current phase
4. Any process improvements based on current task state

Return JSON:
{{
    "workflow_name": "name of suggested workflow",
    "phases": [
        {{
            "name": "phase name",
            "description": "what happens in this phase",
            "checklist": ["item 1", "item 2"],
            "is_current": true/false
        }}
    ],
    "status_flow": ["todo", "in_progress", "review", "done"],
    "current_phase": "which phase the project appears to be in",
    "recommendations": ["process improvement 1", "process improvement 2"],
    "bottlenecks": ["any bottlenecks detected from task data"]
}}

Return ONLY the JSON."""

        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.5, max_tokens=1500)
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
            self.log_action("Error suggesting workflow", {"error": str(e)})
            return {"success": False, "error": str(e)}

    def generate_checklist(self, phase: str, project_type: str = "software_development") -> Dict:
        """Generate a checklist for a specific project phase."""
        self.log_action("Generating checklist", {"phase": phase, "type": project_type})

        prompt = f"""Generate a detailed checklist for the "{phase}" phase of a {project_type} project.

Return JSON:
{{
    "phase": "{phase}",
    "checklist": [
        {{
            "item": "checklist item description",
            "priority": "high/medium/low",
            "category": "category name"
        }}
    ],
    "tips": ["best practice tip 1", "tip 2"]
}}

Return ONLY the JSON."""

        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.5, max_tokens=1000)
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
            return {"success": False, "error": str(e)}

    def validate_transitions(self, tasks: List[Dict]) -> Dict:
        """Validate task status transitions and flag issues."""
        issues = []
        for t in tasks:
            status = t.get('status', '')
            # Flag tasks that skipped review
            if status == 'done' and not t.get('had_review', False):
                issues.append({
                    "task_id": t.get('id'),
                    "task_title": t.get('title'),
                    "issue": "Task marked as done without going through review",
                    "severity": "medium"
                })
            # Flag tasks stuck in progress too long
            if status == 'in_progress' and t.get('days_in_status', 0) > 7:
                issues.append({
                    "task_id": t.get('id'),
                    "task_title": t.get('title'),
                    "issue": f"Task stuck in 'in_progress' for {t.get('days_in_status', 0)} days",
                    "severity": "high"
                })

        return {
            "success": True,
            "issues": issues,
            "issues_count": len(issues),
            "message": f"Found {len(issues)} workflow issue(s)" if issues else "All tasks following proper workflow"
        }

    def process(self, action: str = "suggest", **kwargs) -> Dict:
        """
        Main processing method for workflow agent.
        """
        if action == "suggest":
            return self.suggest_workflow(
                kwargs.get('project_info', {}),
                kwargs.get('tasks', [])
            )
        elif action == "checklist":
            return self.generate_checklist(
                kwargs.get('phase', 'development'),
                kwargs.get('project_type', 'software_development')
            )
        elif action == "validate":
            return self.validate_transitions(kwargs.get('tasks', []))
        else:
            return {"success": False, "error": f"Unknown action: {action}"}

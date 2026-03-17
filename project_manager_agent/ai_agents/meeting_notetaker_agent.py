"""
Meeting Notetaker Agent
Captures, summarizes, and manages meeting notes and action items.
Uses LLM to extract actionable insights from meeting text.
"""

from .base_agent import BaseAgent
from typing import Dict, List, Optional
import json


class MeetingNotetakerAgent(BaseAgent):
    """
    Agent responsible for:
    - Summarize meeting notes/transcripts
    - Extract action items from meetings
    - Identify key decisions and outcomes
    - Link action items to projects/tasks
    - Generate structured meeting reports
    """

    def __init__(self):
        super().__init__()
        self.system_prompt = """You are a Meeting Notetaker Agent for a project management system.
Your role is to analyze meeting notes or transcripts and extract:
1. Key decisions made
2. Action items with owners and deadlines
3. Important discussion points
4. Risks or blockers mentioned
5. Follow-up items

You produce structured, actionable summaries that help teams stay aligned."""

    def summarize_meeting(self, meeting_text: str, meeting_info: Optional[Dict] = None,
                          project_context: Optional[Dict] = None) -> Dict:
        """
        Summarize meeting notes and extract action items.

        Args:
            meeting_text: Raw meeting notes or transcript
            meeting_info: Optional metadata (date, participants, topic)
            project_context: Optional project context for linking
        """
        self.log_action("Summarizing meeting", {"text_length": len(meeting_text)})

        if not meeting_text or len(meeting_text.strip()) < 10:
            return {"success": False, "error": "Meeting text is too short to analyze."}

        context_str = ""
        if meeting_info:
            context_str += f"\nMeeting Info:\n"
            if meeting_info.get('date'):
                context_str += f"- Date: {meeting_info['date']}\n"
            if meeting_info.get('participants'):
                context_str += f"- Participants: {', '.join(meeting_info['participants'])}\n"
            if meeting_info.get('topic'):
                context_str += f"- Topic: {meeting_info['topic']}\n"

        if project_context:
            context_str += f"\nProject Context:\n"
            context_str += f"- Project: {project_context.get('name', 'Unknown')}\n"
            if project_context.get('tasks'):
                context_str += f"- Active Tasks: {len(project_context['tasks'])}\n"

        prompt = f"""Analyze the following meeting notes and extract structured information.
{context_str}

MEETING NOTES:
---
{meeting_text[:3000]}
---

Return a JSON object with this structure:
{{
    "summary": "2-3 sentence executive summary of the meeting",
    "key_decisions": [
        {{
            "decision": "what was decided",
            "context": "brief context"
        }}
    ],
    "action_items": [
        {{
            "action": "what needs to be done",
            "owner": "person responsible (from notes, or 'TBD')",
            "deadline": "mentioned deadline or 'TBD'",
            "priority": "high/medium/low",
            "suggested_task_title": "short task title for creating in PM tool"
        }}
    ],
    "discussion_points": [
        "key point 1",
        "key point 2"
    ],
    "risks_mentioned": [
        {{
            "risk": "risk description",
            "severity": "high/medium/low"
        }}
    ],
    "follow_ups": [
        "follow-up item 1"
    ],
    "participants_detected": ["names mentioned in the notes"]
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
            self.log_action("Error summarizing meeting", {"error": str(e)})
            return {"success": False, "error": str(e)}

    def extract_action_items(self, meeting_text: str) -> Dict:
        """Quick extraction of just action items from meeting text."""
        self.log_action("Extracting action items", {"text_length": len(meeting_text)})

        prompt = f"""Extract ONLY action items from these meeting notes.

MEETING NOTES:
---
{meeting_text[:3000]}
---

Return a JSON array of action items:
[
    {{
        "action": "what needs to be done",
        "owner": "person responsible or 'TBD'",
        "deadline": "deadline or 'TBD'",
        "priority": "high/medium/low"
    }}
]

Return ONLY the JSON array."""

        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=1000)
            try:
                cleaned = response.strip()
                if "```json" in cleaned:
                    cleaned = cleaned.split("```json")[1].split("```")[0].strip()
                elif "```" in cleaned:
                    cleaned = cleaned.split("```")[1].split("```")[0].strip()

                items = json.loads(cleaned)
                return {"success": True, "action_items": items, "count": len(items)}
            except (json.JSONDecodeError, IndexError):
                return {"success": True, "answer": response}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def process(self, action: str = "summarize", **kwargs) -> Dict:
        """
        Main processing method for meeting notetaker agent.
        """
        meeting_text = kwargs.get('meeting_text', '')
        meeting_info = kwargs.get('meeting_info')
        project_context = kwargs.get('project_context')

        if action == "summarize":
            return self.summarize_meeting(meeting_text, meeting_info, project_context)
        elif action == "extract_actions":
            return self.extract_action_items(meeting_text)
        else:
            return {"success": False, "error": f"Unknown action: {action}"}

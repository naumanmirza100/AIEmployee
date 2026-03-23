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

        # Validate that the text resembles meeting notes before processing
        validation_prompt = f"""Determine if the following text is meeting notes, a meeting transcript, or meeting-related content.

TEXT:
---
{meeting_text[:500]}
---

Reply with ONLY "yes" or "no". Answer "yes" if the text contains any of: discussions between people, decisions, action items, task updates, agenda items, or anything that could reasonably come from a meeting. Answer "no" if the text is completely unrelated (e.g. a recipe, a poem, random gibberish, song lyrics, a story)."""

        try:
            validation = self._call_llm(validation_prompt, "You are a text classifier. Reply with only 'yes' or 'no'.", temperature=0.0, max_tokens=10)
            if validation.strip().lower().startswith("no"):
                return {
                    "success": False,
                    "error": "The text you entered doesn't appear to be meeting notes.",
                    "instructions": (
                        "Please paste actual meeting notes or a transcript. Here's what works well:\n\n"
                        "• Raw notes from a meeting (e.g. 'Ahmed said the API is delayed. We decided to push the demo to Friday.')\n"
                        "• Copy-pasted Zoom/Teams/Slack chat logs from a meeting\n"
                        "• Bullet-point summaries (e.g. '- Discussed timeline. - Sara will fix the frontend by Wed.')\n"
                        "• Transcripts from recorded meetings\n"
                        "• Email threads summarizing a meeting\n\n"
                        "The AI will extract: summary, action items, key decisions, risks, and follow-ups."
                    )
                }
        except Exception:
            pass  # If validation fails, proceed with analysis anyway

        # Validate mentioned people against project team members (only if a project is selected)
        if project_context and project_context.get('team_members') is not None:
            team = project_context.get('team_members', [])
            team_lower = [m.lower() for m in team]

            # Extract names from the meeting text using LLM
            name_prompt = f"""Extract all person names mentioned in this text. Return ONLY a JSON array of names, nothing else.

TEXT:
---
{meeting_text[:1500]}
---

Example output: ["Ahmed", "Sara", "John"]
If no names found, return: []"""

            try:
                name_response = self._call_llm(name_prompt, "You extract person names from text. Return only a JSON array.", temperature=0.0, max_tokens=200)
                cleaned_names = name_response.strip()
                if "```json" in cleaned_names:
                    cleaned_names = cleaned_names.split("```json")[1].split("```")[0].strip()
                elif "```" in cleaned_names:
                    cleaned_names = cleaned_names.split("```")[1].split("```")[0].strip()

                detected_names = json.loads(cleaned_names)
                if isinstance(detected_names, list) and detected_names:
                    unrecognized = []
                    for person in detected_names:
                        person_lower = person.lower()
                        matched = any(
                            person_lower in member or member in person_lower
                            for member in team_lower
                        )
                        if not matched:
                            unrecognized.append(person)

                    if unrecognized:
                        team_display = ', '.join(team) if team else 'No members assigned yet'
                        return {
                            "success": False,
                            "error": f"The following people are not part of project \"{project_context.get('name', '')}\":",
                            "instructions": (
                                f"Unrecognized members: {', '.join(unrecognized)}\n\n"
                                f"Current project team members (people with assigned tasks):\n"
                                f"{team_display}\n\n"
                                f"Please make sure the people mentioned in your meeting notes are assigned to tasks in this project, "
                                f"or select a different project that these members belong to."
                            )
                        }
            except (json.JSONDecodeError, Exception):
                pass  # If name extraction fails, proceed with analysis

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

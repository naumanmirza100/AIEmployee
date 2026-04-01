"""
Meeting Scheduler Agent
Chat-based AI agent that helps schedule meetings between company users.
Parses natural language to extract meeting details and manages the scheduling flow.
"""

from .base_agent import BaseAgent
from typing import Dict, Optional, List
import json
import re
import logging
from datetime import datetime, timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


class MeetingSchedulerAgent(BaseAgent):
    """
    Chat-based agent for scheduling meetings between company users.
    Parses user prompts to extract: invitee name, date/time, duration, title/agenda.
    Validates invitees against company user list before scheduling.
    """

    def __init__(self):
        super().__init__()
        self.system_prompt = """You are a Meeting Scheduler assistant for a project management system.
Your job is to help users schedule meetings with other company members.
You parse natural language requests and extract meeting details.
You MUST validate that mentioned users exist in the company before scheduling."""

    def _find_user_in_message(self, message: str, company_users: List[Dict]) -> Dict:
        """
        Find which company user is mentioned in the message.
        Uses word-boundary matching to avoid false positives.
        Returns: { "match": "exact"|"single"|"ambiguous"|"not_found",
                   "user": {...} or None,
                   "candidates": [...] for ambiguous,
                   "matched_name": str or None }
        """
        msg_lower = message.lower()

        # Build a scored list: (user, score, matched_text)
        # Higher score = better match
        matches = []

        for u in company_users:
            full_name = u["full_name"].lower()
            email = u["email"].lower()
            email_prefix = email.split("@")[0] if "@" in email else email
            name_parts = [p for p in full_name.split() if len(p) >= 2]

            best_score = 0
            best_text = None

            # Score 100: full name found in message (word boundary)
            if re.search(r'\b' + re.escape(full_name) + r'\b', msg_lower):
                best_score = 100
                best_text = full_name

            # Score 90: full email found in message
            if best_score < 90 and email in msg_lower:
                best_score = 90
                best_text = email

            # Score 80: email prefix (before @) found as a word in message
            if best_score < 80 and len(email_prefix) >= 3:
                if re.search(r'\b' + re.escape(email_prefix) + r'\b', msg_lower):
                    best_score = 80
                    best_text = email_prefix

            # Score 70: a name part (first/last name) found as a whole word in message
            # Only match parts with 3+ chars to avoid false positives
            if best_score < 70:
                for part in name_parts:
                    if len(part) >= 3 and re.search(r'\b' + re.escape(part) + r'\b', msg_lower):
                        best_score = 70
                        best_text = part
                        break

            if best_score > 0:
                matches.append((u, best_score, best_text))

        if not matches:
            return {"match": "not_found", "user": None, "candidates": [], "matched_name": None}

        # Sort by score descending
        matches.sort(key=lambda x: -x[1])
        top_score = matches[0][1]

        # If there's only one match total, it's a clear single
        if len(matches) == 1:
            return {"match": "single", "user": matches[0][0], "candidates": [], "matched_name": matches[0][2]}

        # If the top scorer has score >= 90 (full name or email match) AND
        # the second best is < 90, it's a clear winner
        if top_score >= 90 and matches[1][1] < 90:
            return {"match": "single", "user": matches[0][0], "candidates": [], "matched_name": matches[0][2]}

        # If top score is 100 (full name exact) and only one has 100, it's single
        top_matches = [m for m in matches if m[1] == top_score]
        if top_score == 100 and len(top_matches) == 1:
            return {"match": "single", "user": top_matches[0][0], "candidates": [], "matched_name": top_matches[0][2]}

        # Multiple matches at similar score levels — check if they matched on the SAME word
        # If multiple users share the same name part that was matched, it's truly ambiguous
        if len(matches) > 1 and matches[0][1] - matches[-1][1] <= 20:
            # Close scores — ambiguous
            return {
                "match": "ambiguous",
                "user": None,
                "candidates": [m[0] for m in matches],
                "matched_name": matches[0][2],
            }

        # The top scorer wins clearly
        if len(top_matches) == 1:
            return {"match": "single", "user": top_matches[0][0], "candidates": [], "matched_name": top_matches[0][2]}

        # Multiple at top score — ambiguous
        return {
            "match": "ambiguous",
            "user": None,
            "candidates": [m[0] for m in top_matches],
            "matched_name": top_matches[0][2],
        }

    def parse_meeting_request(self, message: str, company_users: List[Dict], current_time: str) -> Dict:
        """
        Use LLM to parse a natural language meeting request into structured data.

        Args:
            message: User's natural language request
            company_users: List of company users with id, full_name, email
            current_time: Current datetime ISO string for reference

        Returns:
            Dict with parsed meeting details or error
        """
        users_list = "\n".join(
            f"- ID: {u['id']}, Name: {u['full_name']}, Email: {u['email']}"
            for u in company_users
        )

        # Calculate the current day of week for better relative date parsing
        try:
            from datetime import datetime as _dt
            now = _dt.fromisoformat(current_time.replace("Z", "+00:00")) if "T" in current_time else _dt.now()
            day_of_week = now.strftime("%A")
            date_display = now.strftime("%A, %B %d, %Y at %I:%M %p")
        except Exception:
            day_of_week = "unknown"
            date_display = current_time

        prompt = f"""Parse the following meeting scheduling request. Extract the meeting details.

CURRENT DATE/TIME: {current_time}
TODAY IS: {day_of_week} ({date_display})

AVAILABLE COMPANY USERS:
{users_list}

USER REQUEST: "{message}"

INSTRUCTIONS:
1. Identify which user(s) the organizer wants to meet with. Match names against the AVAILABLE COMPANY USERS list using partial/fuzzy matching (e.g., "hamza" matches "Hamza Ali Khan"). Use the FULL NAME from the list as invitee_name.
2. If a mentioned name does NOT match any user (even partially), set "user_not_found" to that name.
3. Extract the proposed date and time. Convert relative references to absolute ISO datetime:
   - TODAY IS {day_of_week}. Calculate dates correctly from this.
   - "tomorrow" = the next calendar day
   - "this Friday" or "Friday" = the NEXT upcoming Friday from today
   - "next Monday" = the Monday of NEXT week
   - IMPORTANT: Double-check day-of-week matches the calculated date.
4. Extract duration if mentioned (default 30 minutes).
5. Extract meeting title/agenda if mentioned (default: "Meeting with [invitee full name]").
6. If the request is NOT about scheduling a meeting, set "not_meeting_request" to true.

Return ONLY a single JSON object, nothing else (no markdown, no explanation, no extra text):
{{
    "is_meeting_request": true/false,
    "not_meeting_request_response": "helpful response if not a meeting request",
    "invitee_id": <user_id or null>,
    "invitee_name": "<FULL NAME from the company users list>",
    "user_not_found": "<unmatched name or null>",
    "proposed_time": "<ISO datetime string YYYY-MM-DDTHH:MM:SS or null>",
    "duration_minutes": <number>,
    "title": "<meeting title>",
    "description": "<meeting agenda/description>",
    "parse_error": "<error message if cannot parse, else null>"
}}"""

        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.1, max_tokens=500)
            # Clean response - extract JSON
            text = response.strip()
            # Remove markdown code fences if present
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```\s*$", "", text)

            # Extract the first JSON object from the response (LLM may add extra text after)
            # Find the first { and its matching }
            brace_start = text.find('{')
            if brace_start != -1:
                depth = 0
                for i in range(brace_start, len(text)):
                    if text[i] == '{':
                        depth += 1
                    elif text[i] == '}':
                        depth -= 1
                        if depth == 0:
                            text = text[brace_start:i + 1]
                            break

            parsed = json.loads(text)
            logger.info(f"Parsed meeting request: {parsed}")
            return parsed
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to parse meeting request: {e}\nRaw response: {response[:500] if 'response' in dir() else 'N/A'}")
            return {
                "is_meeting_request": True,
                "parse_error": "I couldn't understand your meeting request. Please try again with details like: 'Schedule a meeting with [name] on [date] at [time]'",
            }

    def generate_response(self, action: str, meeting_data: Dict, company_users: List[Dict] = None) -> str:
        """
        Generate a natural language response for meeting actions.

        Args:
            action: The action taken (scheduled, accepted, rejected, counter_proposed, withdrawn, error)
            meeting_data: Meeting details
            company_users: Available users for context

        Returns:
            str: Natural language response
        """
        if action == "scheduled":
            invitee = meeting_data.get("invitee_name", "the invitee")
            time_str = meeting_data.get("proposed_time", "")
            try:
                dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                time_display = dt.strftime("%A, %B %d, %Y at %I:%M %p")
            except Exception:
                time_display = time_str
            duration = meeting_data.get("duration_minutes", 30)
            title = meeting_data.get("title", "Meeting")

            return (
                f"**Meeting Scheduled Successfully!**\n\n"
                f"**Title:** {title}\n"
                f"**With:** {invitee}\n"
                f"**When:** {time_display}\n"
                f"**Duration:** {duration} minutes\n\n"
                f"An email notification has been sent to **{invitee}**. "
                f"They can accept or reject the meeting from their dashboard. "
                f"You'll be notified of their response."
            )

        elif action == "user_not_found":
            name = meeting_data.get("user_not_found", "the user")
            users_str = ""
            if company_users:
                users_str = "\n\nAvailable team members:\n" + "\n".join(
                    f"- **{u['full_name']}** ({u['email']})"
                    for u in company_users[:10]
                )
            return (
                f"I couldn't find a user named **\"{name}\"** in your company. "
                f"Please check the name and try again.{users_str}"
            )

        elif action == "not_meeting_request":
            return meeting_data.get(
                "not_meeting_request_response",
                "I'm the Meeting Scheduler assistant. I can help you:\n\n"
                "- **Schedule a meeting**: \"Schedule a meeting with [name] on [date] at [time]\"\n"
                "- **View meetings**: \"Show my upcoming meetings\"\n"
                "- **Withdraw a meeting**: \"Cancel meeting #[id]\"\n\n"
                "Try something like: *\"Schedule a meeting with John tomorrow at 2 PM\"*"
            )

        elif action == "parse_error":
            return (
                meeting_data.get("parse_error", "") + "\n\n"
                "**Examples:**\n"
                "- \"Schedule a meeting with Sarah on Monday at 3 PM\"\n"
                "- \"Set up a 1-hour meeting with Ahmed tomorrow at 10 AM to discuss the API design\"\n"
                "- \"Meet with developer1 next Friday at 2:30 PM\""
            )

        elif action == "past_time":
            return (
                "The proposed meeting time is in the past. "
                "Please suggest a future date and time."
            )

        elif action == "self_meeting":
            return "You cannot schedule a meeting with yourself. Please specify a different team member."

        return "Meeting request processed."

    def process(self, message: str, company_users: List[Dict], current_time: str,
                organizer_id: int = None) -> Dict:
        """
        Main entry point: parse message and return structured result.
        Uses deterministic user matching first, then LLM for date/time parsing.
        """
        # ── Step 1: Deterministic user matching (before LLM) ──
        user_match = self._find_user_in_message(message, company_users)
        logger.info(f"[MEETING] User match result: {user_match['match']}, matched_name={user_match.get('matched_name')}, user={user_match['user']['full_name'] if user_match.get('user') else 'None'}")

        # Handle ambiguous match — ask user to clarify
        if user_match["match"] == "ambiguous":
            candidates = user_match["candidates"]
            candidates_str = "\n".join(
                f"- **{c['full_name']}** ({c['email']})"
                for c in candidates
            )
            matched = user_match.get("matched_name", "that name")
            return {
                "action": "ambiguous_user",
                "response": (
                    f"I found multiple users matching **\"{matched}\"**. "
                    f"Which one did you mean?\n\n{candidates_str}\n\n"
                    f"Please use their full name or email to clarify."
                ),
                "data": None,
            }

        # Handle no match found
        if user_match["match"] == "not_found":
            all_users_str = "\n".join(
                f"- **{u['full_name']}** ({u['email']})"
                for u in company_users[:15]
            )
            return {
                "action": "user_not_found",
                "response": (
                    f"I couldn't find that user in your company.\n\n"
                    f"Available team members:\n{all_users_str}"
                ),
                "data": None,
            }

        # ── Step 2: LLM parsing for date/time and other details ──
        parsed = self.parse_meeting_request(message, company_users, current_time)

        # Not a meeting request
        if not parsed.get("is_meeting_request"):
            response = self.generate_response("not_meeting_request", parsed, company_users)
            return {"action": "not_meeting_request", "response": response, "data": None}

        # Parse error
        if parsed.get("parse_error"):
            response = self.generate_response("parse_error", parsed)
            return {"action": "parse_error", "response": response, "data": None}

        # ── Step 3: Override LLM's user match with our deterministic match ──
        if user_match["match"] in ("exact", "single"):
            matched_user = user_match["user"]
            parsed["invitee_id"] = matched_user["id"]
            parsed["invitee_name"] = matched_user["full_name"]
            parsed["user_not_found"] = None
        elif parsed.get("user_not_found") and not parsed.get("invitee_id"):
            # LLM also couldn't find — try one more time with LLM's extracted name
            llm_name = parsed.get("user_not_found") or parsed.get("invitee_name")
            if llm_name:
                retry_match = self._match_user(llm_name, company_users)
                if retry_match["match"] in ("exact", "single"):
                    parsed["invitee_id"] = retry_match["user"]["id"]
                    parsed["invitee_name"] = retry_match["user"]["full_name"]
                    parsed["user_not_found"] = None
                elif retry_match["match"] == "ambiguous":
                    candidates_str = "\n".join(
                        f"- **{c['full_name']}** ({c['email']})"
                        for c in retry_match["candidates"]
                    )
                    return {
                        "action": "ambiguous_user",
                        "response": (
                            f"I found multiple users matching **\"{llm_name}\"**. "
                            f"Which one did you mean?\n\n{candidates_str}\n\n"
                            f"Please use their full name or email to clarify."
                        ),
                        "data": None,
                    }
                else:
                    response = self.generate_response("user_not_found", parsed, company_users)
                    return {"action": "user_not_found", "response": response, "data": None}

        # Still no invitee after all matching attempts
        if not parsed.get("invitee_id"):
            response = self.generate_response("user_not_found", parsed, company_users)
            return {"action": "user_not_found", "response": response, "data": None}

        # Self-meeting check
        if organizer_id and int(parsed["invitee_id"]) == int(organizer_id):
            response = self.generate_response("self_meeting", parsed)
            return {"action": "self_meeting", "response": response, "data": None}

        # No time specified
        if not parsed.get("proposed_time"):
            return {
                "action": "parse_error",
                "response": "I understood you want to meet with **" +
                            (parsed.get("invitee_name") or "someone") +
                            "**, but I couldn't determine the date/time. "
                            "Please specify when, e.g., *\"tomorrow at 2 PM\"* or *\"March 28 at 10 AM\"*.",
                "data": None,
            }

        # Validate proposed time is in the future
        try:
            proposed = datetime.fromisoformat(parsed["proposed_time"].replace("Z", "+00:00"))
            if timezone.is_naive(proposed):
                proposed = timezone.make_aware(proposed)
            if proposed < timezone.now():
                response = self.generate_response("past_time", parsed)
                return {"action": "past_time", "response": response, "data": None}
        except Exception:
            pass

        # ── Step 4: Build meeting data with verified user info ──
        meeting_data = {
            "invitee_id": parsed["invitee_id"],
            "invitee_name": parsed.get("invitee_name"),
            "proposed_time": parsed["proposed_time"],
            "duration_minutes": parsed.get("duration_minutes", 30),
            "title": parsed.get("title", f"Meeting with {parsed.get('invitee_name', 'team member')}"),
            "description": parsed.get("description", ""),
        }

        response = self.generate_response("scheduled", meeting_data, company_users)
        return {"action": "schedule", "response": response, "data": meeting_data}

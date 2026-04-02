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

    def _find_all_users_in_message(self, message: str, company_users: List[Dict]) -> List[Dict]:
        """
        Find ALL company users mentioned in the message. Returns a list of matched user dicts.
        Used for multi-participant meetings like "schedule with hamza, sarah, and developer1".
        """
        msg_lower = message.lower()
        found_users = []
        found_ids = set()

        for u in company_users:
            full_name = u["full_name"].lower()
            email = u["email"].lower()
            email_prefix = email.split("@")[0] if "@" in email else email
            name_parts = [p for p in full_name.split() if len(p) >= 3]

            matched = False
            # Full name match
            if re.search(r'\b' + re.escape(full_name) + r'\b', msg_lower):
                matched = True
            # Email match
            elif email in msg_lower:
                matched = True
            # Email prefix match
            elif len(email_prefix) >= 3 and re.search(r'\b' + re.escape(email_prefix) + r'\b', msg_lower):
                matched = True
            # Name part match (first/last name)
            elif any(re.search(r'\b' + re.escape(part) + r'\b', msg_lower) for part in name_parts):
                matched = True

            if matched and u["id"] not in found_ids:
                found_users.append(u)
                found_ids.add(u["id"])

        return found_users

    def check_conflicts(self, user_ids: List[int], proposed_time, duration_minutes: int = 30) -> List[Dict]:
        """
        Check if any of the given users have conflicting meetings at the proposed time.
        Returns a list of conflicts: [{ "user_id": int, "user_name": str, "conflicting_meeting": str, "time": str }]
        """
        from project_manager_agent.models import ScheduledMeeting, MeetingParticipant
        from django.db.models import Q

        if not proposed_time:
            return []

        # Calculate meeting window
        meeting_end = proposed_time + timedelta(minutes=duration_minutes)

        conflicts = []
        for uid in user_ids:
            # Find meetings where this user is a participant and time overlaps
            participant_meeting_ids = MeetingParticipant.objects.filter(
                user_id=uid,
                status__in=['pending', 'accepted'],
            ).values_list('meeting_id', flat=True)

            overlapping = ScheduledMeeting.objects.filter(
                Q(id__in=participant_meeting_ids) | Q(invitee_id=uid),
                status__in=['pending', 'accepted', 'counter_proposed', 'partially_accepted'],
            ).exclude(status='withdrawn')

            for m in overlapping:
                m_start = m.proposed_time
                m_end = m_start + timedelta(minutes=m.duration_minutes)

                # Check overlap: meeting A overlaps B if A starts before B ends AND A ends after B starts
                if proposed_time < m_end and meeting_end > m_start:
                    try:
                        from django.contrib.auth import get_user_model
                        User = get_user_model()
                        user = User.objects.get(id=uid)
                        user_name = user.get_full_name() or user.username
                    except Exception:
                        user_name = f"User {uid}"

                    conflicts.append({
                        "user_id": uid,
                        "user_name": user_name,
                        "conflicting_meeting": m.title,
                        "conflicting_time": m_start.strftime("%I:%M %p") + " - " + m_end.strftime("%I:%M %p"),
                        "conflicting_date": m_start.strftime("%b %d, %Y"),
                    })
                    break  # One conflict per user is enough

        return conflicts

    def suggest_available_slots(self, user_ids: List[int], date, duration_minutes: int = 30) -> List[str]:
        """
        Suggest available time slots on a given date for all specified users.
        Returns list of available slot strings like "10:00 AM", "2:00 PM".
        """
        from project_manager_agent.models import ScheduledMeeting, MeetingParticipant
        from django.db.models import Q

        # Get all meetings for these users on the given date
        day_start = datetime.combine(date, datetime.min.time())
        day_end = datetime.combine(date, datetime.max.time())
        if timezone.is_naive(day_start):
            day_start = timezone.make_aware(day_start)
            day_end = timezone.make_aware(day_end)

        # Collect all busy windows per user
        busy_windows = []  # list of (start, end) tuples
        for uid in user_ids:
            participant_meeting_ids = MeetingParticipant.objects.filter(
                user_id=uid, status__in=['pending', 'accepted'],
            ).values_list('meeting_id', flat=True)

            day_meetings = ScheduledMeeting.objects.filter(
                Q(id__in=participant_meeting_ids) | Q(invitee_id=uid),
                status__in=['pending', 'accepted', 'counter_proposed', 'partially_accepted'],
                proposed_time__gte=day_start,
                proposed_time__lte=day_end,
            )
            for m in day_meetings:
                busy_windows.append((m.proposed_time, m.proposed_time + timedelta(minutes=m.duration_minutes)))

        # Business hours: 9 AM to 6 PM, slots every 30 min
        slots = []
        for hour in range(9, 18):
            for minute in [0, 30]:
                slot_start = datetime.combine(date, datetime.min.time().replace(hour=hour, minute=minute))
                if timezone.is_naive(slot_start):
                    slot_start = timezone.make_aware(slot_start)
                slot_end = slot_start + timedelta(minutes=duration_minutes)

                # Check if slot overlaps any busy window
                has_conflict = any(
                    slot_start < busy_end and slot_end > busy_start
                    for busy_start, busy_end in busy_windows
                )
                if not has_conflict:
                    slots.append(slot_start.strftime("%I:%M %p"))

        return slots[:8]

    def generate_occurrence_dates(self, first_time, recurrence: str, end_date=None, max_occurrences: int = 12) -> List:
        """
        Generate future occurrence datetimes for a recurring meeting.
        Returns list of datetime objects (excluding the first one which is already created).
        """
        if recurrence == 'none' or not recurrence:
            return []

        # Default end date: 3 months from first meeting
        if not end_date:
            end_date = (first_time + timedelta(days=90)).date()

        dates = []
        current = first_time

        for _ in range(max_occurrences * 2):  # safety limit
            if recurrence == 'daily':
                current = current + timedelta(days=1)
            elif recurrence == 'weekly':
                current = current + timedelta(weeks=1)
            elif recurrence == 'weekly_weekdays':
                current = current + timedelta(days=1)
                # Skip weekends
                while current.weekday() >= 5:  # 5=Sat, 6=Sun
                    current = current + timedelta(days=1)
            elif recurrence == 'biweekly':
                current = current + timedelta(weeks=2)
            elif recurrence == 'monthly':
                # Add ~30 days, then snap to same day-of-month
                month = current.month + 1
                year = current.year
                if month > 12:
                    month = 1
                    year += 1
                day = min(current.day, 28)  # safe for all months
                current = current.replace(year=year, month=month, day=day)
            else:
                break

            if current.date() > end_date:
                break

            dates.append(current)

            if len(dates) >= max_occurrences:
                break

        return dates

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
5. Extract meeting title if mentioned (default: "Meeting with [invitee full name]").
6. Extract agenda/discussion topics if mentioned. Look for phrases like "to discuss...", "about...", "agenda:", "topics:", "regarding...", "to review...". Split into individual items.
7. If the request is NOT about scheduling a meeting, set "not_meeting_request" to true.
7. Detect if the meeting is recurring. Look for patterns like:
   - "every Monday", "every day", "every weekday", "daily", "weekly" → recurring
   - "every 2 weeks", "biweekly", "fortnightly" → biweekly
   - "every month", "monthly" → monthly
   - If recurring, extract recurrence type and optional end date ("for 4 weeks", "until June", "for 3 months")
   - If NOT recurring, set recurrence to "none"

Return ONLY a single JSON object, nothing else (no markdown, no explanation, no extra text):
{{
    "is_meeting_request": true/false,
    "not_meeting_request_response": "helpful response if not a meeting request",
    "invitees": [
        {{"id": <user_id>, "name": "<FULL NAME from company users list>"}}
    ],
    "users_not_found": ["<unmatched name 1>", "<unmatched name 2>"],
    "proposed_time": "<ISO datetime string YYYY-MM-DDTHH:MM:SS or null>",
    "duration_minutes": <number>,
    "recurrence": "none|daily|weekly|weekly_weekdays|biweekly|monthly",
    "recurrence_end_date": "<YYYY-MM-DD or null>",
    "title": "<meeting title>",
    "description": "<brief description>",
    "agenda": ["discussion topic 1", "discussion topic 2"],
    "parse_error": "<error message if cannot parse, else null>"
}}"""

        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.1, max_tokens=700)
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
            invitees = meeting_data.get("invitee_names", [])
            invitee_str = ", ".join(f"**{n}**" for n in invitees) if invitees else meeting_data.get("invitee_name", "the invitee")
            time_str = meeting_data.get("proposed_time", "")
            try:
                dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                time_display = dt.strftime("%A, %B %d, %Y at %I:%M %p")
            except Exception:
                time_display = time_str
            duration = meeting_data.get("duration_minutes", 30)
            title = meeting_data.get("title", "Meeting")
            count = len(invitees) if invitees else 1

            recurrence_label = meeting_data.get("_recurrence_label")
            recurrence_line = f"**Recurring:** {recurrence_label}\n" if recurrence_label else ""
            end_date = meeting_data.get("recurrence_end_date")
            end_line = f"**Until:** {end_date}\n" if end_date and recurrence_label else ""

            agenda_items = meeting_data.get("agenda", [])
            agenda_line = ""
            if agenda_items:
                agenda_line = "\n**Agenda:**\n" + "\n".join(f"- {a['item']}" for a in agenda_items) + "\n"

            return (
                f"**Meeting Scheduled Successfully!**\n\n"
                f"**Title:** {title}\n"
                f"**With:** {invitee_str}\n"
                f"**When:** {time_display}\n"
                f"**Duration:** {duration} minutes\n"
                f"{recurrence_line}{end_line}{agenda_line}\n"
                f"{'Notifications have' if count > 1 else 'A notification has'} been sent to {invitee_str}. "
                f"{'Each participant can' if count > 1 else 'They can'} accept or reject from their dashboard. "
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
        Supports multi-participant meetings ("schedule with hamza, sarah, and developer1").
        Uses deterministic user matching first, then LLM for date/time parsing.
        """
        # ── Step 1: Deterministic multi-user matching ──
        all_matched = self._find_all_users_in_message(message, company_users)
        single_match = self._find_user_in_message(message, company_users)
        logger.info(f"[MEETING] Multi-match found {len(all_matched)} users: {[u['full_name'] for u in all_matched]}")

        # Handle ambiguous single match (e.g. "hamza" matches 2 people)
        if not all_matched and single_match["match"] == "ambiguous":
            candidates = single_match["candidates"]
            candidates_str = "\n".join(f"- **{c['full_name']}** ({c['email']})" for c in candidates)
            return {
                "action": "ambiguous_user",
                "response": f"I found multiple users matching **\"{single_match.get('matched_name', 'that name')}\"**. Which one did you mean?\n\n{candidates_str}\n\nPlease use their full name or email to clarify.",
                "data": None,
            }

        # Handle no match found
        if not all_matched and single_match["match"] == "not_found":
            all_users_str = "\n".join(f"- **{u['full_name']}** ({u['email']})" for u in company_users[:15])
            return {
                "action": "user_not_found",
                "response": f"I couldn't find that user in your company.\n\nAvailable team members:\n{all_users_str}",
                "data": None,
            }

        # If multi-match found nothing but single match did, use single
        if not all_matched and single_match["match"] in ("exact", "single"):
            all_matched = [single_match["user"]]

        # ── Step 2: LLM parsing for date/time and other details ──
        parsed = self.parse_meeting_request(message, company_users, current_time)

        if not parsed.get("is_meeting_request"):
            response = self.generate_response("not_meeting_request", parsed, company_users)
            return {"action": "not_meeting_request", "response": response, "data": None}

        if parsed.get("parse_error"):
            response = self.generate_response("parse_error", parsed)
            return {"action": "parse_error", "response": response, "data": None}

        # ── Step 3: Merge deterministic match with LLM results ──
        # If deterministic matching found users, prefer that over LLM
        if all_matched:
            invitees = [{"id": u["id"], "name": u["full_name"]} for u in all_matched]
        elif parsed.get("invitees"):
            # Use LLM-detected invitees, but verify each one
            invitees = []
            for inv in parsed["invitees"]:
                verify = self._find_user_in_message(f"meet with {inv.get('name', '')}", company_users)
                if verify["match"] in ("exact", "single"):
                    invitees.append({"id": verify["user"]["id"], "name": verify["user"]["full_name"]})
        else:
            # Fallback: try LLM's users_not_found
            not_found = parsed.get("users_not_found", [])
            if not_found:
                not_found_str = ", ".join(f"**{n}**" for n in not_found)
                all_users_str = "\n".join(f"- **{u['full_name']}** ({u['email']})" for u in company_users[:15])
                return {
                    "action": "user_not_found",
                    "response": f"I couldn't find: {not_found_str}\n\nAvailable team members:\n{all_users_str}",
                    "data": None,
                }
            response = self.generate_response("user_not_found", parsed, company_users)
            return {"action": "user_not_found", "response": response, "data": None}

        if not invitees:
            response = self.generate_response("user_not_found", parsed, company_users)
            return {"action": "user_not_found", "response": response, "data": None}

        # No time specified
        invitee_names = [i["name"] for i in invitees]
        if not parsed.get("proposed_time"):
            return {
                "action": "parse_error",
                "response": f"I understood you want to meet with {', '.join(f'**{n}**' for n in invitee_names)}, but I couldn't determine the date/time. Please specify when, e.g., *\"tomorrow at 2 PM\"*.",
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

        # ── Step 4: Build meeting data ──
        if len(invitee_names) == 1:
            title_default = f"Meeting with {invitee_names[0]}"
        else:
            title_default = f"Meeting with {', '.join(invitee_names[:3])}" + (f" +{len(invitee_names)-3} more" if len(invitee_names) > 3 else "")

        recurrence = parsed.get("recurrence", "none") or "none"
        recurrence_end_date = parsed.get("recurrence_end_date")

        # Build structured agenda from LLM output
        raw_agenda = parsed.get("agenda") or []
        if isinstance(raw_agenda, list):
            agenda_items = [{"item": str(a), "done": False} for a in raw_agenda if a]
        else:
            agenda_items = []

        meeting_data = {
            "invitees": invitees,
            "invitee_names": invitee_names,
            "proposed_time": parsed["proposed_time"],
            "duration_minutes": parsed.get("duration_minutes", 30),
            "title": parsed.get("title") or title_default,
            "description": parsed.get("description") or "",
            "agenda": agenda_items,
            "recurrence": recurrence,
            "recurrence_end_date": recurrence_end_date,
        }

        # Add recurrence info to the response text
        if recurrence != "none":
            recurrence_labels = {
                "daily": "Daily", "weekly": "Weekly", "weekly_weekdays": "Weekdays (Mon-Fri)",
                "biweekly": "Every 2 weeks", "monthly": "Monthly",
            }
            meeting_data["_recurrence_label"] = recurrence_labels.get(recurrence, recurrence)

        response = self.generate_response("scheduled", meeting_data, company_users)
        return {"action": "schedule", "response": response, "data": meeting_data}

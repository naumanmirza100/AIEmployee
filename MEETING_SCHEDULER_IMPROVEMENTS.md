# Meeting Scheduler Agent — Improvement Roadmap

## Status Legend
- [ ] Not started
- [x] Completed

---

## Phase 1: High Impact (Core Functionality)

### 1. Multi-Participant Meetings
- [x] Update `ScheduledMeeting` model to support multiple invitees (`MeetingParticipant` model)
- [x] Update meeting scheduler agent to parse multiple names from a single request ("schedule a meeting with hamza, sarah, and developer1")
- [x] Add `_find_all_users_in_message()` to return multiple matched users
- [x] All invitees get notified independently (in-app + email)
- [x] Meeting status derived from all participant statuses (`update_overall_status()`)
- [x] Update frontend to show per-participant accept/reject status badges
- [x] Update project user dashboard to show multi-participant meetings with `my_status`

### 2. Recurring Meetings
- [x] Add `recurrence` field to `ScheduledMeeting` (daily, weekly, weekly_weekdays, biweekly, monthly)
- [x] Add `recurrence_end_date` and `parent_meeting` FK fields
- [x] Agent detects recurring language ("every Monday", "daily at 9 AM", "weekly standup", "biweekly")
- [x] LLM prompt extracts recurrence type and end date ("for 4 weeks", "until June")
- [x] `generate_occurrence_dates()` creates future dates (up to 12 occurrences, 3 months default)
- [x] API auto-creates child meeting instances with participants for each occurrence
- [x] Frontend shows recurring badge with type and occurrence count
- [ ] "Cancel this occurrence" vs "Cancel all future occurrences" options (future enhancement)

### 3. Calendar Conflict Detection
- [x] Before creating a meeting, query existing meetings for all invitees at the proposed time
- [x] If conflict found, return: "developer1 has 'Meeting X' at 2-3 PM. Available slots: 10 AM, 4 PM."
- [x] `check_conflicts(user_ids, proposed_time, duration)` method checks all participants
- [x] `suggest_available_slots(user_ids, date, duration)` finds free 30-min windows in business hours (9 AM - 6 PM)
- [x] Duration-aware overlap detection (not just start time)
- [x] Conflict response shown in chat with available slot suggestions

### 4. Meeting Agenda from Chat
- [x] LLM prompt extracts agenda from "to discuss...", "about...", "agenda:", "topics:", "regarding...", "to review..."
- [x] `agenda` JSONField on `ScheduledMeeting` stores structured items: `[{"item": "...", "done": false}]`
- [x] Agent splits topics into individual agenda items in `process()`
- [x] Chat response shows agenda as bullet list
- [x] Company user meeting card shows agenda checklist
- [x] Project user meeting card shows agenda checklist
- [x] Email notification includes agenda as HTML list
- [x] Recurring child meetings inherit agenda from parent
- [ ] Allow editing agenda after creation (future enhancement)

### 5. Google Calendar / Outlook Integration (.ics)
- [x] `ics_generator.py` — generates RFC 5545 compliant iCalendar files
- [x] Includes VEVENT with DTSTART, DTEND, SUMMARY, DESCRIPTION, ORGANIZER, ATTENDEE fields
- [x] ATTENDEE includes PARTSTAT (NEEDS-ACTION, ACCEPTED, DECLINED, TENTATIVE)
- [x] Agenda items included in DESCRIPTION field
- [x] RRULE generated for recurring meetings (DAILY, WEEKLY, BIWEEKLY, MONTHLY)
- [x] VALARM with 15-minute reminder
- [x] `.ics` attached to email when meeting is scheduled (METHOD:REQUEST)
- [x] `.ics` attached to email when meeting is confirmed/accepted (METHOD:REQUEST, STATUS:CONFIRMED)
- [x] `.ics` attached to email when meeting is withdrawn/cancelled (METHOD:CANCEL, STATUS:CANCELLED)
- [x] `_send_meeting_email` upgraded to use `EmailMultiAlternatives` for attachment support
- [ ] Optional: Google Calendar API direct integration (OAuth2 — future enhancement)

---

## Phase 2: Medium Impact (UX & Workflow)

### 6. Smart Time Suggestions
- [ ] When user says "sometime this week" or doesn't specify a time, agent suggests 3-4 available slots
- [ ] Check both organizer's and invitee's existing meetings to find free windows
- [ ] Prefer business hours (9 AM - 6 PM) and avoid lunch (12-1 PM)
- [ ] "Pick a time" response with clickable slot options in the chat
- [ ] Consider meeting duration when suggesting slots

### 7. Meeting Reminders
- [ ] Celery periodic task that checks for upcoming meetings
- [ ] Send email reminder 1 hour before the meeting
- [ ] Send in-app notification 15 minutes before the meeting
- [ ] Add `reminder_sent` boolean fields to avoid duplicate reminders
- [ ] Allow users to configure reminder preferences (1hr, 30min, 15min, none)

### 8. Meeting Notes Linking
- [ ] After a meeting's scheduled time passes, show a "Add Meeting Notes" button on the meeting card
- [ ] Clicking it opens the Meeting Notes Analyzer pre-filled with meeting context (title, participants, agenda)
- [ ] Store the link between `ScheduledMeeting` and the generated notes
- [ ] Show "Notes available" badge on meetings that have linked notes

### 9. Reschedule Flow (Simplified)
- [ ] Agent detects reschedule language: "move my meeting with hamza to Thursday", "reschedule to 4 PM"
- [ ] Directly updates the meeting time without going through reject/counter cycle
- [ ] Sends notification to invitee: "Meeting rescheduled to [new time]"
- [ ] Invitee can still accept or reject the new time
- [ ] Chat shows: "Meeting with hamza rescheduled from Mon 2PM to Thu 4PM"

### 10. Meeting Duration Intelligence
- [ ] Track actual vs scheduled duration for completed meetings
- [ ] After 5+ meetings with same invitee, calculate average actual duration
- [ ] If user schedules 30 min but average is 45 min, suggest: "Your meetings with hamza typically run 45 min. Schedule for 45 min?"
- [ ] Store duration stats per user pair
- [ ] Default duration suggestions based on meeting type (standup=15min, 1on1=30min, review=60min)

---

## Phase 3: Nice to Have (Polish)

### 11. Meeting Search in Chat
- [ ] Agent detects query language: "show my meetings this week", "do I have anything with hamza?", "what's on my calendar tomorrow?"
- [ ] Query `ScheduledMeeting` based on date range, invitee name, status
- [ ] Return formatted list in the chat (not just redirect to Meetings tab)
- [ ] Support filters: "show pending meetings", "show meetings next week"

### 12. Time Zone Awareness
- [ ] Add `timezone` field to `UserProfile` and `CompanyUser` models (or use existing if present)
- [ ] Store meeting times in UTC, display in each user's local timezone
- [ ] When scheduling, agent confirms: "That's 2 PM PKT / 9 AM UTC. Correct?"
- [ ] Email notifications show time in recipient's timezone
- [ ] Handle DST transitions correctly

### 13. Meeting Status Summary Widget
- [ ] Small card/badge on the dashboard overview: "3 pending, 2 accepted, 1 counter-proposed"
- [ ] Quick-access link to the Meetings tab
- [ ] Show next upcoming meeting with countdown: "Next: Meeting with hamza in 2 hours"
- [ ] Auto-refresh every 60 seconds

### 14. Auto-Withdraw Stale Meetings
- [ ] Celery periodic task: check meetings in `pending` status older than 48 hours
- [ ] Send reminder notification to invitee: "Reminder: You have a pending meeting request from [organizer]"
- [ ] After 72 hours with no response, notify organizer: "No response from [invitee]. Withdraw or send another reminder?"
- [ ] Optional auto-withdraw after configurable timeout (default: 7 days)
- [ ] Don't auto-withdraw if meeting time hasn't passed yet

### 15. Meeting Templates
- [ ] Predefined templates: Sprint Review (1hr, whole team), Daily Standup (15min, whole team), 1-on-1 (30min), Design Review (45min)
- [ ] Agent detects template language: "schedule a sprint review", "set up a standup"
- [ ] Auto-fills duration, agenda, and suggests invitees based on project team
- [ ] Allow company users to create custom templates
- [ ] Templates stored in DB, editable from frontend

---

## Implementation Priority Order

| Priority | Feature | Effort | Impact |
|----------|---------|--------|--------|
| 1 | Multi-Participant Meetings | High | High |
| 2 | Calendar Conflict Detection | Medium | High |
| 3 | Recurring Meetings | High | High |
| 4 | Meeting Reminders | Low | Medium |
| 5 | Reschedule Flow | Low | Medium |
| 6 | Meeting Search in Chat | Low | Medium |
| 7 | Meeting Agenda from Chat | Medium | Medium |
| 8 | .ics Calendar Integration | Medium | High |
| 9 | Smart Time Suggestions | Medium | Medium |
| 10 | Auto-Withdraw Stale | Low | Low |
| 11 | Meeting Status Widget | Low | Low |
| 12 | Meeting Templates | Medium | Medium |
| 13 | Meeting Notes Linking | Low | Medium |
| 14 | Duration Intelligence | Medium | Low |
| 15 | Time Zone Awareness | High | Medium |

---

## Notes
- All features should maintain backward compatibility with existing meetings
- Multi-participant is the biggest model change — do it first before other features build on top
- .ics integration makes the product feel professional — high perceived value for clients
- Reminders require Celery to be running (already configured in this project)

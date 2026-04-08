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
- [x] When user doesn't specify a time, agent suggests available slots for the next 3 days
- [x] Uses `suggest_available_slots()` to check all participants' existing meetings
- [x] Business hours only (9 AM - 6 PM), 30-min increments
- [x] Shows slots grouped by day in the chat response
- [x] Duration-aware slot checking

### 7. Meeting Reminders
- [x] Celery periodic task `send_meeting_reminders` runs every 5 minutes
- [x] Sends 1-hour reminder (in-app notification + email) to organizer and all participants
- [x] Sends 15-minute reminder (in-app notification + email)
- [x] Duplicate prevention using reminder_key in notification data
- [x] Added to `CELERY_BEAT_SCHEDULE` in settings.py

### 8. Meeting Notes Linking
- [x] Past accepted meetings show "Meeting completed — add notes in AI Tools → Meeting Notes tab" prompt
- [ ] Pre-fill Meeting Notes Analyzer with meeting context (future enhancement)
- [ ] Store link between meeting and generated notes (future enhancement)

### 9. Reschedule Flow (Simplified)
- [x] Agent detects reschedule keywords: "reschedule", "move my meeting", "change the time", "postpone"
- [x] Extracts new time + invitee name from message
- [x] Finds the most recent active meeting with that invitee and updates the time directly
- [x] Sends notification + email to all participants: "Meeting rescheduled from [old] to [new]"
- [x] Chat shows: "Meeting rescheduled from Mon 2PM to Thu 4PM. All participants notified."

### 10. Meeting Duration Intelligence
- [x] Added `actual_duration_minutes` field to `ScheduledMeeting` model
- [ ] UI for marking actual duration after meeting ends (future enhancement)
- [ ] Duration suggestion based on historical averages (future enhancement)

---

## Phase 3: Nice to Have (Polish)

### 11. Meeting Search in Chat
- [x] `_is_meeting_query()` detects query language: "show my meetings", "meetings this week", "do I have meetings with hamza?"
- [x] `search_meetings()` queries by: status (pending/accepted/rejected), time (today/tomorrow/this week/next week), person
- [x] Returns formatted meeting list with emojis, titles, times, participants, agenda in chat
- [x] Filters exclude withdrawn meetings by default

### 12. Time Zone Awareness
- [ ] `UserProfile.timezone` field exists but rarely populated
- [ ] Full timezone conversion deferred — times stored and displayed in server timezone
- [ ] Future: convert display times per-user when timezone is set

### 13. Meeting Status Summary Widget
- [x] Stats badges in Meetings tab header: pending count, accepted count, counter-proposed count
- [x] "Next meeting" display showing title + time of the next upcoming accepted meeting
- [x] Updates when meetings list refreshes

### 14. Auto-Withdraw Stale Meetings
- [x] Celery task `check_stale_meetings` runs daily
- [x] After 48 hours pending: sends reminder to organizer + pending participants
- [x] After 7 days pending: auto-withdraws meeting, notifies both organizer and participants
- [x] Duplicate reminder prevention using `reminder_key`
- [x] Added to `CELERY_BEAT_SCHEDULE`

### 15. Meeting Templates
- [x] 6 predefined templates: Daily Standup (15min), Sprint Review (1hr), Sprint Planning (1hr), Retrospective (45min), 1-on-1 (30min), Design Review (45min)
- [x] `_detect_template()` matches keywords in message ("standup", "sprint review", "1-on-1", etc.)
- [x] Auto-fills: title, duration, agenda items, recurrence type
- [x] Template defaults only apply when user hasn't explicitly specified those values
- [ ] Custom templates stored in DB (future enhancement)

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

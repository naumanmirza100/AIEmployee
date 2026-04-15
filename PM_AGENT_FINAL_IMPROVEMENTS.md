# Project Manager Agent — Final Improvements for Production Readiness

## Status Legend
- [ ] Not started
- [x] Completed

---

## Phase 1: CRITICAL (Must Fix Before Selling)

### 1. Silent Error Handling — Bare Except Clauses
**File:** `api/views/pm_agent.py` (lines 599, 624, 3190-3204)
- [x] Replaced all bare `except:` with specific exception types (`json.JSONDecodeError`, `ValueError`, `TypeError`)
- [x] Added `logger.debug()` for date parsing and JSON recovery failures
- [x] All error responses now return generic messages (not `str(e)`)
- [x] Audited bare excepts across pm_agent.py — 7 instances fixed

### 2. Placeholder Code in Knowledge QA Agent
**File:** `project_manager_agent/ai_agents/knowledge_qa_agent.py` (line 932)
- [x] Implemented `search_project_history()` — queries tasks by title/description matching
- [x] Implemented `get_project_summary()` — generates LLM summary from project stats
- [x] Implemented `provide_insights()` — returns overdue/blocked/unassigned/completion metrics

### 3. Input Validation on All Endpoints
**File:** `api/views/pm_agent.py`
- [x] Added `_validate_positive_number()` helper — checks positive, within bounds
- [x] Added `_validate_string()` helper — checks max length
- [x] Applied validation to `create_project_manual` budget fields (rejects negative/non-numeric)
- [ ] Validate file uploads: check magic bytes (future — low risk since files go to LLM only)

### 4. Security: Data Isolation Between Company Users
**File:** `api/views/pm_agent.py`
- [x] Meeting respond: changed `ScheduledMeeting.objects.get(id=meeting_id)` to include `organizer=company_user`
- [x] Project lookup in `project_pilot_from_file`: added `created_by_company_user=company_user` filter
- [x] All chat CRUD endpoints already filter by `company_user` — verified
- [x] Meeting list endpoint already filters by `organizer=company_user` — verified

### 5. N+1 Query Problems
**File:** `api/views/pm_agent.py` (chat list endpoints)
- [x] Added `prefetch_related('messages')` to: KQA chats, Project Pilot chats, Meeting Scheduler chats
- [x] Meeting queries already had `select_related('organizer', 'invitee')` — verified

### 6. Pagination Support
**File:** `api/views/pm_agent.py`
- [x] Added `limit` (max 100) and `offset` params to: KQA chat list, Project Pilot chat list, Meeting Scheduler chat list, meeting list
- [ ] Frontend "Load More" controls (future — current usage doesn't hit 50 items)

### Additional Phase 1 Fixes
- [x] Error messages: replaced all `str(e)` in 500 responses with generic "An internal error occurred" (15 instances)
- [x] Default owner: replaced `User.objects.first()` with `_get_project_owner(company_user)` at 3 locations
- [x] Database indexes: added indexes on PMKnowledgeQAChat, PMProjectPilotChat, PMMeetingSchedulerChat, ScheduledMeeting, PMNotification
- [x] Migration 0010_add_database_indexes applied

---

## Phase 2: HIGH (Bad UX / Bugs)

### 7. Error Messages Expose Internal Details
**Already done in Phase 1** — all `str(e)` replaced with generic messages.

### 8. Default Project Owner Issue
**Already done in Phase 1** — `_get_project_owner(company_user)` replaces `User.objects.first()`.

### 9. Frontend Error Boundaries
- [x] Created `ErrorBoundary` React component with "Something went wrong" fallback + "Try Again" button
- [x] Wrapped all 6 PM dashboard tabs: Project Pilot, Task Prioritization, Knowledge QA, Timeline & Gantt, Meeting Scheduler, AI Tools
- [x] Wrapped User Dashboard meetings tab
- [x] Render crashes now show a clean error UI instead of blank screen

### 10. File Upload Hardening
- [x] Server-side file size check: rejects files > 10MB before processing
- [x] Magic byte validation: PDF files must start with `%PDF`, DOCX with `PK` (ZIP signature)
- [x] Returns clear error: "File content does not match .pdf format" if magic bytes mismatch
- [x] Text sanitization: strips control characters, truncates at 50,000 chars to prevent LLM token overflow
- [x] Error messages no longer expose internal details ("Failed to extract text from file. Please ensure the file is not corrupted.")

### 11. Meeting Participant Validation
- [x] `user__is_active=True` filter added when fetching project users for meeting scheduling
- [x] Invitee User lookup includes `is_active=True` — inactive/deleted users can't be scheduled
- [x] Skips invalid invitee IDs with warning log instead of crashing

---

## Phase 3: MEDIUM (Polish for Production)

### 12. Database Indexes
**Already done in Phase 1** — 7 indexes added across 5 models.

### 13. Rate Limiting on LLM Endpoints
- [x] `PMLLMThrottle` class (30 requests/hour per user) using `SimpleRateThrottle`
- [x] Applied to: `project_pilot`, `knowledge_qa`, `task_prioritization`, `meeting_schedule`
- [x] Returns 429 Too Many Requests automatically via DRF
- [x] Configured in `REST_FRAMEWORK.DEFAULT_THROTTLE_RATES` in settings.py

### 14. API Response Standardization
- [x] All 500 error responses now use generic message (not `str(e)`)
- [x] All endpoints already follow `{ status, data, message }` pattern — verified
- [ ] Add `timestamp` field (future — minimal impact)

### 15. Audit Logging
- [x] `PMAuditLog` model: company_user, action, model_name, object_id, object_title, details (JSON), created_at
- [x] 14 action types defined: project/task CRUD, meeting events, priority updates
- [x] `_audit_log()` helper wired into: project creation (3 locations), task creation, meeting schedule/accept/reject/withdraw
- [x] `GET /project-manager/ai/audit-logs` endpoint with pagination + action filter
- [x] Index on `(company_user, -created_at)` for fast queries
- [ ] Frontend audit log viewer (future)

### 16. LLM Configuration Management
- [x] `PM_AGENT_LLM_CONFIG` dict in settings.py — per-agent overrides for model, temperature, max_tokens
- [x] `BaseAgent.__init__` reads agent-specific config by class name
- [x] `GROQ_FALLBACK_MODEL` setting — if primary model fails, tries fallback automatically
- [x] `self.total_tokens_used` counter on BaseAgent for cumulative tracking
- [x] Token usage captured per-request via `self.last_llm_usage`
- [ ] Per-company-user token budget caps (future — needs billing integration)

### 17. Task Assignment Capacity Check
- [x] Before task creation, checks assignee's active task count (todo/in_progress/review)
- [x] Warning generated if assignee has 10+ active tasks (logged, not blocking)
- [x] Audit log entry created for every task creation

### 18. Notification Cleanup
- [x] Celery task `cleanup_old_notifications` runs daily
- [x] Deletes read PMNotifications older than 30 days
- [x] Deletes read User Notifications older than 30 days
- [x] Caps PMNotifications at 200 per user (deletes oldest beyond that)
- [x] Added to `CELERY_BEAT_SCHEDULE`
- [ ] "Delete all read" button in frontend (future)

---

## Phase 4: LOW (Nice to Have Before Launch)

### 19. Loading States & Skeleton UI
- [x] Created reusable `Skeleton` component: `ChatList`, `MeetingList`, `MeetingCard`, `TaskList`, `StatsGrid`
- [x] Applied to Meeting Scheduler sidebar (chat list loading)
- [x] Applied to Meeting Scheduler meetings tab
- [x] Applied to User Dashboard meetings tab

### 20. Keyboard Shortcuts
- [x] Ctrl+Enter / Cmd+Enter to send in: Meeting Scheduler, Project Pilot, Knowledge QA
- [x] Enter (without shift) to send — already worked, now also supports Ctrl+Enter
- [x] Escape to close meeting respond panel

### 21. Export Functionality
- [x] Download .ics button on every meeting card in Meeting Scheduler
- [x] Frontend-side .ics generation (no backend round-trip needed)
- [x] Includes: title, time, duration, participants, agenda, 15-min reminder
- [ ] Export task prioritization as PDF (future)
- [ ] Export meeting list as CSV (future)

### 22. Onboarding Tour
- [x] Enhanced empty state in Meeting Scheduler with 5 clickable example prompts
- [x] Examples cover: scheduling, recurring, 1-on-1, viewing meetings, rescheduling
- [x] Click an example to auto-fill the input field
- [ ] Full guided tour with highlights (future — consider react-joyride)

### 23. Mobile Responsiveness
- [x] Meeting Scheduler sidebar auto-hides on screens < 768px
- [x] MediaQuery listener re-hides on resize to mobile
- [ ] Full responsive audit of all components at 375px (future)

### 24. Performance Monitoring
- [x] LLM call timing logged per request: `[LLM] AgentName | 1.23s | 450 tokens | model=llama-3.1-8b-instant`
- [x] Slow LLM warning: `[LLM SLOW]` logged if any call exceeds 5 seconds
- [x] Health check endpoint: `GET /api/project-manager/health`
  - Database connectivity + latency
  - LLM API key configured
  - Registered agent count + names
  - Overall status: `healthy` or `degraded`

---

## Implementation Priority Order

| Priority | Issue | Effort | Impact | Phase |
|----------|-------|--------|--------|-------|
| 1 | Input validation (3) | 2h | Critical | 1 |
| 2 | Security: data isolation (4) | 1.5h | Critical | 1 |
| 3 | Error messages exposure (7) | 1h | High | 2 |
| 4 | Silent error handling (1) | 1h | Critical | 1 |
| 5 | N+1 queries (5) | 1.5h | Critical | 1 |
| 6 | Pagination (6) | 2h | Critical | 1 |
| 7 | Default owner fix (8) | 1h | High | 2 |
| 8 | Frontend error boundaries (9) | 2h | High | 2 |
| 9 | Placeholder code removal (2) | 1h | Critical | 1 |
| 10 | File upload hardening (10) | 1.5h | High | 2 |
| 11 | Database indexes (12) | 1h | Medium | 3 |
| 12 | Rate limiting (13) | 2h | Medium | 3 |
| 13 | Audit logging (15) | 3h | Medium | 3 |
| 14 | API standardization (14) | 2h | Medium | 3 |
| 15 | LLM config management (16) | 3h | Medium | 3 |
| 16 | Notification cleanup (18) | 1h | Medium | 3 |
| 17 | Participant validation (11) | 1h | High | 2 |
| 18 | Capacity check (17) | 1h | Medium | 3 |
| 19 | Export functionality (21) | 4h | Low | 4 |
| 20 | Loading skeletons (19) | 2h | Low | 4 |
| 21 | Keyboard shortcuts (20) | 1h | Low | 4 |
| 22 | Onboarding tour (22) | 3h | Low | 4 |
| 23 | Mobile audit (23) | 3h | Low | 4 |
| 24 | Performance monitoring (24) | 2h | Low | 4 |

**Estimated total: ~45 hours**
- Phase 1 (Critical): ~9 hours
- Phase 2 (High): ~7 hours
- Phase 3 (Medium): ~13 hours
- Phase 4 (Low): ~15 hours

---

## Notes

- **Phase 1 is non-negotiable before any paid usage** — security and data integrity issues will cause legal liability
- **Phase 2 should be done before the first demo** — these are the bugs users will hit immediately
- **Phase 3 is for scale** — needed once you have 10+ active companies
- **Phase 4 is competitive edge** — differentiates from basic project management tools
- The LLM costs are currently untracked — **add token metering before billing users**

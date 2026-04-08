# Project Manager Agent — Final Improvements for Production Readiness

## Status Legend
- [ ] Not started
- [x] Completed

---

## Phase 1: CRITICAL (Must Fix Before Selling)

### 1. Silent Error Handling — Bare Except Clauses
**File:** `api/views/pm_agent.py` (lines 599, 624, 3190-3204)
- [ ] Replace all bare `except:` with specific exception types (`ValueError`, `TypeError`, `json.JSONDecodeError`)
- [ ] Add `logger.error()` for every caught exception
- [ ] Return user-friendly error messages instead of silently swallowing failures
- [ ] Audit all `except Exception as e: pass` patterns across the codebase

### 2. Placeholder Code in Knowledge QA Agent
**File:** `project_manager_agent/ai_agents/knowledge_qa_agent.py` (line 932)
- [ ] Remove or implement the `search_project_history()` placeholder that returns empty results
- [ ] Audit all agents for TODO/placeholder code that pretends to work

### 3. Input Validation on All Endpoints
**File:** `api/views/pm_agent.py`
- [ ] Validate budget fields (positive numbers, reasonable bounds)
- [ ] Validate date fields (proper format, not in unreasonable past/future)
- [ ] Validate string lengths (title max 255, description max 5000)
- [ ] Sanitize all user inputs that go into LLM prompts (prevent prompt injection)
- [ ] Validate file uploads: check magic bytes, not just extension
- [ ] Add file size validation before processing (not just frontend)

### 4. Security: Data Isolation Between Company Users
**File:** `api/views/pm_agent.py`
- [ ] Audit every endpoint to ensure `company_user` filter is applied
- [ ] Meeting respond endpoint: verify caller is actually the organizer (currently only checks ID)
- [ ] Ensure one company user cannot access another company user's chats, meetings, or notifications
- [ ] Add `company_user` check to meeting list endpoints
- [ ] Prevent IDOR (Insecure Direct Object Reference) on all ID-based lookups

### 5. N+1 Query Problems
**File:** `api/views/pm_agent.py` (chat list endpoints)
- [ ] Add `prefetch_related('messages')` to all chat list queries
- [ ] Add `select_related('organizer', 'invitee')` to all meeting queries
- [ ] Add `prefetch_related('participants__user')` to meeting list queries
- [ ] Profile and fix any other N+1 patterns

### 6. Pagination Support
**File:** `api/views/pm_agent.py`
- [ ] Add `limit` and `offset` query params to: chat lists, meeting lists, notification lists
- [ ] Cap `limit` at 100 to prevent memory exhaustion
- [ ] Return `total_count` in response for frontend pagination
- [ ] Update frontend to support "Load More" or pagination controls

---

## Phase 2: HIGH (Bad UX / Bugs)

### 7. Error Messages Expose Internal Details
**File:** `api/views/pm_agent.py`
- [ ] Replace all `str(e)` in error responses with generic messages
- [ ] Keep detailed errors in logs only (using `logger.exception()`)
- [ ] Example: "Failed to process request. Please try again." instead of SQL error traces

### 8. Default Project Owner Issue
**File:** `api/views/pm_agent.py` (line 2502)
- [ ] Stop using `User.objects.first()` as default owner
- [ ] Create a dedicated project owner from the company user's profile
- [ ] Or use the company user's first created Django User as owner
- [ ] Ensure multi-tenancy: each company user's projects have their own owner

### 9. Frontend Error Boundaries
**Files:** All `PaPerProjectFront/src/components/pm-agent/*.jsx`
- [ ] Add try-catch around all API calls with user-friendly toast messages
- [ ] Validate API response structure before accessing nested properties
- [ ] Add React Error Boundary component to catch render crashes
- [ ] Show "Something went wrong" fallback instead of blank screen

### 10. File Upload Hardening
**File:** `api/views/pm_agent.py` (line 2802)
- [ ] Validate file magic bytes (not just extension)
- [ ] Enforce server-side file size limit (10MB)
- [ ] Add timeout for file processing (PDF parsing can hang)
- [ ] Sanitize extracted text before sending to LLM

### 11. Meeting Participant Validation
**File:** `api/views/pm_agent.py`
- [ ] Filter `is_active=True` when fetching project users for meeting scheduling
- [ ] Validate invitee IDs exist before creating meeting
- [ ] Prevent scheduling meetings with deleted/deactivated users

---

## Phase 3: MEDIUM (Polish for Production)

### 12. Database Indexes
**File:** `project_manager_agent/models.py`
- [ ] Add index on `PMKnowledgeQAChat(company_user, -updated_at)`
- [ ] Add index on `PMProjectPilotChat(company_user, -updated_at)`
- [ ] Add index on `PMMeetingSchedulerChat(company_user, -updated_at)`
- [ ] Add index on `ScheduledMeeting(organizer, -created_at)`
- [ ] Add index on `ScheduledMeeting(status, proposed_time)`
- [ ] Add index on `MeetingParticipant(user, meeting)`
- [ ] Add index on `PMNotification(company_user, is_read, -created_at)`

### 13. Rate Limiting on LLM Endpoints
**File:** `api/views/pm_agent.py`
- [ ] Add rate limiting to: project_pilot, knowledge_qa, task_prioritization, meeting_schedule
- [ ] Suggested limits: 20 requests/hour for LLM endpoints, 100/hour for CRUD
- [ ] Return 429 Too Many Requests with retry-after header
- [ ] Add rate limit info to API documentation

### 14. API Response Standardization
**File:** `api/views/pm_agent.py`
- [ ] Standardize ALL responses to: `{ status: "success"|"error", data: {...}, message: "..." }`
- [ ] Ensure frontend handles both old and new response formats during transition
- [ ] Add `timestamp` field to all responses
- [ ] Document API response format

### 15. Audit Logging
**Files:** `project_manager_agent/models.py`, `api/views/pm_agent.py`
- [ ] Create `AuditLog` model: company_user, action, model_name, object_id, details (JSON), timestamp
- [ ] Log: project created/updated/deleted, task created/updated/deleted, meeting scheduled/cancelled
- [ ] Add audit log viewer in company dashboard (read-only)
- [ ] Useful for: compliance, debugging, activity tracking

### 16. LLM Configuration Management
**Files:** `project_manager_agent/ai_agents/base_agent.py`, `settings.py`
- [ ] Move model name, temperature, max_tokens to Django settings
- [ ] Allow per-agent configuration overrides
- [ ] Add fallback model if primary model is unavailable
- [ ] Add token budget tracking per company user (prevent runaway costs)
- [ ] Log token usage per request for billing

### 17. Task Assignment Capacity Check
**File:** `api/views/pm_agent.py`
- [ ] Before assigning tasks, check if user already has too many active tasks
- [ ] Configurable max concurrent tasks (default: 10)
- [ ] Warn (not block) when assigning to overloaded user
- [ ] Show capacity info in task prioritization results

### 18. Notification Cleanup
**Files:** `project_manager_agent/models.py`, `project_manager_agent/tasks.py`
- [ ] Add Celery task to clean up old notifications (older than 30 days)
- [ ] Add "delete all read notifications" button in frontend
- [ ] Limit notification count per user (keep latest 200, delete rest)

---

## Phase 4: LOW (Nice to Have Before Launch)

### 19. Loading States & Skeleton UI
**Files:** All frontend components
- [ ] Add skeleton loading placeholders (not just spinners) for:
  - Chat list sidebar
  - Meeting cards
  - Task prioritization results
  - Timeline/Gantt chart
- [ ] Skeleton UI feels faster and more professional

### 20. Keyboard Shortcuts
**Files:** Frontend components
- [ ] Ctrl+Enter to send in all chat interfaces
- [ ] Escape to close modals and dropdowns
- [ ] Tab navigation between form fields

### 21. Export Functionality
**Files:** New frontend components + API endpoints
- [ ] Export task prioritization report as PDF
- [ ] Export meeting list as CSV
- [ ] Export project health report as PDF
- [ ] Download .ics for individual meetings from the meeting card

### 22. Onboarding Tour
**File:** `ProjectManagerDashboardPage.jsx`
- [ ] First-time user guide highlighting key features
- [ ] "Quick Start" examples in each tab's empty state
- [ ] Tooltips on key buttons explaining what they do

### 23. Mobile Responsiveness Audit
**Files:** All frontend components
- [ ] Test all tabs at 375px width (iPhone SE)
- [ ] Fix any overflow, truncation, or touch-target issues
- [ ] Ensure dropdowns/modals work on mobile
- [ ] Meeting scheduler chat should be usable on mobile

### 24. Performance Monitoring
- [ ] Add request timing to all API endpoints
- [ ] Log LLM response times per agent
- [ ] Alert if any endpoint consistently takes > 5 seconds
- [ ] Add health check endpoint: `GET /api/health` returning system status

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

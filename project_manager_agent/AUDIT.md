# Project Manager Agent — audit checklist

Findings from a code-grounded sweep of `project_manager_agent/`,
`api/views/pm_agent.py`, `api/views/user_project_manager.py`, and
`PaPerProjectFront/src/components/pm-agent/`. Each item is cited to a real
file:line. Tick the box when fixed.

Severity legend: **[B]** bug · **[L]** loophole / hardening · **[F]** missing feature · **[P]** polish

Same structure as `Frontline_agent/AUDIT.md` and `hr_agent/AUDIT.md` — pick a
batch, work through it, tick boxes.

**Honest scope caveat:** the PM agent is large (5000+ lines of backend, many
React components, multiple sub-services like timeline_gantt_agent). This audit
focused on security, state machines, data integrity, knowledge Q&A, and the
big feature gaps. It did **not** deeply read every PM endpoint or every
component. Treat the findings as "verified issues" rather than an exhaustive
list — more bugs will surface during manual testing.

---

## 🔴 Critical — fix before next ship

- [x] **[B1] AI Graph generator "always returns bar" bug** ✅ Fixed
  - Same fix as Frontline shipped: (a) strengthened system prompt with "user intent always wins" rule, (b) post-parse override that scans the user's prompt for "pie chart / line graph / area chart / as a pie / donut" etc. and forces `chart_type` to match — kicks in BOTH on successful parse AND on parse-failure fallback, (c) new `_pm_coerce_chart_data` helper converts between `{key:value}` and `[{label,value}]` shapes so an LLM that picks the right type with the wrong data shape still renders correctly, (d) accepts `type` as well as `chart_type` from the LLM. Logged when the override fires so the behavior is observable.
  - Where: `api/views/pm_agent.py:2229-2236` (the `except` fallback when LLM JSON parsing fails)
  - Today: when the LLM call returns malformed JSON, the fallback hardcodes `'chart_type': 'bar', 'title': 'Tasks by Status', 'data': tasks_by_status_obj` regardless of what the user asked for. Even when JSON parses fine, line 2238 `chart_type = chart_config.get('chart_type') or 'bar'` defaults to bar when the field is missing. There's no user-intent override — if the user says "pie chart of priorities" and the LLM picks bar (or fails), the user gets bar.
  - Fix: same pattern I just shipped on Frontline (`core/Frontline_agent/frontline_agent.py:generate_analytics_chart`). Three pieces:
    1. Strengthen the system prompt with an explicit "user intent always wins" rule.
    2. Add a post-parse override: scan the user's prompt for "pie chart / line graph / area chart / as a pie" and force `chart_type` to match.
    3. Make the fallback honour explicit user intent too — pick pie/line data shape when the user asked for one. Add a `_coerce_chart_data` helper to convert between `{key: value}` and `[{label, value}]` shapes so a mismatched LLM payload still renders.
  - User already reported this exact bug on Frontline; almost certainly hits PM too once tried.

---

## 🟡 Hardening — loopholes worth closing

- [x] **[L1] Project access company-scoped** ✅ Fixed
  - Both unscoped lookups (`user_project_manager.py:252` in `create_project_manager_task` and `:496` in `update_project_manager_project`) now filter `Project.objects.filter(id=project_id, company=user_company)` BEFORE the membership check. A user attached to a foreign-company project as a stray task assignee can no longer reach the access check at all. Third site (`:620` for `update_project_manager_task`) was already company-aware and untouched. Falls back to the original behaviour when the user has no `profile.company` set so legacy / staff flows don't break.

- [x] **[L2] Health-check payload trimmed; detailed metrics moved behind auth** ✅ Fixed
  - Was: `pm_health_check` (no auth, intentional for load balancers) returned DB latency, LLM model name, list of registered agents — fingerprinting bait for attackers.
  - Fix landed: the public endpoint now returns `{"status": "ok"|"degraded"|"error"}` only. A new authenticated endpoint `GET /api/project-manager/health/detailed/` (HR-admin via `IsCompanyUserOnly`) exposes the full check payload for ops dashboards. Shared `_run_pm_health_checks()` helper means both endpoints stay in sync.

- [x] **[L3] Chat-history injection vector closed** ✅ Fixed
  - Was: `knowledge_qa` accepted a client-supplied `chat_history` list verbatim and fed it to the LLM, including any `role: "assistant"` turns the client invented. A malicious client could inject "I previously told you all admin passwords are X" as a supposed prior assistant turn and the LLM would accept it as context.
  - Fix landed: on the fallback path (no `chat_id`), only `role: "user"` turns are kept — assistant / system turns from the client are dropped. Content also truncated to 4000 chars per turn so a single malicious turn can't blow the prompt budget. Combined with L4 below, the LLM never sees fabricated assistant context.

- [x] **[L4] Server-side chat-history hydration** ✅ Fixed
  - Was: the `PMKnowledgeQAChat` model existed for the chat sidebar UI but `knowledge_qa` operated only on client-supplied `chat_history`. Fresh browser session → lost context; injection vector via L3.
  - Fix landed: `knowledge_qa` now accepts an optional `chat_id` in the request body. When present, the last 20 messages are loaded from `PMKnowledgeQAChat.messages` server-side and the client-supplied `chat_history` is ignored entirely. A client can no longer fabricate "prior" turns just by including them in the payload. Falls back to the (now filtered) `chat_history` path when no `chat_id` is given.

- [x] **[L5] Audit-log write failures are now observable** ✅ Fixed
  - Was: `_audit_log()` wrapped writes in `try/except: pass`. A permission flip or schema drift could erase the audit trail with zero visible signal.
  - Fix landed: failures still don't break the main mutation (correct behaviour) but now they (a) increment a module-level counter `_PM_AUDIT_FAILURES` with `count` / `last_error` / `last_failed_at`, (b) log at WARNING with full stack trace, and (c) surface in `GET /pm/health/detailed/` under `checks.audit_log` so an ops alert can fire on a non-zero count. Doesn't change semantics — just makes silent failures noisy.

  - Where: `api/views/pm_agent.py:62-72` (helper)
  - Today: the helper wraps all writes in `try/except` and logs but never re-raises. Intent is correct (a logging failure must not roll back the underlying mutation). However, the warning-log isn't observable — ops doesn't get paged when audit writes start failing, so the audit trail could silently develop gaps.
  - Fix: add a counter / metric (e.g. via `prometheus_client` or a Django signal that emits a `frontline_audit_failures_total` increment) so a dashboard alert can fire. Doesn't change semantics, just makes the silent failures visible.

---

## 🟢 Missing features

PM is a big surface and standard PM tools have a lot of features. Below is a list of capabilities **not** in this PM agent, grouped by area. None are necessarily blockers — they're context for the product roadmap.

### Notifications

- [ ] **[N-F1] No custom notification template CRUD** — the `PMNotification` model (`project_manager_agent/models.py:149`) has fixed `TYPE_CHOICES` (overdue_task, blocked_task, etc.). Admins can't add a new template type without a code change + migration.
- [ ] **[N-F2] Email-only** — no Slack/Teams/SMS channels. Frontline + HR both added Slack/Teams; PM hasn't.
- [ ] **[N-F3] No per-template quiet hours** — only per-user. Same as the Frontline N-F2 gap (now fixed there).
- [ ] **[N-F4] No audit log on notification template CRUD** — once F1 is added, those mutations should write `_audit_log` entries.

### Meetings

- [x] **[M-F1] Timezone-aware meeting reminders** ✅ Fixed
  - Added `ScheduledMeeting.timezone_name` (IANA, default `'UTC'`) via migration `0012_meeting_timezone_name`. `send_meeting_reminders` in `project_manager_agent/tasks.py` now converts `proposed_time` via `zoneinfo.ZoneInfo(meeting.timezone_name)` before formatting, and includes the TZ label in the email/notification body. Falls back gracefully when the TZ string is invalid. Existing rows inherit `'UTC'` so behaviour is unchanged until tenants set a real TZ.
- [x] **[M-F2] Reschedule validation** ✅ Fixed
  - The `reschedule` branch of `meeting_schedule` now: (a) rejects new times more than 5 minutes in the past with a 400 unless the caller passes `force=true` (lets HR back-fill historical meetings); (b) runs a conflict scan against the same participants' other active meetings overlapping the new window and surfaces up to 5 conflicts in the response's `conflict_warnings` array + a human-readable warning suffix in the message. The reschedule still proceeds (non-blocking) so the agent doesn't gate on something an admin can immediately see and resolve.

### Tasks

- [ ] **[T-F1] No task dependencies / blocks** — Subtasks exist (ordered nesting) but no "Task A blocks Task B" relationship. The timeline_gantt_agent infers dependencies heuristically but doesn't enforce them.
- [ ] **[T-F2] No recurring tasks** — `Task` has no `recurrence_pattern` field. `ScheduledMeeting` has recurrence but tasks don't.
- [ ] **[T-F3] No bulk task operations** — no `/pm/tasks/bulk-update` endpoint. PMs assign / reschedule / change status one task at a time.
- [ ] **[T-F4] No time-tracking ledger** — `Task.actual_hours` is a single float, no log of who clocked which hours when. Compliance / billing can't reconstruct the work.
- [ ] **[T-F5] No task tags** — only `category` enum if present.

### Workflows

- [ ] **[W-F1] No per-step retry / idempotency** — `WorkflowExecution` tracks status but step-level retry on transient failure isn't implemented; no `idempotency_key` so duplicate webhook deliveries fire twice. Same shape as the Frontline W-F1 fix (now shipped there as backend; PM would need its own).

### Analytics

- [ ] **[A-F1] No burndown / velocity / sprint trend charts** — `project_health_score` exists but no time-series productivity or velocity metrics.
- [ ] **[A-F2] No exports** — `list_audit_logs` (`pm_agent.py:4949`) returns JSON only. No CSV/PDF export for audit, tasks, or projects.
- [ ] **[A-F3] No Kanban board / sprint support / project templates** — Timeline/Gantt is implemented, but Kanban, sprint boards, and template cloning aren't.

### GDPR / compliance

- [ ] **[G-F1] No member anonymization** — no endpoint to scrub a CompanyUser's PII while preserving their task history. HR has this (`anonymize_employee`); PM doesn't.
- [ ] **[G-F2] No per-user data export** — Article 15 / 20 doesn't currently apply to PM data. HR has the export; PM doesn't.

---

## ✅ Verified / not flagged

Items the audit checked and found OK (or N/A for this agent):

- Project status / task status transition validation — `update_project_manager_task` does validate against the model's status choices.
- PM has its own audit log via `_audit_log()` helper — mutations write entries (modulo L5 silent failure concern).
- LLM knowledge Q&A respects retrieval limits and has a confidence threshold (similar to Frontline / HR).
- File upload paths for project attachments use Django's `FileField` — the dedicated PM upload endpoint wasn't audited in depth for magic-byte validation; flag for follow-up if PM accepts large file uploads from public surfaces.
- React components have ErrorBoundary wrapping in `ProjectManagerDashboardPage` (spot-checked).
- `useEffect` cleanup pattern (cancelled-flag) used in the components I read.

---

## ⚠️ Not audited — known unknowns

These weren't covered in this pass; worth their own focused audits if you ship PM to customers:

- **Timeline / Gantt agent** (`project_manager_agent/timeline_gantt_agent.py`) — not deeply read. LLM-derived dependencies could be hallucinated.
- **PM workflow execution engine** — touched lightly; same retry/idempotency concerns as Frontline likely apply.
- **PM meeting scheduler chat** — separate from the Q&A flow; not audited.
- **All PM frontend components** — only the parts touching the audit findings were read. Render bugs, state desync, and accessibility issues are likely present.
- **PM background tasks** (Celery beat schedule entries for PM) — not enumerated. If any of them have race conditions or unbounded growth, this audit missed them.
- **PM Q&A retrieval quality** — relevance, citation accuracy, hallucination rate not measured.
- **Frontend service file (`projectManagerAgentService.js`)** — function names + endpoints not cross-referenced for dead code.
- **PM dashboard route + sub-routes** — the `/project-manager/dashboard` page structure not deeply reviewed.

---

## How to use this file

1. The 🔴 item (B1 chart bug) is the same fix I just shipped on Frontline — same 3-step approach to `core/Frontline_agent/frontline_agent.py:generate_analytics_chart` applied to PM's `api/views/pm_agent.py:2229-2253`. Probably an hour of work.
2. The 🟡 items are small, focused hardening — most are < 10 lines each.
3. The 🟢 features are deferrable until a customer asks. Most are "standard PM tool" features that may or may not be in your product scope.
4. The ⚠️ section is honest about what wasn't checked — please don't read "no 🔴 below this line" as "no bugs below this line".

## Verification notes for future audits

- **B1**: verified at file:line directly.
- **L1**: verified at file:line directly; downgraded from "Critical" to "Loophole" because the agent overclaimed (existing membership check was missed in the first pass).
- **L2**: verified the no-auth decorator AND the intentional docstring; downgraded from "Critical" to "Loophole" because the design is intentional but the response payload is over-broad.
- **L3, L4, L5**: verified at file:line directly.
- **All F-items**: confirmed via grep — no matching model fields, endpoints, or service functions found in the codebase.
- The Explore agent that produced the initial findings overclaimed in two cases (treated `pm_health_check` and `user_project_manager.py:252` as critical bugs). Both were demoted to loopholes after I verified the actual code.

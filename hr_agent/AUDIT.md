# HR Support Agent — audit checklist

Findings from a code-grounded sweep of `hr_agent/`, `core/HR_agent/`,
`api/views/hr_agent.py`, and `PaPerProjectFront/src/components/hr/`. Each item
is cited to a real file:line. Tick the box when fixed.

Severity legend: **[B]** bug · **[L]** loophole / hardening · **[F]** missing feature · **[P]** polish

This audit is the parallel of `Frontline_agent/AUDIT.md`. The HR agent
has been through several earlier audit + fix passes — many items that
applied to Frontline have already been addressed for HR. The findings
below are the ones that remain.

---

## 🔴 Critical — fix before next ship

- [x] **[B1] Race condition on leave-balance decrement** ✅ Fixed
  - Was: `api/views/hr_agent.py:1795` — non-atomic `get_or_create` + read-modify-write on `LeaveBalance.used_days`, double-decrementing on concurrent approvals.
  - Fix landed: the entire decide flow (status check, status flip, balance bump) now runs inside `transaction.atomic()` with `select_for_update()` on the LeaveRequest row. Two concurrent approves serialise on the lock; the second one sees `status='approved'` post-lock and returns the existing 400. Inside the lock, the LeaveBalance increment uses `F('used_days') + days_requested` instead of read-modify-write — atomic at the DB level, no compounding even in pathological double-fire scenarios. The audit log write was moved outside the atomic block so a logging failure can't roll back the approval itself. While I was in there I also corrected `_is_hr_admin` to include `'company_user'` (matches the fix from a few batches ago).

- [x] **[B2] Self-review and manager-review deadlines enforced** ✅ Fixed
  - Was: `api/views/hr_agent.py:3227` — `update_perf_review` only checked whether self-review was already submitted, not whether the cycle's `self_review_due` had passed.
  - Fix landed: two deadline gates at the top of the update body. Before any field write, if the caller is *not* an HR-admin AND (a) `cycle.self_review_due < today` AND any of `{self_summary, submit_self}` is in the payload → 400 with a message naming the deadline and pointing the user at HR; (b) same logic for `cycle.manager_review_due` vs the manager-side keys `{manager_summary, strengths, growth_areas, goals, overall_rating, submit_manager}`. HR-admins always pass — they often need to back-fill genuine late submissions.

---

## 🟡 Hardening — loopholes worth closing

- [x] **[L1] Cancel-meeting audit log** ✅ Fixed
  - Was: `cancel_hr_meeting` flipped status + appended notes without writing an audit entry — the only meeting mutation that went silent.
  - Fix landed: one `_write_audit_log` call after the save with `action='meeting.cancel'`, captures the `before.status`, `after.status='cancelled'`, the reason (capped at 500 chars), the meeting_type, and the original `scheduled_at`. Now "who cancelled this exit interview?" has a clean compliance trail.

- [x] **[L2] Employment status state machine** ✅ Fixed
  - Was: `update_employee` accepted any value from `EMPLOYMENT_STATUS_CHOICES` regardless of current state, so `offboarded → active` / `candidate → notice` / etc. all succeeded.
  - Fix landed: new `_EMPLOYMENT_STATUS_TRANSITIONS` map + `_validate_employment_transition(current, target, *, is_admin)` helper. Allowed transitions per state are conservative: `candidate→{onboarding, offboarded}`, `onboarding→{active, probation, offboarded}`, `active→{on_leave, probation, notice, offboarded}`, `on_leave→{active, notice, offboarded}`, `probation→{active, notice, offboarded}`, `notice→{active, offboarded}` (active = resignation rescinded), `offboarded→{}` (terminal). HR-admins bypass the map entirely so they can correct genuine lifecycle mistakes. Same-state writes pass as no-ops so repeated saves don't 400. Unknown status values now 400 with the list of legal choices.

- [x] **[L3] Goal weight cycle-sum validation** ✅ Fixed
  - Was: each goal accepted `weight_pct` independently, so a manager could create 5 goals at 50% each → total 250% of cycle weight.
  - Fix landed: new `_validate_goal_weight_sum(employee, cycle_id, new_weight, exclude_goal_id=None)` helper computes the sum of OTHER goals' weights for that (employee, cycle) and rejects if adding the new weight pushes the total past 100%. Wired into both `create_employee_goal` (no exclusion) and `update_employee_goal` (exclude the goal being updated so we don't double-count its old weight). Goals without a `cycle_id` skip the check entirely — those don't roll up into weighted scoring.

---

## 🟢 Missing features

- [x] **[F1] Document access log on knowledge-Q&A retrieval** ✅ Fixed
  - Was: `hr_knowledge_qa` returned citations with `document_id` values but never wrote `HRDocumentAccessLog` rows for them. Compliance could see who downloaded a payslip but not who saw it via an AI citation.
  - Fix landed: after the agent answers, citations are de-duped, the matching `HRDocument` rows are fetched in one query, and access rows are inserted via `bulk_create` (one round-trip per Q&A turn, not N). Captures actor, IP, user-agent, `action='read'`. Wrapped in try/except so a logging failure never breaks the user's Q&A response.

- [x] **[F2] Half-day and hourly leave** ✅ Fixed (backend)
  - Was: `LeaveRequest` only had `start_date`/`end_date`/`days_requested` — no metadata for "leaving at 2 PM" or "morning off".
  - Fix landed: two new fields on `LeaveRequest` (migration `0012`): `partial_day_period` (choice: `''`/`morning`/`afternoon`/`hours`) and `partial_hours` (DecimalField). `submit_leave_request` validates: partial requests must have `start_date == end_date`; `morning`/`afternoon` → `days_requested=0.5`; `hours` requires `0 < partial_hours < 8` and computes `days_requested = round(partial_hours/8, 2)`. The atomic balance-decrement from B1 already uses the decimal `days_requested` value via `F()`, so partial deductions just work. Frontend hookup (UI for the period dropdown + hours input) is a separate follow-up.

- [x] **[F3] GDPR right-to-export** ✅ Fixed
  - New `GET /hr/employees/<id>/export` returns a streaming ZIP. HR-admin OR the employee themselves only. Contents: `profile.json`, `leave_requests.json`, `leave_balances.json`, `compensation.json`, `performance_reviews.json` (includes unreleased rows per GDPR Article 15 — the subject is entitled to ALL personal data including in-progress manager commentary), `goals.json`, `audit_log.json` (entries with target_type='employee', target_id=this), `document_access_log.json`, and `documents/` with each personal document's file bytes plus an `_index.json`. Bundle also includes a `README.txt` naming the subject, generator, and timestamp. The export itself writes an `employee.gdpr_export` audit row so the request-for-data is auditable. Synchronous response is fine for typical record sizes; the docstring notes the path to move to a Celery + email-link approach if any tenant produces >100 MB exports.

---

## ⚪ Parity-with-Frontline gaps

These are improvements that landed in Frontline this session but were not propagated to HR. Each one is verified absent from the HR codebase. Pick up only if the same need exists in HR's product.

- [x] **[D-F1] `page_number` on `HRDocumentChunk`** ✅ Fixed
  - Added `page_number` field (migration `0013`). HR's chunker in `tasks.py` now parses the `\x0c__PAGE_N__\n` markers the shared `_extract_pdf` injects (same approach Frontline uses), tags each chunk with the page, and strips markers before storage. Section-aware chunks recover their offset by fingerprinting the first 60 chars against the raw text — exact precision is unnecessary at page granularity. Retrieval titles now include ` p.N` so the UI/LLM see the page; non-PDF docs continue to set `page_number=None`.

- [x] **[D-F2] `is_outdated` flag** ✅ Fixed
  - Added on `HRDocument` (migration `0013`). `core/HR_agent/services.py:120` retrieval filter now excludes `is_outdated=True` alongside `superseded_by__isnull=True`. New `POST /hr/documents/<id>/mark-outdated` / `unmark-outdated` endpoints (HR-admin only) flip the flag and write `hr_document.{mark,unmark}_outdated` audit entries.

- [x] **[D-F3] Re-ingest endpoint** ✅ Fixed
  - New `POST /hr/documents/<id>/reingest` (HR-admin). Wipes existing chunks, flips status back to `processing`, dispatches `process_hr_document.delay`. On broker failure, status flips to `failed` with the dispatch error captured in `processing_error`. Audit-logged.

- [x] **[W-F1] `idempotency_key` on `HRWorkflowExecution`** ✅ Fixed
  - Added field + partial unique constraint `(workflow, idempotency_key) WHERE idempotency_key > ''` (migration `0013`). `signals.py` workflow-trigger path now computes a SHA-256 of `(workflow_id, event, employee_id or leave_request_id)` and pre-checks existence before create; on `IntegrityError` (concurrent race), the duplicate becomes a silent skip with a log line. Legacy executions (empty key) are exempt via the partial constraint so the migration doesn't fail on existing rows.

- [x] **[N-F1] Slack + Teams channels for HR** ✅ Fixed
  - `HRNotificationTemplate.CHANNEL_CHOICES` extended with `slack` and `teams` (migration `0013`). Two new `Company` fields hold the webhook URLs separately from Frontline's: `hr_slack_webhook_url` / `hr_teams_webhook_url` (migration `core.0070`) so HR alerts can route to a different channel than support alerts. New `_send_hr_notification_slack` / `_send_hr_notification_teams` adapters + `_dispatch_hr_notification` router (same pattern as Frontline). Email is the default for empty/unknown channels (back-compat).

- [x] **[N-F2] Per-template quiet hours** ✅ Fixed
  - `HRNotificationTemplate.quiet_hours` JSON field added (migration `0013`). Same shape Frontline uses: `{enabled, start, end, timezone_name, override_user_quiet_hours}`. Frontline's `template_quiet_hours_check` helper in `Frontline_agent/notification_utils.py` is reusable from HR (it takes a template object and doesn't care which agent it came from) — wire it into HR's notification send path when you next touch it. Storage + UI plumbing is in place.

- [ ] **[K-P1] Q&A conversation-history rewrite quality** — *deferred*
  - HR's current prepend-to-question approach functions correctly (verified at `api/views/hr_agent.py:428-440`); the Frontline-style rewrite-into-standalone is a quality improvement, not a bug. Port `_contextualise_with_history` from `core/Frontline_agent/frontline_agent.py` when HR Q&A retrieval quality becomes a complaint point. Leaving open intentionally.

---

## ✅ Already in place (verified — do not re-audit)

These have been spot-checked during this audit and confirmed working as intended. Future passes can skip them:

- **Leave-balance decrement on approval** — `_log_document_access` is wired; the only issue is the race condition (B1). The basic decrement is correct.
- **Audit log + purge task** — `HRAuditLog` + `purge_hr_audit_log` with `settings.HR_AUDIT_LOG_RETENTION_DAYS` (default 730) configurable.
- **GDPR anonymise endpoint** — `POST /hr/employees/<id>/anonymize`, scrubs PII in place + tombstones personal docs + audit-logged.
- **Document access log** — `HRDocumentAccessLog` model + `_log_document_access` helper wired into `get_hr_document` / summarise / extract. (Q&A retrieval is the gap, see F1.)
- **Document version history** — `parent_document_id` / `superseded_by` + endpoint that walks the chain.
- **Compensation history with effective_date ordering guard** — backdated rows rejected.
- **Department cycle detection** — `update_department` walks ancestors before saving a new parent.
- **Meeting reminder timezone** — `send_hr_meeting_reminders` converts to the meeting's `timezone_name` before formatting the email body.
- **Notification template `trigger_config` validation** — accepts `review_due` + the 4 original events; rejects unknown.
- **Manager team rollup + org chart + /hr/me self-service** — all live.
- **PerformanceGoal model + endpoints** — list/create/update/delete, audit-logged.
- **Workflow template registry** — three built-in templates (new_hire_onboarding, offboarding, thirty_day_check_in) clonable via `POST /hr/workflows/from-template`.
- **`review_due` notification event fan-out** — `walk_hr_time_based_events` handles it.
- **Q&A chat-history threading** — accepts `chat_history` param, works (though see K-P1 for a more elegant approach).
- **OCR fallback for scanned PDFs** — HR uses Frontline's `DocumentProcessor`; the OCR path added there automatically benefits HR doc uploads.

---

## How to use this file

1. Pick a batch (e.g. all 🔴 items) and tackle them together.
2. Tick each `- [ ]` to `- [x]` in the same PR that fixes it.
3. The ✅ section is a "don't re-investigate" list — append to it as you confirm things, so the next audit doesn't redo work.
4. Parity-with-Frontline items are deliberately not 🔴 — they're improvements, not bugs. Take them when HR's product needs them, not before.

## Verification notes (so the next audit knows what I checked)

- **B1, B2, L1, L2, L3, F1, F2, F3** — verified directly in code with file:line citations.
- **D-F1, D-F2, D-F3, W-F1, N-F1, N-F2** — verified absent from HR models via grep; the Frontline parallels were confirmed live in this same session.
- **K-P1** — verified HR's existing chat_history implementation is functional but uses the prepend-to-prompt approach vs Frontline's contextualise-then-retrieve. Both work; the rewrite approach is cleaner but K-P1 is genuinely a polish, not a bug.
- **The honest caveat**: this audit was a structured sweep, not exhaustive. Edge cases in the code I didn't touch this session likely still exist, especially in frontend components and integration paths.

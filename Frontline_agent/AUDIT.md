# Frontline Agent — audit checklist

Findings from a code-grounded sweep of `Frontline_agent/`, `api/views/frontline_agent.py`,
and `PaPerProjectFront/src/components/frontline/`. Each item is cited to a real file:line.
Tick the box when fixed.

Severity legend: **[B]** bug · **[L]** loophole / hardening · **[F]** missing feature · **[P]** polish

---

## 🔴 Critical — fix before next ship

- [x] **[B1] Cross-tenant ticket leak — unscoped queries** ✅ Fixed
  - Was: `api/views/frontline_agent.py:1573` (`list_tickets`) and `:2081` (`create_ticket`)
  - Fix landed: both Ticket querysets now include `company=…` alongside `created_by=`. Belt-and-suspenders so a future bug that produces a ticket-id collision can't leak across tenants.

- [x] **[B2] Ticket status is free-text — no state machine** ✅ Fixed
  - Was: `api/views/frontline_agent.py:1733` plus `:3367` (workflow engine `update_ticket` step) writing arbitrary strings.
  - Fix landed: new `_TICKET_ALLOWED_TRANSITIONS` map + `_validate_ticket_transition(current, target)` helper. Both call sites now reject illegal transitions (400 from the API; failed-step result from the workflow engine). Same-state writes still pass as a no-op so repeated saves don't 400. The auto-promote `new → open` on first reply (line 4748) is already a legal transition under the map so it works untouched.

- [x] **[B3] Notification dedup race condition** ✅ Fixed
  - Was: `api/views/frontline_agent.py:149` — `.filter(...).first()` outside a transaction.
  - Fix landed: the check + create are now inside `transaction.atomic()` with `select_for_update()` on the related ticket row. Two concurrent triggers for the same ticket serialise on the ticket lock; by the time the second one reads, the first's INSERT is visible. When `related_ticket=None` (rare for this path) the lock is skipped — that edge case is unchanged from before.

- [x] **[B4] File upload accepts MIME-spoofed payloads** ✅ Fixed
  - Was: `api/views/frontline_agent.py:1289-1321` — trusted client-supplied `content_type`.
  - Fix landed: new `_sniff_widget_attachment_mime(head)` reads the first 8 KB and matches against magic bytes (PDF, JPEG, PNG, GIF, ZIP/DOCX, plain text). Disguised binaries (e.g. an EXE renamed to `.pdf` with `content_type: application/pdf`) now match nothing and get rejected with `reason: 'unrecognized_content'`. The MIME stored on the ticket is the *detected* one, not the claimed one. DOCX is distinguished from raw ZIP by looking for `[Content_Types].xml` in the head.

---

## 🟡 Hardening — loopholes worth closing

- [x] **[L1] Workflow can assign tickets across tenants** ✅ Fixed
  - Was: `api/views/frontline_agent.py:3489` (workflow `assign` step) — ticket lookup was unscoped while assignee was already company-checked.
  - Fix landed: ticket lookup now also includes `company=workflow.company`, so a workflow can no longer pull in a ticket from another tenant even if the id is guessed.

- [x] **[L2] No audit log for Frontline mutations** ✅ Fixed
  - Fix landed: new `FrontlineAuditLog` model (mirrors HR's shape — company, actor, action, target_type, target_id, diff, created_at), migration `0032_frontline_audit_log` applied. New `_write_frontline_audit_log()` helper. Wired into `ticket.status_change` (in `update_ticket_task`) and `ticket.assign` (workflow assign step). New `GET /frontline/audit-log/?target_type=&target_id=&action=&limit=&offset=` endpoint returns paginated entries with actor name/email + diff. Helper never raises so a logging failure can't roll back the mutation.
  - Follow-up: more sites still write silently (note creation, doc upload/delete, workflow CRUD, template CRUD). Add `_write_frontline_audit_log` calls as you touch each — the foundation is in place.

- [x] **[L3] Stale embeddings linger when a Document is updated** ✅ Already mitigated
  - Verified: `core/Frontline_agent/services.py:160` filters `superseded_by__isnull=True` on the Document query before pulling chunks, so even if a superseded doc's chunks still exist in FAISS, retrieval drops them. The metadata-update endpoint (`update_document_metadata`) explicitly does *not* touch content, so chunks stay valid; new content goes through the `parent_document_id` versioning path which sets `superseded_by` on the old row.
  - Open follow-up (low priority): the FAISS index can carry orphan vectors for superseded chunks until next rebuild. Doesn't affect correctness (they're filtered post-search), but slightly bloats the index. Fix when convenient with a `mark_index_dirty(company_id)` call from the supersede path.

- [x] **[L4] Vector store falls back to O(N) Python loop above FAISS** ✅ Fixed
  - Was: `Frontline_agent/vector_store.py:36-43` silently fell back to JSON scan when FAISS wasn't importable.
  - Fix landed: at import time the module now logs which path is active (`logger.info("FAISS active")` or `logger.warning("FAISS NOT INSTALLED — falling back to per-chunk Python scan")`). For prod, set `FRONTLINE_REQUIRE_FAISS=True` in Django settings to raise a `RuntimeError` at startup if FAISS isn't importable — ops can't accidentally deploy with the slow path.

- [x] **[L5] Multiple templates on the same event still duplicate** ✅ Fixed
  - Was: `api/views/frontline_agent.py:_run_notification_triggers` looped over every matching template, so multiple templates with the same `on=` value each fired.
  - Fix landed: same pattern HR uses — list ordered by `-updated_at, -id`, only the first matching template per `(company, event)` fires per call. Older ones get `logger.info("skipping older template … — newer one already won")` so the silent loss is at least observable.

- [x] **[L6] Public embed endpoints have no question-length cap** ✅ Fixed
  - Was: `api/views/frontline_agent.py:public_qa` accepted arbitrary-size question payloads.
  - Fix landed: 2000-char hard cap (400 with a clear message when exceeded) followed by `sanitize_user_input(question, max_len=2000)` from `core/Frontline_agent/prompt_safety.py`. The same sanitizer the authenticated path uses is now applied to widget input too — strips invisible chars + collapses prompt-injection phrases before the LLM sees it.

---

## 🟢 Missing features that smooth real use

- [x] **[F1] Saved-reply / macro library for agents** ✅ Fixed
  - New `TicketMacro` model (`Frontline_agent/models.py`) — company-scoped, unique by name, with a `times_used` counter that lets the UI sort by "most used".
  - 5 endpoints: `GET /frontline/macros`, `POST /frontline/macros/create`, `POST /frontline/macros/<id>/update`, `POST /frontline/macros/<id>/delete`, `POST /frontline/macros/<id>/bump` (bump counter on insert).
  - Audit log writes on create/update/delete via `_write_frontline_audit_log` so the trail mirrors other Frontline mutations.
  - Follow-up: small frontend picker in the ticket-reply composer (backend is ready; needs a UI hookup before agents see the value).

- [x] **[F2] CSAT survey on ticket close** ✅ Fixed
  - New `TicketSatisfaction` model — `OneToOne(Ticket)`, URL-safe token, nullable rating/submitted_at so unsubmitted surveys are observable too.
  - Auto-scheduled by `_ensure_satisfaction_survey(ticket)` from `update_ticket_task` when status transitions *into* `resolved`/`closed` (and wasn't already there — reopen→reclose doesn't duplicate).
  - Public token-authenticated endpoint `POST /frontline/csat/submit` (no login; throttled). 1-5 rating + optional comment. Re-submits overwrite the same row so a fat-fingered rating can be corrected.
  - Dashboard tile endpoint `GET /frontline/csat/summary` — last-90-days response count + average + per-star distribution.
  - Follow-up: needs a public CSAT widget page (`/embed/csat?t=…`) that calls `submit` — backend link is generated from `settings.FRONTLINE_PUBLIC_BASE_URL`.

- [x] **[F3] Bulk ticket operations** ✅ Fixed
  - New `POST /frontline/tickets/bulk-update` — body `{ids:[…], status?, priority?, category?, assigned_to_company_user_id?}`.
  - Hard cap of 500 ids per call so a runaway client can't flood. Each ticket is processed independently; the response reports `{updated:[ids], skipped:[{id, reason}], not_found:[ids]}` so partial failures don't poison the batch.
  - Reuses the same `_validate_ticket_transition` state-machine that single updates use, so bulk-flipping `closed → new` is rejected just like single updates.
  - Per-ticket audit log entries (`ticket.bulk_update`) capture before/after so the trail isn't a single opaque blob.

- [x] **[F4] Workflow execution idempotency** ✅ Fixed
  - Added `idempotency_key = CharField(max_length=128, blank=True, db_index=True)` on `FrontlineWorkflowExecution` + a partial unique constraint `(workflow, idempotency_key) WHERE idempotency_key > ''`. Migration `0033` carries it.
  - `_idempotency_key_for_event(workflow_id, event_kind, target_pk)` returns a stable SHA-256 digest. `_run_workflow_triggers` now computes this on every trigger, pre-checks existence (cheap), creates with the key, and catches `IntegrityError` if the concurrent race happens anyway. Both the pre-check and the `IntegrityError` paths log a clean skip message instead of a stack trace.
  - Old executions (idempotency_key='') are exempt from the unique constraint via the `WHERE` clause, so legacy data doesn't fail the migration.

- [x] **[F5] Dead-letter queue for failed tasks** ✅ Fixed
  - New `FrontlineDeadLetter` model — task_name, task_id, args/kwargs JSON, error_type, error_message, traceback, retry_count, first_failed_at, last_failed_at, resolved_at. Company FK is nullable (set only when the task payload makes it recoverable).
  - New `record_task_failure(task_name, *, task_id, args, kwargs, error_type, error_message, traceback, company_id, retry_count)` helper — wraps everything in try/except so a DLQ write failure can't cascade into another failure. Coerces non-JSON args (Celery passes tuples) via `repr()`.
  - `GET /frontline/dead-letters` lists unresolved entries (or all with `?include_resolved=1`), filterable by `task_name`, paginated. `POST /frontline/dead-letters/<id>/resolve` flips `resolved_at`.
  - Follow-up: actual Celery tasks need to call `record_task_failure` from their `on_failure` handler. The example call shape is in the helper's docstring; the foundation is in place.

---

## 🔵 Polish / UX

- [x] **[P1] Auto-open `kb_gap` ticket from `public_qa`** ✅ Fixed
  - Was: when the public widget got no verified answer, the customer just saw the "I don't know" line and the missed question evaporated. The authenticated `knowledge_qa` view already auto-created `kb_gap` tickets at line 1560; the public path didn't.
  - Fix landed: `public_qa` now also creates a `kb_gap` ticket when `has_verified_info=False` and the user didn't already trigger an explicit handoff. Captures the visitor email/name when supplied, the AI answer, and the retrieval confidence on the ticket. The response now also includes `kb_gap_ticket_id` so the widget can show "we've created ticket #N for a human to follow up". Failure is logged but never breaks the user's reply.
  - The frontline agent's response shape (`'success': True, 'answer': "I don't have verified information…"` etc.) at `core/Frontline_agent/frontline_agent.py:102-116` was already doing the right thing — the missing piece was the auto-ticket on the public path.

- [x] **[P2] Mobile tab overflow** ✅ Already implemented
  - Verified `FrontlineDashboard.jsx:2439` already has the `lg:hidden` hamburger / `hidden lg:block` pill-row pattern lifted from HRDashboard. The audit was wrong on this one — no work needed.

- [x] **[P3] Allowed-origins admin UI** ✅ Fixed
  - Was: the backend accepted `allowed_origins` (comma-separated) via `PATCH /api/frontline/widget/config` and `frontline_widget_config` returned it, but the frontend ignored the response field and offered no input.
  - Fix landed: the Chat widget tab now (a) reads `allowed_origins` from the config response into local state, (b) renders a labelled `Input` + Save button with inline help explaining the CSV format and security trade-off, (c) calls `updateFrontlineWidgetConfig({ allowedOrigins })` on save and reflects the server-canonicalised value back. The service function already existed; only the UI hookup was missing.

---

## ✅ Verified already correct (do not re-audit)

These were checked during the audit and found to be working as intended — future passes can skip them:

- Knowledge per-doc confidentiality / `allowed_users` gating — `core/Frontline_agent/services.py:163-171`
- Frontend `useEffect` cleanup (cancelled-flag pattern) — `FrontlineDashboard.jsx:1810, 1824`
- ErrorBoundary wraps every major section — `FrontlineDashboard.jsx:5`
- Ticket SLA tracking (`sla_due_at`, pause/resume, aging alerts) — `:1683-1709`
- Email-to-ticket ingestion (SendGrid + Mailgun, signature verified, threaded by Message-ID) — `inbound_email.py`
- Internal notes vs customer messages — `TicketNote.is_internal`, `TicketMessage.direction`
- File attachments on ticket messages — `TicketAttachment` model
- KB feedback / gap detection (auto-opens `kb_gap` ticket on misses) — `:1019-1032`
- Public widget origin allowlisting — `:1093`
- Public widget CAPTCHA gate — `:1130-1137`
- Throttling on public endpoints — `FrontlinePublicThrottle`

---

## ⚫ Present but shouldn't be — dead / half-built / wrong-headed

Things found in the code that are doing more harm than good. **Each one should be deleted, finished, or merged with its duplicate** — leaving them in this state is a maintenance trap and a source of future bugs.

Severity legend: **[D]** dead code · **[S]** stub / half-built · **[W]** wrong direction · **[C]** redundant / conflicting

### Dead code — delete

- [ ] **[D1] PayPerProject integration in `Frontline_agent/services.py:1-56`**
  Imports `requests`, hardcoded `PAYPERPROJECT_API = "http://localhost:3000"`, defines `get_all_projects()` / `get_project_info()` / `answer_project_question()`. None of these are imported anywhere in the codebase. Looks like a stub from an early prototype that was never wired up. Delete the file (or delete those three functions and replace with a docstring explaining what the file is for).

- [ ] **[D2] `Frontline_agent/urls.py` — stale, conflicting routing**
  Defines routes like `/api/tickets/<id>/auto-resolve/`, `/api/notifications/`, `/api/workflows/execute/` that don't match the actual mounted routes (which live in `api/urls.py`). If this file is `include()`-d anywhere it's creating phantom endpoints; if not, it's just confusing future readers about which URL file is authoritative. Delete it.

- [ ] **[D3] HubSpot CRM endpoints at `api/views/frontline_agent.py:5012-5117`**
  Four endpoints — `hubspot_status`, `hubspot_update_config`, `hubspot_test_connection`, `hubspot_sync_all` — fully implemented backend with no caller. `frontlineService.js` exports nothing for HubSpot. The HubSpot-related UI references in the frontend live under `components/ai-sdr/SDRCRMSyncTab.jsx`, not Frontline. Either move these endpoints to the AI-SDR agent (where the UI is) or delete them. Leaving them in `frontline_agent.py` mislabels them as Frontline functionality.

- [ ] **[D4] Inbound-email webhook orphaned from any settings UI**
  `inbound_email_webhook()` at `api/views/frontline_agent.py:4462-4557` is fully implemented (SendGrid + Mailgun signature verification, threading, etc.) but the frontend has no UI for setting up inbound addresses, viewing the routing slug, or checking webhook delivery health. You either need to add the settings UI (the data is there) or take down the webhook. As-is it works but new tenants can't actually use it.

### Stub / half-built — finish or remove

- [ ] **[S1] Silent `except: pass` swallowing errors**
  At least 11 spots in `api/views/frontline_agent.py` — lines 846, 1061, 1591, 1599, 3032, 3993, 3998, 4262, 4267, 4356, 4361 — catch exceptions and either `pass` or `log + continue` without propagating. Users see "success" responses on partial failures.
  Fix: replace each with either (a) re-raise, (b) return a 4xx/5xx, or (c) `logger.exception(...)` and a clearly-degraded response payload. Pick per-site based on what failed.

- [ ] **[S2] Workflow approval pipeline is backend-complete but has no frontend**
  Approval endpoints + `awaiting_approval` state exist at `api/views/frontline_agent.py:3630-4462`, but the dashboard has no "Pending approvals" list, no approve/reject buttons, and no notification channel that surfaces them. Without UI, a workflow that pauses on approval just sits forever.
  Fix: lift the approval UI pattern from `HRDashboard.jsx` (which already has it) into the Frontline workflows tab.

- [ ] **[S3] Public widget gate helpers are inconsistently applied**
  `_get_company_by_widget_key()` and `_check_widget_gates()` (`:1049-1114`) exist as the canonical pattern for gating public widget calls, but only some public endpoints actually invoke them. Audit each public endpoint and either route all of them through these helpers or remove the helpers if you've decided the per-endpoint checks are enough. Half-applied patterns are worse than either extreme.

### Misdirected / redundant — consolidate

- [ ] **[W1] Two parallel Q&A paths with overlapping responsibilities**
  `public_qa()` at `:1145` and `knowledge_qa()` at `:1342` both do KB-grounded answering. One is widget-facing (no auth), one is authenticated, but the divergence in implementation (different sanitization, different thresholds, different response shapes) means a fix in one doesn't propagate. Refactor: extract a shared `_answer_question(question, *, role, max_results)` and have both views call it; keep the differences (auth, throttle, response wrapping) at the view layer only.

- [ ] **[W2] Notification scheduling has two overlapping CRUD pathways**
  Template CRUD at `:2287-2425` and scheduled-notification CRUD at `:2560-2713` re-implement the same notification_type / channel / personalization concerns. Pick one as the source of truth and have the other reference it. Right now adding a new channel means updating both.

### Dead storage — fields the UI never touches

- [ ] **[C1] `Ticket.intent` and `Ticket.entities`** (`Frontline_agent/models.py:66-67`)
  Backend code may populate these from triage; no frontend reads or filters by them. Either add `?intent=` filter + a chip on the ticket card showing the detected intent, or drop the fields. Storing unused signal is a soft kind of dead code.

- [ ] **[C2] `Ticket.snoozed_until` + `sla_paused_*` fields** (`models.py:51-59`)
  Snooze + SLA-pause are backend-complete (endpoints exist, audit aging respects them) but the UI has no snooze date picker or pause-reason dropdown. Either expose them in the ticket drawer or remove the backend endpoints. Right now users can hit the API directly but won't discover the feature.

---

### Verification notes (so the next audit doesn't re-investigate)

- I spot-checked **D1** (PayPerProject) and **D2** (Frontline_agent/urls.py) directly — both confirmed in the file system.
- **D3** (HubSpot) is plausible based on cross-referencing the frontend search; the HubSpot UI lives under `components/ai-sdr/`, not `components/frontline/`. Confirm intent with the team before deleting — maybe Frontline was supposed to sync tickets to HubSpot and the UI is just missing.
- The other items are reported on the strength of the audit pass — verify each by reading the cited file:line before fixing.

---

## How to use this file

1. Pick a batch (e.g. all four 🔴 items) and tackle them together.
2. Tick each `- [ ]` to `- [x]` in the same PR that fixes it.
3. Add new findings under the right severity heading as they surface.
4. The ✅ section is a "don't re-investigate" list — append to it as you confirm things, so the next audit doesn't redo work.

# Frontline Agent — Feature Gaps Tracker

**Source:** read-only audit of `frontline_agent/`, `api/views/frontline_agent.py`, `PaPerProjectFront/src/components/frontline/*`, and the embed pages.
**Last updated:** 2026-07-01 (reporting batch — #11–#15 all shipped; every audit item closed)

## Legend
- [x] **Done** — implementation verified in current code with file references.
- [~] **Partial** — half-shipped; remaining work noted underneath.
- [ ] **Not done** — gap still present, scoped/triaged but not implemented.
- ❓ **Needs clarification / design decision** — blocked on a choice you need to make.

---

## High-impact gaps

- [x] **#1 — Single-ticket update endpoint**
  Previously the only way to change one ticket's status/priority/category/assignee was the bulk endpoint (which was overkill and produced confusing "0 updated" replies on no-ops). New `PATCH /api/frontline/tickets/{id}/update` accepts `status` (state-machine validated), `priority`, `category`, and `assigned_to_company_user_id` (null = unassign). Audit-logged, scoped by company. Service helper `updateTicket(id, payload)`.
  Evidence: [`api/views/frontline_agent.py:update_ticket`](api/views/frontline_agent.py), URL at [`api/urls.py:424`](api/urls.py#L424).

- [x] **#2 — Delete contact**
  Contacts had list/create/get/update/merge — but no delete. New `DELETE /api/frontline/contacts/{id}/delete` removes the contact (tickets keep, contact reference detaches). UI: Trash button in the Customer-360 dialog with a destructive confirmation dialog explaining what happens to tickets/notes.
  Evidence: [`api/views/frontline_agent.py:delete_contact`](api/views/frontline_agent.py), URL at [`api/urls.py:494`](api/urls.py#L494), service `deleteContact(id)`, UI in [`FrontlineDashboard.jsx`](PaPerProjectFront/src/components/frontline/FrontlineDashboard.jsx) Customer-360 dialog.

- [x] **#3 — DLQ delete (hard purge)**
  `resolve_dead_letter` only soft-hides rows; over time the table accumulates resolved noise. New `DELETE /api/frontline/dead-letters/{id}/delete` actually removes the row. UI in the Frontline Insights DLQ tile gets a ✕ button next to Resolve.
  Evidence: [`api/views/frontline_agent.py:delete_dead_letter`](api/views/frontline_agent.py), URL at [`api/urls.py:428`](api/urls.py#L428), service `deleteFrontlineDeadLetter`, UI in [`FrontlineInsightsPanel.jsx`](PaPerProjectFront/src/components/frontline/FrontlineInsightsPanel.jsx).

- [x] **#4 — Handoff Release + Reassign**
  Handoff queue previously only had Accept — if a handoff was sent to the wrong agent, the only options were "accept and live with it" or "ignore it". Two new actions:
  - **Release** (button in drawer for `accepted` handoffs) — returns the handoff to the unowned pending pool using the existing `release_handoff` endpoint.
  - **Reassign…** (button in drawer for both `pending` and `accepted` handoffs) — new `POST /api/frontline/tickets/{id}/reassign-handoff` accepts `to_company_user_id` and transfers ownership directly to another agent. Picker dialog lists company users.
  Evidence: backend [`reassign_ticket_handoff`](api/views/frontline_agent.py), URL at [`api/urls.py:460`](api/urls.py#L460), services `releaseHandoff` / `reassignHandoff`, UI buttons + picker in [`FrontlineDashboard.jsx`](PaPerProjectFront/src/components/frontline/FrontlineDashboard.jsx) handoff drawer.

- [x] **#5 — Embed-form file attachments (end-to-end)**
  **Surprise during scoping:** the audit said the backend doesn't support attachments — actually it **already did, for one file**, with magic-byte MIME sniffing + size cap + per-tenant MIME allowlist + safe-filename storage. The real gap was *the embed form didn't expose a picker* and the backend was capped at one file. Three changes:

  1. **Backend ([`public_submit`](api/views/frontline_agent.py))** — extended to **multi-file** (`request.FILES.getlist('files')`, legacy single-`file` shape still works). Enforced caps in priority order: hard count cap (5), per-file size cap from widget config (10 MB default), batch total cap (50 MB), magic-byte MIME sniff against the tenant's allowlist. One bad file in a batch doesn't poison the others — each gets its own pass/skip result with a reason. Storage path now includes the file index (`t<id>_<idx>_<safe_name>`) so two `screenshot.png` uploads don't collide.

  2. **New endpoints for triagers** — `GET /api/frontline/tickets/{id}/widget-attachments` enumerates the company directory (no DB row needed; backend just walks the prefix-matched filenames) and `GET /api/frontline/tickets/{id}/widget-attachments/{filename}/download` streams the file with defence-in-depth path checks (rejects `/`, `\`, `..`, leading dots; re-resolves the path and verifies containment inside the company directory).

  3. **Frontend — embed widget ([`FrontlineEmbedFormPage.jsx`](PaPerProjectFront/src/pages/FrontlineEmbedFormPage.jsx))** — new file picker with paperclip icon, multi-select via `<input multiple>` + per-file `accept` allowlist mirror, client-side guard (5-file count, 10 MB per file, 50 MB total). Files shown as removable chips with size; dedup by (name, size). Submit auto-switches to multipart `FormData` when files are present and falls back to JSON otherwise — legacy callers keep working unchanged. If the backend skips a file (e.g. wrong MIME), the response is parsed and surfaced as a non-fatal "Note: N file(s) were rejected" message instead of failing the whole submit.

  4. **Frontend — triager dashboard** — new "Customer attachments" section in the handoff drawer lists each file as a clickable chip (paperclip + filename + size); clicking opens the auth-gated download URL in a new tab (images / PDFs preview inline, binaries trigger save). Loads lazily when the drawer opens.

  Service helpers `listWidgetAttachments(ticketId)` + `widgetAttachmentDownloadUrl(ticketId, storedFilename)`.

  Evidence: backend [`api/views/frontline_agent.py:public_submit`](api/views/frontline_agent.py) + `_list_widget_attachments_for_ticket` + `download_widget_attachment`, URLs at [`api/urls.py:425-426`](api/urls.py#L425), embed UI in [`FrontlineEmbedFormPage.jsx`](PaPerProjectFront/src/pages/FrontlineEmbedFormPage.jsx), drawer UI in [`FrontlineDashboard.jsx`](PaPerProjectFront/src/components/frontline/FrontlineDashboard.jsx).

  **Note on virus scanning:** the audit asked for a virus-scan policy. We don't have a scanner wired in — but the magic-byte MIME sniff + extension allowlist + size cap is the same model used by the internal ticket flow, and the on-disk paths are never user-controlled (the URL takes only a basename, which we re-validate against `t<ticket_id>_` and the company directory). Adding ClamAV or similar can be a follow-up if the threat model demands it; the current code is closed against the obvious classes (RCE, path traversal, MIME confusion).

- [x] **#6 — Workflow approval frontend**
  Backend `approve_workflow_execution` was reachable from nowhere — workflows pausing with `awaiting_approval` accumulated indefinitely. Added service `approveWorkflowExecution(id, action)` and inline ✓/✕ buttons that appear on execution rows only when their status is `awaiting_approval`. Approve resumes the workflow; reject terminates it.
  Evidence: service in [`frontlineAgentService.js`](PaPerProjectFront/src/services/frontlineAgentService.js), UI handler `handleApproveExecution` + buttons in the executions list under `FrontlineWorkflowsTab` in [`FrontlineDashboard.jsx`](PaPerProjectFront/src/components/frontline/FrontlineDashboard.jsx).

- [x] **#7 — Workflow dry-run UI**
  `dryRunWorkflow` service existed but was never called from any component. Added a PlayCircle button on every workflow row that opens a dry-run dialog showing per-step `simulated: true` results, success/failure badge, and the raw `result_data` as a JSON fallback. Side-effect-free.
  Evidence: `runDryRun` handler + new `dryRunDialog` Dialog in [`FrontlineDashboard.jsx`](PaPerProjectFront/src/components/frontline/FrontlineDashboard.jsx).

## Medium-impact polish gaps

- [x] **#8 — MacroPickerDialog UX rebuild**
  **Surprise during scoping:** the audit said agents had to leave the picker to create a macro. Actually the code already had a "+ New" button (line 173) that swapped the dialog into a create form. **The real issue was the UX:** the form *replaced* the list, so an agent drafting a new macro lost sight of the existing ones to copy structure from. Three improvements shipped:

  1. **Inline-collapsible create panel** above the search/list area — the list stays visible underneath while a new macro is drafted. The mode-switch refactor still uses focused edit mode (one-macro view) for `edit`, but `create` now happens in context.
  2. **"Create '<search>' as a new macro" empty-state CTA** — when a search returns zero results, the empty state offers a button that opens the create panel **with the search string pre-filled as the macro's name**. Saves the "I searched X, didn't find it, now I have to retype X" friction.
  3. **`window.confirm` → shared `ConfirmDialog`** for delete, matching the rest of the app. Two-step destructive confirm with a "this cannot be undone" hint.

  Evidence: rewritten [`MacroPickerDialog.jsx`](PaPerProjectFront/src/components/frontline/MacroPickerDialog.jsx) — separate `createForm` / `editForm` state (so a half-typed create draft survives a search interruption), `createOpen` toggle for the inline panel, `openCreateFromSearch` handler, `ConfirmDialog` mounted alongside the main Dialog.

- [x] **#9 — Ticket Links UI + relation picker**
  Backend exposed list/create/delete on `TicketLink` with six relation types (`duplicate_of`, `blocks`, `blocked_by`, `related`, `parent_of`, `child_of`) — but **no frontend at all** existed. Added 3 service helpers, a `TICKET_LINK_RELATIONS` constant, and a "Linked tickets" section in the handoff drawer with: a list of existing links (relation badge + other-ticket title + remove button), and an inline create form (relation Select + numeric target-ticket ID + Link button). Auto-loads when a drawer opens.
  Evidence: service block at end of [`frontlineAgentService.js`](PaPerProjectFront/src/services/frontlineAgentService.js), state + handlers + JSX in [`FrontlineDashboard.jsx`](PaPerProjectFront/src/components/frontline/FrontlineDashboard.jsx) handoff drawer.

- [x] **#10 — Notification template channel dropdown reflects reality**
  Dropdown used to offer `email` / `sms` / `in_app` — but the backend dispatcher (`_dispatch_notification`) only routes `email`, `slack`, and `teams`; sms + in_app are silently dropped. Two fixes: added the actually-implemented `slack` and `teams` options (with hint that they use the global PM webhook), and disabled `sms` + `in_app` with a "coming soon" label so users can see what's planned without saving templates that'll never fire.
  Evidence: [`FrontlineDashboard.jsx`](PaPerProjectFront/src/components/frontline/FrontlineDashboard.jsx) template Channel `<Select>`.

## Lower-impact reporting gaps

- [x] **#11 — Meeting action-items now have an inbox**
  Extracted items were being written to `FrontlineMeeting.action_items` and forgotten — no dashboard view. Two new endpoints: `GET /api/frontline/meetings/action-items` aggregates every meeting's items into a flat, filterable inbox with meeting title, owner, due date, and aging (days since the meeting); `POST /api/frontline/meetings/{id}/action-items/{idx}/toggle-done` flips a `done` flag in place on the JSON blob (item ordering is preserved so the index stays stable). Fifth tile added to `FrontlineInsightsPanel` — shows up to 5 open items, oldest-aging first, with a green ✓ toggle. Aging ≥ 14d renders the aging badge red so stale items stand out. **Trade-off documented:** re-running `extract_meeting_action_items` overwrites the array — including `done` flags — which is acceptable since re-extract is a manual admin action, but flagged for future work if it becomes a pain point.
  Evidence: [`api/views/frontline_agent.py`](api/views/frontline_agent.py) — `list_meeting_action_items` + `toggle_meeting_action_item`, URLs at [`api/urls.py:481-482`](api/urls.py#L481), service `listMeetingActionItems` + `toggleMeetingActionItem`, tile in [`FrontlineInsightsPanel.jsx`](PaPerProjectFront/src/components/frontline/FrontlineInsightsPanel.jsx).

- [x] **#12 — CSAT drill-down: per-agent + monthly trend**
  `satisfaction_summary` extended with opt-in `?by_agent=1` and `?by_month=1` add-ons (baseline payload unchanged, so the existing overview tile keeps its small response). Frontend fetches both when the Analytics tab loads and renders two new tables under a "CSAT drill-down" heading: (1) header stats with inline distribution bars (5★–1★ percentages), (2) monthly trend table with month-over-month delta (+/- coloured green/red beyond ±0.05), (3) per-agent table highlighting outliers — green rows for avg ≥ 4.5 with 3+ responses, red rows for avg < 3.5 with 3+ responses. Median vs. mean discussed: kept mean for CSAT because ratings are 1–5 discrete, so mean is intuitive and the small range limits skew.
  Evidence: [`api/views/frontline_agent.py:satisfaction_summary`](api/views/frontline_agent.py), service `getFrontlineSatisfactionSummary({ byAgent, byMonth })`, UI in `FrontlineAnalyticsTab` inside [`FrontlineDashboard.jsx`](PaPerProjectFront/src/components/frontline/FrontlineDashboard.jsx).

- [x] **#13 — Per-agent performance drill-down**
  Backend already computed per-agent metrics but the frontend never rendered them. Enhanced the endpoint with **median resolution time** (more robust than mean for skewed data — one 30-day-old ticket that finally closes was distorting rankings) and **SLA breach percentage** (breached ÷ resolved, since only resolved tickets can definitively be checked for breach). New sortable table in the Analytics tab: agent, assigned, resolved (with `(N auto)` sub-count), rate, median resolve time, SLA breach %. Two outlier heuristics with visual highlighting: **rose row** if breach % ≥ 15 percentage points above team average AND resolved ≥ 3; **amber row** if median resolve time ≥ 1.5× team median AND resolved ≥ 3. Footer explains the highlighting policy so it's not folklore.
  Evidence: [`frontline_agent_performance`](api/views/frontline_agent.py) (backend metric additions), Team Performance section in `FrontlineAnalyticsTab` inside [`FrontlineDashboard.jsx`](PaPerProjectFront/src/components/frontline/FrontlineDashboard.jsx).

- [x] **#14 — KB coverage gaps: dismiss + draft-KB-doc quick actions**
  New `KBCoverageDismissal` model (company + normalised question_key + optional snooze_until) with migration; the coverage report filters out currently-active dismissals. Two actions per row in the "Knowledge gaps" tile: **📄 Draft KB doc** copies the question to clipboard + navigates to the Documents tab (agent pastes it as the doc title after uploading), and **👁 Dismiss** with a dropdown offering Snooze 24h / 7d / 30d or Dismiss permanently. Snoozes are capped at 30 days server-side so an over-eager click can't hide a real issue forever. Response includes a `dismissed_count` for a subtle footer badge — no permanent counter, just current state.
  Evidence: [`frontline_agent/models.py:KBCoverageDismissal`](frontline_agent/models.py), migration `0042_kbcoveragedismissal`, backend [`kb_coverage_report`](api/views/frontline_agent.py) (filter) + [`dismiss_kb_coverage_gap`](api/views/frontline_agent.py), URL at [`api/urls.py:440`](api/urls.py#L440), tile in [`FrontlineInsightsPanel.jsx`](PaPerProjectFront/src/components/frontline/FrontlineInsightsPanel.jsx).

- [x] **#15 — Analytics export meetings filter**
  The meetings branch of `frontline_analytics_export` exited before the ticket branch's filter loop — so `?status=scheduled` returned every meeting in the window, not scheduled ones. Now applies **status** (valid on `FrontlineMeeting`) and **organizer_id** (meetings-specific), silently ignores **priority/category** with an `INFO` log line (they're ticket-only fields), and the docstring documents which filters apply to which entity. Backwards-compatible: existing ticket callers unchanged.
  Evidence: [`api/views/frontline_agent.py:frontline_analytics_export`](api/views/frontline_agent.py).

---

## Summary

| Status | Count | Items |
|---|---|---|
| Done | **15** | 1–15 (every item from the initial audit) |

### Landed this session (2026-07-01 — reporting batch)

Backend: 1 new model + migration (`KBCoverageDismissal`), 4 new endpoints (`dismiss_kb_coverage_gap`, `list_meeting_action_items`, `toggle_meeting_action_item`; `frontline_analytics_export` and `satisfaction_summary` extended), 3 new URL routes, enhanced `frontline_agent_performance` with median + breach %.
Frontend: 4 new service helpers (`dismissKbCoverageGap`, `listMeetingActionItems`, `toggleMeetingActionItem`, `getFrontlineSatisfactionSummary` extended), fifth tile added to `FrontlineInsightsPanel` (Meeting action items), dismiss/snooze dropdown + Draft KB doc action on the KB tile, two new sections in `FrontlineAnalyticsTab` (Team performance table with outlier highlighting; CSAT drill-down with monthly trend + per-agent breakdown).

Sanity-checked: 3 Python files parse, 3 JSX/JS files compile via esbuild, `python manage.py check` reports no issues, migration applied cleanly.

---

## Open items

None. Every item from the audit is now closed. If more gaps surface during use, they'd get added here as a new batch.

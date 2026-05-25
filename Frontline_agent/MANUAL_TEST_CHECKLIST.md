# Frontline Agent — manual test checklist

For verifying everything that landed during the audit pass. Tick boxes as you
go; if anything fails, note the symptom in the box. Grouped by feature area so
a tester can pick a batch.

**Prereqs**
- Server running (`python manage.py runserver`)
- Celery worker + beat running (`celery -A project_manager_ai worker -l info` and a separate `celery -A project_manager_ai beat -l info`)
- At least one company + CompanyUser + Employee + one HR document already in the DB

---

## 0. Sanity (5 min)

- [ ] **Django check** — `python manage.py check` returns `System check identified no issues`
- [ ] **Migrations applied** — `python manage.py showmigrations Frontline_agent` shows `0037_tags_links_contact_notes` as applied (latest)
- [ ] **Beat startup log** — celery beat console shows `Scheduled Tasks: N (Celery Beat)` and the count includes `frontline-auto-close-inactive-tickets` and `frontline-escalate-near-breach-tickets`
- [ ] **FAISS path log** — server startup logs `Frontline vector store: FAISS active` (or the explicit fallback warning if you don't have faiss installed)

---

## 1. Critical bug fixes (15 min)

### B1 — cross-tenant ticket leak
- [ ] Log in as a user in Company A, note one of their ticket IDs.
- [ ] Log in as a user in Company B. `GET /api/frontline/tickets/?status=open` — should return 0 of Company A's tickets.
- [ ] As Company B user, try `GET /api/frontline/tickets/<id>` (where `<id>` is A's ticket). Expected: 404.

### B2 — ticket status state machine
- [ ] Pick a ticket in `closed` status. `POST /api/frontline/tickets/<id>/task` with `{"status": "new"}`. Expected: 400 with message *"Illegal status transition 'closed' → 'new'. Allowed from 'closed': ['open']."*
- [ ] Same ticket, `POST` `{"status": "open"}`. Expected: 200, status flips to open. **Also**: check `GET /api/frontline/audit-log/?target_type=ticket&target_id=<id>` — should see both a `ticket.status_change` AND a separate `ticket.reopen` entry (T5).

### B4 — MIME-spoofed upload
- [ ] Rename a `.exe` (or any binary) to `evil.pdf`.
- [ ] In the embed widget, submit a ticket with that file attached.
- [ ] Expected: ticket gets created BUT `attachment.skipped = true`, `reason = 'unrecognized_content'`. (Don't expect the file to upload.)

---

## 2. Conversation memory + RAG quality (10 min)

### K1 — follow-up turns carry context
- [ ] In Knowledge Q&A tab, start a chat: *"What's our refund policy?"* → gets an answer.
- [ ] Follow up: *"What about international orders?"* — **with the previous chat still loaded**.
- [ ] Expected: the answer addresses refunds for international orders, not generic info. Backend log should show `Contextualised follow-up via history: 'What about…' → 'What is the refund policy for international orders…'`.

### K2 — page numbers on citations
- [ ] Upload a multi-page PDF (handbook, policy, etc.).
- [ ] Wait for `processing_status='ready'`.
- [ ] Ask a question whose answer is on, say, page 4.
- [ ] Expected: the response's `citations` (or chunk title) includes `p.4` suffix.

### D-O1 — OCR fallback (only if OCR libs installed)
- [ ] Upload an image-only / scanned PDF.
- [ ] Wait for processing.
- [ ] Expected (with pdf2image + pytesseract installed): log says `OCR fallback won: N chars (text-layer was X) — using OCR result`, and `document_content` has real text.
- [ ] Expected (without OCR libs): `processing_error` contains `ocr_used=unavailable` and a clear log line explaining how to install.

---

## 3. New endpoints (30 min)

### Macros (F1)
- [ ] `POST /api/frontline/macros/create` `{"name": "Greeting", "body": "Hi! Thanks for reaching out."}`. Expected: 201, audit entry `macro.create`.
- [ ] `GET /api/frontline/macros` — should return the new macro.
- [ ] `POST /api/frontline/macros/<id>/bump` — `times_used` goes up by 1.
- [ ] Try creating another macro with the same name — expected: 400 "already exists".

### Goals & CSAT (F2)
- [ ] Transition a ticket from `open` → `resolved`. Check the requester's inbox for a CSAT email; the link should be `…/embed/csat?t=<token>`.
- [ ] `POST /api/frontline/csat/submit {"token": "...", "rating": 4, "comment": "good"}` — expected: 200.
- [ ] Same token, send again with rating 5 — should overwrite, not duplicate.
- [ ] `GET /api/frontline/csat/summary` — `response_count` ≥ 1, `average ≈ 5.0`.

### Bulk ticket update (F3)
- [ ] Pick 3 ticket IDs in different statuses. `POST /api/frontline/tickets/bulk-update` `{"ids": [...], "priority": "high"}`. Expected: response includes `updated`, `skipped` (if any), `not_found` arrays.
- [ ] Try with `{"ids": [...], "status": "new"}` on a closed ticket — should land in `skipped` with reason "Illegal status transition".

### DLQ list (F5)
- [ ] `GET /api/frontline/dead-letters` — returns empty list initially (success).
- [ ] No easy way to manually fail a task; this is mostly a smoke test that the endpoint responds 200.

### Ticket tags (T1)
- [ ] `POST /api/frontline/tickets/<id>/task` `{"tags": ["billing", "urgent-customer", "refund"]}`.
- [ ] `GET /api/frontline/tickets/?tag=billing&tag=refund` — should return that ticket.
- [ ] `GET /api/frontline/tickets/?tag=billing&tag=does-not-exist` — should return empty.

### Description search (T2)
- [ ] Create a ticket with description "The user can't reset their password".
- [ ] `GET /api/frontline/tickets/?q=password` — should return it.
- [ ] `GET /api/frontline/tickets/?q=xyzabc123` — should return empty.

### Ticket links (T3)
- [ ] Create 2 tickets. `POST /api/frontline/tickets/<A>/links/create` `{"to_ticket_id": <B>, "relation": "blocks"}`. Expected: 201.
- [ ] `GET /api/frontline/tickets/<A>/links` — shows the outgoing link.
- [ ] `GET /api/frontline/tickets/<B>/links` — shows the same link as `direction: 'incoming'`.
- [ ] Try to link a ticket to itself — expected: 400.

### Document soft-deprecation (D-O2)
- [ ] `POST /api/frontline/documents/<id>/mark-outdated` on an indexed doc.
- [ ] Ask a knowledge question whose answer is in that doc. Expected: now answers "I don't know" or pulls from a different doc.
- [ ] `POST /api/frontline/documents/<id>/unmark-outdated`. Ask again — should answer correctly.

### Document re-ingest (D-O3)
- [ ] `POST /api/frontline/documents/<id>/reingest` on a `ready` doc.
- [ ] Status flips to `processing` immediately. After Celery picks it up, returns to `ready`.

### Contact notes + merge (C-N1, C-N2)
- [ ] Pick a Contact with at least 1 ticket. `POST /api/frontline/contacts/<id>/notes/create` `{"body": "VIP — escalate.", "is_pinned": true}`. Expected: 201.
- [ ] `GET /api/frontline/contacts/<id>/notes` — pinned note first.
- [ ] Create 2 contacts (A: rich data, B: same email). `POST /api/frontline/contacts/merge {"source_id": B, "target_id": A}`. Expected: 200, `notes_moved` and `tickets_moved` counts, B is gone from `GET /api/frontline/contacts/<B>`.

### Handoff release (H1)
- [ ] Find a ticket with `handoff_status='accepted'` (or create one and accept it).
- [ ] `POST /api/frontline/tickets/<id>/release-handoff`. Expected: 200, `handoff_status='pending'`, `assigned_to` cleared.
- [ ] Try on a ticket that ISN'T in `accepted` state — expected: 400.

### KB coverage report (KB-C1)
- [ ] Submit some unanswerable questions via Knowledge Q&A so `kb_gap` tickets get created.
- [ ] `GET /api/frontline/kb-coverage?window_days=30&top_n=5`. Expected: list of `{question, kb_gap_count, thumbs_down_count}` items.

### SLA dashboard (S4)
- [ ] `GET /api/frontline/sla/dashboard?window_days=30`. Expected: returns `total_tickets`, `breached`, `breach_pct`, `at_risk`, `per_priority`, `top_breaching_assignees`.

### Audit log (L2)
- [ ] `GET /api/frontline/audit-log/?target_type=ticket&limit=10`. Should list the recent ticket mutations from earlier steps (status changes, reopens, bulk updates, etc.).

---

## 4. Notifications & channels (20 min)

### Slack channel (N1)
- [ ] Get a real Slack incoming-webhook URL (test workspace is fine).
- [ ] Set `Company.frontline_slack_webhook_url` via Django shell or admin.
- [ ] Create a `NotificationTemplate` with `channel='slack'`, `body="Test from Frontline"`, `notification_type='alert'`.
- [ ] Send it (via `/api/frontline/notifications/<id>/send-now/` or similar). Expected: message appears in Slack.
- [ ] Set the webhook to a garbage URL — send again. Expected: returns failure, log line "Slack send failed for company …".

### Teams channel (N1)
- [ ] Same as Slack but with MS Teams webhook. Expected: MessageCard with subject as title appears in the Teams channel.

### Per-template quiet hours (N2)
- [ ] Edit a template: set `quiet_hours = {"enabled": true, "start": "00:00", "end": "23:59", "timezone_name": "UTC"}` (effectively always quiet).
- [ ] Send the template. Expected: response is 202 Accepted with `deferred_reason='template_quiet_hours'`, NOT a 200 send.
- [ ] Set `quiet_hours.override_user_quiet_hours = true` on an urgent template — set the recipient's per-user quiet hours to a window covering now — send the template. Expected: 200 sent (the override skipped the per-user check).

### Allowed origins UI (P3)
- [ ] In the Chat widget tab, you should see an "Allowed origins" input.
- [ ] Enter `https://example.com,https://app.example.com` and Save. Expected: toast says "Allowed origins saved".
- [ ] From a browser tab on a non-allowed origin, hit the embed widget Q&A endpoint. Expected: 403 with "Origin not allowed for this widget key".

### Per-widget-key throttle (P-S1)
- [ ] Hit `/api/frontline/embed/ask/` (or `public_qa`) with a valid widget_key 250 times in a minute.
- [ ] Expected: starts getting 429 at request ~200 (the new `frontline_widget_key: 200/hour` rate).

### Question length cap (L6)
- [ ] Send a public Q&A request with a 5000-char question. Expected: 400 "Question too long (max 2000 characters)".

---

## 5. Workflow + idempotency (10 min)

### F4 — workflow idempotency
- [ ] Find a workflow that fires on `ticket_created`. Manually call `_run_workflow_triggers` for the same workflow + same ticket twice (via Django shell or by re-firing the post_save signal).
- [ ] Expected: only one `FrontlineWorkflowExecution` row created. Second call logs "skipping duplicate" and exits cleanly.

### W3 — per-step Slack timeout
- [ ] Edit a workflow with a `slack` step. Set `step['timeout_seconds'] = 1`. Point `webhook_url` at a slow / blocking endpoint (or use Slack's own URL with a known-slow workspace).
- [ ] Run the workflow. Expected: step fails with timeout error after ~1s, doesn't hang.

---

## 6. Celery tasks (next day, after Beat has run)

### T4 — auto-close inactive
- [ ] Manually create a ticket, flip to `resolved`. In Django shell, backdate `updated_at` to 8 days ago: `t.updated_at = now - timedelta(days=8); t.save()`.
- [ ] Run the task manually: `from Frontline_agent.tasks import auto_close_inactive_tickets; auto_close_inactive_tickets()`.
- [ ] Expected: returns `{'closed': N>=1, ...}`. The ticket is now `closed`. Audit log has a `ticket.auto_close` entry.

### S3 — escalate near-breach
- [ ] Manually create a ticket with `sla_due_at = now + 30 minutes`, priority `medium`.
- [ ] Run `from Frontline_agent.tasks import escalate_near_breach_tickets; escalate_near_breach_tickets()`.
- [ ] Expected: returns `{'escalated': >=1, ...}`. Ticket's `priority` is now `urgent`. Audit log has `ticket.sla_escalate`.
- [ ] Run it again. Expected: 0 escalated (idempotent — ticket is already urgent).

### Business-hours SLA (S1)
- [ ] In the embed config tab, enable operating hours, Mon-Fri 9-5 in your TZ.
- [ ] Create a ticket via the embed widget at, say, Friday 4 PM with priority `medium` (24h SLA).
- [ ] Expected: `sla_due_at` is Monday 3 PM (8 business hours into Mon), NOT Saturday 4 PM. Verify in Django shell.

---

## 7. Failure modes / regressions to spot-check

### GDPR-adjacent
- [ ] Anonymize a Contact (via shell — there's no Contact anonymize endpoint, only Employee). Check that linked ContactNotes still resolve via the FK.

### Vector index dirty after outdated flip
- [ ] Mark a doc outdated, immediately ask a knowledge question. Expected: doc not in results.
- [ ] Unmark, ask again. Expected: doc is in results again.

### Tag-filter SQL Server compatibility
- [ ] If you're on SQL Server, verify `?tag=foo` works at all (JSONField `__contains` has edge cases there). If it 500s, fall back to a Python-side filter.

### Audit log volume
- [ ] After 100+ ticket updates, check `FrontlineAuditLog` row count and `created_at` index speed: `EXPLAIN SELECT * FROM Frontline_agent_frontlineauditlog WHERE company_id = X ORDER BY created_at DESC LIMIT 50;` should use the `(company, -created_at)` index.

---

## When something fails

For each failed test, capture:
1. **What you did** (exact request body / button click)
2. **What you saw** (status code, error message, log lines)
3. **The relevant audit-log entries** if any (`GET /api/frontline/audit-log/?target_type=…&target_id=…`)
4. **Server log slice** — the last 50 lines of Django + Celery output

Then ask Claude to dig in with those details.

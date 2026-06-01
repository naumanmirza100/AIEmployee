# HR Support Agent — manual test checklist

Verification for everything that landed during the HR audit pass. Same shape
as `Frontline_agent/MANUAL_TEST_CHECKLIST.md`.

**Prereqs**
- Server running (`python manage.py runserver`)
- Celery worker + beat running
- At least one Company, one HR-admin CompanyUser, and a couple of Employee rows
- An HR document already uploaded (handbook, policy, payslip — anything)

⚠️ **Most of these need API calls — there's no UI yet for the new endpoints.**
Use `curl`, Postman, or the existing dashboard's network tab to exercise them.
See the bottom of this file for the list of missing UI hookups.

---

## 0. Sanity (5 min)

- [ ] `python manage.py check` → "System check identified no issues"
- [ ] `python manage.py showmigrations hr_agent` → `0013_parity_with_frontline` is applied
- [ ] `python manage.py showmigrations core` → `0070_hr_channel_webhooks` is applied
- [ ] Celery beat startup log shows the HR tasks (`hr_agent.tasks.process_hr_scheduled_notifications`, `walk_hr_time_based_events`, `accrue_leave_balances`, `purge_hr_audit_log`)

---

## 1. Critical bug fixes (10 min)

### B1 — Leave balance race
- [ ] Create a pending leave request for an employee, days_requested=3. Note their `LeaveBalance.used_days`.
- [ ] Approve it once. `used_days` increases by 3. Audit log entry `leave_request.approve` exists.
- [ ] Now do a quick concurrent-ish test: try to approve the same already-approved request again. Expected: 400 "Leave request is approved, not pending".
- [ ] If you can spare a Django shell: open two shells, race them both calling `decide_leave_request` on a pending leave. Only one should succeed; balance should still be `+3`, not `+6`.

### B2 — Self-review deadline
- [ ] Create a `PerformanceReviewCycle` with `self_review_due` in the past (e.g. yesterday).
- [ ] Create a `PerformanceReview` row for an employee in that cycle.
- [ ] Hit `POST /api/hr/reviews/<id>/update` as that employee (not HR-admin) with `{"self_summary": "test"}`. Expected: 400 with message naming the deadline.
- [ ] Same call as an HR-admin. Expected: 200 (admin override works).

---

## 2. Loopholes (10 min)

### L1 — Meeting-cancel audit
- [ ] Schedule a meeting, then cancel it via `POST /api/hr/meetings/<id>/cancel` with `{"reason": "Test"}`.
- [ ] `GET /api/hr/audit-log/?target_type=meeting&target_id=<id>` should show a `meeting.cancel` entry with `before.status` and `after.reason='Test'`.

### L2 — Employment status state machine
- [ ] Pick an `active` employee. `POST /api/hr/employees/<id>/update` (as a NON-admin) with `{"employment_status": "candidate"}`. Expected: 400 "Illegal employment_status transition 'active' → 'candidate'…".
- [ ] Same call as HR-admin. Expected: 200 (admins override).
- [ ] `POST /api/hr/employees/<id>/update` with `{"employment_status": "offboarded"}` then again to `active` (as HR-admin both times). Both should succeed because admin bypasses the map.

### L3 — Goal weight cycle-sum
- [ ] Create a review cycle. Create goal 1 with `weight_pct=60` linked to that cycle → 200.
- [ ] Create goal 2 with `weight_pct=50` linked to that cycle → expected 400 "Goal weights for this cycle would total 110%…".
- [ ] Update goal 1 to `weight_pct=40` → 200 (now sum is 40 + 50 = 90 if both exist).
- [ ] Goals without a `cycle_id` should pass any weight — verify by creating one with weight_pct=80 and no cycle.

---

## 3. New endpoints (20 min)

### F1 — Document access log on Q&A
- [ ] Make sure at least one HR doc is indexed (`processing_status='ready'`).
- [ ] Hit `POST /api/hr/knowledge-qa` with a question whose answer is in that doc.
- [ ] Inspect `HRDocumentAccessLog` rows (Django admin or shell). Expected: a new row per cited doc with `action='read'`, your IP, your CompanyUser as actor.
- [ ] No citation in the result = no log row (verify by asking a question with no good match).

### F2 — Half-day / hourly leave
- [ ] `POST /api/hr/leave-requests/submit` with `{"employee_id": X, "start_date": "2026-01-15", "end_date": "2026-01-15", "leave_type": "vacation", "partial_day_period": "morning"}`. Expected: 201 with `days_requested=0.5`, `partial_day_period="morning"`.
- [ ] Same but `partial_day_period="hours", partial_hours=2.5`. Expected: 201 with `days_requested=0.31` (2.5/8 rounded to 2dp).
- [ ] `partial_day_period="hours"` without `partial_hours` → 400.
- [ ] `partial_day_period="hours"` with `partial_hours=10` → 400 ("must be > 0 and < 8").
- [ ] `partial_day_period="morning"` with `start_date != end_date` → 400.
- [ ] Approve a half-day request, verify the matching `LeaveBalance.used_days` increments by exactly 0.5.

### F3 — GDPR right-to-export
- [ ] `GET /api/hr/employees/<id>/export` as HR-admin for an employee with some history. Expected: a ZIP download.
- [ ] Open the ZIP. Should contain: `profile.json`, `leave_requests.json`, `leave_balances.json`, `compensation.json`, `performance_reviews.json`, `goals.json`, `audit_log.json`, `document_access_log.json`, `README.txt`, `documents/_index.json`, and `documents/<id>_<filename>` for each personal doc with a file_path.
- [ ] As a non-admin employee, try to export ANOTHER employee → 403.
- [ ] As a non-admin employee, export YOURSELF → 200, ZIP downloads.
- [ ] `GET /api/hr/audit-log/?action=employee.gdpr_export&target_id=<id>` should show the export was logged.

### D-F2 — Document outdated flag
- [ ] `POST /api/hr/documents/<id>/mark-outdated` as HR-admin. Audit-log entry created.
- [ ] Now ask a knowledge question whose answer was in that doc. Expected: agent returns "I don't know" OR pulls from a different doc.
- [ ] `POST /api/hr/documents/<id>/unmark-outdated`. Ask the same question again — should answer correctly.
- [ ] As non-admin → 403.

### D-F3 — Document reingest
- [ ] Pick a doc with `processing_status='failed'` (or any doc). `POST /api/hr/documents/<id>/reingest` as HR-admin.
- [ ] Doc's status should flip to `processing` immediately. Existing `HRDocumentChunk` rows are gone (chunks_total=0, chunks_processed=0). Audit log entry `hr_document.reingest`.
- [ ] After Celery picks it up, status returns to `ready` and chunks repopulate.
- [ ] As non-admin → 403.

### D-F1 — Page numbers on chunks
- [ ] Upload a multi-page PDF as an HR doc.
- [ ] After processing, query the DB: `HRDocumentChunk.objects.filter(document_id=X).values('chunk_index', 'page_number')[:10]`. Expected: chunks have `page_number` populated (not all `None`).
- [ ] Ask a question whose answer is on a specific page. Citation title in the response should include `p.N`.

### W-F1 — Workflow execution idempotency
- [ ] Find an HR workflow that triggers on `employee_hired` (or create one via `POST /hr/workflows/from-template` with `new_hire_onboarding`).
- [ ] Create a new Employee (which fires `employee_hired`). One execution row appears.
- [ ] In Django shell, fire the signal again for the same employee:
  ```python
  from django.db.models.signals import post_save
  from hr_agent.models import Employee
  emp = Employee.objects.get(pk=...)
  post_save.send(sender=Employee, instance=emp, created=True)
  ```
- [ ] Expected: log says `HR workflow trigger: skipping duplicate`. No second execution row created.

---

## 4. Notifications (15 min)

### N-F1 — Slack channel
- [ ] Get a real Slack incoming-webhook URL. Set `Company.hr_slack_webhook_url` via Django shell:
  ```python
  from core.models import Company
  c = Company.objects.get(id=...)
  c.hr_slack_webhook_url = 'https://hooks.slack.com/services/...'
  c.save()
  ```
- [ ] Create an `HRNotificationTemplate` with `channel='slack'`, `body='Test from HR'`, `notification_type='system'`.
- [ ] Create an `HRScheduledNotification` row with this template, `scheduled_at=now`, status='pending', `recipient_email='test@test.com'`.
- [ ] Wait for the next minute-tick of `process_hr_scheduled_notifications` (or call manually: `from hr_agent.tasks import process_hr_scheduled_notifications; process_hr_scheduled_notifications()`).
- [ ] Expected: message appears in Slack. Notification row → `status='sent'`.
- [ ] Set the webhook URL to garbage. Resend. Expected: notification stays `pending` (retry scheduled).

### N-F1 — Teams channel
- [ ] Same as Slack but using `Company.hr_teams_webhook_url` and `template.channel='teams'`. Expected: a MessageCard with the template subject as title appears in the Teams channel.

### N-F2 — Per-template quiet hours
- [ ] Edit a template: set `quiet_hours = {"enabled": true, "start": "00:00", "end": "23:59", "timezone_name": "UTC"}` (effectively always quiet).
- [ ] Schedule + process a notification using this template. Expected: notification stays `pending`, `deferred_reason='template_quiet_hours'`, `scheduled_at` pushed to next legal time.
- [ ] Set `quiet_hours.override_user_quiet_hours = true` and put the recipient's `FrontlineNotificationPreferences.quiet_hours_enabled=true` (any time window covering now). Process — expected: sends immediately (per-template override skipped per-user quiet check).

---

## 5. Celery tasks (separate session, after Beat has run)

### Leave-balance accrual
- [ ] Create a `LeaveAccrualPolicy` for the company: `period='monthly'`, `days_per_period=1.67`, `leave_type='vacation'`, `is_active=True`.
- [ ] Run manually: `from hr_agent.tasks import accrue_leave_balances; accrue_leave_balances()`.
- [ ] Each active employee's vacation `accrued_days` should increase by 1.67. Policy's `last_run_at` is set. Running again immediately should skip (period gate).

### Audit log purge
- [ ] In Django shell, backdate some audit rows: `HRAuditLog.objects.filter(...).update(created_at=now - timedelta(days=800))`.
- [ ] Run: `from hr_agent.tasks import purge_hr_audit_log; purge_hr_audit_log()`.
- [ ] Old rows deleted. Returns `{'deleted': N, 'cutoff': '...', 'retention_days': 730}` (or your `HR_AUDIT_LOG_RETENTION_DAYS` setting).

### Walk time-based events
- [ ] Pick an Employee, set their `probation_end_date` to `today + timedelta(days=7)`.
- [ ] Create an `HRNotificationTemplate` with `trigger_config = {"on": "probation_ending", "days_before": 7}`.
- [ ] Run: `from hr_agent.tasks import walk_hr_time_based_events; walk_hr_time_based_events()`.
- [ ] One `HRScheduledNotification` row should be created for that employee + template combo. Re-running should be a no-op (idempotent within the same day).

### Meeting reminders + timezone
- [ ] Create an `HRMeeting` 24h from now in a non-UTC timezone (e.g. `timezone_name='America/Los_Angeles'`).
- [ ] Run `from hr_agent.tasks import send_hr_meeting_reminders; send_hr_meeting_reminders()` near the 24h-out window.
- [ ] Email body should show the meeting time *in PT*, not UTC.

---

## 6. Regressions to spot-check

### Frontline `DocumentProcessor` shared by HR
- [ ] Upload a scanned (image-only) PDF as an HR doc. Without OCR libs: `processing_error` says `ocr_used=unavailable` with install instructions. With OCR libs installed: log says `OCR fallback won`, `document_content` has real text. **HR inherits Frontline's D-O1 OCR fix.**

### Department cycle detection
- [ ] Create Dept A. Create Dept B with `parent=A`. Try to `update_department` Dept A with `parent=B`. Expected: 400 "Setting this parent would create a circular department hierarchy."

### Existing functionality I didn't touch
- [ ] `GET /api/hr/dashboard` still returns stats.
- [ ] `GET /api/hr/me` still works for the calling user.
- [ ] `GET /api/hr/org-chart` renders.
- [ ] `POST /api/hr/employees/<id>/anonymize` still works for HR-admin.
- [ ] Sample workflow execution from a template still runs.

---

## 7. UI status

### ✅ Now wired (test via the dashboard, not just curl)

- **GDPR export button** — `HREmployeeDetailDrawer`, sky-blue "Export data" button next to Edit / Anonymize. Click → ZIP downloads.
- **Mark/unmark document outdated** — Documents tab → per-card overflow menu → "Mark outdated" or "Restore". Card shows a rose "outdated" badge while flagged.
- **Reingest button** — Documents tab → per-card overflow menu → "Re-ingest". Confirms first; status flips to `processing` immediately.
- **Half-day / hourly leave picker** — `HRLeaveTab` new-request dialog → new "Time off" select (Full / Morning / Afternoon / Specific hours). When partial, end_date is auto-locked to start_date.
- **Goal weight running total** — Goal create/edit dialog → live hint below the Weight input showing "Cycle total: X% (other goals Y%, max 100%)". Turns rose + shows "Save will be rejected" if projected total exceeds 100.

### ✅ Now wired (continued)

- **Notification template — Slack / Teams channels** — `HRNotificationsTab` template-create/edit dialog → Channel dropdown now includes "Slack (webhook)" and "MS Teams (webhook)". An amber inline hint appears reminding the admin which `Company` field to set.
- **Notification template — per-template quiet hours** — same dialog → new "Quiet hours for this template" toggle. When on, reveals Start / End / Timezone inputs plus an "Override recipient's personal quiet hours" checkbox (for urgent alerts).
- **Notification template — `review_due` trigger event** — added to the Trigger event dropdown.

### ⏳ Still missing UI (next batch when needed)

- **Slack / Teams webhook URLs** — needs an HR Settings tab. Backend fields exist on `Company` (`hr_slack_webhook_url`, `hr_teams_webhook_url`). Set via Django shell for now until a Settings tab gets built.
- **Reopen audit display** — show recent `ticket.reopen` / `leave_request.reopen` entries on detail panels. Data is in the audit log, just no surfaced view.

---

## When something fails

For each failure, capture:
1. What you sent (full request body / shell command)
2. What you got back (status + JSON body / shell traceback)
3. Server log slice (last 20 lines from `runserver` + Celery worker output)
4. Audit log entries: `GET /api/hr/audit-log/?target_type=…&target_id=…`

Then ask Claude to dig into those specifics.

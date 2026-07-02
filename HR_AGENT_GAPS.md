# HR Agent — Gap Closure

This document captures the audit-and-fix sweep that closed the HR agent's
functional gaps in the same style as the earlier Operations, PM, and Frontline
sweeps. Read this to understand what changed and why — the code itself covers
the how.

## Summary

Eight prioritised gaps were surfaced; seven required code changes and one
turned out to be an audit false-alarm. All eight are closed.

| # | Gap | Status | Notes |
|---|-----|--------|-------|
| 1 | Notification template edit + delete | ✅ | Endpoints, service, UI wired |
| 2 | Notification "send-now" | ✅ | HR-admin only, dispatches through the same channel resolver as scheduled sends |
| 3 | Leave balance view + adjust | ✅ | Self/report/HR-admin gated view; HR-admin only adjust with reason required |
| 4 | Employee deactivate/reactivate | ✅ | First-class endpoints, distinct from generic status update |
| 5 | Leave withdraw vs cancel semantics | ✅ | New `withdrawn` status + endpoint; restores balance |
| 6 | Close/reopen review cycle | ✅ | Optional review release on close; symmetric reopen |
| 7 | HR meeting reminder Celery task | ✅ (false-alarm) | Task existed at `hr_agent/tasks.py:742`, scheduled at settings:955 |
| 8 | Extend audit log coverage | ✅ | Added to 11 mutating endpoints |

## What changed by area

### 1 + 2 — Notification templates
- **Endpoints**: `update_hr_notification_template`, `delete_hr_notification_template`,
  `send_hr_notification_now` in `api/views/hr_agent.py`.
- **Design**: send-now shares template rendering with the scheduled path via
  `_SafeDict.__missing__` so missing placeholders format to visible tokens
  rather than raising `KeyError`. Slack/Teams channels hide the recipient
  input in the UI because they post to a company channel.

### 3 — Leave balance view + adjust
- **Endpoints**: `list_leave_balances(employee_id)`, `adjust_leave_balance(employee_id)`.
- **Design**: adjust supports both `set_*` (absolute) and `delta_*` (relative)
  operations on `accrued_days`, `used_days`, `carried_over_days`, with a
  non-negative floor. `reason` is required and lands in the audit log — an
  HR-admin adjusting someone's balance is exactly the sort of thing an
  auditor asks about later.

### 4 — Employee deactivate/reactivate
- **Endpoints**: `deactivate_employee(employee_id)`, `reactivate_employee(employee_id)`.
- **Design**: distinct from generic `update_employee` so the audit trail keys
  cleanly ("who ended so-and-so's employment on X?"). `previous_status` is
  stashed on deactivate; reactivate validates the target against
  `EMPLOYMENT_STATUS_CHOICES - {'offboarded'}`.

### 5 — Leave withdraw vs cancel
- **New status**: `withdrawn` on `LeaveRequest.STATUS_CHOICES`, migration
  `0014_leave_withdrawn_status`.
- **Semantic split**:
  - `cancelled` — pending → cancelled. Employee changed their mind before a
    decision. No balance change.
  - `withdrawn` — approved → withdrawn. Employee had approval and gave it
    back. Balance is **restored** (mirror of the approve-time deduction).
- **Guardrails**: owner or HR-admin only; withdrawing a past-end-date leave
  requires HR-admin because otherwise employees could double-dip. `reason`
  required. Uses `select_for_update()` + F() expressions to mirror the
  approve path's concurrency semantics.

### 6 — Close/reopen review cycle
- **Endpoints**: `close_review_cycle(cycle_id)`, `reopen_review_cycle(cycle_id)`.
- **Design**: close accepts `release_reviews=true` to flip all
  `visible_to_employee=True` in one shot — a common HR ask ("close the cycle
  and release everyone's rating at once"). Reopen does NOT re-hide
  already-released reviews (surprising employees who've seen their rating
  is worse than the paperwork gap).

### 7 — Meeting reminder Celery task
Audit false-alarm. `send_hr_meeting_reminders` exists at
`hr_agent/tasks.py:742` and is registered in `project_manager_ai/settings.py:955`
with a 300s interval. It handles 24h + 15m reminders with asymmetric windows,
timezone-aware, gated by `reminder_*_sent_at` fields. No changes needed.

### 8 — Audit log coverage
Added `_write_audit_log` calls to:
- `create_employee` — new-hire event
- `create_hr_notification_template` / `update_*` / `delete_*` — comms infra
- `create_department` / `update_department` / `delete_department` — org structure
- `create_holiday` / `update_holiday` (upsert) / `delete_holiday` — calendar
- `upsert_accrual_policy` / `delete_accrual_policy` — leave policy
- `create_review_cycle` / `delete_review_cycle` — perf infra
- `create_hr_meeting` / `update_hr_meeting` — meeting infra (cancel was
  already covered)
- `update_leave_request` — pre-decision edits
- `delete_hr_document` — document deletion (mark_outdated/unmark/reingest
  were already covered)

**Still uncovered** (deprioritised):
- Knowledge Q&A chats CRUD (low compliance value — chat history)
- HR workflow definition CRUD (execution approve/reject is audited)

## Files touched

**Backend**
- `hr_agent/models.py` — added `withdrawn` status
- `hr_agent/migrations/0014_leave_withdrawn_status.py` — new migration
- `api/views/hr_agent.py` — endpoints + audit log calls
- `api/urls.py` — new route registrations

**Frontend**
- `PaPerProjectFront/src/services/hrAgentService.js` — service helpers +
  default-export bundle
- `PaPerProjectFront/src/components/hr/HRNotificationsTab.jsx` — edit/delete
  wiring + send-now dialog
- `PaPerProjectFront/src/components/hr/HREmployeeDetailDrawer.jsx` — adjust
  balance dialog + deactivate/reactivate buttons
- `PaPerProjectFront/src/components/hr/HRDashboard.jsx` — close/reopen cycle
  buttons + handlers
- `PaPerProjectFront/src/components/hr/HRLeaveTab.jsx` — withdraw button on
  approved leaves + updated copy on cancel

## Verification

- `python manage.py check` → 0 issues
- URL routes verified via URLconf walk (namespace prefix breaks `reverse` in
  a raw shell but the patterns register correctly)
- New `LeaveRequest.STATUS_CHOICES` confirmed via ORM inspection
- All new view functions confirmed importable from `api.views.hr_agent`

## Pre-existing project state

- Migration graph has two conflicting leaf nodes each in `recruitment_agent`
  and `core` from earlier work by other contributors. Not from this sweep;
  documented here so a future `makemigrations --merge` isn't attributed to
  this branch.
- IDE hints for unused imports (`HRDocumentChunk`, `HRPublicThrottle`) and
  unused local variables (`_detected_fmt`, `_cur`) are pre-existing.

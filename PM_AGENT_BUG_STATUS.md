# Project Manager Agent — Bug Status Tracker

**Source:** `AI Employee Project manager testing.pdf`
**Tested by:** Noor &nbsp;·&nbsp; **Verified by:** Hamza &nbsp;·&nbsp; **Owner:** Abdullah
**Last updated:** 2026-06-23 (fifth batch — Channel/Template Edit UI, Delete Task, search bars on Projects/Users/All-Tasks, structured calendar conflicts)

## Legend
- [x] **Done** — verified fix is in the current code (file reference shown).
- [ ] **Not done** — bug still present in current code.
- [~] **Partially done** — part of the bug is fixed; remaining work noted below.
- ❓ **Needs clarification** — I could not determine status confidently; question for you listed under the item.

---

## 1. Project & Task creation form

- [x] **Past-date validation on project creation form**
  Both date inputs now have `min={todayIso()}`, the submit handler rejects past start_date / deadline AND deadline < start_date with a clear toast.
  Evidence: [`ManualProjectCreation.jsx:69-105, 280, 293`](PaPerProjectFront/src/components/pm-agent/ManualProjectCreation.jsx#L69-L105).

- [x] **Past-date validation on task creation form**
  Deadline input has `min={nowDatetimeLocal()}`; submit handler rejects past deadlines.
  Evidence: [`ManualTaskCreation.jsx:88-128, 264`](PaPerProjectFront/src/components/pm-agent/ManualTaskCreation.jsx#L88-L128).

- [x] **Calendar / clock picker on project & task date inputs**
  New shared `DatePicker` + `DateTimePicker` components built on shadcn `Calendar` + `Popover` (react-day-picker under the hood, both already installed). Drop-in replacements for the native inputs — value format stays `YYYY-MM-DD` / `YYYY-MM-DDTHH:mm`, so submit-time validation didn't need to change. DateTime picker uses calendar for the date + native `<input type="time">` for HH:mm.
  Evidence: [`components/common/DatePicker.jsx`](PaPerProjectFront/src/components/common/DatePicker.jsx), [`ManualProjectCreation.jsx:284-303`](PaPerProjectFront/src/components/pm-agent/ManualProjectCreation.jsx#L284-L303), [`ManualTaskCreation.jsx:266-275`](PaPerProjectFront/src/components/pm-agent/ManualTaskCreation.jsx#L266-L275).

---

## 2. Timeline & Gantt Agent

- [x] **Project Timeline Visualization now uses project's actual start date**
  Backend explicitly fetches `project.start_date` and feeds it into the timeline calc instead of `now()`.
  Evidence: [`project_manager_agent/ai_agents/timeline_gantt_agent.py:96-97`](project_manager_agent/ai_agents/timeline_gantt_agent.py#L96-L97).

- [x] **`Calculate Duration` action — fixed `'list' object has no attribute 'get'` error**
  `calculate_duration_estimate()` now safely uses `.get()` on task dicts.
  Evidence: [`project_manager_agent/ai_agents/timeline_gantt_agent.py:1394-1397`](project_manager_agent/ai_agents/timeline_gantt_agent.py#L1394-L1397).

- [x] **`Generate Gantt Chart` now uses project's actual dates**
  Same fix path as the Timeline Visualization above.
  Evidence: [`project_manager_agent/ai_agents/timeline_gantt_agent.py:96-97`](project_manager_agent/ai_agents/timeline_gantt_agent.py#L96-L97).

---

## 3. User management

- [x] **Edit User modal — username now persists (both email and username save)**
  Backend now reads `username` from the payload, rejects empty + duplicate values, and persists it.
  Evidence: [`api/views/company_users.py:385-398`](api/views/company_users.py#L385-L398).

- [x] **Deactivated users no longer appear in the task "Assign To" dropdown**
  All three branches of `_build_available_users` now filter `user__is_active=True` (UserProfile path, TeamMember fallback, and global fallback).
  Evidence: [`api/views/pm_agent.py:318-369`](api/views/pm_agent.py#L318-L369).

---

## 4. Project Pilot chat

- [x] **PDF attachment + "convert it in project" prompt now works**
  **Root cause:** the backend was using the *raw PDF text* as the agent's `question`, dropping the user's typed instruction entirely. So the agent had no idea what to do with the dumped text and replied *"could you clarify what you'd like to convert?"*.
  **Fix:** the frontend now sends a `prompt` field alongside the file, and the backend composes the question as `<user prompt>\n\n--- Attached document: <name> ---\n<extracted text>\n--- end of document ---`. If the user uploads without typing anything, the backend wraps the file in a sensible default ("Read its contents and ask what they'd like to do with it…").
  Evidence: [`ProjectPilotAgent.jsx:171-220`](PaPerProjectFront/src/components/pm-agent/ProjectPilotAgent.jsx#L171-L220), [`pmAgentService.js:projectPilotFromFile`](PaPerProjectFront/src/services/pmAgentService.js#L196), [`api/views/pm_agent.py:project_pilot_from_file`](api/views/pm_agent.py#L3354-L3380).

---

## 5. Meeting Scheduler

- [x] **Meeting with `fatima noor` no longer creates two participants**
  **Root cause:** the NLP `_find_all_users_in_message` matched user *A* `"fatima noor"` via full-name AND user *B* `"noor fatima"` via the partial token `"fatima"`. Both got added to `invitee_users`.
  **Fix:** two-pass matcher in [`meeting_scheduler_agent.py:_find_all_users_in_message`](project_manager_agent/ai_agents/meeting_scheduler_agent.py#L128-L195). Pass 1 collects unambiguous full-name / email / email-prefix matches and "consumes" the matched name tokens. Pass 2 only allows partial token matches on tokens *not already claimed* by a pass-1 match — so when "fatima noor" is matched as a full name, "noor fatima" can no longer trigger a partial match because both its tokens are already consumed.
  Belt-and-braces: the participant-create loop now dedupes by `user.id` and uses `get_or_create` so even if a caller passes the same user twice it doesn't blow up on the unique constraint.
  Evidence: agent fix above; backend defence at [`api/views/pm_agent.py:4967-4977`](api/views/pm_agent.py#L4967-L4977).

- [x] **Meeting accept/reject available to invitees — both in-dashboard and via email link**
  **In-dashboard:** the project-user dashboard ([`UserDashboardPage.jsx`](PaPerProjectFront/src/pages/UserDashboardPage.jsx) → "Meetings" tab at line 1184) already had a full Accept / Reject / Suggest-Time UI calling `/api/meetings/{id}/respond` (handler [`notification.meeting_respond`](api/views/notification.py#L108)). The audit had missed this; no new frontend code was needed.
  **Email link:** new signed-token public endpoint [`meeting_email_action`](api/views/notification.py#L344) at `GET /api/meetings/email-action/<action>/<token>/`. Uses Django's `TimestampSigner` with 14-day TTL; payload is `<meeting_id>:<user_id>`. The invitation email body now contains green "✓ Accept" and red "✕ Reject" buttons that open this URL — no login required, the signed token IS the auth. Endpoint is idempotent (clicking Accept twice shows the same confirmation page instead of creating a duplicate response).
  Evidence: token helpers + endpoint at [`api/views/notification.py:336-525`](api/views/notification.py#L336-L525), URL at [`api/urls.py:152-155`](api/urls.py#L152-L155), email body extended at [`api/views/pm_agent.py:5026-5060`](api/views/pm_agent.py#L5026-L5060).

- [x] **Withdraw now notifies the other participant by email + in-app notification**
  Withdraw handler creates a `Notification` row and calls `_send_meeting_email()`.
  Evidence: [`api/views/pm_agent.py:5023-5034`](api/views/pm_agent.py#L5023-L5034).

- [x] **"Accept Proposed Time" no longer shown to the user who proposed it**
  Computes the most recent `counter_proposed` response and shows the Accept button only when it was the *invitee* who proposed. When the organizer counter-proposed, a status hint *"Waiting for {invitee} to accept your proposed time"* is shown instead.
  Evidence: [`MeetingScheduler.jsx:582-594, 677-700`](PaPerProjectFront/src/components/pm-agent/MeetingScheduler.jsx#L582-L700).

- [x] **Multi-participant meetings now email every invitee**
  Email loop iterates over all `invitee_users` and calls `_send_meeting_email()` for each.
  Evidence: [`api/views/pm_agent.py:4843-4873`](api/views/pm_agent.py#L4843-L4873) (esp. L4856).

---

## 6. Daily Standup

- ❓ **Standup report shown twice**
  I could not find a duplicate render block in [`PaPerProjectFront/src/components/pm-agent/DailyStandupAgent.jsx:117-189`](PaPerProjectFront/src/components/pm-agent/DailyStandupAgent.jsx#L117-L189) — the report renders once. The screenshot in the PDF shows two "Daily Standup Report — 2026-08-04" rows.
  **Question for you:**
  > Is the duplicate now gone after a refresh, or is the backend returning two report rows for the same date? If the latter, this is a backend issue (a duplicate row in the standup-report table) and I need to look at the standup-create endpoint for missing dedupe.

---

## 7. Time Estimation

- [x] **`Estimate Time` now renders the result + uses project start as the timeline anchor**
  **Root cause #15 (empty UI):** field-name mismatch — the agent returned `estimates` / `total_estimated_hours` / `total_estimated_days`, but `TimeEstimationView.jsx` reads `task_estimates` / `total_hours` / `total_days`. So the LLM produced data and the UI quietly showed nothing.
  **Root cause #16 (current date):** the endpoint only passed `project.name` + `project.status` to the agent — no `start_date`, no `deadline`. Each task's timeline had nothing to anchor to.
  **Fix:** [`time_estimation`](api/views/pm_agent.py#L4413) now passes `project.start_date` / `project.deadline` to the agent AND post-processes the result to populate the UI keys (`task_estimates`, `total_hours`, `total_days`) plus a per-task `estimated_start_date` / `estimated_end_date` computed by cumulating `estimated_days` from the real project start (or today if start is null). The agent prompt also includes the project window so reasoning is calibrated to the real timeline (added in [`time_estimation_agent.py`](project_manager_agent/ai_agents/time_estimation_agent.py)).

---

## 8. Calendar / Schedule planner

- [x] **Scheduling conflicts now show structured reason + affected tasks**
  **Root cause:** the agent ([`calendar_planner_agent.py:detect_conflicts`](project_manager_agent/ai_agents/calendar_planner_agent.py#L130)) emitted **plain strings** like *"X has 3 active tasks - potential overload"* with no `criterion`, no `task_ids`, no `severity`. The UI rendered them as opaque blobs and the user couldn't tell why a conflict was flagged or which tasks were involved.
  **Fix:**
  - Agent now emits each conflict as a structured object: `{ type, severity, description, criterion, task_ids, task_titles, metadata }`.
  - Added a **same-deadline** detector (the specific case from the PDF — "Implement Backend API and Implement Avatar Classification Service have the same deadline" — now produces a conflict with the shared date + both task titles).
  - Recommendations follow the same structured pattern with `suggested_action`.
  - Frontend [`CalendarScheduleView.jsx`](PaPerProjectFront/src/components/pm-agent/CalendarScheduleView.jsx) renders the criterion, task-title chips, and a severity-coloured border. Legacy plain-string conflicts still render correctly (backwards compatible).

---

## 9. Smart Notifications & Notification Settings

- [x] **`Scan for Issues` now finds issues across the company's projects**
  **Root cause:** [`scan_notifications`](api/views/pm_agent.py#L4225) filtered projects by `created_by_company_user=company_user` — so a colleague who didn't *personally* create the projects saw "0 projects scanned" even though their company had many. The agent's scan logic (overdue / blocked / approaching / unassigned-high-priority) was fine all along.
  **Fix:** filter is now `company=company_user.company` so the scan covers every project the user's company owns, gated by company so we never expose another tenant's projects.

- [x] **Notification Templates & Channels now refresh after create**
  Both create handlers call `refreshChannels()` / `refreshTemplates()` after the POST succeeds, which re-fetches from the server.
  Evidence: [`PaPerProjectFront/src/components/pm-agent/NotificationSettings.jsx:75-91`](PaPerProjectFront/src/components/pm-agent/NotificationSettings.jsx#L75-L91) (channels) and L126-142 (templates).

---

## 10. Task Prioritization Agent

- [x] **`Suggest Delegation` no longer silently falls back to round-robin**
  **Root cause:** the LLM call had `max_tokens=1200`, which is far too small for the requested response shape (each suggestion needs a 6-8 sentence reasoning block + workload_analysis + reassignment_opportunities + summary). The response was being truncated mid-JSON, `json.loads` raised silently, and the `except Exception` block fired the round-robin "Fallback delegation used" with no log of why.
  **Fix:**
  - Token budget bumped to `max_tokens=4096`.
  - New shared `_extract_json_object` helper handles common LLM quirks (fenced blocks, trailing prose, dangling braces from truncation) and is used in all three big prioritization LLM calls.
  - Inputs capped to 12 candidate tasks × 15 team members so prompt + response always fit.
  - Fallback path now logs the actual exception + a 200-char prefix of the raw response so future incidents are debuggable instead of silent.
  Evidence: [`project_manager_agent/ai_agents/task_prioritization_agent.py:_extract_json_object`](project_manager_agent/ai_agents/task_prioritization_agent.py) and the rewritten `suggest_delegation` body.

- [x] **`Generate Subtasks` — long but honest progress UI**
  **Investigation outcome:** the endpoint *is* working; it takes 60-90 s because it really does generate 70-90 subtasks (per user's confirmation). The UI was showing a single tiny "Generating…" spinner with no elapsed time, so users assumed it had hung.
  **Fix:** new shared [`ProgressLoader`](PaPerProjectFront/src/components/common/ProgressLoader.jsx) component — indeterminate animated bar + real elapsed-time counter + phased status hints that flip based on elapsed-time thresholds + a typical-duration line + an "overdue" hint if elapsed > 1.5× typical. Wired into all 4 actions in `TaskPrioritizationAgent.jsx` with per-action phase presets:
  - *Prioritize & Order Tasks* — typical ~75s, 5 phases (priority scoring → ordering → strategy summary)
  - *Find Bottlenecks* — typical ~30s, 3 phases
  - *Suggest Delegation* — typical ~35s, 3 phases
  - *Generate Subtasks* — typical ~70s, 4 phases (calls out "Generating 70+ subtasks — this is the slow part" so users know it's intentional)
  No fake percentages — single HTTP request has no real per-token progress; we don't pretend it does.

- [x] **`Prioritize & Order Tasks` no longer returns empty Analysis Results**
  **Root cause:** same `max_tokens=1200` truncation pattern as Suggest Delegation — `suggest_task_order` was being cut off mid-JSON, the partial parse returned no `execution_plan`, the merged result had no `tasks` to render. `identify_bottlenecks` had the identical bug.
  **Fix:** bumped `max_tokens` to 4096 in `suggest_task_order` and `identify_bottlenecks`, both now use `_extract_json_object` for permissive parsing, both log a snippet of the raw response when extraction fails so we can see the cause in server logs.

---

## 11. Team Performance Dashboard

- [x] **Team-members graph now has data to plot**
  **Root cause:** `_pm_build_analytics_data()` — the function that builds the data the chart-generation LLM sees — exposed only project/task counts. The LLM literally had no `tasks_by_assignee` or `team_members` field to chart, so any prompt like *"team members of this project"* or *"tasks per person"* came back empty. Also: same per-creator scope bug as #18 — colleagues' projects were invisible.
  **Fix:**
  1. Switched the project / task filter from `created_by_company_user=user` to `company=user.company` so colleagues' projects count.
  2. Added two new chart-ready dicts: `tasks_by_assignee_obj` (total tasks per assignee, "Unassigned" bucketed explicitly) and `assignees_active_obj` (excluding done/completed for an "active workload" chart).
  3. Surfaced both in the data summary passed to the LLM, and extended the system prompt's mapping rules so the LLM picks the right dict for prompts containing "team members", "tasks by assignee", "workload by member", or "active workload".
  Evidence: [`api/views/pm_agent.py:_pm_build_analytics_data`](api/views/pm_agent.py#L2220) and chart prompt at [`_pm_generate_chart_from_prompt`](api/views/pm_agent.py#L2292).

---

## 12. General UI / UX

- [x] **Custom `ConfirmDialog` replaces `window.confirm()` across PM / user-management surfaces**
  All 4 sites (delete channel, delete template, deactivate user, reactivate user) now open the shared [`components/common/ConfirmDialog.jsx`](PaPerProjectFront/src/components/common/ConfirmDialog.jsx) — the component was lifted from `operations/` to `common/` (a re-export shim at the old path keeps existing imports working).
  Evidence: [`NotificationSettings.jsx:102-122, 153-173`](PaPerProjectFront/src/components/pm-agent/NotificationSettings.jsx#L102-L173), [`CompanyDashboardPage.jsx:783-840`](PaPerProjectFront/src/pages/CompanyDashboardPage.jsx#L783-L840).

- [x] **Delete project** — backend endpoint + UI button + confirm dialog
  New `DELETE /api/project-manager/projects/{id}/delete` endpoint scoped to the company (404 for foreign companies). Frontend: red Trash button next to Edit on every project card in the Projects tab, gated by `ConfirmDialog`.
  Evidence: backend [`api/views/pm_agent.py: delete_project_manual`](api/views/pm_agent.py), URL [`api/urls.py:226`](api/urls.py#L226), service [`pmAgentService.deleteProjectManual`](PaPerProjectFront/src/services/pmAgentService.js), button [`CompanyDashboardPage.jsx:1123-1149`](PaPerProjectFront/src/pages/CompanyDashboardPage.jsx#L1123-L1149).

- [x] **Task update no longer fails with "Failed to update task"**
  **Root cause:** the endpoint had TWO too-narrow `created_by_company_user=user` filters:
  - The task lookup 404'd whenever the task's project was created by a *colleague* in the same company (same scope bug pattern as #18 and #27).
  - The assignee validation rejected `assignee_id`s whose `UserProfile.created_by_company_user` wasn't the *current* CompanyUser — even though the Assign-To dropdown was already showing those users. The dropdown showed them via `get_company_users_for_assignment`, which had the same per-creator scope, so on most installs the dropdown also showed too few users.
  Additionally, an unparseable date string was being assigned raw to `task.due_date` and bubbling into a generic 500 with the unhelpful "Failed to update task" toast.
  **Fix in [`api/views/company_projects_tasks.py:update_company_task`](api/views/company_projects_tasks.py#L102):**
  1. Task lookup now scoped by `project__company=user.company`.
  2. Assignee validation now scoped by `UserProfile.created_by_company_user__company=user.company`, AND requires the user to be `is_active=True` (consistent with #27).
  3. `due_date` is now explicitly parsed via `parse_datetime` / `parse_date` — an unparseable string returns a clear 400 *"Invalid due date format. Send an ISO 8601 datetime …"* instead of a generic 500.
  4. The Assign-To dropdown source `get_company_users_for_assignment` was widened the same way, so colleagues' users appear and are valid targets.

- [x] **Search bars added on Projects, Users, and All-Tasks tabs**
  Each tab now has a styled `<Input>` with a search icon. Filtering is client-side over the current page (status/user/project dropdowns on All-Tasks already narrow server-side):
  - **Projects** — searches project name + description AND drills into each project's task titles, so typing a task name surfaces the parent project. Empty-state shows a clear *"No projects or tasks match …"* message.
  - **Users** — searches full name, username, email, role.
  - **All Tasks** — searches title, description, project name (works alongside the existing status/user/project dropdowns).
  Evidence: [`CompanyDashboardPage.jsx:1184+`](PaPerProjectFront/src/pages/CompanyDashboardPage.jsx#L1184), [`:1572+`](PaPerProjectFront/src/pages/CompanyDashboardPage.jsx#L1572), [`:1805+`](PaPerProjectFront/src/pages/CompanyDashboardPage.jsx#L1805).

- [x] **Edit UI for Notification Channels & Templates** *(feature gap closed)*
  Backend already supported `PUT`/`PATCH` on both via `pm_notification_channel_detail` / `pm_notification_template_detail`, but the frontend never wired them up — users could create / toggle-active / test / delete but not edit, so they had to recreate to change a webhook URL or template body. Added inline edit-in-place: a pencil icon on each row flips that row into the same form layout as Create, with Save / Cancel buttons. Save calls the existing `updateNotificationChannel` / `updateNotificationTemplate` services.
  Evidence: [`NotificationSettings.jsx`](PaPerProjectFront/src/components/pm-agent/NotificationSettings.jsx) — new `editingChannelId` / `editingTemplateId` state, `startEditChannel` / `startEditTemplate` / `saveEditedChannel` / `saveEditedTemplate` handlers, plus inline form renderers that mirror the Create form layout.

- [x] **Delete task** — backend endpoint + UI button + confirm dialog *(feature gap closed)*
  Parallel to the delete-project surface I added earlier. New `DELETE /api/company/tasks/{id}/delete` endpoint at [`company_projects_tasks.py:delete_company_task`](api/views/company_projects_tasks.py), scoped by `project__company=user.company` (same security boundary as `update_company_task`). Subtasks cascade via the FK. Service helper `companyProjectsTasksService.deleteTask` calls it. Frontend: red Trash button next to Edit on every task — both in the expanded project card AND in the All-Tasks table — gated by `ConfirmDialog`.
  Evidence: backend [`api/views/company_projects_tasks.py:delete_company_task`](api/views/company_projects_tasks.py), URL [`api/urls.py:209`](api/urls.py#L209), button at [`CompanyDashboardPage.jsx:1281-1294`](PaPerProjectFront/src/pages/CompanyDashboardPage.jsx#L1281) and [`:1884-1904`](PaPerProjectFront/src/pages/CompanyDashboardPage.jsx#L1884).

---

## Summary

| Status | Count | Items |
|---|---|---|
| Done | **28** | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28 (plus new Channel/Template Edit + Delete Task features) |
| Not done | **1** | 14 (skipped by user request) |

### Landed this session (2026-06-23, fifth batch — feature gaps)

1. **#17** Structured calendar conflicts — agent now emits `{ type, severity, description, criterion, task_ids, task_titles, metadata }` objects instead of plain strings. Added same-deadline detection (the specific case the tester flagged). Recommendations follow the same structured pattern. Frontend renders criterion + task-title chips + severity-coloured border; legacy plain-string conflicts still render for backwards-compat.
2. **#28** Search bars — added on Projects tab (filters by project name/description + drills into task titles), Users tab (filters by name/username/email/role), and All-Tasks tab (filters by title/description/project name, complementing the existing status/user/project dropdowns).
3. **Notification Channels + Templates Edit UI** — backend already supported `PUT`/`PATCH`, but the frontend never wired it. Added pencil-icon-driven inline edit that flips each row into the same form layout as Create.
4. **Delete task** — new `DELETE /api/company/tasks/{id}/delete` endpoint scoped by company, parallel to delete-project. Trash button on every task (both project-card view and All-Tasks table), gated by `ConfirmDialog`.

Sanity-checked: 3 Python files parse, 4 JSX/JS files compile cleanly via esbuild, `python manage.py check` reports no issues.

---

## Open items

Only one item remains, deferred per your request:

- **#14** Daily Standup duplicate — code path is clean; if the symptom persists in the running app, it's most likely the backend writing two report rows for the same date. Needs a reproduction to fix.

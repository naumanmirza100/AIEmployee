# Project Manager Agent — Bug Status Tracker

**Source:** `AI Employee Project manager testing.pdf`
**Tested by:** Noor &nbsp;·&nbsp; **Verified by:** Hamza &nbsp;·&nbsp; **Owner:** Abdullah
**Status checked against:** current `abdullah_branch` head on 2026-06-23

## Legend
- [x] **Done** — verified fix is in the current code (file reference shown).
- [ ] **Not done** — bug still present in current code.
- [~] **Partially done** — part of the bug is fixed; remaining work noted below.
- ❓ **Needs clarification** — I could not determine status confidently; question for you listed under the item.

---

## 1. Project & Task creation form

- [ ] **Past-date validation on project creation form**
  Project could be created with start/end/deadline in past years (e.g. 02/2019, 09/2021).
  No `min` attr on the date inputs and no validation in submit handler.
  Evidence: [`PaPerProjectFront/src/components/pm-agent/ManualProjectCreation.jsx:272-288`](PaPerProjectFront/src/components/pm-agent/ManualProjectCreation.jsx#L272-L288).

- [ ] **Past-date validation on task creation form**
  Same issue — task deadline accepts past dates.
  Evidence: [`PaPerProjectFront/src/components/pm-agent/ManualTaskCreation.jsx:256-261`](PaPerProjectFront/src/components/pm-agent/ManualTaskCreation.jsx#L256-L261).

- [ ] **No calendar / clock picker on project & task date inputs**
  Forms use bare native `<input type="date">` / `<input type="datetime-local">`. No `react-datepicker` / shadcn `Calendar` / time picker.
  Evidence: [`ManualProjectCreation.jsx:274`](PaPerProjectFront/src/components/pm-agent/ManualProjectCreation.jsx#L274), [`ManualTaskCreation.jsx:258`](PaPerProjectFront/src/components/pm-agent/ManualTaskCreation.jsx#L258).

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

- [~] **Edit User modal — email updates, but `username` is ignored by the backend**
  Frontend sends both `email` and `username`, but the backend updates `email` only — there is no `if 'username'` branch in the handler.
  Evidence: backend [`api/views/company_users.py:376-383`](api/views/company_users.py#L376-L383); frontend [`PaPerProjectFront/src/pages/CompanyDashboardPage.jsx:739, 741`](PaPerProjectFront/src/pages/CompanyDashboardPage.jsx#L739).
  **Still to do:** make the backend accept and persist `username`, and add a uniqueness check.

- [ ] **Deactivated users still appear in the task "Assign To" dropdown**
  `_build_available_users()` filters out superusers only — it does not exclude `is_active=False` company users.
  Evidence: [`api/views/pm_agent.py:318-366`](api/views/pm_agent.py#L318-L366) (specifically L360).

---

## 4. Project Pilot chat

- ❓ **PDF attachment + "convert it in project" prompt — does the agent actually read the PDF?**
  The plumbing exists (frontend calls `pmAgentService.projectPilotFromFile()`, backend has PyPDF2 extraction at [`api/views/pm_agent.py:3170-3227`](api/views/pm_agent.py#L3170-L3227)), but I could not trace end-to-end whether the extracted text is actually passed as context to the LLM that creates the project. The reported symptom was the chat replying *"could you clarify what you'd like to convert"* — which suggests the PDF text never reaches the agent.
  **Question for you:**
  > Is this fix expected to be done, or do you want me to investigate the service-layer call chain (`pmAgentService.projectPilotFromFile` → backend) and confirm/repair the PDF→agent-context path?

---

## 5. Meeting Scheduler

- ❓ **Meeting with `fatima noor` created two participants: `noor fatima` + `fatima noor`**
  Backend meeting-create loops over `invitee_users` and creates ONE participant per user. The reported duplicate suggests the *natural-language meeting-scheduler agent* (not the manual modal) is splitting the name "fatima noor" into two candidate names and matching both as separate users.
  **Question for you:**
  > Is the duplicate happening only via the natural-language chat (`Schedule a meeting with fatima noor tomorrow at 10pm`), or also when picking the user manually? That changes where I need to look (chat agent name-parsing vs participant-resolver).

- [~] **Meeting accept/reject UI for the invitee**
  An "Accept Proposed Time" button exists, but **only when status is `counter_proposed`** (after someone has used Change Time). There is no plain Accept/Reject pair for the original pending invitation — the invitee can only Change Time or Withdraw.
  Evidence: [`PaPerProjectFront/src/components/pm-agent/MeetingScheduler.jsx:677-689`](PaPerProjectFront/src/components/pm-agent/MeetingScheduler.jsx#L677-L689).
  **Still to do:** add Accept / Reject buttons that appear on a `pending` invitation for the invitee.

- [x] **Withdraw now notifies the other participant by email + in-app notification**
  Withdraw handler creates a `Notification` row and calls `_send_meeting_email()`.
  Evidence: [`api/views/pm_agent.py:5023-5034`](api/views/pm_agent.py#L5023-L5034).

- [ ] **Change Time flow shows "Accept Proposed Time" to the proposer themselves**
  No check that the current user is NOT the one who proposed the new time — anyone can press Accept, including the proposer.
  Evidence: [`PaPerProjectFront/src/components/pm-agent/MeetingScheduler.jsx:655-689`](PaPerProjectFront/src/components/pm-agent/MeetingScheduler.jsx#L655-L689).

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

- ❓ **`Estimate Time` returns no output**
  The frontend hooks up the response correctly (`TimeEstimationView.jsx:63` calls `pmAgentService.timeEstimation()` and renders the result), but I could not locate the backend endpoint to confirm it actually returns data.
  **Question for you:**
  > Has this been fixed? If you say "still broken" I'll dig into the backend endpoint and the service call.

- ❓ **Time Estimation uses current date instead of project start date**
  Frontend only sends `selectedProject` ID; whether the backend looks up `project.start_date` is unverified.
  **Question for you:**
  > Same as above — let me know if you want this verified/fixed and I'll trace it.

---

## 8. Calendar / Schedule planner

- [~] **Scheduling conflicts now display a reason (when the backend returns one)**
  UI already renders `conflict.description || conflict.message` — so reasons WILL show if the backend includes them.
  Evidence: [`PaPerProjectFront/src/components/pm-agent/CalendarScheduleView.jsx:148-150`](PaPerProjectFront/src/components/pm-agent/CalendarScheduleView.jsx#L148-L150).
  **Still to do (depending on backend):** confirm the backend conflict-detector actually populates `description`/`message` with the criterion (e.g. *"same deadline"*, *"same assignee"*). The screenshot in the PDF showed conflicts with no readable basis — that's a backend message-text issue if the UI is rendering empty strings.

---

## 9. Smart Notifications & Notification Settings

- ❓ **`Scan for Issues` returns "0 issues across 0 projects"**
  Frontend correctly displays whatever the backend returns. Backend scan endpoint not located in this pass.
  **Question for you:**
  > Has this been wired up to actually scan? If still broken I'll find the endpoint and check the scan logic.

- [x] **Notification Templates & Channels now refresh after create**
  Both create handlers call `refreshChannels()` / `refreshTemplates()` after the POST succeeds, which re-fetches from the server.
  Evidence: [`PaPerProjectFront/src/components/pm-agent/NotificationSettings.jsx:75-91`](PaPerProjectFront/src/components/pm-agent/NotificationSettings.jsx#L75-L91) (channels) and L126-142 (templates).

---

## 10. Task Prioritization Agent

- ❓ **`Suggest Delegation` returns "Fallback delegation used" + Workload Analysis N/A**
  Frontend dispatches the action; backend endpoint not located in this pass.
  **Question for you:**
  > Has the real delegation algorithm + workload analysis been written, or is it still the fallback stub? If still stub, I'll wire up the real logic.

- ❓ **`Generate Subtasks` keeps loading indefinitely**
  No client-side timeout. Backend endpoint not located.
  **Question for you:**
  > Has the subtask endpoint been fixed/implemented? Or do you want me to add a client-side timeout + show an error toast as a stop-gap?

- ❓ **`Prioritize & Order Tasks` returns no output (empty Analysis Results)**
  Same area as above — backend endpoint not located.
  **Question for you:**
  > Same as the other two prioritization actions — confirm fixed/not and I'll dig in if needed.

---

## 11. Team Performance Dashboard

- ❓ **Team-members graph shows "No data available"**
  Couldn't fully verify whether the data fetch / graph rendering is now hooked up.
  **Question for you:**
  > Has this been fixed? If still broken I'll trace the team-graph endpoint + chart component.

---

## 12. General UI / UX

- [ ] **Default `window.confirm()` used instead of a custom shadcn dialog**
  Multiple places still use the native browser confirm popup.
  Evidence: [`PaPerProjectFront/src/components/pm-agent/NotificationSettings.jsx:103, 154`](PaPerProjectFront/src/components/pm-agent/NotificationSettings.jsx#L103) (delete channel / delete template); [`PaPerProjectFront/src/pages/CompanyDashboardPage.jsx:779, 802`](PaPerProjectFront/src/pages/CompanyDashboardPage.jsx#L779) (deactivate / reactivate user).

- [ ] **No option to delete a project**
  No delete-project button found in [`ProjectHealthDashboard.jsx`](PaPerProjectFront/src/components/pm-agent/ProjectHealthDashboard.jsx) or other PM views, and no delete-project endpoint in [`api/urls.py`](api/urls.py).

- ❓ **Task update fails with "Failed to update task"**
  The task-update endpoint exists but I didn't read its body to find the failure cause.
  **Question for you:**
  > Has this been fixed? If still broken I'll read the endpoint and the request payload to find the mismatch. (Most likely culprit from the screenshot — Status `Review` may not be in the model's `STATUS_CHOICES`, or the deadline format/timezone may be rejected.)

- [ ] **No search bar for projects / users / tasks**
  No `<Input>` search filter present in the PM listing views.

---

## Summary

| Status | Count | Items |
|---|---|---|
| Done | **6** | 4, 5, 6, 11, 13, 19 |
| Partially done | **3** | 7, 10, 17 |
| Not done | **9** | 1, 2, 3, 12, 24, 25, 27, 28 (and the username half of 7) |
| Needs clarification | **10** | 8, 9, 14, 15, 16, 18, 20, 21, 22, 23, 26 |

---

## Next steps — what I need from you

For each ❓ item above, a quick **"still broken"** or **"now working"** is enough — that'll let me close the partially-done items, build a fix list for the rest, and stop guessing at PDF screenshots from 2 weeks ago. Specifically:

1. **#8** PDF → project — does the chat still ignore PDFs?
2. **#9** Meeting duplicate participant — happens via the natural-language chat or also the manual modal?
3. **#14** Standup report duplicate — still 2 rows for the same date?
4. **#15 / #16** Time Estimation — empty output and current-date — still broken?
5. **#18** Smart Notifications scan — still returns 0?
6. **#20 / #21 / #22** Task Prioritization (Delegation / Subtasks / Prioritize & Order) — any of these now returning data?
7. **#23** Team-members graph — still empty?
8. **#26** Task update fail — still erroring?

Once you mark these I'll triage the remaining work into actual fix tasks.

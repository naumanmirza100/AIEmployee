# HR Agent — UX Redesign Notes

Deferred task. Companion to `PM_AGENT_UX_REDESIGN.md` and
`FRONTLINE_AGENT_UX_REDESIGN.md`. Third pass through the same exercise.

Context: audit of the HR (People Ops) agent frontend. `HRDashboard.jsx` is
**2,266 lines** with **10 top-level tabs** serving **three distinct personas**
(HR admin, people manager, individual employee) all mashed into the same
tab bar. Individual-employee self-service already exists at a separate route
(`/hr/me`) but is only linked by a small header button — architecturally
divorced from the dashboard.

Structurally lighter than Frontline (only 3 tabs have massive inline JSX:
Employees ~272, Documents ~394, Workflows ~385; the other 7 already
delegate to sub-component files). Restructure is mostly UX + grouping, not
a big extraction slog.

---

## The real problems

1. **No primary "here is my work" surface.** Overview is a 5-tile menu-of-menus
   that just switches tabs. Zero data, zero actionable signal. Same
   anti-pattern PM and Frontline both had before their restructures.

2. **Three personas sharing one tab bar.**
   - **HR admin / people ops** — owns Employees, Documents, Workflows,
     Notifications, Meetings, plus hidden Depts + Review Cycles managers
   - **People manager** — subset that uses My team, Leave (approve),
     Meetings, and views into Employees
   - **Individual employee** — mostly wants Q&A, Leave (submit), Org chart

   Every persona sees all 10 tabs. Same crowding problem Frontline had.

3. **Employee self-service is architecturally orphaned.** `/hr/me`
   (`HRMyProfilePage.jsx`, 493 lines) is a fully separate route for
   individual employees, linked only by a small "My profile" button in the
   dashboard header (line 891). Either it should be a proper tab, or the
   dashboard should be scoped to admins/managers and `/hr/me` becomes the
   default for employees.

4. **Two chat surfaces doing the same thing.** The `qa` tab
   (`HRKnowledgeQAAgent.jsx`, 717 lines) and the always-mounted
   `HRFloatingChat.jsx` (919 lines) both call
   `hrAgentService.askHRKnowledgeStream` with the same citations logic.
   Floating chat has more features (slash commands, `/find` employee
   search, drag/resize, Ctrl+K) so the tab is the weaker duplicate.
   Same decision as PM and Frontline.

5. **Three tabs share the Employee data model.** Employees (table),
   My team (manager rollup), Org chart (recursive tree) — all views over
   the same `Employee` collection with different lenses. Prime candidate
   for a single "People" tab with a lens toggle.

6. **Hidden admin objects behind employee-tab buttons.** "Manage depts"
   (line 1091) and "Review cycles" (line 1095) are first-class HR entities
   living only as dialogs on the Employees header. Review cycles has a
   full activate/close/reopen/delete flow buried in a modal. New users
   would never guess these exist.

7. **Massive inline JSX blocks.** Documents (~394 lines), Workflows
   (~385 lines), Employees (~272 lines) live inline in
   `HRDashboard.jsx`. The other 7 tabs already delegate to sub-component
   files. These 3 should follow.

8. **Modal chain sprawl.** Documents tab owns 5 modal dialogs (upload,
   result, versions, access log, delete). Workflows owns 4 (create/edit,
   delete, templates, run history — with inline approve/reject inside
   history). Some workflow flows even use `window.confirm` + `window.prompt`
   in sequence (lines 362-368, 383) — mixed with shadcn dialogs, prone
   to being blocked or missed.

9. **Workflow editing exposes raw JSON.** Line 1958-1961 renders the step
   list as a `<Textarea>` of stringified JSON. A new user cannot succeed
   without documentation — the description lists step type names but
   doesn't teach the shape. Templates mitigate this, but the primary
   "New workflow" CTA still leads to raw JSON.

10. **Overview Quick-Jump grid is stale-shaped.** 5 tiles only, all
    going to feature tabs — none surface actual work (approvals waiting,
    urgent leave requests, docs pending re-index).

---

## What to change (ranked by impact)

### 1. Pick a primary entry point per persona

Route-level split first:

- **Individual employee** → land on `/hr/me` (already exists, just needs
  to become the default for non-admin users)
- **HR admin / manager** → land on the HR dashboard's `people` tab
  (see #2 below — the merged Employees / My team / Org chart)

If we can't detect role reliably, default everyone to the dashboard's
new `people` tab. Employees who don't have manager or HR-admin permissions
can still ask the floating chat.

### 2. Collapse 10 tabs → 5

| New tab | Contains | Persona |
|---|---|---|
| **Overview** | Stat cards + a new "Today" panel (pending approvals, urgent leave, docs re-index queue) — replaces the useless 5-tile menu | HR admin |
| **People** | Employees + My team + Org chart as sub-tabs (all one data model); "Manage depts" and "Review cycles" surfaced as their own sub-tab or accordion | Admin + Manager |
| **Knowledge** | Documents + Knowledge Q&A as sub-tabs (same shape as Frontline's Knowledge tab); floating chat stays available for quick asks | All personas |
| **Operations** | Workflows + Leave + Notifications as sub-tabs — the "process-y" HR features that mostly serve admins | HR admin |
| **Meetings** | Kept as its own tab (it's a full chat + meetings list, structurally big enough) | All personas |

**Hide (not delete) outright:**
- `overview` (rebuilt as new content, but the value string can stay)
- `employees`, `my_team`, `org_chart` → live inside People sub-tabs
- `documents`, `qa` → live inside Knowledge sub-tabs
- `workflows`, `leave`, `notifications` → live inside Operations sub-tabs

**Kept as-is (per lesson from Frontline):**
- Meetings — its own top-level tab
- Q&A tab kept alive as a Knowledge sub-tab (floating chat is quick access,
  full tab is for deep sessions with chat history)

### 3. Unbury Departments and Review Cycles
Right now they're `outline` buttons inside the Employees header. Options:
- Add them as sub-tabs of **People** ([Employees | My team | Org chart | Depts | Review cycles])
- Or a **Settings** cluster for HR-admin only (Depts, Review cycles,
  Notification templates admin bits)

I'd recommend they become sub-tabs of People — they're department/employee-scoped
concerns, not global settings.

### 4. Fix the empty states that dead-end
Same pattern PM used. Prioritize:
- **Employees empty state** ("When new auth.Users are added under your
  company, they'll appear here automatically") — needs a **CTA to invite
  users**, not a passive statement.
- **My team empty state** for non-managers — dead-ends silently. Should
  redirect to a useful surface like Q&A or Overview.
- **Workflows empty state** — CTA should push toward **templates** first,
  not raw JSON.

### 5. Extract the 3 large inline tab blocks
Do this before the restructure or as part of it — otherwise every future
diff to Employees/Documents/Workflows will be miserable. Non-negotiable
groundwork:
- Inline Employees JSX → `HREmployeesTab.jsx`
- Inline Documents JSX → `HRDocumentsTab.jsx`
- Inline Workflows JSX → `HRWorkflowsTab.jsx`

Each extraction is mechanical and independently reviewable. Drops
`HRDashboard.jsx` from ~2,266 → ~800-900 lines.

### 6. Rework the Overview into a "Today" surface
Instead of 5 nav tiles, show:
- Stat cards (already there — useful)
- **Pending approvals** list (leave requests, workflow approvals awaiting sign-off)
- **Recently indexed / failed** documents (from processing_status)
- **Upcoming meetings this week** (from Meeting scheduler)
- Small **"Ask HR"** widget that opens the floating chat with a pre-filled
  prompt

Turns Overview from "menu of menus" into "here's what needs your attention
today." Same principle we applied to PM's landing.

### 7. Collapsible sidebar (mirrors PM + Frontline)
Once tab count is down to 5, apply the same sidebar treatment PM and
Frontline got: `hidden lg:flex`, collapsible, remembers state per browser,
tooltip on hover when collapsed, nested sub-tabs indented under parent
when expanded. Same `FrontlineSubTabs`-style shared primitives — we can
extract to `shared/AgentSubTabs.jsx` at that point.

---

## Trade-offs to plan around

- **Persona detection is fragile.** The dashboard can't reliably tell
  admin from manager from employee without a permission call. If we
  route employees to `/hr/me` by default but the check fails, we'd
  land admins on the wrong page. Mitigate: default to dashboard's
  new People tab for everyone, add a "You're viewing as HR admin —
  switch to My profile" link at top.
- **Killing the QA tab** — same trade-off as Frontline. User previously
  chose to keep the QA tab alive (as a sub-tab of Knowledge). Following
  the same call here.
- **Employees + My team + Org chart merge** — some users might expect
  "My team" to always be one click away. In the new People tab it's a
  sub-tab, so it's two clicks (People → My team). Acceptable trade for
  removing 2 tabs from the primary bar.
- **Departments and Review cycles as People sub-tabs** feels a bit
  heterogeneous — Depts is a data object, Review cycles is a process.
  Alternative: keep them as dialogs but promote them to be reachable
  from the People sub-tab bar as buttons alongside the sub-tab triggers.
- **Meetings tab retention** — it's an 885-line chat with its own
  Meetings sub-tab. Could arguably fold into Ops. Keeping it separate
  because it's persona-neutral (employees, managers, and admins all
  use it) whereas Ops is mostly admin.
- **Overview "Today" panel** — real work, not just a shell. Needs
  backend support for the "pending approvals" list if that doesn't
  already exist. Verify before promising it in the UI.

---

## Rollout order (when we come back to this)

Mirrors PM and Frontline exactly — small chunks, each independently
mergeable and reviewable.

1. **Groundwork — extract 3 inline tab blocks** into their own files
   (`HREmployeesTab`, `HRDocumentsTab`, `HRWorkflowsTab`). Pure code
   motion, no behavior change. Shrinks the file from ~2266 → ~1200 lines.
2. **Unbury Departments + Review Cycles** — surface them as top-level
   buttons/tabs, not hidden dialog behind Employees header.
3. **Fix empty states** for Employees / My team / Workflows.
4. **Chunk A — Foundation.** Add `hidden: true` flag to `HR_TAB_ITEMS`,
   filter visible tabs, keep TabsContent for hidden tabs (URL still works),
   scaffold 5 new visible tabs (Overview + People + Knowledge + Operations
   + Meetings) as placeholders that click through to legacy tabs.
5. **Chunk B — Knowledge.** Nested sub-tabs [Documents | Q&A]. Reuse
   the extracted HRDocumentsTab + existing HRKnowledgeQAAgent. Same
   pattern as Frontline's Knowledge.
6. **Chunk C — People.** Nested sub-tabs [Employees | My team | Org chart
   | Depts | Review cycles]. Extracted Employees + existing HRManagerTeamTab
   + HROrgChartTab. Depts and Review cycles extracted from their dialog
   into full sub-tab panels.
7. **Chunk D — Operations.** Nested sub-tabs [Workflows | Leave |
   Notifications]. Extracted Workflows + existing HRLeaveTab + HRNotificationsTab.
8. **Chunk E — Overview rework.** Replace the 5 tiles with the "Today"
   panel (pending approvals + recent docs + upcoming meetings).
9. **Chunk F — Sidebar.** Collapsible left rail with nested sub-tabs
   + URL sub-tab state, mirroring PM/Frontline. Extract shared primitives
   to `shared/AgentSubTabs.jsx` if we haven't already.
10. **Chunk G — Employee self-service routing.** Detect role, default
    non-admins to `/hr/me`. Add "Switch to admin view" link.

Each step is independently mergeable and reviewable.

---

## Files that will be touched (rough scope)

**Modified:**
- `src/components/hr/HRDashboard.jsx` — biggest change. After Step 1
  groundwork it shrinks by ~1000 lines just from extraction. Steps 4–9
  swap the layout.
- `src/components/hr/HRFloatingChat.jsx` — may need discoverability
  improvements (permanent header CTA?) since it becomes the primary
  quick-access surface.
- `src/components/hr/hrTutorialSteps.js` — steps for hidden tabs need
  filtering (same pattern PM/Frontline used), Quick-Jump copy updates.

**New:**
- `src/components/hr/HREmployeesTab.jsx` (extraction)
- `src/components/hr/HRDocumentsTab.jsx` (extraction)
- `src/components/hr/HRWorkflowsTab.jsx` (extraction)
- `src/components/hr/PeopleView.jsx` (Employees + My team + Org chart + Depts + Review cycles sub-tabs)
- `src/components/hr/KnowledgeView.jsx` (Documents + Q&A sub-tabs — could be shared with Frontline's if abstracted)
- `src/components/hr/OperationsView.jsx` (Workflows + Leave + Notifications sub-tabs)
- `src/components/hr/HRTodayPanel.jsx` (new Overview content — pending approvals + recent docs + upcoming meetings)
- `src/components/hr/HRSidebar.jsx` (mirrors PMSidebar / FrontlineSidebar)
- `src/components/hr/HRSubTabs.jsx` OR promote `frontline/FrontlineSubTabs.jsx` → `shared/AgentSubTabs.jsx`

**Backend:** no changes strictly required for the frontend restructure.
The Overview "Today" panel benefits from a dedicated `/hr/today` endpoint
that returns pending approvals + urgent items in one call, but the
frontend can compose from existing endpoints as a first pass.

---

## Deliberately out of scope

Things that came up in the audit but shouldn't derail the restructure:

- **Workflow JSON editor UX.** The step-editor Textarea of stringified
  JSON is a real UX problem — but redesigning it is a full feature project.
  Leave alone; templates cover 80% of cases.
- **HRFloatingChat unification with HR Q&A tab.** They diverge in chat
  history storage (localStorage vs. backend) — merging is a nontrivial
  data migration. Skip until users complain.
- **Employee detail drawer** — 1299 lines of its own. Works, don't touch.
- **Tour/hint infrastructure dedup.** Every tab has its own TabTourButton
  + InfoHint pair. Real refactor opportunity but not blocking.
- **`AgentTile` / `Spinner` / `EmptyState` promotion to shared.** These
  are at the bottom of `HRDashboard.jsx` (lines 2232-2263). Move to
  `shared/` if you find yourself needing them elsewhere; not urgent.

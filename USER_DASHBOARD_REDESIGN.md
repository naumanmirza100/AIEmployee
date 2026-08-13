# User (Employee) Dashboard — UX Redesign + Gaps + Feature Ideas

Companion to `PM_AGENT_UX_REDESIGN.md`, `FRONTLINE_AGENT_UX_REDESIGN.md`, and
`HR_AGENT_UX_REDESIGN.md`. Fourth (and biggest gap) pass through the app.

Context: audit of what an **individual employee** (a user added by a
company-user account) actually sees when they log in. Turns out this
audience has been an afterthought — only **two** user-facing pages exist
in the entire frontend, they're structurally inconsistent, and there are
significant onboarding + navigation gaps a real employee would hit on day 1.

---

## Current state (what an employee sees today)

Just **2 pages**:

1. **`/user/dashboard`** — `UserDashboardPage.jsx` (**2,226 lines**, entirely
   inline JSX). Default landing for any non-admin login. Has 3 tabs for
   plain users (Tasks / Projects / Meetings) plus 3 more tabs only shown
   if `user.role === 'project_manager'` (All Project Tasks / Create Project
   / Create Task) — so it's really two dashboards mashed together, half
   the code dead-for-non-PMs.

2. **`/hr/me`** — `HRMyProfilePage.jsx` (493 lines, single scrolled page,
   7 stacked cards). Only linkable from a small button inside
   `HRDashboard.jsx:947`. Not surfaced in the sidebar.

**No other agent has an employee-facing page.** Not Marketing, not AI SDR,
not Operations, not Reply Draft, not Exec Meeting, not Frontline, not
Recruitment. Every one of those is "company-user admin only."

---

## The real problems

1. **No unified employee shell.** `AgentSidebar` exists for company users
   (9 agents listed) but there is no `EmployeeSidebar` / `EmployeeLayout`.
   An employee has no persistent left-rail navigation, no "My Space" home.
   Every page an employee reaches uses either the raw `DashboardNavbar`
   or the company-user `AgentLayout`.

2. **`UserDashboardPage` serves 3 personas out of one file.** Plain worker
   (3 tabs), project_manager (6 tabs + 4 dialogs), fallback for everyone
   else. PM branch (~880 lines, lines 1332-2219) is a duplicate of what
   already exists at `/project-manager/dashboard`. 40% of the file is dead
   code for the average user.

3. **`/hr/me` is architecturally unreachable for most employees.**
   `AgentLayout.jsx:44-59` requires `localStorage.company_user`. Regular
   Django-token users get bounced to `/company/login` even though HR built
   the page specifically for them. Only employees with a company_user
   account can reach it — inconsistent with `/user/dashboard`'s target
   audience.

4. **Profile menu is broken for non-company users.**
   `DashboardNavbar.jsx:322` hard-codes the Profile link to
   `/company/profile`. A regular user clicking their avatar → Profile
   lands on a company-scoped page that likely errors or is empty. **This
   is a real bug**, not a design nit.

5. **No badges on time-sensitive tabs.** Meetings tab has zero indicator
   of pending invites — user who never clicks Meetings never knows they've
   been invited to anything. Notifications API is wired but the tabs
   themselves don't badge unread items.

6. **Onboarding is silent.** Login → empty Tasks list → "No tasks assigned
   yet." Zero welcome, zero tour, zero profile-setup nudge, zero "meet
   your team" panel, zero primary CTAs on empty states.

7. **Half the visible interactions are read-only silently.**
   - Subtasks display as a list of checkboxes but you can't tick them
     (`UserDashboardPage.jsx:1086-1104`)
   - Goals on `/hr/me` are read-only even though the docstring says
     employees should update progress themselves
   - Progress slider is disabled on blocked tasks with no tooltip
     explaining why (`UserDashboardPage.jsx:1061`)

8. **Meeting inboxes scattered across THREE places** with different data
   shapes: `/user/dashboard`'s Meetings tab, `/hr/dashboard?tab=meetings`,
   and `/exec-meeting/dashboard`. Employee has to guess which one to
   check for what.

9. **File is a 2,226-line inline-JSX monolith.** Every tab body, every
   dialog, every form is inline. No `UserTasksTab`, `UserMeetingsTab`,
   `PMBulkToolbar`, `PMDepsDialog` extractions. Same architectural smell
   we hit with FrontlineDashboard.jsx.

10. **The `showCompanyUserOptions={false}` prop passed to `DashboardNavbar`
    at `UserDashboardPage.jsx:918` is dead** — the navbar never reads it.
    Whole thing is derived from `localStorage.company_auth_token`. Misleading
    surface area.

11. **Dashboard title `"THE PROJECT_MANAGER DASHBOARD"`** (all caps, raw
    enum) reads badly. Cosmetic but grating.

---

## What to change (ranked by impact)

### 1. Split `UserDashboardPage` into two clean surfaces
- **`/user/dashboard`** — plain employee only. Tabs: Home / Tasks /
  Meetings. Optionally Projects (read-only).
- **PM branch removed entirely** — `project_manager` users get redirected
  to `/project-manager/dashboard` on login (they already have a full
  dashboard there). Kills ~880 lines of duplicated PM code.

Cuts file from 2,226 → ~800 lines. Makes each page's persona coherent.

### 2. Build a unified `EmployeeLayout` + `EmployeeSidebar`
Mirror what `AgentLayout` does for company users. New shell that renders:
- Header: brand, notifications bell, avatar → **/me/profile** (not
  /company/profile — fix the profile bug at the same time)
- Left sidebar (collapsible, same pattern as AgentSidebar) with:
  - **Home** — landing with today's summary tiles
  - **My Tasks**
  - **My Meetings**
  - **My Documents** (docs shared with me)
  - **My Goals** (if HR module enabled for the company)
  - **My Leave** (if HR module enabled)
  - **My Profile** (`/me/profile`)
  - **Notifications** (all-in-one inbox)

New file: `src/components/common/EmployeeLayout.jsx`
New file: `src/components/common/EmployeeSidebar.jsx`
New file: `src/utils/employeeNavItems.js`
New route group in `App.jsx` under `<EmployeeLayout />`.

### 3. Build a real "Home / Today" landing tab
Replace the empty-Tasks-first-thing-I-see with a summary landing:
- Stat tiles: "3 tasks due this week", "1 pending meeting invite",
  "2 goals in progress", "45% of month's tasks complete"
- **Pending action items** list (the highest-priority thing needing my
  attention today — meeting invite awaiting response, task with today's
  deadline, unread notification)
- **My schedule today** (small calendar strip)
- **Recent activity** feed (comments on my tasks, mentions, doc shares)
- Quick-add task button
- Optional "Ask HR" widget that opens the HR floating chat with a
  pre-filled prompt

This turns the dashboard from a to-do list into a "here's what needs
your attention today" surface — matches how PM Dashboard evolved (from
menu-of-menus to Pilot-as-landing).

### 4. Fix the notification bug + add tab badges
- Notifications tab in the sidebar gets an unread count badge
- Meetings tab in the sidebar gets a "N pending invites" badge
- Tasks tab in the sidebar gets an "N overdue" badge if any
- Overdue tasks get a red left-border in the task list

### 5. Add sub-task interactivity + task detail
- Subtasks become clickable checkboxes (currently display-only)
- Each task gets a detail drawer/dialog on click with:
  - Comments (add + reply)
  - Attachments (upload + preview)
  - Activity log (status changes, assignments, comments)
  - Related tasks / dependencies (visible to everyone, not just PMs)

### 6. Fix `/me/profile` (kill /company/profile hard-link for employees)
- New route `/me/profile` — employee-editable profile: avatar, phone,
  timezone, notification preferences, password change, connected accounts
  (Google Cal, Slack, Zoom, GitHub if relevant to their role).
- `DashboardNavbar.jsx:322` → route by userType.
- If HR module enabled, also embed the HR profile card (leave balances,
  goals, reviews) — becomes the natural evolution of `/hr/me` which we
  can then deprecate.

### 7. Unify the 3 meeting inboxes into one "My Meetings"
- Backend federates: user's calendar meetings + HR meetings + exec meetings
- Frontend renders as one chronological list with source badges
- One accept/reject/counter-propose flow, whatever backend the meeting
  came from

### 8. Extract the 4 dialog components from UserDashboardPage
Non-negotiable groundwork before doing #1:
- Inline Edit Project modal → `PMEditProjectDialog.jsx`
- Inline Edit Task modal → `PMEditTaskDialog.jsx`
- Inline Task Dependencies dialog → `PMTaskDepsDialog.jsx`
- Inline Recurring Task dialog → `PMRecurringTaskDialog.jsx`

Or just delete them all when we redirect PM users to
`/project-manager/dashboard`. Whichever.

### 9. First-run onboarding
Replicate the pattern from PM/Frontline/HR:
- Employee-scoped `Take the Tour` walking through Home / Tasks / Meetings /
  Profile
- "Complete your profile" nudge on first landing if avatar/phone/timezone
  are empty
- "Your manager set 2 goals for you — review them" nudge if unread goals
- Empty-state CTAs on every tab (currently zero — see problem #6)

### 10. Employee tour + hint infrastructure
Add `userTutorialSteps.js` matching the shape of `pmTutorialSteps.js` /
`hrTutorialSteps.js` / `frontlineTutorialSteps.js`. New tab keys, new
hints. Consumed by the same `FrontlineTutorial` component the other
dashboards use.

---

## New features that don't exist anywhere yet

### Big new features (worth their own project)
- **Global command-K** for employees — jump to any of my tasks / meetings /
  docs / goals via fuzzy search. Same pattern as the existing floating
  Quick Chat but for navigation.
- **Time tracking** — start/stop timer on a task, automatic timesheet
  per day/week, exportable. Currently zero surface for this.
- **Employee time-off calendar** — see when teammates are on leave
  (from HR data), request my own time off in one click, see approval
  status. Cross-cutting between HR + Calendar.
- **Personal task inbox** — one place where everything that mentions me
  or assigns me something surfaces: tasks (PM), meeting invites (any),
  ticket assignments (Frontline handoffs), leave approvals (HR).
- **AI "what should I work on now"** — floating chat mode that reads
  my open tasks + due dates + priorities and recommends the next thing.
- **My-tickets view for Frontline agents** — currently Frontline handoffs
  are only reachable via the full Frontline company dashboard. Employees
  assigned tickets can't see their own queue without admin permissions.

### Medium features
- **Goals & OKRs for everyone** (not just HR-tracked employees) — current
  goals only exist inside HR module.
- **1:1 meeting notes** — schedule + take notes + track action items on
  recurring 1:1s with my manager. Exec-Meeting already extracts action
  items; wire that into employee view.
- **Payslips / documents-shared-with-me** area — right now `/hr/me`
  shows docs but only in a small card. Deserves a proper section.
- **Employee handbook Q&A widget** — the HR floating chat already answers
  policy questions from indexed docs. Surface it prominently on the
  employee landing instead of hiding it in HR's chrome.
- **Reply Draft integration** — currently a company-user tool. An employee
  handling their own email replies would benefit from AI-drafted responses
  without needing full Reply Draft dashboard access.
- **Learning & development section** — track completed trainings, view
  assigned learning paths. No such surface today.
- **Peer recognition / kudos** — send/receive shout-outs across the org.
  Would tie into HR performance reviews.
- **Emergency contact + banking info self-service** — currently only
  editable by HR admins.

### Small features / polish
- **Notification preferences page** — mute channels, digest cadence,
  quiet hours
- **Profile photo upload**
- **Language / timezone preference** with the whole app respecting it
- **Dark mode toggle** (matches theme already but no per-user override)
- **Keyboard shortcuts** for common actions (mark task done, snooze, etc.)

---

## Loopholes / bugs found during audit

1. **`/company/profile` link for non-company users** — hard-coded in
   `DashboardNavbar.jsx:322`, breaks for regular Django users. **Real
   bug.**
2. **`showCompanyUserOptions={false}` dead prop** on
   `UserDashboardPage.jsx:918` — DashboardNavbar doesn't read it.
   Misleading. Delete.
3. **`AgentLayout` bounces regular users from `/hr/me`** — HR built the
   self-service page but Layout locks non-company_user accounts out.
   Users the HR module was designed for can't reach it. Real
   architectural inconsistency.
4. **`ProtectedRoute.jsx:14` accepts both `company_user` and Django token**
   but `UserDashboardPage.jsx:69` checks strict `role === 'project_manager'`
   — doesn't handle `company_user` accounts, so a company_user who is
   also a PM won't see PM tabs.
5. **Progress slider disabled on blocked tasks silently** — no tooltip,
   no visual explanation. Users get stuck.
6. **Recurring task badges + dependency badges are PM-only** —
   `UserDashboardPage.jsx:1535-1546`. Plain employees see "blocked by X"
   in a badge but can't click to see what's blocking them. Should be
   visible to all task owners.
7. **PM's Edit Project dialog** at `UserDashboardPage.jsx:1803-1944`
   duplicates the one on `ProjectManagerDashboardPage.jsx` — two sources
   of truth, no shared component. Divergence risk.
8. **Dashboard title formatting**: `"THE ${role.toUpperCase()} DASHBOARD"`
   at line 902. Renders "THE COMPANY USER DASHBOARD" or "THE PROJECT_MANAGER
   DASHBOARD" — all caps, raw enum, jarring.
9. **Meeting Reject/Suggest Time coupled under one button** at
   `1317-1320` — two disparate actions collapsed into one label.
10. **The word "PROJECT_MANAGER" in the URL query** appears in
    `UserDashboardPage.jsx:1332-1794` if you inspect network requests
    — leaks internal role naming into user-facing surfaces.

---

## Trade-offs to plan around

- **`/hr/me` deprecation vs. preservation** — `/hr/me` has 493 lines of
  real employee-facing content (leave balances, reviews, goals, meetings).
  Best migration: fold its content into the new `/me/profile` under the
  employee shell, then leave `/hr/me` in place as a redirect for existing
  bookmarks. Don't try to serve two versions.
- **Auth model unification** — current dual system (Django token OR
  company_user in localStorage) makes gating fragile. Fixing it properly
  requires backend work (one canonical user identity). For the frontend
  restructure, we can work around by making `EmployeeLayout` accept both.
- **PM branch of `/user/dashboard`** — killing it entirely might break
  users who have a `project_manager` role but no direct URL to
  `/project-manager/dashboard`. Migration: add a redirect that
  role-checks and sends PMs to the full dashboard.
- **Notifications badge accuracy** — requires the backend `unread_count`
  endpoint to be per-tab-category, not one blob. Verify before promising
  in the UI.
- **`AgentLayout.jsx:44-59` auth check** — changing this to allow non-
  company_user access breaks assumption everywhere else in the
  company-user code. Safer: build EmployeeLayout as a peer, not a
  modification.

---

## Rollout order

Follows the same chunk pattern that worked for PM, Frontline, and HR.
Each chunk is independently mergeable.

1. **Groundwork — fix the profile bug** (`DashboardNavbar.jsx:322`) and
   remove the dead `showCompanyUserOptions` prop. Tiny, safe.
2. **Chunk A — Foundation.** Build `EmployeeLayout` + `EmployeeSidebar` +
   `employeeNavItems.js`. Add `/me/*` route group. All initial routes
   return placeholder "coming soon" panels. Doesn't touch existing
   `/user/dashboard`.
3. **Chunk B — Home.** Build the `HomeView` with summary tiles + pending
   action items + today's schedule. Wire to existing endpoints
   (getMyTasks, getMyProjects, meeting APIs).
4. **Chunk C — Tasks.** Extract from `UserDashboardPage`. Add sub-task
   interactivity, task detail drawer, comments/attachments (comments +
   attachments require backend, phase in).
5. **Chunk D — Meetings.** Unified meeting inbox (federate from HR + PM +
   Exec Meeting backends). Accept/Reject/Counter under three distinct
   buttons (fix current UX).
6. **Chunk E — Profile + Notifications.** Build `/me/profile` (avatar,
   phone, timezone, notification prefs, password) and `/me/notifications`
   (all-in-one inbox with unread tracking).
7. **Chunk F — HR employee content.** If HR module is enabled, fold
   `/hr/me`'s cards (leave, goals, reviews) into `/me/profile` sub-tabs
   or new `/me/hr` route. Deprecate `/hr/me` with a redirect.
8. **Chunk G — Delete PM branch from `UserDashboardPage`.** Redirect PM
   users to `/project-manager/dashboard` on login. Kills ~880 lines.
9. **Chunk H — First-run onboarding.** `userTutorialSteps.js`, welcome
   tour, profile completion nudge, empty-state CTAs.
10. **Chunk I — Kill old `/user/dashboard`.** All content migrated to
    `/me/*`. Add redirect so old bookmarks continue to work.

---

## Files that will be touched (rough scope)

**Modified:**
- `src/pages/UserDashboardPage.jsx` — biggest change. After Chunks C/D
  the tab bodies are extracted; after Chunk G the PM branch is deleted;
  after Chunk I the file becomes a redirect stub.
- `src/components/common/DashboardNavbar.jsx` — fix profile hard-link,
  add employee-aware nav items.
- `src/components/hr/HRMyProfilePage.jsx` — content folds into the new
  `/me/profile` in Chunk F.
- `src/App.jsx` — new route group under `EmployeeLayout`.
- `src/pages/LoginPage.jsx` — role-based redirect after login (PM →
  `/project-manager/dashboard`; company_user → agent dashboards;
  regular employee → `/me/home`).
- `src/components/common/ProtectedRoute.jsx` — new `requireEmployee`
  gate variant.

**New files:**
- `src/components/common/EmployeeLayout.jsx`
- `src/components/common/EmployeeSidebar.jsx`
- `src/utils/employeeNavItems.js`
- `src/pages/me/HomeView.jsx`
- `src/pages/me/TasksView.jsx`
- `src/pages/me/MeetingsView.jsx`
- `src/pages/me/ProfileView.jsx`
- `src/pages/me/NotificationsView.jsx`
- `src/pages/me/DocumentsView.jsx` (optional, Chunk F)
- `src/pages/me/GoalsView.jsx` (if HR enabled, Chunk F)
- `src/pages/me/LeaveView.jsx` (if HR enabled, Chunk F)
- `src/components/user/UserTaskDetailDrawer.jsx`
- `src/components/user/UserTaskCard.jsx`
- `src/components/user/UserMeetingCard.jsx`
- `src/components/user/EmployeeEmptyState.jsx`
- `src/utils/userTutorialSteps.js`

**Backend (out of scope for this frontend doc but worth flagging):**
- Federated meeting inbox endpoint `/api/me/meetings` (aggregate)
- Federated notifications endpoint with per-category unread counts
- Comment + attachment endpoints for tasks (if not existing)
- Employee self-service endpoints for profile fields (avatar upload,
  password change, notification prefs)
- Time-tracking endpoints (if we commit to the feature)

---

## Deliberately out of scope

Things that surfaced in the audit but shouldn't derail the restructure:

- **Auth model unification** (dual Django-token + company_user) — real
  backend work. Frontend restructure can proceed by accepting both.
- **Time tracking, learning & development, peer recognition** — big
  features. List them as follow-ups, don't scope-creep the restructure.
- **`CandidatePortalPage`** at `/candidate-portal` — external job
  candidates, different audience, leave alone.
- **`AgentLayout` audit** — not touching. New `EmployeeLayout` sits
  next to it, doesn't modify it.
- **`/company/profile`** — company-user profile page. Fix the routing
  bug in Chunk 1 but don't rebuild the page itself.
- **Frontline handoffs "my tickets" view** — real feature, needs
  backend permission model work, defer.
- **Reply Draft employee integration** — needs product decision on
  what an employee-scoped Reply Draft looks like vs. the admin tool.

---

## Recommendation on rollout

Given the size of this (13+ new files, 4-6 hour foundation work + follow-up
chunks over multiple sessions), the pragmatic order is:

1. **Fix the bug + dead prop this session** (Chunk 1) — 10 min, ships alone.
2. **Chunk A foundation this session** — new layout + sidebar with
   placeholder views. Zero regressions since it's a peer to existing
   routes. Employees can start seeing the new shell.
3. **Chunk B (Home) next session** — replace default landing.
4. **Chunks C-D** — progressively fill in Tasks + Meetings with extracted
   components + comments/attachments.
5. **Chunks E-F** — Profile + Notifications + HR employee-content migration.
6. **Chunks G-I** — kill old `/user/dashboard` PM branch, onboarding,
   redirect legacy URLs.

Each chunk stands alone; nothing is destructive until Chunk G/I.

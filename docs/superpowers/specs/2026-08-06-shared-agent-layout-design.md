# Shared Agent Layout — mount sidebar/navbar once, swap only content

**Date:** 2026-08-06
**Scope:** Frontend only (`PaPerProjectFront`). No backend changes.
**Builds on:** the nested agent sidebar (2026-08-06-nested-agent-sidebar-design.md).

## Problem

Switching agents feels like a full page reload: the sidebar disappears and a
full-screen spinner shows, then the new agent's shell re-appears. Two causes:

1. Four agents (SDR, Recruitment, Operations, Reply Draft) use **flat routes**
   where every navigation re-mounts the whole page — including the navbar +
   sidebar — and re-runs auth + `usePurchasedModules` (a DB call).
2. Every agent page's loading gate returns a **full-screen spinner** with no
   navbar/sidebar, so the sidebar vanishes on each mount.

The user wants: on login, purchased agents load with a **skeleton inside the
sidebar**; switching agents changes **only the right-hand content**, never the
sidebar.

## Investigation summary

The 8 agent pages are near-identical clones. 100% shared: the auth-guard effect,
`usePurchasedModules()`, the loading gate, the access-denied card, the gradient
wrapper, `<DashboardNavbar>` (which itself renders the top bar AND the left
`AgentSidebar`), and `handleLogout`. Per-page unique: `icon`, `title` fallback,
`section` string, and the `checkModuleAccess` module key. Four pages already use
`<Outlet/>` (Marketing, Frontline, HR, ExecMeeting); four render directly.

## Design

### 1. Per-agent config — `src/utils/agentMeta.js` (new)

A small map keyed by section, holding the per-agent bits the layout needs:

```js
export const AGENT_META = {
  'ai-sdr':      { icon: Target,       title: 'AI SDR Agent',        moduleKey: null /* always granted */ },
  'recruitment': { icon: UserCheck,    title: 'Recruitment Agent',   moduleKey: 'recruitment_agent' },
  'marketing':   { icon: Megaphone,    title: 'Marketing Agent',     moduleKey: 'marketing_agent' },
  'operations':  { icon: FileSearch,   title: 'Operations Agent',    moduleKey: 'operations_agent' },
  'frontline':   { icon: Headphones,   title: 'Frontline Agent',     moduleKey: 'frontline_agent' },
  'hr':          { icon: Users,        title: 'HR Support Agent',    moduleKey: 'hr_agent' },
  'exec-meeting':{ icon: CalendarClock,title: 'AI Executive Meeting Assistant', moduleKey: 'exec_meeting_agent' },
  'reply-draft': { icon: Reply,        title: 'Reply Draft Agent',   moduleKey: 'reply_draft_agent' },
};
```

### 2. `AgentLayout.jsx` (new) — the single mounted shell

One component for all 8 agents. Determines the current agent from the URL
(`location.pathname` → section, matching each agent's `basePath`). Does exactly
what every page did, ONCE:

- Auth guard effect (read `company_user`, redirect on missing/invalid).
- `usePurchasedModules()` — runs **once** and stays mounted across agent
  switches (no re-fetch, no re-mount).
- Loading + access-denied handling (see below).
- Renders the gradient wrapper + `<DashboardNavbar>` (→ top bar + sidebar) with
  props from `AGENT_META[section]` + `getAgentNavItems(purchasedModules, section, navigate)`.
- Content area: `<ErrorBoundary><Outlet/></ErrorBoundary>` (ErrorBoundary made
  universal — Frontline/HR/ExecMeeting already wrapped).

**Key behaviour — the sidebar never unmounts:**
- Because all agent routes are nested under ONE `AgentLayout` element, React
  Router keeps the same layout instance mounted while only the `<Outlet/>`
  swaps. Navbar + sidebar + `usePurchasedModules` persist. Only content changes.
- **Loading (modules not yet loaded):** DO NOT full-screen spinner. Render the
  navbar + sidebar normally; the sidebar shows an **agents skeleton** (shimmer
  rows) until `modulesLoaded`. The content area shows a small inline spinner.
  So on first login the shell is already there and agents fill in.
- **Access denied** (module not purchased, per `AGENT_META.moduleKey`): render
  the shell + the existing "Module Not Purchased" card in the content area
  (not full-screen), so the sidebar stays usable to navigate elsewhere.
  `ai-sdr` has `moduleKey: null` → always granted (matches current behaviour).

### 3. `App.jsx` — nest all agent routes under `AgentLayout`

Replace the 8 agents' flat/nested routes with children of one layout route:

```jsx
<Route element={<AgentLayout />}>
  {/* SDR (was flat) */}
  <Route path="/ai-sdr" element={<Navigate to="/ai-sdr/dashboard" replace />} />
  <Route path="/ai-sdr/dashboard" element={<SDRDashboard />} />
  <Route path="/ai-sdr/leads" element={<SDRDashboard />} />
  ... (all sdr tab paths → <SDRDashboard/>)
  {/* Recruitment (was flat) → <RecruitmentDashboard/> per path */}
  {/* Operations (was flat) → <OperationsDashboard/> per path */}
  {/* Reply Draft → <ReplyDraftWorkspace/> (extracted content) */}
  {/* Marketing/Frontline/HR/ExecMeeting keep their existing nested children */}
</Route>
```

The dashboards already read the URL internally (path or `?tab=`), so pointing
each path at the dashboard component (rendered through the layout's `<Outlet/>`)
switches content without re-mounting the shell.

`/recruitment/candidates/:id` (CandidateDetailPage) stays OUTSIDE the layout —
it's a separate full page today; leave it as-is to avoid scope creep.

### 4. Slim the 4 direct-render pages to content-only

- **SDR / Recruitment / Operations:** the page files become unnecessary — their
  content is just `<SDRDashboard/>` etc., which now render directly as Outlet
  children. Delete the page shells (or keep thin re-exports) and route straight
  to the dashboard components.
- **Reply Draft:** its 1740-line inline workspace + two sibling modals move into
  a `ReplyDraftWorkspace` component (extract the content JSX from the page's
  return, minus the shared shell) rendered as the Outlet child. Its own state/
  logic stays intact — only the shared shell (auth/navbar/gradient) is removed.

The 4 Outlet pages (Marketing/Frontline/HR/ExecMeeting) lose their shell too;
their existing Outlet children now render under `AgentLayout`.

### 5. `AgentSidebar.jsx` — skeleton + expand chevron

- **Skeleton:** accept a `loading` prop; while true, render shimmer placeholder
  rows instead of the agent list (shown during first `usePurchasedModules` load).
- **Expand chevron:** each agent row with `children` gets a chevron (▸ / ▾) on
  the right. Clicking the chevron toggles that agent's expanded state WITHOUT
  navigating; clicking the label/icon still navigates. The active agent is
  expanded by default; a per-section expanded map (local state) tracks manual
  toggles so a user can peek at another agent's items without leaving.

### 6. `DashboardNavbar.jsx` — sticky top bar

Make the header `sticky top-0 z-30` so it stays pinned while content scrolls.
(The sidebar is already `fixed`; the body padding-left already reserves space.)

## Migration safety

- Do the routing swap agent-by-agent is not possible (one layout wraps all), so
  we swap all 8 at once but keep each dashboard component unchanged — the risk is
  in `App.jsx` wiring and the 4 slimmed pages, both mechanical.
- `ProjectManagerDashboardPage` and `CompanyDashboardPage` are hub dashboards
  with different guard/logout logic — **left untouched**, not part of this
  layout.
- ExecMeeting's `[]` dep array and per-page toast strings are normalized by the
  single shared effect.

## Verification

- `npm run build` passes.
- Switch between agents: sidebar/top bar do NOT flash or reload; only content
  changes; no full-screen spinner between agents.
- First login: sidebar shows a skeleton until modules load, then agents appear.
- Access-denied agent shows the card in-content with the sidebar still present.
- Each agent's inner tabs still work (URL/`?tab=` driven); reload keeps the tab.
- Expand chevron toggles a non-active agent's children without navigating.
- Reply Draft workspace + its modals still function.

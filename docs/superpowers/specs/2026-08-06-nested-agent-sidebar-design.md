# Nested Agent Sidebar — inner tabs under each agent

**Date:** 2026-08-06
**Scope:** Frontend only (`PaPerProjectFront`). No backend/API changes.
**Builds on:** `2026-08-05-agent-sidebar-nav-design.md` (cross-agent sidebar).

## Problem

The left `AgentSidebar` lists agents (Dashboard, Recruitment, SDR, …) but each
agent's **inner** navigation (SDR: Leads / Meetings / Settings; Recruitment:
Jobs / Candidates / …) still lives as a horizontal tab bar inside the agent's
dashboard. The user wants those inner items **nested under each agent in the
sidebar**, and the redundant inner top tab bar removed.

## Current state (from investigation)

Each agent defines its inner tabs as a `TAB_ITEMS` array and switches via one of
three mechanisms:

| Agent | Switch mechanism | Tab defs |
|---|---|---|
| SDR | URL path — `navigate('/ai-sdr/<x>')` | `SDRDashboard.jsx` `TAB_ITEMS` |
| Recruitment | URL path — `navigate('/recruitment/<x>')` | `RecruitmentDashboard.jsx` `TAB_ITEMS` |
| Operations | URL path — `navigate('/operations/<x>')` | `OperationsDashboard.jsx` `TAB_ITEMS` |
| Frontline | URL query — `?tab=<x>` (same path) | `FrontlineDashboard.jsx` `FRONTLINE_TAB_ITEMS` |
| Marketing | **local `useState`** (no navigation) | `MarketingDashboard.jsx` inline array |

The three path-based and one query-based agents are URL-backed, so a sidebar link
just navigates. Marketing is local-state and must be refactored to be URL-backed.

## Design

### 1. Central config (`src/utils/agentNavItems.js`)

Add a `children` array to each agent in `ALL_AGENTS`, describing its inner items
as sidebar links. Two link shapes:

- **path**: `{ label, icon, path: '/ai-sdr/leads' }`
- **query**: `{ label, icon, path: '/frontline/dashboard', tab: 'documents' }`
  → sidebar navigates to `/frontline/dashboard?tab=documents`.

`getAgentNavItems` gains each shown agent's `children` (and `basePath` for
active detection). This is the single source of truth the sidebar reads; each
agent's own `TAB_ITEMS` stays as-is for now (they render the content routes), and
the config mirrors them. (Values verified against each dashboard's array.)

### 2. Marketing refactor (make it URL-backed)

`MarketingDashboard` currently does `const [activeTab, setActiveTab] = useState(...)`.
Change to derive from the URL query param, matching Frontline:

```js
const [searchParams, setSearchParams] = useSearchParams();
const activeTab = searchParams.get('tab') || 'dashboard';
const setActiveTab = (v) => setSearchParams(p => { p.set('tab', v); return p; }, { replace: true });
```

It already reads `?tab=` once on mount, so this is a small, behaviour-preserving
change: the inner content still switches, but now driven by the URL so the
sidebar (and reload / deep-link) can control it.

### 3. `AgentSidebar.jsx` — nested rendering

- Expanded desktop / mobile drawer:
  - Each agent is a row. The **active** agent (its `basePath` matches the current
    path) is expanded, showing its `children` indented below.
  - Clicking a non-active agent navigates to that agent's first/base route
    (existing `onClick`) — which makes it active and expands it.
  - Clicking a child navigates to the child link (path or `?tab=`).
  - Active child = violet highlight, derived from `location.pathname` +
    `searchParams`.
- Collapsed rail (icons only): children hidden; clicking an agent icon still
  navigates. (Keeps the rail compact.)
- Active-state detection: sidebar uses `useLocation` + `useSearchParams`.
  - agent active ⇔ `pathname.startsWith(agent.basePath)`
  - child active ⇔ path-child: `pathname` matches `child.path`; query-child:
    `pathname` matches `child.path` AND `searchParams.get('tab') === child.tab`.

### 4. Remove inner top tab bars (5 dashboards)

In each dashboard component, remove the horizontal tab **bar** (the desktop
`TabsList` + mobile dropdown) but KEEP the content switching:

- SDR / Recruitment / Operations: keep the `<Tabs value=… >` + `<TabsContent>`
  (they read the URL) but drop the `<TabsList>`/mobile dropdown block.
- Frontline: same — keep query-driven content, drop the tab bar.
- Marketing: keep `<TabsContent>` content, drop the `<TabsList>`; state now from
  the query param.

Content still renders for the active tab; only the now-duplicate bar is gone.

## Out of scope

- Backend/routes (all inner routes already exist).
- Re-styling the content pages themselves.
- Fixing the pre-existing SDR route/tab drift (`email-assistant` vs `crm-sync`) —
  noted but not in scope; the sidebar mirrors the rendered `TAB_ITEMS`.

## Verification

- `npm run build` passes.
- Each agent: sidebar shows its children when active; clicking a child switches
  content and highlights correctly; reload keeps the tab (URL-backed); collapse
  rail works; mobile drawer works; the old inner tab bar is gone.
- Marketing specifically: switching tabs updates `?tab=` and survives reload.

# Agent Navigation: Top Tabs → Collapsible Left Sidebar

**Date:** 2026-08-05
**Scope:** Frontend only (`PaPerProjectFront`). No backend/API changes.

## Problem

Cross-agent navigation (Dashboard, Recruitment, Marketing, SDR, Frontline, …)
currently renders as a horizontal row of **tabs** inside the top `DashboardNavbar`.
As the number of agents grows this reads as cramped and "bad dashboard". The user
wants these agents in a **left sidebar** like modern SaaS dashboards, not tabs.

## Goal

Move the cross-agent navigation out of the top-bar tabs into a **collapsible left
sidebar**. Keep each agent's own **inner** tabs (e.g. SDR's Leads / Meetings /
Settings) exactly as they are.

## Constraints

- Frontend only. No backend, API, or route changes.
- `DashboardNavbar` is used by ~10 agent pages (RecruitmentAgentPage,
  AiSdrAgentPage, MarketingAgentPage, …). One change should update all of them.
- The agent list source of truth stays `src/utils/agentNavItems.js`
  (`getAgentNavItems`) — purchased-module filtering unchanged; adding a new agent
  keeps working automatically.
- Preserve the existing dark-violet visual language (`#0d0b1a`, `#7c3aed`,
  lucide icons, violet glow active state).

## Approach (low-churn)

Render the sidebar **from within `DashboardNavbar`** as a `position: fixed` left
panel, and push page content right with a `margin-left` on the header + a spacer
mechanism. Because every page already mounts `DashboardNavbar` with
`navItems`/`activeSection`, no agent page JSX needs to change — the sidebar reads
the same `navItems` the tabs used.

### Components

1. **`AgentSidebar.jsx`** (new)
   - Props: `navItems` (from `getAgentNavItems`), `activeSection`, `collapsed`,
     `onToggle`, `mobileOpen`, `onMobileClose`.
   - Renders the agent list: icon + label (expanded) or icon-only with a native
     `title` tooltip (collapsed). Active item = violet highlight/glow.
   - A collapse toggle pinned at the bottom (‹ / ›).
   - Desktop: `position: fixed`, full-height, width 232px expanded / 64px
     collapsed.
   - Mobile (`< md`): hidden by default; shown as an overlay drawer when
     `mobileOpen`, with a scrim that calls `onMobileClose`.

2. **`DashboardNavbar.jsx`** (edit)
   - Remove the bottom "Navigation Tabs" block (lines ~313-339).
   - Add a hamburger button (mobile: opens the drawer; desktop: also toggles
     collapse) to the left of the title.
   - Render `<AgentSidebar/>` when `showNavTabs && navItems.length`.
   - Offset the header and the page below it by the sidebar width on desktop.

### Layout offset (zero page changes)

The sidebar is `position: fixed` at the far left. To stop it overlapping the
centered page content without editing any page, `DashboardNavbar` sets a
**`padding-left` on `document.body`** equal to the current sidebar width via an
effect:

- expanded desktop → `232px`
- collapsed desktop → `64px`
- mobile (`< md`) → `0` (sidebar becomes an overlay drawer, no reserved space)

The effect reads the collapsed state + a viewport media query, applies the
padding, and **restores the previous value on unmount**. Because the whole
document body shifts, both the sticky header and every page's content move
together — pages stay untouched.

### State

- `collapsed` persisted in `localStorage` (`agentSidebarCollapsed`), default
  expanded on desktop.
- `mobileOpen` is ephemeral component state, closed on route change / item click.
- `activeSection` already provided by each page.

## Out of scope

- Nesting each agent's inner tabs under the sidebar (user chose cross-agent only).
- Any change to `agentNavItems.js` data or purchased-module logic.
- Backend/routes.

## Verification

- `npm run build` passes.
- Spot-check: Recruitment, SDR, Marketing pages render with the sidebar; active
  agent highlighted; collapse toggle persists; mobile drawer opens/closes; inner
  agent tabs unaffected.

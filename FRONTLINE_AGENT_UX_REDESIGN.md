# Frontline Agent — UX Redesign Notes

Deferred task. Companion to `PM_AGENT_UX_REDESIGN.md`. Come back to this after
finishing the current in-flight work.

Context: audit of the Frontline (customer support) agent frontend. The
dashboard has **10 top-level tabs** with duplicated surfaces, a landing tab
that's a menu-of-menus, and no clear primary entry point for the person
who's actually here to work. It's a support-team platform trying to serve
two very different personas from one flat tab bar — the result is heavy for
both.

The audit that fed this doc found ~5,680 lines of JSX in a single dashboard
file with four "tab components" defined inline. So the restructure is not
just a UX call — it's also the right moment to split the file up.

---

## The real problems

1. **No primary "here is my work" surface.** PM has Project Pilot (a
   conversational entry point that works whether you have data or not).
   Frontline has 10 sibling tabs of equal visual weight. The most work-y
   tab — **Hand-offs** (the queue an agent replies from) — is **6th in the
   bar and missing from the Overview quick-jump grid** entirely. New agents
   can miss it.

2. **Two personas sharing one tab bar.** Support agents (who work the
   Hand-offs queue and reply to tickets) and admins (who feed the KB,
   watch SLA/gaps, configure workflows/notifications/the widget) get
   identical navigation. The 10 tabs aren't 10 problems — they're two
   personas of 5 tabs each interleaved.

3. **Two knowledge-Q&A surfaces doing the same thing.** The `qa` tab and
   the always-mounted floating chat both call the exact same
   `knowledgeQAStream` endpoint with the same citations. Same decision
   we made for PM: pick one surface. The floating chat is the better
   candidate because it's globally reachable via Ctrl+K from every tab.

4. **Two graph surfaces.** `ai-graphs` tab + `qa` tab's "Graph" mode
   dropdown do the same thing.

5. **Two "ask in plain language" boxes.** The `analytics` tab has its own
   NL query box independent of QA/Floating Chat, styled differently.

6. **Overview is a menu with admin insights sprinkled on top.** Stat cards
   (mostly zeros for new users) + `FrontlineInsightsPanel` (SLA / KB
   gaps / DLQ / audit / meeting action items — admin signals) + a
   6-card Quick Jump grid + a recent-documents strip. It competes with
   itself for attention. First-time users see stats of zero, "No data"
   in insights, and a menu. Same "lobby, not a workspace" problem PM had.

7. **Overview Quick-Jump grid is stale.** Missing Hand-offs, Notifications,
   AI Graphs — tabs shipped but the landing wasn't updated.

8. **Widget tab is really Settings** — it configures the public embed
   snippet, not a work surface. Belongs in an admin cluster.

9. **Notifications tab is two features in one.** End-user preferences
   (checkboxes) + admin template CRUD + scheduled sends. Different
   personas glued together.

10. **Ticket power-actions are buried.** Snooze, SLA pause, re-triage,
    notes, customer 360 all live behind a 3-dot dropdown menu — three
    clicks for high-value triage actions.

11. **Structural smell.** `FrontlineDashboard.jsx` is 5,680 lines with
    `HandoffQueueTab`, `FrontlineNotificationsTab`, `FrontlineWorkflowsTab`,
    and `FrontlineAnalyticsTab` defined as inline hoisted functions in
    the same file. Any restructure that doesn't extract them is going
    to be miserable to review.

12. **Bug found in flight:** `FrontlineInsightsPanel.jsx:203` sets
    `window.location.hash = 'documents'` to navigate. The dashboard is
    URL-query-param-driven (`?tab=…`), so the hash version silently
    doesn't switch tabs. Kill on sight.

---

## What to change (ranked by impact)

### 1. Pick a primary entry point per persona
Two viable landings, depending on who logs in:

- **Support agent** → land on **Queue** (Hand-offs + Tickets combined).
  This is their actual work.
- **Admin** → land on **Overview** or **Analytics**.

If we can't detect role reliably, default everyone to **Queue** — agents
almost always outnumber admins in a support org.

### 2. Collapse 10 tabs → 5

| New tab | Contains | Persona |
|---|---|---|
| **Queue** *(default landing)* | Hand-offs + Tickets as sub-tabs | Agent |
| **Knowledge** | Documents + full Knowledge Q&A as sub-tabs (QA tab kept — floating chat is for quick access, dashboard QA is for deep sessions) | Both |
| **Insights** | Overview's stat cards + `FrontlineInsightsPanel` (SLA / KB gaps / DLQ / audit) + Analytics + AI Graphs, all as sub-tabs | Admin |
| **Automation** | Workflows + Notification Templates + Scheduled sends, as sub-tabs | Admin |
| **Settings** | Widget config + Notification Preferences + any org-wide toggles, as sub-tabs | Admin |

**Hide (not delete) outright:**
- **`ai-graphs` tab** → fold into Insights as a sub-tab. Keep the Graph
  mode dropdown inside QA (it's a shortcut, harmless).
- **Analytics NL query box** → point users to the floating chat for
  natural-language questions; Analytics keeps just KPIs + charts +
  team perf + CSV export.

**Kept as-is (per user direction):**
- **`qa` tab** — floating chat is quick access; the full QA tab is for
  deep sessions with the sidebar history + scope picker + expandable
  graph dialog. Both coexist. QA moves into the new **Knowledge** tab
  as a sub-tab alongside Documents.

### 3. Unbury Hand-offs
Even before the tab collapse: **Hand-offs must be in the Overview quick-jump
grid**. Right now it's the tab you use most as an agent and it's the tab
Overview forgets exists. Small fix that helps immediately.

### 4. Fix the empty states that dead-end
Same pattern we used for PM. New users on:
- **Hand-offs**: "No hand-offs yet — this queue fills up when a ticket
  can't be auto-resolved by the AI. Meanwhile, [open a ticket manually →]."
- **Tickets**: replace bare "No tickets found" with an illustration + CTA
  to open the floating chat and describe an issue (Pilot's `/ticket`
  slash command creates one).
- **Widget**: add a first-run onboarding hint — "Copy the embed snippet
  below, paste into your site's HTML, then customers can start chatting."

### 5. Inline the ticket power-actions
Snooze / SLA pause / re-triage / notes are triage-flow actions. Behind a
3-dot menu they take 3 clicks. Options:
- Inline them as row-hover-revealed icons (like Gmail's row actions)
- OR open the ticket into a right-drawer with all actions visible (same
  pattern as Hand-offs already does)

The drawer pattern is more consistent since Hand-offs already uses it.

### 6. Split the 5,680-line file
Extract each inline tab component into its own file **before** doing the
restructure work. Non-negotiable groundwork:
- `HandoffQueueTab` → `frontline/HandoffQueueTab.jsx`
- `FrontlineNotificationsTab` → `frontline/FrontlineNotificationsTab.jsx`
- `FrontlineWorkflowsTab` → `frontline/FrontlineWorkflowsTab.jsx`
- `FrontlineAnalyticsTab` → `frontline/FrontlineAnalyticsTab.jsx`

Each extraction is mechanical and independently reviewable.

### 7. Collapsible sidebar (same as PM)
Once the tab count is down to 5, apply the same sidebar treatment PM got:
`hidden lg:flex`, collapsible, remembers state per browser, tooltip on
hover when collapsed, nested sub-tabs indented under parent when expanded.

### 8. Fix the hash-vs-query bug
`FrontlineInsightsPanel.jsx:203` sets `window.location.hash = 'documents'`.
Change to use `useSearchParams` and set `?tab=knowledge` (or whatever
the new tab name becomes). Silent broken navigation should not survive
the restructure.

---

## Trade-offs to plan around

- **Persona detection is fragile.** If we default to Queue as landing but
  an admin doesn't have any hand-offs / tickets, they hit an empty
  queue and think the app is broken. Two options: (a) always land on
  Queue, add strong empty-state coaching for admins; (b) detect role
  and route. Option (a) is simpler and matches "agents outnumber admins."
- **The floating chat's discoverability.** Killing the QA tab makes the
  floating chat the *only* KB Q&A surface. New users may not know
  Ctrl+K exists. Mitigate with a permanent "Ask the KB" pill in the
  header or on the Knowledge tab that opens the floating chat, similar
  to how PM has "Open Project Pilot" CTAs everywhere.
- **AI Graphs as its own tab was recent.** Folding it into Insights may
  demote it. If graphs are heavily used, keep them as a headline
  sub-tab within Insights, not a footer.
- **Workflows is huge and gnarly.** The step-builder modal alone is
  five levels of nested UI. Folding Workflows into Automation is fine,
  but the workflows sub-view itself likely deserves its own follow-up
  refactor (out of scope for this plan).
- **Widget under Settings.** If a customer-facing team uses the Widget
  tab to demo the widget to prospects, hiding it under Settings hurts
  that flow. Verify who actually clicks Widget today before moving it.
- **The Notifications tab split is real work.** End-user preferences
  belong under Settings; template CRUD + scheduling belong under
  Automation. That's not a rename, it's a real feature split.
- **Existing bookmarks / deep-links break.** URLs like
  `?tab=qa` will no longer highlight anything after we hide QA. Same
  approach as PM: `hidden: true` flag keeps content deep-link-reachable
  but out of the tab bar.

---

## Rollout order (when we come back to this)

Mirrors the PM rollout — small chunks, each independently mergeable and
reviewable.

1. **Groundwork — extract inline tab components** into their own files
   (`HandoffQueueTab`, `FrontlineNotificationsTab`, `FrontlineWorkflowsTab`,
   `FrontlineAnalyticsTab`). Pure code motion, no behavior change.
2. **Add Hand-offs to Overview Quick-Jump grid.** Include it +
   Notifications + AI Graphs. Trivial fix that helps today.
3. **Kill the hash-vs-query bug** in `FrontlineInsightsPanel.jsx:203`.
   One-line correctness fix.
4. **Empty-state CTAs** (mirrors PM Chunk 1) — Hand-offs / Tickets /
   Widget get proper empty-state cards steering to the useful action.
5. **Chunk A — Foundation.** Add `hidden: true` flag to `FRONTLINE_TAB_ITEMS`,
   filter visible tabs in the bar, keep TabsContent for hidden tabs
   (URL still works), scaffold the 5 new visible tabs (Queue, Knowledge,
   Insights, Automation, Settings) as placeholders.
6. **Chunk B — Knowledge.** Simplest new tab. Documents-only, straight
   port from the current `documents` tab.
7. **Chunk C — Queue.** Nested sub-tabs [Hand-offs | Tickets]. Reuse the
   extracted `HandoffQueueTab` and the current Tickets JSX.
8. **Chunk D — Insights.** Nested sub-tabs [Overview | Analytics |
   AI Graphs]. Overview keeps `FrontlineInsightsPanel`. Analytics loses
   its NL query box.
9. **Chunk E — Automation.** Nested sub-tabs [Workflows | Notification
   Templates | Scheduled]. Notifications tab gets split here.
10. **Chunk F — Settings.** Nested sub-tabs [Widget | Notification
    Preferences]. Rest of the Notifications tab lands here.
11. **Kill the QA tab.** Once floating chat has a permanent header CTA
    ("Ask the KB — Ctrl+K"), the QA tab is redundant. Add `hidden: true`.
12. **Collapsible sidebar** (mirrors PM). New file `FrontlineSidebar.jsx`,
    URL sub-tab state (`?tab=X&sub=Y`), localStorage-persisted collapse.
13. **Cleanup.** De-dupe anything left behind (AI Graphs Graph-mode dropdown
    inside QA, Analytics NL box, stale Quick-Jump grid).

Each step is a separate mergeable chunk.

---

## Files that will be touched (rough scope)

**Modified:**
- `src/components/frontline/FrontlineDashboard.jsx` — the big one.
  After Step 1 groundwork it'll shrink from ~5680 → ~2000 lines just from
  extraction. After Steps 5–12 the layout swaps to sidebar-driven.
- `src/components/frontline/FrontlineInsightsPanel.jsx` — bug fix +
  possibly moved under the new Insights tab
- `src/components/frontline/FrontlineFloatingChat.jsx` — becomes the
  sole KB Q&A surface; may need discoverability improvements
- `src/components/frontline/frontlineTutorialSteps.js` — steps for hidden
  tabs need filtering (same pattern as PM), quick-jump copy updates

**New:**
- `src/components/frontline/HandoffQueueTab.jsx` (extraction)
- `src/components/frontline/FrontlineNotificationsTab.jsx` (extraction)
- `src/components/frontline/FrontlineWorkflowsTab.jsx` (extraction)
- `src/components/frontline/FrontlineAnalyticsTab.jsx` (extraction)
- `src/components/frontline/QueueView.jsx` (new: Hand-offs + Tickets sub-tabs)
- `src/components/frontline/KnowledgeView.jsx` (new: Documents)
- `src/components/frontline/InsightsView.jsx` (new: Overview + Analytics + AI Graphs sub-tabs)
- `src/components/frontline/AutomationView.jsx` (new: Workflows + Templates + Scheduled sub-tabs)
- `src/components/frontline/SettingsView.jsx` (new: Widget + Preferences sub-tabs)
- `src/components/frontline/FrontlineSidebar.jsx` (mirrors PMSidebar)
- Empty-state component — can reuse the pattern from `pm-agent/EmptyState.jsx`
  or extract to `shared/AgentEmptyState.jsx` for both agents

**Backend:** no changes required. Same endpoints, same shapes.

---

## Deliberately out of scope

Things that came up in the audit but shouldn't derail the restructure:

- **Workflows step-builder refactor.** The nested modal-in-modal for
  building workflow steps is a real UX problem. Solve it in a follow-up.
- **Ticket table density.** 9 columns is a lot but users may want them
  all. Don't touch column set until someone complains.
- **Tour/hint density.** Every tab has spotlight glow + "Tour this tab"
  button + `InfoHint` icons. Reduce only after the restructure lands —
  otherwise we'd rewrite tour steps twice.
- **Recent-documents strip on Overview.** Fine as-is; migrate to the
  new Insights tab intact.
- **Two graph engines** (AI Graphs's LLM chart generator vs. Analytics's
  three fixed charts). Different features, both keep. Just group them
  under Insights.

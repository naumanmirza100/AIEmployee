# PM Agent — UX Redesign Notes

Deferred task. Come back to this after finishing the current in-flight work.

Context: audit of the Project Manager (Project Pilot) agent frontend. The
dashboard has grown into a *toolbox* — 9 tabs + floating chat + 9 sub-tools
inside "AI Tools" (~19 first-level entry points). It's not broken, but it
overwhelms new users and hides the actual value.

---

## The real problems

1. **Overview tab is a menu of menus.** New user lands on stats-of-zero + 5
   nav cards. Zero information, zero progress toward doing anything. It's a
   lobby, not a workspace.

2. **Empty state is silent.** With 0 projects: Task Prioritization is unusable
   (no projects in the dropdown), Timeline & Gantt is unusable, Knowledge Q&A
   has nothing to know about. Only Project Pilot and the Create tabs work —
   but that's not communicated anywhere. New users are silently steered into
   dead ends.

3. **Three ways to create a project.** Manual "Create Project" tab + manual
   "Create Task" tab + Project Pilot chat + Floating Chat's Pilot mode.
   Decision paralysis. Modern AI-first agents pick one dominant flow.

4. **19 first-level entry points is too many.** 9 tabs + Ctrl+K floating chat
   + 9 sub-tools in AI Tools. "AI Tools" itself is a junk drawer — Daily
   Standup, Notification Settings, and Meeting Notes have nothing in common
   except "AI made them."

5. **The tour is doing the UI's job.** The reason the onboarding tour is long
   is because the UI can't stand on its own. Good UX shouldn't need a
   walkthrough to be usable.

---

## What to change (ranked by impact)

### 1. Make Project Pilot the landing view
Not Overview. Pilot works with zero data (upload a spec, describe an idea,
ask a question). Overview becomes secondary — visit it once there are
projects worth looking at.

### 2. Collapse 9 tabs → 4

| New tab | Contains |
|---|---|
| **Ask** | Project Pilot chat (hero) |
| **Projects** | Project list + "New project" button; manual form becomes a dialog, not a tab |
| **Tasks** | Task list + "New task" button + Prioritization + Timeline/Gantt all folded in (they all operate on tasks) |
| **Insights** | Project Health, Daily Standup, Team Performance — the report-y things |

Delete outright:
- Create Project tab → dialog on Projects tab
- Create Task tab → dialog on Tasks tab
- Meeting Scheduler tab → Pilot can handle "schedule a meeting for Tuesday"; keep meetings list inside Projects
- Knowledge Q&A tab → redundant with floating chat; keep floating chat as the single Q&A surface

### 3. Fix the empty state
When 0 projects, replace the stats grid with one big card:

> **Describe your project or upload a spec — Pilot will set it up for you**
> [Try it →]
>
> Sample prompts:
> - "Plan a 3-week website redesign"
> - "Import from PRD"
> - "Break down this feature into tasks"

Show the stats grid only once real data exists.

### 4. Pick one Q&A surface
Floating chat OR tab — not both. Recommend keeping the floating chat (Ctrl+K
everywhere) and dropping the tab.

### 5. Unbury the two killer features
- **File upload in Pilot** ("upload a PRD, get a full project tree") — right
  now it's a small paperclip. Should be advertised at the top of Pilot.
- **Counter-propose for meetings** — currently buried inside Meeting Scheduler
  tab → Meetings sub-tab → invite list. Should surface as an inline action on
  any incoming invite.

---

## Trade-offs to plan around

- **Power users lose quick access to advanced features.** Mitigate with a
  slash-command palette in Pilot (`/health`, `/standup`, `/gantt`) — one
  keystroke away.
- **Existing users are used to the current layout.** Roll out behind a
  "New layout" toggle for a release, then flip the default. Don't just
  swap the layout in one PR.
- **Meeting Scheduler is a real feature, not a toy.** Folding it into Pilot
  works only if Pilot's meeting-handling is solid. Verify the meeting-related
  intents in `project_pilot_pipeline.py` handle scheduling/rescheduling
  before killing the standalone tab.
- **AI Tools has 9 sub-tools.** Some (Health, Standup) belong in Insights.
  Others (Notification Settings) belong in a Settings menu. A couple might be
  genuinely dead weight — decide per-tool before folding.

---

## Rollout order (when we come back to this)

1. Add empty-state CTAs on every tab first (low risk, high impact — makes the
   current UI usable even before restructuring).
2. Prototype "New layout" toggle in a settings menu; default OFF.
3. Ship Pilot-as-landing behind the toggle.
4. Ship the 4-tab consolidation behind the toggle.
5. Add slash-command palette to Pilot for power-user shortcuts.
6. Once feedback is positive, flip the toggle default to ON.
7. Delete the old layout after one release cycle.

Each step is independently mergeable and reviewable.

---

## Files that will be touched (rough scope)

- `src/pages/ProjectManagerDashboardPage.jsx` — biggest change (tab
  consolidation, default landing)
- `src/components/pm-agent/ProjectPilotAgent.jsx` — hero refinements,
  slash-command palette, upload advertisement
- `src/components/pm-agent/PMFloatingChat.jsx` — becomes the single Q&A surface
- `src/components/pm-agent/pmTutorialSteps.js` — tour shrinks because UI needs
  less explanation
- New: empty-state components for Projects / Tasks / Insights tabs
- Backend: no changes required for the frontend restructure. Slash commands
  reuse existing Pilot intents.

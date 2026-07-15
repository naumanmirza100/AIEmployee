# Tutorial & Onboarding — Roadmap

Suggestions for improving the tutorial, hints, and floating-chat system across the Frontline, HR, and Project Manager agents. Tick a box when done.

Each item has a short **why** so you can decide whether it's worth the effort.

---

## 🥇 Priority 1 — Quick wins (few hours each)

- [ ] **Extend to the Recruitment agent**
  Same pattern as PM: `recruitmentTutorialSteps.js`, wire main + per-tab tours, add hints, mount a floating chat. Only major differences: no dual-mode chat needed — just one recruitment-focused agent.
  *Why:* Only agent left without the system. Users will feel the inconsistency.

- [ ] **Extend to any other agents I missed** (Operations, Marketing, AI SDR, CRM Sync, Reply Draft, Meeting agent, Employee onboarding)
  Same recipe. Reuse `FrontlineTutorial` + `InfoHint`.
  *Why:* Users switching dashboards feel a jarring drop in helpfulness.

- [ ] **Hide the launcher pulse after first use**
  After the user opens a floating chat once, drop the `fcPing` animation. Store a `fc_launcher_seen` flag. The pulse is great for discovery but annoying for daily users.

- [x] **"Skip all remaining tours" button** in the skip-confirm modal
  Right now users have to skip 10 individual tab tours one by one. Give them a checkbox: *"Also skip other tab tours for this agent"* that sets all `<agent>_tour_*` keys at once.

- [ ] **Reset all tutorials** button in a Settings page or in the Hints toggle dropdown
  Power users and QA need a one-click way to re-enable every tour. Currently requires clearing localStorage manually.

- [x] **Copy consistency pass on all hint text**
  Read through every `HINTS` map end-to-end and tighten the copy. Some entries drift longer than others; some end with periods, others don't. A single style pass is worth doing before this gets translated. *(Done for Frontline / HR / PM only.)*

---

## 🥈 Priority 2 — UX polish (half a day each)

- [x] **Progress persistence across steps** — resume where you left off
  If a user clicks Skip mid-tour, save the current step index. Next replay offers *"Resume from step 5"* or *"Start over"*.

- [x] **Show a "tours available" badge next to each tab trigger**
  A small dot on tabs whose tour hasn't been seen yet — subtle prompt to click Tour this tab. Disappears once seen.

- [x] **Highlight the "Take the Tour" button on first login**
  A one-time pulse or tooltip pointing at the header button, so users know it exists even if they Skip the auto-launched tour.

- [x] **Toast when hints get toggled**
  Right now flipping the toggle is silent. A brief toast (*"Hints hidden — click the toggle again to show them"*) gives immediate feedback.

- [x] **Preserve last mode in PM Quick Chat**
  If a user last used Q&A mode, reopen in Q&A. Store `pm_fc_last_mode` in localStorage.

- [x] **Empty-state prompts differ per user's role**
  A brand new user sees different sample prompts than someone who's been active for weeks. Rotate the samples or pull from actual recent activity. *(Implemented as: dynamic samples from Recently Viewed + rotating pick from static pool.)*

- [ ] **Keyboard shortcut cheatsheet**
  A dialog reachable via `?` key showing every shortcut (Ctrl+K for chat, arrow keys for tour, Esc to close, etc). Especially useful for the tour keyboard nav which is currently undiscoverable.

- [ ] **Tooltip on the launcher showing chat count / unread**
  If the chat has 3 saved conversations, the launcher tooltip could preview the most recent one — like Gmail's compose button.

- [x] **Animate step transitions in the tour**
  Right now the ring snaps between targets. A short 200ms slide would feel more polished (but do it carefully — laggy animation is worse than snappy snap).

---

## 🥉 Priority 3 — Bigger features (a day+ each)

- [x] **Slash-command autocomplete for real values**
  When someone types `/ticket ` in Frontline chat, suggest recent ticket titles or a list of pending drafts. Similarly `/find` in HR should suggest matches as they type. *(Implemented for HR `/find <name>`; Frontline `/ticket` and PM commands take free-text titles so autocomplete adds no value.)*

- [x] **Action confirmations in Project Pilot**
  When Pilot creates a project/task, show a small inline card with the actual object it created, plus an Undo button (or a link to the created item). Currently the confirmation is text-only. *(Implemented as "View in Task Prioritization →" / "View in Timeline & Gantt →" jump links; Undo skipped because the PM API doesn't expose task-delete for Pilot-created tasks.)*

- [x] **Multi-turn context indicator**
  Show a small `↑ 6 messages of context` chip near the input so users know the AI remembers the earlier conversation.

- [x] **Draggable / resizable floating chat**
  The chat is stuck at 380x580 in the bottom-right. Some users will want to drag it or make it bigger. Add drag handle + resize corner.

- [ ] **"Explain this" right-click / long-press**
  Anywhere with a `data-tour-*` anchor, add a right-click menu with *Explain this element* that opens the same InfoHint card. Alternative discovery path for people who never notice the `!` icons.

- [ ] **Search across all chats (both dashboards)**
  A global search modal (via `Ctrl+Shift+F`?) that searches every conversation across every agent's chat history. Great for finding *"what was that ticket about last week?"* type questions.

- [ ] **Sticky "Recently Viewed" strip at the top of each dashboard**
  Currently only surfaced inside the floating chat's empty state. A small chip row at the top of the dashboard (`Recently viewed: #42 password reset · Doc: Refund Policy · Meeting: Q4 planning`) makes them one-click reachable.

- [ ] **Command palette (Ctrl+P) that runs any action**
  *"Create ticket…", "Open tab: Documents", "Search employees…", "Take tour: HR Meetings"* — same idea as VS Code. Complements the AI chat: chat for questions, palette for jumps.

- [x] **Contextual tour launches**
  When a user hovers on the Documents tab for 3 seconds without clicking, offer the Documents tour. Detect confusion and offer help proactively.

- [x] **Interactive tour steps — click-to-continue**
  Some steps could require the user to actually perform the action ("Click Create Ticket to continue"), similar to Duolingo's inline lessons. Higher engagement than pure narration. *(Engine support shipped via `step.waitFor: { selector, event, hint, autoAdvance }` — Next is disabled and a hint row appears until the user does the action. Not yet used in any tour step; add on the tour-copy side when useful.)*

- [ ] **Video snippets in tour steps**
  Optional short GIF / MP4 per step showing the interaction in motion. Adds file size and complexity, but great for genuinely complex tools like Timeline & Gantt.

---

## 📊 Analytics & feedback

- [ ] **Track tour completion rates**
  Fire a backend event on tour start, step advance, skip, finish. Answer questions like *"do users finish the PM main tour?"* or *"which step do they skip on?"*. Requires a `POST /telemetry/tour-event` endpoint.

- [ ] **Track chat engagement**
  Which mode do PM users prefer — Pilot or Q&A? How many messages per session? Which slash commands are used?

- [ ] **In-tour feedback capture**
  On the last step, add *"Was this tour helpful? 👍 👎"* — if 👎, ask what was missing. Sends to a `TourFeedback` model.

- [ ] **"Was this hint helpful?"** in every InfoHint popover
  Same idea but per-hint. Identify the hints nobody reads or that confuse people.

- [ ] **Session replay for tour dropouts**
  Optional integration with LogRocket / FullStory / Rrweb to replay sessions where users skipped early. Very high-signal for finding UX friction.

---

## ♿ Accessibility

- [ ] **Focus trap inside the tour tooltip**
  When the tour is open, `Tab` should cycle through Skip / Back / Next only, not escape into the underlying page.

- [ ] **Screen reader announcements**
  Add `aria-live="polite"` on the tour title change so screen readers announce each new step. Currently they may re-read the whole page.

- [ ] **Reduced-motion respect**
  Detect `prefers-reduced-motion: reduce` and disable the launcher pulse, ping animations, and tour tooltip transitions.

- [ ] **High-contrast mode**
  The amber-on-dark tour palette can be hard to read for some users. Detect `prefers-contrast: high` and swap to stronger borders + white/black text.

- [ ] **Keyboard-only tour usage audit**
  Try running every tour with just the keyboard (no mouse). Fix anything unreachable.

---

## 📱 Mobile

- [x] **Tour on mobile viewport**
  The current tour tooltip is 380px wide — clips off on narrow phones. Add a mobile mode: bottom-sheet-style tooltip that doesn't try to point at anything, just narrates the step. *(Detects viewport ≤640px via `useIsMobile`; tour tooltip becomes a full-width bottom sheet with a drag-handle pill, max-height 55vh, scrollable body. Highlight ring still tracks the target above the sheet.)*

- [x] **Floating chat as bottom sheet on mobile**
  The 380×580 modal covers the whole mobile screen anyway. On mobile, render as a full-height bottom sheet with a drag handle to dismiss. *(All three chats — Frontline, HR, PM — switch to 100vw × 85vh bottom sheet with a top-pill handle. Drag/resize disabled on mobile.)*

- [ ] **Ctrl+K equivalent for mobile**
  Long-press the launcher? Small floating help button? Something mobile users can discover.

---

## 🧪 Testing

- [ ] **Playwright / Cypress test suite for the tour engine**
  End-to-end tests that open each dashboard, run each main tour to the last step, verify no step's target 404s. Would have caught the "hidden sub-tab" issue much earlier.

- [ ] **Unit tests for `HintsProvider`, `useHints`, storage helpers**
  Simple pure functions — easy to test, high value if they break.

- [ ] **Screenshot regression tests for the tooltip layout**
  Each step's rendered tooltip should look consistent across browsers. Playwright's screenshot compare or Chromatic.

- [ ] **Storybook for InfoHint + FrontlineTutorial**
  Interactive playground for designers/PMs to preview tour copy without spinning up the whole app.

---

## 📚 Documentation

- [ ] **Developer README** for the tour system
  How to add a new tour to a new agent, how the `onEnter` hook works, how to name storage keys, how to reuse `HintsProvider`. New engineers currently have to reverse-engineer the whole pattern from HR/PM.

- [ ] **User-facing help center article**
  *"How Quick Chat works", "How the tour works, and how to replay it", "How to turn hints off"*. Link to it from the graduation cap button's tooltip.

- [ ] **Copy-owner document**
  A spreadsheet or Notion page listing every hint + tour step and who owns the copy. Currently the copy lives in three JS files scattered across three folders — hard for content people to audit.

- [ ] **Naming conventions doc**
  All the `data-tour-*` attributes follow a pattern (`data-tour-pm-tp="action-prioritize"`). Write down the convention so new anchors don't drift.

---

## 🧹 Cleanup / refactor

- [ ] **Move `InfoHint` + `FrontlineTutorial` to `components/common/`**
  They're already used by HR, PM, and the floating chats — the `frontline/` folder location is a historical accident. A rename would clean up all the `import from '../frontline/InfoHint'` cross-directory paths.

- [ ] **Extract `FloatingChatShell` component**
  The three floating chats (Frontline, HR, PM) share ~80% of the code — header, history sidebar, slash menu, input row. Extract a shell that takes props for the AI call, hints, storage keys, and mode config. Would let future agents add a floating chat in ~30 lines.

- [ ] **Unify storage-key naming**
  Some keys use `_v1`, some don't; some use camelCase, some snake_case. Pick one convention (recommend `<agent>_<feature>_v1` snake_case) and migrate.

- [ ] **Remove the leftover Django-template tour system**
  I built one for the Django-rendered version of Frontline early on, before we knew the real UI was the React SPA. That code still lives in `templates/frontline_agent/` + `static/frontline_agent/` and is dead. Safe to delete.

- [ ] **Consider one `HintsProvider` at the app root**
  Right now each dashboard wraps its own. If you move it up to `App.jsx`, the Hints: On/Off preference genuinely applies everywhere without any per-dashboard wiring.

---

## 🎁 Nice-to-have polish

- [ ] **Themed tour palettes per agent**
  Frontline = amber, HR = violet, PM = cyan — already partially there. Add gradient variants for each tour tooltip so users get visual cues about which agent they're in.

- [ ] **Confetti on Finish button 🎉**
  A tiny celebratory particle burst when the user completes their first tour. Cheap to add (10 lines of CSS/JS) and delightful.

- [ ] **Tour completion badges / achievements**
  *"You've completed all HR tours!"* Feed on progress. May feel gamified for a business tool — depends on your brand.

- [ ] **Localization**
  Wrap every string in an i18n hook (`t(...)`) so tours can be translated. Especially valuable if you have international customers — a lot of the tour value evaporates if the copy is only in English.

- [ ] **Contextual "Did you know?" tips**
  Once a week, when a user opens a dashboard, show a small dismissible tip: *"Did you know you can `/upload` a file directly into Quick Chat?"* Rotating pool of tips keeps discovery going long after the initial tour.

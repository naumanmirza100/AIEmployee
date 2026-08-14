# Agent Bugs — Frontline / Project Manager / HR

Extracted from `Agent Bugs.pdf` on **2026-08-13**.

- Bugs are grouped by the agent whose dashboard they affect.
- Bugs that appeared in a specific agent's section of the PDF but describe
  a **cross-cutting** issue (auth, global tabs, AI streaming, etc.) are
  copied into every agent they touch, with a note pointing back to the
  original section.
- A few bugs appeared under **other** agents' sections in the PDF
  (Recruitment / Exec Meeting / Marketing / Operations) but describe a
  pattern that clearly also exists in PM / Frontline / HR. Those are
  listed at the bottom of each affected agent as
  **"Same pattern in other agents — likely also here"** so we don't miss
  them.

Tick each box as we ship the fix.

---

## 1. Project Manager Agent

### 1a. Data integrity & business logic

- [x] **BUG-01 — Duplicate project names allowed** (Create Project)
  No unique constraint on Project Name; multiple projects can share the
  identical name.
  **Expected:** prevent duplicate names per workspace, or warn on save.
  > **Clarification (2026-08-13, before implementation):** The `Project`
  > model (`core/models.py:96`) has `name` (200 chars) plus a nullable
  > `company` FK — no `unique_together` today. I'll interpret "workspace"
  > as **the company** (Project.company), since that's the only
  > multi-tenant scoping the model has. Chosen behaviour: **soft warning
  > only** ("A project named X already exists in this workspace —
  > continue?"), because (a) real-world teams sometimes want duplicates
  > (e.g., "Website Redesign 2025", "Website Redesign 2026") and (b) a
  > hard block on an existing DB with duplicates would break existing
  > data. If you'd prefer a **hard block with an auto-suggested
  > "-copy" suffix instead**, say so and I'll switch.

- [x] **BUG-02 — Invalid budget logic** (Create Project)
  "Max Budget" accepts values lower than "Min Budget" (e.g., Min $1000,
  Max $500).
  **Expected:** enforce `Max ≥ Min` before submit.

- [x] **BUG-03 — Dashboard metric counter capped at 10** (Dashboard)
  After 10 projects, the dashboard tile freezes at "10".
  **Expected:** dynamic increment past 10 with no arbitrary limit.
  > **Clarification (2026-08-13):** Root cause: `api/views/company_dashboard.py:74`
  > slices `recent_projects[:10]` (intentional — panel is meant to show
  > "recent"). The frontend
  > (`ProjectManagerDashboardPage.jsx:534-539`) then uses
  > `projects.length` on the sliced list. The endpoint **already**
  > returns `stats.total_projects` with the correct count (line 64,
  > unused). Fix: point the tile at `stats.total_projects`. No backend
  > change needed for the counter; slice stays because the recent-panel
  > below the tile still uses it.

- [x] **BUG-04 — Project Pilot creates tasks for non-existent projects** (Project Pilot)
  Agent executes task-create commands even when the target project
  doesn't exist in the DB.
  **Expected:** reject task creation if parent project is not found.
  > **Clarification (2026-08-13):** Location is
  > `project_manager_agent/project_pilot_pipeline.py:646-748`. Currently
  > when the LLM emits `{"project_id": <int>}`, code fetches by ID with
  > **no company/owner scope** and (worse) silently falls back to the
  > first created project if the ID misses. Fix: (a) require the
  > project exists AND is owned by `created_by_company_user == company_user`,
  > (b) if lookup fails, **skip the task and log a warning to the
  > pilot's response** rather than silently reassigning to another
  > project. That "silent fallback" behaviour has caused tasks to land
  > on the wrong project — this is the real risk.

- [x] **BUG-05 — Knowledge Q&A prompt leakage** (Knowledge Q&A Agent)
  Agent answers off-topic questions (e.g., cake recipes) instead of
  staying on workspace data.
  **Expected:** tighten system-prompt constraints; refuse off-topic asks.

- [x] **BUG-06 — Task deadline allowed without project timeline** (Timeline & Gantt)
  Tasks accept deadlines even when the parent project has no timeline
  defined.
  **Expected:** bind task deadlines to parent project timeline; prompt
  the user to set it first.
  > **Clarification (2026-08-13):** Three cases to decide.
  >   1. Project has neither `start_date` nor `deadline` → **allow**
  >      task deadline, no warning. Rationale: many projects legitimately
  >      have no dates set yet (planning phase).
  >   2. Task deadline is **before** project.start_date → **hard reject**
  >      with clear message. Impossible to start a task before the
  >      project starts.
  >   3. Task deadline is **after** project.deadline → **hard reject**.
  >      This is the case the audit flagged (Gantt inconsistency).
  > Frontend: also constrain the date picker's `min`/`max` attributes so
  > the invalid dates aren't selectable in the first place.
  > If you'd prefer soft warnings instead of hard rejects, tell me.

### 1b. Security & data flow

- [x] **BUG-07 — Unrestricted file uploads** (Project Pilot)
  No file-size or MIME-type checks on document upload.
  **Expected:** enforce ≤ 10 MB size cap + strict MIME-type allowlist.
  > **Clarification (2026-08-13):** Partial protection already exists —
  > `api/views/pm_agent.py:3275` sets `MAX_FILE_SIZE = 10*1024*1024`,
  > and the extension whitelist at lines 3407-3414 restricts to
  > `.txt/.pdf/.docx`. **Missing:** (a) content-type / MIME check against
  > `request.FILES['file'].content_type`, (b) filename sanitisation
  > beyond `os.path.basename` (guard against `..`, embedded paths,
  > excessive length, null bytes). Not adding a magic-byte check because
  > `python-magic` isn't in requirements.txt and installing
  > libmagic-dev on Windows is painful — `content_type` from the browser
  > + extension whitelist is a reasonable second layer, deep magic-byte
  > check can be a follow-up if needed. Frontend also gets a client-side
  > size hint (currently silent when a user picks a 100MB file).

- [x] **BUG-08 — Incomplete Update-Project schema** (Create Project)
  Optional fields skipped at creation cannot be added later — the
  "Update Project" screen is missing those fields.
  **Expected:** Update UI has parity with Create UI.
  > **Clarification (2026-08-13):** The Update modal is in
  > `PaPerProjectFront/src/pages/CompanyDashboardPage.jsx:2822-2946`
  > (NOT in the PM Agent dashboard — PM's `ProjectsListView.jsx` is
  > read-only). Create form
  > (`components/pm-agent/ManualProjectCreation.jsx`) has: name,
  > description, status, priority, project_type, industry_id,
  > budget_min, budget_max, start_date, deadline. Update currently has
  > only: name, description, status, priority, project_type. **Adding:**
  > industry_id, budget_min, budget_max, start_date, deadline —
  > exactly the ones Create has that Update doesn't. Verifying the
  > update endpoint (`PUT /company/projects/{id}/update`) accepts those
  > fields before wiring the inputs.

### 1c. UI / UX

- [x] **UX-14 — Confusing Upload-button placement** (Project Pilot)
  An "Upload" button sits inside the chat box in a workspace meant for
  conversational task management.
  **Expected:** clearer visual/description or placement (RAG vs.
  attachment vs. avatar upload).

- [x] **UX-15 — Prioritize Tasks runs on 0-task project** (Task Prioritization)
  Button runs successfully on empty projects, produces confusing output.
  **Expected:** disable the button OR return "No tasks to prioritize."

- [x] **UX-16 — Orphaned subtasks** (Task Prioritization)
  Subtask generator reports "generated 0 subtasks" on empty projects; on
  populated projects, generated subtasks are hard to find.
  **Expected:** specify output target for generated subtasks; handle
  0-task state gracefully.

- [x] **UX-17 — Gantt chart label overlap** (Timeline & Gantt) — **ALREADY FIXED**
  Verified 2026-08-13: `TimelineGanttAgent.jsx:620, 697, 810-813, 822`
  already uses `line-clamp-2` / `truncate` on task titles,
  `whitespace-nowrap` + `bg-background px-1 rounded` on date labels,
  and skips calendar markers when < 3% or > 97% apart. No action needed
  unless visual QA finds an edge case.

### 1d. Cross-cutting bugs also affecting PM (from PDF's global rows)

- [x] **BUG-09 (Global) — Auth state stale across browsers**
  Logout on one browser leaves other sessions "partially authenticated":
  user stays on dashboard, protected features return 403 until manual
  logout/login.
  **Expected:** on 403 or invalid session, auto-clear state + redirect
  to login. *Also affects Frontline + HR — one fix clears three.*

- [ ] **UX-10 (Global Tabs) — No unsaved-changes warning on tab switch**
  Switching tabs with a dirty form wipes typed input silently.
  **Expected:** confirmation modal or draft preservation.
  *Also affects Frontline + HR.*
  > **⚠ Confusion (2026-08-13) — SKIPPED, needs product decision:**
  > "Dirty form" scope isn't obvious. Options:
  >   1. Track every input in the dashboard (biggest surface, most work).
  >   2. Track only Create/Edit modals + full-page forms (medium scope).
  >   3. Track only the two Create wizards (Project + Task) and Edit
  >      Project dialog (smallest scope, matches the audit's example).
  > Also: draft-preservation (auto-save to localStorage and restore on
  > return) vs confirm-dialog (block navigation until user confirms) are
  > very different UX. And on route-based tab switching (PM/HR use
  > `?tab=X`), a `useBlocker` guard is needed — different code from a
  > component-local state switch. Please pick scope + behaviour, then
  > we implement.

- [x] **UX-11 (Global Tabs) — No tab route persistence**
  Reloading any tab drops the user back on "Overview".
  **Expected:** route-based tab state (`?tab=…`).
  *Also affects Frontline + HR.*

- [x] **UX-12 (Create Forms) — Inconsistent submit-button disabled state**
  "Create Task" submit disables until inputs are filled; "Create
  Project" submit stays active on an empty form.
  **Expected:** disable submit on any empty mandatory form.

- [x] **UX-13 (Conversations) — No confirmation on chat-history delete** — PM agents done; HR/Frontline pending
  Trash icon deletes past chat thread immediately.
  **Expected:** confirmation modal.
  *Also affects Frontline chat + HR floating chat + Meeting Scheduler.*

- [ ] **UX-18 (AI Agent) — No "Stop generating" button during streaming**
  Cannot cancel an active AI stream.
  **Expected:** "Stop Generating" button during streaming states.
  *Also affects Frontline Q&A, HR chat, HR Meeting Scheduler, PM Pilot.*
  > **⚠ Confusion (2026-08-13) — SKIPPED, larger scope than it looks:**
  > Neither Project Pilot nor Knowledge Q&A actually **streams** today —
  > both are single-shot: request goes out, spinner shows, one big reply
  > lands. Grep for `AbortController`, `EventSource`, `SSE`, `stream`
  > returns nothing in either agent. A real "Stop generating" button
  > needs one of two changes:
  >   1. Switch to SSE / streamed responses end-to-end (backend LLM call,
  >      Django streaming response, frontend `EventSource` reader) so the
  >      user can `AbortController.abort()` mid-stream.
  >   2. Add a `/pilot/jobs/{id}/cancel` endpoint that the running Celery
  >      task polls between LLM turns.
  > Either is real work. A "fake" Stop button that just discards the
  > response client-side while the server keeps running would be
  > misleading. Please pick 1 or 2 before we implement.

### 1e. Same pattern in other agents — likely also here

- [x] **EXEC-BUG-02 pattern — Past due dates accepted** (from Exec Meeting Tasks)
  PM's task-creation date picker likely accepts past dates the same way.
  **Expected:** restrict to today+ or warn.
  Fixed: Edit Project + Edit Task modals in CompanyDashboardPage now use
  `min={today}` / `min={now}`. Create flows already enforced this.

- [x] **EXEC-BUG-03 pattern — Editable fields during AI generation** (from Exec Meeting Documents)
  PM Pilot / Prioritization forms likely stay editable while the AI
  streams a response.
  **Expected:** disable inputs during generation.
  Fixed: Project Pilot now also disables the project Select, Attach Spec
  button, Send-file button, and remove-file X while generating. Textarea
  + Send were already gated.

- [ ] **MKT-04/05/06 pattern — Q&A hallucination / no context memory / claims false actions**
  PM Knowledge Q&A (BUG-05) already leaks off-topic; verify it also
  loses context across follow-ups and refuses to falsely claim
  destructive actions succeeded.
  > **Status (2026-08-13):**
  > - **MKT-04** (off-topic hallucination) — FIXED by the BUG-05 scope
  >   guard added to `knowledge_qa_agent.py:509-542`.
  > - **MKT-05** (context memory) — FIXED already. The Q&A agent stitches
  >   the last 10 turns of `chat_history` into `conversation_context`
  >   before calling the LLM (`knowledge_qa_agent.py:544-585`).
  > - **MKT-06** (claims false actions) — **⚠ Confusion — SKIPPED,
  >   needs product decision.** The Pilot's per-action `action_results`
  >   ARE truthful (failures set `success: False, error: …` at
  >   `project_pilot_pipeline.py:633-638`). But the LLM's natural-language
  >   `answer` string is generated BEFORE the DB writes run and is
  >   never reconciled with the actual outcomes, so it can still say
  >   "Task created!" while `action_results` shows the failure. Three
  >   options for fixing:
  >     1. Post-process the LLM `answer` to strip / rewrite success
  >        claims that don't match `action_results` (regex-heavy, brittle).
  >     2. Run a second LLM turn AFTER actions execute that rewrites
  >        the answer given the true outcomes (costs one more LLM call).
  >     3. Prepend/append a system-generated banner to the answer
  >        listing failed actions with their errors (cheapest, honest,
  >        but adds duplicate info alongside the LLM answer).
  >   Please pick 1/2/3 before we implement.

---

## 2. Frontline Agent

### 2a. Explicit Frontline bugs (FRONTLINE-BUG-01 … 12)

- [ ] **FRONTLINE-BUG-01 — "Accept Hand-off" crashes the panel** (Hand-offs Tab)
  React error boundary: `RotateCcw is not defined`.
  **Expected:** ticket assignment updates; status smoothly transitions
  to active without crash.

- [ ] **FRONTLINE-BUG-02 — "Reassign" throws JS TypeError** (Hand-offs Tab)
  `frontlineAgentService.listWorkflowCompanyUs...is not a function` —
  typo/missing export.
  **Expected:** dropdown of available team members.

- [ ] **FRONTLINE-BUG-03 — Public Chat crashes on gibberish input** (Public Chat Widget)
  Random text → backend 500 → "Failed to process question" red box.
  **Expected:** graceful fallback message: "I didn't quite catch that.
  Could you please rephrase?"

- [ ] **FRONTLINE-BUG-04 — Chat Widget saves corrupted CSS** (Chat Widget Config)
  Garbage like `---000` for font or `1@@@3` for colors saves without
  validation; public chat renders as a solid unreadable box.
  **Expected:** validate hex colors + CSS length units; block save on
  invalid input.

- [ ] **FRONTLINE-BUG-05 — Q&A can't see document list or upload dates** (Knowledge Q&A)
  Agent does semantic search instead of registry lookup — returns
  random chunks from unrelated PDFs.
  **Expected:** query the document metadata table directly.

- [ ] **FRONTLINE-BUG-06 — "Send Reply" fails on internal KB-gap tickets** (Hand-offs Tab)
  Internal tickets have no customer → "Send failed: No recipient available".
  **Expected:** disable Send Reply for internal tickets, or replace
  with "Internal Note / Resolve" button.

- [ ] **FRONTLINE-BUG-07 — Outdated docs still selectable in Q&A dropdown** (Knowledge Q&A)
  Marking a document outdated doesn't filter it from the "Add document"
  dropdown, causing dead-end UX loop.
  **Expected:** filter outdated files OR show them disabled with
  "(Outdated)" badge.

- [ ] **FRONTLINE-BUG-08 — Analytics date picker accepts impossible dates** (Analytics Tab)
  `02/31/0343` and 6-digit years like `232333` accepted, queried.
  **Expected:** validate calendar boundaries + enforce reasonable year
  range.

- [ ] **FRONTLINE-BUG-09 — Allowed-origins field accepts malformed strings** (Chat Widget Config)
  Double commas, empty entries saved verbatim → breaks CORS matching.
  **Expected:** sanitize, trim, dedupe origins on save.

- [ ] **FRONTLINE-BUG-10 — Analytics confuses "Documents" with "Tickets"** (Analytics Tab)
  "How many documents exist?" returns the ticket count (4) instead of
  the actual doc count (5).
  **Expected:** query the correct source OR clarify the metric name.

- [ ] **FRONTLINE-BUG-11 — "Choose File" button invisible in dark mode** (Documents Tab)
  Dark grey button on dark grey modal — essentially unfindable.
  **Expected:** high-contrast background.

- [ ] **FRONTLINE-BUG-12 — "Save Prompt" active on failed generations** (AI Graphs Tab)
  Save button remains clickable even after "No data available".
  **Expected:** disable Save on failed/empty generation.

### 2b. Cross-cutting bugs also affecting Frontline

- [x] **BUG-09 (Global) — Auth state stale across browsers** — see PM 1d.
- [ ] **UX-10 (Global Tabs) — No unsaved-changes warning on tab switch** — see PM 1d.
- [x] **UX-11 (Global Tabs) — No tab route persistence** — see PM 1d.
- [x] **UX-13 (Conversations) — No confirmation on chat-history delete** — PM agents done; HR/Frontline pending — Frontline public chat + hand-off notes.
- [ ] **UX-18 (AI Agent) — No stop button during streaming** — Frontline Q&A + public chat.

### 2c. Same pattern in other agents — likely also here

- [ ] **MKT-03 pattern — "Choose File" invisible / hard-to-see uploader**
  Same as FRONTLINE-BUG-11 (Documents Tab) — Marketing Add-Leads
  uploader has the same styling bug. If we fix one shared component it
  clears both.

- [ ] **OPS-01 pattern — Faulty document upload shows technical error, not human message**
  Ops Documents tab returns raw stack-trace-style errors on bad CSV.
  Frontline document upload has the same shape; likely same failure
  mode.

- [ ] **REC-BUG-01 pattern — LLM hallucinates when data truncated / missing** — same
  class as FRONTLINE-BUG-05 (Q&A can't see doc list). Any Frontline
  agent that truncates retrieval context will hallucinate confidently.

---

## 3. HR Support Agent

### 3a. Explicit HR bugs (from PDF "HR Support Agent" section)

- [ ] **HR-BUG-01 — Deactivate / Anonymize use browser alerts, not styled modals** (Employees tab)
  Native `alert()` / `confirm()` dialogs on Deactivate and Anonymize
  actions.
  **Expected:** styled in-app confirmation modal matching the rest of
  the HR UI.

- [ ] **HR-BUG-02 — "Review Cycles" date picker not visible** (Employees → Review Cycles)
  Date-picker inputs in the "Performance review cycles" dialog render
  invisibly (styling issue).
  **Expected:** legible/clickable date-picker component.

- [ ] **HR-BUG-03 — Leave-Balances "Apply" button does nothing** (Employees → Leave Balances → Adjust)
  Clicking Apply in the "Adjust leave balance" modal has no effect.
  **Expected:** apply the change, persist, close modal, refresh row.

- [ ] **HR-BUG-04 — Compensation form has no numeric validation** (Employees → Compensation History → Add)
  Negative numbers accepted for base salary, bonus target %, equity
  grant value, and grade/band. Notes field accepts giant unfiltered
  strings.
  **Expected:** enforce non-negative numerics + reasonable maxima;
  reasonable notes length.

- [ ] **HR-BUG-05 — "Add Goal" form has no numeric or date validation** (Employees → Goals & OKRs → Add Goal)
  Negative Target / Progress / Weight accepted; due date accepts
  invalid values like `08/07/2333`.
  **Expected:** validate numerics (non-negative, sensible ranges) and
  clamp date to sane year range.

- [ ] **HR-BUG-06 — Meeting Scheduler loses participants across turns** (Meeting Scheduler)
  Multi-turn conversation forgets participants previously selected in
  earlier turns.
  **Expected:** persist participant selection across the full
  scheduling flow.

- [ ] **HR-BUG-07 — Meeting Scheduler misinterprets relative weekdays** (Meeting Scheduler)
  "Schedule for Friday" resolves to the wrong date (e.g., past
  Thursday, or a Feb-30 style non-date).
  **Expected:** correctly resolve relative weekday phrases against the
  scheduler's current date.

### 3b. Cross-cutting bugs also affecting HR

- [x] **BUG-09 (Global) — Auth state stale across browsers** — see PM 1d.
- [ ] **UX-10 (Global Tabs) — No unsaved-changes warning on tab switch** — HR forms suffer this too.
- [x] **UX-11 (Global Tabs) — No tab route persistence** — reload on HR dashboard resets to Overview.
- [x] **UX-13 (Conversations) — No confirmation on chat-history delete** — PM agents done; HR/Frontline pending — HR floating chat + Meeting Scheduler conversations.
- [ ] **UX-18 (AI Agent) — No stop button during streaming** — HR chat + Meeting Scheduler + any HR AI action.

### 3c. Same pattern in other agents — likely also here

- [ ] **EXEC-BUG-02 pattern — Past due dates accepted**
  HR Review Cycles (`period_start`, `period_end`, self-review due,
  manager-review due) and HR Goals due-date likely accept past dates.
  Compensation "Effective date" should probably not be far-future.

- [ ] **EXEC-BUG-03 pattern — Editable fields during AI generation**
  HR chat + Meeting Scheduler inputs stay editable while the AI
  streams. Same mutation risk as EXEC-BUG-03.

- [ ] **EXEC-BUG-05 / EXEC-BUG-01 pattern — Developer placeholder / prompt-template leak on empty inputs**
  HR generated documents (offer letters, review templates, if any) may
  leak literal `[Name]` / `[DD MMM YYYY]` when data is missing.

- [ ] **MKT-04/05/06 pattern — Q&A hallucination, lost context, false-success claims**
  HR chatbot ("Ask HR") likely has:
  - Off-topic / hallucinated answers when a policy isn't indexed
  - Lost context across follow-up turns
  - Claims to have performed employee-record changes it can't actually do

- [ ] **REC-BUG-01 pattern — LLM hallucinates on truncated retrieval**
  If HR's employee/policy retrieval hard-truncates fields, HR chat will
  confidently claim "no mention of X" when X was truncated out.

---

## Implementation order — recommendation

Working from highest-severity / lowest-effort to biggest:

1. **Hard crashes first** — FRONTLINE-BUG-01, FRONTLINE-BUG-02.
2. **All-users-see-instantly HR polish** — HR-BUG-01, HR-BUG-02, HR-BUG-03.
3. **Global one-fix-clears-three** — BUG-09 (auth), UX-10/11/13/18.
   Land these once in the shared layout/chat components.
4. **Input validation sweep** — HR-BUG-04, HR-BUG-05, FRONTLINE-BUG-08,
   FRONTLINE-BUG-09, BUG-01, BUG-02, BUG-06, plus EXEC-BUG-02 pattern
   (dates).
5. **Q&A / RAG grounding sweep** — BUG-05 (PM), FRONTLINE-BUG-05,
   FRONTLINE-BUG-07, FRONTLINE-BUG-10 + the MKT-04/05/06 patterns for
   HR chat + PM Pilot.
6. **UX polish** — UX-14/15/16/17, FRONTLINE-BUG-04, FRONTLINE-BUG-11,
   FRONTLINE-BUG-12, HR-BUG-06, HR-BUG-07.

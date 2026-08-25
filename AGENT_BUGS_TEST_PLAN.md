# Agent Bugs — Manual Test Plan

Companion to [AGENT_BUGS.md](AGENT_BUGS.md). Every bug that was actually
implemented is listed here with reproduction steps and the expected
post-fix behaviour. Tick each one as you verify.

- ⚡ = crash / regression risk — test first
- 🎯 = user-visible behaviour change
- 🔒 = validation / security check
- 🧠 = LLM-driven behaviour (may need 1–2 retries to see the pattern)

---

## Setup

Before starting, get a clean environment:

1. **Backend up:** `python manage.py runserver` (from repo root).
2. **Frontend up:** `cd PaPerProjectFront && npm run dev`.
3. **Fresh browser session** — open an incognito window so localStorage
   is clean and old cached tokens don't confuse the auth tests.
4. **Log in as a company_user** who has:
   - PM Agent + Frontline Agent + HR Agent modules enabled.
   - At least **2 Employees** (for HR + Meeting Scheduler tests).
   - At least **2 Projects with tasks** (for PM tests).
   - Enough tickets/docs (for Frontline analytics tests).
5. Keep a second browser (e.g. Firefox) ready for the **BUG-09 auth
   test** — you need two active sessions.

Backend logs are useful — watch the terminal running `runserver` for
`HR-BUG-06 fallback`, `HR-BUG-07 corrected LLM date`, and similar
markers we added.

---

## 1. Project Manager Agent

### 1a. Data integrity & business logic

- [ ] 🎯 **BUG-01 — Duplicate project names**
  1. PM Agent → Projects → **Create project** → name it `Foo`.
  2. Create another project with the exact name `Foo`.
  3. **Expected:** browser confirm dialog: *"A project named 'Foo'
     already exists in this workspace — Create it anyway?"* Cancel →
     nothing saved. Confirm → second `Foo` created.

- [ ] 🔒 **BUG-02 — Invalid budget logic**
  1. Create Project → Budget Min = `1000`, Budget Max = `500` → Submit.
  2. **Expected:** red toast *"Maximum budget must be greater than or
     equal to the minimum."* Nothing saved.
  3. Try Budget Min = `-100` → *"Minimum budget must be a non-negative
     number."*

- [ ] 🎯 **BUG-03 — Dashboard counter capped at 10**
  1. Have (or create) more than 10 projects for this company_user.
  2. Reload `/project-manager/dashboard`.
  3. **Expected:** the **Total Projects** stat card shows the real
     total (e.g. `13`), not `10`. Active / Planning / Completed tiles
     also reflect true counts.

- [ ] ⚡🧠 **BUG-04 — Project Pilot creates tasks for non-existent projects**
  1. PM Agent → Project Pilot → *"Create task 'Test' in project id
     999999"* (a project id that definitely doesn't exist).
  2. **Expected:** response says *"Rejected task 'Test': target
     project not found — no project_id or project_name was
     specified."* No stray task created against another project.
  3. Backend log should include: `Project Pilot: rejecting task 'Test'
     — project_id 999999 does not exist…`.

- [ ] 🧠 **BUG-05 — Knowledge Q&A off-topic**
  1. PM Agent → Knowledge Q&A → ask *"What's a good chocolate cake
     recipe?"*.
  2. **Expected:** *"I can only answer questions about your projects,
     tasks, team, and related workspace data…"* — no cake recipe.
  3. Also try *"What's the weather in London?"* → same refusal.
  4. Sanity check: ask a real workspace question ("How many tasks in
     project X?") → still answers normally.

- [ ] 🔒 **BUG-06 — Task deadline outside project timeline**
  1. Create a project with start_date `today`, deadline `today + 30d`.
  2. Create a task inside it with due_date `today + 60d` → rejected
     with *"…is after the project deadline…"*.
  3. Try due_date `today - 5d` → rejected with *"before project start"*.
  4. Also confirm the picker itself refuses those dates — the calendar
     greys out anything outside the project window.
  5. The task-create form should show *"Project window: 2026-08-13 →
     2026-09-12"* under the deadline input.

### 1b. Security & data flow

- [ ] 🔒 **BUG-07 — Unrestricted file uploads**
  1. Project Pilot → Attach spec → pick a `.txt` bigger than 10 MB →
     rejected client-side *"X MB exceeds the 10 MB limit."*
  2. Rename a `.zip` to `.pdf` and upload → server rejects with
     *"File's declared type (application/zip) does not match its
     extension (.pdf)."*
  3. Try an empty file → *"This file is empty (0 bytes)…"*.
  4. Try a filename with `../../etc/passwd` embedded → server
     sanitises, file stored under just `passwd` in the upload dir
     (check backend `media/project_pilot_uploads/`).

- [ ] 🎯 **BUG-08 — Update Project schema parity**
  1. Company Dashboard → Projects → **Edit** any existing project.
  2. **Expected:** the Edit modal now shows: name, description, status,
     priority, project type, **industry, budget min, budget max, start
     date, deadline** — the last five used to be missing.
  3. Change all of them → Save → reopen → values persisted.

### 1c. UI/UX

- [ ] 🎯 **UX-12 — Consistent submit disabled state**
  1. Create Project with empty name → **Create Project** button
     disabled (was previously clickable).
  2. Create Task with empty title → **Create Task** button disabled
     even after selecting a project.

- [ ] 🎯 **UX-13 for PM — Chat delete confirmation**
  1. Project Pilot → hover a chat in the sidebar → trash icon → click.
  2. **Expected:** browser confirm *"Delete 'Chat title'? This cannot
     be undone."* Same for Knowledge Q&A chats.

- [ ] 🎯 **UX-14 — Upload button label**
  1. Project Pilot chat bar → the file button now reads **"Attach
     spec"** (not the ambiguous "Upload"). Hover it → tooltip:
     *"Attach a spec, brief, or notes (.txt / .pdf / .docx) for the
     agent to read."*

- [ ] 🎯 **UX-15 — Prioritize on 0-task project**
  1. Create a new project with **zero tasks**.
  2. PM Agent → Task Prioritization → select that project.
  3. **Expected:** all four action buttons (Prioritize, Bottlenecks,
     Delegation, Generate Subtasks) disabled. Amber hint below the
     project selector: *"This project has no tasks yet — create at
     least one task before prioritising or generating subtasks."*
  4. In the project dropdown, empty projects are annotated with *"— 0
     tasks"*.

- [ ] 🎯 **UX-16 — Subtask generation output**
  1. On a project **with tasks**, run Generate Subtasks.
  2. **Expected:** success toast shows *"Generated N subtask(s)
     successfully — They now nest under each task on the Tasks tab —
     open a task's row to review or edit them."*
  3. Open the Tasks tab and verify they actually appear under each
     task.

- [ ] 🎯 **EXEC-BUG-02 pattern — Past due dates in Edit modals**
  1. Company Dashboard → Edit Project → Start Date picker → try to
     pick a date before today → greyed out.
  2. Company Dashboard → Edit Task → Due Date (datetime-local) → same.

- [ ] 🎯 **EXEC-BUG-03 pattern — Editable inputs during generation**
  1. Project Pilot → type a prompt → send.
  2. While the spinner is running, try to:
     - Click **Attach spec** → button disabled.
     - Change the project in the **All projects** dropdown → disabled.
     - Click the file **X** to remove an attached file (if any) →
       disabled.
  3. Textarea and Send were already disabled — should stay that way.

### 1d. Cross-cutting

- [ ] ⚡🔒 **BUG-09 — Auth state stale across browsers**
  1. Open Browser A + Browser B, log into the same company_user
     account in both.
  2. In A, hit **Logout**.
  3. In B, click any tab / trigger any API call.
  4. **Expected:** Browser B auto-redirects to `/company/login`
     (or `/login` for Django-token users) with a toast about the
     session ending. Before the fix, B would stay on the dashboard
     and every request would silently 403.

- [ ] 🎯 **UX-11 — Tab route persistence**
  1. PM Agent → click any non-default tab (say **Tasks**).
  2. Reload the browser.
  3. **Expected:** you stay on Tasks. URL still shows `?tab=tasks`.
  4. Same for HR (`?tab=employees`, `?tab=meetings`) and Frontline
     (`?tab=documents`, etc.).

---

## 2. Frontline Agent

### 2a. Explicit Frontline bugs

- [ ] ⚡ **FRONTLINE-BUG-01 — Accept Hand-off crash**
  1. Frontline → Hand-offs tab → open any pending ticket → click
     **Accept hand-off**.
  2. **Expected:** ticket flips to active, no red React error box, no
     "RotateCcw is not defined". The **Release** button (which uses
     that icon) also renders correctly on accepted hand-offs.

- [ ] ⚡ **FRONTLINE-BUG-02 — Reassign TypeError**
  1. Same Hand-offs pending ticket → click **Reassign…**.
  2. **Expected:** popover opens with a list of company users. Before
     the fix it showed a red error toast about
     `listWorkflowCompanyUs…is not a function`.

- [ ] 🎯🧠 **FRONTLINE-BUG-03 — Public Chat crash on gibberish**
  1. Open your public chat widget page (`/embed/chat?widget_key=…` or
     wherever your tenant's public widget lives).
  2. Type `dejheuhfrufr` → send.
  3. **Expected:** a friendly reply like *"I didn't quite catch that
     — could you rephrase your question? Try including specific
     product names, ticket IDs, or a bit more context."* No red 500
     error box.

- [ ] 🔒 **FRONTLINE-BUG-04 — Widget CSS validation**
  1. Frontline → Chat Widget Config → **Theme** section.
  2. Set primary_color = `1@@@3` → Save.
  3. **Expected:** save rejected with *"theme.primary_color must be a
     hex colour like '#7c3aed' (got: '1@@@3')."*
  4. Set border_radius = `---000` → *"theme.border_radius must be a
     CSS length like '12px' or '0.75rem'…"*
  5. Set primary_color = `#3b82f6` → saves fine.

- [ ] 🎯 **FRONTLINE-BUG-06 — Send Reply gated on internal tickets**
  1. Frontline → Q&A → ask something the KB can't answer → an
     internal KB-gap ticket gets auto-created.
  2. Frontline → Tickets → open that ticket (Customer column will show
     `—`).
  3. Type a reply → **Expected:** Send button reads *"No recipient"*
     and is disabled with tooltip *"This is an internal knowledge-gap
     ticket with no customer to reply to. Add an internal note or
     resolve it instead."*
  4. Contrast: open a normal ticket with a customer → Send Reply
     works as before.

- [ ] 🎯 **FRONTLINE-BUG-07 — Outdated docs in Q&A dropdown**
  1. Frontline → Documents → any doc → **⋯** → **Mark outdated**.
  2. Frontline → Knowledge Q&A → click **Add document…** dropdown.
  3. **Expected:** the outdated doc appears with `⚠️ outdated` badge,
     greyed out and unselectable.

- [ ] 🔒 **FRONTLINE-BUG-08 — Analytics date bounds**
  1. Frontline → Analytics → From/To date inputs.
  2. Try to type a future date → the calendar picker refuses (max =
     today).
  3. Set From = `2026-08-15`, then open the To picker → dates before
     the 15th are greyed out.
  4. Repeat on **Tickets tab** filters and **AI Graphs** From/To.

- [ ] 🔒 **FRONTLINE-BUG-09 — Allowed origins sanitisation**
  1. Frontline → Chat Widget Config → **Allowed origins** →
     paste: `https://example.com, , https://app.example.com,`
  2. Save.
  3. **Expected:** saves as `https://example.com, https://app.example.com`
     (spaces trimmed, empty entries dropped, trailing comma gone).
  4. Try invalid: `not a url, https://foo.com` → rejected with
     *"These allowed_origins entries are not valid scheme://host[:port]
     URLs: 'not a url'"*.

- [ ] 🧠 **FRONTLINE-BUG-10 — Analytics doesn't confuse docs with tickets**
  1. Frontline → Analytics → **Ask a question** box.
  2. Ask: *"How many documents exist?"*
  3. **Expected:** answer references the actual document count (from
     `total_documents`), NOT the ticket count. Should also mention
     whether any are outdated if applicable.
  4. Ask *"How many tickets do we have?"* → still gives the ticket
     count correctly.
  5. Ask *"Any documents outdated?"* → answers from `outdated_documents`.

- [ ] 🎯 **FRONTLINE-BUG-11 — Choose File button visibility**
  1. Frontline → Documents tab → **Upload Document** button → modal
     opens.
  2. **Expected:** the *Choose File* button is clearly visible against
     the dark modal (previously it was dark grey on dark grey).

### 2b. Cross-cutting for Frontline

- [ ] 🎯 **UX-13 for Frontline — Chat delete confirms**
  1. Frontline → Knowledge Q&A → trash a past chat → confirm dialog.
  2. Bottom-right floating HR/Frontline chat → history → delete one
     entry → confirm dialog.
  3. Floating chat → "clear conversation" → confirm dialog.

- [ ] 🎯 **UX-11 for Frontline** — already validated in PM 1d.

### 2c. Cross-agent patterns applied to Frontline / Marketing / Ops

- [ ] 🎯 **MKT-03 pattern — Marketing uploader visibility**
  1. Marketing → any campaign → **Manage** → **Add campaign leads**.
  2. **Expected:** Choose File button clearly visible on the dark
     modal (matches Frontline BUG-11 fix). Same in Sequence
     Management + Campaign Detail Add-Leads flows.

- [ ] 🎯 **OPS-01 pattern — Friendly upload error**
  1. Operations → Documents → Upload Document → pick a truly broken
     file (e.g. a zero-byte file renamed to `.pdf`, or a `.pdf` that's
     actually a random blob).
  2. **Expected:** friendly toast: *"Something went wrong while
     processing this file. Please try a different file, or contact
     support if it keeps happening."* No stack-trace / no `str(e)`
     leak in the browser.
  3. Same test on Frontline → Documents → Upload → same message.

---

## 3. HR Agent

### 3a. Explicit HR bugs

- [ ] 🎯 **HR-BUG-01 — Styled Deactivate / Anonymize modal**
  1. HR → Employees → click any employee → drawer opens.
  2. Click **Anonymize**.
  3. **Expected:** styled dialog (dark, red-accented) instead of
     browser `alert()`. Shows the employee's tag, warning text, a
     **Reason (audit log)** textarea, and Cancel / **Anonymize
     permanently** buttons.
  4. Same flow for **Deactivate** — different copy, different button
     colour, same styled layout.
  5. Provide a reason → confirm → toast success → drawer reloads.

- [ ] 🎯 **HR-BUG-02 — Review Cycles date pickers visible**
  1. HR → Employees → **⋯** → **Review Cycles** → dialog opens →
     scroll to the "New cycle" panel.
  2. **Expected:** all four date inputs (Period start / Period end /
     Self-review due / Manager-review due) show legible text in dark
     mode. Try clicking one → calendar picker appears with text
     visible.
  3. Period-start picker refuses dates before today. Period-end can't
     be earlier than Period start.

- [ ] 🎯 **HR-BUG-03 — Adjust Leave Balance Apply works**
  (Already worked — sanity check.)
  1. HR → Employees → click employee → **Leave balances** → **Adjust**.
  2. Set a value → click **Apply**.
  3. **Expected:** the row updates, dialog closes, toast success.

- [ ] 🔒 **HR-BUG-04 — Compensation numeric validation**
  1. HR → Employees → any employee → **Compensation History** →
     **Add**.
  2. Base salary = `-1000` → *"Base salary must be a non-negative
     number"*.
  3. Bonus target % = `-987` → *"Bonus target must be between 0 and
     100"*.
  4. Equity grant value = `-56` → *"Equity grant value must be
     non-negative"*.
  5. Fix all → Save succeeds. Backend also rejects any of these if a
     rogue client bypasses the frontend.

- [ ] 🔒 **HR-BUG-05 — Add Goal validation**
  1. HR → Employees → any employee → **Goals & OKRs** → **Add goal**.
  2. Weight % = `-45` → *"Weight % must be between 0 and 100"*.
  3. Progress % = `-12` → *"Progress % must be between 0 and 100"*.
  4. Due date picker → try to select a past date → greyed out.
  5. Manually type `08/07/2333` → server rejects with *"due_date is
     too far in the future (max ~5 years)"*.

- [ ] 🧠 **HR-BUG-06 — Meeting Scheduler preserves participants**
  1. HR → Meeting Scheduler → new chat.
  2. Send: *"Schedule a meeting with Ali and Bilal"* (use two real
     employee names from your tenant).
  3. Scheduler responds asking for a time.
  4. Send: *"Make it tomorrow at 3pm"* (no names).
  5. **Expected:** the meeting gets scheduled WITH Ali + Bilal, not
     with an empty participant list. Backend log will show
     `HR-BUG-06 fallback resolved 2 participant(s) from history…`.
  6. Sanity check: send *"Actually only with Ali"* — should now
     schedule with only Ali (current-turn names still win).

- [ ] 🧠 **HR-BUG-07 — Relative weekday parsing**
  1. HR → Meeting Scheduler → *"Schedule 1:1 with Ali next Friday at
     4pm"*.
  2. **Expected:** meeting date is the Friday **following** the
     current week (not the same-week Friday, not the wrong Friday
     entirely).
  3. Try *"tomorrow at 3pm"* → resolves to today+1.
  4. Try *"in 2 weeks"* → resolves to today+14.
  5. Backend log shows `HR-BUG-07 corrected LLM date X → Y` whenever
     the deterministic parse disagreed with what the LLM produced.

### 3b. Cross-cutting for HR

- [ ] 🎯 **UX-13 for HR — Chat delete confirms**
  1. HR → Meeting Scheduler → trash a past chat in the sidebar →
     confirm dialog.
  2. Bottom-right HR floating chat → history → delete one entry →
     confirm dialog.

### 3c. Cross-agent patterns applied to HR

- [ ] 🎯 **EXEC-BUG-02 pattern for HR** — already covered by HR-02
  (Review Cycles) and HR-05 (Goal due dates). Compensation
  `effective_date` deliberately still accepts past dates (backdated
  raises).

- [ ] 🎯 **EXEC-BUG-03 pattern for HR**
  1. HR → **Knowledge Q&A** (Ask HR) → type a question → send.
  2. While spinner is running, try typing more in the textarea →
     **disabled**.
  3. Repeat on **Meeting Scheduler** — textarea disabled during send.
  4. Sanity: HR **Floating chat** was already correct.

- [ ] 🧠 **REC-BUG-01 pattern for HR**
  Hardest to verify manually — background check:
  1. Have an HR document long enough to exceed 2000 chars in a single
     retrieved chunk.
  2. Ask a question that pulls that chunk into context.
  3. **Expected:** in the raw prompt (visible in backend LLM debug
     logs if enabled), the truncated chunk now ends with
     *"[…truncated for length — N more characters not shown. Ask a
     more specific follow-up if the answer needs the rest.]"*
  4. The LLM's response should reflect this — e.g. it may say "based
     on the snippet, X — for the rest you'll need to check the full
     document" rather than confidently making up the missing tail.

---

## Skipped bugs (need product decisions)

These are documented in [AGENT_BUGS.md](AGENT_BUGS.md) with clarification
blocks. Nothing to test until a decision is made.

- **UX-10** — Unsaved-changes warning (scope: which forms count?
  Behaviour: modal vs draft-preserve?).
- **UX-18** — AI stop button (needs streaming or cancel-endpoint
  architecture; nothing streams today).
- **MKT-06 for PM** — Pilot claims false actions (3 fix strategies —
  regex post-process vs 2nd LLM call vs banner).
- **FRONTLINE-BUG-05** — Q&A can't list documents (tool-use LLM
  refactor vs UI-panel workaround).
- **FRONTLINE-BUG-12** — Save Prompt on failed generation (needs
  repro of the specific empty-response shape).
- **REC-BUG-01 for Frontline** — Token-budget-aware truncation
  refactor (needs token-count strategy decision).
- **MKT-04 for HR** — Scope guard on Ask HR (hard-scope vs
  retrieval-confidence gate).

---

## Suggested test order (most likely to catch a regression)

1. **Crashes first** — PM BUG-04 (Pilot), Frontline BUG-01 + BUG-02
   (hand-off panel), BUG-09 (auth loop).
2. **Data-loss-adjacent** — PM BUG-01 (duplicate), BUG-06 (task/project
   window), HR BUG-06 (participants), HR BUG-07 (dates).
3. **Validation** — all the input-rule bugs at once (PM 02/07, HR
   04/05, Frontline 04/08/09).
4. **UX polish** — the dark-mode / confirm / gating fixes.
5. **LLM guardrails** — PM 05 (Q&A scope), Frontline 03 (public chat
   fallback), Frontline 10 (docs vs tickets).

Time budget for a full sweep: **~60-90 min** if you already have test
data set up.

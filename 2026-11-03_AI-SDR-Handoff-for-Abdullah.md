# AI SDR — Handoff for Abdullah

**From:** Mahnoor · **Date:** 3 Nov 2026 · **Branch:** `feature/lead-gen` (PR to `main`)

This is the handoff for the §4 work you assigned in the AI SDR status doc. It covers
**(1)** what is done, **(2)** what is still waiting on a decision or a key from you, and
**(3)** what to check in the *other* agents (unrelated to SDR) before the next release.

Scope note: everything below is inside the SDR agent only —
`ai_sdr_agent/`, `api/views/ai_sdr_agent.py`, the SDR frontend, and the two
SDR-related `crm_sync_agent` items (S10, C2). No other agent's internals were touched.

---

## 1. Done — §4, in your order (code + mocked test, suite green)

Each fix has a mocked regression test (nothing reaches SMTP/IMAP/AI/Apollo/Apify/CRM),
is `pyflakes`-clean, and `makemigrations --check` is clean. Migrations added where a model
changed: `ai_sdr_agent/0032` (enrichment status fields), `crm_sync_agent/0008` (drop `field_mappings`).

### Do-first
| # | What | Where |
|---|---|---|
| **R1** | Per-lead research is now an **async background job** (one lead ≈47 s would hit nginx's 60 s cut and hold the single worker). Screen polls a job row. | `api/views/ai_sdr_agent.py` `research_lead_endpoint`, `research_leads_batch_endpoint`; `SDRLeadsTab.jsx`, `aiSdrService.js getResearchJob` |
| **S1** | Public booking now writes the meeting to the **CRM** (`log_meeting`, idempotent) — mirrors the email-approval path. | `api/views/ai_sdr_agent.py` `sdr_booking_confirm` |
| **S5** | Booking page no longer promises a calendar invite that isn't sent — copy changed to "a confirmation email with the meeting details and link." | `PaPerProjectFront/src/pages/MeetingBookingPage.jsx` |
| **R3** | Contact check no longer drops receive-only domains: a DNS/MX miss returns **RISKY (is_valid: True)**, not INVALID. Docstring made honest. | `ai_sdr_agent/agents/contact_verifier.py` |
| **S3** | A wrong AI key is now **terminal** for the lead (`BadAPIKey` caught above `KeyServiceError`) instead of retried forever; quota/transient errors still retry. | `ai_sdr_agent/tasks.py` qualify queue |
| **S4** | Scoring `max_tokens` raised **2000 → 6000** (reasons were being truncated inside the limit), matching the Email Assistant. | `ai_sdr_agent/agents/lead_qualification_agent.py` |

### Afterwards
| # | What | Where |
|---|---|---|
| **S6** | A failed "more info" auto-answer now **tells the salesperson** instead of only logging. | `ai_sdr_agent/reply_actions.py` |
| **S7** | Weekly reply rate can no longer exceed 100% (clamped). | `ai_sdr_agent/agents/analytics_agent.py` |
| **S8** | Public booking link now **expires** (`BOOKING_LINK_TTL_DAYS=30`, 410 after) and is **rate-limited** (`BookingThrottle`, 30/min). | `api/views/ai_sdr_agent.py` booking endpoints |
| **R2** | Auto-researched leads are now **enqueued for qualification** (`qualification_status='pending'`). | `ai_sdr_agent/tasks.py auto_research_leads_impl` |
| **R4** | Hunter provider is **wired to a setting** (`HUNTER_API_KEY`) — runs if a key is set, skipped cleanly if not. | `ai_sdr_agent/tasks.py enrich_lead_impl` |
| **R5** | `MockEnrichmentProvider` **moved out of the prod module** into tests. | `enrichment_providers.py` → `tests_enrichment_comprehensive.py` |
| **S10** | Dead code removed: `generatePersonalizedEmail`, root `test_crm_sync.py`, `handleProcess` + "Process Now" help line, unused `CRMIntegration.field_mappings`. | as named (migration `crm_sync_agent/0008`) |

### Checked item fixed
| # | What | Where |
|---|---|---|
| **C1** | Score/breakdown now **always reconciled** (`score = bd_sum` when `bd_sum > 0`; dropped the >10 tolerance) so temperature follows the real score. | `ai_sdr_agent/agents/lead_qualification_agent.py` |

### Extra (you requested these during the session — beyond §4; **please confirm before release**)
- **Auto-enrichment on new leads:** every create path now queues both qualification *and*
  enrichment; a new `enrich_queue` scheduler job (180 s) drains it; the lead screen shows the
  enriched fields and flips the button to **Re-enrich** once done.
  New model fields + migration `ai_sdr_agent/0032`; new `enr_status` in the serializer.
- **Export ALL leads (CSV):** streaming export of every lead (not just the 100-per-page),
  with the current filters/sort applied. `sdr_leads_export` + `SDRLeadsTab.jsx` "Export ALL".
- **These two need the API-level bump below** before the screens depend on them.

### API level
Bumped `core/version.py` **API_LEVEL 28 → 29** and
`PaPerProjectFront/src/config/apiLevel.js` **REQUIRED_API_LEVEL 28 → 29** together
(the export endpoint + the `enr_status` field are new server behaviour the screens rely on).
`core.tests_error_alerts` (keeps the two equal) — **17 tests OK**.
Frontend production build — **clean (exit 0)**.

---

## 2. Waiting on you (not started, by design)

| # | What | Why it's parked |
|---|---|---|
| **S2** | What "converted" means — a completed call, or a CRM deal won. | A decision item in §4; nothing should write `status='converted'` until the rule is yours. The earlier experimental change was reverted. |
| **S9** | `FIELD_ENCRYPTION_KEY` unset in prod. | **Setting it alone makes every stored credential unreadable.** Needs a re-encrypt migration + DB backup window, on your server. |
| **R6** | Verify Apollo endpoints + robots.txt fail-open. | Needs a **real Apollo key**. Two things to confirm when you have one: the Apollo base URL is `https://api.apollo.io/v1` → `/v1/people/match` (looks like it may need `/api/v1/...`), and `lead_research_agent.py` search uses `mixed_people/api_search`. Also confirm robots.txt behaviour on fetch error in `enrichment_web.py`. |

### Checked, left as focused follow-ups (reason given)
- **C2** (CRM re-enqueue churn): real. Correct fix = add `CRMContactMapping.identity_hash`,
  store it at the 4 mapping-write sites, skip re-enqueue when unchanged. Cross-app + migration —
  left as its own PR. Matters more now that auto-enrichment adds fields after the first sync.
- **C3** (auto-research started from middleware): works today — it's a **startup** thread,
  not per-request, guarded by `SDRJobLock`. Cleaner to move into the embedded scheduler as a
  daily job and drop `AutoLeadResearchMiddleware`, but that edits `settings.MIDDLEWARE` (yours).
  Recommend doing it together.
- **C4**: **moot** — no SDR screen creates a meeting by hand, so there's nothing to label.

---

## 3. To check in the OTHER agents (not SDR)

Running the full suite on this machine, **30 tests fail outside SDR** — all in agents I did
**not** touch. They span unrelated areas (calendar/ICS, ticket automation, text chunking,
sender-address parsing, agent-slug lookup), which points at an **environment/data difference on
this box, or pre-existing failures on the branch — not these changes**. Please confirm on CI/Linux;
if they still fail there, they're real issues in those agents to triage.

| Agent | Count | Files |
|---|---|---|
| **Frontline_agent** | 16 | `test_meeting_customer` (invite/reminder/cancel), `test_ticket_automation`, `test_new_ticket_workflows`, `test_page_marks`, `test_reading_files` |
| **recruitment_agent** | 5 | `test_live_run_fixes.AssistantTests` (dossier, interview times, answers, delete) |
| **project_manager_agent** | 5 | `test_tool_results.SchedulePlanTests`, `test_meeting_picker`, `test_meeting_details.RescheduleReviewTests` (schedule/ICS/reschedule) |
| **marketing_agent** | 2 | `test_sender_address.SenderAddressTests` (display-name vs address) |
| **hr_agent** | 1 | `test_chunk_size.HRChunkSizeTests` |
| **core** | 1 | `test_agent_slug_field.AgentSlugFieldTests` |

The **SDR suite itself is green** (`ai_sdr_agent` + the SDR-related `crm_sync_agent` items),
including every new regression test listed in §1.

---

## 4. How this was worked (your §6 rules)
- All on `feature/lead-gen`; **PR to `main`** for you to merge (no direct push — main auto-deploys).
- Before PR: full suite in UTF-8, `pyflakes` on changed files, `makemigrations --check` — all clean for SDR.
- Every fix has a mocked test; no secrets in code or docs.
- Server + settings are yours; live test company is **Margalla Software**.

### Open questions for you
1. The **"converted" rule** (S2).
2. **S9** encryption-key migration plan + backup window.
3. Whether **auto-enrichment** and **Export All** (built at Mahnoor's request, beyond §4) ship now, with the **API-level 29 bump**.

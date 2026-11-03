# AI SDR Platform — Complete Technical, Integration & Reliability Audit

**Date:** 2026-11-03
**Auditor:** Independent technical audit (read-only; no code modified)
**Scope:** The 7-agent AI Sales Development Rep platform inside this Django monorepo.
**Product objective under test:** *Keep the sales pipeline full by prospecting, qualifying, engaging leads, and booking meetings.*

**Method.** Each agent's execution path was traced from trigger → backend logic → persistence → API → frontend, with `file:line` evidence. Findings are explicitly tagged **[CODE-REVIEWED]** (logic traced statically) or **[VERIFIED]** (I executed it / queried the live DB) or **[NEEDS-RUNTIME-CHECK]** (cannot confirm without live external services). Where I ran something, the exact command/result is given in §4. I did **not** fabricate results; untested items say so.

> **Codebase note.** This repo hosts several unrelated products (Project Manager, HR, Frontline, Exec Meeting, Recruitment, Marketing). `AGENT_BUGS.md` and most `*_UX_REDESIGN.md` files concern **those** products and are **out of scope**. The SDR platform is: `ai_sdr_agent/`, `crm_sync_agent/`, parts of `marketing_agent/`, `reply_draft_agent/`, `api/views/ai_sdr_agent.py`, `api/views/crm_sync_agent.py`, and `PaPerProjectFront/src/components/ai-sdr/`.

**Authorship (contributions evaluated equally).** Per `git log`: **Ameer Hamza** — Lead Research/Enrichment; **Noor Fatima** — Lead Qualification/Scoring; **M-Abdullah-Iftikhar** (primary, ~82 commits) — Outreach, Meeting Scheduling, CRM Sync, Email Assistant, Analytics. Quality is high and consistent across both developers' areas; the weaknesses below are distributed across all of them and are mostly *integration seams* and *unverified live execution*, not bad code.

---

## 0. Resolved since initial audit (2026-11-03)

Found and fixed after the initial audit. All changes verified; the `ai_sdr_agent` suite remains green at **420/420** (0 failures, 0 errors).

| Item | What was done | Verification |
|---|---|---|
| ✅ **P0-1 — ICP save fails** (`NOT NULL constraint … seniority_weights`) | Reconciled the DB to the shipping code: dropped the orphan `seniority_weights` column + its stale `django_migrations` record, and applied the pending `0031_campaign_inbox_error` migration (which also fixes a latent `no such column: sdr_campaign.inbox_error` crash on inbox-read failure). Backup at `db.sqlite3.bak-audit-2026-11-03`. | Live `update_or_create` INSERT succeeds; `migrate --check` clean; suite 420/420. |
| ✅ **Lead-generate endpoint was synchronous** (blocked large runs) | Converted `research_leads` (POST `/sdr/leads/research/`) to an **async background job**: returns `job_id` immediately, runs discovery in a daemon thread writing progress to `SDRLeadResearchJob`, polled via new `GET /sdr/leads/research/jobs/<id>/`. Frontend polls with a live progress counter and handles failed/approval states. A synchronous pre-flight keeps "no API key" an instant error. | Routes resolve; async-contract tests updated; suite 420/420. |
| ✅ **Frontend dropped `icp_id`** on generate (§2.1) | `researchLeads()` now forwards `icp_id`, so a non-active ICP selection is honored. | Code-reviewed; wired through the generate modal. |
| ✅ **Lead-generate slider cap** 50 → 1500 | Raised the frontend slider max and the backend `count` cap (`api/views/ai_sdr_agent.py:636`). | — |

**Still open (not touched this session):** P1-1 (Apify free-plan discovery), P1-2 (Celery topology), **P1-3** (the **per-lead** `research_lead_endpoint` / `research_leads_batch_endpoint` at `:858–894` are still synchronous — the same async pattern now used in `research_leads` can be applied), and all P2/P3 items. See §5.

---

## 1. Executive Summary

The platform is **architecturally complete and genuinely substantial**. All seven agents exist as real implementations wired to real external services — SMTP (`smtplib`), IMAP (`imaplib`), Groq LLM, Apollo/Apify/Hunter, HubSpot/Salesforce/Pipedrive REST APIs, and Google Calendar/Meet. It has strong cross-process locking (`SDRJobLock`), consistent per-company data isolation, Fernet-encrypted credentials, honest (non-faked) analytics, and an extensive **495-method test suite that I ran to a 100% pass (420 SDR + 75 CRM, 0 failures)** — though those tests mock all external boundaries.

**However, it is not production-ready, and the back half of the funnel is unproven.** The live database shows the pipeline has only ever been exercised through **research → qualification** (268 scored leads) — there are **0 campaigns, 0 enrollments, 0 outreach emails, 0 replies, 0 meetings, and 0 CRM integrations** on record. Several cross-agent hand-offs are missing or broken, automated lead discovery fails under the configured Apify plan, and the async execution topology is split in a fragile way (SDR on an embedded scheduler; CRM/marketing/reply-draft on Celery that the SDR design explicitly disclaims).

### Health scorecard (feature-level, across all 7 agents)

| Status | Count (approx.) | Examples |
|---|---|---|
| **Fully Functional** | ~34 | Rule-based scoring, real SMTP/IMAP send+poll, reply classification, double-send prevention, CRM connectors, real slot generation, honest analytics aggregation, org isolation |
| **Partially Functional** | ~20 | AI scoring (silent truncation fallback), Apollo search/enrich URLs, email MX check, weekly reply-rate math, denormalized campaign counters, timezone labeling, Google invite promise |
| **Broken** | ~6 | Automated Apify discovery (external plan), public-booking→CRM sync, auto-research→qualify hand-off, meeting-complete→`converted` hand-off, `send_info` false-success, marketing reply sub-sequence race |
| **Missing** | ~8 | Auto-enroll of qualified leads, SDR open/click tracking, re-qualify after enrichment, company-wide analytics roll-up, lead-discovery fallback, booking-token expiry |
| **Not Verified (live)** | all of stages 4–8 | Enroll→send→reply→meeting→CRM never executed end-to-end on real data |

### Critical blockers to the AI SDR workflow

1. **[P1] Automated prospecting does not work in the delivered configuration.** 9 of 11 lead-research jobs on record failed; the configured Apify actor times out, needs manual permission approval, and **the free Apify plan forbids API-triggered runs entirely**. Only manual CSV import and "fetch from an Apify UI run" actually populate leads. The top of the funnel — the product's headline promise — is effectively manual.
2. **[P1] Async topology fragility.** CRM sync, marketing sends, and reply-draft inbox sync drain **only** via a running Celery **worker + beat** (SQLite broker), while SDR runs on an in-process APScheduler advertised as "no Celery needed." If a deployment runs only the web/SDR process, CRM never syncs and the reply-draft inbox never populates — silently.
3. **[P1] Synchronous research endpoints.** `research_lead`/`research_leads_batch` run the multi-minute crawl+search+LLM workflow inline in the HTTP request (batch up to 50 leads), risking gateway timeouts and worker starvation.
4. **[P2] The funnel never closes.** `SDRLead.status='converted'` is defined and read by the analytics funnel but **never written anywhere** — "Converted" is permanently 0. And the **primary** (self-serve) booking path never pushes the meeting to CRM.
5. **[P2] Qualification reliability traps.** An invalid LLM key is misclassified as "tokens exhausted" and retried forever; AI responses can silently truncate to rule-based scores with no signal.

### Overall platform health: **Functionally Complete but Needs Hardening** — *not* production-ready. (Full justification in §7.)

---

## 2. Agent-by-Agent Audit

Status legend: **Fully Functional / Partially Functional / Broken / Missing / Not Verified.**

### 2.1 Lead Research & Enrichment Agent  *(Ameer Hamza)*

Files: `ai_sdr_agent/agents/lead_research_agent.py`, `lead_research_workflow.py`, `lead_research_tools.py`, `lead_research_verification.py`, `enrichment_*.py`, `contact_verifier.py`, `lead_validator.py`.

| Functionality | Status | Evidence | Problem | Required Fix |
|---|---|---|---|---|
| Lead discovery — Apify (auto) | **Broken** (external) | 9/11 jobs failed in DB (§4); `lead_research_agent.py:620-733` | Free Apify plan forbids API runs; actor times out / needs approval | Document paid-plan requirement; add import fallback as the primary path |
| Lead discovery — Apollo search | Partially Functional | `lead_research_agent.py:513-571` | Endpoint `mixed_people/api_search` is non-standard | Verify vs Apollo docs with a live key |
| Import leads from existing Apify run | Fully Functional | `lead_research_agent.py:735-806` | — | — |
| Company website crawl (SSRF-safe) | Fully Functional | `lead_research_tools.py:129-346` | depends on `curl.exe` on PATH for anti-bot fallback | confirm curl present on worker |
| Grounded Groq synthesis + deterministic fallback | Fully Functional | `lead_research_workflow.py:396-498` | — | — |
| Deterministic verification (identity/role/grounding) | Fully Functional | `lead_research_verification.py` (well unit-tested) | — | — |
| Research persistence onto `SDRLead` | Fully Functional | `lead_research_agent.py:347-411` | writes `buying_signals/recent_news/seniority/company_industry` → consumed by qualification | — |
| Enrichment waterfall (Apollo→Hunter→web), non-destructive merge | Fully Functional | `enrichment_waterfall.py`, `enrichment_contract.py:189-293` | — | — |
| Apollo **enrichment** provider | Broken (suspected) | `enrichment_providers.py:78` | base_url `/v1/people/match` likely missing `/api/`; error swallowed → silent `{}` | fix URL; verify live |
| Email domain verification | Partially Functional | `contact_verifier.py:61-89` | uses A-record (`getaddrinfo`) not MX → valid MX-only domains marked INVALID and email dropped (`enrichment_validator.py:206`) | query MX, or treat A-absence as RISKY |
| robots.txt compliance | Partially Functional | `enrichment_web.py:107-136` | fails **open** on fetch error (`:124-126`) | fail closed / cap to homepage |
| Auto-research → qualification hand-off | **Broken** | `tasks.py:624-646` vs `:896-900` | auto-created leads get `qualification_status='none'`; queue only picks `pending/failed/processing` → never scored | set `pending` + `queued_at` on create |
| Research endpoints async | ⚠️ **Partially resolved** | `api/views/ai_sdr_agent.py:858-860,894-899` | discovery/generate (`research_leads`) now async (§0); **per-lead** research/enrich batch endpoints still synchronous | apply the same background-job pattern to the per-lead endpoints |
| Re-qualify after research/enrich | Missing | (no caller) | new signals/contacts don't re-score existing leads | enqueue re-qualification on change |

**Placeholders/mocks:** `MockEnrichmentProvider` shipped in a prod module (`enrichment_providers.py:340-379`); placeholder bot-info URL (`enrichment_web.py:45`); hardcoded Groq model & default Apify actor; Hunter score fallback `or 60`; Apollo-enrich 429 swallowed and mis-reported as `not_found`; several silent `except…pass`.
**Tests:** `tests_research.py` (112), `tests_enrichment_comprehensive.py` (16), `tests_enrichment_phase1.py` (6) — thorough, fully mocked at provider boundaries.

### 2.2 Lead Qualification & Scoring Agent  *(Noor Fatima)*

File: `ai_sdr_agent/agents/lead_qualification_agent.py` (+ `lead_validator.py`, `sdr_key_resolver.py`).

| Functionality | Status | Evidence | Problem | Required Fix |
|---|---|---|---|---|
| Rule-based scoring (5-category, 0–100) | **Fully Functional** **[VERIFIED]** | `:221-344`; re-ran live, matched stored 75/hot (§4) | — | — |
| AI (Groq) scoring | Partially Functional | `:92-215` | `max_tokens=2000` on a "thinking" model can truncate JSON → silent rule fallback; breakdown ints not float-tolerant (`:192-196`) | raise/measure token budget; tolerate floats |
| Score ↔ breakdown consistency | Partially Functional | `:198-205` | reconciled only if `abs>10`; within 10 they can disagree and temperature follows the un-reconciled score | reconcile always; derive temp from final |
| Temperature (ICP thresholds) | Fully Functional | `:346-352` | crashes if `icp is None` (see register) | guard None |
| Single / bulk / background-queue qualify | Fully Functional | `api/views/ai_sdr_agent.py:537-599`, `tasks.py:884-998` | fair multi-tenant batching | — |
| Auto-qualify on lead creation | Partially Functional | enqueued on manual/CSV/API (`:479,774,1111,1263`) but **not** on auto-research (`tasks.py:624`) | auto-research leads never scored | queue them too |
| LLM key resolution & usage metering | Fully Functional | `sdr_key_resolver.py:68-95` | bad-key path mislabeled (register B6) | treat `BadAPIKey` as terminal |
| `outreach_strategy`/`key_strengths`/`concerns` | Partially Functional | written `:207-215`; read only in UI `SDRLeadsTab.jsx:1459-1505` | **display-only** — outreach agent consumes none | wire into outreach or document |
| Unit tests of scoring math | **Missing** | only a smoke test asserting keys exist (`tests_research.py:422-439`) | no test of `_ai_qualify`, reconciliation, rule values, `_score_to_temp` | add unit tests |

**Scoring-quality observations [VERIFIED via DB]:** 268 leads scored; breakdown always sums to the stored score; **no lead scores above 75** and a gap exists at 71–74; a "hot" (75) lead can have `business_fit=10/25` — i.e. **"hot" does not require ICP industry fit** (company_quality+contact+completeness alone can reach ~60). Worth a product review of weighting.
**Hardcoded:** model `'openai/gpt-oss-20b'`, `max_tokens=2000`, `temperature=0.1`; inconsistent size sentinels `99999` vs `999_999`.

### 2.3 Outreach & Campaign Agent  *(M-Abdullah-Iftikhar)*

Files: `ai_sdr_agent/agents/outreach_agent.py`, `tasks.py`, `scheduler.py`; `marketing_agent/*` (parallel engine).

| Functionality | Status | Evidence | Problem | Required Fix |
|---|---|---|---|---|
| SDR email send (real SMTP) | Fully Functional | `outreach_agent.py:906,953-1010` | dead unreachable Django-`send_mail` fallback (`:931-951`) | remove dead code |
| Lead segmentation → enrollment | Partially Functional / **Missing (auto)** | `api/views/ai_sdr_agent.py:2148-2267` | enrollment is **manual** (UI `lead_ids`); no auto-enroll of qualified/hot leads | add auto-enroll if product wants it |
| Follow-up scheduling / next-step timing | Fully Functional | `outreach_agent.py:1342-1357` | `next_action_at = max(enrolled+delay, now+gap)` | — |
| Double-send / race prevention (SDR) | Fully Functional | `SDRJobLock` + 4 guards + atomic step-claim (`outreach_agent.py:1096-1181`) | — | — |
| Double-send prevention (marketing reply sub-seq) | **Broken** | `send_sequence_emails.py:218-305` | no DB claim; host-local **fail-open** file lock → cross-host double-send | add atomic claim; DB/Redis lock |
| Unsubscribe / do-not-email | Fully Functional | `outreach_agent.py:233-357`; shared `core/do_not_email.py` | company-wide, cross-engine, List-Unsubscribe header | — |
| Bounce detection → suppression | Fully Functional | `outreach_agent.py:376-409` | — | — |
| Email open/click tracking (SDR) | **Missing** | no pixel/link-wrap in `ai_sdr_agent` | SDR never measures opens/clicks (analytics is reply-based) | add if required |
| Email open/click tracking (marketing) | Partially Functional | `email_service.py:666-805` | real pixel/links, but URL falls back to `127.0.0.1:8000` if `SITE_URL` unset → 0% recorded silently | require public base URL |
| Reply detection stops sequence | Fully Functional | `reply_actions.py:49-246` | — | — |
| Auto-start / auto-complete campaigns | Fully Functional | `tasks.py:345-404` | — | — |
| Manual "Process outreach" | Partially Functional | `api/views/ai_sdr_agent.py:2365-2435` | defaults `force=True` → sends next step to **all** enrollments ignoring `next_action_at` | default `force=False` / confirm in UI |

**Not verified live:** 0 campaigns / enrollments / outreach logs in the DB — the entire send/reply loop has never run on real data here (it is, however, heavily unit-tested with mocked SMTP/IMAP).

### 2.4 Meeting Scheduling Agent  *(M-Abdullah-Iftikhar)*

Files: `ai_sdr_agent/agents/meeting_scheduling_agent.py`, `views_booking.py`, `api/views/ai_sdr_agent.py` (booking), `core/google_calendar.py`.

| Functionality | Status | Evidence | Problem | Required Fix |
|---|---|---|---|---|
| Meeting-intent detection from reply | Fully Functional | `email_assistant_agent.py:181-228`; `reply_actions.py:197-235` | AI-first + keyword fallback | — |
| Auto-create meeting on positive reply | Fully Functional | `reply_actions.py:197-235` | per-person open-meeting dedupe | — |
| Real free-slot generation (not faked) | Fully Functional | `api/views/ai_sdr_agent.py:3686-3715` | uses shared-calendar busy intervals + other meetings | — |
| Google Calendar / Meet event | Partially Functional | `core/google_calendar.py:110-162` | real, but `sendUpdates='none'` → lead gets **no** calendar invite despite UI promising one (`MeetingBookingPage.jsx:350`) | `sendUpdates='all'` or fix copy |
| Confirmed meeting → CRM sync | **Broken** (primary path) | `api/views/ai_sdr_agent.py:3832-3891` | public `/book` confirm uses `.update()` only → `post_save` never fires → CRM never told (manual + approval paths DO sync) | call `log_meeting(meeting)` after confirm |
| Double-booking prevention | Fully Functional | lock + `ensure_free` + atomic conditional `UPDATE` (`:2547-2573,3805-3853`) | `awaiting_approval` holds the slot | — |
| Timezone handling | Partially Functional | `meeting_scheduling_agent.py:139-177`; `:1166-1168` | instants correct, but label guessed from company location / SDR browser tz; lead's real tz never stored | capture booking-page tz |
| Reminder / confirm / completion / cancel emails | Fully Functional | `tasks.py:407-447`; `:907-1039` | — | — |
| Public booking page token | Partially Functional | `models.py:541`; `:3636-3672` | UUID4 (unguessable) but **never expires**, no rate-limit, leaks lead/company/sender | add expiry/one-time + rate-limit |
| Manual meetings with no campaign | Broken (silent) | `api/views/ai_sdr_agent.py:3867` | get **no** scheduling/confirmation email at all | send via a default sender |

**Not verified live:** 0 `sdr_meeting` rows. **Tests gap:** no test of the public-booking→CRM path (why the P2 above went uncaught), no double-booking race test, no Google-event test.

### 2.5 CRM & System Sync Agent  *(M-Abdullah-Iftikhar)*

Files: `crm_sync_agent/agents/crm_sync_agent.py`, `connectors/{base,hubspot,salesforce,pipedrive}.py`, `signals.py`, `tasks.py`, `models.py`; `api/views/crm_sync_agent.py`.

| Functionality | Status | Evidence | Problem | Required Fix |
|---|---|---|---|---|
| HubSpot / Salesforce / Pipedrive connectors | **Fully Functional** (real APIs) | `hubspot.py:349-381`, `salesforce.py:281-421`, `pipedrive.py:269-302` | genuine HTTP; OAuth/token/engagements/deals/pipelines | — |
| Sync triggers (post_save signals) | Fully Functional | `signals.py:98-276`; registered `apps.py:9-10` | broad per-handler except (logged) | — |
| Durable queue + retry/back-off | Fully Functional | `CRMSyncQueue`; `tasks.py:77-106`; `_backoff_delay` | — | — |
| Idempotency (contact/activity mappings) | Fully Functional | `models.py:136-173,360-377`; `_claim` `:601-614` | item-level claim prevents duplicate sends | — |
| Credential storage / security | Fully Functional | Fernet via `core/crypto_utils.py`; admin-gated; masked egress | key falls back to SECRET_KEY-derived when `FIELD_ENCRYPTION_KEY` unset (hardening gap, see register) | set a dedicated stable key in prod |
| Org / company isolation | Fully Functional | `agents:65-67,563,874-881`; tasks `active_company_ids` | none found | — |
| Deals / pipelines (opt-in) | Fully Functional | `_enqueue_deal/_sync_deal`; API `_apply_deals` | — | — |
| Bidirectional pull (`sync_back`) | Fully Functional | `pull_changes:307-350` | writes via `update()` (no loop) | — |
| Contact re-enqueue churn | Partially Functional | `agents:77-93` + `:957-963` | every lead save re-enqueues (dedups only PENDING/FAILED) → redundant upsert API calls (rate-limit burn) | skip when mapping exists & unchanged |
| `CRMIntegration.field_mappings` | Broken (dead) | stored/serialized but **never read** by any connector | config has no effect | wire in or remove from UI |
| Conflict resolution | Partially Functional | fill-blanks-only outbound; CRM wins on pull | local correction never overwrites non-blank CRM value | document or add local-wins |
| Root `test_crm_sync.py` | Broken | stale signatures (`:140,257`) | misleads QA into thinking sync is broken | fix/delete; use real suite |

**Not configured live:** 0 `crm_integration` rows — connectors are real and extensively unit-tested (6 test files) but never run against a live CRM here. **No P0/P1 inside the agent itself**; its exposures are the Celery-topology dependency (§3) and the booking-path signal gap (§2.4).

### 2.6 Email Assistant Agent  *(M-Abdullah-Iftikhar)*

Files: `ai_sdr_agent/agents/email_assistant_agent.py`, `reply_actions.py`, `reply_answers.py`; `reply_draft_agent/*`.

| Functionality | Status | Evidence | Problem | Required Fix |
|---|---|---|---|---|
| Outbound personalization (LLM, grounded) | Fully Functional | `email_assistant_agent.py:232-288` | only 4 lead fields fed (anti-hallucination design); richer enrichment ignored | optional: pass more fields |
| "Tell me more" follow-up generation | Fully Functional | `:292-371` | no-LLM fallback greeting bug (register) | minor |
| Manual AI Assistant (write/read) | Fully Functional | `:453-517`; `api/views/ai_sdr_agent.py:1900-1945` | — | — |
| Answer fact-check second pass | Fully Functional | `:389-426` | retries, falls back to original | — |
| Reply classification (AI + keyword) | Fully Functional | `:181-228,521-562` | invalid category coerced to neutral | — |
| SDR inbox IMAP polling + reply match | Fully Functional | `outreach_agent.py:671-887`; `tasks.py:250-342` | real IMAP4_SSL, SSRF-guard, Message-ID + INTERNALDATE dedupe | verify live mailbox |
| Reply-draft inbox sync (marketing) | Fully Functional | `sync_inbox.py:302-1068` | **depends on Celery beat+worker** (§3) | confirm deployed |
| Inbox triage (AI) | Fully Functional | `reply_draft_agent/triage.py` | `PER_RUN=25`/mailbox/tick → backlog on busy mailboxes | raise cap / prioritize |
| Reply auto-pauses sequence | Fully Functional | `reply_actions.py:133-246` | — | — |
| Positive reply → meeting scheduling | Fully Functional | `reply_actions.py:197-235` | — | — |
| Draft approval (human-gated) | Fully Functional | `reply_draft_agent.py:457-507` | never auto-sends | — |
| `send_info` failure reporting | **Broken** (silent) | `reply_actions.py:172-195` | send exception swallowed; returns success with `info_email_sent=False`; lead marked replied, sequence stopped, nobody told | surface held/failed state + alert |

**Tests:** very strong — `tests_reply_answers.py` (21), `tests_replies_29_oct.py` (57), `tests_answer_check_30_oct.py` (4), `tests_reply_mailbox.py` (9), `tests_mailbox_refused.py` (10), `reply_draft_agent/tests/*`. All mock the mail/LLM boundary.

### 2.7 Analytics & Dashboard Agent  *(M-Abdullah-Iftikhar)*

Files: `ai_sdr_agent/agents/analytics_agent.py`; `api/views/ai_sdr_agent.py` (`/sdr/analytics/`, `/sdr/dashboard/`).

| Functionality | Status | Evidence | Problem | Required Fix |
|---|---|---|---|---|
| Lead / email / reply / meeting counts (all windows) | Fully Functional | `analytics_agent.py:48-113` | **real ORM aggregation, per-tenant** | — |
| Status / temperature / source / sentiment breakdowns | Fully Functional | `:56-100` | — | — |
| Per-campaign performance table | Partially Functional | `:122-134` | uses **denormalized** `c.emails_sent/meetings_booked` while KPI cards use live counts → can diverge | compute from logs or reconcile |
| Weekly reply rate | Partially Functional | `:137` | replies-this-week / emails-this-week = cohort mismatch; can exceed 100% | document as approximate |
| Meeting rate | Fully Functional | `:140-142` | distinct-enrollment dedupe | — |
| Pipeline funnel | Partially Functional | `:160-167` | `Contacted=max(emailed, replied)` can overstate; final stage `converted` always 0 (never written) | fix converted hand-off (§3) |
| 7-day daily trend | Fully Functional | `:145-155` | — | — |
| Low-meetings alert + daily summary email | Fully Functional | `:172-173,219-461` | gated on `activated_at`; honest `sent` bool | — |
| Frontend tile → backend field mapping | Fully Functional | `SDRAnalyticsTab.jsx:217-461`; `SDROverviewTab.jsx:277-300` | every key exists | — |
| Empty / zero-data states | Fully Functional | `SDRAnalyticsTab.jsx:209-215` | — | — |
| Open-rate / click-rate | **Missing** (not faked) | `SDROutreachLog` has no open/click fields | absent by design in SDR | add tracking if required |
| Company-wide / admin roll-up | **Missing** | all aggregates key on `company_user` | admin sees only own pipeline, not team | add company scope if required |
| Blank-dashboard-on-timezone-error | Partially Functional | `:38-40` (no try/except) | invalid `timezone_name` → whole `compute_metrics` 500s → blank tab | guard tz resolution |

**Headline [VERIFIED by tracing every metric to its query]:** **no faked, randomized, or hardcoded demo metrics anywhere.** Every number is a real DB aggregate with correct per-tenant isolation. (The dashboard currently shows mostly zeros because stages 4–8 have no data yet — that is honest, not broken.)

---

## 3. Integration Issues

The pipeline is **well-wired *within* the SDR app** and individually sound; the failures are concentrated at **app boundaries** and **terminal hand-offs**.

**End-to-end wiring map** (✓ wired / ✗ missing / ◑ manual):

1. Import/research → create `SDRLead` — ✓ (`api/views/ai_sdr_agent.py:461,735,1079,1245`)
2. New lead → qualification queue — ✓ for manual/CSV/API; ✗ for **auto-research** (`tasks.py:624-645` omits `pending`)
3. Queue → score — ✓ (`scheduler.py:135` → `tasks.py:953`)
4. Qualified → enroll in campaign — ◑ **MANUAL ONLY** (no auto-enroll)
5. Enrollment → send outreach — ✓ (`scheduler.py:122` → `outreach_agent.process_enrollment`)
6. Send → CRM email activity — ✓ signal (`crm_sync_agent/signals.py:182`)
7. Inbound reply → classify — ✓ (`scheduler.py:148` → `reply_actions.py:49`)
8. Reply → enrollment/lead state — ✓ (`reply_actions.py:116-246`)
9. Reply recorded → CRM note — ✓ signal (`signals.py:249`)
10. Positive reply → create `SDRMeeting` — ✓ (`reply_actions.py:197-235`)
11. Meeting scheduled → `lead.status='meeting_scheduled'` — ✓
12. Meeting confirmed → CRM — ◑/✗ **public-booking path missing** (`:3832` `.update()` only)
13. Lead/meeting → CRM contact/deal — ✓ signals (`signals.py:98,234`)
14. Meeting completed → `lead.status='converted'` — ✗ **MISSING** (never written; funnel stuck at 0)
15. All stages → analytics — ✓ (read-side)

| # | Integration issue | Sev | Agents | Evidence | Root cause |
|---|---|---|---|---|---|
| I-1 | CRM/marketing/reply-draft drain **only** via Celery worker+beat; SDR runs embedded APScheduler ("no Celery needed"). Split topology → CRM/inbox silently dead if only the web process runs. | **P1** [NEEDS-RUNTIME-CHECK] | CRM, Outreach, Email | beat tasks exist (`crm-process-sync-queue` 120s, etc., **verified**); SDR has **0** beat tasks; `apps.py:35` markets no-Celery | two schedulers, one disclaimed |
| I-2 | Public booking-page confirmation never pushes meeting to CRM (`.update()` bypasses `post_save`). | **P2** | Meeting, CRM | `api/views/ai_sdr_agent.py:3832` vs approval `:3138` | `.update()` skips signal |
| I-3 | `status='converted'` never written → funnel "Converted" permanently 0. | **P2** [VERIFIED: 0 converted] | Meeting, Analytics | enum `models.py:67`; read `analytics_agent.py:166`; no writer | missing terminal hand-off |
| I-4 | Auto-research leads never queued for qualification. | **P2** | Research, Qualification | `tasks.py:624-645` | omitted queueing |
| I-5 | Qualified leads are not auto-enrolled into any campaign; the engage stage requires a human. | **P2** (or by-design) | Qualification, Outreach | `api/views/ai_sdr_agent.py:2148` only | no auto-segment/enroll path |
| I-6 | Per-process `LocMemCache` (verified; `USE_REDIS=False`) used for CRM burst-dedup → redundant runs across workers (item-claim still prevents double-send). | **P2** | CRM | `signals.py:39`; cache backend **verified** LocMem | wrong cache backend for multi-proc |
| I-7 | Frontend `generatePersonalizedEmail` → `/sdr/emails/generate/` has **no route** (dead export; **verified** no caller). | **P3** | Email | `aiSdrService.js:595` | stale export |
| I-8 | `tasks.py` imports `_get_qualification_agent` from the API **view** layer (layering inversion). | **P3** | Qualification | `tasks.py:887` | factory misplaced |

**Org isolation:** consistently enforced; **no cross-company leak found**. Every authenticated SDR/CRM endpoint scopes by `company_user`/`company`; batch endpoints re-scope to owned IDs; public endpoints authorize by unguessable UUID/signed token; background tasks re-check subscription fail-closed.
**Enum/status consistency:** reply-sentiment, meeting-status, enrollment-status, and `qualification_status` vocabularies match across every writer and reader — **except** the orphaned `converted` (I-3).

---

## 4. Test Results

Two categories: **(A) checks I actually executed** against this repo/DB, and **(B) the existing automated suite**. Nothing here is fabricated.

### A. Executed by the auditor — [VERIFIED]

| # | Check | Command / method | Result |
|---|---|---|---|
| A-1 | Django boots & config sane | `manage.py check` | ✅ Passes (only a Stripe-webhook warning). Celery broker=SQLite, `USE_REDIS=False`, CACHE=`LocMemCache`. |
| A-2 | Live pipeline state | sqlite row counts | 268 leads (all `qualified`/`done`); **0** campaigns/steps/enrollments/outreach-logs/reply-drafts/meetings; **0** CRM integrations/mappings/logs; 1 ICP; 11 research jobs. |
| A-3 | Qualification executes correctly | ran `LeadQualificationAgent(company=None).qualify_lead(lead, icp)` on real lead | ✅ "Helen Pearce" re-scored **75/hot**, breakdown sum **75**, matching stored data. Rule-based path works. |
| A-4 | Scoring data integrity | sum(breakdown) vs score for all 268 | ✅ Equal for **all 268**. But **no score >75**, gap at 71–74, and "hot" leads can have `business_fit=10/25` (ICP mismatch). |
| A-5 | Unguarded ICP crash | `qualify_lead(lead, None)` | ⚠️ **Raises `AttributeError: 'NoneType' has no attribute 'industries'`** — confirms register item Q-B4. |
| A-6 | Dict lead / string size | `qualify_lead({... 'company_size':'11-50'}, icp)` | Scored 54, **no crash** but size under-credited — confirms Q-B7. |
| A-7 | Lead-discovery reliability | inspected 11 `sdr_lead_research_job` rows | ⚠️ **9 failed** (Apify timeout / permission-approval / *"free plan: run via UI, not API"* / actor FAILED), 1 completed (19 leads), 2 timed out. Automated discovery effectively non-functional here. |
| A-8 | CRM Celery topology | read `CELERY_BEAT_SCHEDULE` | CRM tasks present (`crm-process-sync-queue`@120s, retry@1800s, ping@3600s, pull@900s); **SDR has 0 beat tasks** → confirms I-1. |
| A-9 | Converted funnel | `count(status='converted')` | **0** — confirms I-3. |
| A-10 | Credential encryption | read `fields.py`, `FIELD_ENCRYPTION_KEY` | Credentials **are** Fernet-encrypted (not plaintext); key falls back to SECRET_KEY-derived when `FIELD_ENCRYPTION_KEY` unset (it is unset here) — hardening gap only. |
| A-11 | Dead frontend route | grep `generatePersonalizedEmail` in `src/` | No caller → confirms I-7 (harmless dead export). |

### B. Existing automated suite

The SDR/CRM test suites are large and mostly hermetic (mock LLM/IMAP/SMTP/CRM at the boundary). **I executed both suites in this environment — results below [VERIFIED]:**

| Suite | Command | Result |
|---|---|---|
| `ai_sdr_agent` | `manage.py test ai_sdr_agent` | ✅ **Ran 420 tests — OK (0 failures, 0 errors)**, 25.6s |
| `crm_sync_agent` | `manage.py test crm_sync_agent` | ✅ **Ran 75 tests — OK (0 failures, 0 errors)**, 5.7s |
| **Total** | | **495 tests, 100% pass** |

**Interpretation (important):** a fully-green 495-test suite is a genuine positive — the agents' internal logic is self-consistent and regression-protected. But these tests **mock the external boundaries** (LLM, IMAP, SMTP, CRM HTTP, calendar). They prove the code behaves correctly *given mocked responses*; they do **not** prove the live integrations work, and — critically — they do **not** cover the broken seams in §3/§5 (the suite is green *because* those paths are untested, not because they work).

**Known coverage gaps (from reading the tests):** no unit test of the qualification scoring math/reconciliation; no test of the public-booking→CRM path (I-2) or double-booking race; no test of the auto-research→qualify gap (I-4), the `send_info` false-success path, the marketing reply-subsequence race, or the localhost tracking-URL fallback. These are exactly the places the bugs hide.

---

## 5. Prioritized Issue Register

**P0 — Critical (workflow-blocking / security / data-integrity):**

| ID | Issue | Agent | Status | Evidence | Root cause |
|---|---|---|---|---|---|
| P0-1 | **ICP save fails** — `NOT NULL constraint failed: sdr_icp_profile.seniority_weights` — blocks all ICP setup (step 0 of the pipeline) | Qualification / infra | **FIXED 2026-11-03** (DB reconciled to code) | reproduced in portal; `fields`/model have no `seniority_weights`; DB column exists NOT NULL | **DB migration-state corruption** from a botched merge of two developers' `0031_*` migrations: `0031_sdricpprofile_seniority_weights` was applied then its source deleted + field removed from model (orphan NOT-NULL column remained); and `0031_campaign_inbox_error` was left **unapplied** (missing `inbox_error` columns → latent crash on inbox-read failure). Fixed by dropping the orphan column + stale migration record and applying the pending migration. A pre-existing broader multi-app migration drift (`showmigrations` lists many unapplied migrations whose tables already exist) remains and should be reviewed before any blanket `migrate`. |

*(Note: this class of bug is invisible to static code review and to the test suite — tests build a fresh, internally-consistent DB from current migrations, so they pass while the real database is the corrupted artifact. Only running against the real DB surfaced it.)*

### P1 — High

| ID | Issue | Agent | Root cause | Evidence | Fix |
|---|---|---|---|---|---|
| P1-1 | **Automated prospecting non-functional** in delivered config | Research | Apify free plan forbids API runs; actor timeouts/approval | §4 A-7; `lead_research_agent.py:620-733` | Require paid Apify plan or make UI-run-import the primary path; surface a clear setup state |
| P1-2 | **Async topology split** — CRM/marketing/reply-draft need Celery worker+beat that SDR disclaims | CRM, Outreach, Email | two schedulers | §4 A-8; `scheduler.py:278-288`, `settings.py` beat | Run & monitor Celery worker+beat in prod, or add a CRM-drain job to the embedded scheduler |
| P1-3 | **Synchronous research endpoints** (batch inline) → timeouts/worker starvation. ⚠️ **Partially resolved** — the discovery/generate endpoint `research_leads` is now async (§0); the **per-lead** `research_lead_endpoint` / `research_leads_batch_endpoint` remain synchronous. | Research | no `.delay` | `api/views/ai_sdr_agent.py:858-860,894-899` | Apply the same background-job pattern now used in `research_leads` |

### P2 — Medium

| ID | Issue | Agent | Evidence | Fix |
|---|---|---|---|---|
| P2-1 | Public-booking confirm never syncs meeting to CRM | Meeting/CRM | `:3832` | call `log_meeting()` after confirm |
| P2-2 | `converted` never written → funnel stuck at 0 | Meeting/Analytics | §4 A-9; `models.py:67` | set `converted` on meeting completion |
| P2-3 | Auto-research leads never qualified | Research/Qualify | `tasks.py:624-645` | enqueue `pending` on create |
| P2-4 | Invalid LLM key retried forever as "tokens exhausted" | Qualify | `tasks.py:968-976`; `BadAPIKey` is a `KeyServiceError` | treat `BadAPIKey` as terminal, fail the lead |
| P2-5 | AI score silently truncates → rule-based with no signal | Qualify | `:165,184` | raise/measure token budget; tag which path scored |
| P2-6 | Score/breakdown can disagree (±10); temp follows raw score | Qualify | `:198-205` | always reconcile |
| P2-7 | ICP `None` crashes the agent | Qualify | §4 A-5 | guard `icp is None` |
| P2-8 | Google event sends no invite but UI promises one; campaign-less meetings send no email | Meeting | `google_calendar.py:153`; `:3867` | `sendUpdates='all'` / fix copy / default sender |
| P2-9 | Marketing reply sub-sequence can double-send across hosts | Outreach | `send_sequence_emails.py:218-305` | atomic claim + DB/Redis lock |
| P2-10 | Marketing open/click tracking silently 0% if `SITE_URL` unset | Outreach | `email_service.py:693-699` | require public base URL, fail loud |
| P2-11 | Manual "Process" ignores step timing (`force=True`) → premature follow-ups | Outreach | `:2375` | default `force=False` |
| P2-12 | Denormalized campaign counters can diverge from live counts on same screen | Analytics | `:122-134` | compute from logs or reconcile |
| P2-13 | Weekly reply-rate cohort mismatch (can exceed 100%) | Analytics | `:137` | label approximate / fix formula |
| P2-14 | `send_info` reports success when the answer send failed | Email | `reply_actions.py:172-195` | surface failure + alert |
| P2-15 | CRM contact re-enqueue churn burns API rate limit | CRM | `agents:77-93` | skip when mapping exists & unchanged |
| P2-16 | Enrichment never re-triggers qualification (stale scores) | Research/Qualify | no caller | enqueue re-qualify on change |

### P3 — Low

Email MX-vs-A check drops valid emails (`contact_verifier.py:74`); robots.txt fails open (`enrichment_web.py:124`); Apollo enrichment base-URL suspect (`enrichment_providers.py:78`); public booking token never expires + info leak + low-entropy Jitsi room; `CRMIntegration.field_mappings` dead config; conflict resolution fill-blanks-only (no local-wins); `generatePersonalizedEmail` dead route (I-7); `tasks.py`→API-view import (I-8); `MockEnrichmentProvider` in prod module; dead `send_mail` fallback; `FIELD_ENCRYPTION_KEY` unset (falls back to SECRET_KEY-derived); per-process marketing rate limit; triage `PER_RUN=25` backlog; `send_info` fallback greeting "Hi there"; broken root `test_crm_sync.py`; "hot without ICP fit" scoring weight (product review); two conflicting "hot" definitions (category≥90 vs temp≥75); no scoring unit tests.

---

## 6. Missing Functionality (not implemented — distinct from broken)

1. **Automatic lead-discovery fallback** that works without a paid Apify plan (the only working inflows are manual CSV and UI-run import).
2. **Auto-enrollment of qualified leads** into campaigns (segment → enroll is manual).
3. **Re-qualification** of a lead after new research/enrichment data arrives.
4. **Meeting-completed → `converted`** terminal transition (funnel never closes).
5. **SDR email open/click tracking** (only replies/meetings are measured on the SDR side).
6. **Company-wide / admin analytics roll-up** (analytics are strictly per-user).
7. **Booking-token lifecycle** (expiry / one-time use / rate-limiting) on the public page.
8. **`CRMIntegration.field_mappings`** actually applied by connectors (UI implies it works; it does nothing).

---

## 7. Final Platform Assessment

### Verdict: **Functionally Complete but Needs Hardening** — and explicitly **NOT production-ready**.

**Why "Functionally Complete":** Every one of the seven agents is a real, non-trivial implementation wired to real services — not stubs or mocks. Discovery→research→qualification is **demonstrably working on real data** (268 leads scored; I re-ran qualification live and it matched). The engage→reply→meeting→CRM→analytics half is **built and extensively unit-tested** (~400 mostly-hermetic tests), with genuinely good engineering: cross-process locking, idempotent claims, company isolation with no leak found, encrypted credentials, honest analytics with zero faked numbers, and careful LLM-key failure isolation.

**Why "Needs Hardening / not production-ready" (evidence-based):**
- **The back half of the funnel has never executed on real data** here — 0 campaigns, 0 sends, 0 replies, 0 meetings, 0 CRM syncs. Its correctness currently rests entirely on mocked tests, and the tests have blind spots exactly where the P2 bugs live (public-booking→CRM, `converted`, `send_info`, double-send races).
- **Automated prospecting — the product's headline — does not work** in the configured environment (9/11 discovery jobs failed; free-plan API ban). [P1-1]
- **The funnel cannot close:** `converted` is never set, and the primary booking path doesn't reach CRM. [P2-1, P2-2]
- **Operational fragility:** CRM/inbox depend on a Celery worker+beat that the SDR design disclaims; with the delivered SQLite broker / LocMem cache, a single-process deployment silently loses CRM sync and the reply-draft inbox. [P1-2]
- **Reliability traps** (infinite retry on a bad key; silent AI→rule fallback; silent `send_info` failure) will mislead operators in production. [P2-4, P2-5, P2-14]

**Bottom line / roadmap framing.** No rewrites are warranted — the architecture is sound and the fixes are small and localized. Close the five P1/early-P2 seams (discovery fallback, Celery topology, async research, booking→CRM, `converted`), harden the handful of silent-failure paths, then **run one real end-to-end campaign** (enroll → send → reply → book → sync → see it on the dashboard) to convert stages 4–8 from "unit-tested" to "verified." After that, this is a credible production SDR platform.

---

### Appendix — Automated suite run (completed)

Executed in this environment, Python 3.11.9 venv, fresh test DB:

```
manage.py test ai_sdr_agent   → Ran 420 tests in 25.6s — OK   (exit 0)
manage.py test crm_sync_agent → Ran 75 tests in 5.7s  — OK   (exit 0)
Total: 495 tests, 0 failures, 0 errors.
```

Caveat repeated for emphasis: all boundaries (LLM/IMAP/SMTP/CRM/calendar) are mocked, so this confirms **logic correctness and regression safety**, not live end-to-end integration. The §5 register items survive a green suite precisely because they are in untested paths.

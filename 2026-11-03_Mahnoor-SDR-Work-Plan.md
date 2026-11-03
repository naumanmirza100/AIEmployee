# Mahnoor — AI SDR Work Plan

Aligned to Abdullah's `2026-11-03_AI-SDR-Status-for-Mahnoor.md`. 3 Nov 2026.

## Ownership boundaries (from the status doc)

- **Mine** = §4.1 **R1–R6** (lead research & enrichment code), plus the two features you asked for this session (auto-enrichment, export-all).
- **Do NOT touch** (other developer / already done):
  - §2 — the seven parts that are built & tested on live (no redo).
  - §3 — audit items already handled or not true of live.
  - §4.2 — **S1–S10 (Abdullah's).**
  - §1 — Abdullah's merge fixes in `lead_research_agent.py search()` and `meeting_scheduling_agent.py _build_approval_request_html`.

## Reverted this session (they were in Abdullah's / joint territory)

I had earlier made these from the audit; they are **now removed** so I don't step on the other developer's work:

| Reverted | Was | Belongs to |
|---|---|---|
| `log_meeting(meeting)` in `sdr_booking_confirm` | booking→CRM | **S1 (Abdullah)** |
| `lead.status='converted'` in `sdr_meeting_detail` | funnel "Converted" | **S2 (Abdullah)** |
| re-queue qualification inside `enrich_lead_impl` | re-score after enrichment | **§5 (joint decision)** |

Their tests were removed too. `enrich_lead_impl` still sets `enrichment_status` done/failed (that is mine), it just no longer re-scores.

## Done this session (my scope — keep)

| Done | Where | Note |
|---|---|---|
| **R2** — auto-researched leads queued for qualification | `tasks.py auto_research_leads_impl` | exactly what R2 asks |
| Lead **generate/discovery** endpoint made async + progress polling; slider 50→**1500**; `icp_id` forwarded | `research_leads`, `SDRLeadsTab.jsx`, `aiSdrService.js` | my research UI; R1's *per-lead* endpoints still open |
| Enrichment **"No New Data"** fix — result exposes `fields_updated` | `enrichment_agent.py`, `SDRLeadsTab.jsx` | UI showed "no data" even when it added a field |
| **Auto-enrichment** pipeline — `enrichment_status` field (+migration 0032), `enrich_queue_impl`, scheduler `enrich_queue` job, pending on every create path, "Enriching…/Re-enrich" button, **Enriched Data** panel | `models.py`, `tasks.py`, `scheduler.py`, `api/views`, `SDRLeadsTab.jsx` | **you requested it.** ⚠ Per §5 this automation is a *joint decision* — confirm with Abdullah before it goes to main. Does **not** touch qualification. |
| **Export All (CSV)** — all leads (every page), server-streamed, filter- + company-scoped | new `GET /sdr/leads/export/`, `SDRLeadsTab.jsx` | you requested it |
| Ops only (local): set `SDR_SCHEDULER_ENABLED=true` in `.env` so the qualify/enrich queues run on the dev server; drained the 1,342 stuck leads; backfilled 1,328 for enrichment | local `.env`, DB data | **local dev only.** Production already runs the scheduler (doc §3). |

## Remaining — my items (§4.1)

| # | Task | Where | Priority |
|---|---|---|---|
| **R1** | Make the **per-lead research** endpoints async (one lead ≈47 s; nginx cuts at 60 s; a 50-lead batch fails on screen while it keeps running and holds up other API calls). Reuse the background-job pattern already added to `research_leads` (job row + screen polling). | `api/views/ai_sdr_agent.py`: `research_lead_endpoint`, `research_leads_batch_endpoint` | **High** |
| **R3** | Contact check uses `socket.getaddrinfo` (A record), not MX, though it says MX — a receive-only domain is marked invalid and the email dropped. Add `dnspython` + real MX lookup, **or** mark a no-A domain *risky* rather than invalid. | `contact_verifier.py` | Low |
| **R4** | Hunter provider is never given a key (`EnrichmentAgent` built with only `apollo_api_key`). Wire a Hunter setting, or remove the provider. | `tasks.py enrich_lead_impl` | Tidy |
| **R5** | `MockEnrichmentProvider` lives in the production module — move it to the tests. | `enrichment_providers.py` | Tidy |
| **R6** | Verify robots.txt handling when the file can't be fetched (audit says it then allows everything), and the Apollo `mixed_people/api_search` + `/v1/people/match` addresses — needs a **real Apollo key** to test. | `enrichment_web.py`, `enrichment_providers.py`, `lead_research_agent.py` | To check (needs key) |

## Process rules (from the doc — follow before anything ships)

1. **Pull main into the branch first** (`git pull origin main`) so Abdullah's §1 fixes aren't undone. (Branch is currently diverged: main +2, mine +5.)
2. **Open a PR — don't merge to main yourself.** Main auto-deploys to the live site on every push.
3. **Run `python -m pyflakes <changed files>`** before pushing.
4. Optional tidy (doc §1): remove `PaPerProjectFront/bun.lock` and `requirements-clean.txt` (unused — build uses `package-lock.json`, server uses `requirements.txt`).
5. Test against **Margalla Software** on live (ask Abdullah for access); a local DB won't reflect what the live site has run.

## Verification

- Keep the `ai_sdr_agent` test suite green (run `python manage.py test ai_sdr_agent`).
- R1: confirm each per-lead research endpoint returns a job id immediately and the screen polls to completion (no request longer than a second or two).
- Auto-enrichment / export: covered by `ai_sdr_agent/tests_funnel_fixes.py`.

## Open question for you

The **auto-enrichment** automation and **re-score-after-enrichment** sit in the doc's §5 "new features, for Abdullah and the client to decide on." I built auto-enrichment at your request and removed the re-score. Please confirm with Abdullah whether auto-enrichment should go to main, or stay on the branch as a proposal.

# AI SDR: where things stand

For Mahnoor · 3 November 2026 · from Abdullah

Your lead research and enrichment work is **live** on payperproject.com (PR #368, API level 28). This covers:

1. what we changed when it went in;
2. what is already built and tested, so it needn't be redone;
3. which points in `AI_SDR_PLATFORM_AUDIT.md` are already handled, or don't apply to the live site;
4. what is still worth fixing.

## 1. Your merge, and what we changed in it

`feature/lead-gen` was merged into main on 2 November (`6b87e0b`). Its deploy failed, and the live site stayed on the previous version until PR #368. Two things needed fixing, plus the API level.

**`ai_sdr_agent/agents/lead_research_agent.py`, `search()`**
- Both sides of the conflict had been kept. Main's old ending (the early `return`, `raise NoLeadSource(...)` and the `_apify_headers` method) ended up inside your provider loop. That was an IndentationError at line 477, so the server could not start.
- The same choice listed Apify twice in `available_sources`.
- **Now:** your provider loop as you wrote it (Apollo, then Apify if Apollo fails, deduped). When no source is set, it raises `NoLeadSource(NO_SOURCE_MESSAGE)`; the view turns that into "add a key, or import a file". The old `'ai'` source raises it too, with your sentence in front. The existing test `NoMadeUpLeadsTests` expects `code: no_lead_source` for both.

**`ai_sdr_agent/agents/meeting_scheduling_agent.py`, `_build_approval_request_html`**
- The f-string change for older Python put `{notes_html}` in the email without defining it. Every call proposal to a lead would have failed with a NameError.
- **Now:** the original notes block is built outside the f-string, with the HTML unchanged; notes are still escaped by `_escape_args`. It has a test now: `test_a_call_proposal_is_built_with_and_without_notes`.

**API level 28** (`core/version.py` and `PaPerProjectFront/src/config/apiLevel.js`, raised together), because your new Leads tab calls four new addresses.

The full suite passed afterwards: 2,776 tests, your 1,750 lines of tests included. Live checks:
- with no key, a search gives our message;
- the Leads tab opens with the new Quality column and research buttons;
- the research and enrichment views open.

**Could you, before your next change:**
- **Update your branch from main** (`git pull origin main` into `feature/lead-gen`), so these fixes aren't undone.
- **Send changes to main as a pull request rather than merging into it yourself.** Main deploys to the live site on every push.
- **Run pyflakes on the files you changed** (`python -m pyflakes <files>`). It finds both of the problems above in a second.
- **Consider removing `PaPerProjectFront/bun.lock` and `requirements-clean.txt`.** The build uses `package-lock.json` (npm) and the server uses `requirements.txt`, so neither file is used.

## 2. Already built and tested: no need to redo

All seven parts in the client's AI Employee list are built. These were demonstrated on the live site on 29 and 30 October with a real Gmail account, have user manuals and videos, and each answered on the live site again today (test company: Margalla Software).

| Part | What is there | How it was tested |
|---|---|---|
| Lead Qualification & Scoring | The AI scores each lead against the ICP (hot, warm, cold) with reasons. A background queue takes a few leads from each company at a time. | Live: 6 leads scored by the AI, at 75, 73, 65 and 60, each with its own reasons |
| Outreach & Campaign | Sends from the salesperson's own mailbox; its settings are tried before saving. Schedules within limits; handles unsubscribes and bounces. Reads replies in any language; the AI's answers use only the campaign's words and are checked. | Real Gmail campaign sent and replied to (29 and 30 October); live: a completed campaign |
| Meeting Scheduling | A booking page offering only the salesperson's free times. Meet or Jitsi link per call; confirmation, reminders, prep notes; move and cancel; alerts to the salesperson. | Calls booked, moved and cancelled live; live: 3 calls |
| CRM & System Sync | HubSpot, Pipedrive and Salesforce: a retry queue, deals, and changes read back from the CRM every 15 minutes. | Real HubSpot, Pipedrive and Salesforce accounts (31 October and 2 November); live: all three connected |
| Email Assistant | Writes a personal email from a kind and a tone; reads a pasted reply and drafts the answer. | Live |
| Analytics & Dashboard | Funnel figures on the company's clock, a daily summary, and a Monday low-meetings note. No made-up numbers. | Live |
| Lead Research & Enrichment (yours) | Search with Apollo, then Apify; research and enrichment of existing leads with no paid key. | Live (no key on Margalla); research and enrichment run on a copy of the demo data |

How your research and enrichment behaved on that copy, for a CSV lead whose made-up clinic has no web presence:
- **research** took 47 s and answered "partially completed", mostly "unknown", with seniority "inferred from the title only";
- **enrichment** took 5 s and answered "no data" from the public web.

Nothing was invented, which is the rule we set for the AI SDR. It hasn't been tried yet on a company with a real website, or with a real Apollo or Apify key.

## 3. The audit: already handled, or not true of the live site

`AI_SDR_PLATFORM_AUDIT.md` reads today's code correctly (its test counts, 420 and 75, are exactly main's). But its "live" numbers come from a local database: 268 leads, 0 campaigns, SQLite, Python 3.11. Production runs Redis, a Celery worker and beat, and Python 3.12. **These audit items need no work:**

| Audit item | Why not |
|---|---|
| "The back half of the funnel never ran: 0 campaigns, sends, replies, meetings, CRMs" | It has, on the live site (section 2). |
| P1-2, the "Celery topology"; "CRM and inbox silently dead" | Production runs the worker and beat (45 scheduled jobs) beside the web server, which runs the AI SDR scheduler. |
| "CRM connectors never run against a live CRM" | Tested with all three real CRMs. |
| P2-10, "Marketing tracking 0% because SITE_URL is unset" | `SITE_URL` is built from `BACKEND_URL`; production resolves it to `https://api.payperproject.com`, and opens and clicks are recorded. |
| "An invalid timezone blanks the dashboard" | `zone_name()` falls back to UTC (fix CO-240). |
| P2-7, "ICP None crashes the agent" | Only when called directly with `None`. Both views and the scoring queue check for a missing ICP first. |
| P2-11, "manual Process ignores timing" | No screen calls it any more (`handleProcess` has no button). |
| "`field_mappings`: the UI implies it works" | No screen shows it; it is just an unused field (see 4.2). |
| "No score above 75; AI scoring silently falls back" | Live scores vary and carry the AI's reasons; 75 is the ceiling while engagement signals are 0. |
| "AI-generated leads"; "Apify token in the URL" | Both already gone: you and we each removed them. |
| Authorship of the research code | The new research, enrichment and verification modules are yours; Ameer Hamza and Noor Fatima wrote the earlier versions. |

## 4. Worth fixing

None of these stops the product today. I've split them by whose code they are in. Abdullah will confirm who takes which.

### 4.1 In the lead research and enrichment code (suggested: you)

| # | What | Where | Why it matters |
|---|---|---|---|
| R1 | **Research runs inside the web request.** One lead takes about 47 s, and a batch is up to 50. nginx gives an API request 60 s, so a batch will fail on the screen while it keeps running. The API server has one worker with 8 threads, so a few such requests hold up every other API call. Enrichment already has an `async` path; research needs one too, with the screen polling for the result. | `api/views/ai_sdr_agent.py`: `research_lead_endpoint`, `research_leads_batch_endpoint` | High, as soon as people use research |
| R2 | **Leads made by the auto-research job are never scored.** They are created with `qualification_status='none'`, and the queue takes only `pending`. Set `pending` and `qualification_queued_at` when creating them. | `ai_sdr_agent/tasks.py`, `auto_research_leads_impl` | Latent: needs an Apify key |
| R3 | **The contact check uses `socket.getaddrinfo` (an A record), not MX**, though its description says MX. A domain that only receives mail is marked invalid, and the email is dropped. The standard library can't look up MX records, and `dnspython` isn't in `requirements.txt`. Either add it and check MX, or mark a domain with no address as risky rather than invalid. | `ai_sdr_agent/agents/contact_verifier.py` | Low |
| R4 | **The Hunter provider is never given a key** (`EnrichmentAgent` is built with only `apollo_api_key`). Wire it to a setting, or remove it. | `ai_sdr_agent/tasks.py`, `enrich_lead_impl` | Tidy-up |
| R5 | **`MockEnrichmentProvider` lives in the production module.** Move it to the tests. | `ai_sdr_agent/agents/enrichment_providers.py` | Tidy-up |
| R6 | **Not checked yet:** robots.txt handling when the file can't be fetched (the audit says it then allows everything), and Apollo's `mixed_people/api_search` and `/v1/people/match` addresses, which need a real Apollo key to test. | `enrichment_web.py`, `enrichment_providers.py`, `lead_research_agent.py` | To check |

### 4.2 Elsewhere in the AI SDR (suggested: Abdullah, unless you'd like any)

| # | What | Where |
|---|---|---|
| S1 | **A call booked on the lead's booking page reaches the CRM only at its reminder**, because confirming uses `.update()`, which fires no save signal. Call `log_meeting(meeting)` after confirming. | `sdr_booking_confirm`, `_give_call_a_link` |
| S2 | **"Converted" is never set**, so that funnel stage always shows 0. It needs a rule, for example a completed call. | `analytics_agent.py` reads it; nothing writes it |
| S3 | **A wrong AI key is retried forever** as "tokens used up", because `BadAPIKey` is a `KeyServiceError`. Make it final for the lead. | `ai_sdr_agent/tasks.py`, the scoring queue |
| S4 | **AI scoring has `max_tokens=2000`** on gpt-oss-20b, which reasons inside that limit. Give it more room, as the Email Assistant has (6,000). | `lead_qualification_agent.py:165` |
| S5 | **The booking page promises a calendar invite** that isn't sent (`sendUpdates='none'`, no .ics). Change the sentence, or send the invite. | `core/google_calendar.py`, `MeetingBookingPage.jsx:350` |
| S6 | **A failed "more info" answer is only logged.** Tell the salesperson. | `reply_actions.py` |
| S7 | **The weekly reply rate can pass 100%** (this week's replies over this week's emails). | `analytics_agent.py:137` |
| S8 | **The booking link never expires**, and nothing limits requests to it. | `sdr_booking_info`, `sdr_booking_confirm` |
| S9 | **`FIELD_ENCRYPTION_KEY` is not set on production**, so stored credentials use a key derived from Django's secret key. Setting it needs every stored credential re-encrypted first, so it needs a plan. | Server settings |
| S10 | **Dead code:** `generatePersonalizedEmail` (no address behind it), the root `test_crm_sync.py`, `handleProcess` and its "Process Now" help line, and the unused `CRMIntegration.field_mappings`. | as named |

## 5. Not bugs: beyond the client's list

These came up in the audit. They would be new features, for Abdullah and the client to decide on:

- campaigns enrolling qualified leads by themselves;
- open and click tracking for AI SDR emails;
- one analytics view for the whole company;
- leads scored again after research or enrichment;
- finding new leads without a paid Apollo or Apify account.

## For next time

The test company on the live site is **Margalla Software**. Ask Abdullah for access when you want to check something against production; a local database won't show what the live site has run.

The full claim-by-claim review of the audit is `2026-11-03_AI-SDR-Audit-Review.md`, in the same folder.

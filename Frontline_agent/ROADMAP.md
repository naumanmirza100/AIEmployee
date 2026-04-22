# Frontline Agent — Roadmap & Checklist

Living checklist of (a) loopholes in the current implementation that need fixing, (b) improvements to existing features, and (c) new features needed to make the Frontline Agent sellable. Tick items off as they land.

Legend: `- [ ]` = open · `- [x]` = done · `- [~]` = in progress

---

## 0. Executive Summary

**Where we are today:** The Frontline Agent already has the bones of a real product — RAG Q&A, ticket triage with auto-resolution, notifications, workflows/SOPs, document processing, meetings, analytics, and an embeddable widget.

**What's missing to be sellable:** Multi-channel ingestion (email, WhatsApp, Slack, phone), enterprise-grade security (SSO, RBAC, audit), customer identity/context (CRM integrations, Customer 360), real evaluation & testing of the AI, cost controls, and the ops polish buyers expect.

**Three-horizon plan:**
1. **Horizon 1 — Harden (4–6 weeks):** Close loopholes, add tests, rate-limiting, observability, RAG quality.
2. **Horizon 2 — Make it sellable (2–3 months):** Multi-channel, CRM, SSO, agent hand-off, customer 360, white-labeling, billing.
3. **Horizon 3 — Differentiate (ongoing):** Voice, proactive support, self-healing KB, agent co-pilot, VoC analytics, eval harness.

---

## 1. Loopholes & Risks (fix first)

Things that are actively risky or broken in what's shipped today. These should be closed before Horizon 2 features.

### 1.1 Security loopholes
- [ ] **`SECRET_KEY` hardcoded in `project_manager_ai/settings.py`, `DEBUG=True`, `ALLOWED_HOSTS=['*']`** — move to env, rotate the leaked key, set `DEBUG=False` + explicit hosts in prod
- [x] **No rate limiting on public `/frontline/public/*` endpoints** — abuse + cost escalation vector *(Batch 1: FrontlinePublicThrottle, 20/hour by IP)*
- [x] **No rate limiting on auth endpoints** — brute-force on `CompanyUserToken` *(Phase 2 Batch 9: `CompanyAuthThrottle` @ 10/hour per IP applied to login + register)*
- [x] **No rate limiting on LLM-backed endpoints** — single tenant can blow up the bill *(Batch 1: FrontlineLLMThrottle on qa/summarize/extract/create-ticket/search, 60/hour per user; upload separately 30/hour)*
- [ ] **No CAPTCHA on public widget / form** — bot spam creates tickets and chats
- [x] **Widget key not origin-validated** — key scraped from embed snippet works from any domain; validate `Origin`/`Referer` against tenant-allowed domains *(Batch 1: added `Company.frontline_allowed_origins`, enforced in `_get_company_by_widget_key`; empty = back-compat)*
- [x] **No MIME / magic-byte validation on document uploads** — only size is checked; extension is spoofable *(Batch 1: `DocumentProcessor.validate_content` rejects mismatches; also fixed latent dedupe bug)*
- [ ] **No virus scanning on uploads** — integrate ClamAV or VirusTotal
- [x] **Upload filenames not sanitized** — verify no path-traversal when constructing storage path *(Batch 1: `DocumentProcessor.sanitize_filename` via `get_valid_filename`)*
- [ ] **Token rotation / revocation** — no mechanism to force-logout on compromise; tokens appear long-lived
- [ ] **CSRF posture on public endpoints** — audit which public POSTs accept cross-origin without a token
- [x] **Sensitive data in logs** — audit log statements for PII, tokens, customer message bodies; add a redaction filter *(Phase 2 Batch 9: `Frontline_agent.logging_filters.RedactPIIFilter` wired into Django's LOGGING config; redacts email, bearer/API/Stripe/AWS/JWT/card-number patterns + password= keys)*
- [x] **Meeting links not validated** — any URL accepted into `meeting_link`; risk of phishing links routed through notifications *(Phase 2 Batch 9: `_validate_meeting_link` — requires http/https + netloc; localhost/private ranges blocked in non-DEBUG)*

### 1.2 Prompt injection & LLM safety
- [x] **Customer content flows straight into LLM prompts** with no instruction isolation *(Phase 2 Batch 9: `prompt_safety.sanitize_user_input` scrubs invisible chars + collapses known injection phrases; `wrap_untrusted` wraps all user data in labelled tags; `ANTI_INJECTION_SYSTEM_ADDENDUM` appended to system prompt; applied to `get_knowledge_prompt` and `_extract_ticket_intent`)*
- [ ] **LLM-personalized notifications are an exfil / phishing vector** — attacker-controlled ticket content can shape outbound email copy to other customers
- [~] **Document content poisoning of RAG** — *(Phase 2 Batch 9: partial — all retrieved content flows through the same wrapped-tag prompt, but per-chunk `<source_N>` wrapping is not yet applied in `get_knowledge_prompt`; retrieval provenance via citations shipped in Phase 2 Batch 1. Output scanning still pending)*
- [~] **No output sanitization before rendering LLM text in admin UI / emails** *(Phase 2 Batch 9: `prompt_safety.escape_llm_output_html` helper available; React dashboard auto-escapes JSX, so UI path is safe. Email HTML render path still pending — call the helper before injecting LLM text into HTML bodies)*
- [ ] **No jailbreak / prompt-injection test suite** — add red-team prompts to the eval harness
- [ ] **System prompt leakable via prompt-injection** — test and harden

### 1.3 Data integrity & multi-tenant isolation
- [ ] **Audit every retrieval/query path for company scoping** — one missing `company=request.user.company` filter = cross-tenant data leak
- [ ] **Confirm embedding similarity search is company-scoped** — vector search is easy to forget on
- [ ] **File-hash dedupe must be (company, hash) not hash alone** — otherwise tenant A sees tenant B's doc was "already uploaded"
- [ ] **Singleton agent init under concurrency** — shared instance may leak state across requests/tenants; use per-request construction or request-scoped context
- [ ] **Signal-driven workflow triggers can loop** — workflow updates a ticket → `on_ticket_update` fires → workflow runs again; add re-entrancy guard
- [ ] **Cascading deletes** — when a Document or KnowledgeBase entry is deleted, are `DocumentChunk`, embeddings, and chat references cleaned up? Verify `on_delete` everywhere
- [ ] **Directory typo `core/Fronline_agent/`** (missing 't') — not a bug but will confuse every new engineer forever; rename with an import-path refactor

### 1.4 Cost & abuse vectors
- [~] **No LLM cost caps per tenant** — runaway bill on a single abusive tenant *(Batch 1: `LLMUsage` model + BaseAgent tracking landed; caps/enforcement still to come)*
- [ ] **Synchronous embedding generation during upload** — large file = long-held worker, easy DoS
- [ ] **No semantic cache on Q&A** — same question by many users costs N× LLM calls
- [ ] **Public form creates tickets unverified** — ticket-flood attack possible
- [ ] **LLM personalization runs on every notification** — bulk send = bulk LLM spend; gate behind per-template opt-in + per-tenant cap

### 1.5 Concurrency & reliability
- [ ] **No background job queue** — notification send, doc processing, workflow execution all run in the request cycle; move to Celery + Redis (or RQ)
- [ ] **No retry on workflow step failure** — step fails, execution marked failed, nothing retried
- [ ] **No retry + DLQ on notification send** — bounce or 5xx = silently lost
- [ ] **No idempotency keys on workflow execution** — retried run may double-send emails, double-charge
- [ ] **Doc processing blocks on large files** — no progress, no resumability
- [ ] **No graceful LLM degradation** — if primary provider is down, behavior is undefined; need automatic failover + user-visible fallback message

### 1.6 Code quality & maintainability
- [ ] **Zero tests** — no regression safety net anywhere
- [ ] **N+1 queries in ticket / metric endpoints** — profile under load, add `select_related` / `prefetch_related`
- [ ] **Embeddings stored as JSON in `TextField`** — 1000s of chunks → multi-MB rows, slow similarity search; migrate to pgvector
- [ ] **Hardcoded chunk size (4000) / overlap (200)** — not configurable per doc type or tenant
- [ ] **Partial type hints** — tighten so mypy catches regressions
- [ ] **Generic `except Exception:` blocks** — swallow real bugs; narrow them and log with stack traces
- [ ] **No API versioning** — `/frontline/...` has no `/v1/` prefix; breaking changes will break widgets & integrations
- [x] **No error boundaries in React** — one component crash = white screen *(Batch 1: wrapped `<Outlet />` in FrontlineAgentPage + every TabsContent in FrontlineDashboard with existing `ErrorBoundary`)*
- [ ] **No frontend loading / empty / error states** in several dashboard tabs

---

## 2. Improvements to Existing Features

### 2.1 RAG / Knowledge Q&A
- [ ] Move embeddings to vector store (note: MSSQL not Postgres, so not pgvector — Qdrant/Azure Cognitive Search/FAISS)
- [~] Add cross-encoder reranker on top-N *(existing LLM reranker via gpt-4o-mini already in `services._llm_rerank`; swap to true cross-encoder later)*
- [x] Return citations `{answer, sources: [{doc_id, chunk_id, snippet, score}]}` with every answer *(Phase 2 Batch 1: multi-source citations from all chunks fed to LLM, not just top-1)*
- [x] Render citations as inline footnotes in the UI *(Phase 2 Batch 1: numbered list with title/snippet/score in QA chat)*
- [x] Query rewriting / HyDE pass before retrieval *(Phase 2 Batch 1: `FrontlineAgent._rewrite_query`; opt-in via `enable_rewrite`, auto-retries on weak retrieval)*
- [ ] Semantic / structure-aware chunking (preserve headings, tables, avoid mid-sentence cuts)
- [x] Metadata filters on retrieval (access level, category, recency, tags) *(Phase 2 Batch 1: `min_similarity`, `max_age_days`, `max_results`, plus existing `scope_document_type`/`scope_document_ids`)*
- [x] Formalize confidence threshold → "I don't know" + auto-escalate *(Phase 2 Batch 1: `FRONTLINE_RAG_MIN_CONFIDENCE` setting, returns `confidence: 'low'` + `best_score` + `threshold`; UI shows escalation hint)*
- [ ] Multi-turn conversation memory in Q&A chat
- [x] Configurable chunk size / overlap per tenant & per doc type *(Phase 2 Batch 1: `FRONTLINE_CHUNK_SIZE`/`FRONTLINE_CHUNK_OVERLAP` settings + optional `chunk_size`/`chunk_overlap` upload params, clamped to safe bounds)*
- [ ] KB feedback loop: thumbs-down → weekly review queue; flagged chunks re-indexed or marked stale

### 2.2 Ticket Triage & Auto-Resolution
- [ ] Duplicate detection via embedding similarity + merge flow
- [ ] Weekly cluster report: "28 tickets this week = 'reset password'" → suggest KB article
- [x] Re-triage on new messages (priority/category shouldn't be frozen at creation) *(Phase 2 Batch 2: `POST /frontline/tickets/<id>/retriage/` + Re-triage action in dashboard)*
- [ ] Skills-based routing (language, product area, tier, availability, least-busy)
- [ ] Per-tenant configurable tags & custom fields
- [x] Internal notes / private comments *(Phase 2 Batch 2: `TicketNote` model + notes CRUD endpoints + notes dialog in dashboard)*
- [ ] @mentions + assignment notifications
- [ ] Ticket splitting (one message → two tickets)
- [x] Snooze / follow-up reminders *(Phase 2 Batch 2: `snoozed_until` field + snooze/unsnooze endpoints + 1h/1d/3d preset actions + Celery `wake_snoozed_tickets` every 5min)*
- [~] SLA pause while waiting on customer, auto-resume on reply *(Phase 2 Batch 2: manual pause/resume landed — `sla_paused_at`, `sla_paused_accumulated_seconds`, pause/resume endpoints. Auto-resume on customer reply still pending — needs a ticket-messages model first)*

### 2.3 Notifications
- [ ] Delivery receipts, open / click tracking, bounce handling (auto-disable bad channel per user)
- [x] Retry with backoff + dead-letter queue *(Phase 2 Batch 3: `attempts`/`max_attempts`/`next_retry_at`/`dead_lettered_at`/`last_error` on ScheduledNotification; Celery `process_scheduled_notifications` every 60s; exponential backoff 5m/30m/2h; DLQ list + retry endpoints)*
- [x] Timezone-aware quiet hours (no sends 10pm–8am local) *(Phase 2 Batch 3: `timezone_name` + `quiet_hours_enabled/start/end` on preferences; sender defers to next allowed window; send_now returns `202 Accepted` with deferred_at)*
- [ ] Template versioning + rollback
- [ ] A/B test two template versions, measure response rate
- [x] Preview mode with sample data *(Phase 2 Batch 3: `POST /frontline/notifications/templates/<id>/preview/` returns rendered subject+body with sample defaults)*
- [~] One-click unsubscribe + hosted preference center (GDPR / CAN-SPAM) *(Phase 2 Batch 3: signed-token public endpoint `/frontline/unsubscribe/` landed + `{{unsubscribe_url}}` auto-injected; hosted HTML preference-center page still pending — today returns JSON, a simple confirmation page is a small add)*
- [ ] Rich email templates (MJML or drag-and-drop editor)

### 2.4 Workflows / SOPs
- [x] Retry config per step (attempts, backoff) *(Phase 2 Batch 4: per-step `retries` + `backoff_seconds` honoured in `_execute_step_list`; caps at 5 retries / 300s backoff)*
- [x] Conditional branching (`if priority==high else …`) *(Phase 2 Batch 4: new `branch` step type + `workflow_conditions.py` DSL supporting `==/!=/>/</in/not_in/contains/startswith/endswith/is_empty` and nested `all/any/not` combinators)*
- [ ] Parallel (fan-out / fan-in) steps
- [ ] Visual workflow builder (drag-and-drop graph)
- [x] Workflow versioning + dry-run mode *(Phase 2 Batch 4: `FrontlineWorkflowVersion` snapshots on every update; `/versions/`, `/versions/<N>/rollback/`, and `/dry-run/` endpoints)*
- [~] Expanded step catalog *(Phase 2 Batch 4: already had `send_email`, `update_ticket`, `webhook`/`http_webhook`, `slack`, `assign`; added `wait`/`wait_for_duration`. Still pending: `create_calendar_event`, `run_script`, `wait_for_event`)*
- [x] Execution timeout (kill runaway workflows) *(Phase 2 Batch 4: `FrontlineWorkflow.timeout_seconds` + monotonic check per step; aborts with `workflow_timeout` error)*
- [ ] One-click approvals via email / Slack (not only dashboard)

### 2.5 Document Processing
- [x] MIME + magic-byte validation *(Phase 1 Batch 1)*
- [ ] Virus scanning pipeline (needs ClamAV/VirusTotal infra)
- [ ] OCR for scanned PDFs / images (Tesseract or cloud OCR)
- [ ] Table extraction as structured data (preserve rows/columns)
- [ ] Image & screenshot support with vision LLM
- [x] Background processing via Celery/RQ *(Phase 2 Batch 5: `process_document` Celery task; upload now returns `202 Accepted` and enqueues; chunks+embeddings generated in the worker)*
- [~] Processing status UI (progress bar, partial results) *(Phase 2 Batch 5: `GET /frontline/documents/<id>/status/` exposes `processing_status`, `chunks_processed/total`, `progress_percent`, error. Frontend progress bar still to wire up)*
- [x] Document versioning; supersede old chunks, re-embed new ones *(Phase 2 Batch 5: `version`/`parent_document`/`superseded_by` fields; upload with `parent_document_id` creates v+1 and supersedes the old row; retrieval skips superseded)*
- [x] Per-document access control (role/group), enforced in retrieval *(Phase 2 Batch 5: `visibility='company'|'private'` + `allowed_users` M2M; `KnowledgeService._search_documents` enforces; public widget limited to company-visibility docs)*
- [x] Configurable retention (auto-delete after N days) *(Phase 2 Batch 5: per-doc `retention_days` field + daily `prune_expired_documents` Celery task that deletes expired docs + underlying files)*

### 2.6 Meetings
- [ ] Google Calendar + Outlook/Microsoft Graph two-way sync
- [~] Video-link auto-generation *(Phase 2 Batch 6: Jitsi Meet auto-links on create when `meeting_link` empty & `auto_jitsi=true`; Zoom/Google Meet/MS Teams still pending — they need per-tenant OAuth / API keys)*
- [~] Availability / free-busy lookup *(Phase 2 Batch 6: internal availability check across existing FrontlineMeeting rows via `GET /frontline/meetings/availability/`. External-calendar free-busy still pending)*
- [x] 24h + 15-min reminder auto-sends *(Phase 2 Batch 6: `send_meeting_reminders` Celery task every 5min; `reminder_24h_sent_at`/`reminder_15m_sent_at` bookkeeping; reminders reset when `scheduled_at` is edited)*
- [ ] Recording + auto-transcription (Whisper or vendor); feed transcripts to KB
- [x] Extract action items from transcripts → tasks/tickets *(Phase 2 Batch 6: `POST /frontline/meetings/<id>/extract-action-items/` — LLM parses transcript → JSON list stored on `action_items`; optional `create_tickets: true` promotes each item to a frontline Ticket)*

**Bonus:** full company-user CRUD for meetings (list / create / get / update / delete / transcript) is now wired into the company-user API — previously meetings existed only in an old internal view unreachable from the dashboard.

### 2.7 Analytics
- [~] Scheduled weekly / monthly PDF + email digests per tenant *(Phase 2 Batch 8: weekly plain-text digest landed — `send_weekly_analytics_digest` Celery task emails every active company user with 7-day KPIs. PDF rendering + monthly cadence still pending)*
- [ ] Drill-down from chart → filtered ticket list
- [ ] Cohort & funnel analysis
- [x] CSV / Excel export *(Phase 2 Batch 8: rebuilt `GET /frontline/analytics/export/` — now company-scoped (was user-scoped, a multi-tenant bug), supports `entity=tickets|meetings`, richer fields incl. SLA + notes_count)*
- [x] Agent performance metrics (response time, resolution rate, CSAT) *(Phase 2 Batch 8: `GET /frontline/analytics/agent-performance/` — per-agent tickets_assigned/resolved/auto_resolved, resolution_rate, avg_resolution_seconds, sla_breached_count. CSAT integration deferred until CSAT survey ships)*
- [ ] Custom dashboards per tenant; save + share layouts

### 2.8 Embed Widget
- [x] Rate limiting + CAPTCHA on public endpoints *(rate-limiting Phase 1 Batch 1; hCaptcha verification Phase 2 Batch 7 — gated by `Company.frontline_widget_config.require_captcha` + `HCAPTCHA_SECRET` env)*
- [x] Widget theming: colors, logo, position, launcher text *(Phase 2 Batch 7: stored in `Company.frontline_widget_config.theme`; surfaced via `GET /frontline/widget/public-config/`)*
- [x] Optional pre-chat form (name / email) *(Phase 2 Batch 7: `pre_chat_form.enabled` + `fields` list in config)*
- [ ] Proactive messages (URL / time-on-page / exit intent)
- [x] File uploads from widget *(Phase 2 Batch 7: multipart on `public_submit`; MIME + size validated against widget config; saved to `media/frontline_widget_uploads/<company>/`)*
- [x] Operating hours + offline form *(Phase 2 Batch 7: per-weekday tz-aware schedule; public endpoints return `status: 'closed'` with tenant-configured `offline_message` outside hours)*
- [ ] Multi-language auto-detect
- [ ] Installation snippets for WordPress, Shopify, Wix, plain HTML, React, Next.js

---

## 3. New Features — Must-have to be sellable

### 3.1 Multi-Channel Ingestion
- [ ] Email inbound (IMAP or SES/SendGrid webhook) — threading, attachments, HTML sanitization
- [ ] WhatsApp Business API (Meta Cloud API or Twilio)
- [ ] SMS inbound (Twilio / MessageBird)
- [ ] Slack Connect — customer Slack channels → ticket streams
- [ ] Microsoft Teams
- [ ] Facebook Messenger / Instagram DMs
- [ ] Twitter / X DMs & mentions
- [ ] Telegram / Discord (vertical-specific)
- [ ] Generic inbound webhook API for custom channels
- [ ] Phone / Voice (Twilio Voice + ASR + TTS) with post-call summaries
- [ ] Unified inbox UI; replies route back on original channel

### 3.2 Agent Hand-off & Human Co-pilot
- [ ] Seamless hand-off with full context + draft suggestion when confidence is low or customer asks for human
- [ ] Live AI co-pilot for human agents (drafts replies, surfaces KB, flags sentiment, suggests macros)
- [ ] Macros / canned responses with placeholders + LLM suggestions
- [ ] Shared inbox UI (assigned-to-me, unassigned, team queues)

### 3.3 Customer 360 / CRM Integrations
- [ ] HubSpot two-way sync
- [ ] Salesforce two-way sync
- [ ] Pipedrive, Zoho
- [ ] Shopify integration (order history, issue refund from ticket)
- [ ] WooCommerce, Stripe integrations
- [ ] Customer profile panel next to every ticket (past tickets, LTV, sentiment history, tier, custom attrs)
- [ ] Identity verification (OTP email/SMS) before sensitive actions

### 3.4 Tool Calling / Action Execution
- [ ] Action framework: declarative tools (JSON schema) the LLM can call
- [ ] Built-in actions: `issue_refund`, `reset_password`, `update_shipping_address`, `cancel_subscription`
- [ ] Per-action permissions + approval gates (high-risk = human approval)
- [ ] Per-tenant custom tools via webhook registration
- [ ] Full audit trail of every action (who / what / when / result)

### 3.5 Localization & Multi-language
- [ ] Auto-detect language on every inbound
- [ ] Translate + respond in customer's language
- [ ] Multilingual KB (translate on demand, cache translations)
- [ ] i18n for dashboard (10+ languages minimum)

### 3.6 Sentiment & Intent Analytics
- [ ] Per-message sentiment classification
- [ ] Churn-risk flags (angry + long tenure + high value → escalate to CSM)
- [ ] Intent trend detection ("complaints about checkout up 40% this week")
- [ ] VoC dashboard (topic clustering, emerging issues, CSAT drivers)

### 3.7 Self-Service & Customer Portal
- [ ] Branded, SEO-indexed hosted help center
- [ ] Logged-in "my tickets" portal for customers
- [ ] CSAT / NPS post-resolution surveys (one-click + free text)
- [ ] Deflection metrics ("deflected X tickets this month")

### 3.8 Self-healing Knowledge Base
- [ ] Gap detection — when agent can't answer, log as knowledge gap
- [ ] Auto-draft KB articles from resolved tickets (LLM proposes, human approves)
- [ ] Stale content detection (not updated in X months + low usage)
- [ ] Per-article usage analytics (views, Q&A hits, thumbs-up/down)

### 3.9 Evaluation & Quality
- [ ] Golden-set test harness (frozen (question, expected behavior) pairs) run on every prompt/model change
- [ ] LLM-as-judge automatic scoring
- [ ] Triage regression tests (did category/priority drift?)
- [ ] Prompt A/B testing (10% traffic → new prompt, measure CSAT / resolution)
- [ ] Red-team / prompt-injection test suite in CI

### 3.10 Cost & Usage Governance
- [x] LLM cost tracking per tenant (tokens in/out × model × price) *(Batch 1: `LLMUsage` model + `_record_llm_usage` in BaseAgent, opt-in via `self.company_id`; caps still pending)*
- [ ] Per-tenant daily/monthly caps with hard stop or cheap-model fallback
- [ ] Model routing (cheap model for easy queries, expensive for hard ones; classifier decides)
- [ ] Semantic cache on Q&A (embedding similarity → cached answer)

---

## 4. Enterprise & Compliance

### 4.1 Auth & Access
- [ ] SSO: OIDC (Google, Microsoft, Auth0)
- [ ] SSO: SAML 2.0 (Okta, enterprise IdPs)
- [ ] SCIM user provisioning
- [ ] Fine-grained RBAC (admin / agent / viewer / auditor)
- [ ] 2FA / MFA (TOTP + WebAuthn)
- [ ] Session policies (idle timeout, concurrent session limit, IP allow-list)

### 4.2 Data Privacy & Compliance
- [ ] PII detection & redaction at ingestion (Presidio or similar) before logs + LLM prompts
- [ ] GDPR: per-user data export endpoint
- [ ] GDPR: right-to-be-forgotten deletion
- [ ] Consent tracking
- [ ] Per-tenant data residency (US / EU / APAC)
- [ ] Encryption at rest for documents + sensitive fields (pgcrypto / KMS)
- [ ] Per-tenant retention policies; auto-purge after N days
- [ ] BYOK (bring-your-own-key) for LLM providers
- [ ] Per-tenant model allow-list ("this tenant: Azure OpenAI EU only")

### 4.3 Audit & Observability
- [ ] Tamper-evident append-only audit log
- [ ] Admin activity feed ("who changed what, when")
- [ ] Data-access logs (which user read which doc/ticket)
- [ ] SIEM export stream (Splunk / Datadog / CloudWatch)

### 4.4 Certifications path (process, not code)
- [ ] SOC 2 Type II
- [ ] ISO 27001
- [ ] HIPAA (for healthcare verticals)
- [ ] GDPR DPA template
- [ ] Security whitepaper + annual pentest

---

## 5. DevOps, Observability, Reliability

- [ ] Unit test suite (models, services)
- [ ] Integration test suite (API endpoints)
- [ ] E2E tests (Playwright on frontend)
- [ ] CI/CD pipeline (lint + typecheck + tests + build on PR; deploy on merge)
- [ ] Structured JSON logs with correlation IDs across request → LLM → DB
- [ ] OpenTelemetry tracing (request → retrieval → rerank → LLM → response)
- [ ] Prometheus metrics (request rate, p50/p95/p99 latency, token usage, error rate, queue depth)
- [ ] Grafana dashboards
- [ ] `/healthz`, `/readyz`, `/version` endpoints
- [ ] Feature flags (LaunchDarkly, Unleash, or in-DB)
- [ ] Celery + Redis background queue (doc processing, notifications, workflows)
- [ ] WebSocket / SSE for real-time dashboard updates
- [ ] Multi-provider LLM failover with user-visible fallback message
- [ ] Load + soak tests (k6 or Locust with realistic traffic)

---

## 6. Business / Go-to-Market

- [ ] Multi-tenant billing (Stripe) with metered usage (tickets, tokens, seats)
- [ ] Plan tiers (Starter / Pro / Enterprise)
- [ ] Trial mode + guided onboarding wizard + demo data seed
- [ ] White-labeling (custom domain, logo, colors, email "from")
- [ ] Reseller / agency accounts (parent manages sub-tenants)
- [ ] Public API + API keys
- [ ] Outbound webhooks (ticket events → customer endpoint)
- [ ] Zapier / Make integration (listed in marketplaces)
- [ ] In-app product tours + documentation
- [ ] Public status page (status.yourcompany.com)
- [ ] Changelog / release notes (in-product + public)

---

## 7. Prioritized Roadmap

### Horizon 1 — Harden (weeks 1–6)
Close loopholes + foundation. Nothing customer-visible but everything else rests on it.
- [ ] Unit + integration test suite (see §5)
- [x] Rate limiting on public endpoints + LLM calls (see §1.1, §1.4) *(Batch 1)*
- [~] MIME + magic-byte validation + virus scan on uploads (see §1.1) *(Batch 1: magic-byte + filename sanitization done; virus scan still pending)*
- [ ] Vector store migration — note: MSSQL not Postgres, so **not** pgvector; pick Qdrant / Azure Cognitive Search / FAISS file (see §2.1)
- [ ] Reranker + citations in Q&A (see §2.1)
- [ ] Celery + Redis background queue for Frontline (marketing already uses Celery; Frontline needs to adopt it) (see §5, §1.5)
- [ ] Structured logs + health checks + basic Prometheus metrics (see §5)
- [x] LLM cost tracking per tenant (see §3.10) *(Batch 1)*
- [ ] LLM cost **caps** per tenant (hard-stop or cheap-model fallback)
- [ ] Retry + DLQ on notifications and workflow steps (see §1.5)
- [x] React error boundaries *(Batch 1)* + loading/empty/error states (see §1.6)
- [x] Widget-key origin validation *(Batch 1, see §1.1)*
- [ ] Prompt-injection hardening: delimited prompts, output sanitization, red-team eval set (see §1.2)
- [ ] Rename `core/Fronline_agent/` → `core/Frontline_agent/` (see §1.3)
- [ ] **Rotate the leaked `SECRET_KEY`** committed in `project_manager_ai/settings.py` and move it + `DEBUG` + `ALLOWED_HOSTS` to env (see §1.1)

### Horizon 2 — Make it sellable (months 2–4)
What a buyer expects to see on the demo call.
- [ ] Email inbound channel (see §3.1)
- [ ] WhatsApp channel (see §3.1)
- [ ] Slack channel (see §3.1)
- [ ] HubSpot CRM integration (see §3.3)
- [ ] Customer 360 panel in ticket view (see §3.3)
- [ ] Agent hand-off + human co-pilot (see §3.2)
- [ ] SSO (OIDC first, then SAML) (see §4.1)
- [ ] Fine-grained RBAC (see §4.1)
- [ ] Widget theming / white-labeling (see §2.8, §6)
- [ ] CSAT survey + analytics (see §3.7)
- [ ] Stripe billing + plans (see §6)
- [ ] Eval harness with golden set (see §3.9)
- [ ] Audit log (see §4.3)

### Horizon 3 — Differentiate (months 4+)
Where we win deals vs Zendesk / Intercom / Freshdesk.
- [ ] Voice channel (phone + ASR + TTS + post-call summaries) (see §3.1)
- [ ] Tool-calling action framework with approval gates (see §3.4)
- [ ] Self-healing KB (gap detection → auto-draft) (see §3.8)
- [ ] VoC analytics + sentiment-driven escalation (see §3.6)
- [ ] Visual workflow builder (see §2.4)
- [ ] Multi-language with translate-on-the-fly (see §3.5)
- [ ] Proactive support triggered by product telemetry
- [ ] BYOK + data residency (see §4.2)
- [ ] OCR + vision for image/screenshot support (see §2.5)
- [ ] Scheduled + exportable reports (see §2.7)

---

## 8. Open questions to resolve before building

- **Target ICP?** — SMB (self-serve, low-ACV, many tenants) vs mid-market (sales-led, CRM matters most) vs enterprise (SSO, compliance, BYOK). Drives priority.
- **Vertical or horizontal?** — e.g., "AI frontline agent for ecommerce" with Shopify-native features can beat horizontal competitors in that niche.
- **Build vs buy on channels?** — use a single aggregator (Sunshine Conversations / MessageBird) vs native integrations. Faster but margin hit.
- **Self-hosted / on-prem option?** — opens regulated industries but doubles ops burden.
- **LLM billing model?** — our keys (simple, we absorb cost/risk) vs BYOK (enterprise-friendly, harder UX).

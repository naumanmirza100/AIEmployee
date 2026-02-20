# Frontline Agent – Feature Status vs. Vision

This document maps the **intended AI Customer Support Representative** (frontline across chat, email, web forms, social) to what is **already implemented**, what **can be implemented** (and how), what **cannot be implemented** (and why), and what **existing features need updates**.

---

## 1. Knowledge Q&A Agent

**Vision:** User asks in natural language → RAG (vector search + retrieved chunks) → LLM answers **only** from that context to avoid hallucination. Example: “What is the company policy for paternity at Laskon tech?” → search HR docs → concise summary with duration, pay, process.

### Already implemented
- Document upload (PDF, DOCX, TXT, MD, HTML) per company.
- Text extraction and embedding/indexing for semantic search.
- RAG-style flow: search vector DB for relevant chunks → pass question + context to LLM → answer grounded in context.
- Knowledge Q&A API and chat UI with conversation history.
- Fallback when no verified info (e.g. “no verified information” + creation of a ticket task for the user to add a document).

### Updates needed (no full re-implementation)
- **Citations:** Expose which document/chunk each part of the answer came from (e.g. “Source: HR Policy 2024, section 3.2”).
- **RAG tuning:** Configurable chunk size/overlap, optional re-ranking, and clearer “answer only from context” prompt wording.
- **Scope:** Optional filters (e.g. “only HR docs”) and/or document sets for different use cases (HR vs. IT).

### Can be implemented further
- Multi-document comparison (“Compare policy A and policy B on X”).
- “Summarize this document” and “Extract key points” as explicit actions in the same RAG/LLM pipeline.

### Cannot be implemented (or strong limits)
- Real-time “live” knowledge (e.g. today’s intranet) without a refresh/indexing pipeline. The system is based on **uploaded and indexed** content; anything not in the index is out of scope by design.

---

## 2. Ticket Triage & Auto-resolution Agent

**Vision:** Incoming ticket (email, chat, form) → intent + urgency + category (e.g. Password Reset, Billing, Bug) → for simple issues: auto-resolve (instructions, script, API like password reset) → clear, empathetic reply.

### Already implemented
- Ticket creation API and UI.
- **Triage:** Rule-based classification (category, priority) and optional LLM-based classification.
- **Auto-resolution:** Search knowledge base for a solution; if found, mark ticket auto-resolved and return resolution text.
- Escalation path when not auto-resolved (ticket stored for human follow-up).
- List/filter tickets (status, priority, category, date range, pagination).

### Updates needed
- **Intent/entity extraction with LLM:** Replace or augment rules with LLM-based intent and entity extraction (user ID, error message, product name) for more accurate triage.
- **External actions:** For known intents (e.g. “Password Reset”), call external APIs (e.g. account/password-reset service) and confirm in the reply. Requires secure API credentials and idempotency handling.
- **Response tone:** Add an explicit “empathetic, clear, confirm action” instruction in the prompt for the reply to the user.

### Can be implemented
- Webhook or polling for “incoming ticket” from email/chat so that triage and auto-resolution run on every new ticket.
- Simple diagnostic/script steps (e.g. “run script X and attach result to ticket”) with strict sandboxing and security review.

### Cannot be implemented (or strong limits)
- **Performing actions in arbitrary external systems** without explicit, approved integrations (e.g. “reset password” only if you integrate with your IAM/CRM). The system cannot safely “call any API” by default.
- **Fully automated resolution of sensitive cases** (e.g. refunds, account changes) without human-in-the-loop or strict business rules; that’s a policy/design choice, not just implementation.

---

## 3. Proactive Notification & Follow-up Agent

**Vision:** Triggers (e.g. shipment delayed, system down, meeting soon) → gather context → LLM generates **personalized** message (not just template) → send notification → handle replies in a two-way loop.

### Already implemented
- **Notification templates** (subject, body) with placeholders (e.g. `{{ticket_id}}`, `{{ticket_title}}`, `{{resolution}}`).
- **Channels:** Email (Django `send_mail`); SMS/in-app stubbed (log only).
- **Send now** and **schedule** APIs; scheduled notifications stored with status (pending/sent/failed).
- **History:** List of scheduled/sent notifications (APIs + basic UI in Notifications tab).

### Updates needed
- **Triggers:** No automatic triggers yet. Add: event sources (e.g. “ticket status changed”, “order delayed”, “meeting in 15 min”) and a small engine or Celery task that evaluates rules and creates scheduled/send-now notifications.
- **LLM-generated message:** Today messages are template + placeholders. Add an optional step: “when sending, call LLM with context (e.g. order details, delay reason) to generate a short, personalized message” and use that as the body (with safety limits and fallback to template).
- **Two-way loop:** Not implemented. Would require: inbound channel (email/webhook) → match to “notification thread” → LLM or rules to handle reply (e.g. “Yes, notify me when shipped”) and create follow-up. Depends on multi-channel (see below).

### Can be implemented
- Trigger engine + rules (e.g. “if ticket open > 24h, schedule follow-up with template X”).
- LLM personalization as an optional step in the send pipeline.
- Basic “notification preferences” (e.g. email vs SMS, frequency) stored per user/customer and respected when sending.

### Cannot be implemented (or strong limits)
- **True two-way conversational loop** without at least one inbound channel (email, chat, or webhook) and a way to correlate replies with the original notification. That depends on the “Multi-channel support” piece.
- **SMS** at scale without a provider (Twilio, etc.) and compliance (opt-in, etc.); the current “SMS” is a stub.

---

## 4. Workflow / SOP Runner Agent

**Vision:** High-level goal (e.g. “onboard new employee”) → agent breaks it into steps using SOP knowledge → for each step: ask user for info and/or call APIs (HRIS, IT, calendar, email) → LLM interprets results and decides next step.

### Already implemented
- **Workflow definitions:** Name, description, `trigger_conditions`, `steps` (JSON). Steps supported: `send_email`, `update_ticket`.
- **Execution engine:** Run steps in order; pass context (e.g. `ticket_id`, `recipient_email`).
- **APIs:** List/create/get/update/delete workflows; execute workflow with context; list executions.
- **UI:** Workflows tab (list workflows, run with optional ticket ID and recipient email).

### Updates needed
- **SOP as “knowledge”:** Today steps are fixed JSON. Add: store SOP text (e.g. “Onboarding checklist”) and use LLM to turn a goal (“Onboard Jane Doe”) into a sequence of steps, then map steps to existing workflow actions or new ones.
- **More step types:** e.g. “call_webhook”, “create_jira_ticket”, “send_slack_message”, “create_calendar_event” with secure config (URLs, tokens in env).
- **User-in-the-loop steps:** “Ask user for X” → store answer in context → continue workflow. Requires a way to pause execution and resume when user responds (e.g. via chat or form).
- **Trigger from events:** Run a workflow when a ticket is created or status changes (event bus or webhook).

### Can be implemented
- LLM “goal → steps” with a fixed set of allowed actions (and no arbitrary code).
- More step types as wrappers around approved internal/partner APIs.
- Simple pause/resume with token stored in DB and a “continue workflow” API called when the user submits the form or reply.

### Cannot be implemented (or strong limits)
- **Arbitrary “create account in Active Directory” / “order laptop”** without concrete integrations to your HRIS, AD, procurement system. The agent can only do what you explicitly implement (steps + APIs). No generic “do anything in any system.”
- **Fully autonomous execution** of high-risk steps (e.g. financial, legal) should remain human-approved; the engine can support “approval” as a step type.

---

## 5. Meeting Scheduling Agent

**Vision:** User says “Schedule 45-min project sync with marketing next week” → agent understands purpose and participants → checks calendars → proposes times → handles “I’m busy then” in natural language → negotiates and confirms.

### Already implemented
- **Model only:** `FrontlineMeeting` (title, description, organizer, participants, scheduled_at, duration, status, etc.). No scheduling logic, no calendar, no UI.

### Updates needed (full implementation)
- **Calendar integration:** OAuth and API for at least one provider (e.g. Google Calendar, Microsoft Graph). Read busy/free; create/update/cancel events.
- **Availability and slots:** Backend logic to compute “free slots” for a set of participants and duration; propose N options.
- **Scheduling API:** e.g. “Create meeting with these participants, this duration, preferred window” → create calendar event and send invites (or return deep links).
- **LLM layer:** Parse natural language (“project sync with marketing next week”) → extract participants (e.g. from “marketing team”), duration, time window. Generate human-friendly messages for proposing times and handling counter-offers.
- **Two-way negotiation:** Depends on a channel (email or chat) where the agent can send proposals and process replies; without it, you can only “propose and wait for manual confirm.”

### Can be implemented
- Single-provider calendar (e.g. Google) for “find slots” and “create meeting.”
- NL parsing for participants + duration + window and simple proposal messages.
- A “scheduling” workflow that: (1) gets participants and duration from user/LLM, (2) calls calendar API for slots, (3) offers choices via UI or email, (4) on choice, creates the event.

### Cannot be implemented (or strong limits)
- **Full “negotiates like a human”** (e.g. “Tuesday 4 PM is late; how about Wednesday 11 AM if X and Y can make it?”) without either (a) a rich conversational channel and stateful dialogue, or (b) complex multi-round email parsing. Doable but non-trivial.
- **Multi-provider calendar** (Google + Outlook in one view) without separate integrations and a unified availability model (e.g. polling both and merging busy/free).

---

## 6. Document Processing Agent

**Vision:** Upload documents → summarize, extract data, compare, translate; answer questions (e.g. “Summarize this and what are the early-termination penalties?”); from multiple docs, “Create a table comparing R&D spend.”

### Already implemented
- **Upload and index:** Documents (PDF, DOCX, TXT, etc.) uploaded, text extracted, stored and embedded for search.
- **Q&A over documents:** User asks a question → RAG over uploaded docs → LLM answer (see Knowledge Q&A). So “answer from this document” is covered.
- No dedicated “summarize this doc,” “extract key data,” or “compare these N docs” endpoints.

### Updates needed
- **Summarization:** New endpoint or action: “Summarize document ID X” (and optionally “in N sentences” or “by section”). Use full or chunked text + LLM.
- **Structured extraction:** “Extract: parties, dates, amounts” from a document; return JSON. Define schemas per doc type and use LLM (or LLM + validation).
- **Compare N documents:** User selects 2+ docs and asks “Compare X across these.” Retrieve relevant chunks from each, send to LLM, return comparison (table or prose).
- **OCR:** For scanned PDFs/images, add an OCR step before embedding and Q&A. Use a service (e.g. Tesseract, or cloud OCR) and then feed text into the existing pipeline.

### Can be implemented
- Summarization and extraction as separate API + UI actions.
- Comparison of 2–3 documents with a clear prompt and schema.
- OCR in the pipeline for images and scanned PDFs (with cost and quality trade-offs).

### Cannot be implemented (or strong limits)
- **Perfect extraction** from complex layouts (tables, multi-column, handwriting) without dedicated models or services; quality will vary.
- **“Create a table comparing R&D % across three annual reports”** is doable with good prompts and chunking, but accuracy depends on how well the docs are parsed and how the LLM handles numbers; it should be validated for business use.

---

## 7. Analytics & Dashboard Agent

**Vision:** User asks in plain English (“Top 5 products in the US last month vs previous month?”) → agent turns it into a query (e.g. SQL) → runs it → interprets results and can generate a chart and narrative.

### Already implemented
- **Dashboard stats:** Ticket counts (total, open, resolved, auto-resolved); document counts; recent tickets/documents.
- **Analytics API:** Tickets by date, by status, by category; total tickets; average resolution time (hours); auto-resolved count. Optional date range.
- **Export:** CSV export of tickets (with filters). Analytics tab in UI: date range, load, and export CSV.

### Updates needed
- **Natural language → query:** No “ask in plain English” yet. Add: NL interface that maps questions to a **fixed set of metrics/dimensions** (e.g. “tickets by status”, “by category”, “resolution time”) or to a safe query layer (parameterized queries, no raw user SQL).
- **Narrative:** After running the query, pass results to an LLM to generate a short summary (e.g. “Top seller was Wireless Headphones, 10k units, 15% up from last month”).
- **Charts:** Return or generate chart config (e.g. bar chart of “top 5 products”) from the same data; render in the existing dashboard or a small viz component.

### Can be implemented
- **Controlled NL → analytics:** Predefined “question templates” or a small set of intents (e.g. “top N by X”, “compare period A vs B”) mapped to parameterized backend queries. LLM parses the question into parameters, backend runs the query, LLM summarizes the result.
- **Narrative + chart:** Same as above plus a chart spec (e.g. JSON for a bar chart) and a simple frontend chart (e.g. Chart.js or similar).
- **Safe “ad-hoc” for power users:** If you expose a read-only SQL interface or a query builder, the agent could suggest or build queries with strict allowlists (tables, columns) and no writes.

### Cannot be implemented (or strong limits)
- **Arbitrary natural language → arbitrary SQL** on production DBs without tight control. Unrestricted NL-to-SQL is risky (wrong query, performance, data exposure). Use allowlisted metrics, parameterized queries, or a dedicated analytics DB/OLAP layer.
- **Real-time “live” data** in the agent’s answer depends on when you run the query; the narrative is as fresh as the last run.

---

## Multi-channel support (cross-cutting)

**Vision:** One frontline across chat, email, web forms, social. Unified inbox and routing.

### Already implemented
- **In-app only:** Knowledge Q&A and Tickets (and related features) are used inside the company dashboard. No embeddable chat widget, no inbound email, no social.

### Updates needed
- **Chat widget:** Embeddable JS widget for your website that sends messages to your backend; backend uses the same Knowledge Q&A and (optionally) ticket creation. Needs: CORS, auth/session for anonymous or logged-in users, and optionally conversation ID.
- **Email in/out:** Inbound: receive email (e.g. via SendGrid inbound parse or AWS SES) → create ticket or thread → run triage and auto-resolution; reply by sending email. Outbound: already have templates and send; need to tie to “thread” or ticket.
- **Web forms:** Form on website POSTs to your API → create ticket → same triage/auto-resolution; reply can be “we’ve received your request” and later email.
- **Social (e.g. Facebook, Twitter):** Webhooks from the platform → map to ticket or conversation → reply via platform API. Requires app approval and compliance with platform policies.
- **Unified inbox:** One UI showing all channels (labels or filters by source: email, chat, form, social). Backend stores “channel” and “external_id” on each ticket or conversation.

### Can be implemented
- Chat widget + web form are straightforward (APIs + front-end).
- Email in/out is doable with a provider (SendGrid, SES, etc.) and a secure endpoint.
- Social is per-platform (API keys, webhooks, business verification where required).

### Cannot be implemented (or strong limits)
- **“All platforms”** without implementing and maintaining each integration; there is no single universal social/chat API.
- **Rich social features** (e.g. Instagram DMs) are subject to platform rules and API availability.

---

## Summary table

| Feature | Implemented | Needs update / enhancement | Can implement (how) | Cannot / limits |
|--------|-------------|-----------------------------|----------------------|------------------|
| **1. Knowledge Q&A** | Yes (RAG, docs, chat) | Citations; RAG tuning; scopes | Comparison, summarization flows | Only indexed content; no “live” external world |
| **2. Ticket Triage & Auto-resolution** | Yes (rules, KB auto-resolve, list/filter) | LLM intent/entities; external APIs; tone | Webhooks; safe script steps | Arbitrary external systems; full auto for sensitive actions |
| **3. Proactive Notification** | Yes (templates, send/schedule, history) | Triggers; LLM personalization; two-way | Trigger engine; prefs; LLM step | Two-way without inbound channel; SMS at scale without provider |
| **4. Workflow / SOP** | Yes (workflow defs, execute, steps) | SOP as knowledge; more step types; user-in-loop; triggers | Goal→steps via LLM; approval step | Arbitrary systems without integrations; full autonomy for high risk |
| **5. Meeting Scheduling** | No (model only) | Full implementation | Calendar + slots + NL + proposals | Full human-like negotiation without channel/state |
| **6. Document Processing** | Partial (upload, Q&A) | Summarize; extract; compare; OCR | All of the above with clear scope | Perfect extraction from complex layouts; unvalidated numbers |
| **7. Analytics & Dashboard** | Partial (stats, trends, export) | NL→query; narrative; charts | Controlled NL + param queries; narrative + chart | Arbitrary NL→SQL; “live” depends on when query runs |
| **Multi-channel** | No | Full implementation | Widget; email; forms; social per platform | Single universal API for all channels |

---

## How to implement remaining / updated pieces

1. **Prioritize by business value:** e.g. NL analytics and document summarization if your users ask for that; meeting scheduling if calendar is critical.
2. **Reuse existing building blocks:** Notifications (templates + send/schedule), workflows (execute + steps), RAG (search + LLM), and tickets (triage + list) are all in place; extend them with new triggers, step types, and channels.
3. **Integrate step by step:** Add one calendar provider, one email provider, one social platform; avoid “everything at once.”
4. **Keep safety:** No raw user SQL; no arbitrary code execution; external APIs only with explicit credentials and allowlists; human approval for sensitive workflow steps.
5. **Document and maintain:** For each new trigger, workflow step, or channel, document how it works, what it can and cannot do, and how to monitor and turn it off if needed.

This file is the single reference for **what’s done**, **what to update**, **what you can add**, and **what to avoid or limit** for the Frontline Agent.

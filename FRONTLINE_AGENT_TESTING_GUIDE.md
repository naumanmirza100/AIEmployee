# Frontline Agent – Testing the New Implementations

This guide explains how to verify that the new features (citations, document summarization/extraction, notification triggers, analytics narrative, and LLM ticket triage) are working.

---

## Prerequisites

1. **Backend running**  
   ```bash
   python manage.py runserver
   ```

2. **Frontend running** (if testing via UI)  
   ```bash
   cd PaPerProjectFront && npm run dev
   ```

3. **Company user account**  
   Log in as a company user that has access to the Frontline Agent (Company Dashboard → Frontline Agent).

4. **LLM configured**  
   At least one of: Groq, OpenRouter, or OpenAI (see your project’s LLM settings). Required for: summarization, extraction, analytics narrative, and ticket intent extraction.

---

## 1. Knowledge Q&A – Source citations

**What to verify:** Answers show a clear source (e.g. document title or “PayPerProject Database”).

### UI test

1. Open **Frontline Agent** → **Knowledge Q&A** tab.
2. Ensure you have at least one document uploaded (Documents tab) or that PayPerProject DB has FAQs/policies.
3. Ask a question that matches your content (e.g. “What is the refund policy?” or “How do I reset my password?”).
4. **Check:** Under the answer you see a line like:
   - `Source: Uploaded Document – YourDocumentName.pdf`, or  
   - `Source: PayPerProject Database – FAQ title`

### API test (optional)

```bash
# Replace TOKEN and optionally BASE_URL
curl -X POST "http://localhost:8000/api/frontline/knowledge/qa/" \
  -H "Authorization: Token YOUR_COMPANY_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"What is the refund policy?\"}"
```

**Expected:** JSON response includes `has_verified_info`, `answer`, and `source` (and optionally `document_title`, `citations`).

---

## 2. Document summarization and extraction

**What to verify:** You can summarize a document and extract structured data (e.g. parties, dates) from the Documents tab and/or API.

### UI test

1. **Documents** tab → upload a document (PDF/DOCX/TXT) if you don’t have one.
2. On a document row you should see two actions (in addition to delete):
   - **Summarize** (e.g. file/search icon)
   - **Extract data** (e.g. list/check icon)
3. Click **Summarize**  
   - **Check:** A dialog opens and shows an AI-generated summary (or “Processing…” then the summary).
4. Click **Extract data**  
   - **Check:** A dialog opens and shows JSON (e.g. `parties`, `dates`, `amounts`, `key_terms`).

### API test (optional)

Replace `DOCUMENT_ID` and `YOUR_COMPANY_TOKEN`.

**Summarize:**
```bash
curl -X POST "http://localhost:8000/api/frontline/documents/DOCUMENT_ID/summarize/" \
  -H "Authorization: Token YOUR_COMPANY_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"max_sentences\": 5}"
```

**Extract:**
```bash
curl -X POST "http://localhost:8000/api/frontline/documents/DOCUMENT_ID/extract/" \
  -H "Authorization: Token YOUR_COMPANY_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"schema\": [\"parties\", \"dates\", \"amounts\"]}"
```

**Expected:**  
- Summarize: `status: "success"`, `data.summary` with text.  
- Extract: `status: "success"`, `data.extracted` with the requested keys.

---

## 3. Proactive notification – Trigger engine

**What to verify:** Creating or updating a ticket creates a scheduled notification when a template has the right `trigger_config`.

### Setup

1. **Notifications** tab → create or edit a **Notification template** (subject + body, e.g. placeholders `{{ticket_id}}`, `{{ticket_title}}`).
2. Set **trigger_config** for that template.  
   - **Option A – Django Admin:**  
     - Open `/admin/` → **Frontline_agent** → **Notification templates** → your template.  
     - In **Trigger config** enter JSON, e.g.:  
       - On ticket created: `{"on": "ticket_created", "delay_minutes": 0}`  
       - On ticket updated: `{"on": "ticket_updated", "delay_minutes": 0}`  
   - **Option B – DB (if you have access):**  
     - Update the template row:  
       `trigger_config = {"on": "ticket_created", "delay_minutes": 0}`

### Test “ticket_created”

1. Create a ticket (Tickets tab → Create ticket, or Knowledge Q&A ask something that has no answer so a KB-gap ticket is created).
2. **Check:**  
   - Notifications tab → **Scheduled / history** (or equivalent): a new scheduled notification appears for that template, linked to the new ticket.  
   - If `delay_minutes` is 0 and you have a worker/celery that sends pending notifications, the notification may be sent immediately (check logs or email).

### Test “ticket_updated”

1. Open **Ticket tasks** (or Tickets), find a ticket you can edit.
2. Change status (e.g. to Resolved) and save.
3. **Check:** Same as above – a new scheduled notification appears for templates with `"on": "ticket_updated"`.

### API check (optional)

After creating a ticket, list scheduled notifications:

```bash
curl -X GET "http://localhost:8000/api/frontline/notifications/scheduled/?limit=20" \
  -H "Authorization: Token YOUR_COMPANY_TOKEN"
```

**Expected:** Entries with `template_id`, `scheduled_at`, `status` (e.g. `pending`), and `related_ticket` or context including the new ticket.

---

## 4. Analytics – LLM narrative summary

**What to verify:** Analytics response includes a short narrative and the UI shows it.

### UI test

1. **Analytics** tab → set date range (or leave default) → **Load**.
2. **Check:**  
   - You see the usual stats (total tickets, by status, by category, etc.).  
   - Above or near the stats there is a **Summary** block with 2–4 sentences (e.g. total tickets, main categories, resolution time, auto-resolved count).  
   - If the LLM is not configured or the request fails, the rest of the analytics still load; only the summary may be missing.

### API test (optional)

```bash
curl -X GET "http://localhost:8000/api/frontline/analytics/?narrative=1" \
  -H "Authorization: Token YOUR_COMPANY_TOKEN"
```

**Expected:** `data` contains `tickets_by_status`, `tickets_by_category`, `total_tickets`, etc., and a `narrative` string when the LLM runs successfully.

---

## 5. Ticket triage – LLM intent/entity extraction

**What to verify:** Creating a ticket returns (or uses) intent and entities from the LLM, and classification can be influenced by it.

### UI test

1. **Tickets** tab → **Create ticket**.
2. Submit a ticket with clear intent, e.g.:  
   - Title: “Password reset for user john@example.com”  
   - Description: “User reported error 500 on login page, need to reset password.”
3. **Check:**  
   - Ticket is created and you get a success message (and optional auto-resolution if applicable).  
   - In the API response (or in network tab): the create-ticket response includes `classification` and, when the LLM runs, `intent` and/or `entities` (e.g. `user_id`, `error_message`, `product_name`).  
   - Category/priority may align with the described intent (e.g. account, password reset).

### API test (optional)

```bash
curl -X POST "http://localhost:8000/api/frontline/tickets/create/" \
  -H "Authorization: Token YOUR_COMPANY_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"title\": \"Password reset\", \"description\": \"User john@example.com cannot login, error 500.\"}"
```

**Expected:** Response includes `ticket_id`, `classification` (e.g. `category`, `priority`), and optionally `intent` and `entities`. Check backend logs for lines like “LLM extraction: intent=..., category=..., entities=...”.

---

## Quick checklist

| Feature              | Where to test                    | What to look for                                      |
|----------------------|----------------------------------|--------------------------------------------------------|
| Citations            | Knowledge Q&A tab                | “Source: …” under the answer                          |
| Summarize document   | Documents tab → Summarize        | Dialog with summary text                              |
| Extract document     | Documents tab → Extract data     | Dialog with JSON (parties, dates, etc.)               |
| Notification triggers | Create/update ticket + Notifications | New row in scheduled/history for triggered template |
| Analytics narrative  | Analytics tab → Load             | “Summary” block with 2–4 sentences                    |
| Ticket intent/LLM    | Create ticket (UI or API)        | Response has intent/entities; logs show LLM extraction |

---

## Troubleshooting

- **No narrative / no intent / no summary:**  
  Check that an LLM is configured (Groq/OpenRouter/OpenAI) and that the backend logs don’t show API or key errors.

- **Trigger not creating notifications:**  
  Confirm the template’s `trigger_config` is valid JSON and has `"on": "ticket_created"` or `"ticket_updated"`.  
  Ensure the template belongs to the same company as the user creating/updating the ticket.

- **Citations show “PayPerProject Database” only:**  
  That’s expected when the answer came from FAQs/policies/manuals rather than an uploaded document. Upload a document and ask something only that document answers to see “Uploaded Document – …”.

- **Migration issues:**  
  If you still have migration errors (e.g. recruitment_agent 0025), ensure you applied the fixed 0025 migration that uses conditional index/table renames before running other migrations.

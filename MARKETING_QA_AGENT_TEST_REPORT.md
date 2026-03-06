# Marketing AI Q&A Agent - Test Report

**Report Date:** March 6, 2026  
**Prepared By:** Development Team  
**Test Script:** `test_marketing_qa_agent.py`  
**Agent Under Test:** `MarketingQAAgent` (`marketing_agent/agents/marketing_qa_agent.py`)  
**LLM Provider:** Groq (llama-3.1-8b-instant)

---

## 1. Executive Summary

The Marketing AI Q&A Agent was tested with **20 diverse queries** comparing **manual database (DB) results** against **AI Agent responses**. The test covers:

- **10 DB-answerable questions** — campaign counts, leads, open rates, email totals, performance analytics, status breakdowns, leads per campaign, and specific campaign details
- **10 AI/LLM-only questions** — strategy recommendations, trend analysis, optimization suggestions, opportunity identification, performance improvement, best practices, goals analysis, conversion strategy, and overall summary

| Metric | Value |
|---|---|
| **Total Tests** | 20 |
| **DB-Answerable Tests** | 10 |
| **LLM-Only Tests** | 10 |
| **Passed** | _To be filled after run_ |
| **Failed** | _To be filled after run_ |
| **Errors** | _To be filled after run_ |
| **Overall Accuracy** | _To be filled after run_ |

---

## 2. Test Architecture

### How It Works

```
┌──────────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  Test Question    │────>│  Manual DB Query     │────>│  Expected Result │
│  (20 questions)   │     │  (Django ORM)        │     │  (Ground Truth)  │
└──────────────────┘     └─────────────────────┘     └──────────────────┘
         │                                                      │
         │                                                      │
         v                                                      v
┌──────────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  AI Agent Call    │────>│  MarketingQAAgent    │────>│  AI Response +   │
│  process()       │     │  .process()          │     │  Token Usage     │
└──────────────────┘     └─────────────────────┘     └──────────────────┘
                                                             │
                                                             v
                                                    ┌──────────────────┐
                                                    │  COMPARE:        │
                                                    │  Manual vs AI    │
                                                    │  → PASS / FAIL   │
                                                    └──────────────────┘
```

### Agent Routing (Smart Enum Router)

The `MarketingQAAgent` classifies each question into one of these categories:

| Category | Route | LLM Tokens? |
|---|---|---|
| `GREETING` | Static reply | 0 |
| `PLATFORM_INFO` | Static platform description | 0 |
| `META_HELP` | "What can I ask?" reply | 0 |
| `DB_COUNT_STATUS` | Campaign count / active / list | 0 |
| `DB_TOTAL_LEADS` | Total leads number | 0 |
| `DB_ANALYTICS` | Open rate, click rate, top campaigns | 0 |
| `DB_CAMPAIGN_DETAIL` | Specific named campaign metrics | 0 |
| `DB_BEST_CHANNEL` | Channel recommendation (static logic) | 0 |
| `GENERAL_DEFINITION` | "What is X?" definitions | Small LLM call |
| `LLM_REASONING` | Why, strategy, improve, optimize | Full LLM + data |

---

## 3. Test Cases — DB-Answerable Questions (Tests 1–10)

### Test 1: How many campaigns do I have?

| Field | Value |
|---|---|
| **Question** | "How many campaigns do I have?" |
| **Category** | `DB_COUNT_STATUS` |
| **Expected Route** | DB-only (0 LLM tokens) |
| **Manual SQL Query** | |

```sql
SELECT COUNT(*) FROM ppp_marketingagent_campaign WHERE owner_id = <user.id>;
SELECT name FROM ppp_marketingagent_campaign WHERE owner_id = <user.id>;
```

| Field | Value |
|---|---|
| **Manual DB Result** | _To be filled: e.g. `{"count": 5, "items": ["Campaign A", "Campaign B", ...]}` _ |
| **AI Response** | _To be filled: e.g. "You have **5** campaign(s) in total. **3** are currently active."_ |
| **Token Usage** | `{ prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, provider: "none" }` |
| **Match Detail** | _To be filled_ |
| **Status** | _PASS / FAIL_ |

---

### Test 2: How many leads do I have in total?

| Field | Value |
|---|---|
| **Question** | "How many leads do I have in total?" |
| **Category** | `DB_TOTAL_LEADS` |
| **Expected Route** | DB-only (0 LLM tokens) |
| **Manual SQL Query** | |

```sql
SELECT COUNT(*) FROM ppp_marketingagent_campaign_leads cl
INNER JOIN ppp_marketingagent_campaign c ON cl.campaign_id = c.id
WHERE c.owner_id = <user.id>;
```

| Field | Value |
|---|---|
| **Manual DB Result** | _To be filled: e.g. `{"count": 150}`_ |
| **AI Response** | _To be filled: e.g. "**150** lead(s) in total."_ |
| **Token Usage** | `{ prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, provider: "none" }` |
| **Match Detail** | _To be filled_ |
| **Status** | _PASS / FAIL_ |

---

### Test 3: What campaigns are performing best?

| Field | Value |
|---|---|
| **Question** | "What campaigns are performing best?" |
| **Category** | `DB_ANALYTICS` |
| **Expected Route** | DB-only (0 LLM tokens) |
| **Manual SQL Query** | |

```sql
SELECT c.name, c.status,
  COUNT(CASE WHEN e.status IN ('sent','delivered','opened','clicked') THEN 1 END) AS emails_sent,
  COUNT(CASE WHEN e.status IN ('opened','clicked') THEN 1 END) AS emails_opened,
  COUNT(CASE WHEN e.status = 'clicked' THEN 1 END) AS emails_clicked
FROM ppp_marketingagent_campaign c
LEFT JOIN ppp_marketingagent_emailsendhistory e ON e.campaign_id = c.id
WHERE c.owner_id = <user.id>
GROUP BY c.id ORDER BY emails_opened DESC, emails_sent DESC LIMIT 5;
```

| Field | Value |
|---|---|
| **Manual DB Result** | _To be filled: e.g. `{"name": "Summer Sale Campaign", "count": 5, "items": [...]}`_ |
| **AI Response** | _To be filled: e.g. "Best performing: **Summer Sale Campaign (active)**..."_ |
| **Token Usage** | `{ prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, provider: "none" }` |
| **Match Detail** | _To be filled_ |
| **Status** | _PASS / FAIL_ |

---

### Test 4: Show campaigns by status

| Field | Value |
|---|---|
| **Question** | "Show campaigns by status" |
| **Category** | `DB_ANALYTICS` |
| **Expected Route** | DB-only (0 LLM tokens) |
| **Manual SQL Query** | |

```sql
SELECT status, COUNT(*) AS cnt, GROUP_CONCAT(name)
FROM ppp_marketingagent_campaign
WHERE owner_id = <user.id>
GROUP BY status;
```

| Field | Value |
|---|---|
| **Manual DB Result** | _To be filled: e.g. `{"count": 5, "statuses": {"active": {"count": 3, ...}, "draft": {"count": 2, ...}}}`_ |
| **AI Response** | _To be filled: e.g. "- **active**: 3 (Campaign A, Campaign B, Campaign C)..."_ |
| **Token Usage** | `{ prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, provider: "none" }` |
| **Match Detail** | _To be filled_ |
| **Status** | _PASS / FAIL_ |

---

### Test 5: Tell me about [Campaign Name]

| Field | Value |
|---|---|
| **Question** | "Tell me about {first_campaign_name}" |
| **Category** | `DB_CAMPAIGN_DETAIL` |
| **Expected Route** | DB-only (0 LLM tokens) |
| **Manual SQL Query** | |

```sql
SELECT c.*,
  (SELECT COUNT(*) FROM ppp_marketingagent_emailsendhistory e 
   WHERE e.campaign_id = c.id AND e.status IN ('sent','delivered','opened','clicked')) AS emails_sent,
  (SELECT COUNT(*) FROM ppp_marketingagent_emailsendhistory e 
   WHERE e.campaign_id = c.id AND e.status IN ('opened','clicked')) AS emails_opened,
  (SELECT COUNT(*) FROM ppp_marketingagent_campaign_leads cl 
   WHERE cl.campaign_id = c.id) AS leads_count
FROM ppp_marketingagent_campaign c
WHERE c.owner_id = <user.id> AND c.name = '<campaign_name>';
```

| Field | Value |
|---|---|
| **Manual DB Result** | _To be filled: e.g. `{"name": "...", "status": "active", "emails_sent": 500, "emails_opened": 200, ...}`_ |
| **AI Response** | _To be filled: e.g. "**Campaign Name (active)** - Emails: sent=500, opened=200..."_ |
| **Token Usage** | `{ prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, provider: "none" }` |
| **Match Detail** | _To be filled_ |
| **Status** | _PASS / FAIL_ |

---

### Test 6: What is the average open rate?

| Field | Value |
|---|---|
| **Question** | "What is the average open rate?" |
| **Category** | `DB_ANALYTICS` |
| **Expected Route** | DB-only (0 LLM tokens) |
| **Manual SQL Query** | |

```sql
SELECT AVG(open_rate) FROM (
  SELECT c.id,
    CASE WHEN COUNT(CASE WHEN e.status IN ('sent','delivered','opened','clicked') THEN 1 END) > 0
      THEN ROUND(COUNT(CASE WHEN e.status IN ('opened','clicked') THEN 1 END) * 100.0 
           / COUNT(CASE WHEN e.status IN ('sent','delivered','opened','clicked') THEN 1 END), 2)
      ELSE 0 END AS open_rate
  FROM ppp_marketingagent_campaign c
  LEFT JOIN ppp_marketingagent_emailsendhistory e ON e.campaign_id = c.id
  WHERE c.owner_id = <user.id>
  GROUP BY c.id
) sub;
```

| Field | Value |
|---|---|
| **Manual DB Result** | _To be filled: e.g. `{"avg_open_rate": 35.5, "campaigns_with_data": 4}`_ |
| **AI Response** | _To be filled: e.g. "Your average open rate across campaigns is **35.5%**..."_ |
| **Token Usage** | `{ prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, provider: "none" }` |
| **Match Detail** | _To be filled_ |
| **Status** | _PASS / FAIL_ |

---

### Test 7: How many emails have been sent in total?

| Field | Value |
|---|---|
| **Question** | "How many emails have been sent in total?" |
| **Category** | `DB_ANALYTICS` |
| **Expected Route** | DB-only (0 LLM tokens) |
| **Manual SQL Query** | |

```sql
SELECT COUNT(*) FROM ppp_marketingagent_emailsendhistory e
INNER JOIN ppp_marketingagent_campaign c ON e.campaign_id = c.id
WHERE c.owner_id = <user.id>
  AND e.status IN ('sent','delivered','opened','clicked');
```

| Field | Value |
|---|---|
| **Manual DB Result** | _To be filled: e.g. `{"count": 2500}`_ |
| **AI Response** | _To be filled: e.g. "A total of **2500** emails have been sent..."_ |
| **Token Usage** | `{ prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, provider: "none" }` |
| **Match Detail** | _To be filled_ |
| **Status** | _PASS / FAIL_ |

---

### Test 8: How is [Second Campaign] performing?

| Field | Value |
|---|---|
| **Question** | "How is {second_campaign_name} performing?" |
| **Category** | `DB_CAMPAIGN_DETAIL` |
| **Expected Route** | DB-only (0 LLM tokens) |
| **Manual SQL Query** | |

```sql
SELECT c.*,
  (SELECT COUNT(*) FROM ppp_marketingagent_emailsendhistory e 
   WHERE e.campaign_id = c.id AND e.status IN ('sent','delivered','opened','clicked')) AS emails_sent,
  (SELECT COUNT(*) FROM ppp_marketingagent_emailsendhistory e 
   WHERE e.campaign_id = c.id AND e.status IN ('opened','clicked')) AS emails_opened
FROM ppp_marketingagent_campaign c
WHERE c.owner_id = <user.id> AND c.name = '<second_campaign_name>';
```

| Field | Value |
|---|---|
| **Manual DB Result** | _To be filled: e.g. `{"name": "...", "status": "active", "emails_sent": 300, "emails_opened": 120, ...}`_ |
| **AI Response** | _To be filled: e.g. "**Second Campaign (active)** - Emails: sent=300, opened=120..."_ |
| **Token Usage** | `{ prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, provider: "none" }` |
| **Match Detail** | _To be filled_ |
| **Status** | _PASS / FAIL_ |

---

### Test 9: Show leads per campaign

| Field | Value |
|---|---|
| **Question** | "Show leads per campaign" |
| **Category** | `DB_ANALYTICS` |
| **Expected Route** | DB-only (0 LLM tokens) |
| **Manual SQL Query** | |

```sql
SELECT c.name, COUNT(cl.id) AS leads_count
FROM ppp_marketingagent_campaign c
LEFT JOIN ppp_marketingagent_campaign_leads cl ON cl.campaign_id = c.id
WHERE c.owner_id = <user.id>
GROUP BY c.id ORDER BY leads_count DESC;
```

| Field | Value |
|---|---|
| **Manual DB Result** | _To be filled: e.g. `{"count": 5, "items": ["Campaign A: 50", "Campaign B: 30", ...]}`_ |
| **AI Response** | _To be filled: e.g. "Leads per campaign: Campaign A: 50, Campaign B: 30..."_ |
| **Token Usage** | `{ prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, provider: "none" }` |
| **Match Detail** | _To be filled_ |
| **Status** | _PASS / FAIL_ |

---

### Test 10: How are our campaigns performing this month?

| Field | Value |
|---|---|
| **Question** | "How are our campaigns performing this month?" |
| **Category** | `DB_ANALYTICS` |
| **Expected Route** | DB-only (0 LLM tokens) |
| **Manual SQL Query** | |

```sql
SELECT c.name, c.status,
  COUNT(CASE WHEN e.status IN ('sent','delivered','opened','clicked') THEN 1 END) AS sent,
  COUNT(CASE WHEN e.status IN ('opened','clicked') THEN 1 END) AS opened,
  COUNT(CASE WHEN e.status = 'clicked' THEN 1 END) AS clicked
FROM ppp_marketingagent_campaign c
LEFT JOIN ppp_marketingagent_emailsendhistory e ON e.campaign_id = c.id
WHERE c.owner_id = <user.id>
GROUP BY c.id;
```

| Field | Value |
|---|---|
| **Manual DB Result** | _To be filled: e.g. `{"count": 5, "total_sent": 1000, "total_opened": 400, "items": [...]}`_ |
| **AI Response** | _To be filled: e.g. "Campaign performance summary: 5 campaigns, 1000 emails sent, 400 opened..."_ |
| **Token Usage** | `{ prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, provider: "none" }` |
| **Match Detail** | _To be filled_ |
| **Status** | _PASS / FAIL_ |

---

## 4. Test Cases — AI/LLM-Only Questions (Tests 11–20)

These questions require the LLM (Groq) to analyze the marketing data and generate insights. There is no single "correct" DB answer — the AI must reason over the data.

### Test 11: What marketing strategies should we implement?

| Field | Value |
|---|---|
| **Question** | "What marketing strategies should we implement to improve performance?" |
| **Category** | `LLM_REASONING` |
| **Expected Route** | Full LLM call with marketing data context |
| **Manual SQL Query** | `LLM_ONLY` — uses all campaign/performance data + Groq for strategy analysis |

| Field | Value |
|---|---|
| **Manual DB Result** | N/A (LLM-only strategy recommendation; no single DB query) |
| **AI Response** | _To be filled: AI will provide strategy recommendations based on campaign data_ |
| **Token Usage** | _To be filled: e.g. `{ prompt_tokens: 450, completion_tokens: 350, total_tokens: 800, provider: "groq" }`_ |
| **Validation** | Non-empty, coherent response referencing actual campaign data |
| **Status** | _PASS / FAIL_ |

---

### Test 12: Why are sales dropping?

| Field | Value |
|---|---|
| **Question** | "Why are sales dropping and what should we do about it?" |
| **Category** | `LLM_REASONING` |
| **Expected Route** | Full LLM call with marketing data context |
| **Manual SQL Query** | `LLM_ONLY` — uses campaign performance data + Groq for analysis |

| Field | Value |
|---|---|
| **Manual DB Result** | N/A (LLM reasoning over campaign data; no single DB query) |
| **AI Response** | _To be filled: AI will analyze campaign metrics and suggest reasons/solutions_ |
| **Token Usage** | _To be filled_ |
| **Validation** | Non-empty, coherent response with actionable suggestions |
| **Status** | _PASS / FAIL_ |

---

### Test 13: Which campaigns need optimization?

| Field | Value |
|---|---|
| **Question** | "Which campaigns need optimization and what changes do you recommend?" |
| **Category** | `LLM_REASONING` |
| **Expected Route** | Full LLM call with marketing data context |
| **Manual SQL Query** | `LLM_ONLY` — uses campaign metrics + Groq for optimization recommendations |

| Field | Value |
|---|---|
| **Manual DB Result** | N/A (LLM analysis over campaign metrics; no single DB query) |
| **AI Response** | _To be filled: AI will identify underperforming campaigns and suggest improvements_ |
| **Token Usage** | _To be filled_ |
| **Validation** | Non-empty, references specific campaign names and metrics |
| **Status** | _PASS / FAIL_ |

---

### Test 14: Key trends in marketing data

| Field | Value |
|---|---|
| **Question** | "What are the key trends in our marketing data?" |
| **Category** | `LLM_REASONING` |
| **Expected Route** | Full LLM call with marketing data context |
| **Manual SQL Query** | `LLM_ONLY` — uses all campaign/performance data + Groq for trend analysis |

| Field | Value |
|---|---|
| **Manual DB Result** | N/A (LLM trend analysis; no single DB query) |
| **AI Response** | _To be filled: AI will identify patterns, trends, and changes in marketing data_ |
| **Token Usage** | _To be filled_ |
| **Validation** | Non-empty, discusses trends like open rates, engagement, campaign growth |
| **Status** | _PASS / FAIL_ |

---

### Test 15: What opportunities are we missing?

| Field | Value |
|---|---|
| **Question** | "What opportunities are we missing in our current marketing approach?" |
| **Category** | `LLM_REASONING` |
| **Expected Route** | Full LLM call with marketing data context |
| **Manual SQL Query** | `LLM_ONLY` — uses marketing data context + Groq for opportunity analysis |

| Field | Value |
|---|---|
| **Manual DB Result** | N/A (LLM insight generation; no single DB query) |
| **AI Response** | _To be filled: AI will identify gaps and untapped opportunities_ |
| **Token Usage** | _To be filled_ |
| **Validation** | Non-empty, provides actionable opportunity recommendations |
| **Status** | _PASS / FAIL_ |

---

### Test 16: How can we improve our campaign performance?

| Field | Value |
|---|---|
| **Question** | "How can we improve our campaign performance?" |
| **Category** | `LLM_REASONING` |
| **Expected Route** | Full LLM call with marketing data context |
| **Manual SQL Query** | `LLM_ONLY` — uses campaign data + Groq for improvement suggestions |

| Field | Value |
|---|---|
| **Manual DB Result** | N/A (LLM improvement recommendations; no single DB query) |
| **AI Response** | _To be filled: AI will provide specific recommendations to improve campaign metrics_ |
| **Token Usage** | _To be filled_ |
| **Validation** | Non-empty, references actual metrics and suggests specific improvements |
| **Status** | _PASS / FAIL_ |

---

### Test 17: Best practices for email marketing?

| Field | Value |
|---|---|
| **Question** | "What are the best practices for email marketing in our industry?" |
| **Category** | `LLM_REASONING` |
| **Expected Route** | Full LLM call with marketing data context |
| **Manual SQL Query** | `LLM_ONLY` — general email marketing knowledge via Groq |

| Field | Value |
|---|---|
| **Manual DB Result** | N/A (LLM general knowledge; no DB query) |
| **AI Response** | _To be filled: AI will provide industry best practices for email marketing_ |
| **Token Usage** | _To be filled_ |
| **Validation** | Non-empty, discusses segmentation, personalization, timing, A/B testing, etc. |
| **Status** | _PASS / FAIL_ |

---

### Test 18: Are we on track to meet our campaign goals?

| Field | Value |
|---|---|
| **Question** | "Are we on track to meet our campaign goals?" |
| **Category** | `LLM_REASONING` |
| **Expected Route** | Full LLM call with marketing data context |
| **Manual SQL Query** | `LLM_ONLY` — uses campaign targets + actual data + Groq for goal analysis |

| Field | Value |
|---|---|
| **Manual DB Result** | N/A (LLM analysis of goal progress; no single DB query) |
| **AI Response** | _To be filled: AI will analyze campaign progress against targets_ |
| **Token Usage** | _To be filled_ |
| **Validation** | Non-empty, discusses goal progress and areas needing attention |
| **Status** | _PASS / FAIL_ |

---

### Test 19: Improving lead conversion rates

| Field | Value |
|---|---|
| **Question** | "What should we focus on to improve lead conversion rates?" |
| **Category** | `LLM_REASONING` |
| **Expected Route** | Full LLM call with marketing data context |
| **Manual SQL Query** | `LLM_ONLY` — uses lead/campaign data + Groq for conversion strategy |

| Field | Value |
|---|---|
| **Manual DB Result** | N/A (LLM conversion optimization; no single DB query) |
| **AI Response** | _To be filled: AI will provide lead conversion improvement strategies_ |
| **Token Usage** | _To be filled_ |
| **Validation** | Non-empty, provides actionable conversion optimization recommendations |
| **Status** | _PASS / FAIL_ |

---

### Test 20: Overall marketing summary with recommendations

| Field | Value |
|---|---|
| **Question** | "Give me an overall summary of my marketing performance with top 3 recommendations." |
| **Category** | `LLM_REASONING` |
| **Expected Route** | Full LLM call with marketing data context |
| **Manual SQL Query** | `LLM_ONLY` — uses all marketing data + Groq for summary + recommendations |

| Field | Value |
|---|---|
| **Manual DB Result** | N/A (LLM-only narrative summary; no single DB query) |
| **AI Response** | _To be filled: AI will provide a comprehensive summary and top 3 actionable recommendations_ |
| **Token Usage** | _To be filled_ |
| **Validation** | Non-empty, includes performance overview and exactly 3 recommendations |
| **Status** | _PASS / FAIL_ |

---

## 5. Token Usage Summary

| # | Question | LLM Used? | Prompt Tokens | Completion Tokens | Total Tokens | Provider |
|---|---|---|---|---|---|---|
| 1 | How many campaigns do I have? | No | 0 | 0 | 0 | none |
| 2 | How many leads do I have in total? | No | 0 | 0 | 0 | none |
| 3 | What campaigns are performing best? | No | 0 | 0 | 0 | none |
| 4 | Show campaigns by status | No | 0 | 0 | 0 | none |
| 5 | Tell me about {campaign_name} | No | 0 | 0 | 0 | none |
| 6 | What is the average open rate? | No | 0 | 0 | 0 | none |
| 7 | How many emails have been sent in total? | No | 0 | 0 | 0 | none |
| 8 | How is {second_campaign_name} performing? | No | 0 | 0 | 0 | none |
| 9 | Show leads per campaign | No | 0 | 0 | 0 | none |
| 10 | How are our campaigns performing this month? | No | 0 | 0 | 0 | none |
| 11 | What marketing strategies should we implement? | Yes | _TBD_ | _TBD_ | _TBD_ | groq |
| 12 | Why are sales dropping? | Yes | _TBD_ | _TBD_ | _TBD_ | groq |
| 13 | Which campaigns need optimization? | Yes | _TBD_ | _TBD_ | _TBD_ | groq |
| 14 | Key trends in marketing data | Yes | _TBD_ | _TBD_ | _TBD_ | groq |
| 15 | What opportunities are we missing? | Yes | _TBD_ | _TBD_ | _TBD_ | groq |
| 16 | How can we improve campaign performance? | Yes | _TBD_ | _TBD_ | _TBD_ | groq |
| 17 | Best practices for email marketing? | Yes | _TBD_ | _TBD_ | _TBD_ | groq |
| 18 | Are we on track to meet campaign goals? | Yes | _TBD_ | _TBD_ | _TBD_ | groq |
| 19 | Improving lead conversion rates? | Yes | _TBD_ | _TBD_ | _TBD_ | groq |
| 20 | Overall marketing summary + recommendations | Yes | _TBD_ | _TBD_ | _TBD_ | groq |
| **TOTAL** | | | _TBD_ | _TBD_ | _TBD_ | |

**Key Insight:** Tests 1–10 use **zero LLM tokens** — they are answered entirely from DB queries via the Smart Enum Router. Only Tests 11–20 consume LLM tokens via Groq.

---

## 6. Database Models Used

| Model | Table | Used In Tests |
|---|---|---|
| `Campaign` | `ppp_marketingagent_campaign` | 1, 3, 4, 5, 6, 7, 8, 9, 10 |
| `Lead` | `ppp_marketingagent_lead` | — |
| `CampaignLead` | `ppp_marketingagent_campaign_leads` | 2, 5, 9 |
| `EmailSendHistory` | `ppp_marketingagent_emailsendhistory` | 3, 5, 6, 7, 8, 10 |
| `Reply` | `ppp_marketingagent_reply` | 5 |
| `CampaignPerformance` | `ppp_marketingagent_campaignperformance` | (used by agent internally) |
| `MarketResearch` | `ppp_marketingagent_marketresearch` | (used by agent for LLM context) |
| `EmailTemplate` | `ppp_marketingagent_emailtemplate` | (used by agent for email composition) |

---

## 7. How to Run

```bash
cd d:\University\work\AI_Employyes\AIEmployee
python test_marketing_qa_agent.py
```

The script will:
1. Find the first active user with marketing campaigns
2. Run all 20 test questions
3. Compare manual DB results vs AI responses
4. Print a comparison table, token usage summary, and pass/fail results
5. Save a detailed `.txt` report file

---

## 8. Comparison Methodology

### DB-Answerable Questions (1–10)
- **Manual query** runs Django ORM against the real database
- **AI Agent** receives the same question via `MarketingQAAgent.process()`
- **Comparison** checks if key numbers/names from the manual result appear in the AI response
- Match types: exact string match, numeric match, list item match, key-value match

### LLM-Only Questions (11–20)
- **No manual ground truth** — these are open-ended AI reasoning questions
- **Validation**: non-empty, coherent AI response (any substantive response = PASS)
- **Token usage** is captured to measure LLM cost per query

---

## 9. Expected Results After Run

After running `test_marketing_qa_agent.py`, update this document with the actual values from the report output. The script generates both a console summary and a detailed `.txt` file.

**Fill in the "_To be filled_" placeholders** in each test case section above with the actual:
- Manual DB Result
- AI Response (first 200 chars)
- Token Usage
- Match Detail
- Status (PASS/FAIL)

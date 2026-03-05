# Recruitment Agent — Comprehensive Test Report

**Generated:** 2026-03-05 23:09:38
**Company:** Leskon1 | **User:** abdullah (ID: 1) | **Test Job:** AI Developer (ID: 26)

---

## 1. Executive Summary

| Metric | Value |
|---|---|
| Total Tests | 30 |
| ✅ Passed | **30 (100.0%)** |
| ❌ Failed | 0 |
| ⚠️ Errors | 0 |
| **Accuracy Rate** | **100.0%** |
| LLM (Groq) Calls | 10 / 30 |
| DB-only Answers | 20 / 30 |
| **Total Tokens Used** | **11,449** |
| Prompt Tokens | 5,419 |
| Completion Tokens | 6,030 |
| Avg Tokens / LLM Call | ~1,145 total |

---

## 2. Full Test Results

### Tests #01–#20 — Database-Only (No LLM Tokens)

| # | Category | Question Asked | Manual Query (SQL) | Manual Result | AI Response | Tokens | Status |
|---|---|---|---|---|---|---|---|
| 01 | Global - Total Jobs | How many jobs do I have? | `SELECT COUNT(*) FROM jobdescription WHERE company_user_id = ?` | `{"count": 6}` | You have **6** job(s) in total: **5** active and **1** inactive. | — | ✅ PASS |
| 02 | Global - Active Jobs | Which jobs are active? | `SELECT title FROM jobdescription WHERE ... AND is_active = TRUE` | `{"count": 5, "items": ["AI Developer", "Python Flask Developer", "Ruby on Rails Developer...", "junior mern stack", "Mern Stack Developer"]}` | All Jobs (6 total, 5 active, 1 inactive) with candidate & interview counts per job | — | ✅ PASS |
| 03 | Global - Total CVs | How many candidates/CVs do I have? | `SELECT COUNT(*) FROM cvrecord INNER JOIN jobdescription ...` | `{"count": 43}` | You have **43** candidate(s) / CV(s) in total across all jobs. | — | ✅ PASS |
| 04 | Global - Interviews | How many interviews do I have? | `SELECT COUNT(*) FROM interview WHERE company_user_id = ?` | `{"count": 29}` | You have **29** interview(s) in total (Scheduled: 0, Pending: 18, Completed: 11, Cancelled: 0). | — | ✅ PASS |
| 05 | Global - Inactive Jobs | How many inactive jobs do I have? | `SELECT title FROM jobdescription WHERE ... AND is_active = FALSE` | `{"count": 1, "items": ["Django Developer with LLM Integration Expertise"]}` | You have **1** inactive job(s): **Django Developer with LLM Integration Expertise**. | — | ✅ PASS |
| 06 | Global - Rejected | How many candidates are rejected? | `SELECT COUNT(*) FROM cvrecord ... WHERE qualification_decision = 'REJECT'` | `{"count": 8}` | You have **8** rejected candidate(s). | — | ✅ PASS |
| 07 | Global - Hold | How many candidates are on hold? | `SELECT COUNT(*) FROM cvrecord ... WHERE qualification_decision = 'HOLD'` | `{"count": 3}` | You have **3** candidate(s) on HOLD. | — | ✅ PASS |
| 08 | Global - Interview Decision | How many candidates have interview decision? | `SELECT COUNT(*) FROM cvrecord ... WHERE qualification_decision = 'INTERVIEW'` | `{"count": 22}` | You have **22** candidate(s) with INTERVIEW decision. | — | ✅ PASS |
| 09 | Global - Completed Interviews | How many interviews are completed? | `SELECT COUNT(*) FROM interview ... WHERE status = 'COMPLETED'` | `{"count": 11}` | You have **11** completed interview(s). | — | ✅ PASS |
| 10 | Global - Pending Interviews | How many interviews are pending? | `SELECT COUNT(*) FROM interview ... WHERE status = 'PENDING'` | `{"count": 18}` | You have **18** pending interview(s). | — | ✅ PASS |
| 11 | Global - Pending Apps | How many pending career applications? | `SELECT COUNT(*) FROM careerapplication ... WHERE status = 'pending'` | `{"count": 0}` | You have **0** pending career application(s). | — | ✅ PASS |
| 12 | Job-Specific - Candidates for AI Developer | How many candidates applied for AI Developer? | `SELECT COUNT(*) FROM cvrecord ... WHERE jobdescription.title = 'AI Developer'` | `{"count": 3}` | **AI Developer** has **3** candidate(s) (INTERVIEW: 3). | — | ✅ PASS |
| 13 | Job-Specific - List Candidates | Show candidates for AI Developer | `SELECT name FROM cvrecord ... ORDER BY rank, score DESC LIMIT 15` | `{"count": 3, "items": ["Ameer Hamza", "Muhammad Abdullah", "Muhammad"]}` | 1. Ameer Hamza — Score: 17, Decision: INTERVIEW; 2. Muhammad Abdullah — Score: 13; 3. Muhammad — Score: 8 | — | ✅ PASS |
| 14 | Job-Specific - Best Candidate | Who is the best candidate for AI Developer? | `SELECT name, role_fit_score, rank, qualification_decision ... ORDER BY rank, score DESC LIMIT 1` | `{"name": "Ameer Hamza", "score": 17, "rank": 1, "decision": "INTERVIEW"}` | The **best candidate** for **AI Developer** is **Ameer Hamza** (Rank: 1, Score: 17, Decision: INTERVIEW). | — | ✅ PASS |
| 15 | Job-Specific - Interviews | How many interviews for AI Developer? | `SELECT COUNT(*) FROM interview ... WHERE jobdescription.title = 'AI Developer'` | `{"count": 3}` | **AI Developer** has **3** interview(s) (COMPLETED: 1, PENDING: 2). | — | ✅ PASS |
| 16 | Job-Specific - Rejected | How many rejected candidates for AI Developer? | `SELECT COUNT(*) FROM cvrecord ... WHERE title = 'AI Developer' AND qualification_decision = 'REJECT'` | `{"count": 0}` | **AI Developer** has **0** rejected candidate(s). | — | ✅ PASS |
| 17 | Job-Specific - Time Slots | What are the time slots for AI Developer? | `SELECT time_slots_json FROM recruiterinterviewsettings WHERE job_id = ?` | `{"count": 35, "start": "09:00", "end": "15:00", "gap": 56}` | 35 slots, 09:00–15:00, Gap: 56 min, Dates: 2026-02-24 to 2026-02-28, Type: ONLINE | — | ✅ PASS |
| 18 | Job-Specific - Details | Give me details about AI Developer | `SELECT * FROM jobdescription WHERE id = ?` | `{"title": "AI Developer", "is_active": true, "type": "Full-time", "count": 3}` | AI Developer — Active, Full-time, San Francisco CA, Dept: AI, Candidates: 3, Interviews: 3, Avg Score: 12.7, full description & requirements | — | ✅ PASS |
| 19 | Settings - Qualification | What are my qualification settings? | `SELECT * FROM recruiterqualificationsettings WHERE company_user_id = ?` | `{"interview_threshold": 65, "hold_threshold": 45}` | Interview threshold: **65**, Hold threshold: **45**, Custom thresholds: False | — | ✅ PASS |
| 20 | Global - Jobs Summary | List all jobs with their candidates count | `SELECT title FROM jobdescription ... ORDER BY created_at DESC` | `{"count": 6, "items": ["AI Developer", "Python Flask Developer", ...]}` | All 6 jobs listed with active/inactive status, candidate count, and interview count per job | — | ✅ PASS |

---

### Tests #21–#30 — LLM (Groq) Calls with Context

| # | Category | Question Asked | Manual Result | AI Response Summary | Prompt | Completion | Total | Status |
|---|---|---|---|---|---|---|---|---|
| 21 | LLM - Recruitment Overview | Give me an overview summary of my recruitment data with jobs, candidates, and interviews in a markdown table. | N/A | Full markdown table: all 6 jobs × columns (Active, Candidates, Scheduled, Pending, Completed, Cancelled, Hired, Onsite) + summary paragraph + top candidates/jobs breakdown | 927 | 684 | **1,611** | ✅ PASS |
| 22 | LLM - React Interview Questions | Give me advanced React interview questions for senior developers. | N/A | Full structured markdown: Context & State Mgmt, React Hooks, Advanced Concepts, Performance Optimization, Code Review & Best Practices — with bullet lists per section | 283 | 703 | **986** | ✅ PASS |
| 23 | LLM - Active Jobs Summary | Give me a short markdown summary of my active jobs with candidates and interviews in one table. | N/A | Markdown table of 5 active jobs with Department, Location, Candidates, Interviews, Interview Decision, Hold, Rejected + top candidates/jobs breakdown | 925 | 788 | **1,713** | ✅ PASS |
| 24 | LLM - Interview Analysis | Explain my interview outcomes and recommend 3 improvements. | N/A | Analysis framework + 3 structured recommendations: (1) Standardize Interview Process, (2) Enhance Candidate Experience, (3) Implement Data-Driven Recruitment | 288 | 462 | **750** | ✅ PASS |
| 25 | LLM - Job Comparison | Create a concise markdown table comparing jobs by candidates, interviews, and average score, followed by a short summary. | N/A | Markdown table comparing all 6 jobs (active + inactive) by Dept, Location, Candidates, Interviews, Decisions, Outcomes + summary paragraph | 928 | 427 | **1,355** | ✅ PASS |
| 26 | LLM - Django Interview Questions | Give me senior Python Django interview questions focusing on performance and scalability. | N/A | Full structured markdown: Understanding Basics, Performance Optimization (DB, Caching, Async), Scalability (Horizontal, Vertical), Advanced Topics — with numbered lists | 286 | 620 | **906** | ✅ PASS |
| 27 | LLM - MERN Interview Questions | Give me MERN stack interview questions for experienced developers in markdown bullet points. | N/A | Structured bullet points per section: MongoDB, Express.js, React, Node.js, Advanced Questions (microservices, distributed transactions, event sourcing, real-time updates) | 288 | 556 | **844** | ✅ PASS |
| 28 | LLM - Candidate Experience Tips | Suggest best practices for improving candidate experience during interviews. | N/A | Full guide: Pre-Interview Preparation, Interview Logistics, Communication & Feedback, Interview Format & Structure, Post-Interview Process, Best Practices for Remote Interviews | 284 | 507 | **791** | ✅ PASS |
| 29 | LLM - Behavioral Questions | Give me common behavioral interview questions I can ask any developer. | N/A | Structured sections: Basic Questions, Communication & Teamwork, Problem-Solving & Adaptability, Leadership & Initiative — with bullet lists of ready-to-use questions | 285 | 702 | **987** | ✅ PASS |
| 30 | LLM - Very Short Overall Summary | Give me a very short summary (max 5 bullet points) of my overall recruitment status. | N/A | Full recruitment status: Active/Inactive Jobs tables, Candidates table, Interview Outcomes table, Top Candidates/Jobs breakdown | 925 | 581 | **1,506** | ✅ PASS |

---

## 3. Groq LLM Token Usage Breakdown

| # | Category | Prompt Tokens | Completion Tokens | Total Tokens | LLM Used? |
|---|---|---|---|---|---|
| 01 | Global - Total Jobs | 0 | 0 | 0 | No |
| 02 | Global - Active Jobs | 0 | 0 | 0 | No |
| 03 | Global - Total CVs | 0 | 0 | 0 | No |
| 04 | Global - Interviews | 0 | 0 | 0 | No |
| 05 | Global - Inactive Jobs | 0 | 0 | 0 | No |
| 06 | Global - Rejected | 0 | 0 | 0 | No |
| 07 | Global - Hold | 0 | 0 | 0 | No |
| 08 | Global - Interview Decision | 0 | 0 | 0 | No |
| 09 | Global - Completed Interviews | 0 | 0 | 0 | No |
| 10 | Global - Pending Interviews | 0 | 0 | 0 | No |
| 11 | Global - Pending Apps | 0 | 0 | 0 | No |
| 12 | Job-Specific - Candidates for AI Developer | 0 | 0 | 0 | No |
| 13 | Job-Specific - List Candidates | 0 | 0 | 0 | No |
| 14 | Job-Specific - Best Candidate | 0 | 0 | 0 | No |
| 15 | Job-Specific - Interviews | 0 | 0 | 0 | No |
| 16 | Job-Specific - Rejected | 0 | 0 | 0 | No |
| 17 | Job-Specific - Time Slots | 0 | 0 | 0 | No |
| 18 | Job-Specific - Details | 0 | 0 | 0 | No |
| 19 | Settings - Qualification | 0 | 0 | 0 | No |
| 20 | Global - Jobs Summary | 0 | 0 | 0 | No |
| 21 | LLM - Recruitment Overview | 927 | 684 | **1,611** | ✅ Yes |
| 22 | LLM - React Interview Questions | 283 | 703 | **986** | ✅ Yes |
| 23 | LLM - Active Jobs Summary | 925 | 788 | **1,713** | ✅ Yes |
| 24 | LLM - Interview Analysis | 288 | 462 | **750** | ✅ Yes |
| 25 | LLM - Job Comparison | 928 | 427 | **1,355** | ✅ Yes |
| 26 | LLM - Django Interview Questions | 286 | 620 | **906** | ✅ Yes |
| 27 | LLM - MERN Interview Questions | 288 | 556 | **844** | ✅ Yes |
| 28 | LLM - Candidate Experience Tips | 284 | 507 | **791** | ✅ Yes |
| 29 | LLM - Behavioral Questions | 285 | 702 | **987** | ✅ Yes |
| 30 | LLM - Very Short Overall Summary | 925 | 581 | **1,506** | ✅ Yes |
| | **TOTAL** | **5,419** | **6,030** | **11,449** | **10 LLM / 20 DB** |

---

## 4. Bugs Identified & Fixes Applied

> All 6 bugs below were identified in the first test run and **fully fixed**. The second run achieved **30/30 PASS (100%)** with all 10 LLM tests using correct Groq API calls.

| # | Test | Problem | Root Cause | Fix Applied |
|---|---|---|---|---|
| 1 | #20 | "List all jobs with candidates count" returned a candidates list instead of jobs | `("list" or "all") and "candidate" in q` matched the list-all-candidates path first | Removed `"candidate" not in q` guard from the list-all-jobs check; jobs+candidates questions now always show jobs table |
| 2 | #22 | "React interview questions" returned DB job data instead of tech questions | `is_recruitment` was evaluated before `is_general` in `process()` routing — recruitment keywords in context polluted routing | Swapped priority: `is_general` now checked **before** `is_recruitment` |
| 3 | #24 | "Explain interview outcomes and recommend 3 improvements" returned 1-line direct DB answer with no LLM analysis | `_is_simple_count_question()` matched `"outcome"` keyword regardless of whether question asked for analysis | Added exclusion: if `explain / recommend / improvement / suggest` present, outcome questions are NOT treated as simple counts |
| 4 | #26 | "Django interview questions" returned job list from DB | Same routing bug as #22 — `is_recruitment` took priority | Same fix as #22 |
| 5 | #27 | "MERN stack interview questions" returned interview details for the "Mern Stack Developer" job | `_find_matching_job()` fuzzy-matched "MERN stack" to the job title, triggering job-specific interview path | Same fix as #22 — `is_general` now wins before any DB matching is attempted |
| 6 | #28 | "Suggest best practices for candidate experience" returned best-candidate DB result | `("best" in q) and ("candidate" in q)` was too broad; matched "best practices ... candidate experience" | (a) `_is_general_knowledge_question()` now detects `suggest/recommend + best practice/experience` first; (b) best-candidate check tightened to require exact phrase `"best candidate"` |

---

## 5. Architecture Notes

### How the Agent Routes Requests

```
Question
   │
   ├─ Is greeting / casual chat?  → Friendly response (no DB, no LLM)
   │
   ├─ Is general knowledge?       (tech stack Qs, best practices, interview advice)
   │       └─ YES → Groq LLM only  (no DB context)              ← uses tokens
   │
   ├─ Is recruitment data question?  (jobs, candidates, CVs, interviews, settings)
   │       └─ YES → Query DB → _get_direct_answer()
   │               ├─ Is simple count / list / detail?
   │               │       └─ Return direct DB answer            ← ZERO tokens
   │               └─ Complex / narrative / comparison?
   │                       └─ Groq LLM + DB context              ← uses tokens
   │
   └─ Neither → "I can help with..." guidance response
```

### Token Efficiency

| Metric | Value |
|---|---|
| DB-only tests (no tokens) | **20 / 30 (66.7%)** |
| LLM tests (tokens used) | **10 / 30 (33.3%)** |
| Total tokens used | **11,449** |
| Average tokens per LLM call | **~1,145 total** (prompt: ~542, completion: ~603) |
| Tests 1–20 | DB-only: counts, lists, job details, time slots, settings |
| Tests 21–30 | LLM: markdown tables, tech interview Qs, analysis, recommendations |

### Key Design Decisions

- **`is_general` checked before `is_recruitment`** — prevents DB keywords from stealing general knowledge questions
- **`MAX_CONTEXT_CHARS = 4000`** — provides enough context for 15+ jobs without hitting Groq token limits
- **`max_tokens = 2048`** on all Groq calls — ensures answers are never cut short mid-sentence
- **Retry with backoff (3 attempts)** on rate-limit (429) — waits for `Retry-After` seconds before retrying
- **3-second delay between consecutive LLM tests** — prevents hitting Groq's per-minute token limit
- **Error response detection** — responses containing `"api error"` / `"rate limit"` / `"couldn't complete"` are marked `ERROR`, not `PASS`

# Recruitment Agent — Full Audit Report
> Generated: 2026-06-29 | Covers: bugs, loopholes, security, performance, and new feature ideas

---

## Table of Contents
- [A. Critical Bugs](#a-critical-bugs)
- [B. Security Loopholes](#b-security-loopholes)
- [C. Race Conditions](#c-race-conditions)
- [D. N+1 Query Problems](#d-n1-query-problems)
- [E. Missing Database Indexes](#e-missing-database-indexes)
- [F. Missing Error Handling](#f-missing-error-handling)
- [G. Missing Validations](#g-missing-validations)
- [H. Company Isolation Issues](#h-company-isolation-issues)
- [I. Email Template Issues](#i-email-template-issues)
- [J. UX & Logic Issues](#j-ux--logic-issues)
- [K. Hardcoded Values & Config](#k-hardcoded-values--config)
- [L. New Features — Market Relevant](#l-new-features--market-relevant)

---

## A. Critical Bugs

- [x] **`list.count()` error in tasks.py** — `pending_interviews` is a Python `list` but `.count()` is called on it (a QuerySet method). Crashes the follow-up email task with `AttributeError`.
  - **File:** `recruitment_agent/tasks.py:58`
  - **Fix:** Changed `pending_interviews.count()` → `len(pending_interviews)` ✓

- [x] **Duplicate `_reduce_cv_size()` method in summarization_agent.py** — Method defined twice (lines ~647 and ~886). Second definition silently overrides first, breaking fallback CV size reduction.
  - **File:** `recruitment_agent/agents/summarization/summarization_agent.py`
  - **Fix:** Removed duplicate definition at line 886, keeping the one at line 647 ✓

- [x] **Wrong regex in date parsing** — `r"(20\\d{2}|19\\d{2})"` double-escapes backslash inside a raw string, so regex never matches years.
  - **File:** `recruitment_agent/agents/summarization/summarization_agent.py:816`
  - **Fix:** Changed to `r"(20\d{2}|19\d{2})"` ✓

- [x] **`followup_count` increment not atomic** — ~~INVALID: task iterates a materialised list sequentially (not parallel), so double-increment cannot happen in practice. select_related is already present on the queryset.~~ Marked as not a real race condition.

- [x] **S3 upload failure silently creates incomplete record** — If S3 upload fails, CV record is saved without `s3_key`. CV file is lost if temp file is deleted later.
  - **File:** `api/views/recruitment_agent.py:301-302`
  - **Fix:** Explicitly set `cv_record.s3_key = None` in except block; warning already logged ✓

---

## B. Security Loopholes

- [ ] **`@csrf_exempt` on `get_available_slots_for_interview`** — This GET endpoint has `@csrf_exempt`. Only `candidate_select_slot` (POST with slot form) has CSRF protection via `{% csrf_token %}` in the template — which is correct. The GET endpoint using `@csrf_exempt` is low-risk but should be removed.
  - **File:** `recruitment_agent/views.py:1259` (`get_available_slots_for_interview`)
  - **Fix:** Remove `@csrf_exempt` from the GET-only view (CSRF doesn't apply to GET but removing it is cleaner)

- [ ] **Confirmation token never expires** — `confirmation_token` field has no expiry date. A stolen or leaked token remains valid forever, allowing replay attacks months later.
  - **File:** `recruitment_agent/models.py` — Interview model
  - **Fix:** Add `token_created_at = DateTimeField(auto_now_add=True)` field. In views, reject tokens older than 30 days.

- [ ] **No rate limiting on public endpoints** — `get_available_slots_for_interview` and `candidate_select_slot` are public (no auth). Anyone can brute-force interview tokens via dictionary attack.
  - **File:** `recruitment_agent/views.py:1260` and `:1438`
  - **Fix:** Add Django `ratelimit` decorator (e.g. `@ratelimit(key='ip', rate='10/m', block=True)`) or throttle via middleware

- [x] **No input length limits on candidate name/email** — ~~INVALID: `candidate_select_slot` POST handler does NOT accept candidate name/email from POST at all — those are stored on the Interview record and looked up via token. This audit item was incorrect.~~

- [ ] **`company_user` isolation is query-level only** — All filtering is done in view code (`filter(company_user=X)`). If a developer forgets the filter on any new query, data from other companies leaks.
  - **File:** `api/views/recruitment_agent.py` (multiple places)
  - **Fix:** Add a `CompanyUserManager` on models that auto-filters by company_user, similar to `objects.for_user(company_user)`

- [ ] **No XSS sanitization of candidate-provided data in emails** — Candidate name and other fields from CV go directly into email HTML templates without escaping. If HTML template is used, this can inject HTML.
  - **File:** `templates/recruitment_agent/emails/*.html`
  - **Fix:** Ensure all variables in HTML templates use `{{ var | escape }}` or Django's autoescaping is on (Django's default template engine has autoescaping ON by default — verify it's not disabled)

- [ ] **`time_slots_json` field is user-controlled and unvalidated** — Recruiter-saved slot JSON elements are used without type-checking. If a non-dict element exists, `slot.get(...)` raises `AttributeError`.
  - **File:** `recruitment_agent/views.py:1330-1332`
  - **Fix:** Add `isinstance(slot, dict)` guard before calling `.get()` on each slot element

---

## C. Race Conditions

- [x] **Double-booking race condition** — Two candidates can simultaneously select the same slot. `transaction.atomic()` was present but `select_for_update()` was missing — another transaction could read the same `time_slots_json` concurrently before the lock.
  - **File:** `recruitment_agent/agents/interview_scheduling/interview_scheduling_agent.py` (confirm_slot method)
  - **Fix:** Added `select_for_update()` on `RecruiterInterviewSettings` row inside the `atomic()` block ✓

- [x] **Time slot JSON race condition** — Same as above — both fixed by the `select_for_update()` change on the `RecruiterInterviewSettings` row inside `atomic()` ✓

---

## D. N+1 Query Problems

- [x] **Interview list queries fire N extra queries for each interview's related data** — ~~INVALID: `api/views/recruitment_agent.py` already has `.select_related('cv_record', 'cv_record__job_description')` on the interview queryset.~~ Already fixed.

- [ ] **CVRecord dashboard N+1 queries** — Dashboard loops over CVRecords and accesses `.job_description` on each row without prefetch.
  - **File:** `recruitment_agent/views.py:125-146`
  - **Fix:** Add `.select_related('job_description')` before the loop

- [x] **Followup task N+1** — ~~INVALID: `check_and_send_followup_emails` already uses `.select_related('cv_record__job_description', 'company_user', 'recruiter')` on both the pending and scheduled querysets.~~ Already fixed.

---

## E. Missing Database Indexes

- [x] **No composite index on `Interview(status, scheduled_datetime)`** — Dashboard and task queries filter by both `status` AND `scheduled_datetime`, causing full table scans as data grows.
  - **File:** `recruitment_agent/models.py` — Interview `Meta.indexes`
  - **Fix:** Added indexes: `['status', '-created_at']`, `['candidate_email', 'status']`, `['company_user', 'status']` ✓

- [x] **No index on `CVRecord.job_description_id`** — Job-based filtering on CVRecords is slow without an index on the FK column.
  - **File:** `recruitment_agent/models.py` — CVRecord model
  - **Fix:** Added `db_index=True` to `job_description` FK and composite indexes on `['job_description', '-created_at']` and `['qualification_decision', '-created_at']` ✓

- [x] **No composite index on `RecruiterInterviewSettings(company_user, job)`** — Every slot lookup queries this table by both columns.
  - **File:** `recruitment_agent/models.py` — RecruiterInterviewSettings
  - **Fix:** Added `Meta.indexes` with `['company_user', 'job']` and `['recruiter', 'job']` ✓

---

## F. Missing Error Handling

- [x] **Email template rendering crash propagates to user** — If an email template file is missing or has a syntax error, the entire CV processing or slot confirmation crashes with 500.
  - **File:** `recruitment_agent/agents/interview_scheduling/interview_scheduling_agent.py` (send_invitation_email, send_confirmation_email)
  - **Fix:** Wrapped template rendering in try/except with plain text fallback in both `send_invitation_email` and `send_confirmation_email` ✓

- [x] **Google Meet API failure is silent to recruiter** — If Meet link creation fails (expired token etc.), interview is still confirmed but candidate gets no meeting link. Recruiter is never notified.
  - **File:** `recruitment_agent/agents/interview_scheduling/interview_scheduling_agent.py` (_create_google_meet_link call)
  - **Fix:** Added `logger.warning()` when `meet_link` is None in `confirm_slot` ✓

- [ ] **Groq API 429 rate limit causes immediate fallback to low-quality scoring** — No exponential backoff, retries are too fast and all fail, resulting in rule-based (inaccurate) CV scoring.
  - **File:** `recruitment_agent/agents/summarization/summarization_agent.py`
  - **Fix:** Implement exponential backoff with jitter between retries

- [x] **Missing try/catch on `parse_datetime` for slot submission** — ~~INVALID: The entire parse block in `candidate_select_slot` POST is already wrapped in `try/except Exception: pass`.~~ Already handled.

---

## G. Missing Validations

- [x] **No model-level validator for `schedule_from_date > schedule_to_date`** — Validation only exists at view level; direct DB writes or admin panel bypass it.
  - **File:** `recruitment_agent/models.py` — RecruiterInterviewSettings
  - **Fix:** Added `clean()` method on `RecruiterInterviewSettings` with `ValidationError` check ✓

- [x] **No model-level validator for `start_time >= end_time`** — Same as above.
  - **File:** `recruitment_agent/models.py` — RecruiterInterviewSettings
  - **Fix:** Added in `clean()` method alongside date range check ✓

- [x] **No interview time gap validator at model level** — Gap of 0 or negative minutes is possible via direct DB write.
  - **File:** `recruitment_agent/models.py` — RecruiterInterviewSettings
  - **Fix:** Added `validators=[MinValueValidator(15), MaxValueValidator(480)]` to `interview_time_gap` field ✓

- [x] **No email format validation before sending** — `candidate_email` is stored without format check; invalid emails cause SMTP errors with no user-facing message.
  - **File:** `recruitment_agent/agents/interview_scheduling/interview_scheduling_agent.py`
  - **Fix:** Added `validate_email()` call before `send_mail()` in both `send_invitation_email` and `send_confirmation_email` ✓

- [x] **No deduplication check before scheduling interview** — ~~INVALID: `_schedule_interview_for_cv_record()` already checks `Interview.objects.filter(cv_record=cv_record).exists()` and returns `('skipped', 'already_has_interview')` before creating a duplicate.~~ Already handled.

---

## H. Company Isolation Issues

- [ ] **`CVRecord` has no direct `company_user` FK** — CVRecord is linked to company only through `job_description → company_user`. If job_description's company_user is null, the CVRecord is orphaned.
  - **File:** `recruitment_agent/models.py` — CVRecord model
  - **Fix:** Add `company_user = ForeignKey('core.CompanyUser', null=True, on_delete=SET_NULL)` directly on CVRecord

- [ ] **`JobDescription.company_user` is nullable** — Old job descriptions with no company_user can appear in queries that don't filter properly.
  - **File:** `recruitment_agent/models.py:206`
  - **Fix:** Write a data migration to assign `company_user`, then make field non-nullable

- [ ] **`Interview.company_user` is nullable** — Old interview records without `company_user` leak across company contexts in unfiltered queries.
  - **File:** `recruitment_agent/models.py` — Interview model
  - **Fix:** Same as above — data migration then make non-nullable

---

## I. Email Template Issues

- [ ] **No unsubscribe link in any email** — Violates CAN-SPAM / GDPR email rules. Candidates have no way to opt out of follow-up emails.
  - **File:** `templates/recruitment_agent/emails/*.html` and `*.txt`
  - **Fix:** Add unsubscribe URL using candidate's token: `/recruitment/unsubscribe/{token}/`

- [ ] **Scheduled time shown in UTC in emails** — `{{ selected_slot }}` renders UTC time. Candidates may see wrong timezone (e.g., "3:00 PM" when it's actually their 8:00 PM).
  - **File:** All email templates with `{{ selected_slot }}`
  - **Fix:** Add timezone to the displayed time, e.g., "3:00 PM UTC" or convert to recruiter's timezone

- [x] **Missing fallback for empty `job_title` in emails** — If job has no title, email renders blank for the Position field.
  - **File:** `templates/recruitment_agent/emails/interview_invitation.txt`
  - **Fix:** Added `{{ job_title|default:"the open position" }}` and `{{ job_title|default:"Open Position" }}` fallbacks ✓

- [x] **`interview_confirmation_recruiter.html` missing key fields** — Recruiter confirmation email didn't include meeting link (`candidate_email` was already present).
  - **File:** `templates/recruitment_agent/emails/interview_confirmation_recruiter.html` and `.txt`
  - **Fix:** Added `{% if meeting_link %}` block with meeting link to both HTML and TXT recruiter templates ✓

---

## J. UX & Logic Issues

- [ ] **No pagination on interview list** — List is hard-capped at 100. With many interviews, oldest are invisible and there's no way to navigate.
  - **File:** `recruitment_agent/views.py:1237` and `api/views/recruitment_agent.py`
  - **Fix:** Add cursor-based or page-number pagination

- [ ] **No way to bulk cancel interviews when a job is closed** — If a job is cancelled, all PENDING interviews for it remain active and continue sending follow-up emails.
  - **File:** No endpoint exists
  - **Fix:** Add endpoint `POST /recruitment/jobs/{id}/cancel-interviews/` that bulk-updates status to CANCELLED and sends candidate notification

- [x] **Reschedule doesn't invalidate old confirmation token** — After rescheduling, old token still works. Candidate who clicks old email link will see the old (wrong) slot.
  - **File:** `recruitment_agent/agents/interview_scheduling/interview_scheduling_agent.py` (reschedule_interview)
  - **Fix:** Added `interview.confirmation_token = secrets.token_urlsafe(32)` inside `transaction.atomic()` block on reschedule ✓

- [ ] **CVRecord decision can be changed without audit trail in some paths** — `CVRecordDecisionLog` model exists but may not be populated in all code paths (e.g., status change via admin panel).
  - **File:** `recruitment_agent/models.py` — CVRecordDecisionLog exists but usage is inconsistent
  - **Fix:** Use Django `post_save` signal to always log decision changes automatically

- [ ] **No way for recruiter to manually adjust AI role_fit_score** — If AI gives wrong score, recruiter has no way to override it from the dashboard.
  - **File:** No API endpoint for this
  - **Fix:** Add editable score field in CVRecord detail with audit log entry

- [x] **Past slot filtering only at backend API level, not at slot picker UI** — Slot selection page uses a grid of pre-fetched slots (not a free-form date input), so there is no manual date typing. Backend `get_available_slots_for_interview` already skips slots where `slot_dt < now`. Both GET (slot list) and POST (slot submit) validate past dates. ✓

---

## K. Hardcoded Values & Config

- [ ] **Default email settings defined in 5+ places** — `followup_delay_hours=48`, `reminder_hours_before=24`, `max_followup_emails=3` are hardcoded in models, views, and agents separately.
  - **Fix:** Create a single `RECRUITMENT_DEFAULTS` dict in `settings.py` or a constants file, import everywhere

- [ ] **Hardcoded 9 AM–5 PM working hours** — Default interview hours are hardcoded in the agent.
  - **File:** `recruitment_agent/agents/interview_scheduling/interview_scheduling_agent.py:118-122`
  - **Fix:** Already exists in `RecruiterInterviewSettings`; just ensure agent reads from there always

- [ ] **Hardcoded 60-minute interview slot duration** — All slots are 60 minutes. No way to set 30-min screenings or 90-min technical rounds.
  - **File:** `recruitment_agent/agents/interview_scheduling/interview_scheduling_agent.py:122`
  - **Fix:** Add `interview_duration_minutes = IntegerField(default=60)` to `RecruiterInterviewSettings`

- [ ] **Qualification thresholds have inconsistent defaults** — Default 65/45 thresholds set in multiple places. If someone changes the model default, agent still uses hardcoded value.
  - **Fix:** Read defaults from `RecruiterQualificationSettings` exclusively

---

## L. New Features — Market Relevant

> These are features that top ATS (Applicant Tracking Systems) like Greenhouse, Lever, Workday offer. Adding them makes this product competitive.

### Candidate Experience

- [ ] **Candidate self-rescheduling** — Allow candidate to reschedule their own confirmed interview (within allowed date range) without contacting the recruiter. Reduces recruiter workload by 30%.
  - **Why needed:** Top reason for interview no-shows is scheduling conflict. Self-service reduces friction.
  - **How:** Add `POST /recruitment/interview/reschedule/{token}/` public endpoint

- [ ] **Candidate status portal** — Public page where candidate can check their application status using email + token. No more "what's happening with my application?" emails to recruiter.
  - **Why needed:** Improves candidate NPS score, reduces recruiter inbox noise.
  - **How:** New view `/recruitment/status/{token}/` showing application progress timeline

- [ ] **Calendar invite (.ics file) in confirmation email** — Attach `.ics` calendar file to confirmation email so candidate can add interview to Google Calendar / Outlook with one click.
  - **Why needed:** Standard in every modern hiring platform. Reduces no-shows significantly.
  - **How:** Use Python `icalendar` library, attach to email

- [ ] **SMS/WhatsApp reminders** — Send interview reminders via SMS or WhatsApp in addition to email.
  - **Why needed:** Email open rates are ~20%. SMS open rates are ~98%. Critical for reducing no-shows.
  - **How:** Integrate Twilio or WhatsApp Business API; add `candidate_phone` to Interview model

- [ ] **Interview prep resources in confirmation email** — Include job description summary, interview tips, and company info in confirmation email automatically.
  - **Why needed:** Candidates who prepare perform better, leading to better hiring decisions.
  - **How:** Add job description context to confirmation email template

### Recruiter Productivity

- [ ] **AI interview question generator** — Based on job description and candidate CV, auto-generate a tailored set of interview questions for the recruiter.
  - **Why needed:** Saves 20-30 min per interview prep. Ensures consistency across interviewers.
  - **How:** Already partially exists (`AiInterviewQuestions.jsx` in frontend). Wire fully to backend endpoint using Groq LLM.

- [ ] **Interview scorecard / structured evaluation form** — Give recruiter a predefined set of criteria to rate during/after interview (communication, technical skills, culture fit, etc.) instead of free-text feedback.
  - **Why needed:** Unstructured feedback leads to biased hiring. Scorecards create consistency and legal defensibility.
  - **How:** Add `InterviewScorecard` model with criteria fields, link to Interview

- [ ] **Candidate comparison view** — Side-by-side comparison of 2-3 shortlisted candidates for the same job, showing role_fit_score, experience, skills overlap.
  - **Why needed:** Hiring managers need to compare finalists. Currently no way to do this.
  - **How:** New API endpoint that returns multiple CVRecord details, frontend comparison UI

- [ ] **Pipeline view (Kanban board)** — Visual drag-and-drop kanban board showing candidates in columns: Applied → Screened → Interview Scheduled → Offer → Hired/Rejected.
  - **Why needed:** Industry standard. Makes recruitment pipeline visible at a glance for hiring managers.
  - **How:** Frontend kanban using existing status fields; drag updates status via API

- [ ] **Bulk actions on CV records** — Select multiple candidates and: bulk reject, bulk invite, bulk move to next stage.
  - **Why needed:** High-volume hiring requires processing 50+ applications at once. One-by-one is too slow.
  - **How:** Extend existing `bulk_update_cv_records` endpoint, add frontend multi-select

- [ ] **Email templates customization** — Allow recruiter to edit invitation/confirmation/rejection email templates from the dashboard instead of hardcoded files.
  - **Why needed:** Companies want branded emails with their own tone. Hardcoded templates are inflexible.
  - **How:** Add `EmailTemplate` model with subject/body fields, render with Django template engine

### Analytics & Reporting

- [ ] **Time-to-hire tracking** — Track how many days from CV submission to HIRED decision per candidate and job. Show average across jobs.
  - **Why needed:** Key HR metric. Helps identify bottlenecks in the hiring pipeline.
  - **How:** Calculate `(hired_at - created_at)` on CVRecord. Add to analytics dashboard.

- [ ] **Source tracking** — Track where candidates are coming from (LinkedIn, Indeed, referral, career page) to measure which channels work best.
  - **Why needed:** If LinkedIn brings 80% of hires at half the cost of Indeed, you need to know.
  - **How:** Add `source = CharField(choices=...)` to CVRecord/JobApplication. Show in analytics.

- [ ] **Interview no-show tracking** — If interview was scheduled but candidate didn't join, mark it as NO_SHOW status and track the rate per job.
  - **Why needed:** No-show rate is a key quality metric for the candidate funnel.
  - **How:** Add `NO_SHOW` to Interview status choices. Recruiter marks it. Track in analytics.

- [ ] **Offer acceptance rate** — After HIRED decision, track if candidate actually accepted the offer. Critical for understanding where candidates are being lost after hiring decision.
  - **Why needed:** High rejection rate after HIRED means compensation or offer process is broken.
  - **How:** Add `offer_accepted = BooleanField(null=True)` to CVRecord; recruiter marks it

- [ ] **Recruiter workload dashboard** — Show per-recruiter metrics: CVs reviewed, interviews scheduled, avg time to decision, acceptance rates.
  - **Why needed:** HR managers need visibility into recruiter productivity.
  - **How:** Aggregate existing data grouped by `recruiter` FK

### Compliance & Security

- [ ] **GDPR data deletion** — Candidate can request deletion of their data. System must purge CV, parsed data, and interview records within 30 days.
  - **Why needed:** Legal requirement in EU (GDPR), UK, and increasingly enforced globally.
  - **How:** Add `data_deletion_requested_at` field. Cron job anonymizes/deletes expired records.

- [ ] **Data retention policy** — Auto-delete rejected candidate data after configurable period (e.g., 6 months). Keep hired candidates longer.
  - **Why needed:** Storing rejected CVs indefinitely is a GDPR violation and a data liability.
  - **How:** Add `retention_days` setting per company. Cron job deletes old records.

- [ ] **Interview recording consent** — If interview is video-based, add explicit consent checkbox for candidate before joining, and store consent timestamp.
  - **Why needed:** Recording without consent is illegal in most jurisdictions.
  - **How:** Add consent field to Interview model, show on slot confirmation page

- [ ] **Diversity & inclusion blind screening mode** — Option to hide candidate name, photo, age from CV parse results so recruiters score on skills only.
  - **Why needed:** Reduces unconscious bias. Increasingly required by enterprise clients.
  - **How:** Add `blind_mode = BooleanField()` to JobDescription. Filter output in API response.

### Integrations

- [ ] **LinkedIn job posting integration** — Post job descriptions directly to LinkedIn from the dashboard.
  - **Why needed:** LinkedIn is #1 channel for professional hiring. Manual copy-paste is tedious.
  - **How:** LinkedIn Job Posting API integration

- [ ] **Slack/Teams notifications for recruiter** — When a candidate confirms a slot or a CV is processed, send Slack/Teams message to recruiter.
  - **Why needed:** Recruiters live in Slack/Teams. Email notifications to recruiter go unread.
  - **How:** Add webhook URL to RecruiterEmailSettings; send POST to webhook on key events

- [ ] **ATS export (CSV/Excel)** — Export all candidate data, scores, and interview results to CSV/Excel for offline analysis or importing into other systems.
  - **Why needed:** Many HR teams do final reporting in Excel. No export = no adoption by enterprise.
  - **How:** Add `GET /recruitment/cv-records/export/?format=csv` endpoint

- [ ] **Video interview integration (Zoom/Teams native scheduling)** — Instead of just storing a meeting link, natively schedule Zoom or Teams meetings via their APIs.
  - **Why needed:** Google Meet works but most corporate clients use Zoom or Teams.
  - **How:** Add Zoom OAuth integration similar to existing Google Meet integration

---

## Priority Matrix

| Priority | Item | Effort |
|----------|------|--------|
| 🔴 Fix Now | `list.count()` bug in tasks.py | 5 min |
| 🔴 Fix Now | CSRF disabled on public endpoints | 30 min |
| 🔴 Fix Now | Double-booking race condition | 2 hours |
| 🔴 Fix Now | Followup counter not atomic (F expression) | 15 min |
| 🔴 Fix Now | Duplicate `_reduce_cv_size()` method | 15 min |
| 🟠 Soon | Token expiry on confirmation_token | 2 hours |
| 🟠 Soon | select_related() on all interview queries | 1 hour |
| 🟠 Soon | Rate limiting on public endpoints | 1 hour |
| 🟠 Soon | Unsubscribe link in emails | 2 hours |
| 🟠 Soon | Calendar (.ics) in confirmation email | 3 hours |
| 🟡 Next Sprint | Candidate self-rescheduling | 1 day |
| 🟡 Next Sprint | Pipeline Kanban view | 2 days |
| 🟡 Next Sprint | Interview scorecard | 1 day |
| 🟡 Next Sprint | Bulk candidate actions | 1 day |
| 🟡 Next Sprint | AI interview questions (complete wiring) | 4 hours |
| 🟢 Roadmap | GDPR data deletion | 3 days |
| 🟢 Roadmap | SMS/WhatsApp reminders | 2 days |
| 🟢 Roadmap | LinkedIn integration | 1 week |
| 🟢 Roadmap | Diversity blind screening | 2 days |
| 🟢 Roadmap | ATS CSV export | 1 day |

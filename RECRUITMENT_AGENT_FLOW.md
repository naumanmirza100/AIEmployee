# Recruitment Agent System - Complete Flow Documentation

## Overview
The Recruitment Agent is an AI-powered system that automates CV processing, candidate evaluation, and interview scheduling. It uses multiple specialized agents working together to parse CVs, analyze candidates, and automatically schedule interviews for qualified candidates.

---

## 🎯 Complete Flow: From CV Upload to Interview Assignment

### **Phase 1: CV Upload & Initial Processing**

#### 1.1 API Endpoint: `POST /api/recruitment/process-cvs/`
- **Location**: `api/views/recruitment_agent.py` → `process_cvs()`
- **Authentication**: Company User Token Authentication
- **Input**:
  - `files`: List of CV files (PDF, DOCX, TXT)
  - `job_description_id`: Optional job description ID
  - `job_description_text`: Optional job description text
  - `job_keywords`: Optional comma-separated keywords
  - `top_n`: Optional limit for top candidates
  - `parse_only`: Boolean flag to skip analysis

#### 1.2 Job Description Processing
- If `job_description_id` provided:
  - Fetches `JobDescription` from database
  - **Validates interview settings** are complete (required for auto-scheduling):
    - `schedule_from_date` and `schedule_to_date`
    - `start_time` and `end_time`
    - `time_slots_json` (must have slots)
  - Extracts `description` and `keywords_json` from job description
- If `job_description_text` provided:
  - Uses `JobDescriptionParserAgent` to extract keywords
- If `job_keywords` provided:
  - Parses comma-separated keywords into list
- **Result**: `job_kw_list` - normalized list of job requirement keywords

---

### **Phase 2: CV Parsing**

#### 2.1 File Processing
- **Agent**: `CVParserAgent` (`recruitment_agent/agents/cv_parser/cv_parser_agent.py`)
- **Process**:
  1. **File Type Detection**: Identifies PDF, DOCX, or TXT
  2. **Text Extraction**:
     - PDF: Uses `pdfplumber` to extract text from all pages
     - DOCX: Uses `python-docx` to extract paragraphs
     - TXT: Direct file read
  3. **Text Cleaning**: Normalizes whitespace, removes non-informative characters
  4. **Email Extraction**: 
     - First tries regex pattern matching
     - Falls back to spaCy NER (if available)
     - Ensures complete email addresses are captured

#### 2.2 LLM-Based Parsing
- **LLM**: Groq API (using `GroqClient`)
- **Prompt**: `CV_PARSING_SYSTEM_PROMPT` from `recruitment_agent/agents/cv_parser/prompts.py`
- **Extracts Structured Data**:
  ```json
  {
    "name": string,
    "email": string,
    "phone": string,
    "skills": [string],
    "experience": [{
      "role": string,
      "company": string,
      "start_date": string,
      "end_date": string,
      "description": string
    }],
    "education": [{
      "degree": string,
      "institution": string,
      "graduation_year": string
    }],
    "certifications": [{
      "name": string,
      "issuer": string,
      "year": string
    }],
    "summary": string
  }
  ```

#### 2.3 Data Normalization
- Validates all required fields exist
- Normalizes skills list (handles string/array formats)
- Normalizes experience, education, certifications
- Ensures consistent data types

#### 2.4 Storage
- **Repository**: `DjangoRepository.store_parsed()`
- Creates `CVRecord` in database:
  - `file_name`: Original filename
  - `parsed_json`: Full parsed CV data (JSON string)
  - `company_user`: Links to company user
  - `job_description`: Links to job (if provided)
- **Returns**: `record_id` for tracking

---

### **Phase 3: Summarization & Analysis**

#### 3.1 Summarization Agent
- **Agent**: `SummarizationAgent` (`recruitment_agent/agents/summarization/summarization_agent.py`)
- **Input**: Parsed CV + Job Keywords
- **Process**:

##### 3.1.1 LLM-Based Summarization (Primary)
- Uses Groq LLM with `SUMMARIZATION_SYSTEM_PROMPT`
- Generates intelligent analysis:
  - `candidate_summary`: Professional summary
  - `total_experience_years`: Calculated from experience dates
  - `key_skills`: Top 10 most relevant skills
  - `role_fit_score`: 0-100 score (primary ranking metric)
  - `notable_achievements`: Extracted achievements
  - `education_level`: Highest degree (PhD, Master, Bachelor, etc.)

##### 3.1.2 Manual Validation & Fallback
- **Experience Calculation**: Manual calculation from date ranges
  - Parses dates (handles "Present", "YYYY", "MMM YYYY" formats)
  - Calculates total months across all positions
  - Converts to years (rounded to 2 decimals)
- **Role Fit Score Validation**:
  - If LLM score seems unreasonable vs. skill match percentage:
    - Recalculates using manual method
    - Uses skill equivalences (Node.js ↔ JavaScript, etc.)
    - Considers: Skills match (80 pts max), Experience (8 pts max), Experience relevance (5 pts max)
- **Fallback**: If LLM fails, uses rule-based approach

##### 3.1.3 Skill Matching with Equivalences
- **File**: `recruitment_agent/skill_equivalences.py`
- **Function**: `skill_matches_keyword()` and `get_all_match_terms()`
- **Examples**:
  - "Node.js" ↔ "JavaScript" (bidirectional)
  - "React" ↔ "React.js" ↔ "ReactJS"
  - "MERN" → expands to MongoDB, Express, React, Node.js
  - "Python" → Django, Flask, FastAPI
- **Matching Logic**:
  1. Direct match
  2. Equivalence match (via `SKILL_EQUIVALENCES` dict)
  3. Substring match

#### 3.2 Output
- **Stored in**: `CVRecord.insights_json` (JSON string)
- **Key Fields**:
  - `role_fit_score`: **Primary ranking metric** (0-100)
  - `total_experience_years`
  - `key_skills`
  - `candidate_summary`
  - `education_level`
  - `notable_achievements`

---

### **Phase 4: Lead Enrichment**

#### 4.1 Enrichment Agent
- **Agent**: `LeadResearchEnrichmentAgent` (referenced but file not found in search)
- **Purpose**: Adds additional context to candidate profile
- **Input**: Parsed CV + Summary/Insights
- **Output**: Enriched data with:
  - `normalized_skills`: Standardized skill names
  - `primary_role`: Inferred primary role
  - `seniority_level`: Estimated seniority
  - `technical_depth_signals`: Technical indicators
  - `critical_skills`: Critical skills for role

#### 4.2 Storage
- **Stored in**: `CVRecord.enriched_json` (JSON string)

---

### **Phase 5: Qualification & Decision Making**

#### 5.1 Qualification Agent
- **Agent**: `LeadQualificationAgent` (`recruitment_agent/agents/lead_qualification/lead_qualification_agent.py`)
- **Input**: 
  - Parsed CV
  - Candidate Insights (summary)
  - Job Keywords
  - Enriched Data
  - **Custom Thresholds** (from `RecruiterQualificationSettings`):
    - `interview_threshold`: Default 65 (minimum for INTERVIEW decision)
    - `hold_threshold`: Default 45 (minimum for HOLD decision)
    - `use_custom_thresholds`: Boolean flag

#### 5.2 Skill Inference
- **Explicit Skills**: From CV skills list
- **Inferred Skills**: From context analysis:
  - MERN Stack → MongoDB, Express, React, Node.js
  - React Native → React
  - AI/LLM terms → LLMs, NLP, Transformers
  - Backend/API work → Node.js, API Design
  - Full Stack → Frontend + Backend Development
  - Leadership terms → Communication, Leadership
  - Docker → Containerization
  - CI/CD signals → CI/CD

#### 5.3 Matching with Inference
- Uses `skill_matches_keyword()` with equivalences
- Matches job keywords against:
  - Explicit skills
  - Inferred skills
- **Output**: 
  - `matched_skills`: List of matched keywords
  - `missing_skills`: List of unmatched keywords
  - `match_percentage`: (matched / total) * 100

#### 5.4 Decision Algorithm
- **Gating Rule**: 
  - If `matched_count < 3` OR `match_ratio < 0.35` → **REJECT** (confidence: 0)
- **Score Calculation**:
  1. **Base Score** (0-40):
     - Uses `role_fit_score` if available
     - Or calculates from match ratio
  2. **Skill Evidence** (0-30):
     - Explicit matched skills: 3 points each
     - Inferred skills: 1 point each
     - Max: 30 points
  3. **Match Quality** (0-30):
     - ≥80% match: 30 pts
     - ≥65% match: 22 pts
     - ≥50% match: 12 pts
     - ≥35% match: 5 pts
  4. **Experience Boost** (0-8):
     - ≥5 years: 8 pts
     - ≥3 years: 5 pts
     - ≥1 year: 2 pts
- **Final Score**: Base + Skill Evidence + Match Quality + Experience
- **Decision**:
  - Score ≥ `interview_threshold` (default 65) → **INTERVIEW**
  - Score ≥ `hold_threshold` (default 45) → **HOLD**
  - Score < `hold_threshold` → **REJECT**

#### 5.5 Priority Assignment
- **HIGH**: INTERVIEW + confidence ≥75 + experience ≥3 years
- **MEDIUM**: INTERVIEW (other cases)
- **LOW**: HOLD or REJECT

#### 5.6 Reasoning Generation
- Builds human-readable reasoning:
  - Decision and confidence
  - Job requirements match percentage
  - Matched skills list
  - Inferred skills
  - Experience years
  - Missing skills (if significant)
  - Strengths summary

#### 5.7 Storage
- **Stored in**: `CVRecord.qualification_json` (JSON string)
- **Fields Updated**:
  - `qualification_decision`: INTERVIEW/HOLD/REJECT
  - `qualification_confidence`: Final score (0-100)
  - `qualification_priority`: HIGH/MEDIUM/LOW

---

### **Phase 6: Ranking & Filtering**

#### 6.1 Ranking
- **Primary Metric**: `role_fit_score` from summary (NOT qualification confidence)
- **Sorting**: Descending by `role_fit_score`
- **Applied to**: All processed CVs

#### 6.2 Top N Filtering
- If `top_n` provided, limits results to top N candidates
- Updates `CVRecord.rank` field (1 = best, 2 = second, etc.)

#### 6.3 Final Results Structure
```json
{
  "file_name": "john_doe_cv.pdf",
  "record_id": 123,
  "parsed": {...},
  "summary": {
    "role_fit_score": 85,
    "total_experience_years": 5.5,
    "key_skills": ["Python", "Django", "React"],
    ...
  },
  "enriched": {...},
  "qualified": {
    "decision": "INTERVIEW",
    "confidence_score": 78,
    "priority": "HIGH",
    "matched_skills": ["Python", "Django", "React"],
    "match_percentage": 75,
    ...
  }
}
```

---

### **Phase 7: Auto-Interview Scheduling**

#### 7.1 Auto-Scheduling Trigger
- **Condition**: `qualification_decision == "INTERVIEW"` AND `candidate_email` exists
- **Location**: `api/views/recruitment_agent.py` → `process_cvs()` (lines 322-376)

#### 7.2 Interview Scheduling Agent
- **Agent**: `InterviewSchedulingAgent` (`recruitment_agent/agents/interview_scheduling/interview_scheduling_agent.py`)
- **Method**: `schedule_interview()`

#### 7.3 Email Settings Configuration
- **Source Priority**:
  1. Provided `email_settings` dict
  2. `RecruiterEmailSettings` for company user
  3. Default values:
     - `followup_delay_hours`: 48
     - `reminder_hours_before`: 24
     - `max_followup_emails`: 3
     - `min_hours_between_followups`: 24

#### 7.4 Interview Record Creation
- **Model**: `Interview` (`recruitment_agent/models.py`)
- **Fields**:
  - `candidate_name`, `candidate_email`, `candidate_phone`
  - `job_role`: Extracted from job description or keywords
  - `interview_type`: Default "ONLINE"
  - `status`: "PENDING" (awaiting candidate response)
  - `confirmation_token`: Unique secure token (32 bytes, URL-safe)
  - `cv_record`: Links to CVRecord
  - `company_user`: Links to company user
  - `available_slots_json`: Empty array (uses date-time picker)
  - Email timing preferences (from settings)

#### 7.5 Invitation Email
- **Template**: `templates/recruitment_agent/emails/interview_invitation.txt/html`
- **Subject**: "Interview Invitation - {job_role}"
- **Content**:
  - Candidate name
  - Job role
  - Interview type (ONLINE/ONSITE)
  - **Slot Selection URL**: `{domain}/recruitment/interview/select/{confirmation_token}/`
- **Sending**: Django `send_mail()` with HTML and plain text
- **Timestamp**: `invitation_sent_at` updated

#### 7.6 Response Tracking
- **Result**: 
  - `interview_scheduled`: true/false
  - `interview_id`: Interview record ID
  - `interview_error`: Error message if failed

---

### **Phase 8: Interview Management & Follow-ups**

#### 8.1 Django Signals (Automatic Follow-ups)
- **File**: `recruitment_agent/signals.py`
- **Signal**: `post_save` on `Interview` model
- **Handler**: `auto_check_interview_followups()`
- **Runs in**: Background thread (non-blocking)

#### 8.2 Follow-up Logic (PENDING Interviews)
- **Trigger Conditions**:
  - Status = "PENDING"
  - `invitation_sent_at` exists
  - Time since invitation ≥ `followup_delay_hours`
  - `followup_count < max_followup_emails`
  - Time since last follow-up ≥ `min_hours_between_followups`
- **Action**: 
  - Calls `interview_agent.send_followup_reminder(interview_id)`
  - Increments `followup_count`
  - Updates `last_followup_sent_at`
- **Email Template**: `interview_followup.txt/html`

#### 8.3 Pre-Interview Reminder (SCHEDULED Interviews)
- **Trigger Conditions**:
  - Status = "SCHEDULED"
  - `scheduled_datetime` exists and is in future
  - Within 2 hours of reminder time
  - `pre_interview_reminder_sent_at` is null
- **Reminder Time**: `scheduled_datetime - reminder_hours_before`
- **Action**:
  - Calls `interview_agent.send_pre_interview_reminder(interview_id, hours_before)`
  - Updates `pre_interview_reminder_sent_at`
- **Email Template**: `interview_pre_reminder.txt/html`

#### 8.4 Auto-Completion
- **Condition**: Interview is past (2+ hours ago) and status is PENDING/SCHEDULED
- **Action**: Auto-updates status to "COMPLETED"

---

### **Phase 9: Candidate Slot Selection**

#### 9.1 Slot Selection Page
- **URL**: `/recruitment/interview/select/{confirmation_token}/`
- **Access**: Public (token-based authentication)

#### 9.2 Slot Confirmation
- **Method**: `InterviewSchedulingAgent.confirm_slot()`
- **Process**:
  1. Validates `confirmation_token`
  2. Parses selected datetime (ISO format)
  3. **Validates against Interview Settings**:
     - Date within `schedule_from_date` to `schedule_to_date`
     - Time within `start_time` to `end_time`
     - Slot exists in `time_slots_json`
     - Slot is `available: true`
     - Slot is not already `scheduled: true`
  4. **Double-booking Check**: Queries existing interviews for same datetime
  5. **Atomic Transaction**:
     - Marks slot as `scheduled: true` in `time_slots_json`
     - Updates interview:
       - `status`: "SCHEDULED"
       - `scheduled_datetime`: Selected datetime
       - `selected_slot`: Human-readable format
  6. **Confirmation Emails**:
     - Candidate: Confirmation with interview details
     - Recruiter: Notification of scheduled interview

---

## 📊 Data Models

### **CVRecord**
- Stores parsed CV and all analysis results
- **Key Fields**:
  - `parsed_json`: Raw parsed data
  - `insights_json`: Summary/analysis
  - `enriched_json`: Enrichment data
  - `qualification_json`: Qualification decision
  - `role_fit_score`: Primary ranking score
  - `qualification_decision`: INTERVIEW/HOLD/REJECT
  - `qualification_confidence`: Decision confidence
  - `rank`: Final ranking position

### **Interview**
- Tracks interview scheduling and status
- **Statuses**: PENDING, SCHEDULED, COMPLETED, CANCELLED, RESCHEDULED
- **Email Tracking**:
  - `invitation_sent_at`
  - `confirmation_sent_at`
  - `last_followup_sent_at`
  - `pre_interview_reminder_sent_at`
  - `followup_count`

### **RecruiterEmailSettings**
- Per-company email timing preferences
- **Fields**: Follow-up delay, reminder hours, max follow-ups, etc.

### **RecruiterInterviewSettings**
- Per-job interview scheduling preferences
- **Fields**: Date range, time range, time gap, time slots JSON

### **RecruiterQualificationSettings**
- Per-company qualification thresholds
- **Fields**: Interview threshold, hold threshold, use_custom_thresholds

---

## 🔄 Key Algorithms

### **Role Fit Score Calculation** (Summarization)
- **Skills Match** (80 pts max):
  - If job keywords: Match percentage × 80 (using skill equivalences)
  - If no keywords: 8 pts per skill (max 80)
- **Experience** (8 pts max):
  - `min(8, total_experience_years × 1.5)`
- **Experience Relevance** (5 pts max):
  - Keyword hits in experience descriptions
- **Total**: 0-100 integer

### **Qualification Decision** (Lead Qualification)
- **Gating**: <3 matches OR <35% match → REJECT
- **Score Components**:
  - Base (0-40)
  - Skill Evidence (0-30): Explicit 3x, Inferred 1x
  - Match Quality (0-30): Based on match ratio
  - Experience (0-8): Based on years
- **Decision Thresholds**:
  - ≥65 (or custom): INTERVIEW
  - ≥45 (or custom): HOLD
  - <45: REJECT

### **Skill Matching** (Equivalences)
- **Bidirectional Matching**:
  - "Node.js" matches "JavaScript" and vice versa
  - Uses `SKILL_EQUIVALENCES` dictionary
  - Supports substring matching
  - Handles stack expansions (MERN → MongoDB, Express, React, Node.js)

---

## 🎯 API Endpoints

### **CV Processing**
- `POST /api/recruitment/process-cvs/`: Main CV processing endpoint

### **Job Descriptions**
- `GET /api/recruitment/job-descriptions/`: List jobs
- `POST /api/recruitment/job-descriptions/create/`: Create job
- `PUT /api/recruitment/job-descriptions/{id}/update/`: Update job
- `DELETE /api/recruitment/job-descriptions/{id}/delete/`: Delete job

### **Interviews**
- `GET /api/recruitment/interviews/`: List interviews
- `POST /api/recruitment/interviews/schedule/`: Manually schedule interview
- `GET /api/recruitment/interviews/{id}/`: Get interview details

### **CV Records**
- `GET /api/recruitment/cv-records/`: List CV records (with filters)

### **Settings**
- `GET/POST /api/recruitment/settings/email/`: Email settings
- `GET/POST /api/recruitment/settings/interview/`: Interview settings
- `GET/POST /api/recruitment/settings/qualification/`: Qualification thresholds

### **Analytics**
- `GET /api/recruitment/analytics/`: Comprehensive analytics dashboard

---

## 🔍 Important Details

### **Skill Equivalences**
- Handles 100+ skill variations
- Bidirectional matching
- Stack expansions (MERN, MEAN, MEVN)
- Framework relationships (React ↔ React.js ↔ ReactJS)

### **Email Automation**
- Follow-ups: Automatic for PENDING interviews
- Reminders: Automatic before SCHEDULED interviews
- Configurable timing per company user
- Background thread execution (non-blocking)

### **Interview Slot Management**
- Job-specific time slots
- Atomic slot booking (prevents double-booking)
- Date/time range validation
- Availability tracking in JSON

### **Ranking Logic**
- **Primary**: `role_fit_score` from summarization (0-100)
- **Secondary**: Qualification confidence (for decision making)
- **Tertiary**: Match percentage, experience, skills

### **Error Handling**
- LLM failures fall back to rule-based approaches
- Email failures logged but don't block processing
- Missing data handled gracefully (null values)
- Comprehensive logging via `LogService`

---

## 📝 Summary

The Recruitment Agent is a sophisticated multi-agent system that:

1. **Parses CVs** using LLM (Groq) with fallback to rule-based extraction
2. **Analyzes candidates** using intelligent summarization and skill matching
3. **Enriches profiles** with inferred skills and context
4. **Qualifies candidates** using recruiter-style decision algorithms
5. **Ranks candidates** by role fit score
6. **Auto-schedules interviews** for qualified candidates
7. **Manages follow-ups** automatically via Django signals
8. **Tracks everything** in comprehensive database models

The system is highly configurable with per-company and per-job settings for email timing, interview scheduling, and qualification thresholds.

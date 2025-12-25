# Complete Recruitment AI Process - Full Explanation

## Overview
This document explains the complete end-to-end process of the AI-based recruitment system, including all agents and their roles.

---

## 📋 Complete Process Flow

### **Phase 0: Job Description Preparation** (Optional but Recommended)

#### **Agent: JobDescriptionParserAgent**
**Purpose**: Extract keywords and requirements from job descriptions

**What it does**:
1. Takes job description text (from file upload or text input)
2. Uses LLM (Groq) to intelligently parse the description
3. Extracts structured data:
   - Job title
   - Required skills
   - Preferred skills
   - Technologies, frameworks, tools
   - Programming languages
   - Experience requirements
   - Education requirements
   - Certifications
   - Keywords (combined list for matching)

**Output**: 
- Structured JSON with all extracted keywords
- Stored in `JobDescription.keywords_json` field

**When it runs**:
- When creating/updating a job description
- Keywords are stored for later use during CV processing

---

## 🔄 Main CV Processing Pipeline

When you upload CVs and process them, the following agents work in sequence:

---

### **Phase 1: CV Parsing**

#### **Agent: CVParserAgent**
**Purpose**: Extract structured data from raw CV files

**Input**: 
- CV file (PDF, DOCX, or TXT)

**Process**:
1. **File Detection**: Identifies file type (PDF/DOCX/TXT)
2. **Text Extraction**: 
   - PDF → Uses `pdfplumber` to extract text
   - DOCX → Uses `python-docx` to extract text
   - TXT → Direct text reading
3. **Text Cleaning**: Removes extra whitespace, normalizes format
4. **Email Extraction**: 
   - First tries regex pattern matching (fast, reliable)
   - Optionally tries spaCy NER if model is available (fallback)
5. **LLM Parsing**: Sends cleaned text to Groq LLM with structured prompt
6. **Structured Extraction**: LLM extracts:
   - Name
   - Email
   - Phone
   - Skills (array)
   - Experience (array with role, company, dates, description)
   - Education (array with degree, institution, graduation year)
   - Certifications (array with name, issuer, year)
   - Summary

**Output**: 
- Structured JSON with all candidate information
- Stored in `CVRecord.parsed_json` field

**Technology**: 
- LLM: Groq (using OpenAI-compatible API)
- Libraries: pdfplumber, python-docx
- Optional: spaCy for NER (with regex fallback)

---

### **Phase 2: Summarization & Role Fit Scoring**

#### **Agent: SummarizationAgent**
**Purpose**: Analyze candidate profile and calculate role fit score

**Input**: 
- Parsed CV data (from CVParserAgent)
- Job keywords (optional, for role matching)

**Process**:
1. **LLM-based Analysis** (Primary method):
   - Sends parsed CV + job keywords to LLM
   - LLM analyzes candidate profile
   - Generates:
     - Candidate summary (concise professional summary)
     - Role fit score (0-100)
     - Total experience years
     - Key strengths
     - Potential concerns

2. **Rule-based Fallback** (if LLM unavailable):
   - Calculates experience from dates
   - Extracts key skills
   - Computes fit score based on:
     - Skills match percentage
     - Experience level
     - Education level
     - Certifications
     - Achievements

**Scoring Logic**:
- **0-30**: Poor match
- **31-50**: Moderate match
- **51-70**: Good match
- **71-100**: Excellent match

**Output**: 
- Insights JSON with:
  - `role_fit_score`: 0-100 score
  - `candidate_summary`: Professional summary
  - `total_experience_years`: Years of experience
  - `key_skills`: Important skills extracted
- Stored in `CVRecord.insights_json` and `CVRecord.role_fit_score`

**Technology**: LLM (Groq) with rule-based fallback

---

### **Phase 3: Initial Ranking**

**Process**:
- Candidates sorted by `role_fit_score` (highest first)
- Rank assigned to each candidate
- Stored in `CVRecord.rank`

---

### **Phase 4: Candidate Enrichment**

#### **Agent: LeadResearchEnrichmentAgent**
**Purpose**: Enrich candidate profile with additional insights

**Input**: 
- Parsed CV data
- Insights/summary from SummarizationAgent

**Process**:
1. Analyzes candidate data
2. Extracts additional metadata:
   - **Primary Role**: Most suitable role (e.g., "Backend Engineer", "Full Stack Developer")
   - **Seniority Level**: Junior/Mid/Senior/Manager
   - **Industry Experience**: Industry type
   - **Technology Stack**: Main technologies used
   - **Career Progression**: Growth trajectory analysis

**Output**: 
- Enriched data JSON with role classification and seniority
- Stored in `CVRecord.enriched_json`

**Note**: This is a rule-based agent (doesn't use LLM currently)

---

### **Phase 5: Qualification & Decision Making**

#### **Agent: LeadQualificationAgent**
**Purpose**: Make hiring decision (INTERVIEW/HOLD/REJECT)

**Input**: 
- Parsed CV data
- Insights/summary
- Job keywords (for skills matching)
- Enriched data (optional)

**Process**:
1. **Skills Matching**:
   - Matches candidate skills against job keywords
   - Identifies:
     - **Matched Skills**: Skills present in both CV and job description
     - **Missing Skills**: Required skills not found in CV
     - **Inferred Skills**: Skills that can be inferred from experience

2. **Decision Making** (Rule-based logic):
   - Analyzes:
     - Skills match percentage
     - Experience level vs. requirements
     - Education level
     - Role fit score
     - Overall profile quality

3. **Decision Output**:
   - **INTERVIEW**: Strong candidate, proceed to interview
   - **HOLD**: May be suitable, needs review
   - **REJECT**: Not suitable for role

4. **Confidence & Priority**:
   - **Confidence Score**: 0-100 (how confident in the decision)
   - **Priority**: HIGH/MEDIUM/LOW (for INTERVIEW candidates)

**Output**: 
- Qualification JSON with:
  - `decision`: INTERVIEW/HOLD/REJECT
  - `confidence_score`: 0-100
  - `priority`: HIGH/MEDIUM/LOW
  - `matched_skills`: List of matched skills
  - `missing_skills`: List of missing skills
  - `inferred_skills`: List of inferred skills
  - `match_percentage`: Percentage of job keywords matched
- Stored in `CVRecord.qualification_json`, `qualification_decision`, `qualification_confidence`, `qualification_priority`

**Technology**: Rule-based decision logic with skills matching

---

### **Phase 6: Final Ranking**

**Process**:
- Re-ranks candidates based on:
  1. Skills match ratio (if job keywords provided)
  2. Number of matched skills
  3. Number of inferred skills
  4. Confidence score
  5. Role fit score

**Output**: 
- Final ranked list with updated ranks
- Stored in `CVRecord.rank`

---

### **Phase 7: Automatic Interview Scheduling** (For INTERVIEW Decisions)

#### **Agent: InterviewSchedulingAgent**
**Purpose**: Automatically schedule interviews for approved candidates

**Trigger**: 
- Only runs for candidates with `qualification_decision = "INTERVIEW"`

**Process**:
1. **Interview Creation**:
   - Creates `Interview` record in database
   - Links to `CVRecord`
   - Sets status to `PENDING`

2. **Slot Generation**:
   - Generates available interview time slots
   - Default: Next 5-7 business days
   - Working hours: 9 AM - 5 PM
   - Slot duration: 60 minutes each
   - Stores as JSON array

3. **Unique Token Generation**:
   - Creates unique confirmation token
   - Used for candidate slot selection page

4. **Email Invitation**:
   - Sends interview invitation email to candidate
   - Includes:
     - Job role information
     - Link to slot selection page (with token)
     - Available time slots
     - Interview type (Online/Onsite)

5. **Email Notifications**:
   - Candidate receives invitation email
   - Recruiter receives notification (optional)

**Output**: 
- `Interview` record created
- Email sent to candidate
- Status: `PENDING` (waiting for candidate to select slot)

**Technology**: Django email backend (SMTP or console)

---

## 📊 Data Flow Summary

```
User Uploads CVs
    ↓
[1] CVParserAgent
    → Extracts structured data
    → Stores in CVRecord.parsed_json
    ↓
[2] SummarizationAgent
    → Analyzes profile
    → Calculates role_fit_score (0-100)
    → Stores in CVRecord.insights_json
    ↓
[3] Initial Ranking
    → Sort by role_fit_score
    → Assign ranks
    ↓
[4] LeadResearchEnrichmentAgent
    → Enriches profile
    → Determines primary role & seniority
    → Stores in CVRecord.enriched_json
    ↓
[5] LeadQualificationAgent
    → Skills matching
    → Decision: INTERVIEW/HOLD/REJECT
    → Confidence & priority
    → Stores in CVRecord.qualification_json
    ↓
[6] Final Ranking
    → Re-rank based on skills match
    → Update ranks
    ↓
[7] InterviewSchedulingAgent (for INTERVIEW only)
    → Creates interview record
    → Generates time slots
    → Sends invitation email
    → Candidate selects slot
    ↓
Results Display
    → Candidates grouped by decision
    → Ranked list shown
```

---

## 🗄️ Database Storage

### **CVRecord Model**
Stores all processing results:
- `parsed_json`: Structured CV data (from CVParserAgent)
- `insights_json`: Summary and insights (from SummarizationAgent)
- `role_fit_score`: 0-100 score (from SummarizationAgent)
- `rank`: Final ranking position
- `enriched_json`: Enrichment data (from LeadResearchEnrichmentAgent)
- `qualification_json`: Qualification results (from LeadQualificationAgent)
- `qualification_decision`: INTERVIEW/HOLD/REJECT
- `qualification_confidence`: 0-100
- `qualification_priority`: HIGH/MEDIUM/LOW
- `job_description`: Link to JobDescription (if applicable)

### **Interview Model**
Stores interview scheduling:
- Candidate information
- Job role
- Available slots (JSON)
- Selected slot
- Status: PENDING/SCHEDULED/COMPLETED/CANCELLED
- Confirmation token
- Email timestamps

### **JobDescription Model**
Stores job descriptions:
- Title and description
- `keywords_json`: Parsed keywords (from JobDescriptionParserAgent)

---

## 🔑 Key Features

1. **Intelligent Parsing**: LLM-based extraction understands CV formats
2. **Smart Matching**: Skills-based matching with job requirements
3. **Automated Decisions**: Rule-based qualification system
4. **Auto-Scheduling**: Automatic interview invitations for approved candidates
5. **Email Automation**: Candidate receives slot selection link
6. **Ranking System**: Multiple ranking methods (fit score + skills match)
7. **Fallback Mechanisms**: Rule-based fallbacks if LLM unavailable

---

## ⚙️ Technology Stack

- **LLM**: Groq API (OpenAI-compatible)
- **File Processing**: pdfplumber, python-docx
- **Email**: Django email backend (SMTP/console)
- **Database**: Django ORM (SQL Server/SQLite)
- **Logging**: JSONL logs for debugging

---

## 📈 Performance Considerations

- **Parallel Processing**: Can process multiple CVs in sequence
- **Caching**: Keywords stored in database (not parsed every time)
- **Rate Limiting**: Handles Groq API rate limits with error handling
- **Fallbacks**: Rule-based fallbacks ensure system works even if LLM fails


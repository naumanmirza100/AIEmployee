# How the Recruitment Agent is Integrated in PaPerProjectFront

Analysis of how the recruitment agent is connected end-to-end (routes → page → dashboard → components → service → API).

---

## 1. Backend API (Django `api` app)

**Where:** `api/urls.py` imports `api.views.recruitment_agent` and registers all recruitment routes under the **api** app.  
**Base path:** All URLs are under `/api/` (because `project_manager_ai/urls.py` has `path('api/', include('api.urls'))`).

**Auth:** Every recruitment view uses:
- `@authentication_classes([CompanyUserTokenAuthentication])`
- `@permission_classes([IsCompanyUserOnly])`  
So the frontend must send `Authorization: Token <company_auth_token>` (company user logged in via Company Login).

**Endpoints (all under `/api/recruitment/...`):**

| Method | URL pattern | View function | Purpose |
|--------|-------------|---------------|---------|
| POST | `/api/recruitment/process-cvs/` | process_cvs | Upload CVs, parse/rank by job |
| GET | `/api/recruitment/job-descriptions/` | list_job_descriptions | List job descriptions |
| POST | `/api/recruitment/job-descriptions/create/` | create_job_description | Create job |
| PUT/PATCH | `/api/recruitment/job-descriptions/<id>/update/` | update_job_description | Update job |
| DELETE | `/api/recruitment/job-descriptions/<id>/delete/` | delete_job_description | Delete job |
| GET | `/api/recruitment/interviews/` | list_interviews | List interviews |
| POST | `/api/recruitment/interviews/schedule/` | schedule_interview | Schedule interview |
| GET | `/api/recruitment/interviews/<id>/` | get_interview_details | Get interview details |
| GET | `/api/recruitment/cv-records/` | list_cv_records | List CV records/candidates |
| GET/POST | `/api/recruitment/settings/email/` | email_settings | Email settings |
| GET/POST | `/api/recruitment/settings/interview/` | interview_settings | Interview settings |
| GET/POST | `/api/recruitment/settings/qualification/` | qualification_settings | Qualification settings |
| GET | `/api/recruitment/analytics/` | recruitment_analytics | Analytics |

**Response shape (backend):**  
- Success: `{ "status": "success", "data": ... }` (e.g. list endpoints return `data` as array or object).  
- Errors: `{ "status": "error", "message": "..." }` with appropriate HTTP status.  
- process_cvs returns `{ "status": "success", "results": [...], "total": N }` (not wrapped in `data`).

---

## 2. Frontend route

**Where:** `PaPerProjectFront/src/App.jsx`

- **Route:** `<Route path="/recruitment/dashboard" element={<RecruitmentAgentPage />} />`
- No `ProtectedRoute`; the page itself checks company user and module access.
- User reaches it by: Company Dashboard nav tab “Recruitment Agent”, or Home → AI-Powered Modules → Recruitment Agent (purchase/access), or direct URL `/recruitment/dashboard`.

---

## 3. Page: RecruitmentAgentPage

**Where:** `PaPerProjectFront/src/pages/RecruitmentAgentPage.jsx`

**Responsibilities:**
1. **Auth:** Read `company_user` from `localStorage`. If missing → toast + `navigate('/company/login')`.
2. **Module access:** Call `checkModuleAccess('recruitment_agent')` and `getPurchasedModules()` from `modulePurchaseService`. If no access → show “Module Not Purchased” card with buttons (Home, Back to Dashboard).
3. **Layout:** Once allowed, render:
   - **DashboardNavbar** with: Dashboard (→ `/company/dashboard`), optional Project Manager Agent (if purchased), Recruitment Agent (current), optional Marketing Agent (if purchased). Plus logout.
   - **RecruitmentDashboard** in the main content area.

**State:** `companyUser`, `loading`, `hasAccess`, `checkingAccess`, `activeSection`, `purchasedModules`, `modulesLoaded`.  
**No API calls to recruitment backend in the page itself** — all recruitment API usage is inside child components via the service.

---

## 4. Dashboard: RecruitmentDashboard

**Where:** `PaPerProjectFront/src/components/recruitment/RecruitmentDashboard.jsx`

**Responsibilities:**
1. **Stats:** On load, calls `getJobDescriptions()`, `getInterviews()`, `getCVRecords()` from `recruitmentAgentService` and derives stats (total CVs, total interviews, active jobs, pending interviews). Expects `response.data` to be the list (e.g. `jobsRes.data`, `interviewsRes.data`, `cvRecordsRes.data`).
2. **Tabs:** Single tab list: Dashboard, Analytics, CV Processing, Job Descriptions, Candidates, Interviews, Settings.
3. **Content per tab:** Renders one of: Quick Actions (dashboard), RecruitmentAnalytics, CVProcessing, JobDescriptions, CVRecords, Interviews, RecruiterSettings.

**Service usage:** Imports and uses only: `getJobDescriptions`, `getInterviews`, `getCVRecords`, `getEmailSettings`, `getInterviewSettings` from `@/services/recruitmentAgentService`.

---

## 5. Service: recruitmentAgentService

**Where:** `PaPerProjectFront/src/services/recruitmentAgentService.js`

**Auth:** Uses `companyApi` from `companyAuthService.js` for most calls (sends `Authorization: Token <company_auth_token>`). Base URL is `VITE_API_URL` (e.g. `http://localhost:8000/api`).  
**Exception:** `processCVs` uses raw `fetch` to `API_BASE_URL/recruitment/process-cvs` with the same token and `FormData` (file upload).

**Methods and API mapping:**

| Service method | HTTP | Backend path | Notes |
|----------------|------|--------------|--------|
| processCVs(files, jobDescriptionId, ...) | POST | `/recruitment/process-cvs` | FormData, raw fetch |
| getJobDescriptions() | GET | `/recruitment/job-descriptions` | companyApi.get |
| createJobDescription(jobData) | POST | `/recruitment/job-descriptions/create` | companyApi.post |
| updateJobDescription(jobId, jobData) | PUT | `/recruitment/job-descriptions/<id>/update` | companyApi.put |
| deleteJobDescription(jobId) | DELETE | `/recruitment/job-descriptions/<id>/delete` | companyApi.delete |
| getInterviews(filters) | GET | `/recruitment/interviews?…` | companyApi.get |
| scheduleInterview(interviewData) | POST | `/recruitment/interviews/schedule` | companyApi.post |
| getInterviewDetails(interviewId) | GET | `/recruitment/interviews/<id>` | companyApi.get |
| getCVRecords(filters) | GET | `/recruitment/cv-records?…` | companyApi.get |
| getEmailSettings() | GET | `/recruitment/settings/email` | companyApi.get |
| updateEmailSettings(settings) | POST | `/recruitment/settings/email` | companyApi.post |
| getInterviewSettings(jobId) | GET | `/recruitment/settings/interview?job_id=…` | companyApi.get |
| updateInterviewSettings(settings) | POST | `/recruitment/settings/interview` | companyApi.post |
| getQualificationSettings() | GET | `/recruitment/settings/qualification` | companyApi.get |
| updateQualificationSettings(settings) | POST | `/recruitment/settings/qualification` | companyApi.post |
| getRecruitmentAnalytics(days, months, jobId) | GET | `/recruitment/analytics` | companyApi.get(..., { params }) |

**Response handling:** Service returns the full response body (e.g. `{ status: 'success', data: [...] }`). Components check `response.status === 'success'` and use `response.data` (or `response.results` for process_cvs).

---

## 6. Components under recruitment/

| Component | File | What it uses from service | Purpose |
|-----------|------|---------------------------|---------|
| RecruitmentDashboard | RecruitmentDashboard.jsx | getJobDescriptions, getInterviews, getCVRecords, getEmailSettings, getInterviewSettings | Layout, stats, tabs, delegates to children |
| CVProcessing | CVProcessing.jsx | processCVs, getJobDescriptions, getInterviewSettings | Upload CVs, select job, run processing |
| JobDescriptions | JobDescriptions.jsx | getJobDescriptions, createJobDescription, updateJobDescription, deleteJobDescription | CRUD job descriptions |
| Interviews | Interviews.jsx | getInterviews, scheduleInterview, getInterviewDetails, getCVRecords, getJobDescriptions | List/schedule interviews |
| CVRecords | CVRecords.jsx | getCVRecords, getJobDescriptions | List candidates/CV records |
| RecruiterSettings | RecruiterSettings.jsx | getEmailSettings, updateEmailSettings, getInterviewSettings, updateInterviewSettings, getQualificationSettings, updateQualificationSettings | Email, interview, qualification settings |
| RecruitmentAnalytics | RecruitmentAnalytics.jsx | getRecruitmentAnalytics, getJobDescriptions | Analytics charts/filters |

Each component:
- Imports only the service methods it needs.
- Calls the service (e.g. `getJobDescriptions()`), then checks `response.status === 'success'` and uses `response.data` (or equivalent) for UI state.

---

## 7. Connection flow (end-to-end)

1. **Entry:** User logs in as company user (Company Login) → `company_auth_token` and `company_user` stored in `localStorage`.
2. **Navigation:** User goes to `/recruitment/dashboard` (from Company Dashboard nav, or Home module card, or direct).
3. **RecruitmentAgentPage:** Reads `company_user`, runs `checkModuleAccess('recruitment_agent')` and `getPurchasedModules()`. If no access → “Module Not Purchased”. If access → renders DashboardNavbar + RecruitmentDashboard.
4. **RecruitmentDashboard:** Calls `getJobDescriptions()`, `getInterviews()`, `getCVRecords()` (via recruitmentAgentService). Service uses `companyApi.get('/recruitment/...')` → request goes to `VITE_API_URL` + `/recruitment/...` = `http://localhost:8000/api/recruitment/...` with `Authorization: Token <token>`.
5. **Backend:** Django serves `/api/recruitment/...` via `api.urls` → `api.views.recruitment_agent.*` → CompanyUserTokenAuthentication resolves token to CompanyUser → view returns `{ status: 'success', data: ... }`.
6. **Frontend:** Service returns that JSON. Components use `response.status` and `response.data` to update state and render (stats, tables, forms, etc.).

---

## 8. Summary

| Layer | Recruitment agent |
|-------|--------------------|
| **Backend** | `api/urls.py` + `api/views/recruitment_agent.py`; all under `/api/recruitment/...`; CompanyUserTokenAuthentication. |
| **Frontend route** | `/recruitment/dashboard` → RecruitmentAgentPage (in App.jsx). |
| **Page** | RecruitmentAgentPage: company user + module check; then DashboardNavbar + RecruitmentDashboard. |
| **Dashboard** | RecruitmentDashboard: stats from getJobDescriptions, getInterviews, getCVRecords; tabs; child components. |
| **Service** | recruitmentAgentService: companyApi (and raw fetch for processCVs); base URL = VITE_API_URL (e.g. http://localhost:8000/api). |
| **Components** | CVProcessing, JobDescriptions, Interviews, CVRecords, RecruiterSettings, RecruitmentAnalytics — each calls service and uses response.status / response.data. |
| **Discovery** | Company Dashboard nav (if recruitment_agent purchased), Home AI-Powered Modules (ModuleCardsSection), direct URL. |

No separate “recruitment agent Django app” is used by PaPerProjectFront; everything goes through the **api** app and **company** auth.

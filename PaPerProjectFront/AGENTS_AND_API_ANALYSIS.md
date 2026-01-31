# PaPerProjectFront – How Agents Are Merged, URLs/Views/APIs, and Flow

This document describes how the **Project Manager**, **Recruitment**, and **Marketing** agents are wired in **PaPerProjectFront** (frontend) and the Django **api** app (URLs, views, services).

---

## 1. High-Level Architecture

```
PaPerProjectFront (Vite/React)
    ↓ routes
    ↓ calls
api/* (Django REST – project_manager_ai/urls.py → api/urls.py)
    ↓ views use
Agent backends (project_manager_agent, recruitment_agent, marketing_agent)
```

- **Frontend**: `PaPerProjectFront/src` – React, React Router, services that call the API.
- **Backend API**: Django app `api` – all agent-related HTTP endpoints live under `api/urls.py`.
- **Auth for agents**: Company users log in via **Company Login**; frontend stores `company_auth_token` and `company_user`. Agent APIs use **CompanyUserTokenAuthentication** (token in `Authorization: Token <token>`).

---

## 2. How Agents Are “Merged” and Connected

### 2.1 Single API Prefix

- Django: `path('api/', include('api.urls'))` in `project_manager_ai/urls.py`.
- So every agent endpoint is under `/api/...` (e.g. `/api/marketing/dashboard`, `/api/recruitment/...`, `/api/project-manager/...`).

### 2.2 Same Auth Model for All Three Agents

- **Company users** (from Company Login) can use:
  - Project Manager Agent  
  - Recruitment Agent  
  - Marketing Agent  
- Access is **per-module**: each company can purchase modules (`project_manager_agent`, `recruitment_agent`, `marketing_agent`). Frontend checks `checkModuleAccess('<module_name>')` and `getPurchasedModules()` and only shows/enters the dashboards the company has bought.

### 2.3 Shared Layout and Navigation

- Each agent has its own **page** (e.g. `MarketingAgentPage.jsx`, `RecruitmentAgentPage.jsx`, `ProjectManagerDashboardPage.jsx`).
- Each page uses **DashboardNavbar** with **navItems** built from `purchasedModules`:
  - If `project_manager_agent` is purchased → show “Project Manager Agent” tab → `navigate('/project-manager/dashboard')`.
  - If `recruitment_agent` is purchased → show “Recruitment Agent” tab → `navigate('/recruitment/dashboard')`.
  - If `marketing_agent` is purchased → show “Marketing Agent” tab → `navigate('/marketing/dashboard')`.
- So from any agent dashboard, the user can switch to other purchased agents via the same navbar.

### 2.4 Same Page Pattern for All Agents

Each agent page follows the same structure:

1. Read `company_user` from `localStorage`; if missing → redirect to `/company/login`.
2. Optionally load cached `company_purchased_modules` from `localStorage`.
3. `checkModuleAccess('<module>')` and `getPurchasedModules()` (from `modulePurchaseService`).
4. If no access → show “Module Not Purchased” and buttons (e.g. Home, Company Dashboard).
5. If access → render **DashboardNavbar** (with cross-links to other purchased agents) + main content (e.g. **MarketingDashboard**, **RecruitmentDashboard**, or PM dashboard with PM-specific components).

So “merged” means: **one API base**, **one company auth**, **one module/purchase check**, and **one navbar** that links all purchased agent dashboards.

---

## 3. URLs and Routes

### 3.1 Frontend (React Router) – `PaPerProjectFront/src/App.jsx`

| Route | Component | Protection |
|-------|------------|------------|
| `/company/login` | CompanyLoginPage | None |
| `/company/dashboard` | CompanyDashboardPage | None (page checks auth) |
| `/project-manager/dashboard` | ProjectManagerDashboardPage | ProtectedRoute (requireProjectManager) |
| `/marketing/dashboard` | MarketingAgentPage | None (page checks company user + module) |
| `/recruitment/dashboard` | RecruitmentAgentPage | None (page checks company user + module) |

Marketing and Recruitment do **not** use `<ProtectedRoute>`; they enforce company login and module access inside the page.

### 3.2 Backend API – `api/urls.py`

**Project Manager Agent**

- `GET /api/project-manager/dashboard/` → company_dashboard.project_manager_dashboard  
- `GET /api/project-manager/ai/project-pilot/`, `POST` (and upload)  
- `POST /api/project-manager/ai/task-prioritization/`  
- `POST /api/project-manager/ai/generate-subtasks/`  
- `POST /api/project-manager/ai/timeline-gantt/`  
- `POST /api/project-manager/ai/knowledge-qa/`  
- `POST /api/project-manager/projects/create/`, `POST /api/project-manager/tasks/create/`  
- `GET /api/project-manager/users/`  

**Recruitment Agent**

- `POST /api/recruitment/process-cvs/`  
- `GET/POST /api/recruitment/job-descriptions/` (+ create, update, delete by id)  
- `GET /api/recruitment/interviews/`, `POST /api/recruitment/interviews/schedule/`, `GET /api/recruitment/interviews/<id>/`  
- `GET /api/recruitment/cv-records/`  
- `GET/POST /api/recruitment/settings/email|interview|qualification`  
- `GET /api/recruitment/analytics/`  

**Marketing Agent**

- `GET /api/marketing/dashboard/`  
- `GET /api/marketing/campaigns/`, `GET /api/marketing/campaigns/<id>/`  
- `POST /api/marketing/campaigns/create/`  
- `POST /api/marketing/qa/`  
- `POST /api/marketing/market-research/`  
- `POST /api/marketing/outreach-campaign/`  
- `POST /api/marketing/document-authoring/`  
- `GET /api/marketing/notifications/`  

All of these are registered in `api/urls.py` and live under the single `api/` prefix.

---

## 4. How Views and APIs Work

### 4.1 Auth on the Backend

- Agent views use:
  - `@authentication_classes([CompanyUserTokenAuthentication])`
  - `@permission_classes([IsCompanyUserOnly])`
- Request carries `Authorization: Token <company_auth_token>`. The backend resolves this to a **CompanyUser** and attaches it as `request.user`.

### 4.2 Frontend API Usage

- **Company-scoped requests** use `companyApi` from `companyAuthService.js`:
  - Reads `company_auth_token` from `localStorage`.
  - Sends `Authorization: Token <token>`.
  - Base URL: `VITE_API_URL` (e.g. `http://localhost:8000/api`).
- Each agent has a **service** module that calls these endpoints:
  - **Project Manager**: `pmAgentService.js` → `/project-manager/...`
  - **Recruitment**: `recruitmentAgentService.js` → `/recruitment/...`
  - **Marketing**: `marketingAgentService.js` → `/marketing/...`

### 4.3 Marketing Agent Flow (Example)

1. User opens `/marketing/dashboard` → `MarketingAgentPage` loads.
2. Page checks `company_user` and `checkModuleAccess('marketing_agent')` / `getPurchasedModules()`.
3. If allowed, it renders `MarketingDashboard`, which:
   - Calls `marketingAgentService.getMarketingDashboard()` → `GET /api/marketing/dashboard/`.
   - Renders tabs: Dashboard, Campaigns, Q&A, Research, Documents.
4. Sub-components use the same service:
   - **Campaigns** → listCampaigns, getCampaign, createCampaign (and backend list/create/get campaign).
   - **MarketingQA** → marketingAgentService.marketingQA → `POST /api/marketing/qa/`.
   - **MarketResearch** → marketResearch → `POST /api/marketing/market-research/`.
   - **Documents** → documentAuthoring → `POST /api/marketing/document-authoring/`.
   - **Notifications** → getNotifications → `GET /api/marketing/notifications/`.
5. Backend views in `api/views/marketing_agent.py` map to these URLs, use `_get_or_create_user_for_company_user(company_user)` where the marketing app expects a Django User, and call into `project_manager_agent.ai_agents.agents_registry.AgentRegistry` (e.g. `AgentRegistry.get_agent("marketing_qa")`, `"market_research"`, `"outreach_campaign"`, `"document_authoring"`, `"proactive_notification"`).

So: **URL → api/urls.py → api/views/marketing_agent.py → AgentRegistry / marketing_agent models**.

---

## 5. Summary Table

| Layer | Project Manager Agent | Recruitment Agent | Marketing Agent |
|-------|------------------------|-------------------|-----------------|
| **Frontend route** | `/project-manager/dashboard` | `/recruitment/dashboard` | `/marketing/dashboard` |
| **Frontend page** | ProjectManagerDashboardPage | RecruitmentAgentPage | MarketingAgentPage |
| **Main content** | PM tabs + ProjectPilotAgent, TaskPrioritization, etc. | RecruitmentDashboard | MarketingDashboard (Campaigns, Q&A, Research, Documents) |
| **Service** | pmAgentService.js | recruitmentAgentService.js | marketingAgentService.js |
| **API prefix** | `/api/project-manager/...` | `/api/recruitment/...` | `/api/marketing/...` |
| **Backend views** | api/views/pm_agent.py, company_dashboard | api/views/recruitment_agent.py | api/views/marketing_agent.py |
| **Module name** | project_manager_agent | recruitment_agent | marketing_agent |
| **Navbar** | Same DashboardNavbar; tabs for other purchased agents | Same | Same |

---

## 6. Next Steps for Marketing Agent in PaPerProjectFront

- **Already done**: Route, page, module check, navbar integration, service, and backend endpoints for dashboard, campaigns, Q&A, market research, outreach, document authoring, notifications.
- **Fixed**: `MarketingAgentPage.jsx` was using `getPurchasedModules` without importing it; added `getPurchasedModules` to the import from `@/services/modulePurchaseService`.
- **Possible next steps** (depending on product priorities):
  - Add **campaign update/delete** in backend and frontend (and in `marketingAgentService` and Campaigns UI) if needed.
  - Add **Outreach/Sequence** UI that calls `outreachCampaign` (e.g. upload leads file, launch campaign) if not already covered.
  - Add **Notifications** tab or bell in the marketing dashboard that uses `getNotifications`.
  - Ensure **MarketingDashboard** has a “Notifications” tab or panel that uses the existing `Notifications` component and `getNotifications` (already in MarketingDashboard.jsx as Documents; confirm if a Notifications tab is desired and add if missing).
  - Add deep links for campaigns (e.g. `/marketing/dashboard/campaigns/:id`) and wire them to `getCampaign` and a campaign detail view.

If you tell me which of these you want (e.g. “campaign update/delete” or “Notifications tab”), I can outline the exact file and code changes next.

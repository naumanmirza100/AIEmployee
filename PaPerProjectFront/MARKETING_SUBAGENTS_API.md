# Marketing sub-agents – API used by PaPerProjectFront

PaPerProjectFront talks to the **Django API app** (under `/api/`), not the standalone marketing_agent app (under `/marketing/`). Base URL is `VITE_API_URL` (e.g. `http://localhost:8000/api`). Auth: **Company user token** (`Authorization: Token <company_auth_token>`).

---

## 1. Proactive Notifications

- **Backend:** `api/urls.py` → `api/views/marketing_agent.get_notifications`
- **URL:** `GET /api/marketing/notifications`
- **Query:** `unread_only` (true/false), `type`, `campaign_id`
- **Response:** `{ "status": "success", "data": { "success": true, "count": N, "unread_count": M, "notifications": [ { "id", "notification_type", "priority", "title", "message", "action_required", "action_url", "is_read", "campaign_id", "campaign_name", "metadata", "created_at" } ] } }`  
  or `{ "status": "error", "message": "..." }`

**Frontend:** `marketingAgentService.getNotifications(params)` → `Notifications.jsx`

---

## 2. Document Authoring

- **Backend:** `api/urls.py` → `api/views/marketing_agent.document_authoring`
- **URL:** `POST /api/marketing/document-authoring`
- **Body:** `{ "action": "create", "document_type": "strategy"|"proposal"|"report"|"brief"|"presentation", "document_data": { "title?", "notes?" }, "campaign_id": number|null, "context": {} }`
- **Response:** `{ "status": "success", "data": { "success": true, "title?", "content?", "message?", "document_id?" } }`  
  or `{ "status": "error", "message": "..." }`  
  or `data.success === false` with `data.error`

**Frontend:** `marketingAgentService.documentAuthoring(action, documentType, documentData, campaignId, context)` → `Documents.jsx`

---

## Checklist

1. **Backend:** Django running with `api` app; `api/urls.py` includes the marketing routes above.
2. **Auth:** User logged in as company user (Company Login); `company_auth_token` and `company_user` in localStorage.
3. **Env:** `VITE_API_URL=http://localhost:8000/api` (no trailing slash) so requests go to `/api/marketing/...`.

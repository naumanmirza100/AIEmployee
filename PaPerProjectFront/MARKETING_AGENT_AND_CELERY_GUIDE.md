# Marketing Agent in PaPerProjectFront + Celery Setup

## 1. How marketing_agent is integrated in PaPerProjectFront

The marketing agent is **already integrated**. Here is what is in place:

| Layer | What | Location |
|-------|------|----------|
| **Route** | `/marketing/dashboard` | `PaPerProjectFront/src/App.jsx` |
| **Page** | MarketingAgentPage | `PaPerProjectFront/src/pages/MarketingAgentPage.jsx` |
| **Service** | marketingAgentService | `PaPerProjectFront/src/services/marketingAgentService.js` |
| **Dashboard** | MarketingDashboard + tabs | `PaPerProjectFront/src/components/marketing/` |
| **Backend API** | marketing_agent views | `api/urls.py` → `api/views/marketing_agent.py` |

**Frontend API base URL:** Set in `PaPerProjectFront/.env` (or root `.env` used by Vite):

```env
VITE_API_URL=http://localhost:8000/api
```

Use your real Django API URL (no trailing slash). Restart `npm run dev` after changing.

**Module access:** Users reach the marketing dashboard after **Company Login**. Access is gated by the **marketing_agent** module (purchased via Stripe/module purchase). The page checks `checkModuleAccess('marketing_agent')` and `getPurchasedModules()`.

**No extra “integration” step is required** for the marketing agent to appear and work in PaPerProjectFront; ensure backend is running and `VITE_API_URL` points to it.

---

## 2. Setting up Celery (for marketing automation)

Celery runs **background/scheduled tasks** for the marketing agent (send sequence emails, sync inbox, auto-pause campaigns, etc.). It is **separate** from `python manage.py runserver`.

### 2.1 Install dependencies

From repo root:

```bash
pip install celery redis django-celery-beat
# If not using Redis (dev fallback with SQLite broker):
pip install sqlalchemy
```

(Or use `requirements.txt`: `pip install -r requirements.txt`.)

### 2.2 Broker: Redis (recommended) or SQLite

**Option A – Redis (recommended for production and smoother dev)**

1. Install and start Redis (e.g. Windows: WSL, Docker, or a Redis build).
2. In project root `.env`:

```env
USE_REDIS=True
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

**Option B – SQLite (no Redis, dev only)**

In project root `.env`:

```env
USE_REDIS=False
# Optional; defaults in settings.py:
# CELERY_BROKER_URL=sqla+sqlite:///celery_broker.db
# CELERY_RESULT_BACKEND=db+sqlite:///celery_results.db
```

Requires `sqlalchemy` installed.

### 2.3 Run Celery Worker

From **repo root** (same place as `manage.py`):

```bash
celery -A project_manager_ai worker -l info
```

On Windows you may need:

```bash
celery -A project_manager_ai worker -l info --pool=solo
```

This runs the **worker** that executes tasks (including `marketing_agent.tasks`).

### 2.4 Run Celery Beat (scheduler)

In **another terminal**, from repo root:

```bash
celery -A project_manager_ai beat -l info
```

Beat triggers the periodic tasks (every 5 min, 15 min, etc.) defined in `CELERY_BEAT_SCHEDULE` in `project_manager_ai/settings.py`.

**Summary:** You need **both** the worker and beat running for full marketing automation (sequence emails, inbox sync, auto-pause, etc.).

---

## 3. Do you need to run Celery when using `python manage.py runserver`?

**Short answer:**

- **No** – You do **not** have to run Celery for the backend or frontend to work.  
  `python manage.py runserver` is enough for:
  - API (login, dashboard, campaigns, marketing QA, etc.)
  - PaPerProjectFront (Marketing Agent page, API calls).

- **Yes** – You **do** need to run Celery (worker + beat) if you want **automated marketing tasks** to run:
  - Sending sequence emails (every 5 min)
  - Syncing inbox / reply detection (every 5 min)
  - Retry failed emails (every 15 min)
  - Auto-start scheduled campaigns (every 15 min)
  - Monitor campaigns and notifications (every 30 min)
  - Auto-pause expired campaigns (daily)

So:

| Goal | Run Django? | Run Celery worker? | Run Celery beat? |
|------|--------------|--------------------|------------------|
| Use site + Marketing dashboard (API + UI) | Yes (`runserver`) | No | No |
| Marketing automation (emails, sync, etc.) | Yes | Yes | Yes |

**Typical local setup:**

1. Terminal 1: `python manage.py runserver` (Django + API).
2. Terminal 2: `cd PaPerProjectFront` then `npm run dev` (frontend).
3. (Optional) Terminal 3: `celery -A project_manager_ai worker -l info --pool=solo` (worker).
4. (Optional) Terminal 4: `celery -A project_manager_ai beat -l info` (scheduler).

If you skip Celery, the Marketing Agent dashboard and API still work; only the scheduled/background tasks will not run.

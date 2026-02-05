# Celery commands (this project)

Run all commands from the **project root** (where `manage.py` is).

App name: **`project_manager_ai`**

---

## 1. Worker (runs tasks)

```bash
celery -A project_manager_ai worker -l info
```

**On Windows** (use solo pool):

```bash
celery -A project_manager_ai worker -l info --pool=solo
```

---

## 2. Beat (scheduler for periodic tasks)

In a **separate terminal**:

```bash
celery -A project_manager_ai beat -l info
```

---

## 3. Worker + Beat in one process (dev only)

```bash
celery -A project_manager_ai worker -l info --beat
```

On Windows:

```bash
celery -A project_manager_ai worker -l info --pool=solo --beat
```

---

## 4. Inspect / purge (optional)

List registered tasks:

```bash
celery -A project_manager_ai inspect registered
```

Purge all pending tasks (use with care):

```bash
celery -A project_manager_ai purge
```

---

## 5. Environment

- **Broker:** Set `CELERY_BROKER_URL` (e.g. `redis://localhost:6379/0`) in `.env` or env. With `USE_REDIS=False`, settings fall back to SQLite broker.
- **Result backend:** Set `CELERY_RESULT_BACKEND` if you need task results (e.g. same Redis URL).

Full setup: see `PaPerProjectFront/MARKETING_AGENT_AND_CELERY_GUIDE.md`.

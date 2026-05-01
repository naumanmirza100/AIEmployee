# HR Support Agent

Sister to `Frontline_agent`, but built around **employees**, not customers.

## Layout

| Path | Role |
| --- | --- |
| `hr_agent/` | Django app — models, throttling, signals, migrations |
| `core/HR_agent/` | `HRAgent` class + `HRKnowledgeService` + prompts |
| `api/views/hr_agent.py` | DRF endpoints (one or more per sub-agent) |

## Sub-agents (scaffolded)

1. **Knowledge Q&A** — `POST /api/hr/knowledge-qa/`
   * RAG over `HRDocument` chunks via `HRKnowledgeService`.
   * Confidentiality gate: `public` / `employee` / `manager` / `hr_only`. CompanyUser role
     is mapped to one of those buckets in `_resolve_asker_role`.
   * Auto-injects employee context (manager, leave balances) into the prompt when the
     asking CompanyUser is linked to an `Employee`.

2. **Document Processing** — `POST /api/hr/documents/upload/` *(stub)*,
   `GET /api/hr/documents/`, `POST /api/hr/documents/<id>/summarize/`,
   `POST /api/hr/documents/<id>/extract/`
   * Summarize / extract reuse the `HRAgent` LLM path. Upload is wired to a 202 stub —
     port `process_document` from Frontline as the Celery task.
   * `extracted_fields` JSON on the document captures auto-extracted values (offer
     letter → name / role / salary / start date).

3. **Workflow / SOP Runner** — `GET/POST /api/hr/workflows/...`,
   `POST /api/hr/workflows/<id>/execute/` *(stub)*
   * Trigger conditions key off lifecycle events (`employee_hired`,
     `leave_request_submitted`, `probation_ending`, `review_due`, `birthday`,
     `work_anniversary`).
   * `HRWorkflowExecution.pause_state` is already on the model so the Frontline
     non-blocking `wait` step engine ports cleanly.
   * Pre-built step templates in `core/HR_agent/prompts.py`
     (`DEFAULT_ONBOARDING_STEPS`, `DEFAULT_OFFBOARDING_STEPS`).

4. **Proactive Notifications** — `GET/POST /api/hr/notifications/...`
   * `HRNotificationTemplate` adds HR-specific event types (birthday, work anniversary,
     probation ending, document expiring, leave request status, …).
   * `HRScheduledNotification` mirrors Frontline's retry / DLQ / quiet-hours fields,
     plus `recipient_employee` FK so a notification can target an Employee directly
     (not just a free-form email).

5. **Meeting Scheduling** — `GET/POST /api/hr/meetings/...`,
   `GET /api/hr/meetings/availability/`
   * Typed (`one_on_one`, `performance_review`, `exit_interview`,
     `grievance_hearing`, …). Sensitive types default to
     `visibility='private'` on creation.
   * `availability` returns clashing meetings inside a window.

## Bonus: leave requests

`POST /api/hr/leave-requests/submit/` and `.../decide/` are first-class because
they're the most common HR workflow trigger. The decided status change can drive
a workflow that updates the `LeaveBalance`, posts to the team calendar, and emails
a confirmation.

## What's a stub vs. wired

- ✅ Wired: knowledge Q&A, summarize, extract, list/create employees, list/create
  workflows, list/create notification templates, list/create meetings,
  meeting availability, leave-request submit/decide, dashboard.
- 🟡 Stubbed: document upload (needs a `process_hr_document` Celery task) and workflow
  execute (needs the Frontline `_execute_step_list` engine ported).

## Migrations

```
python manage.py makemigrations hr_agent
python manage.py migrate
```

`core/0050_alter_companyuser_role.py` adds the `hr_agent` role choice.
`hr_agent/0001_initial.py` creates all the HR tables.

## Throttle scopes

Defined in `settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']`:

```
hr_public  20/hour
hr_llm     60/hour
hr_upload  30/hour
hr_crud    300/hour
```

## Where to start when filling in the stubs

1. **Document upload pipeline** — copy `Frontline_agent.tasks.process_document`,
   point it at `HRDocument` + `HRDocumentChunk`, default-set `retention_days` per
   `document_type` (e.g. payroll → 2555, offer_letter → 365 * 7).
2. **Workflow executor** — copy `_execute_step_list` / `_run_single_step` and add the
   HR-specific step types (`provision_account`, `assign_training`, `schedule_meeting`,
   `update_leave_balance`).
3. **Notification scheduler** — copy `process_scheduled_notifications` and add the
   time-based event walker (probation ending in N days → schedule template).
4. **Workflow signals** — wire `post_save` on `Employee` (status transitions) and
   `LeaveRequest` to fire the matching workflows. Re-use the
   `Frontline_agent.workflow_context.workflow_execution_guard` pattern to prevent
   re-entrancy.

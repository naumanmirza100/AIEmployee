# Running the tests

```bash
python manage.py test project_manager_agent --settings=project_manager_ai.settings_test
```

95 tests, about 8 seconds. Run it before pushing anything that touches
projects, tasks, subtasks or the PM API views.

Run one class or one test while you work on it:

```bash
python manage.py test project_manager_agent.tests.test_tasks.BulkUpdateTests --settings=project_manager_ai.settings_test
```

## The settings module is not optional

`--settings=project_manager_ai.settings_test` puts the tests on a **local
SQLite database**. Without it the test runner tries to create a test database
on the shared Hostinger server, where:

- the database user may not be allowed to create one, and
- the account allows only **500 new connections an hour for the whole team**,
  so a test run can lock everyone out, logins included.

The test settings also skip migrations (tables are built straight from the
models — there are ~390 migrations and some are MySQL-only), turn off rate
limiting, and send email to memory.

Two consequences when you write a test:

- **Data migrations don't run**, so create the rows your test needs. The base
  class already creates companies, logins, an industry and projects.
- **Rate limits aren't enforced.** That they're *attached* to the views is
  checked separately, in `test_wiring.py`.

## What's covered

`project_manager_agent/tests/`

| File | Covers |
|---|---|
| `base.py` | shared setup: two companies, both login kinds, a dated project |
| `test_projects.py` | creating, editing and deleting projects in all three API families |
| `test_tasks.py` | tasks: assignees, due dates, dependencies, bulk update, deletes |
| `test_subtasks.py` | subtask CRUD, ordering, completion |
| `test_scope.py` | the module-purchase gate, the two login kinds, assignable-user lists |
| `test_wiring.py` | the audit trail, rate-limit wiring, pagination |

Every test starts with **two companies**, because most of the bugs these
tests exist to catch were one company reaching into another's data. When you
add a test for a new rule, add the "other company" case too.

## Writing a test

`PMTestCase` (in `base.py`) gives you:

- `self.company` / `self.rival` — two companies, the second one for the
  cross-company case;
- `self.dash`, `self.dash_colleague`, `self.rival_dash` — dashboard logins
  (`CompanyUser`);
- `self.pm`, `self.other_pm`, `self.dev`, `self.rival_pm` — employee logins
  (`auth.User`);
- `self.project` (has start date and deadline), `self.colleague_project`,
  `self.rival_project`;
- `self.call(view, actor, data, method=..., **url_kwargs)` — call a view
  function directly, returns `(status_code, body)`;
- `self.http(actor)` + `self.send(client, 'post', url, payload)` — go through
  the real URLs, authentication and middleware;
- `self.task(**fields)`, `self.employee(name, role=...)`,
  `self.buy_module(company)`.

Prefer `self.call` for a rule, and `self.http` when the point of the test is
the URL, the login kind or the module gate.

## The rest of the project

Only the PM agent has a test suite. `api/tests.py` and the other apps'
`tests.py` are still Django's empty stubs, so `python manage.py test` with no
arguments runs almost nothing. If you add tests for another agent, the same
settings module works:

```bash
python manage.py test hr_agent --settings=project_manager_ai.settings_test
```

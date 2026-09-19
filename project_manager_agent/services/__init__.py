"""Project and task operations shared by every PM API family.

  /api/project-manager/       dashboard login  (api/views/pm_agent.py, pm_deletes.py)
  /api/company/               dashboard login  (api/views/company_projects_tasks.py)
  /api/user/project-manager/  employee login   (api/views/user_project_manager.py)

Each of those views builds an Actor, calls one function here and formats the
result in its own response shape. Validation, scope, permissions and the audit
trail therefore exist once (audit item ARCH-1; MDS/PM_API_CONSOLIDATION_PLAN.md).
"""
from .actor import Actor, DashboardActor, EmployeeActor, project_owner_for  # noqa: F401
from .errors import ServiceError  # noqa: F401
from .projects import create_project, delete_project, update_project  # noqa: F401
from .tasks import (  # noqa: F401
    blockers, bulk_update_tasks, create_task, delete_task, serialize_brief, set_dependencies,
    update_task, validate_dependencies,
)

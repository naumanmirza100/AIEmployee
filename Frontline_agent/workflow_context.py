"""Re-entrancy guard for workflow execution.

Problem: when a workflow runs an `update_ticket` step, Django's `post_save`
signal on Ticket fires `_run_workflow_triggers(..., 'ticket_updated', ...)`
which may re-enter the same workflow, create another execution row, and do
the same update again. The only thing stopping an infinite loop today is
luck: the trigger condition usually no longer matches after the first run.

Fix: a `contextvars.ContextVar` we set around the workflow runner. The
post_save receiver checks the flag and bails when it's already inside a
workflow. ContextVar (vs threading.local) is the right tool because Django
request-handling + Celery workers may both be async/sync, and contextvars
propagate correctly through asyncio.

Usage:
    with workflow_execution_guard(workflow_id=w.id):
        run_steps(...)

    # In a signal:
    if is_workflow_executing():
        return
"""
from __future__ import annotations

import contextlib
import contextvars

# ContextVar holding the currently-running workflow id (0 = not inside a workflow).
# We store the id instead of just a bool so nested logs / debugging can identify
# which workflow is holding the reentry token.
_CURRENT_WORKFLOW_ID: contextvars.ContextVar[int] = contextvars.ContextVar(
    'frontline_current_workflow_id', default=0,
)


@contextlib.contextmanager
def workflow_execution_guard(workflow_id: int = 0):
    """Context manager that marks the current execution context as being
    inside a workflow run. Nesting is supported (the outer id is restored on
    exit), but the receiver only needs to know that `is_workflow_executing()`
    returns True — it doesn't distinguish nested vs top-level."""
    token = _CURRENT_WORKFLOW_ID.set(int(workflow_id or 0))
    try:
        yield
    finally:
        _CURRENT_WORKFLOW_ID.reset(token)


def is_workflow_executing() -> bool:
    """True while the current execution context is inside a workflow run."""
    return _CURRENT_WORKFLOW_ID.get() != 0


def current_workflow_id() -> int:
    """Returns the id of the workflow currently executing, or 0."""
    return _CURRENT_WORKFLOW_ID.get()

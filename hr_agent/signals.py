"""HR Support Agent signals — fire workflow triggers on lifecycle events.

Stubbed at scaffold time. The wiring shape mirrors `Frontline_agent/signals.py`:
when an event of interest (Employee hired, LeaveRequest submitted, etc.) is
saved, look up matching `HRWorkflow.trigger_conditions` and run them via
the executor in `api/views/hr_agent.py`.
"""
import logging

logger = logging.getLogger(__name__)

# Receivers will be hooked up here once the executor exists. Keep the module
# importable so apps.ready() doesn't fail.

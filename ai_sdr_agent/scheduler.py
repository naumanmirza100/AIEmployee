"""
SDR Embedded Scheduler
======================
Runs SDR automation jobs inside the Django process using Python's built-in
threading.Timer — no APScheduler or Celery worker required.

Jobs:
  send_due_steps      — every 5 min  (first run after 30 s)
  check_inbox_replies — every 5 min  (first run after 60 s)
  auto_start_campaigns — every 15 min (first run after 90 s)
  auto_pause_expired   — every 60 min (first run after 120 s)
"""

import logging
import threading

logger = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()


def _run_job(name, fn, interval_seconds, first_run=False):
    """Execute fn(), log result/errors, then reschedule itself."""
    if first_run:
        logger.debug("SDR scheduler: first run of %s", name)
    try:
        result = fn()
        if result:
            logger.debug("SDR scheduler: %s → %s", name, result)
    except Exception as exc:
        logger.exception("SDR scheduler: %s crashed: %s", name, exc)
    finally:
        t = threading.Timer(interval_seconds, _run_job, args=(name, fn, interval_seconds))
        t.daemon = True
        t.name = f"sdr-{name}"
        t.start()


def _send_due_steps():
    from ai_sdr_agent.tasks import send_due_steps_impl
    return send_due_steps_impl()


def _check_inbox():
    from ai_sdr_agent.tasks import check_inbox_replies_impl
    return check_inbox_replies_impl()


def _auto_start():
    from ai_sdr_agent.tasks import auto_start_campaigns_impl
    return auto_start_campaigns_impl()


def _auto_complete():
    from ai_sdr_agent.tasks import auto_pause_expired_campaigns_impl
    return auto_pause_expired_campaigns_impl()


def start_scheduler():
    """Start the embedded scheduler. Idempotent — safe to call multiple times."""
    global _started
    with _lock:
        if _started:
            return
        _started = True

    jobs = [
        ('send_due_steps',   _send_due_steps, 300,  30),   # every 5 min,  first in 30s
        ('check_inbox',      _check_inbox,    300,  60),   # every 5 min,  first in 60s
        ('auto_start',       _auto_start,     900,  90),   # every 15 min, first in 90s
        ('auto_complete',    _auto_complete,  3600, 120),  # every 60 min, first in 120s
    ]

    for name, fn, interval, delay in jobs:
        t = threading.Timer(delay, _run_job, args=(name, fn, interval, True))
        t.daemon = True
        t.name = f"sdr-{name}-init"
        t.start()

    logger.info(
        "SDR scheduler started — send_due_steps(5m), check_inbox(5m), "
        "auto_start(15m), auto_complete(1h)"
    )

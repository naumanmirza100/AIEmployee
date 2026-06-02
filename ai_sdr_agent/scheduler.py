"""
SDR Embedded Scheduler
======================
Uses APScheduler BackgroundScheduler for robust in-process job scheduling.
Jobs are re-registered every time Django starts via AppConfig.ready().

Why APScheduler instead of threading.Timer:
  - max_instances=1     →  no job stacking if a run takes longer than the interval
  - coalesce=True       →  missed firings don't pile up after a restart / sleep
  - misfire_grace_time  →  a job that fires up to 5 min late still runs (no silent drop)
  - ThreadPoolExecutor  →  proper thread-pool lifecycle, not ad-hoc daemon threads
  - DB connection close →  each worker thread closes its Django DB connection when done
  - atexit + signal     →  clean shutdown on Ctrl-C / gunicorn SIGTERM

Jobs
----
  send_due_steps        every 5 min   (first run 30 s after startup)
  check_inbox_replies   every 5 min   (first run 60 s after startup)
  auto_start_campaigns  every 15 min  (first run 90 s after startup)
  auto_pause_expired    every 60 min  (first run 120 s after startup)
  meeting_reminders     every 60 min  (first run 150 s after startup)
  daily_analytics       every 24 h    (first run 180 s after startup)
"""

import atexit
import datetime
import logging
import threading

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

# ── Module-level state ───────────────────────────────────────────────────────
_scheduler: BackgroundScheduler | None = None
_lock = threading.Lock()


# ── DB connection cleanup ────────────────────────────────────────────────────

def _close_db():
    """
    Close the thread-local Django DB connection after every job.
    APScheduler reuses threads from its pool; without this the connection
    can go stale (timeout / OperationalError) between runs.
    """
    try:
        from django.db import connection
        connection.close()
    except Exception:
        pass


# ── Job wrappers ─────────────────────────────────────────────────────────────

def _run_send_due_steps():
    try:
        from ai_sdr_agent.tasks import send_due_steps_impl
        result = send_due_steps_impl()
        if result:
            logger.debug("SDR send_due_steps → %s", result)
    except Exception as exc:
        logger.exception("SDR send_due_steps crashed: %s", exc)
    finally:
        _close_db()


def _run_check_inbox():
    try:
        from ai_sdr_agent.tasks import check_inbox_replies_impl
        result = check_inbox_replies_impl()
        if result:
            logger.debug("SDR check_inbox → %s", result)
    except Exception as exc:
        logger.exception("SDR check_inbox crashed: %s", exc)
    finally:
        _close_db()


def _run_auto_start():
    try:
        from ai_sdr_agent.tasks import auto_start_campaigns_impl
        result = auto_start_campaigns_impl()
        if result:
            logger.debug("SDR auto_start → %s", result)
    except Exception as exc:
        logger.exception("SDR auto_start crashed: %s", exc)
    finally:
        _close_db()


def _run_auto_complete():
    try:
        from ai_sdr_agent.tasks import auto_pause_expired_campaigns_impl
        result = auto_pause_expired_campaigns_impl()
        if result:
            logger.debug("SDR auto_complete → %s", result)
    except Exception as exc:
        logger.exception("SDR auto_complete crashed: %s", exc)
    finally:
        _close_db()


def _run_meeting_reminders():
    try:
        from ai_sdr_agent.tasks import send_meeting_reminders_impl
        result = send_meeting_reminders_impl()
        if result:
            logger.debug("SDR meeting_reminders → %s", result)
    except Exception as exc:
        logger.exception("SDR meeting_reminders crashed: %s", exc)
    finally:
        _close_db()


def _run_daily_analytics():
    try:
        from ai_sdr_agent.tasks import send_daily_analytics_impl
        result = send_daily_analytics_impl()
        if result:
            logger.debug("SDR daily_analytics → %s", result)
    except Exception as exc:
        logger.exception("SDR daily_analytics crashed: %s", exc)
    finally:
        _close_db()


# ── APScheduler event listener ───────────────────────────────────────────────

def _on_job_event(event):
    if event.code == EVENT_JOB_MISSED:
        logger.warning("SDR scheduler: job '%s' missed its fire time", event.job_id)
    elif event.code == EVENT_JOB_ERROR:
        logger.error(
            "SDR scheduler: job '%s' raised an unhandled exception: %s",
            event.job_id, event.exception,
        )
    # EVENT_JOB_EXECUTED → debug already handled inside each wrapper


# ── Public API ───────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    """
    Start the BackgroundScheduler. Idempotent — safe to call multiple times.
    If the scheduler is already running this is a no-op.
    """
    global _scheduler

    with _lock:
        if _scheduler is not None and _scheduler.running:
            logger.debug("SDR scheduler: already running — skipping start")
            return

        executors = {
            # 4 threads: enough to run all jobs in parallel if they overlap
            'default': ThreadPoolExecutor(max_workers=4),
        }
        job_defaults = {
            'coalesce': True,           # collapse multiple missed runs into one
            'max_instances': 1,         # never run the same job concurrently
            'misfire_grace_time': 300,  # run a job if it fires within 5 min of its due time
        }

        _scheduler = BackgroundScheduler(
            executors=executors,
            job_defaults=job_defaults,
            timezone='UTC',
        )
        _scheduler.add_listener(
            _on_job_event,
            EVENT_JOB_ERROR | EVENT_JOB_MISSED | EVENT_JOB_EXECUTED,
        )

        # ── Job registry ─────────────────────────────────────────────────────
        # (job_id, callable, interval_seconds, initial_delay_seconds)
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        jobs = [
            ('send_due_steps',    _run_send_due_steps,     300,    30),
            ('check_inbox',       _run_check_inbox,         300,    60),
            ('auto_start',        _run_auto_start,          900,    90),
            ('auto_complete',     _run_auto_complete,       3600,  120),
            ('meeting_reminders', _run_meeting_reminders,   3600,  150),
            ('daily_analytics',   _run_daily_analytics,    86400,  180),
        ]

        for job_id, func, interval, delay in jobs:
            _scheduler.add_job(
                func,
                trigger='interval',
                seconds=interval,
                id=job_id,
                name=f'sdr-{job_id}',
                start_date=now + datetime.timedelta(seconds=delay),
                replace_existing=True,
            )

        _scheduler.start()

        # Ensure clean shutdown when the Python process exits (Ctrl-C, SIGTERM, etc.)
        atexit.register(stop_scheduler)

        logger.info(
            "SDR scheduler started (APScheduler %s) — "
            "send_due_steps(5m), check_inbox(5m), auto_start(15m), "
            "auto_complete(1h), meeting_reminders(1h), daily_analytics(24h)",
            _apscheduler_version(),
        )


def stop_scheduler() -> None:
    """Gracefully stop the scheduler (called by atexit and Django shutdown signal)."""
    global _scheduler
    with _lock:
        if _scheduler is not None and _scheduler.running:
            try:
                _scheduler.shutdown(wait=False)
                logger.info("SDR scheduler stopped")
            except Exception as exc:
                logger.warning("SDR scheduler shutdown error: %s", exc)
            _scheduler = None


def get_scheduler() -> BackgroundScheduler | None:
    """Return the live scheduler instance, or None if not started."""
    return _scheduler


def scheduler_status() -> dict:
    """
    Return a status dict suitable for a health-check API endpoint.
    Example: {"running": true, "jobs": [{"id": "send_due_steps", "next_run": "..."}]}
    """
    s = _scheduler
    if s is None or not s.running:
        return {"running": False, "jobs": []}

    jobs = []
    for job in s.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
        })
    return {"running": True, "jobs": jobs}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _apscheduler_version() -> str:
    try:
        import apscheduler
        return apscheduler.__version__
    except Exception:
        return "unknown"

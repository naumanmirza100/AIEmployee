"""
Auto Lead Research Middleware
Runs Apify lead research automatically in background every 24 hours.
"""

import logging
import threading
import time

from django.utils import timezone

logger = logging.getLogger(__name__)

# 24 hours between Apify runs
RESEARCH_INTERVAL = 24 * 60 * 60

_last_run_time = None
_run_lock = threading.Lock()
_bg_thread = None
_bg_running = False
_bg_lock = threading.Lock()


class AutoLeadResearchMiddleware:
    """Background middleware that fetches new leads from Apify every 24 hours."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._start_background_thread()
        logger.info("AutoLeadResearchMiddleware initialized")

    def _start_background_thread(self):
        global _bg_thread, _bg_running
        with _bg_lock:
            if _bg_running:
                return
            _bg_running = True

            def loop():
                logger.info("Apify lead research background thread started")
                while _bg_running:
                    try:
                        time.sleep(RESEARCH_INTERVAL)
                        if not _bg_running:
                            break
                        logger.info("Apify auto-research: starting scheduled run")
                        from ai_sdr_agent.tasks import auto_research_leads_impl
                        result = auto_research_leads_impl(leads_per_run=10)
                        logger.info("Apify auto-research completed: %s", result)
                    except Exception as exc:
                        logger.error("Apify background thread error: %s", exc, exc_info=True)
                        time.sleep(60)

            _bg_thread = threading.Thread(target=loop, daemon=True)
            _bg_thread.start()

    def __call__(self, request):
        return self.get_response(request)

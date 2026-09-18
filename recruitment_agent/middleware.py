"""
Middleware that starts a background thread which checks for and sends
interview follow-up emails every CHECK_INTERVAL.

Requests no longer trigger a check of their own. They used to start a new
thread every 30 seconds whenever any request arrived — and the dashboards
poll every 30 seconds — so an open browser tab alone started ~120 threads an
hour. Each new thread opened its own database connection, and the database
user is allowed only 500 new connections an hour. The background thread
already runs the same check on the same interval, and keeps its connection
between runs (`check_and_send_followup_emails` calls close_old_connections).
"""

from django.utils import timezone
from datetime import timedelta
import threading
import logging
import time

logger = logging.getLogger(__name__)

CHECK_INTERVAL = timedelta(seconds=30)  # Check every 30 seconds (reduced for testing small intervals like 0.1 hours)

# Background thread control
_background_thread = None
_background_thread_running = False
_background_thread_lock = threading.Lock()


class AutoInterviewFollowupMiddleware:
    """
    Starts (once per process) the background thread that sends follow-up
    emails. Requests pass straight through.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self._start_background_thread()
        logger.info("AutoInterviewFollowupMiddleware initialized and active")
    
    def _start_background_thread(self):
        """Start a background thread that runs follow-up checks periodically"""
        global _background_thread, _background_thread_running
        
        with _background_thread_lock:
            if _background_thread_running:
                return  # Already running
            
            _background_thread_running = True
            
            def background_check_loop():
                """Background thread that runs follow-up checks periodically"""
                logger.info("Background follow-up check thread started")
                
                while _background_thread_running:
                    try:
                        # Wait for the check interval
                        time.sleep(CHECK_INTERVAL.total_seconds())
                        
                        if not _background_thread_running:
                            break
                        
                        # Run the follow-up check
                        logger.info(f"Background thread triggered follow-up check at {timezone.now()}")
                        
                        # Import and run the check function directly
                        from recruitment_agent.tasks import check_and_send_followup_emails
                        stats = check_and_send_followup_emails()
                        logger.info(f"Background thread follow-up check completed: {stats}")
                        
                    except Exception as e:
                        logger.error(f"Error in background follow-up thread: {str(e)}", exc_info=True)
                        # Continue running even if there's an error
                        time.sleep(5)  # Wait a bit before retrying
                
                logger.info("Background follow-up check thread stopped")
            
            _background_thread = threading.Thread(target=background_check_loop, daemon=True)
            _background_thread.start()
    
    def __del__(self):
        """Stop background thread when middleware is destroyed"""
        global _background_thread_running
        _background_thread_running = False
    
    def __call__(self, request):
        return self.get_response(request)

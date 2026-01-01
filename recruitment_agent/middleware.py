"""
Middleware to automatically check and send follow-up emails on each request.
This ensures emails are sent automatically without needing cron jobs.
"""

from django.utils import timezone
from datetime import timedelta
import threading
import logging

logger = logging.getLogger(__name__)

# Track last check time to avoid checking on every request
_last_check_time = None
_check_lock = threading.Lock()
CHECK_INTERVAL = timedelta(minutes=30)  # Check every 30 minutes


class AutoInterviewFollowupMiddleware:
    """
    Middleware that automatically checks and sends follow-up emails.
    Runs in background thread to avoid slowing down requests.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Check if we should run the follow-up check
        global _last_check_time
        
        with _check_lock:
            now = timezone.now()
            should_check = False
            
            if _last_check_time is None:
                should_check = True
            elif (now - _last_check_time) >= CHECK_INTERVAL:
                should_check = True
            
            if should_check:
                _last_check_time = now
                # Run check in background thread
                thread = threading.Thread(target=self._run_followup_check)
                thread.daemon = True
                thread.start()
        
        response = self.get_response(request)
        return response
    
    def _run_followup_check(self):
        """Run the follow-up email check in background"""
        try:
            from recruitment_agent.tasks import check_and_send_followup_emails
            stats = check_and_send_followup_emails()
            logger.info(f"🤖 Auto follow-up check completed: {stats}")
        except Exception as e:
            logger.error(f"Error in auto follow-up check middleware: {str(e)}", exc_info=True)


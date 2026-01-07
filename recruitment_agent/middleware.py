"""
Middleware to automatically check and send follow-up emails on each request.
Also runs a background thread that checks periodically regardless of requests.
"""

from django.utils import timezone
from datetime import timedelta
import threading
import logging
import time

logger = logging.getLogger(__name__)

# Track last check time to avoid checking on every request
_last_check_time = None
_check_lock = threading.Lock()
CHECK_INTERVAL = timedelta(seconds=30)  # Check every 30 seconds (reduced for testing small intervals like 0.1 hours)

# Background thread control
_background_thread = None
_background_thread_running = False
_background_thread_lock = threading.Lock()


class AutoInterviewFollowupMiddleware:
    """
    Middleware that automatically checks and sends follow-up emails.
    Runs in background thread to avoid slowing down requests.
    Also starts a background thread that runs checks periodically.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self._start_background_thread()
        print("\n" + "="*70)
        print("✅ AutoInterviewFollowupMiddleware LOADED")
        print("="*70)
        print("   📧 Follow-up email checking is ACTIVE")
        print(f"   ⏱️  Check interval: {CHECK_INTERVAL.total_seconds() / 60} minutes")
        print("   🔄 Checks will run automatically on each request")
        print("   🔄 Background thread will run checks every 30 seconds (even without requests)")
        print("="*70 + "\n")
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
                print("\n🔄 Starting background follow-up check thread...")
                logger.info("Background follow-up check thread started")
                
                while _background_thread_running:
                    try:
                        # Wait for the check interval
                        time.sleep(CHECK_INTERVAL.total_seconds())
                        
                        if not _background_thread_running:
                            break
                        
                        # Run the follow-up check
                        print(f"\n🔄 [BACKGROUND THREAD] Running periodic follow-up check at {timezone.now()}")
                        logger.info(f"Background thread triggered follow-up check at {timezone.now()}")
                        
                        # Import and run the check function directly
                        from recruitment_agent.tasks import check_and_send_followup_emails
                        stats = check_and_send_followup_emails()
                        logger.info(f"🤖 Background thread follow-up check completed: {stats}")
                        
                    except Exception as e:
                        print(f"\n❌ ERROR in background follow-up thread: {str(e)}")
                        logger.error(f"Error in background follow-up thread: {str(e)}", exc_info=True)
                        # Continue running even if there's an error
                        time.sleep(5)  # Wait a bit before retrying
                
                print("\n🛑 Background follow-up check thread stopped")
                logger.info("Background follow-up check thread stopped")
            
            _background_thread = threading.Thread(target=background_check_loop, daemon=True)
            _background_thread.start()
            print("✅ Background thread started successfully")
    
    def __del__(self):
        """Stop background thread when middleware is destroyed"""
        global _background_thread_running
        _background_thread_running = False
    
    def __call__(self, request):
        # Check if we should run the follow-up check
        global _last_check_time
        
        with _check_lock:
            now = timezone.now()
            should_check = False
            
            if _last_check_time is None:
                should_check = True
                print(f"\n🔄 [MIDDLEWARE] First check triggered at {now}")
            elif (now - _last_check_time) >= CHECK_INTERVAL:
                should_check = True
                time_since_last = (now - _last_check_time).total_seconds()
                print(f"\n🔄 [MIDDLEWARE] Check interval reached ({time_since_last:.1f}s since last check)")
            
            if should_check:
                _last_check_time = now
                # Run check in background thread
                thread = threading.Thread(target=self._run_followup_check)
                thread.daemon = True
                thread.start()
            # else:
            #     time_since_last = (now - _last_check_time).total_seconds() if _last_check_time else 0
            #     remaining = (CHECK_INTERVAL.total_seconds() - time_since_last) if _last_check_time else 0
            #     print(f"⏳ [MIDDLEWARE] Waiting... ({remaining:.1f}s until next check)")
        
        response = self.get_response(request)
        return response
    
    def _run_followup_check(self):
        """Run the follow-up email check in background"""
        try:
            from recruitment_agent.tasks import check_and_send_followup_emails
            print(f"\n🔄 Middleware triggered follow-up check at {timezone.now()}")
            logger.info(f"Middleware triggered follow-up check at {timezone.now()}")
            stats = check_and_send_followup_emails()
            logger.info(f"🤖 Auto follow-up check completed: {stats}")
        except Exception as e:
            print(f"\n❌ ERROR in middleware follow-up check: {str(e)}")
            logger.error(f"Error in auto follow-up check middleware: {str(e)}", exc_info=True)


"""
Celery configuration for Django project.
Handles all marketing automation tasks (replaces Windows Task Scheduler).
"""
import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')

# Import db_backends early to patch mssql backend and prevent REGEXP_LIKE errors
# This must be imported BEFORE Django setup to patch the backend before model introspection
try:
    import project_manager_ai.db_backends
except ImportError:
    pass  # If patching fails, continue (might not be using SQL Server)

app = Celery('project_manager_ai')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
# Wrap in try-except to handle database connection issues during startup
# This is especially important for SQL Server which may have compatibility issues
try:
    app.autodiscover_tasks()
except Exception as e:
    # Log the error but don't fail completely - allows Celery to start even if some tasks can't be discovered
    import logging
    import traceback
    logger = logging.getLogger(__name__)
    error_msg = str(e)
    error_type = type(e).__name__
    
    # Check if it's a database-related error (like REGEXP_LIKE)
    if 'REGEXP_LIKE' in error_msg or 'ProgrammingError' in error_type or 'database' in error_msg.lower():
        logger.warning(f"Database error during task autodiscovery (likely REGEXP_LIKE issue): {error_type}")
        logger.warning("This is a known SQL Server compatibility issue. Celery will continue.")
    else:
        logger.warning(f"Error during task autodiscovery: {error_type}: {error_msg}")
    
    logger.warning("Celery will continue, but some tasks may not be available")
    
    # Try to discover tasks from specific apps that we know exist
    # This allows Celery to start even if autodiscovery fails
    try:
        import marketing_agent.tasks
        logger.info("Successfully loaded marketing_agent.tasks manually")
    except Exception as import_error:
        logger.warning(f"Could not manually import marketing_agent.tasks: {import_error}")


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')

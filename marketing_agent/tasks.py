"""
Celery tasks for marketing agent automation
"""
from celery import shared_task
from django.core.management import call_command
import logging

logger = logging.getLogger(__name__)

@shared_task
def send_sequence_emails_task():
    """
    Celery task to send sequence emails automatically.
    This calls the Django management command.
    
    This task should be scheduled via Celery Beat to run every 30 minutes.
    """
    try:
        logger.info('Starting sequence emails task...')
        call_command('send_sequence_emails')
        logger.info('Sequence emails task completed successfully')
        return 'Success'
    except Exception as e:
        logger.error(f'Error in sequence emails task: {str(e)}', exc_info=True)
        raise



"""
Core periodic tasks for module subscription management.
"""
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name='core.tasks.expire_module_purchases')
def expire_module_purchases():
    """
    Check all active module purchases and mark expired ones.
    Runs every hour via Celery Beat.
    """
    from core.models import CompanyModulePurchase

    now = timezone.now()
    expired_purchases = CompanyModulePurchase.objects.filter(
        status='active',
        expires_at__isnull=False,
        expires_at__lt=now,
    )

    count = expired_purchases.count()
    if count > 0:
        expired_purchases.update(status='expired')
        logger.info('Auto-expired %d module purchase(s).', count)
    else:
        logger.debug('No module purchases to expire.')

    return f'Expired {count} purchase(s)'

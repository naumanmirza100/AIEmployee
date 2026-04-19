"""
Frontline Agent periodic tasks.
"""
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name='Frontline_agent.tasks.wake_snoozed_tickets')
def wake_snoozed_tickets():
    """
    Clear the snooze on tickets whose snoozed_until has passed.
    Runs on a short cadence so woken tickets reappear in queues promptly.
    """
    from Frontline_agent.models import Ticket

    now = timezone.now()
    qs = Ticket.objects.filter(snoozed_until__isnull=False, snoozed_until__lte=now)
    count = qs.update(snoozed_until=None)
    if count:
        logger.info("Woke %d snoozed tickets", count)
    return {'woken': count}

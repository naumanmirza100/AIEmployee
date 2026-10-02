"""
Core periodic tasks for module subscription management.
"""
import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name='core.tasks.send_notification_email')
def send_notification_email(company_user_id, topic_key, title, message, link=None):
    """One alert by email to one dashboard login (core.notification_settings)."""
    from core.notification_settings import deliver
    return deliver(company_user_id, topic_key, title, message, link)


@shared_task(name='core.tasks.reset_weekly_token_quotas')
def reset_weekly_token_quotas():
    """Apply every managed-token reset that is due right now.

    This is a thin delegate to `core.api_key_service.run_due_token_resets`,
    which is the single canonical reset implementation (also driven by the
    APScheduler `token_resets` job).

    It used to carry its own copy of the reset logic, which diverged from the
    canonical one in two ways that corrupted the reset history: it advanced
    next_reset_at in hard-coded 7-day steps (ignoring the key's
    reset_interval_days, so daily keys jumped a week), and it never wrote a
    WeeklyResetLog row, so a quota reset by this task showed as
    "Not yet reset" in the admin UI forever. Whichever engine won the race
    decided both outcomes. Delegating keeps beat scheduling intact while
    guaranteeing one behaviour.
    """
    from core.api_key_service import run_due_token_resets

    result = run_due_token_resets()
    logger.info(
        "reset_weekly_token_quotas: applied %s of %s due",
        result.get('applied'), result.get('checked'),
    )
    return f"Reset {result.get('applied', 0)} quota(s)"


@shared_task(name='core.tasks.expire_managed_keys')
def expire_managed_keys():
    """
    Auto-expire managed keys whose valid_until has passed.
    Runs every hour.
    """
    from core.models import CompanyAPIKey, CompanyUser
    now = timezone.now()
    expired_keys = CompanyAPIKey.objects.filter(
        mode='managed',
        status='active',
        valid_until__isnull=False,
        valid_until__lte=now,
    ).select_related('company')

    count = 0
    for key in expired_keys:
        key.status = 'expired'
        key.save(update_fields=['status', 'updated_at'])
        count += 1

        from core.api_key_service import record_key_event
        record_key_event(key.company, key.agent_name, 'expired', key=key,
                         note='Auto-expired: valid_until passed')

        try:
            from project_manager_agent.models import PMNotification
            agent_label = key.get_agent_name_display()
            for cu in CompanyUser.objects.filter(company=key.company, is_active=True):
                PMNotification.objects.create(
                    company_user=cu,
                    notification_type='custom',
                    severity='critical',
                    title=f"Managed key expired — {agent_label}",
                    message=(
                        f"Your managed key for {agent_label} has expired. "
                        f"Please request a new key from the admin to continue."
                    ),
                )
        except Exception as exc:
            logger.warning("Failed to send expiry notification for key %s: %s", key.id, exc)

        logger.info("Managed key expired: company=%s agent=%s key=%s",
                    key.company_id, key.agent_name, key.id)

    return f'Expired {count} managed key(s)'


@shared_task(name='core.tasks.expire_module_purchases')
def expire_module_purchases():
    """
    Auto-expire the purchases whose expiry we own locally, once past expires_at:
    legacy one-time purchases, and admin-granted complimentary access.

    Live Stripe subscriptions are excluded — their lifecycle is driven by webhooks
    and `current_period_end`, not by this sweep. Complimentary rows are included
    even when they carry a subscription id, because that id belongs to an already
    cancelled subscription and no webhook will ever expire the row for us.

    Runs every hour via Celery Beat.
    """
    from django.db.models import Q
    from core.models import CompanyModulePurchase

    now = timezone.now()
    expired_purchases = CompanyModulePurchase.objects.filter(
        Q(stripe_subscription_id__isnull=True) | Q(is_complimentary=True),
        status='active',
        expires_at__isnull=False,
        expires_at__lt=now,
    )

    count = expired_purchases.count()
    if count > 0:
        expired_purchases.update(status='expired')
        logger.info('Auto-expired %d legacy module purchase(s).', count)
    else:
        logger.debug('No legacy module purchases to expire.')

    return f'Expired {count} legacy purchase(s)'


@shared_task(name='core.tasks.rebuild_calendar_blocks')
def rebuild_calendar_blocks():
    """Nightly repair of the shared busy-time table (`CalendarBlock`).

    Meeting saves keep the table current through signals; this catches the
    changes signals can't see (queryset `.update()`, a user deactivated or
    moved between companies, an HR employee's login linked or unlinked).
    Runs once a day via Celery Beat — one database connection, well inside
    the host's hourly connection limit.
    """
    from core.scheduling.sync import rebuild

    stats = rebuild()
    total = sum(s['blocks'] for s in stats.values())
    logger.info('rebuild_calendar_blocks: %s', stats)
    return f'Rebuilt {total} calendar block(s)'


# How long a document may sit in `pending` / `processing` with no progress
# before it is called stuck. Progress (`updated_at`) moves at the start and
# after every batch of chunks; parsing a very large scanned PDF is the longest
# silent stretch, hence the margin. A job that was merely slow still finishes
# and sets itself back to `ready`.
DOCUMENT_STALL_MINUTES = 30

_NEVER_STARTED = ("Processing never started. The background worker may be down. "
                  "Press Retry to process it again.")
_STOPPED = ("Processing stopped before it finished. The background worker may have "
            "restarted. Press Retry to process it again.")


def stalled_documents(model, now=None):
    """`model`'s documents stuck in `pending` / `processing` (Frontline and HR
    documents share these fields)."""
    cutoff = (now or timezone.now()) - timedelta(minutes=DOCUMENT_STALL_MINUTES)
    return model.objects.filter(processing_status__in=('pending', 'processing'),
                                updated_at__lt=cutoff)


def is_stalled(document, now=None):
    cutoff = (now or timezone.now()) - timedelta(minutes=DOCUMENT_STALL_MINUTES)
    return (document.processing_status in ('pending', 'processing')
            and document.updated_at is not None and document.updated_at < cutoff)


@shared_task(name='core.tasks.fail_stalled_documents')
def fail_stalled_documents():
    """Mark Frontline and HR documents that stopped processing as failed.

    They used to show "processing" forever: when the queue is reachable but no
    worker takes the job, or a worker dies partway, nothing ever updated the
    row. Failing it tells the user and shows the Retry button. It is not
    re-queued here: the original job may still be waiting in the queue, and
    two copies running together would interleave their chunks.
    """
    from Frontline_agent.models import Document
    from hr_agent.models import HRDocument

    failed = 0
    for model in (Document, HRDocument):
        for doc in stalled_documents(model):
            doc.processing_error = _NEVER_STARTED if doc.processing_status == 'pending' else _STOPPED
            doc.processing_status = 'failed'
            doc.save(update_fields=['processing_status', 'processing_error', 'updated_at'])
            failed += 1
    if failed:
        logger.warning('fail_stalled_documents: marked %d stuck document(s) failed', failed)
    return f'Marked {failed} stuck document(s) failed'

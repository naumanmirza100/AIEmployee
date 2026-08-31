"""
Core periodic tasks for module subscription management.
"""
import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


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

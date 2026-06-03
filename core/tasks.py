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
    """
    Reset managed token quotas that are due for their weekly reset.
    Runs every hour — only acts on quotas whose next_reset_at has passed.

    For each due quota:
      - managed_used_tokens → 0
      - managed_included_tokens → tokens_per_period from the managed key
      - next_reset_at → advanced by 7 days
      - notification flags reset
      - Company notified via PMNotification
    """
    from core.models import AgentTokenQuota, CompanyAPIKey

    now = timezone.now()
    due_quotas = AgentTokenQuota.objects.filter(
        next_reset_at__isnull=False,
        next_reset_at__lte=now,
    ).select_related('company')

    count = 0
    for quota in due_quotas:
        # Get the active managed key to read tokens_per_period
        managed_key = CompanyAPIKey.objects.filter(
            company=quota.company,
            agent_name=quota.agent_name,
            mode='managed',
            status='active',
        ).first()

        if not managed_key or not managed_key.renewal_period or managed_key.renewal_period == 'none':
            # No renewal — clear next_reset_at so this never fires again
            AgentTokenQuota.objects.filter(pk=quota.pk).update(next_reset_at=None)
            continue

        if not managed_key.tokens_per_period or managed_key.tokens_per_period <= 0:
            continue

        # Advance next_reset_at by 7-day steps until it is in the future
        next_reset = quota.next_reset_at
        while next_reset <= now:
            next_reset = next_reset + timedelta(days=7)

        AgentTokenQuota.objects.filter(pk=quota.pk).update(
            managed_used_tokens=0,
            managed_included_tokens=managed_key.tokens_per_period,
            next_reset_at=next_reset,
            last_reset_at=now,
            managed_notified_80pct=False,
            managed_notified_90pct=False,
            managed_notified_100pct=False,
        )
        count += 1

        # Notify company
        try:
            from project_manager_agent.models import PMNotification
            from core.models import CompanyUser
            agent_label = managed_key.get_agent_name_display()
            for cu in CompanyUser.objects.filter(company=quota.company, is_active=True):
                PMNotification.objects.create(
                    company_user=cu,
                    notification_type='custom',
                    severity='info',
                    title=f"Weekly tokens reset — {agent_label}",
                    message=(
                        f"Your weekly token quota for {agent_label} has been reset. "
                        f"{managed_key.tokens_per_period:,} tokens are available again. "
                        f"Next reset: {next_reset.strftime('%d %b %Y')}."
                    ),
                )
        except Exception as exc:
            logger.warning("Failed to send weekly reset notification for %s/%s: %s",
                           quota.company_id, quota.agent_name, exc)

        logger.info("Weekly token reset: company=%s agent=%s tokens=%s next_reset=%s",
                    quota.company_id, quota.agent_name,
                    managed_key.tokens_per_period, next_reset)

    return f'Reset {count} quota(s)'


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

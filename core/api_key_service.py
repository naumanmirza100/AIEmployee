"""Central API key resolution + quota enforcement for agents.

Call flow every LLM request should go through:

    from core.api_key_service import resolve_for_call, record_usage, QuotaExhausted, NoKeyAvailable

    try:
        ctx = resolve_for_call(company, 'frontline_agent')
    except (QuotaExhausted, NoKeyAvailable) as exc:
        # hard-block — surface exc.reason to the user / frontend
        raise

    client = OpenAI(api_key=ctx.api_key)  # or Groq(api_key=...)
    response = client.chat.completions.create(...)
    record_usage(ctx, total_tokens=response.usage.total_tokens)

The resolver prefers BYOK over managed. BYOK has no quota; managed decrements
AgentTokenQuota.used_tokens and hard-blocks when exhausted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.db.models import F

from core.models import (
    AGENT_CHOICES,
    AGENT_DEFAULT_PROVIDER,
    AdminPricingConfig,
    AgentProviderUsage,
    AgentTokenQuota,
    CompanyAPIKey,
    DEFAULT_FREE_TOKENS,
    PlatformAPIKey,
)


VALID_AGENTS = {name for name, _ in AGENT_CHOICES}


class KeyServiceError(Exception):
    """Base for hard-block errors — catch and surface `.reason` to the user."""
    reason: str = "unknown"
    user_message: str = "LLM call blocked."


class QuotaExhausted(KeyServiceError):
    reason = "quota_exhausted"
    user_message = (
        "Free tokens for this agent are exhausted. Add your own API key (BYOK) "
        "or request a managed key from the admin."
    )


class ManagedQuotaExhausted(KeyServiceError):
    reason = "managed_quota_exhausted"
    user_message = (
        "Your managed key token limit has been reached. "
        "Contact your admin to increase the limit or add your own API key (BYOK)."
    )


class NoKeyAvailable(KeyServiceError):
    reason = "no_key"
    user_message = (
        "No API key is configured for this agent. Add your own API key (BYOK) "
        "or request a managed key from the admin."
    )


class InvalidAgent(KeyServiceError):
    reason = "invalid_agent"
    user_message = "Unknown agent."


@dataclass
class CallContext:
    """Everything a caller needs for one LLM call."""
    company_id: int
    agent_name: str
    mode: str          # 'byok' | 'managed'
    provider: str      # 'openai' | 'claude' | ...
    api_key: str       # decrypted plaintext — DO NOT log or return to user
    key_id: int        # CompanyAPIKey.pk
    quota_id: Optional[int] = None  # AgentTokenQuota.pk (managed only)


def _ensure_quota(company, agent_name: str) -> AgentTokenQuota:
    """Get or create the quota row for this (company, agent).

    Called on first managed-mode use if the purchase signal somehow missed it
    (defensive). Pulls included_tokens from AdminPricingConfig at creation time.
    """
    quota = AgentTokenQuota.objects.filter(company=company, agent_name=agent_name).first()
    if quota:
        return quota
    try:
        cfg = AdminPricingConfig.objects.get(agent_name=agent_name)
        included = cfg.free_tokens_on_purchase
    except AdminPricingConfig.DoesNotExist:
        included = DEFAULT_FREE_TOKENS
    return AgentTokenQuota.objects.create(
        company=company, agent_name=agent_name, included_tokens=included
    )


def resolve_for_call(company, agent_name: str) -> CallContext:
    """Pick the key to use for one LLM call. Raises on hard-block.

    Preference order:
      1. Active BYOK key (no quota — info-only metering)
      2. Active per-company managed key (admin override) — bypasses platform quota
      3. Quota exhausted? → hard block (platform path only)
      4. Platform key for the agent's default provider (the "free tokens" path)
      5. Hard block: no key available anywhere

    BYOK and managed keys both bypass the platform quota gate because they
    bring their own API keys.  Platform quota only gates the free-tier path.
    """
    if agent_name not in VALID_AGENTS:
        raise InvalidAgent()

    # Step 1 — BYOK wins, always (no quota consumed)
    byok = (
        CompanyAPIKey.objects
        .filter(company=company, agent_name=agent_name, mode='byok', status='active')
        .first()
    )
    if byok:
        plaintext = byok.get_plaintext_key()
        if plaintext:
            return CallContext(
                company_id=company.id,
                agent_name=agent_name,
                mode='byok',
                provider=byok.provider,
                api_key=plaintext,
                key_id=byok.id,
            )

    # Step 2 — per-company managed key (admin-assigned) bypasses platform quota
    managed = (
        CompanyAPIKey.objects
        .filter(company=company, agent_name=agent_name, mode='managed', status='active')
        .first()
    )
    if managed:
        plaintext = managed.get_plaintext_key()
        if plaintext:
            quota = _ensure_quota(company, agent_name)
            # Enforce managed token limit when admin set one (>0)
            if quota.managed_included_tokens > 0 and quota.managed_used_tokens >= quota.managed_included_tokens:
                raise ManagedQuotaExhausted()
            return CallContext(
                company_id=company.id,
                agent_name=agent_name,
                mode='managed',
                provider=managed.provider,
                api_key=plaintext,
                key_id=managed.id,
                quota_id=quota.id,
            )

    # Step 3 — quota gate (platform-key path only)
    quota = _ensure_quota(company, agent_name)
    if quota.is_exhausted:
        raise QuotaExhausted()

    # Step 4 — platform default key (the "free tokens" path)
    default_provider = AGENT_DEFAULT_PROVIDER.get(agent_name, 'openai')
    platform = PlatformAPIKey.objects.filter(provider=default_provider, status='active').first()
    if platform:
        plaintext = platform.get_plaintext_key()
        if plaintext:
            return CallContext(
                company_id=company.id,
                agent_name=agent_name,
                mode='platform',
                provider=platform.provider,
                api_key=plaintext,
                key_id=platform.id,
                quota_id=quota.id,
            )

    # Step 5 — nothing configured anywhere
    raise NoKeyAvailable()


def _check_quota_notifications(quota_id: int) -> None:
    """Fire 80% / 90% / 100% notifications exactly once per threshold crossing."""
    try:
        from core.notification_utils import notify_company_quota
        q = AgentTokenQuota.objects.select_related('company').get(pk=quota_id)
        if q.included_tokens <= 0:
            return
        pct = (q.used_tokens / q.included_tokens) * 100
        actual = round(pct, 1)

        if pct >= 100 and not q.notified_100pct:
            AgentTokenQuota.objects.filter(pk=quota_id).update(notified_100pct=True)
            notify_company_quota(q.company, q.get_agent_name_display(), 100, actual_pct=actual)
        elif pct >= 90 and not q.notified_90pct:
            AgentTokenQuota.objects.filter(pk=quota_id).update(notified_90pct=True)
            notify_company_quota(q.company, q.get_agent_name_display(), 90, actual_pct=actual)
        elif pct >= 80 and not q.notified_80pct:
            AgentTokenQuota.objects.filter(pk=quota_id).update(notified_80pct=True)
            notify_company_quota(q.company, q.get_agent_name_display(), 80, actual_pct=actual)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Quota notification check failed: %s", exc)


def record_usage(ctx: CallContext, total_tokens: int) -> None:
    """Increment the right counter after an LLM call completes.

    Managed: decrements remaining quota (atomic F-update, safe under concurrency).
    BYOK: bumps info-only counter; never blocks.
    """
    total_tokens = int(total_tokens or 0)
    if total_tokens <= 0:
        return

    if ctx.mode == 'platform' and ctx.quota_id:
        AgentTokenQuota.objects.filter(pk=ctx.quota_id).update(
            used_tokens=F('used_tokens') + total_tokens
        )
        # Per-provider breakdown — atomic upsert
        updated = AgentProviderUsage.objects.filter(
            quota_id=ctx.quota_id, provider=ctx.provider
        ).update(used_tokens=F('used_tokens') + total_tokens)
        if not updated:
            try:
                AgentProviderUsage.objects.create(
                    quota_id=ctx.quota_id, provider=ctx.provider, used_tokens=total_tokens
                )
            except Exception:
                AgentProviderUsage.objects.filter(
                    quota_id=ctx.quota_id, provider=ctx.provider
                ).update(used_tokens=F('used_tokens') + total_tokens)

        # Quota threshold notifications (fire once per threshold)
        _check_quota_notifications(ctx.quota_id)

    elif ctx.mode == 'managed' and ctx.quota_id:
        # Managed key has its own counter so it never pollutes the platform quota
        AgentTokenQuota.objects.filter(pk=ctx.quota_id).update(
            managed_used_tokens=F('managed_used_tokens') + total_tokens
        )

    elif ctx.mode == 'byok':
        AgentTokenQuota.objects.filter(
            company_id=ctx.company_id, agent_name=ctx.agent_name
        ).update(byok_tokens_info=F('byok_tokens_info') + total_tokens)


@transaction.atomic
def provision_quota_on_purchase(company, agent_name: str) -> AgentTokenQuota:
    """Called from the CompanyModulePurchase post_save signal.

    Idempotent — if a quota already exists (re-purchase, renewal) we leave it
    alone rather than resetting used_tokens.
    """
    if agent_name not in VALID_AGENTS:
        return None
    return _ensure_quota(company, agent_name)

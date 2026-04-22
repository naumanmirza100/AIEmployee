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
      2. Quota exhausted? → hard block (blocks BOTH managed + platform paths)
      3. Active per-company managed key (admin override)
      4. Platform key for the agent's default provider (the "free tokens" path)
      5. Hard block: no key available anywhere

    Step 1 is BEFORE the quota check because BYOK users don't consume quota,
    so an exhausted quota shouldn't stop them if they have their own key.
    """
    if agent_name not in VALID_AGENTS:
        raise InvalidAgent()

    # Step 1 — BYOK wins, always
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

    # Step 2 — quota gate (applies to managed + platform paths)
    quota = _ensure_quota(company, agent_name)
    if quota.is_exhausted:
        raise QuotaExhausted()

    # Step 3 — per-company managed override, if admin assigned one
    managed = (
        CompanyAPIKey.objects
        .filter(company=company, agent_name=agent_name, mode='managed', status='active')
        .first()
    )
    if managed:
        plaintext = managed.get_plaintext_key()
        if plaintext:
            return CallContext(
                company_id=company.id,
                agent_name=agent_name,
                mode='managed',
                provider=managed.provider,
                api_key=plaintext,
                key_id=managed.id,
                quota_id=quota.id,
            )

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


def record_usage(ctx: CallContext, total_tokens: int) -> None:
    """Increment the right counter after an LLM call completes.

    Managed: decrements remaining quota (atomic F-update, safe under concurrency).
    BYOK: bumps info-only counter; never blocks.
    """
    total_tokens = int(total_tokens or 0)
    if total_tokens <= 0:
        return

    if ctx.mode in ('managed', 'platform') and ctx.quota_id:
        AgentTokenQuota.objects.filter(pk=ctx.quota_id).update(
            used_tokens=F('used_tokens') + total_tokens
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

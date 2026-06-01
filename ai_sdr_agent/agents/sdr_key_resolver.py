"""
Shared API-key resolver for all AI SDR Agent sub-agents.

Usage in each agent __init__:
    from ai_sdr_agent.agents.sdr_key_resolver import resolve_sdr_groq_client
    self.groq_client, self._key_ctx = resolve_sdr_groq_client(company)

After every Groq call:
    from ai_sdr_agent.agents.sdr_key_resolver import record_sdr_usage
    record_sdr_usage(self._key_ctx, response.usage.total_tokens)
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

AGENT_KEY = 'ai_sdr_agent'


def resolve_sdr_groq_client(company) -> Tuple[Optional[object], Optional[object]]:
    """Return (groq_client, ctx) for the given company using the platform key service.

    Raises core.api_key_service.KeyServiceError subclasses on hard-block
    (quota exhausted, agent disabled, etc.) — let these propagate to the view layer.
    Returns (None, None) only on unexpected SDK/import errors (not key errors).
    """
    from core.api_key_service import resolve_for_call
    # KeyServiceError propagates directly — NOT inside try/except
    ctx = resolve_for_call(company, AGENT_KEY)
    try:
        from groq import Groq
        client = Groq(api_key=ctx.api_key)
        return client, ctx
    except Exception as exc:
        logger.error("SDR Groq SDK init failed: %s", exc)
        return None, None


def record_sdr_usage(ctx, total_tokens: int) -> None:
    """Record token usage after a successful Groq call."""
    if ctx is None or not total_tokens:
        return
    try:
        from core.api_key_service import record_usage
        record_usage(ctx, total_tokens=int(total_tokens))
    except Exception as exc:
        logger.warning("SDR usage recording failed: %s", exc)

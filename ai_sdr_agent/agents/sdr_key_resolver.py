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
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

AGENT_KEY = 'ai_sdr_agent'


class _Reporting:
    """`client.chat.completions`, except that a key the provider refuses is
    raised as `BadAPIKey`. Every AI SDR agent already lets a KeyServiceError
    through; anything else it catches and carries on without AI, which is how
    a wrong key used to go unnoticed for good."""

    def __init__(self, completions, ctx):
        self._completions = completions
        self._ctx = ctx

    def create(self, *args, **kwargs):
        started = time.monotonic()
        try:
            response = self._completions.create(*args, **kwargs)
        except Exception as exc:
            _log_call(self._ctx, kwargs.get('model'), started, False)
            from core.api_key_service import raise_if_auth_error
            raise_if_auth_error(exc, self._ctx)
            raise
        usage = getattr(response, 'usage', None)
        _log_call(self._ctx, kwargs.get('model'), started, True, usage and {
            'prompt_tokens': getattr(usage, 'prompt_tokens', 0),
            'completion_tokens': getattr(usage, 'completion_tokens', 0),
            'total_tokens': getattr(usage, 'total_tokens', 0)})
        return response


def _log_call(ctx, model, started, success, usage=None):
    """One LLMUsage row per AI call, so the API Keys page counts AI SDR's calls and failures. It showed 0 (CO-69)."""
    from project_manager_agent.ai_agents.base_agent import _record_llm_usage
    _record_llm_usage(company_id=getattr(ctx, 'company_id', None), agent_name='AISDRAgent', model=model,
                      usage_dict=usage, duration_ms=(time.monotonic() - started) * 1000, success=success,
                      agent=AGENT_KEY)


class _CheckedGroq:
    def __init__(self, client, ctx):
        self._client = client
        self.chat = type('Chat', (), {})()
        self.chat.completions = _Reporting(client.chat.completions, ctx)

    def __getattr__(self, name):
        return getattr(self._client, name)


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
        return _CheckedGroq(client, ctx), ctx
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

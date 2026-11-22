"""What an AI call costs, in US dollars (22 Nov 2026).

Every agent writes one `LLMUsage` row per call with its tokens (`project_manager_agent.ai_agents.base_agent.
_record_llm_usage`). The price map there knew a few Groq models and gpt-4.1, so gpt-4.1-mini, which the live site
runs on, was priced at a $0.50 default. Spend is worked out from the tokens with this table when it is read, so a
correction here also corrects the past.

Prices per million tokens, (input, output), as the providers publish them for the standard tier. A model is matched by
the longest name it starts with ('gpt-4.1-mini-2025-04-14' is gpt-4.1-mini). `settings.AI_PRICES_PER_MTOK` (a dict of
the same shape) overrides or adds models without a release.
"""
from decimal import Decimal

from django.conf import settings

PRICES_PER_MTOK = {
    # OpenAI
    'gpt-4.1-nano': (0.10, 0.40),
    'gpt-4.1-mini': (0.40, 1.60),
    'gpt-4.1': (2.00, 8.00),
    'gpt-4o-mini': (0.15, 0.60),
    'gpt-4o': (2.50, 10.00),
    'gpt-5-nano': (0.05, 0.40),
    'gpt-5-mini': (0.25, 2.00),
    'gpt-5': (1.25, 10.00),
    'gpt-image-1-mini': (2.00, 8.00),        # text in, image tokens out
    'gpt-image-1': (5.00, 40.00),
    'text-embedding-3-small': (0.02, 0.0),
    'text-embedding-3-large': (0.13, 0.0),
    # Groq
    'openai/gpt-oss-20b': (0.10, 0.50),
    'openai/gpt-oss-120b': (0.15, 0.75),
    'llama-3.3-70b-versatile': (0.59, 0.79),
    'llama-3.1-70b-versatile': (0.59, 0.79),
    'llama-3.1-8b-instant': (0.05, 0.08),
    'gemma2-9b-it': (0.20, 0.20),
    'mixtral-8x7b-32768': (0.24, 0.24),
}
#: A model not in the table is counted at gpt-4.1's price: better to over-count than to miss spend.
UNKNOWN = (2.00, 8.00)


def price_of(model):
    """(input, output) dollars per million tokens for `model`, and whether it was in the table."""
    table = {**PRICES_PER_MTOK, **(getattr(settings, 'AI_PRICES_PER_MTOK', None) or {})}
    name = (model or '').strip().lower()
    for known in sorted(table, key=len, reverse=True):
        if name.startswith(known.lower()):
            return tuple(table[known]), True
    return UNKNOWN, False


def cost_usd(model, prompt_tokens, completion_tokens) -> Decimal:
    (inp, out), _ = price_of(model)
    cost = ((prompt_tokens or 0) * inp + (completion_tokens or 0) * out) / 1_000_000
    return Decimal(str(round(cost, 6)))

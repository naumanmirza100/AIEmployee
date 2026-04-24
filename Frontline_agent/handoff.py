"""Hand-off helpers for the Frontline Agent.

Two triggers flip a ticket into `handoff_status='pending'`:
  1. **AI low confidence** — QA couldn't find a verified answer (score < threshold).
  2. **Customer request** — the customer explicitly asked for a human.

`trigger_handoff()` is idempotent — calling twice doesn't re-stamp the
`handoff_requested_at` timestamp so the "time in queue" metric stays accurate.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Customer-asked-for-a-human detection
# --------------------------------------------------------------------------

# Keyword phrases that strongly signal the customer wants out of the bot.
# Match whole words with word boundaries so "humane" doesn't false-positive.
_HANDOFF_PATTERNS = [
    r'\btalk\s+to\s+(?:a\s+)?(?:human|person|agent|representative|rep|someone)\b',
    r'\bspeak\s+to\s+(?:a\s+)?(?:human|person|agent|representative|rep|someone)\b',
    r'\b(?:real|live|actual)\s+(?:human|person|agent)\b',
    r'\bhuman\s+(?:agent|support|help|please)\b',
    r'\b(?:get|give)\s+me\s+(?:a\s+)?(?:human|person|agent|rep)\b',
    r'\bneed\s+(?:a\s+)?(?:human|person|agent|rep)\b',
    r'\bcustomer\s+service\s+(?:representative|rep|agent)\b',
    r"\bi\s+(?:don'?t|do\s+not)\s+want\s+(?:to\s+)?(?:talk\s+to\s+)?(?:a\s+)?(?:bot|chatbot|ai)\b",
    r'\b(?:this|your)\s+(?:bot|chatbot|ai)\s+(?:is\s+)?(?:useless|not\s+helping|not\s+helpful)\b',
    r'\bescalat(?:e|ion)\b',
]
_HANDOFF_RE = re.compile('|'.join(_HANDOFF_PATTERNS), re.I)


def detect_handoff_request(text: str) -> bool:
    """True when the input text looks like a customer asking for a human.

    Deliberately conservative — false negatives are fine (AI can still answer)
    but false positives annoy customers who didn't ask for an agent.
    """
    if not text or not isinstance(text, str):
        return False
    # Hard cap so a 10 MB paste doesn't stall the regex engine.
    snippet = text[:5000]
    return bool(_HANDOFF_RE.search(snippet))


# --------------------------------------------------------------------------
# Hand-off state transitions
# --------------------------------------------------------------------------

VALID_REASONS = {'low_confidence', 'customer_requested', 'manual_escalation', 'sla_risk'}


def trigger_handoff(ticket, reason: str, context: Optional[dict] = None) -> bool:
    """Flip a ticket into pending hand-off. Idempotent — returns True the first
    time it does anything, False when the ticket is already pending/accepted."""
    if not ticket or ticket.handoff_status in ('pending', 'accepted'):
        return False
    if reason not in VALID_REASONS:
        logger.warning("trigger_handoff: unknown reason=%s (ignoring)", reason)
        return False

    ticket.handoff_status = 'pending'
    ticket.handoff_reason = reason
    ticket.handoff_context = _sanitize_context(context or {})
    ticket.handoff_requested_at = timezone.now()
    # When AI couldn't close it, we usually want priority bumped so it surfaces.
    # Don't downgrade higher priorities.
    if reason in ('customer_requested', 'low_confidence') and ticket.priority == 'low':
        ticket.priority = 'medium'
    ticket.save(update_fields=[
        'handoff_status', 'handoff_reason', 'handoff_context',
        'handoff_requested_at', 'priority', 'updated_at',
    ])
    logger.info("Ticket %s handoff requested (reason=%s)", ticket.id, reason)
    return True


def accept_handoff(ticket, user) -> bool:
    """Agent claims the hand-off. Assigns the ticket to them and records the
    acceptance timestamp. Returns True on state change."""
    if not ticket or ticket.handoff_status not in ('pending',):
        return False
    ticket.handoff_status = 'accepted'
    ticket.handoff_accepted_at = timezone.now()
    ticket.handoff_accepted_by = user
    ticket.assigned_to = user
    if ticket.status == 'new':
        ticket.status = 'open'
    ticket.save(update_fields=[
        'handoff_status', 'handoff_accepted_at', 'handoff_accepted_by',
        'assigned_to', 'status', 'updated_at',
    ])
    return True


def resolve_handoff(ticket) -> bool:
    """Called when the ticket is closed/resolved after hand-off. Idempotent."""
    if not ticket or ticket.handoff_status not in ('accepted', 'pending'):
        return False
    ticket.handoff_status = 'resolved'
    ticket.save(update_fields=['handoff_status', 'updated_at'])
    return True


def _sanitize_context(ctx: dict) -> dict:
    """Cap stored context size so a huge LLM answer can't balloon the row.
    We only keep the keys the UI actually renders."""
    if not isinstance(ctx, dict):
        return {}
    out: dict = {}
    for key in ('question', 'ai_answer', 'confidence', 'best_score',
                'threshold', 'channel', 'from_email', 'customer_text'):
        if key in ctx:
            v = ctx[key]
            if isinstance(v, str):
                v = v[:4000]
            out[key] = v
    return out

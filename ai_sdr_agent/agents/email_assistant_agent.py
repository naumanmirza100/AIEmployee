"""
Email Assistant Agent
---------------------
1. classify_reply()           — reads prospect reply → OOO / not interested / wants more / positive
2. improve_email()            — personalises outbound email content per lead
3. generate_more_info_email() — writes a "tell me more" follow-up response
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Categories ────────────────────────────────────────────────────────────────
CAT_OUT_OF_OFFICE  = 'out_of_office'
CAT_NOT_INTERESTED = 'not_interested'
CAT_WANTS_MORE     = 'wants_more_info'
CAT_POSITIVE       = 'positive_interest'
CAT_NEUTRAL        = 'neutral'

CATEGORY_ACTION = {
    CAT_OUT_OF_OFFICE:  'pause',
    CAT_NOT_INTERESTED: 'stop',
    CAT_WANTS_MORE:     'send_info',
    CAT_POSITIVE:       'book_meeting',
    CAT_NEUTRAL:        'wait',
}

CATEGORY_LABEL = {
    CAT_OUT_OF_OFFICE:  'Out of Office',
    CAT_NOT_INTERESTED: 'Not Interested',
    CAT_WANTS_MORE:     'Wants More Info',
    CAT_POSITIVE:       'Interested — Book Meeting',
    CAT_NEUTRAL:        'Neutral',
}

# ── Keyword banks ─────────────────────────────────────────────────────────────
_OOO = [
    'out of office', 'out of the office', 'on vacation', 'on leave',
    'annual leave', 'away from office', 'away until', 'back on',
    'back in office', 'currently unavailable', 'auto-reply', 'automatic reply',
    'will be back', 'return on', 'returning on', 'on holiday', 'i am away',
    "i'm away", 'i will be out', "i'll be out", 'maternity leave',
    'paternity leave', 'parental leave', 'limited access to email',
    'limited access to my email',
]

_NOT_INTERESTED = [
    'not interested', 'no thanks', 'no thank you', 'not relevant',
    'not a fit', 'not the right fit', 'please remove', 'unsubscribe',
    'stop emailing', 'stop contacting', 'do not contact', "don't contact",
    'remove me', 'take me off', 'opt out', 'not looking',
    'not in the market', 'not right now', 'not at this time',
    'not for us', 'we already have', 'we use another', 'not a priority',
    'no budget', 'going with someone else', 'not pursuing',
    'please stop', 'kindly remove',
]

_WANTS_MORE = [
    'tell me more', 'more information', 'more info', 'more details',
    'learn more', 'can you explain', 'how does it work', 'sounds interesting',
    'interested to learn', 'what is your', "what's your", 'send me',
    'share more', 'curious about', 'want to know more', 'would like to know',
    'could you elaborate', 'what are the', 'how much', 'pricing', 'cost',
    'what does it include', 'case study', 'can you share', 'how does',
    'tell us more', 'please share', 'what exactly',
]

_POSITIVE = [
    "let's connect", "let's talk", "let's schedule", "let's meet",
    'schedule a call', 'book a meeting', 'book a call', 'happy to chat',
    'happy to connect', 'set up a call', 'set up a meeting',
    'yes i am interested', "yes i'm interested", 'sounds good', 'would love to',
    'absolutely', 'definitely', 'when are you available', 'available for a call',
    'open for a meeting', 'yes please', 'count me in', "i'm in", 'i am in',
    'let us connect', 'open to a chat', 'interested in a demo', 'book a demo',
]


class EmailAssistantAgent:
    """Reads, classifies, and responds to prospect emails intelligently."""

    def __init__(self, company=None):
        self._key_ctx = None
        self.groq_client = None

        if company is not None:
            from ai_sdr_agent.agents.sdr_key_resolver import resolve_sdr_groq_client
            self.groq_client, self._key_ctx = resolve_sdr_groq_client(company)
        else:
            logger.warning(
                "EmailAssistantAgent initialised without a company — no LLM key resolved."
            )

        self.model = getattr(settings, 'GROQ_MODEL', 'llama-3.1-8b-instant')

    # ── classify_reply ────────────────────────────────────────────────────────

    def classify_reply(self, reply_text: str) -> dict:
        """
        Classify a prospect reply.

        Returns:
            {
                'category':      str   (one of CAT_* constants),
                'action':        str   ('pause' | 'stop' | 'send_info' | 'book_meeting' | 'wait'),
                'label':         str   (human-readable),
                'confidence':    str   ('high' | 'low'),
                'reason':        str,
                'is_interested': bool,
                'resume_date':   datetime | None,
            }
        """
        if not reply_text or not reply_text.strip():
            return self._result(CAT_NEUTRAL, confidence='high', reason='Empty reply')

        lower = reply_text.lower()

        # OOO first — most distinct signal
        if any(k in lower for k in _OOO):
            return self._result(
                CAT_OUT_OF_OFFICE,
                reason='Out-of-office detected',
                resume_date=self._extract_return_date(reply_text),
            )

        if any(k in lower for k in _NOT_INTERESTED):
            return self._result(CAT_NOT_INTERESTED, reason='Not-interested keyword match')

        if any(k in lower for k in _POSITIVE):
            return self._result(CAT_POSITIVE, reason='Positive-interest keyword match')

        if any(k in lower for k in _WANTS_MORE):
            return self._result(CAT_WANTS_MORE, reason='Wants-more-info keyword match')

        # Ambiguous — use AI
        if self.groq_client:
            return self._ai_classify(reply_text)

        return self._result(CAT_NEUTRAL, confidence='low', reason='No keyword match, no AI available')

    # ── improve_email ─────────────────────────────────────────────────────────

    def improve_email(self, subject: str, body: str, lead, campaign_context: dict | None = None) -> dict:
        """Personalise outbound email for a specific lead. Falls back to original if AI unavailable."""
        if not self.groq_client:
            return {'subject': subject, 'body': body}

        ctx = campaign_context or {}
        prompt = f"""You are a top B2B sales email writer. Improve this email to be personalised for the specific prospect below.

Prospect:
- Name: {lead.full_name or f"{lead.first_name} {lead.last_name}".strip()}
- Title: {lead.job_title or 'N/A'}
- Company: {lead.company_name or 'N/A'}
- Industry: {lead.company_industry or 'N/A'}

Sender: {ctx.get('sender_name','')} — {ctx.get('sender_title','')} at {ctx.get('sender_company','')}

Original subject: {subject}
Original body:
{body}

Rules:
- Under 130 words
- Use prospect's real name and company
- Remove generic openers like "I hope this finds you well"
- One specific CTA only
- Sound human

Return ONLY JSON: {{"subject": "...", "body": "..."}}"""

        try:
            resp = self.groq_client.chat.completions.create(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.4,
                max_tokens=600,
            )
            from ai_sdr_agent.agents.sdr_key_resolver import record_sdr_usage
            record_sdr_usage(self._key_ctx, getattr(resp.usage, 'total_tokens', 0))
            content = resp.choices[0].message.content.strip()
            if '```' in content:
                content = content.split('```')[1].lstrip('json').strip()
            data = json.loads(content)
            return {
                'subject': data.get('subject', subject)[:500],
                'body': data.get('body', body),
            }
        except Exception as exc:
            from core.api_key_service import KeyServiceError
            if isinstance(exc, KeyServiceError):
                raise
            logger.warning('EmailAssistantAgent.improve_email failed: %s', exc)
            return {'subject': subject, 'body': body}

    # ── generate_more_info_email ──────────────────────────────────────────────

    def generate_more_info_email(self, lead, campaign, original_reply: str = '') -> dict:
        """Generate a follow-up email when prospect says 'tell me more'."""
        first_name = lead.first_name or (lead.full_name or '').split()[0] if (lead.full_name or '').split() else 'there'
        calendar = campaign.calendar_link or ''

        if not self.groq_client:
            return {
                'subject': f"Re: More about {campaign.sender_company}",
                'body': (
                    f"Hi {first_name},\n\n"
                    f"Thanks for your interest! Happy to share more.\n\n"
                    + (f"You can book a quick 15-min call here: {calendar}\n\n" if calendar else "Feel free to reply and I'll share details.\n\n")
                    + f"Best,\n{campaign.sender_name}"
                ),
            }

        prompt = f"""Write a SHORT reply to a prospect who asked for more information about our product/service.

Prospect: {lead.full_name}, {lead.job_title or ''} at {lead.company_name or ''}
Their reply: "{original_reply[:300]}"
Sender: {campaign.sender_name}, {campaign.sender_title} at {campaign.sender_company}
Calendar link: {calendar or '(none)'}

Write a reply that:
- Opens warmly, acknowledges their interest
- Gives 2-3 concise bullet points about key benefits
- Ends with a single CTA to book a call {"at: " + calendar if calendar else "(ask to reply with availability)"}
- Under 120 words total
- Conversational, not salesy

Return ONLY JSON: {{"subject": "...", "body": "..."}}"""

        try:
            resp = self.groq_client.chat.completions.create(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.5,
                max_tokens=500,
            )
            from ai_sdr_agent.agents.sdr_key_resolver import record_sdr_usage
            record_sdr_usage(self._key_ctx, getattr(resp.usage, 'total_tokens', 0))
            content = resp.choices[0].message.content.strip()
            if '```' in content:
                content = content.split('```')[1].lstrip('json').strip()
            data = json.loads(content)
            return {
                'subject': data.get('subject', f"Re: {campaign.sender_company} — More Details")[:500],
                'body': data.get('body', ''),
            }
        except Exception as exc:
            from core.api_key_service import KeyServiceError
            if isinstance(exc, KeyServiceError):
                raise
            logger.warning('EmailAssistantAgent.generate_more_info_email failed: %s', exc)
            return {
                'subject': f"Re: More about {campaign.sender_company}",
                'body': (
                    f"Hi {first_name},\n\nGreat to hear you're curious!\n\n"
                    + (f"Book a quick call: {calendar}\n\n" if calendar else "")
                    + f"Best,\n{campaign.sender_name}"
                ),
            }

    # ── Private ───────────────────────────────────────────────────────────────

    def _ai_classify(self, reply_text: str) -> dict:
        prompt = f"""Classify this sales email reply into one category.

Reply:
\"\"\"{reply_text[:600]}\"\"\"

Categories:
- out_of_office    : auto-reply, vacation, away message
- not_interested   : clearly rejecting, asking to stop, unsubscribing
- wants_more_info  : asking questions, curious, wants details or pricing
- positive_interest: ready to meet, schedule a call, book a demo, says yes
- neutral          : vague, unclear, off-topic

Return ONLY JSON: {{"category": "...", "reason": "one sentence explanation"}}"""

        try:
            resp = self.groq_client.chat.completions.create(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.1,
                max_tokens=120,
            )
            from ai_sdr_agent.agents.sdr_key_resolver import record_sdr_usage
            record_sdr_usage(self._key_ctx, getattr(resp.usage, 'total_tokens', 0))
            content = resp.choices[0].message.content.strip()
            if '```' in content:
                content = content.split('```')[1].lstrip('json').strip()
            data = json.loads(content)
            cat = data.get('category', CAT_NEUTRAL)
            if cat not in CATEGORY_ACTION:
                cat = CAT_NEUTRAL
            return self._result(cat, confidence='high', reason=data.get('reason', 'AI classified'))
        except Exception as exc:
            from core.api_key_service import KeyServiceError
            if isinstance(exc, KeyServiceError):
                raise
            logger.warning('EmailAssistantAgent._ai_classify failed: %s', exc)
            return self._result(CAT_NEUTRAL, confidence='low', reason='AI classification failed')

    @staticmethod
    def _result(category: str, confidence: str = 'high', reason: str = '', resume_date=None) -> dict:
        return {
            'category':      category,
            'action':        CATEGORY_ACTION.get(category, 'wait'),
            'label':         CATEGORY_LABEL.get(category, category),
            'confidence':    confidence,
            'reason':        reason,
            'is_interested': category in (CAT_POSITIVE, CAT_WANTS_MORE),
            'resume_date':   resume_date,
        }

    @staticmethod
    def _extract_return_date(text: str):
        """Parse OOO return date. Falls back to now + 5 days."""
        patterns = [
            r'back (?:on|from)\s+([\w]+ \d{1,2}(?:,?\s*\d{4})?)',
            r'return(?:ing)? (?:on|from)\s+([\w]+ \d{1,2}(?:,?\s*\d{4})?)',
            r'(?:until|till)\s+([\w]+ \d{1,2}(?:,?\s*\d{4})?)',
            r'available (?:again )?(?:on|from)\s+([\w]+ \d{1,2}(?:,?\s*\d{4})?)',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                try:
                    from dateutil import parser as dp
                    dt = dp.parse(m.group(1), fuzzy=True)
                    aware = timezone.make_aware(dt.replace(hour=9, minute=0, second=0))
                    return aware + timedelta(days=1)  # 1-day buffer after return
                except Exception:
                    pass
        return timezone.now() + timedelta(days=5)

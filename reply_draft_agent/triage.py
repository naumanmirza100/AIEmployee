"""Triage: the AI reads each new email as it arrives and says what kind it is, how soon it needs someone, and what it
says in one sentence.

A mail was read by the AI only when someone asked for a draft, with no priority or category (the AI Employee
list's Email Assistant, 30 Oct 2026). `triage_inbox_task` runs every five minutes, after the mailbox read, over the
mail that has not been read yet. Only recent mail is read, so connecting a mailbox with months of history costs no
AI tokens on the backlog.
"""
import logging
import re

from .models import CATEGORY_CHOICES, PRIORITY_CHOICES
from .text import for_ai, parse_json

logger = logging.getLogger(__name__)

CATEGORIES = [c for c, _ in CATEGORY_CHOICES]
PRIORITIES = [p for p, _ in PRIORITY_CHOICES]
#: Mail older than this is not read by the AI.
WINDOW_DAYS = 7
#: Emails read per mailbox in one run of the job; the rest wait for the next run.
PER_RUN = 15

SYSTEM_PROMPT = """You sort a company's incoming email for the person who answers it.

Read the email, in whatever language it is written (English, Urdu, Roman Urdu), and return ONLY this JSON:
{"category": "...", "priority": "...", "summary": "...", "needs_reply": true}

category, one of:
- customer: a customer or prospect asks a question about the company's products or services
- sales: a new lead, an enquiry about buying, a request for a quote or a demo
- support: something does not work, a complaint, a problem to fix
- billing: an invoice, a payment, a refund, a quotation to pay
- meeting: arranging, moving or cancelling a meeting or call
- internal: from a colleague inside the company
- newsletter: a newsletter, notification, receipt, marketing mail or any automatic message
- personal: personal mail
- other: none of these

priority, one of:
- urgent: needs someone today: something broken or a service down, an angry customer, a payment or deadline due
  today or tomorrow, a legal or security matter
- high: a customer or lead is waiting for an answer
- normal: a person should read it, but nothing is waiting on it
- low: newsletters, notifications, receipts, automatic messages

summary: one sentence in English, at most 25 words, saying who wants or tells what. Name the person, with their
company when the email gives it, never "the sender": "Kiran Shah (Capital Dental) asks the monthly price for two
branches." Only what the email says: no guesses, no greeting, no advice.

needs_reply: true when the sender asks something or waits for an answer; false otherwise."""

# Words a no-reply or bulk sender leaves, for the fallback when the AI's answer cannot be read.
_BULK = re.compile(r'no-?reply|newsletter|notifications?@|mailer-daemon|unsubscribe|do not reply', re.IGNORECASE)


def triage_prompt(email) -> str:
    sender = f'{email.from_name} <{email.from_email}>' if email.from_name else email.from_email
    lines = [f'From: {sender}']
    if email.reply_to:
        lines.append(f'Reply-To: {email.reply_to}')
    lines += [
        f'To: {email.to_email or ""}',
        f'Subject: {email.subject or "(no subject)"}',
        '',
        for_ai(email.body, limit=3000) or '(empty body)',
    ]
    return '\n'.join(lines)


def read_triage(raw: str) -> dict:
    """The AI's answer as the email's fields; KeyError/ValueError when it cannot be read."""
    data = parse_json(raw)
    category = str(data.get('category', '')).strip().lower()
    priority = str(data.get('priority', '')).strip().lower()
    summary = ' '.join(str(data.get('summary', '')).split())
    if category not in CATEGORIES or priority not in PRIORITIES or not summary:
        raise ValueError(f'unreadable triage: {raw[:200]}')
    return {
        'category': category,
        'priority': priority,
        'ai_summary': summary[:300],
        'needs_reply': bool(data.get('needs_reply')),
    }


def fallback_triage(email) -> dict:
    """Without the AI: only what the headers make certain (an automatic sender), and the subject as the summary."""
    automatic = bool(_BULK.search(f'{email.from_email} {email.from_name} {(email.body or "")[-600:]}'))
    return {
        'category': 'newsletter' if automatic else 'other',
        'priority': 'low' if automatic else 'normal',
        'ai_summary': (email.subject or '')[:300],
        'needs_reply': not automatic,
    }


class AIUnreachable(Exception):
    """The AI could not be asked just now (a connection error, a timeout): the email waits for the next run."""


def triage_email(email, agent) -> dict:
    """The AI's reading of one email. A key or quota problem is raised as it is, and an AI that cannot be reached
    as AIUnreachable: either way the email stays unread and is tried again. Only an answer that came back and
    cannot be read gives the fallback, so one odd email cannot hold up the mailbox. A connection error used to
    give the fallback too, and the email kept the plain reading for good (the Reply Draft film, 30 Oct)."""
    from core.api_key_service import KeyServiceError
    try:
        raw = agent._call_llm(prompt=triage_prompt(email), system_prompt=SYSTEM_PROMPT,
                              temperature=0, max_tokens=300)
    except KeyServiceError:
        raise
    except Exception as exc:
        raise AIUnreachable(str(exc)) from exc
    try:
        return read_triage(raw)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        logger.warning('triage: email %s read by the fallback: %s', email.id, exc)
        return fallback_triage(email)

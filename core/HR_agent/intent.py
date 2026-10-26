"""What a message to HR's question boxes asks for, read by one small AI call — as Project Manager's pilot_intent.

The floating chat, the Q&A tab and My Space's "Ask HR" sent every message to the document search. "kal ki chutti
chahiye" (I need leave tomorrow) or "cancel my leave" got policy text, or "I'll route this to the HR team", which
routes nothing; a question in Roman Urdu found nothing in English documents; a follow-up ("and for managers?") was
searched with the whole conversation in front of it. Asked for on 26 Oct 2026, the same fix as Project Pilot's:

- the reading says whether the message is a question, a request for leave, a cancellation, or about a meeting;
- a request the boxes can't carry out is answered with where it is done (`redirect`), not with policy text;
- a question comes back restated in English, standalone (the conversation's "it" filled in), and that is what the
  documents are searched with; it also says whether the question wants a complete list (the whole-document mode).

With no reading (switched off by `HR_AI_INTENT`, the call failed, or it wasn't sure), the boxes work as before.
"""
from __future__ import annotations

import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

KINDS = ('question', 'leave_request', 'leave_cancel', 'meeting', 'other')
MIN_CONFIDENCE = 0.6

_PROMPT = """You read one message sent to a company's HR assistant, which answers questions from the company's HR
documents (policies, handbook) and the asker's own HR record (their leave balance, manager). It cannot put in leave,
cancel leave or book meetings: those are done on screens.

{history}Message: {message}

The message may have typos, be in another phrasing, or be in Roman Urdu / Hinglish (e.g. "chutti" = leave,
"kal" = tomorrow, "parson" = day after tomorrow, "kitni" = how many, "batao" = tell me, "meeting rakh do" = book a
meeting, "cancel kar do" = cancel it, "saari" / "sab" = all).

Return ONLY a JSON object:
{{"kind": one of "question" (asks for information, including about leave rules or the asker's balance),
          "leave_request" (wants time off put in: "I need leave tomorrow", "kal ki chutti chahiye"),
          "leave_cancel" (wants a leave request cancelled or withdrawn),
          "meeting" (wants a meeting booked, moved or cancelled),
          "other" (a greeting, thanks, or anything else),
 "english": the message as ONE standalone question or request in plain English, with anything it refers to from
            the conversation spelled out ("and for managers?" -> "How many days of annual leave do managers get?"),
 "full_list": true only when it asks for a complete list of something ("list all leave types", "saari leave types
              batao", "what are the different departments"), false for a question about one thing,
 "confidence": a number from 0 to 1}}"""


def read(message, history=None, *, company_id):
    """The reading of `message`, or None. Raises a key or quota error (the box reports those); anything else gives
    None, and the box works as before."""
    if not getattr(settings, 'HR_AI_INTENT', True) or not (message or '').strip():
        return None
    from core.api_key_service import KeyServiceError
    from core.HR_agent.hr_agent import HRAgent
    lines = []
    for turn in (history or [])[-6:]:
        if isinstance(turn, dict) and (turn.get('role') or '').lower() in ('user', 'assistant') and turn.get('content'):
            lines.append(f"{turn['role'].capitalize()}: {str(turn['content'])[:600]}")
    prompt = _PROMPT.format(history=('Conversation so far:\n' + '\n'.join(lines) + '\n\n') if lines else '',
                            message=str(message)[:2000])
    try:
        raw = HRAgent(company_id=company_id)._call_llm(
            prompt=prompt, system_prompt='You classify messages. Output only one JSON object.',
            temperature=0, max_tokens=400, json_mode=True)
        reading = json.loads((raw or '').strip().strip('`').removeprefix('json').strip())
    except KeyServiceError:
        raise
    except Exception as exc:
        logger.info('HR intent: no reading (%s: %s)', type(exc).__name__, exc)
        return None
    if not isinstance(reading, dict) or reading.get('kind') not in KINDS:
        return None
    try:
        if float(reading.get('confidence', 0)) < MIN_CONFIDENCE:
            return None
    except (TypeError, ValueError):
        return None
    english = str(reading.get('english') or '').strip()
    return {'kind': reading['kind'], 'english': english[:500] or None, 'full_list': reading.get('full_list') is True}


#: Where each request is done instead. `dashboard`: an HR dashboard login (the floating chat, the Q&A tab);
#: `my_space`: an employee's own page (/me/hr).
_WHERE = {
    ('leave_request', 'dashboard'): (
        "I can't put in leave from the chat. Open **Operations › Leave** in the HR menu and press **New request**: choose the "
        "person, the leave type, the dates and a reason. Whoever approves it is told straight away."),
    ('leave_request', 'my_space'): (
        "I can't put in leave from here. Use **Ask for leave** on this page: choose the leave type, the dates and a "
        "reason. Your manager or HR is told straight away, and their answer appears under **My leave requests**."),
    ('leave_cancel', 'dashboard'): (
        "I can't cancel leave from the chat. Open **Operations › Leave** in the HR menu, find the request and press **Cancel**, "
        "or **Withdraw** if it was already approved."),
    ('leave_cancel', 'my_space'): (
        "I can't cancel leave from here. Under **My leave requests** on this page, press **Cancel** next to a request "
        "that is still waiting; for leave already approved, ask HR."),
    ('meeting', 'dashboard'): (
        "I answer questions here. To book a meeting, open **Meetings** in the HR menu and describe it, for example "
        "\"1:1 with Ali tomorrow at 3 pm for 30 minutes\". To move or cancel one, use **Change time** or **Cancel** "
        "on it there."),
    ('meeting', 'my_space'): (
        "I answer questions here. HR books meetings; yours are on **My Meetings**, where you can accept one or "
        "suggest another time."),
}


def redirect(reading, where):
    """What to say instead of searching the documents, for a request the box can't carry out; None for a
    question."""
    if not reading:
        return None
    return _WHERE.get((reading['kind'], where))


NOT_IN_THE_DOCUMENTS = ("I couldn't find this in the company's HR documents, so I can't answer it reliably. "
                        "Please ask HR directly.")

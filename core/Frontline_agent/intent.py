"""What a message to Frontline asks for, read by one small AI call — as HR's and Project Pilot's readings.

Every message on the website chat went straight to the document search, and the only other decision, "does the
customer want a person", was a list of phrases (Frontline_agent/handoff.py). So:

- "hi" or "thanks" were searched, answered "I don't have verified information… a human agent will assist you",
  and opened a "KB gap: hi" ticket;
- "I don't need a human, just tell me the price" matched "need a human" and opened a hand-off;
- "kisi insaan se baat karwa do" (let me talk to a person) and other phrasings were missed;
- "can we have a call tomorrow?" and "our website has been down since morning" were searched like questions, and the
  customer was left with document text or "I don't have verified information";
- a question in Roman Urdu found nothing in English documents, and "list all your plans" was judged by word lists.

The reading says what the message is (a question, wanting a person, wanting a call, reporting a problem, a greeting,
thanks, or off-topic), whether it is urgent, the question restated in English for the search, and whether it asks for
a complete list. With no reading (switched off by `FRONTLINE_AI_INTENT`, the call failed, or it wasn't sure), the chat
works as before, word lists included.
"""
from __future__ import annotations

import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

KINDS = ('question', 'wants_person', 'wants_call', 'problem', 'greeting', 'thanks', 'off_topic')
MIN_CONFIDENCE = 0.6

_PROMPT = """You read one message a customer sent to a company's support chat. The chat answers questions from the
company's own help documents; a person from the company's team can take over.

{history}Message: {message}

The message may have typos, another phrasing, or be in Roman Urdu / Hinglish (e.g. "kisi insaan se baat karwa do" =
let me talk to a person, "call kar lein" = let's have a call, "website band hai" = the website is down, "kitne ka
hai" = how much is it, "batao" = tell me, "saare" / "sab" = all, "shukriya" = thanks, "assalam o alaikum" = hello).

Return ONLY a JSON object:
{{"kind": one of
     "question" (asks for information: prices, hours, how something works, what is included),
     "wants_person" (asks to talk to, or be contacted by, a person / human / agent / someone from the team; NOT when
                     they say they do NOT need one),
     "wants_call" (asks for a call, meeting, video call or demo to be arranged),
     "problem" (reports something wrong that needs someone to act: a fault, an outage, a wrong charge, a complaint),
     "greeting" (only a greeting, with no question),
     "thanks" (only thanks or goodbye, with no question),
     "off_topic" (nothing to do with the company or its services, e.g. the weather, jokes, homework),
 "urgent": true when the message says it is urgent or describes something stopping their business (down, can't
           take orders, charged twice), else false,
 "english": the message as ONE standalone question in plain English, with anything it refers to from the
            conversation spelled out ("and the yearly one?" -> "How much is the yearly support plan?"),
 "full_list": true only when it asks for a complete list ("what are all your plans", "saare services batao"),
 "roman_urdu": true when the message is written in Roman Urdu or Hinglish,
 "confidence": a number from 0 to 1}}"""


def read(message, history=None, *, company_id):
    """The reading of `message`, or None. Raises a key or quota error (the chat reports those); anything else gives
    None, and the chat works as before."""
    if not getattr(settings, 'FRONTLINE_AI_INTENT', True) or not (message or '').strip():
        return None
    from core.api_key_service import KeyServiceError
    from core.Frontline_agent.frontline_agent import FrontlineAgent
    lines = []
    for turn in (history or [])[-6:]:
        if isinstance(turn, dict) and (turn.get('role') or '').lower() in ('user', 'assistant') and turn.get('content'):
            lines.append(f"{turn['role'].capitalize()}: {str(turn['content'])[:600]}")
    prompt = _PROMPT.format(history=('Conversation so far:\n' + '\n'.join(lines) + '\n\n') if lines else '',
                            message=str(message)[:2000])
    try:
        raw = FrontlineAgent(company_id=company_id)._call_llm(
            prompt=prompt, system_prompt='You classify messages. Output only one JSON object.',
            temperature=0, max_tokens=400, json_mode=True)
        reading = json.loads((raw or '').strip().strip('`').removeprefix('json').strip())
    except KeyServiceError:
        raise
    except Exception as exc:
        logger.info('Frontline intent: no reading (%s: %s)', type(exc).__name__, exc)
        return None
    if not isinstance(reading, dict) or reading.get('kind') not in KINDS:
        return None
    try:
        if float(reading.get('confidence', 0)) < MIN_CONFIDENCE:
            return None
    except (TypeError, ValueError):
        return None
    english = str(reading.get('english') or '').strip()
    return {'kind': reading['kind'], 'english': english[:500] or None, 'full_list': reading.get('full_list') is True,
            'urgent': reading.get('urgent') is True, 'roman_urdu': reading.get('roman_urdu') is True}


#: What the chat says when it does not search: (English, Roman Urdu).
_SAY = {
    'greeting': ("Hello! I can answer questions about our services and support. What would you like to know? "
                 "You can also ask to talk to a person at any time.",
                 "Assalam o alaikum! Main hamari services aur support ke baare mein sawalon ke jawab de sakta hoon. "
                 "Aap kya jaanna chahte hain? Aap kisi bhi waqt kisi insaan se baat karne ko keh sakte hain."),
    'thanks': ("You're welcome! Is there anything else I can help you with?",
               "Koi baat nahi! Kya main kisi aur cheez mein madad kar sakta hoon?"),
    'off_topic': ("I can only help with questions about our services and support. Is there something about those I "
                  "can help with?",
                  "Main sirf hamari services aur support ke baare mein madad kar sakta hoon. Kya in mein se kisi "
                  "cheez ke baare mein poochna chahte hain?"),
    'wants_person': ("Of course. I've asked a person from our team to take over, and they'll reply to you as soon as "
                     "they can.",
                     "Zaroor. Main ne hamari team ke kisi shakhs ko keh diya hai, woh jald aap ko jawab denge."),
    'wants_call': ("I can't book calls myself, but I've asked our team to arrange one. They'll contact you to agree "
                   "a time.",
                   "Main khud call book nahi kar sakta, lekin main ne team ko keh diya hai. Woh waqt tay karne ke "
                   "liye aap se rabta karenge."),
    'problem': ("I'm sorry about this. I've passed it to our team, and a person will follow up with you.",
                "Is ke liye maazrat. Main ne yeh hamari team ko bhej diya hai, aur koi aap se jald rabta karega."),
    'problem_also': ("I've also passed this to our team, so a person will follow up with you.",
                     "Main ne yeh hamari team ko bhi bhej diya hai, koi aap se jald rabta karega."),
}


def say(key, reading):
    """The fixed reply for `key`, in Roman Urdu when the customer wrote in it."""
    english, roman_urdu = _SAY[key]
    return roman_urdu if reading and reading.get('roman_urdu') else english


#: Kinds answered without searching the documents.
NO_SEARCH = ('greeting', 'thanks', 'off_topic', 'wants_person', 'wants_call')
#: Kinds that put the conversation before a person, and the hand-off reason each gives.
HANDOFF_REASON = {'wants_person': 'customer_requested', 'wants_call': 'call_requested', 'problem': 'problem_reported'}

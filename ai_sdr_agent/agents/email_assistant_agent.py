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
CAT_UNSUBSCRIBE    = 'unsubscribe'
CAT_NOT_INTERESTED = 'not_interested'
CAT_WANTS_MORE     = 'wants_more_info'
CAT_POSITIVE       = 'positive_interest'
CAT_NEUTRAL        = 'neutral'

# Only an explicit request to stop is 'unsubscribe' (off every campaign of the company). 'Not interested' stops this
# campaign alone, and 'not right now' is left for a person (CO-145).
CATEGORY_ACTION = {
    CAT_OUT_OF_OFFICE:  'pause',
    CAT_UNSUBSCRIBE:    'unsubscribe',
    CAT_NOT_INTERESTED: 'stop',
    CAT_WANTS_MORE:     'send_info',
    CAT_POSITIVE:       'book_meeting',
    CAT_NEUTRAL:        'wait',
}

CATEGORY_LABEL = {
    CAT_OUT_OF_OFFICE:  'Out of Office',
    CAT_UNSUBSCRIBE:    'Unsubscribe',
    CAT_NOT_INTERESTED: 'Not Interested',
    CAT_WANTS_MORE:     'Wants More Info',
    CAT_POSITIVE:       'Interested — Book Meeting',
    CAT_NEUTRAL:        'Neutral',
}

# ── Keyword banks: used only when the AI cannot be asked ───────────────────────
_OOO = [
    'out of office', 'out of the office', 'on vacation', 'on leave',
    'annual leave', 'away from office', 'away until',
    'back in office', 'currently unavailable', 'auto-reply', 'automatic reply',
    'will be back', 'return on', 'returning on', 'on holiday', 'i am away',
    "i'm away", 'i will be out', "i'll be out", 'maternity leave',
    'paternity leave', 'parental leave', 'limited access to email',
    'limited access to my email',
]

_UNSUBSCRIBE = [
    'unsubscribe', 'stop emailing', 'stop contacting', 'do not contact', "don't contact",
    'do not email', "don't email", 'remove me', 'take me off', 'opt out', 'opt me out',
    'please remove', 'kindly remove', 'please stop', 'stop sending',
]

_NOT_INTERESTED = [
    'not interested', 'no thanks', 'no thank you', 'not relevant',
    'not a fit', 'not the right fit', 'not looking',
    'not in the market', 'not for us', 'we already have', 'we use another',
    'no budget', 'going with someone else', 'not pursuing',
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
    'when are you available', 'available for a call',
    'open for a meeting', 'yes please', 'count me in', "i'm in", 'i am in',
    'let us connect', 'open to a chat', 'interested in a demo', 'book a demo',
]


# ── Reply-text helpers ────────────────────────────────────────────────────────
# Where a mail client starts quoting the earlier thread. Everything from the
# first marker on is our own outbound text (which itself contains words like
# "unsubscribe" and "pricing"), so it must not be classified as the prospect's.
_QUOTE_START = re.compile(
    r'^[ \t]*(?:'
    r'on\s[^\n]{0,200}(?:\n[^\n]{0,200})?\swrote:'      # "On <date>, X wrote:" (may wrap)
    r'|-{2,}\s*(?:original message|forwarded message)\s*-{2,}'
    r'|_{10,}'
    r'|from:[^\n]*\n\s*(?:sent|date):'                  # Outlook header block
    r')',
    re.IGNORECASE | re.MULTILINE,
)


# Our own footer, which a reply can quote without the 'On ... wrote:' line (a mail program in another language):
# it says 'Unsubscribe' and must not be read as the lead's words (CO-145).
_OUR_FOOTER = re.compile(
    r"^[ \t>]*(?:-{2,3}[ \t]*$|.*?/api/sdr/unsubscribe/|.*?reply 'unsubscribe'|.*?don't want these emails\?)",
    re.IGNORECASE | re.MULTILINE,
)


# A question the campaign's words do not answer is neither confirmed nor denied: asked whether reminders go by
# WhatsApp, the AI answered "only SMS, not WhatsApp" from a description that mentions SMS (manual run, 30 Oct).
_NOT_IN_THE_FACTS = ('If they ask about something the facts above do not mention, do not say yes or no to it: '
                     'say you will check and come back to them, or that it can be covered on the call. Promise '
                     'nothing the facts do not offer (a discount, a version made for them, a date)')
# Answers state facts, so the AI is kept close to them: at 0.5 it added "it can be customised for both your branches"
# to a price question (the AI SDR film, 30 Oct).
_ANSWER_TEMPERATURE = 0.2


def strip_quoted_reply(text: str) -> str:
    """Return only what the prospect wrote, without the quoted earlier thread or our footer."""
    if not text:
        return ''
    m = _QUOTE_START.search(text)
    if m:
        text = text[:m.start()]
    m = _OUR_FOOTER.search(text)
    if m:
        text = text[:m.start()]
    return '\n'.join(
        line for line in text.splitlines() if not line.lstrip().startswith('>')
    ).strip()


def _keyword_regex(keywords):
    """Whole-word/phrase matcher, so "i'm in" doesn't fire inside "I'm interested"."""
    return re.compile(
        '|'.join(r'(?<![a-z0-9])' + re.escape(k) + r'(?![a-z0-9])' for k in keywords)
    )


_OOO_RE = _keyword_regex(_OOO)
_UNSUBSCRIBE_RE = _keyword_regex(_UNSUBSCRIBE)
_NOT_INTERESTED_RE = _keyword_regex(_NOT_INTERESTED)
_WANTS_MORE_RE = _keyword_regex(_WANTS_MORE)
_POSITIVE_RE = _keyword_regex(_POSITIVE)
_NEGATED = re.compile(r"^\W*(?:not|no|never)\b|^\W*(?:\w+\W+){0,2}(?:not|no|never)\b")


def _positive(lower: str) -> bool:
    """A positive phrase not followed closely by a 'not' ('sounds good, but not now' is not a yes)."""
    return any(not _NEGATED.match(lower[m.end():m.end() + 25]) for m in _POSITIVE_RE.finditer(lower))


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

        self.model = getattr(settings, 'GROQ_MODEL', 'openai/gpt-oss-20b')

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

        full_text = reply_text
        reply_text = strip_quoted_reply(reply_text)
        if not reply_text:
            return self._result(CAT_NEUTRAL, confidence='high', reason='Reply contained only quoted text')

        # The AI reads the reply. The word lists decided most replies before it was asked, and misread common ones:
        # 'Absolutely not' booked a meeting, 'not right now' opted the person out for good (CO-145).
        if self.groq_client:
            result = self._ai_classify(reply_text)
            if result['confidence'] == 'high':
                if result['category'] == CAT_OUT_OF_OFFICE:
                    result['resume_date'] = self._extract_return_date(full_text)
                return result
        return self._keyword_classify(reply_text, full_text)

    def _keyword_classify(self, reply_text: str, full_text: str) -> dict:
        """Only when the AI cannot be asked or does not answer."""
        lower = reply_text.lower()
        if _OOO_RE.search(lower):
            return self._result(CAT_OUT_OF_OFFICE, reason='Out-of-office detected',
                                resume_date=self._extract_return_date(full_text))
        if _UNSUBSCRIBE_RE.search(lower):
            return self._result(CAT_UNSUBSCRIBE, reason='Asked to stop the emails')
        if _NOT_INTERESTED_RE.search(lower):
            return self._result(CAT_NOT_INTERESTED, reason='Not-interested keyword match')
        if _positive(lower):
            return self._result(CAT_POSITIVE, reason='Positive-interest keyword match')
        if _WANTS_MORE_RE.search(lower):
            return self._result(CAT_WANTS_MORE, reason='Wants-more-info keyword match')
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
- You know only the four facts above about the prospect. Never say you have seen, read or noticed anything
  about them or their company (news, launches, plans, growth), and never guess what they are working on
- Add no fact, number, customer name or promise about our offer that is not in the original email

Return ONLY JSON: {{"subject": "...", "body": "..."}}"""

        try:
            # It used to make up things it had "seen" about the prospect, in an email sent in the
            # salesperson's name; the last two rules above are there for that.
            resp = self.groq_client.chat.completions.create(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.4,
                max_tokens=2000,
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

        # What the AI may say about the product is what the campaign says about it.
        # It used to be asked for "key benefits" with nothing to take them from, so
        # it made them up, in an email sent in the salesperson's name.
        about = ' '.join((campaign.description or '').split())[:1500]
        if about:
            facts = f'What we offer (the ONLY facts you may use about it): {about}'
            benefits = '- Gives 2-3 concise bullet points taken from "What we offer" above, in your own words'
        else:
            facts = 'What we offer: (nothing has been written down)'
            benefits = ('- Does NOT describe the product, list benefits, quote prices or make any claim about it: '
                        'you have been told nothing about it. Say you would be glad to walk them through it')

        prompt = f"""Write a SHORT reply to a prospect who asked for more information about our product/service.

Prospect: {lead.full_name}, {lead.job_title or ''} at {lead.company_name or ''}
Their reply: "{strip_quoted_reply(original_reply)[:300]}"
Sender: {campaign.sender_name}, {campaign.sender_title} at {campaign.sender_company}
Calendar link: {calendar or '(none)'}
{facts}

Write a reply that:
- Opens warmly, acknowledges their interest
{benefits}
- Never states a fact, number, price, customer name or feature that is not given above
- Answers their question if the facts above answer it
- {_NOT_IN_THE_FACTS}
- Ends with ONE sentence asking them to {"book a call at: " + calendar if calendar else "reply with a time that suits them for a short call"}; never two
- Signs off with "Best," and then {(campaign.sender_name or campaign.sender_company or 'the sender').split()[0]} on the next line
- Under 120 words total
- Conversational, not salesy
- In the same language and script as their reply (Roman Urdu stays in Latin letters)

Return ONLY JSON: {{"subject": "...", "body": "..."}}"""

        try:
            resp = self.groq_client.chat.completions.create(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}],
                temperature=_ANSWER_TEMPERATURE,
                max_tokens=2000,
            )
            from ai_sdr_agent.agents.sdr_key_resolver import record_sdr_usage
            record_sdr_usage(self._key_ctx, getattr(resp.usage, 'total_tokens', 0))
            content = resp.choices[0].message.content.strip()
            if '```' in content:
                content = content.split('```')[1].lstrip('json').strip()
            data = json.loads(content)
            return {
                'subject': data.get('subject', f"Re: {campaign.sender_company} — More Details")[:500],
                'body': self._checked_answer(about, strip_quoted_reply(original_reply), data.get('body', '')),
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

    # ── The Email Assistant screen ────────────────────────────────────────────
    # It was a "Coming soon" page (the client's list, part 6). Both use only what the person typed: the AI used to
    # make up things it had "seen" about a prospect, and benefits of an offer nobody had described.

    EMAIL_KINDS = {
        'first_email': 'a first email introducing what we offer',
        'follow_up': 'a short follow-up to a first email that had no answer',
        'meeting_request': 'an email asking for a short call',
        'last_touch': 'a polite last email saying this is the final note',
    }
    TONES = {
        'professional': 'professional and courteous',
        'friendly': 'warm and friendly, still businesslike',
        'direct': 'brief and direct, no small talk',
    }

    def _checked_answer(self, facts: str, their_words: str, body: str) -> str:
        """The answer read once more against the facts, by itself: a rule among many in the writing prompt was not
        enough. On live after PR #344 an answer still told Kiran "WhatsApp reminders are not currently included",
        in English to her Roman Urdu. Where the check fails, the answer stays as it was."""
        if not (body or '').strip():
            return body
        prompt = f"""You check a sales answer before it is shown to the salesperson.

What we offer (the ONLY facts): {facts or '(nothing has been written down)'}
The prospect wrote: \"\"\"{(their_words or '')[:600]}\"\"\"
The answer: \"\"\"{body[:2500]}\"\"\"

Work in three steps:
1. Name the language and script the prospect wrote in (for example "Roman Urdu, Latin letters" or "English").
2. List every sentence of the answer that says something about our offer the facts do not say. Saying that a thing
   is NOT included or NOT available counts too, as do prices, promises and results.
3. Write the answer again, wholly in the prospect's language and script, with each listed sentence replaced by
   saying you will check and come back to them. Keep the greeting, the points that are in the facts, the request
   and the sign-off.

Return ONLY JSON: {{"language": "...", "unsupported": ["..."], "body": "..."}}"""
        # The model thinks before it answers, and its thinking counts against max_tokens: at 2,000 the check came back
        # empty or cut off two times in four. More room, and a second try.
        for attempt in (1, 2):
            try:
                checked = self._tidy(str(self._ask_json(prompt, temperature=0, max_tokens=6000).get('body', '')))
            except Exception as exc:
                from core.api_key_service import KeyServiceError
                if isinstance(exc, KeyServiceError):
                    raise
                logger.warning('EmailAssistantAgent: the answer check failed (try %d of 2): %s', attempt, exc)
                continue
            # A check rewrites a sentence or two; it never drops most of the answer. On live it once cut one down to
            # "Hi Kiran, Great to hear you're curious!" (30 Oct): such a rewrite is not used.
            if len(checked) >= len(body.strip()) // 2:
                return checked
            logger.warning('EmailAssistantAgent: the answer check dropped most of the answer (try %d of 2)', attempt)
        return body

    @staticmethod
    def _tidy(text: str) -> str:
        """The model sometimes writes its line breaks as the two characters \\n, and says "I will check" once for each
        sentence it replaced."""
        lines = []
        for line in text.replace('\\n', '\n').split('\n'):
            if line.strip() and lines and line.strip() == lines[-1].strip():
                continue
            lines.append(line)
        return '\n'.join(lines).strip()

    def _ask_json(self, prompt, temperature=0.5, max_tokens=2000):
        if not self.groq_client:
            raise ValueError('The AI is not available for your company right now (no AI key or no tokens left).')
        resp = self.groq_client.chat.completions.create(
            model=self.model, messages=[{'role': 'user', 'content': prompt}],
            temperature=temperature, max_tokens=max_tokens)
        from ai_sdr_agent.agents.sdr_key_resolver import record_sdr_usage
        record_sdr_usage(self._key_ctx, getattr(resp.usage, 'total_tokens', 0))
        content = resp.choices[0].message.content.strip()
        if '```' in content:
            content = content.split('```')[1].lstrip('json').strip()
        # strict=False: the model's JSON sometimes has real line breaks inside a string.
        return json.loads(content, strict=False)

    def write_email(self, kind, tone, prospect: dict, sender: dict, offer: str) -> dict:
        """A personal outreach email from a kind, a tone and what the person typed about the prospect."""
        what = self.EMAIL_KINDS.get(kind, self.EMAIL_KINDS['first_email'])
        how = self.TONES.get(tone, self.TONES['professional'])
        known = '\n'.join(f'- {label}: {value}' for label, value in (
            ('Name', prospect.get('name')), ('Job title', prospect.get('title')),
            ('Company', prospect.get('company')), ('Industry', prospect.get('industry')),
            ('Notes from the salesperson', prospect.get('notes'))) if (value or '').strip())
        offer = ' '.join((offer or '').split())[:1500] or '(nothing has been written down)'
        signer = (sender.get('name') or sender.get('company') or 'the sender').split()[0]
        prompt = f"""Write {what}, in a {how} tone.

The prospect (the ONLY facts you know about them):
{known or '- nothing beyond their email address'}

What we offer (the ONLY facts you may use about it): {offer}
Sender: {sender.get('name', '')}, {sender.get('title', '')} at {sender.get('company', '')}

Rules:
- Under 130 words; one clear request at the end, never two
- Never say you have seen, read or noticed anything about them or their company, and never guess their plans
- Never state a fact, number, price, customer name or feature that is not given above
- No placeholders in brackets; if a fact is missing, write around it
- Sign off with "Best," and then {signer} on the next line

Return ONLY JSON: {{"subject": "...", "body": "..."}}"""
        data = self._ask_json(prompt)
        return {'subject': str(data.get('subject', ''))[:300], 'body': str(data.get('body', ''))}

    def read_reply(self, reply_text: str, sender: dict, offer: str) -> dict:
        """What a lead's reply means, what the agent would do, and an answer to send if one is due."""
        reading = self.classify_reply(reply_text)
        result = {'category': reading['category'], 'label': reading['label'], 'reason': reading['reason'],
                  'action': reading['action'], 'answer': None}
        if reading['category'] in (CAT_OUT_OF_OFFICE, CAT_UNSUBSCRIBE):
            return result                          # nothing to answer: the agent waits, or stops for good
        purpose = {
            CAT_POSITIVE: 'thank them and propose a short call; ask which day suits them',
            CAT_WANTS_MORE: 'answer their question from the facts below only, then offer a short call',
            CAT_NOT_INTERESTED: 'thank them politely, say you will not follow up, and leave the door open',
            CAT_NEUTRAL: 'answer briefly and ask one clear question to understand what they need',
        }[reading['category']]
        offer = ' '.join((offer or '').split())[:1500] or '(nothing has been written down)'
        signer = (sender.get('name') or sender.get('company') or 'the sender').split()[0]
        prompt = f"""A prospect replied to our sales email. Write our answer: {purpose}.

Their reply: \"\"\"{strip_quoted_reply(reply_text)[:1200]}\"\"\"
What we offer (the ONLY facts you may use about it): {offer}
Sender: {sender.get('name', '')}, {sender.get('title', '')} at {sender.get('company', '')}

Rules:
- Write in the same language and the same script as their reply: Roman Urdu stays in Latin letters (a Roman Urdu
  reply was answered in Urdu script in the live run of 29 Oct)
- Under 110 words; never state a fact, number or price that is not given above
- {_NOT_IN_THE_FACTS}
- Sign off with "Best," and then {signer} on the next line
- If the reply means nothing (random letters, an empty message), answer nothing: {{"subject": "", "body": ""}}

Return ONLY JSON: {{"subject": "...", "body": "..."}}"""
        data = self._ask_json(prompt, temperature=_ANSWER_TEMPERATURE)
        body = str(data.get('body', '')).strip()
        if body:
            body = self._checked_answer(offer, strip_quoted_reply(reply_text), body)
            result['answer'] = {'subject': str(data.get('subject', ''))[:300], 'body': body}
        return result

    # ── Private ───────────────────────────────────────────────────────────────

    def _ai_classify(self, reply_text: str) -> dict:
        prompt = f"""Classify this reply to a sales email into one category. It may be in any language, including
Roman Urdu; read what the person means.

Reply:
\"\"\"{reply_text[:1200]}\"\"\"

Categories:
- out_of_office    : an automatic away or vacation message
- unsubscribe      : explicitly asks to stop the emails or to be removed ("stop emailing me", "unsubscribe me")
- not_interested   : declines ("not interested", "we already have a tool") without asking to stop all emails
- wants_more_info  : asks questions, wants details or the price
- positive_interest: wants to meet, a call or a demo, or says yes
- neutral          : unclear, off-topic, or "not right now" / "maybe later" / "ask me next quarter"

A yes with a 'not' is not a yes: "absolutely not" is not_interested.

Return ONLY JSON: {{"category": "...", "reason": "one sentence explanation"}}"""

        try:
            resp = self.groq_client.chat.completions.create(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.1,
                max_tokens=800,
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
        # "November 5" and "5 November" both: "until 5 November" fell back to five days (live run of 30 Oct).
        day_first = r'(\d{1,2}(?:st|nd|rd|th)? [A-Za-z]{3,9}(?:,?\s*\d{4})?)'
        patterns = [
            r'back (?:on|from)\s+([\w]+ \d{1,2}(?:,?\s*\d{4})?)',
            r'return(?:ing)? (?:on|from)\s+([\w]+ \d{1,2}(?:,?\s*\d{4})?)',
            r'(?:until|till)\s+([\w]+ \d{1,2}(?:,?\s*\d{4})?)',
            r'available (?:again )?(?:on|from)\s+([\w]+ \d{1,2}(?:,?\s*\d{4})?)',
            r'(?:back (?:on|from)|return(?:ing)? (?:on|from)|until|till|available (?:again )?(?:on|from))\s+' + day_first,
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                try:
                    from dateutil import parser as dp
                    dt = dp.parse(m.group(1), fuzzy=True)
                    aware = timezone.make_aware(dt.replace(hour=9, minute=0, second=0))
                    if aware < timezone.now():
                        # 'Back on January 3', read in December, is next year's (CO-241).
                        try:
                            aware = aware.replace(year=aware.year + 1)
                        except ValueError:
                            aware = aware + timedelta(days=365)
                        if aware < timezone.now():
                            break
                    return aware + timedelta(days=1)  # 1-day buffer after return
                except Exception:
                    pass
        return timezone.now() + timedelta(days=5)

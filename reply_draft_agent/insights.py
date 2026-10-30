"""What the AI can say about the mail itself: a summary of a conversation or of an attached document, and answers to
questions about the inbox.

Three parts of the AI Employee list's Inbox Manager were missing (30 Oct 2026): Document Summarization (no summary
of an email, a thread or an attachment) and Knowledge Q&A (no way to ask about the inbox). Every answer here uses
only the mail it was given, and says which emails it used.
"""
import json
import logging
import os
import re
import tempfile
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import InboxAttachment, InboxEmail
from .text import ai_json, for_ai, parse_json

logger = logging.getLogger(__name__)

# ---- a conversation ----------------------------------------------------------------------------------------------

#: Characters of each message, and of the whole conversation, the AI is given.
PER_MESSAGE = 1500
CONVERSATION = 12000

# People are named, not "he" or "she": on live a summary guessed "him".
THREAD_PROMPT = """Summarise this email conversation for the person in the company who answers it.

Return ONLY this JSON:
{"points": ["...", "..."], "next_step": "...", "open_questions": ["..."]}

- points: 2 to 6 short points, in the order things happened: who asked or said what, and what was agreed.
- next_step: one sentence: who has to do what next ("We owe them a price for two branches"), or "" when nothing.
- open_questions: what the other side asked that has not been answered yet; [] when none.
Use only what the messages say. Write in English, whatever language the messages are in. Name people; never
write "he" or "she": a name does not tell you who someone is."""


def conversation(email):
    """Every message of the email's conversation in its mailbox, oldest first; the email alone without one."""
    if not email.thread_key:
        return [email]
    return list(InboxEmail.objects.filter(email_account_id=email.email_account_id, thread_key=email.thread_key)
                .order_by('received_at'))


def _transcript(messages):
    parts = []
    for m in messages:
        who = f'{m.from_name} <{m.from_email}>' if m.from_name else m.from_email
        side = 'WE WROTE' if m.direction == 'out' else 'THEY WROTE'
        when = m.received_at.strftime('%d %b %Y %H:%M') if m.received_at else ''
        parts.append(f'--- {side}, {when}, from {who}, subject "{m.subject or ""}"\n{for_ai(m.body, PER_MESSAGE)}')
    text = '\n\n'.join(parts)
    # The latest messages matter most: a long conversation loses its beginning.
    return text if len(text) <= CONVERSATION else '[… earlier messages cut]\n' + text[-CONVERSATION:]


def _points(data: dict, keys) -> dict:
    out = {}
    for key in keys:
        value = data.get(key, [] if key != 'next_step' else '')
        if isinstance(value, list):
            out[key] = [' '.join(str(v).split()) for v in value if str(v).strip()][:8]
        else:
            out[key] = ' '.join(str(value or '').split())
    return out


def summarize_conversation(email, agent) -> dict:
    """The summary of the email's conversation, made once and made again only when it has new messages."""
    messages = conversation(email)
    if email.thread_summary and email.thread_summary_count == len(messages):
        try:
            return json.loads(email.thread_summary)
        except ValueError:
            pass
    summary = _points(ai_json(agent, prompt=_transcript(messages), system_prompt=THREAD_PROMPT, max_tokens=700),
                      ('points', 'next_step', 'open_questions'))
    if not summary['points']:
        raise ValueError('the AI gave no summary')
    summary['messages'] = len(messages)
    InboxEmail.objects.filter(pk=email.pk).update(thread_summary=json.dumps(summary),
                                                  thread_summary_count=len(messages))
    return summary


# ---- an attachment -----------------------------------------------------------------------------------------------

#: What can be read as text, by the same reader the Frontline knowledge base uses.
READABLE = {'pdf', 'docx', 'txt', 'md', 'html', 'htm'}
DOCUMENT = 12000

DOCUMENT_PROMPT = """Summarise this document, which came attached to an email, for the person who answers the email.

Return ONLY this JSON:
{"what": "...", "points": ["..."], "figures": ["..."]}

- what: what the document is, in a few words ("An invoice from Shifa Clinic", "A signed lease").
- points: 2 to 6 short points on what it says.
- figures: amounts, dates, deadlines and names that matter, each as written in the document; [] when none.
Use only what the document says. Write in English, whatever language it is in."""


def _extension(filename, content_type=''):
    ext = os.path.splitext(filename or '')[1].lower().lstrip('.')
    if ext:
        return ext
    return {'application/pdf': 'pdf', 'text/plain': 'txt', 'text/html': 'html',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx'}.get(
        (content_type or '').split(';')[0].strip().lower(), '')


def can_summarize(filename, content_type='') -> bool:
    return _extension(filename, content_type) in READABLE


def attachment_text(att) -> str:
    """The attachment's text, read from a copy on disk (storage may not be a local file)."""
    from Frontline_agent.document_processor import DocumentProcessor
    ext = _extension(att.filename, att.content_type)
    if ext not in READABLE:
        raise ValueError('Only PDF, Word and text files can be summarised.')
    with att.file.open('rb') as fh:
        data = fh.read()
    fmt = 'html' if ext == 'htm' else ext
    fd, path = tempfile.mkstemp(suffix='.' + fmt)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
        ok, text, error = DocumentProcessor.extract_text(path, fmt)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    if not ok or not (text or '').strip():
        raise ValueError(error or 'No text could be read from this file (a scanned picture, perhaps).')
    return text


def summarize_attachment(att, agent) -> dict:
    """The attachment's summary, made once."""
    if att.summary:
        try:
            return json.loads(att.summary)
        except ValueError:
            pass
    text = ' '.join(attachment_text(att).split())
    if len(text) > DOCUMENT:
        text = text[:DOCUMENT] + ' [… the rest of the document was cut]'
    summary = _points(ai_json(agent, prompt=f'File name: {att.filename}\n\n{text}', system_prompt=DOCUMENT_PROMPT,
                              max_tokens=700), ('what', 'points', 'figures'))
    if not summary['points']:
        raise ValueError('the AI gave no summary')
    att.summary = json.dumps(summary)
    att.summarized_at = timezone.now()
    att.save(update_fields=['summary', 'summarized_at'])
    return summary


# ---- questions about the inbox -------------------------------------------------------------------------------------

#: Emails the answer may draw on in full, and the other recent ones it sees one line each of.
SOURCES = 12
INDEX = 60

PLAN_PROMPT = """A person asks a question about their company's email. Decide how to look for the emails that answer it.

Return ONLY this JSON:
{"language": "...", "terms": ["..."], "people": ["..."], "days": null, "categories": [], "priorities": [],
 "waiting": false}

- language: the language the question is written in: "English", "Roman Urdu" (Urdu in Latin letters), "Urdu"
  (Urdu script), or another language's name.
- terms: up to 6 words or short phrases, in English and in the singular, likely to appear in those emails' subject
  or text (translate Urdu or Roman Urdu words: "qeemat" -> "price"; "invoices" -> "invoice"). Leave out words like
  email, inbox, message.
- people: names, companies or email addresses the question mentions; [] when none.
- days: how far back to look, as a number of days, when the question says ("this week" = 7, "today" = 1); null when
  it does not.
- categories: any of customer, sales, support, billing, meeting, internal, newsletter, personal, other that the
  question is about ("complaints" -> support, "invoices" -> billing); [] when none.
- priorities: ["urgent", "high"] when the question asks what is urgent, important, needs attention or must be done
  first ("urgent", "zaroori", "jaldi"); [] otherwise.
- waiting: true when the question asks which mail still needs an answer or a reply ("jawab dena baqi hai");
  false otherwise."""

# "Every email that fits": on live, "which clinics replied?" left out the one that asked the price.
ANSWER_PROMPT = """You answer questions about a company's email, from the emails below only. Return ONLY this JSON,
with the email numbers as plain numbers: {"answer": "...", "sources": [12, 40]}

The first emails are given in full. The rest of the recent mail follows, one line each. Each email's head shows its
kind and priority as read when it arrived (for example support/urgent).

- Write in the same language and script as the question: Roman Urdu stays in Latin letters, Urdu stays in Urdu
  script, English stays English.
- After each fact, name the email it came from as [#id].
- Use only what these emails say. When they do not answer the question, say so plainly.
- When the question asks who or which, name every email that fits, not only some.
- You only answer questions. You cannot reply, send, delete, book or change anything. When asked to, say in one
  sentence that you cannot do that here, and name the email to open as [#id] so the person can reply from it.
- When the question is not about this mail at all (a poem, the weather, general knowledge), say in one sentence that
  you answer questions about this inbox only.
- Be brief: a few sentences, or a short list.
- Name people; never write he, she, him, her or his: a name does not tell you who someone is."""

_SCRIPT_URDU = re.compile(r'[؀-ۿ]')
_LANGUAGES = {'roman urdu': 'Roman Urdu (Urdu in Latin letters)', 'urdu': 'Urdu, in Urdu script'}


def answer_last(language):
    """Said after the question. With the rules alone, gpt-4o-mini answered English questions in Roman Urdu (the
    inbox had a Roman Urdu email) and dropped the JSON; naming the question's language, as the plan read it, fixed
    it."""
    name = _LANGUAGES.get((language or '').strip().lower(), (language or '').strip()[:30])
    lang = f'in {name}' if name else 'in the language and script of the QUESTION'
    # Names, not "he" or "she", said here too: on live the rules alone still gave "he is not interested", and with
    # "he" and "she" named, "works for him".
    return (f'\n\nWrite the answer {lang}, repeating people\'s names instead of he, she, him, her or his, as the '
            f'JSON {{"answer": "...", "sources": [...]}}.')


def _plan(question, history, agent) -> dict:
    asked = '\n'.join(f'Earlier question: {q}' for q, _ in history[-3:])
    data = ai_json(agent, prompt=(asked + '\n' if asked else '') + f'Question: {question}',
                   system_prompt=PLAN_PROMPT, max_tokens=300)
    days = data.get('days')
    language = str(data.get('language') or '').strip()
    if _SCRIPT_URDU.search(question):
        language = 'Urdu'
    return {
        'language': language,
        'terms': [t.strip() for t in data.get('terms', []) if isinstance(t, str) and len(t.strip()) >= 3][:6],
        'people': [p.strip() for p in data.get('people', []) if isinstance(p, str) and len(p.strip()) >= 2][:4],
        'days': int(days) if isinstance(days, (int, float)) and 0 < days <= 365 else None,
        'categories': [c for c in data.get('categories', []) if isinstance(c, str)][:4],
        'priorities': [p for p in data.get('priorities', []) if p in ('urgent', 'high')],
        'waiting': data.get('waiting') is True,
    }


def _stem(term):
    """The word without its plural ending, so "alerts" finds "Security alert" (on live it found nothing)."""
    t = term.strip()
    if len(t) > 4 and t.lower().endswith('ies'):
        return t[:-3] + 'y'
    if len(t) > 4 and t.lower().endswith('s') and not t.lower().endswith('ss'):
        return t[:-1]
    return t


def _window(account, plan):
    qs = InboxEmail.objects.filter(email_account=account)
    if plan.get('days'):
        qs = qs.filter(received_at__gte=timezone.now() - timedelta(days=plan['days']))
    return qs


def find_emails(account, plan, limit=SOURCES):
    """The mailbox's emails that best match the plan, mail received before mail sent and newest first among equals;
    the newest when nothing matches."""
    qs = _window(account, plan)
    terms = [_stem(t) for t in plan.get('terms', [])]
    match = Q()
    for term in terms:
        match |= Q(subject__icontains=term) | Q(ai_summary__icontains=term) | Q(body__icontains=term)
    for person in plan.get('people', []):
        match |= Q(from_name__icontains=person) | Q(from_email__icontains=person) | Q(to_email__icontains=person)
    if plan.get('categories'):
        match |= Q(category__in=plan['categories'])
    if plan.get('priorities'):
        match |= Q(priority__in=plan['priorities'])
    # "Kin emails ka jawab abhi dena baqi hai?" left out a meeting move that waited for an answer: such a question
    # gets the mail that waits, and nobody has answered, in full.
    answered = []
    if plan.get('waiting'):
        from .models import ReplyDraft
        answered = list(ReplyDraft.objects.filter(inbox_email__email_account=account, status='sent')
                        .values_list('inbox_email_id', flat=True))
        match |= Q(direction='in', needs_reply=True) & ~Q(id__in=answered)
    found = list(qs.filter(match).order_by('-received_at')[:80]) if match else []
    if not found:
        return list(qs.order_by('-received_at')[:limit])
    words = [w.lower() for w in terms + plan.get('people', [])]

    def hits(m):
        text = f'{m.subject} {m.ai_summary} {m.from_name} {m.from_email} {(m.body or "")[:4000]}'.lower()
        waits = plan.get('waiting') and m.direction == 'in' and m.needs_reply and m.id not in answered
        return (sum(1 for w in words if w in text) + (1 if m.category in plan.get('categories', []) else 0)
                + (2 if m.priority in plan.get('priorities', []) else 0) + (3 if waits else 0))
    # A campaign's own sent emails used to outrank the replies to them, and a clinic's price question was left out.
    found.sort(key=lambda m: (hits(m), m.direction == 'in', m.received_at), reverse=True)
    return found[:limit]


def _head(m, answered=frozenset()):
    who = f'{m.from_name} <{m.from_email}>' if m.from_name else m.from_email
    side = 'sent by us to ' + (m.to_email or '') if m.direction == 'out' else 'from ' + who
    when = m.received_at.strftime('%a %d %b %Y %H:%M') if m.received_at else ''
    head = f'[#{m.id}] {when}, {side}, subject "{m.subject or ""}"'
    if m.category:
        head += f', {m.category}/{m.priority}'
    # "Which emails still need an answer?" listed an invoice that needs none: the answer now sees what the AI read.
    if m.direction == 'in' and m.id in answered:
        head += ', answered by us'
    elif m.direction == 'in' and m.needs_reply:
        head += ', waits for an answer'
    elif m.direction == 'in' and m.triaged_at:
        head += ', needs no answer'
    return head


def _answered(ids):
    from .models import ReplyDraft
    return frozenset(ReplyDraft.objects.filter(inbox_email_id__in=ids, status='sent')
                     .values_list('inbox_email_id', flat=True))


def _email_block(m, files=(), answered=frozenset()):
    text = f'{_head(m, answered)}\n{for_ai(m.body, 700)}'
    for name, summary in files:
        text += f'\nAttached file "{name}", as summarised: {summary}'
    return text


def _file_summaries(emails):
    """The summaries made of the emails' attached files, by email: an invoice's amount is in its PDF, not in the
    email ("Please find attached our invoice")."""
    out = {}
    rows = (InboxAttachment.objects.filter(inbox_email_id__in=[m.id for m in emails]).exclude(summary='')
            .values_list('inbox_email_id', 'filename', 'summary'))
    for email_id, name, raw in rows:
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        parts = [data.get('what') or ''] + list(data.get('points') or []) + list(data.get('figures') or [])
        out.setdefault(email_id, []).append((name, '; '.join(p for p in parts if p)[:600]))
    return out


def _index(account, plan, skip):
    """The other recent emails, one line each: a question about "everything urgent" or "who replied" is not left
    to the search alone."""
    return list(_window(account, plan).exclude(id__in=skip).order_by('-received_at')
                .only('id', 'direction', 'from_name', 'from_email', 'to_email', 'subject', 'received_at', 'category',
                      'priority', 'ai_summary', 'needs_reply', 'triaged_at')[:INDEX])


def _read_answer(raw):
    """The answer's JSON. The AI sometimes writes its sources as [#60] (on live, a question in Urdu failed so), and
    sometimes answers in plain words: those are the answer, with the emails it names in it."""
    try:
        return parse_json(raw)
    except ValueError:
        pass
    fixed = re.sub(r'("sources"\s*:\s*\[)([^\]]*)\]',
                   lambda mt: mt.group(1) + ','.join(re.findall(r'\d+', mt.group(2))) + ']', raw or '')
    try:
        return parse_json(fixed)
    except ValueError:
        if '{' in (raw or ''):
            raise
        return {'answer': (raw or '').strip(), 'sources': []}


def ask_inbox(question, account, agent, history=()) -> dict:
    """An answer to a question about the mailbox, with the emails it came from."""
    question = ' '.join((question or '').split())[:500]
    history = [(str(q)[:300], str(a)[:600]) for q, a in list(history)[-3:]]
    try:
        plan = _plan(question, history, agent)
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning('ask_inbox: the search plan could not be read (%s); the newest mail is used', exc)
        plan = {'language': 'Urdu' if _SCRIPT_URDU.search(question) else '', 'terms': [], 'people': [], 'days': None,
                'categories': [], 'priorities': [], 'waiting': False}
    emails = find_emails(account, plan)
    if not emails:
        return {'answer': 'There is no mail in this inbox yet.', 'sources': [], 'searched': 0}
    others = _index(account, plan, [m.id for m in emails])
    answered = _answered([m.id for m in emails + others])
    index = '\n'.join(_head(m, answered) + (f': {m.ai_summary}' if m.ai_summary else '') for m in others)
    files = _file_summaries(emails)
    # Asked what still needs an answer, the AI named two of three on live, a different two each time: the list is
    # worked out here and given to it.
    waiting = ''
    if plan.get('waiting'):
        ids = [m.id for m in emails + others if m.direction == 'in' and m.needs_reply and m.id not in answered]
        waiting = ('\n\nEMAILS THAT WAIT FOR AN ANSWER, none answered yet (name every one): '
                   + (', '.join(f'[#{i}]' for i in ids) if ids else 'none'))
    earlier = '\n'.join(f'Q: {q}\nA: {a}' for q, a in history)
    today = timezone.localtime().strftime('%A %d %B %Y')
    prompt = (f'Today is {today}.\n\n' + (f'Earlier in this conversation:\n{earlier}\n\n' if earlier else '')
              + 'EMAILS IN FULL:\n\n' + '\n\n'.join(_email_block(m, files.get(m.id, ()), answered) for m in emails)
              + (f'\n\nOTHER RECENT EMAILS, ONE LINE EACH:\n{index}' if index else '') + waiting
              + f'\n\nQUESTION: {question}' + answer_last(plan.get('language')))
    raw = agent._call_llm(prompt=prompt, system_prompt=ANSWER_PROMPT, temperature=0.2, max_tokens=800)
    data = _read_answer(raw)
    answer = str(data.get('answer', '')).strip()
    if not answer:
        raise ValueError('the AI gave no answer')
    by_id = {m.id: m for m in emails + others}
    cited = [int(i) for i in re.findall(r'\[#(\d+)\]', answer)]
    listed = [int(i) for i in data.get('sources', []) if isinstance(i, int) or (isinstance(i, str) and i.isdigit())]
    ids = [i for i in dict.fromkeys(cited + listed) if i in by_id]
    return {
        'answer': answer,
        'sources': [{
            'id': m.id, 'direction': m.direction, 'from_email': m.from_email, 'from_name': m.from_name,
            'to_email': m.to_email, 'subject': m.subject or '(no subject)',
            'received_at': m.received_at.isoformat() if m.received_at else None,
        } for m in (by_id[i] for i in ids)],
        'searched': len(emails) + len(others),
    }

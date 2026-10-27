"""What Frontline does by itself with a ticket a customer opens: by chat hand-off, web form or email.

Customer tickets arrived as "medium / other" and stayed that way until someone pressed Re-triage, and nothing ever
answered a simple one, so the dashboard's "Auto-resolved" figure only counted staff tickets. Two switches per company,
both off until an admin turns them on (Chat widget tab, "Ticket automation"):

- classify_incoming: the triage staff tickets and Re-triage use sets the category, priority, intent and entities.
- resolve_from_knowledge: a web-form or email ticket the knowledge base answers gets the answer by email and is marked
  auto-resolved, when one small AI check finds the message a simple question and the drafted reply a full answer. The
  customer's reply comes back onto the ticket and reopens it (inbound email does that for every resolved ticket). A
  chat hand-off is never answered this way: that customer asked for a person.

After classifying, the company's own "when a ticket is created" workflows run for the ticket (run_new_ticket_workflows),
so their category and priority conditions see the classified ticket.

It runs on a Celery worker once the ticket is committed, never inside the customer's request.
"""
import logging

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

SETTINGS_KEY = 'ticket_automation'
DEFAULTS = {'classify_incoming': False, 'resolve_from_knowledge': False}
VALID_CATEGORIES = {'technical', 'billing', 'account', 'feature_request', 'bug', 'other'}
VALID_PRIORITIES = {'low', 'medium', 'high', 'urgent'}
# Channels whose customer gave an address to answer and did not ask for a person.
RESOLVABLE_CHANNELS = ('form', 'email')
# An answer the model wrote although the knowledge base matched, saying it does not know after all.
_NOT_KNOWING = ("don't have", 'do not have', "couldn't find", 'could not find', 'no information',
                'not able to find', 'unable to find', "i'm not sure", 'i am not sure')
_SIGN_OFF = ("\n\nIf this doesn't answer your question, just reply to this email and a member of our team will "
             "pick it up.")
# Whether a drafted answer may go out without a person. It used to need search confidence 'high', which never came:
# search_knowledge drops each passage's similarity, and for a short guide stored as one passage the similarity can't
# tell a good match from a bad one (27 Oct, text-embedding-3-large: "For how long do you keep backups?" 0.24, "Who is
# your CEO?" 0.24). So the live contact form's "Do you take backups…?" was never answered.
_CHECK = """A customer wrote to a company's support. The company's assistant drafted a reply from the company's own
help documents. Decide whether the reply can be emailed without a person checking it first.

Customer's message:
{question}

Drafted reply:
{answer}

Return ONLY a JSON object:
{{"simple_question": true when the message only asks for general information (hours, prices, what a plan includes,
                     how something works, when invoices are due, how to pay); false when it reports a problem, asks for
                     something to be done, complains, or needs the customer's own records looked up (a particular
                     order, payment, charge or invoice of theirs),
 "fully_answered": true when the reply answers everything the message asks, leaving nothing as unknown,
 "confidence": a number from 0 to 1}}"""
_CHECK_MIN_CONFIDENCE = 0.8


def _safe_to_send(ticket, question, answer):
    """One small AI call: is the message a simple question, and does the drafted reply answer all of it?"""
    import json
    from core.Frontline_agent.frontline_agent import FrontlineAgent
    try:
        raw = FrontlineAgent(company_id=ticket.company_id)._call_llm(
            prompt=_CHECK.format(question=question[:3000], answer=answer[:3000]),
            system_prompt='You check support replies. Output only one JSON object.',
            temperature=0, max_tokens=200, json_mode=True)
        check = json.loads((raw or '').strip().strip('`').removeprefix('json').strip())
        return (check.get('simple_question') is True and check.get('fully_answered') is True
                and float(check.get('confidence', 0)) >= _CHECK_MIN_CONFIDENCE)
    except Exception as exc:
        logger.info("Ticket %s not auto-resolved: no check (%s: %s)", ticket.id, type(exc).__name__, exc)
        return False


def switches(company):
    """The company's two switches, off unless turned on."""
    from Frontline_agent.widget_utils import resolved_widget_config
    saved = resolved_widget_config(company).get(SETTINGS_KEY) or {}
    return {key: saved.get(key) is True for key in DEFAULTS}


def suggest_triage(company_id, title, description):
    """Category, priority, intent and entities for a ticket: the AI's reading, else the rules'. Shared with Re-triage."""
    from core.Frontline_agent.frontline_agent import FrontlineAgent
    agent = FrontlineAgent(company_id=company_id)
    read = agent._extract_ticket_intent(title, description) or {}
    rules = agent.ticket_service.classify_ticket(title, description)
    category = (read.get('suggested_category') or rules.get('category') or '').lower()
    priority = (read.get('suggested_priority') or rules.get('priority') or '').lower()
    entities = read.get('entities')
    return {
        'category': category if category in VALID_CATEGORIES else None,
        'priority': priority if priority in VALID_PRIORITIES else None,
        'intent': read.get('intent') or None,
        'entities': {k: v for k, v in entities.items() if v} if isinstance(entities, dict) else {},
    }


def has_new_ticket_workflows(company):
    """Whether the company has an active workflow that runs when a ticket is created."""
    from Frontline_agent.models import FrontlineWorkflow
    return any((w.trigger_conditions or {}).get('on') == 'ticket_created'
               for w in FrontlineWorkflow.objects.filter(company=company, is_active=True).only('trigger_conditions'))


def queue(ticket, channel):
    """Hand a new customer ticket to the worker, when the company has a switch on that applies to it, or a workflow
    that runs when a ticket is created."""
    on = switches(ticket.company)
    if not (on['classify_incoming'] or (on['resolve_from_knowledge'] and channel in RESOLVABLE_CHANNELS)
            or has_new_ticket_workflows(ticket.company)):
        return False

    def send():
        try:
            from Frontline_agent.tasks import handle_customer_ticket
            handle_customer_ticket.delay(ticket.id, channel)
        except Exception:
            logger.exception("Could not queue ticket automation for ticket %s", ticket.id)

    transaction.on_commit(send)
    return True


def handle(ticket_id, channel):
    """Classify and, where allowed, answer one new customer ticket. Returns what was done."""
    from core.modules import has_module
    from Frontline_agent.models import Ticket

    ticket = Ticket.objects.select_related('company', 'contact').filter(pk=ticket_id).first()
    if not ticket or not ticket.company or not has_module(ticket.company, 'frontline_agent'):
        return {'classified': False, 'resolved': False}
    from core.api_key_service import KeyServiceError
    on = switches(ticket.company)
    done = {'classified': False, 'resolved': False}
    if on['classify_incoming']:
        try:
            done['classified'] = classify(ticket)
        except KeyServiceError as exc:
            # No AI: the ticket keeps the category and priority it came in with, and its workflows still run.
            logger.info("Ticket %s not classified: %s", ticket.id, exc)
    run_new_ticket_workflows(ticket)
    if on['resolve_from_knowledge'] and channel in RESOLVABLE_CHANNELS:
        done['resolved'] = resolve_from_knowledge(ticket)
    return done


def run_new_ticket_workflows(ticket):
    """The company's "when a ticket is created" workflows for a customer ticket, once it is classified.

    They used to run only for contact-form and staff tickets, and the form's ran while the request was still open,
    before classification: a chat hand-off or an emailed ticket ran no workflow at all, and a workflow for "billing"
    or "urgent" tickets never matched a customer's, which were all still "other" and "medium" then.
    """
    from api.views.frontline_agent import _run_workflow_triggers
    ticket.refresh_from_db()
    _run_workflow_triggers(ticket.company_id, 'ticket_created', ticket, ticket.created_by)


def classify(ticket):
    """Apply the triage suggestion to the ticket, moving its SLA deadline with its priority."""
    from api.views.frontline_agent import _sla_due_at_for_priority

    suggestion = suggest_triage(ticket.company_id, ticket.title, ticket.description)
    fields = ['last_triaged_at', 'updated_at']
    if suggestion['category'] and suggestion['category'] != ticket.category:
        ticket.category = suggestion['category']
        fields.append('category')
    if ticket.handoff_status in ('pending', 'accepted') and suggestion['priority'] == 'low':
        suggestion['priority'] = None        # a hand-off is kept at medium or above so it surfaces
    if suggestion['priority'] and suggestion['priority'] != ticket.priority:
        ticket.priority = suggestion['priority']
        fields.append('priority')
        if ticket.sla_due_at:
            ticket.sla_due_at = _sla_due_at_for_priority(ticket.priority, company=ticket.company)
            fields.append('sla_due_at')
    if suggestion['intent']:
        ticket.intent = suggestion['intent'][:100]
        fields.append('intent')
    if suggestion['entities']:
        ticket.entities = {**(ticket.entities or {}), **suggestion['entities']}
        fields.append('entities')
    ticket.last_triaged_at = timezone.now()
    ticket.save(update_fields=fields)
    return True


def _customer_question(ticket):
    """What the customer asked. A web-form ticket's description starts with the From and Email lines."""
    text = ticket.description or ''
    if text.startswith('From: ') and '\n\n' in text:
        return text.split('\n\n', 1)[1].strip()
    if ticket.title and not ticket.title.startswith('Web form: '):
        return f'{ticket.title}\n\n{text}'.strip()
    return text.strip()


def resolve_from_knowledge(ticket):
    """Email the knowledge base's answer and mark the ticket auto-resolved, when the check finds it safe to send."""
    from api.views.frontline_agent import send_ticket_reply
    from core.Frontline_agent.frontline_agent import FrontlineAgent, says_not_found
    from Frontline_agent.ticket_state import apply_status_change

    if ticket.status not in ('new', 'open') or ticket.priority == 'urgent':
        return False
    question = _customer_question(ticket)
    if not question:
        return False
    result = FrontlineAgent(company_id=ticket.company_id).answer_question(question, company_id=ticket.company_id,
                                                                          for_customer=True)
    answer = (result.get('answer') or '').strip()
    if not (result.get('has_verified_info') and answer) or says_not_found(answer):
        return False
    if any(phrase in answer.lower() for phrase in _NOT_KNOWING):
        return False
    if not _safe_to_send(ticket, question, answer):
        return False

    msg, problem, _ = send_ticket_reply(ticket, answer + _SIGN_OFF)
    if problem:
        logger.info("Ticket %s not auto-resolved: %s", ticket.id, problem)
        return False
    fields = apply_status_change(ticket, 'auto_resolved')
    ticket.auto_resolved = True
    ticket.resolution = answer
    ticket.resolution_confidence = result.get('best_score')
    ticket.save(update_fields=list(set(fields + ['auto_resolved', 'resolution', 'resolution_confidence',
                                                 'updated_at'])))
    return True

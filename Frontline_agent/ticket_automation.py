"""What Frontline does by itself with a ticket a customer opens: by chat hand-off, web form or email.

Customer tickets arrived as "medium / other" and stayed that way until someone pressed Re-triage, and nothing ever
answered a simple one, so the dashboard's "Auto-resolved" figure only counted staff tickets. Two switches per company,
both off until an admin turns them on (Chat widget tab, "Ticket automation"):

- classify_incoming: the triage staff tickets and Re-triage use sets the category, priority, intent and entities.
- resolve_from_knowledge: a web-form or email ticket the knowledge base answers with high confidence gets the answer
  by email and is marked auto-resolved. The customer's reply comes back onto the ticket and reopens it (inbound email
  does that for every resolved ticket). A chat hand-off is never answered this way: that customer asked for a person.

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


def queue(ticket, channel):
    """Hand a new customer ticket to the worker, when the company has a switch on that applies to it."""
    on = switches(ticket.company)
    if not (on['classify_incoming'] or (on['resolve_from_knowledge'] and channel in RESOLVABLE_CHANNELS)):
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
    on = switches(ticket.company)
    done = {'classified': False, 'resolved': False}
    if on['classify_incoming']:
        done['classified'] = classify(ticket)
    if on['resolve_from_knowledge'] and channel in RESOLVABLE_CHANNELS:
        done['resolved'] = resolve_from_knowledge(ticket)
    return done


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
    """Email the knowledge base's answer and mark the ticket auto-resolved, when the answer is a confident one."""
    from api.views.frontline_agent import send_ticket_reply
    from core.Frontline_agent.frontline_agent import FrontlineAgent
    from Frontline_agent.ticket_state import apply_status_change

    if ticket.status not in ('new', 'open') or ticket.priority == 'urgent':
        return False
    question = _customer_question(ticket)
    if not question:
        return False
    result = FrontlineAgent(company_id=ticket.company_id).answer_question(question, company_id=ticket.company_id)
    answer = (result.get('answer') or '').strip()
    if not (result.get('has_verified_info') and result.get('confidence') == 'high' and answer):
        return False
    if any(phrase in answer.lower() for phrase in _NOT_KNOWING):
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

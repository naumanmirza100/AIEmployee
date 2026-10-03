"""Frontline's AI suggests; a person decides.

A ticket staff filed from the dashboard or the floating chat's /ticket could be
closed on the spot by the AI ("auto-resolved") with a knowledge-base answer
nobody had read, and Re-triage changed a ticket's category and priority
straight away. Both now propose first.
"""
from unittest import mock

from api.views import frontline_agent as views
from core.Frontline_agent.frontline_agent import FrontlineAgent
from core.Frontline_agent.services import TicketAutomationService
from Frontline_agent.models import Ticket

from .base import FrontlineTestCase

ANSWER = 'Reset it from Settings, then Security.'


def knowledge_base_has_an_answer():
    return mock.patch.multiple(
        TicketAutomationService,
        find_solution=mock.Mock(return_value={'solution': ANSWER}),
        auto_resolve_ticket=mock.Mock(return_value=(True, ANSWER, {'solution': ANSWER})),
    )


def no_model():
    return mock.patch.object(FrontlineAgent, '_extract_ticket_intent', return_value=None)


class StaffTicketTests(FrontlineTestCase):

    def create(self):
        with knowledge_base_has_an_answer(), no_model():
            return self.call(views.create_ticket, self.member,
                             {'title': 'Password reset fails', 'description': 'A 500 on submit.'})

    def test_a_ticket_staff_file_stays_open_with_the_answer_suggested(self):
        code, body = self.create()
        self.assertEqual(code, 201, body)
        data = body['data']
        self.assertEqual((data['auto_resolved'], data['suggested_resolution']), (False, ANSWER))
        ticket = Ticket.objects.get(pk=data['ticket_id'])
        self.assertEqual((ticket.status, ticket.auto_resolved, ticket.resolution), ('open', False, None))
        self.assertIsNotNone(ticket.sla_due_at)
        # Kept on the ticket for whoever opens it.
        [note] = ticket.notes.all()
        self.assertTrue(note.is_internal)
        self.assertIn(ANSWER, note.body)

    def test_accepting_the_suggestion_resolves_it_with_that_answer(self):
        ticket_id = self.create()[1]['data']['ticket_id']
        code, body = self.call(views.update_ticket, self.member, {'status': 'resolved', 'resolution': ANSWER},
                               method='patch', ticket_id=ticket_id)
        self.assertEqual(code, 200, body)
        ticket = Ticket.objects.get(pk=ticket_id)
        self.assertEqual((ticket.status, ticket.resolution), ('resolved', ANSWER))
        self.assertIsNotNone(ticket.resolved_at)

    def test_the_customer_facing_path_still_answers_at_once(self):
        user = self.login_user_for(self.member)
        with knowledge_base_has_an_answer():
            result = TicketAutomationService().process_ticket('Password reset fails', 'A 500.', user.id,
                                                              company_id=self.company.id)
        ticket = Ticket.objects.get(pk=result['ticket_id'])
        self.assertEqual((ticket.status, ticket.auto_resolved, ticket.resolution), ('auto_resolved', True, ANSWER))
        self.assertNotIn('suggested_resolution', result)


class RetriageTests(FrontlineTestCase):

    def retriage(self, data=None):
        suggestion = {'suggested_category': 'billing', 'suggested_priority': 'high', 'intent': 'refund_request'}
        with mock.patch.object(FrontlineAgent, '_extract_ticket_intent', return_value=suggestion):
            return self.call(views.retriage_ticket, self.member, data or {}, ticket_id=self.ticket.id)

    def test_retriage_proposes_and_changes_nothing(self):
        self.ticket.category, self.ticket.priority = 'technical', 'low'
        self.ticket.save()
        code, body = self.retriage()
        self.assertEqual(code, 200, body)
        data = body['data']
        self.assertEqual((data['applied'], data['old_category'], data['new_category'],
                          data['old_priority'], data['new_priority']),
                         (False, 'technical', 'billing', 'low', 'high'))
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.category, self.ticket.priority, self.ticket.last_triaged_at),
                         ('technical', 'low', None))

    def test_applying_saves_what_was_proposed_without_asking_again(self):
        with mock.patch.object(FrontlineAgent, '_extract_ticket_intent', side_effect=AssertionError('no model')):
            code, body = self.call(views.retriage_ticket, self.member,
                                   {'apply': True, 'category': 'billing', 'priority': 'high', 'intent': 'refund'},
                                   ticket_id=self.ticket.id)
        self.assertEqual((code, body['data']['applied']), (200, True), body)
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.category, self.ticket.priority, self.ticket.intent), ('billing', 'high', 'refund'))
        self.assertIsNotNone(self.ticket.last_triaged_at)

    def test_applying_a_value_that_isnt_allowed_changes_nothing(self):
        before = (self.ticket.category, self.ticket.priority)
        self.call(views.retriage_ticket, self.member, {'apply': True, 'category': 'nonsense', 'priority': 'max'},
                  ticket_id=self.ticket.id)
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.category, self.ticket.priority), before)

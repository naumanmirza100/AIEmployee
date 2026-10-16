"""A website visitor who asks for a person can be answered.

The chat asked nobody for an address, so a hand-off from it had no one to reply to,
and "Send reply" on it, or on a web-form ticket, always failed with "No recipient":
the reply only looked for an earlier email in the ticket's thread, and these have none.
"""
import json
from datetime import timedelta
from unittest import mock

from django.core import mail, signing
from django.core.cache import cache
from django.test import Client

from api.views import frontline_agent as views
from Frontline_agent.models import Ticket

from .base import FrontlineTestCase

KEY = 'wk_made_up_for_a_test'
ANSWER = {'answer': 'Our team will help with pricing.', 'has_verified_info': True, 'confidence': 0.9,
          'sources': [], 'citations': [], 'best_score': 0.9}


class WidgetHandoffEmailTests(FrontlineTestCase):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.company.frontline_widget_key = KEY
        self.company.save(update_fields=['frontline_widget_key'])
        self.rival.frontline_widget_key = 'wk_rival'
        self.rival.save(update_fields=['frontline_widget_key'])
        answering = mock.patch.object(views.FrontlineAgent, 'answer_question', return_value=ANSWER)
        answering.start()
        self.addCleanup(answering.stop)

    def post(self, path, body, key=KEY):
        response = Client().post(path, json.dumps({'widget_key': key, **body}), content_type='application/json')
        return response.status_code, json.loads(response.content)

    def ask_for_a_person(self, **extra):
        code, body = self.post('/api/frontline/public/qa', {'question': 'Can I talk to a person about the price?',
                                                             **extra})
        self.assertEqual(code, 200, body)
        self.assertTrue(body['data'].get('handoff_requested'), body)
        return body['data'], Ticket.objects.get(pk=body['data']['handoff_ticket_id'])

    def leave(self, token, email='kiran@clinic.example', key=KEY):
        return self.post('/api/frontline/public/handoff-contact', {'handoff_token': token, 'email': email,
                                                                    'name': 'Kiran'}, key=key)

    def test_a_visitor_with_no_address_is_asked_for_one_and_it_reaches_the_ticket(self):
        data, ticket = self.ask_for_a_person()
        self.assertIsNone(ticket.contact)
        code, body = self.leave(data['handoff_token'])
        self.assertEqual(code, 200, body)
        ticket.refresh_from_db()
        self.assertEqual(ticket.contact.email, 'kiran@clinic.example')
        self.assertEqual(ticket.handoff_context.get('from_email'), 'kiran@clinic.example')

    def test_a_visitor_who_gave_an_address_is_not_asked_again(self):
        data, ticket = self.ask_for_a_person(visitor_email='kiran@clinic.example')
        self.assertNotIn('handoff_token', data)
        self.assertEqual(ticket.contact.email, 'kiran@clinic.example')

    def test_the_token_adds_one_address_to_its_own_ticket_only(self):
        data, ticket = self.ask_for_a_person()
        self.assertEqual(self.leave(data['handoff_token'])[0], 200)
        code, _ = self.leave(data['handoff_token'], email='someone.else@example.com')     # not a second time
        self.assertEqual(code, 400)
        ticket.refresh_from_db()
        self.assertEqual(ticket.contact.email, 'kiran@clinic.example')
        forged = signing.dumps({'ticket': self.ticket.id, 'company': self.company.id}, salt='another-purpose')
        self.assertEqual(self.leave(forged)[0], 400)
        data2, _ = self.ask_for_a_person()
        self.assertEqual(self.leave(data2['handoff_token'], key='wk_rival')[0], 400)      # another company's key
        self.assertEqual(self.leave(data2['handoff_token'], email='not an address')[0], 400)

    def test_an_old_token_has_expired(self):
        data, _ = self.ask_for_a_person()
        later = signing.time.time() + views.HANDOFF_CONTACT_MAX_AGE + 60
        with mock.patch('django.core.signing.time.time', return_value=later):
            self.assertEqual(self.leave(data['handoff_token'])[0], 400)

    def test_the_reply_goes_to_the_visitor(self):
        data, ticket = self.ask_for_a_person()
        self.leave(data['handoff_token'])
        mail.outbox = []
        code, body = self.call(views.reply_to_ticket, self.admin, {'body_text': 'Hi Kiran, about the price...'},
                               ticket_id=ticket.id)
        self.assertEqual(code, 201, body)
        self.assertEqual([m.to for m in mail.outbox], [['kiran@clinic.example']])

    def test_a_web_form_ticket_can_be_answered_too(self):
        code, body = self.post('/api/frontline/public/submit', {'name': 'Kiran', 'email': 'kiran@clinic.example',
                                                                 'message': 'Do you build clinic apps?'})
        self.assertLess(code, 300, body)
        ticket = Ticket.objects.filter(company=self.company, title__startswith='Web form').latest('id')
        mail.outbox = []
        code, body = self.call(views.reply_to_ticket, self.admin, {'body_text': 'Yes, we do.'}, ticket_id=ticket.id)
        self.assertEqual(code, 201, body)
        self.assertEqual([m.to for m in mail.outbox], [['kiran@clinic.example']])

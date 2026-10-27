"""What Frontline does by itself with a ticket a customer opens, when the company turns it on.

Customer tickets (chat hand-off, web form, email) arrived as "medium / other" and stayed that way until someone pressed
Re-triage, and nothing answered a simple one. Two switches, both off until an admin turns them on: classify incoming
tickets with the triage staff tickets use, and answer web-form and email tickets the knowledge base answers, when a
small AI check finds the message a simple question and the reply a full answer (mocked here as passing).
"""
import json
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from api.views import frontline_agent as views
from core.Frontline_agent.frontline_agent import FrontlineAgent
from core.models import CompanyModulePurchase
from Frontline_agent.models import Ticket, TicketMessage
from Frontline_agent.tasks import process_inbound_email

from .base import FrontlineTestCase
from .test_inbound_email import payload

KEY = 'wk_automation_test'
TRIAGE = {'suggested_category': 'billing', 'suggested_priority': 'high', 'intent': 'refund_request',
          'entities': {'product_name': 'Pro plan', 'user_id': None}}
SURE = {'answer': 'Refunds are paid within 5 working days of the request.', 'has_verified_info': True,
        'confidence': 'high', 'best_score': 0.82}


class TicketAutomationTests(FrontlineTestCase):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.company.frontline_widget_key = KEY
        self.company.frontline_widget_config = {'require_captcha': False}
        self.company.save(update_fields=['frontline_widget_key', 'frontline_widget_config'])
        from Frontline_agent import ticket_automation
        self.check = mock.patch.object(ticket_automation, '_safe_to_send', return_value=True).start()
        self.addCleanup(mock.patch.stopall)

    def switch_on(self, classify=False, resolve=False):
        self.company.frontline_widget_config = {
            'require_captcha': False,
            'ticket_automation': {'classify_incoming': classify, 'resolve_from_knowledge': resolve}}
        self.company.save(update_fields=['frontline_widget_config'])

    def ai(self, triage=TRIAGE, answer=SURE):
        return (mock.patch.object(FrontlineAgent, '_extract_ticket_intent', return_value=triage),
                mock.patch.object(FrontlineAgent, 'answer_question', return_value=answer))

    def submit_form(self, message='How long does a refund take?'):
        triage, answering = self.ai()
        with triage, answering, self.captureOnCommitCallbacks(execute=True):
            response = Client().post('/api/frontline/public/submit', json.dumps({
                'widget_key': KEY, 'name': 'Sana Malik', 'email': 'sana@customer.test', 'message': message}),
                content_type='application/json')
        self.assertIn(response.status_code, (200, 201), response.content)
        return Ticket.objects.filter(company=self.company, title__startswith='Web form').latest('id')

    def from_automation(self):
        """The emails automation sent: not the acknowledgement every contact-form sender now gets."""
        return [m for m in mail.outbox if not m.subject.startswith('We received your message')]

    def email_in(self, answer=SURE, **overrides):
        triage, answering = self.ai(answer=answer)
        with triage, answering, self.captureOnCommitCallbacks(execute=True):
            result = process_inbound_email(payload(self.company.id, **overrides))
        return Ticket.objects.get(pk=result['ticket_id'])

    # ---- off by default ------------------------------------------------------------------------------------

    def test_nothing_happens_until_it_is_turned_on(self):
        with mock.patch.object(FrontlineAgent, '_extract_ticket_intent', side_effect=AssertionError('no AI')):
            ticket = self.submit_form()
        self.assertEqual((ticket.category, ticket.priority, ticket.last_triaged_at), ('other', 'medium', None))
        self.assertEqual(self.from_automation(), [])

    # ---- classifying ---------------------------------------------------------------------------------------

    def test_a_form_ticket_is_classified_and_its_deadline_follows_its_priority(self):
        self.switch_on(classify=True)
        ticket = self.submit_form()
        self.assertEqual((ticket.category, ticket.priority, ticket.intent), ('billing', 'high', 'refund_request'))
        self.assertIsNotNone(ticket.last_triaged_at)
        self.assertEqual(ticket.entities, {'product_name': 'Pro plan'})
        self.assertLess(ticket.sla_due_at, timezone.now() + timedelta(hours=9))     # high: 8 hours, not 24
        self.assertEqual(self.from_automation(), [])                                # classifying sends nothing

    def test_an_email_ticket_keeps_its_sender_when_classified(self):
        self.switch_on(classify=True)
        ticket = self.email_in()
        self.assertEqual(ticket.entities['from_email'], 'customer@test.local')
        self.assertEqual(ticket.entities['product_name'], 'Pro plan')
        self.assertEqual(ticket.category, 'billing')

    def test_a_hand_off_is_not_lowered_below_medium(self):
        self.switch_on(classify=True)
        ticket = self.make_ticket(title='Hand-off: hello', handoff_status='pending', priority='medium')
        from Frontline_agent import ticket_automation
        with self.ai(triage={**TRIAGE, 'suggested_priority': 'low'})[0]:
            ticket_automation.handle(ticket.id, 'chat')
        ticket.refresh_from_db()
        self.assertEqual((ticket.priority, ticket.category), ('medium', 'billing'))

    # ---- answering from the knowledge base -----------------------------------------------------------------

    def test_a_sure_answer_is_emailed_and_the_ticket_resolved_and_a_reply_reopens_it(self):
        self.switch_on(resolve=True)
        ticket = self.email_in()

        self.assertEqual((ticket.status, ticket.auto_resolved), ('auto_resolved', True))
        self.assertEqual(ticket.resolution, SURE['answer'])
        self.assertIsNotNone(ticket.resolved_at)
        [sent] = mail.outbox
        self.assertEqual(sent.to, ['customer@test.local'])
        self.assertIn(SURE['answer'], sent.body)
        self.assertIn('just reply', sent.body)
        self.assertTrue(TicketMessage.objects.filter(ticket=ticket, direction='outbound').exists())

        process_inbound_email(payload(self.company.id, existing_ticket_id=ticket.id, message_id='<msg-2@test.local>',
                                      body_text='That did not help, my refund is 3 weeks late.'))
        ticket.refresh_from_db()
        self.assertEqual((ticket.status, ticket.resolved_at), ('open', None))

    def test_a_form_ticket_is_answered_at_the_address_given(self):
        self.switch_on(resolve=True)
        ticket = self.submit_form()
        self.assertEqual(ticket.status, 'auto_resolved')
        self.assertEqual(mail.outbox[0].to, ['sana@customer.test'])
        # In the receipt's thread, not "Re: Web form: Sana Malik".
        [answer] = self.from_automation()
        self.assertEqual(answer.subject, f'Re: We received your message [FL-{ticket.id}]')

    def test_an_answer_that_is_not_sure_is_left_for_a_person(self):
        from core.Frontline_agent.frontline_agent import NOT_IN_THE_DOCUMENTS
        self.switch_on(resolve=True)
        for answer in ({**SURE, 'has_verified_info': False},
                       {**SURE, 'answer': "I don't have information about refunds for that plan."},
                       {**SURE, 'answer': NOT_IN_THE_DOCUMENTS}):
            mail.outbox.clear()
            ticket = self.email_in(answer=answer, message_id=f'<{len(answer["answer"])}-{answer["has_verified_info"]}@t>')
            self.assertEqual((ticket.status, ticket.auto_resolved), ('new', False), answer)
            self.assertEqual(mail.outbox, [])

    def test_a_reply_the_check_does_not_pass_is_left_for_a_person(self):
        self.switch_on(resolve=True)
        self.check.return_value = False
        ticket = self.email_in()
        self.assertEqual((ticket.status, ticket.auto_resolved), ('new', False))
        self.assertEqual(mail.outbox, [])

    def test_a_medium_search_match_is_answered_when_the_check_passes(self):
        # Search confidence never reached 'high' on the live site, so nothing was ever answered (27 Oct).
        self.switch_on(resolve=True)
        ticket = self.email_in(answer={**SURE, 'confidence': 'medium', 'best_score': None})
        self.assertEqual((ticket.status, ticket.auto_resolved), ('auto_resolved', True))
        question, answer = self.check.call_args.args[1:]
        self.assertEqual(answer, SURE['answer'])

    def test_the_check_asks_whether_the_message_is_simple_and_fully_answered(self):
        from Frontline_agent import ticket_automation
        mock.patch.stopall()
        ticket = self.make_ticket(title='Backups', description='How long do you keep backups?')
        for raw, expected in (('{"simple_question": true, "fully_answered": true, "confidence": 0.9}', True),
                              ('{"simple_question": false, "fully_answered": true, "confidence": 0.9}', False),
                              ('{"simple_question": true, "fully_answered": true, "confidence": 0.5}', False),
                              ('not json', False)):
            with mock.patch.object(FrontlineAgent, '_call_llm', return_value=raw):
                self.assertIs(ticket_automation._safe_to_send(ticket, 'q', 'a'), expected, raw)

    def test_a_chat_hand_off_is_never_answered_by_the_ai(self):
        self.switch_on(resolve=True)
        ticket = self.make_ticket(title='Hand-off: refunds', description='How long does a refund take?',
                                  handoff_status='pending', status='new')
        from Frontline_agent import ticket_automation
        self.assertFalse(ticket_automation.queue(ticket, 'chat'))
        with self.ai()[1]:
            self.assertEqual(ticket_automation.handle(ticket.id, 'chat'), {'classified': False, 'resolved': False})
        self.assertEqual(mail.outbox, [])

    def test_an_urgent_ticket_is_left_for_a_person(self):
        self.switch_on(classify=True, resolve=True)
        triage, answering = self.ai(triage={**TRIAGE, 'suggested_priority': 'urgent'})
        with triage, answering, self.captureOnCommitCallbacks(execute=True):
            result = process_inbound_email(payload(self.company.id))
        ticket = Ticket.objects.get(pk=result['ticket_id'])
        self.assertEqual((ticket.priority, ticket.status), ('urgent', 'new'))
        self.assertEqual(mail.outbox, [])

    def test_a_company_without_frontline_now_gets_nothing_done(self):
        self.switch_on(classify=True, resolve=True)
        ticket = self.make_ticket(title='Refund', description='How long does a refund take?')
        CompanyModulePurchase.objects.filter(company=self.company).update(status='cancelled')
        from Frontline_agent import ticket_automation
        with mock.patch.object(FrontlineAgent, '_extract_ticket_intent', side_effect=AssertionError('no AI')):
            self.assertEqual(ticket_automation.handle(ticket.id, 'email'), {'classified': False, 'resolved': False})

    # ---- the switches --------------------------------------------------------------------------------------

    def test_an_admin_turns_them_on_and_both_are_saved_as_true_or_false(self):
        code, body = self.call(views.update_frontline_widget_config, self.admin,
                               {'config': {'ticket_automation': {'classify_incoming': True, 'junk': 1}}},
                               method='patch')
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data']['config']['ticket_automation'],
                         {'classify_incoming': True, 'resolve_from_knowledge': False})

    def test_a_member_cannot_turn_them_on(self):
        code, _ = self.call(views.update_frontline_widget_config, self.member,
                            {'config': {'ticket_automation': {'resolve_from_knowledge': True}}}, method='patch')
        self.assertEqual(code, 403)

    def test_a_new_company_has_both_off(self):
        code, body = self.call(views.frontline_widget_config, self.admin, method='get')
        self.assertEqual(body['data']['config']['ticket_automation'],
                         {'classify_incoming': False, 'resolve_from_knowledge': False})

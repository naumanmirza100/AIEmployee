"""The website chat reads each message (core/Frontline_agent/intent.py) instead of a list of phrases.

Found preparing the Frontline demo (27 Oct 2026): "hi" was searched, answered "I don't have verified information… a
human agent will assist you" and filed as a "KB gap: hi" ticket; "I don't need a human" opened a hand-off; a request
for a call or a report that the customer's website is down was searched like a question; Roman Urdu was missed.
"""
import json
from unittest import mock

from django.core.cache import cache
from django.test import Client

from api.views import frontline_agent as views
from core.Frontline_agent import intent
from Frontline_agent.models import Ticket

from .base import FrontlineTestCase

KEY = 'wk_reading_test'
FOUND = {'answer': 'Support is open 9 am to 6 pm.', 'has_verified_info': True, 'confidence': 0.9,
         'sources': [], 'citations': [], 'best_score': 0.9}
NOT_FOUND = {'answer': 'not in the documents', 'has_verified_info': False, 'confidence': 0.0,
             'sources': [], 'citations': [], 'best_score': 0.0}


def reading(kind, **extra):
    return {'kind': kind, 'english': extra.pop('english', 'What are your support hours?'),
            'full_list': extra.pop('full_list', False), 'urgent': extra.pop('urgent', False),
            'roman_urdu': extra.pop('roman_urdu', False)}


class WidgetReadingTests(FrontlineTestCase):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.company.frontline_widget_key = KEY
        self.company.save(update_fields=['frontline_widget_key'])
        self.answer = mock.patch.object(views.FrontlineAgent, 'answer_question', return_value=FOUND).start()
        self.addCleanup(mock.patch.stopall)

    def ask(self, question, read, **extra):
        with mock.patch.object(intent, 'read', return_value=read):
            response = Client().post('/api/frontline/public/qa',
                                     json.dumps({'widget_key': KEY, 'question': question, **extra}),
                                     content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        return json.loads(response.content)['data']

    def tickets(self):
        return list(Ticket.objects.filter(company=self.company).exclude(pk=self.ticket.pk)
                    .values_list('title', 'handoff_reason', 'priority'))

    def test_a_greeting_is_answered_without_a_search_or_a_ticket(self):
        data = self.ask('hi', reading('greeting'))
        self.assertTrue(data['answer'].startswith('Hello!'))
        self.answer.assert_not_called()
        self.assertEqual(self.tickets(), [])

    def test_thanks_in_roman_urdu_is_answered_in_roman_urdu(self):
        data = self.ask('shukriya', reading('thanks', roman_urdu=True))
        self.assertTrue(data['answer'].startswith('Koi baat nahi'))
        self.assertEqual(self.tickets(), [])

    def test_saying_no_person_is_needed_is_not_a_hand_off(self):
        # The phrases matched "need a human" in "I don't need a human".
        data = self.ask("I don't need a human, just tell me your hours", reading('question'))
        self.assertNotIn('handoff_requested', data)
        self.assertEqual(self.tickets(), [])

    def test_asking_for_a_person_in_roman_urdu_is_a_hand_off(self):
        data = self.ask('kisi insaan se baat karwa do', reading('wants_person', roman_urdu=True))
        self.assertTrue(data['handoff_requested'])
        self.assertTrue(data['answer'].startswith('Zaroor'))      # answered in Roman Urdu
        [(title, reason, _)] = self.tickets()
        self.assertEqual((title.split(':')[0], reason), ('Hand-off', 'customer_requested'))
        self.answer.assert_not_called()

    def test_asking_for_a_call_goes_to_a_person_as_a_call_request(self):
        data = self.ask('Can we have a call tomorrow about the new menu page?', reading('wants_call'),
                        visitor_email='farhan@bakery.test', visitor_name='Farhan')
        self.assertIn("arrange one", data['answer'])
        [(title, reason, _)] = self.tickets()
        self.assertEqual((title.split(':')[0], reason), ('Call requested', 'call_requested'))
        ticket = Ticket.objects.get(pk=data['handoff_ticket_id'])
        self.assertEqual(ticket.contact.email, 'farhan@bakery.test')

    def test_an_urgent_problem_is_answered_and_goes_to_a_person_as_high_priority(self):
        data = self.ask('Our website is down and we cannot take orders!', reading('problem', urgent=True))
        self.assertIn('Support is open 9 am to 6 pm.', data['answer'])       # what the documents say
        self.assertIn('passed this to our team', data['answer'])
        [(title, reason, priority)] = self.tickets()
        self.assertEqual((title.split(':')[0], reason, priority), ('Problem', 'problem_reported', 'high'))

    def test_a_problem_the_documents_do_not_cover_is_not_a_knowledge_gap(self):
        self.answer.return_value = NOT_FOUND
        data = self.ask('You charged us twice', reading('problem'))
        self.assertTrue(data['answer'].startswith("I'm sorry"))
        self.assertEqual([t[1] for t in self.tickets()], ['problem_reported'])

    def test_a_question_is_searched_in_english_and_says_whether_a_whole_list_is_wanted(self):
        self.ask('aap ke saare plans batao', reading('question', english='What are all your support plans?',
                                                       full_list=True, roman_urdu=True))
        kwargs = self.answer.call_args.kwargs
        self.assertEqual((kwargs['search_query'], kwargs['wants_everything']),
                         ('What are all your support plans?', True))

    def test_without_a_reading_the_phrases_still_hand_off(self):
        data = self.ask('Can I talk to a person please?', None)
        self.assertTrue(data['handoff_requested'])
        self.assertEqual(self.answer.call_args.kwargs['search_query'], None)


class PromptTests(FrontlineTestCase):

    def test_the_assistant_speaks_for_the_company_not_for_payperproject(self):
        agent = views.FrontlineAgent(company_id=self.company.id)
        self.assertIn(f'customer support assistant of {self.company.name}', agent.system_prompt)
        self.assertNotIn('PayPerProject', agent.system_prompt.split('CRITICAL RULES')[0])


class RuleTests(FrontlineTestCase):

    def test_words_inside_other_words_do_not_set_the_priority(self):
        from core.Frontline_agent.rules import TicketClassificationRules
        out = TicketClassificationRules.classify_ticket('I would like to know how the download works')
        self.assertNotEqual(out['priority'], 'urgent')      # "now" in "know", "down" in "download"

    def test_an_urgent_how_to_is_not_marked_easy(self):
        from core.Frontline_agent.rules import TicketClassificationRules
        out = TicketClassificationRules.classify_ticket('How do I stop being charged twice? This is urgent')
        self.assertFalse(out['auto_resolvable'])
        self.assertEqual(out['priority'], 'urgent')


class FormAcknowledgementTests(FrontlineTestCase):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.company.frontline_widget_key = KEY
        self.company.save(update_fields=['frontline_widget_key'])

    def test_the_customer_is_told_by_email_that_their_message_arrived(self):
        # The page said "We'll get back to you soon" and nothing came by email: no reference, no sign it arrived.
        from django.core import mail
        with self.captureOnCommitCallbacks(execute=True):
            response = Client().post('/api/frontline/public/submit', json.dumps({
                'widget_key': KEY, 'name': 'Farhan', 'email': 'farhan@bakery.test',
                'message': 'Our menu page shows old prices.'}), content_type='application/json')
        self.assertLess(response.status_code, 300, response.content)
        ticket = Ticket.objects.filter(company=self.company, title__startswith='Web form').latest('id')
        [email] = [m for m in mail.outbox if m.to == ['farhan@bakery.test']]
        self.assertEqual(email.subject, f'We received your message [FL-{ticket.id}]')
        self.assertIn('Our menu page shows old prices.', email.body)

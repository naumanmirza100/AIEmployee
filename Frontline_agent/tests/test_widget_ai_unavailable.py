"""When a company's AI cannot be used, its customers are not told why.

The chat widget sits on the company's own website and needs no login. If the
company's AI allowance was used up, its key refused, or the agent switched off,
the visitor was shown our internal message word for word ("Free platform tokens
for this agent are exhausted. Add your own API key (BYOK)…"), and the request
stopped there, so a visitor asking for a person never reached the hand-off.
A scheduled customer email using AI wording hit the same wall and was never
sent. Requests go through the URL, as the widget's do.
"""
import json
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from api.views import frontline_agent as views
from core.api_key_service import QuotaExhausted
from Frontline_agent.models import NotificationTemplate, ScheduledNotification, Ticket
from Frontline_agent.tasks import process_scheduled_notifications
from project_manager_agent.models import PMNotification

from .base import FrontlineTestCase

INTERNAL_WORDS = ('token', 'byok', 'api key', 'managed key', 'admin')


class WidgetWithoutAITests(FrontlineTestCase):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.company.frontline_widget_key = 'wk_made_up_for_a_test'
        self.company.save(update_fields=['frontline_widget_key'])
        blocked = mock.patch.object(views.FrontlineAgent, 'answer_question', side_effect=QuotaExhausted())
        blocked.start()
        self.addCleanup(blocked.stop)

    def ask(self, question, **extra):
        response = Client().post('/api/frontline/public/qa', json.dumps(
            {'widget_key': 'wk_made_up_for_a_test', 'question': question, **extra}), content_type='application/json')
        return response.status_code, json.loads(response.content)

    def alerts(self, who=None):
        return list(PMNotification.objects.filter(company_user=who or self.admin,
                                                  title='Your website chat cannot answer visitors'))

    def test_the_visitor_gets_a_polite_answer_not_our_billing_message(self):
        code, body = self.ask('How do I reset my password?')
        self.assertEqual((code, body['status']), (200, 'success'), body)
        text = json.dumps(body).lower()
        for word in INTERNAL_WORDS:
            self.assertNotIn(word, text)
        self.assertIn('try again', body['data']['answer'])
        self.assertFalse(body['data']['has_verified_info'])

    def test_the_company_is_told_why_once_an_hour_not_once_a_visitor(self):
        for question in ('How do I reset my password?', 'Where is my invoice?', 'Is there a mobile app?'):
            self.ask(question)
        [alert] = self.alerts()
        self.assertIn('Free platform tokens for this agent are exhausted', alert.message)
        self.assertEqual(alert.data.get('link'), '/company/settings/api-keys')
        self.assertEqual(self.alerts(self.member), [])                  # admins and the Frontline role only

    def test_a_visitor_who_asks_for_a_person_still_reaches_someone(self):
        code, body = self.ask('I want to talk to a human agent please', visitor_email='vera@customer.example')
        self.assertEqual(code, 200, body)
        self.assertTrue(body['data'].get('handoff_requested'), body)
        ticket = Ticket.objects.get(pk=body['data']['handoff_ticket_id'])
        self.assertEqual((ticket.company_id, ticket.handoff_status), (self.company.id, 'pending'))

    def test_it_is_not_filed_as_a_gap_in_the_knowledge_base(self):
        self.ask('How do I reset my password?')
        self.assertFalse(Ticket.objects.filter(company=self.company, category='knowledge_gap').exists())


class WidgetWithAITests(FrontlineTestCase):
    def test_a_working_assistant_answers_as_before_and_raises_no_alert(self):
        cache.clear()
        self.company.frontline_widget_key = 'wk_made_up_for_a_test'
        self.company.save(update_fields=['frontline_widget_key'])
        answer = {'answer': 'Use the Forgot password link.', 'has_verified_info': True, 'confidence': 0.9,
                  'sources': [], 'citations': [], 'best_score': 0.9}
        with mock.patch.object(views.FrontlineAgent, 'answer_question', return_value=answer):
            response = Client().post('/api/frontline/public/qa', json.dumps(
                {'widget_key': 'wk_made_up_for_a_test', 'question': 'How do I reset my password?'}),
                content_type='application/json')
        self.assertEqual(json.loads(response.content)['data']['answer'], 'Use the Forgot password link.')
        self.assertFalse(PMNotification.objects.filter(title='Your website chat cannot answer visitors').exists())


class ScheduledEmailWithoutAITests(FrontlineTestCase):
    def test_the_email_goes_out_with_the_template_text(self):
        template = NotificationTemplate.objects.create(
            company=self.company, name='Follow-up', subject='About ticket {{ticket_id}}',
            body='Hello, ticket {{ticket_id}} was updated.', channel='email')
        notice = ScheduledNotification.objects.create(
            company=self.company, template=template, scheduled_at=timezone.now() - timedelta(minutes=1),
            recipient_email='vera@customer.example', context={'ticket_id': 41})
        with mock.patch.object(views, '_generate_llm_notification_body', side_effect=QuotaExhausted()):
            process_scheduled_notifications()
        notice.refresh_from_db()
        self.assertEqual(notice.status, 'sent')
        [email] = mail.outbox
        self.assertEqual((email.to, email.subject), (['vera@customer.example'], 'About ticket 41'))
        self.assertIn('ticket 41 was updated', email.body)

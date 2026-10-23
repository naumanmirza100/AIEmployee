"""The website chat answers with its rate limits on.

The widget-key throttle reads the widget key from `request.data`, which consumes the request's body, and the
public views then read `request.body` again: Django raised RawPostDataException ("You cannot access body after
reading from request's data stream"), and every visitor got "I didn't quite catch that — could you rephrase your
question?". The test settings switch the throttles off, so these tests switch them back on, as the live site has
them.
"""
import json
from unittest import mock

from django.core.cache import cache
from django.test import Client

from api.views import frontline_agent as views
from Frontline_agent.throttling import FrontlinePublicThrottle, FrontlineWidgetKeyThrottle

from .base import FrontlineTestCase

LIVE_RATES = {'frontline_public': '200/hour', 'frontline_widget_key': '1000/hour'}
ANSWER = {'success': True, 'answer': 'Yes, we build booking apps for clinics: 8 to 10 weeks.', 'has_verified_info': True,
          'confidence': 'high', 'best_score': 0.6, 'citations': []}


class WidgetWithThrottlesTests(FrontlineTestCase):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.company.frontline_widget_key = 'wk_made_up_for_a_test'
        self.company.save(update_fields=['frontline_widget_key'])
        for throttle in (FrontlinePublicThrottle, FrontlineWidgetKeyThrottle):
            patcher = mock.patch.object(throttle, 'THROTTLE_RATES', LIVE_RATES)
            patcher.start()
            self.addCleanup(patcher.stop)

    def post(self, path, body):
        response = Client().post(path, json.dumps({'widget_key': 'wk_made_up_for_a_test', **body}),
                                 content_type='application/json')
        return response.status_code, json.loads(response.content)

    def test_a_visitor_gets_the_answer(self):
        with mock.patch.object(views.FrontlineAgent, 'answer_question', return_value=ANSWER) as asked:
            code, body = self.post('/api/frontline/public/qa',
                                   {'question': 'Do you build appointment apps for clinics, and how long would one take?'})
        self.assertEqual(code, 200, body)
        self.assertNotIn('fallback', body['data'], body)
        self.assertEqual(body['data']['answer'], ANSWER['answer'])
        self.assertEqual(asked.call_args.args[0],
                         'Do you build appointment apps for clinics, and how long would one take?')

    def test_a_satisfaction_rating_is_read_too(self):
        # An unknown survey token: the answer must be "not found", not the body error.
        code, body = self.post('/api/frontline/csat/submit', {'token': 'no-such-survey', 'rating': 5})
        self.assertEqual((code, body.get('message')), (404, 'Survey not found'), body)

    def test_the_widget_form_reaches_the_company_too(self):
        code, body = self.post('/api/frontline/public/submit',
                               {'name': 'Kiran', 'email': 'kiran@noorclinic.test', 'message': 'Please call me back.'})
        self.assertNotEqual(code, 500, body)
        self.assertNotIn('cannot access body', json.dumps(body).lower())

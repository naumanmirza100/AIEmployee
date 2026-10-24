"""A suggested reply speaks for the company, as the person sending it does.

The guide says "their team will provide a written estimate", and the suggestion repeated it to the customer:
"they will provide an estimate", sent by someone on that team.
"""
from django.test import SimpleTestCase

from api.views.frontline_agent import _build_suggest_reply_prompt


class SuggestedReplyVoiceTests(SimpleTestCase):

    def test_the_reply_is_written_as_the_company(self):
        prompt = _build_suggest_reply_prompt(ticket_title='Price?', thread='Can I talk to someone about the price?',
                                             kb_snippet='Their team will provide a written estimate.',
                                             customer_name='', company_name='Crestline Technologies')
        self.assertIn("You write as Crestline Technologies's support team", prompt)
        self.assertIn("never 'they' or 'their' for the company", prompt)

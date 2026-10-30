"""The AI's answers are read once more against the campaign's words before anyone sees them.

Found on live after PR #344 (30 Oct): asked whether reminders also go by WhatsApp, an answer still said "WhatsApp
reminders are not currently included", in English to a question in Roman Urdu, although the writing prompt forbids
both. A second, single-purpose call now checks each answer.
"""
from unittest import mock

from ai_sdr_agent.agents.email_assistant_agent import EmailAssistantAgent
from ai_sdr_agent.tests import SDRBase


def answer(text):
    return mock.MagicMock(choices=[mock.MagicMock(message=mock.MagicMock(content=text))], usage=None)


class AnswerCheckTests(SDRBase):
    def setUp(self):
        super().setUp()
        self.campaign.description = 'A patient booking app for dental clinics, with SMS reminders.'
        self.campaign.save()

    def agent(self, *answers):
        agent = EmailAssistantAgent()
        agent.groq_client = mock.MagicMock()
        agent.groq_client.chat.completions.create.side_effect = [answer(a) for a in answers]
        return agent

    def test_the_answer_is_checked_against_the_campaigns_words(self):
        agent = self.agent(
            '{"subject": "Re: reminders", "body": "Hi Kiran, WhatsApp reminders are not currently included."}',
            '{"language": "Roman Urdu", "unsupported": ["WhatsApp reminders are not currently included."], '
            '"body": "Hi Kiran,\\\\nMain check karke bataunga.\\\\nMain check karke bataunga.\\\\nBest, Sam"}')
        email = agent.generate_more_info_email(self.make_lead(), self.campaign,
                                               'Kya reminders WhatsApp par bhi jate hain?\n\n> Hi Kiran,\n> our app')
        self.assertEqual(email['body'], 'Hi Kiran,\nMain check karke bataunga.\nBest, Sam')
        check = agent.groq_client.chat.completions.create.call_args_list[1].kwargs
        self.assertIn('A patient booking app for dental clinics, with SMS reminders.', check['messages'][0]['content'])
        self.assertIn('is NOT included or NOT available counts too', check['messages'][0]['content'])
        self.assertIn('Kya reminders WhatsApp par bhi jate hain?', check['messages'][0]['content'])
        self.assertNotIn('our app', check['messages'][0]['content'])      # the quoted email is not their words
        self.assertEqual((check['temperature'], check['max_tokens']), (0, 6000))

    def test_a_failed_check_keeps_the_answer_as_written(self):
        agent = self.agent('{"subject": "Re: x", "body": "Hi Kiran, SMS reminders are included."}', '', '')
        email = agent.generate_more_info_email(self.make_lead(), self.campaign, 'SMS bhi?')
        self.assertEqual(email['body'], 'Hi Kiran, SMS reminders are included.')
        self.assertEqual(agent.groq_client.chat.completions.create.call_count, 3)    # writing, and two tries

    def test_a_check_that_drops_most_of_the_answer_is_not_used(self):
        # On live (30 Oct) a check cut an answer down to "Hi Kiran, Great to hear you're curious!".
        written = ('{"subject": "Re: x", "body": "Hi Kiran, patients book and move their own appointments, and SMS '
                   'reminders cut missed visits. WhatsApp is not included. Could we talk on Tuesday? Best, Sam"}')
        gutted = '{"body": "Hi Kiran, great to hear from you! Best, Sam"}'
        good = ('{"body": "Hi Kiran, patients book and move their own appointments, and SMS reminders cut missed '
                'visits. Main WhatsApp ke baare mein check karke bataunga. Could we talk on Tuesday? Best, Sam"}')
        email = self.agent(written, gutted, good).generate_more_info_email(self.make_lead(), self.campaign, 'WhatsApp?')
        self.assertIn('Main WhatsApp ke baare mein check karke bataunga.', email['body'])
        email = self.agent(written, gutted, gutted).generate_more_info_email(self.make_lead(), self.campaign, 'WhatsApp?')
        self.assertIn('Could we talk on Tuesday?', email['body'])          # as written, rather than gutted

    def test_the_email_assistants_answer_is_checked_too(self):
        agent = self.agent('{"category": "wants_more_info", "reason": "asks about WhatsApp"}',
                           '{"subject": "Re: WhatsApp", "body": "Yes, WhatsApp is included."}',
                           '{"body": "Main check karke bataunga."}')
        result = agent.read_reply('WhatsApp bhi?', {'name': 'Sam'}, 'A booking app with SMS reminders.')
        self.assertEqual(result['answer']['body'], 'Main check karke bataunga.')

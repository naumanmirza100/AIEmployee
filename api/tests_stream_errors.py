"""A chat says why it cannot answer.

When a company ran out of AI tokens, reached a cap or had the agent switched
off, the HR, Frontline and Project Manager chats were sent an error with no
words in it: those errors are raised with no arguments, and the views sent
`str(exc)`. The chats then showed "(no answer)" or "The answer stopped
part-way". A bell alert went out once at 100%, but the chat never said.
"""
import json
from unittest import mock

from django.test import SimpleTestCase

from api.streaming import error_event
from api.views import hr_agent as hr_views
from core import api_key_service as keys
from hr_agent.tests.base import HRTestCase


class ErrorEventTests(SimpleTestCase):

    def test_every_key_problem_carries_its_own_words_and_a_code(self):
        problems = [keys.QuotaExhausted(), keys.ManagedQuotaExhausted(), keys.NoKeyAvailable(), keys.AgentDisabled(),
                    keys.ByokCapReached(), keys.BadAPIKey(mode='byok'),
                    keys.UnsupportedProvider('hr_agent', 'claude', mode='byok')]
        for exc in problems:
            with self.subTest(type(exc).__name__):
                event = error_event(exc)
                self.assertEqual((event['type'], event['code']), ('error', exc.reason))
                self.assertEqual(event['message'], exc.user_message)
                self.assertGreater(len(event['message']), 20)        # words a person can act on

    def test_the_plain_exception_text_was_empty(self):
        # Why the chats showed nothing: this is what used to be sent.
        self.assertEqual(str(keys.QuotaExhausted()), '')

    def test_anything_else_gets_a_plain_sentence_not_the_exceptions_text(self):
        event = error_event(RuntimeError("relation 'hr_agent_secret' does not exist"))
        self.assertEqual(event['type'], 'error')
        self.assertNotIn('hr_agent_secret', event['message'])
        self.assertIn('try again', event['message'])


class HRChatStreamTests(HRTestCase):

    def ask(self, raises):
        request = self.factory.post('/', {'question': 'How much leave do I have?'}, format='json')
        from rest_framework.test import force_authenticate
        force_authenticate(request, user=self.member)
        with mock.patch.object(hr_views.HRAgent, 'answer_question_stream', side_effect=raises):
            response = hr_views.hr_knowledge_qa_stream(request)
            return [json.loads(line) for line in b''.join(response.streaming_content).decode().splitlines() if line]

    def test_out_of_tokens_reaches_the_chat_as_a_reason(self):
        events = self.ask(keys.QuotaExhausted())
        error = events[-1]
        self.assertEqual((error['type'], error['code']), ('error', 'quota_exhausted'))
        self.assertEqual(error['message'], keys.QuotaExhausted.user_message)

    def test_a_crash_does_not_leak_into_the_chat(self):
        events = self.ask(RuntimeError('column hr_secret does not exist'))
        self.assertEqual(events[-1]['type'], 'error')
        self.assertNotIn('hr_secret', events[-1]['message'])

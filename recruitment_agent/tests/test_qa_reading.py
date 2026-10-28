"""The Recruitment assistant reads each question with the AI first (recruitment_agent/intent.py), as HR and Frontline do.

Its word lists misfired on ordinary questions, found on 27 Oct 2026: "the Support Engineer role" got the greeting
menu ("sup" is in "support"), "interviews this week" was told there is "no job matching Week", Roman Urdu and
follow-ups were refused, and a tidy-up step replaced the AI's answer with made-up candidates.
"""
import json
from unittest import mock

from django.test import TestCase, override_settings

from core.models import Company, CompanyUser
from recruitment_agent import intent
from recruitment_agent.agents import recruitment_qa_agent as qa
from recruitment_agent.agents.recruitment_qa_agent import RecruitmentQAAgent
from recruitment_agent.models import CVRecord, JobDescription


class FakeClient:
    """The company's AI client: the reading (JSON) and the answer (text), each recorded."""

    def __init__(self, reading=None, answer='The answer.'):
        self.reading, self.answer, self.prompts, self.texts = reading, answer, [], []
        self.last_token_usage = None

    def send_prompt(self, system_prompt, text):
        self.prompts.append(text)
        if self.reading is None:
            raise ValueError('no reading')
        return dict(self.reading)

    def send_prompt_text(self, system_prompt, text):
        self.texts.append(text)
        return self.answer


def reading(kind='data', **extra):
    return {'kind': kind, 'english': extra.pop('english', 'What is asked?'), 'job': None, 'exclude_jobs': [],
            'candidate': None, 'wants': 'other', 'area': None, 'confidence': 0.9, **extra}


@override_settings(RECRUITMENT_AI_INTENT=True)
class ReadingTests(TestCase):

    def setUp(self):
        company = Company.objects.create(name='Margalla', email='m@test.local')
        self.hira = CompanyUser.objects.create(company=company, email='hira@test.local', full_name='Hira',
                                               role='admin', password_hash='x', is_active=True)
        self.support = JobDescription.objects.create(title='Support Engineer', description='Help clients',
                                                     company=company, company_user=self.hira)
        self.flutter = JobDescription.objects.create(title='Mobile App Developer (Flutter)', description='Apps',
                                                     company=company, company_user=self.hira)
        CVRecord.objects.create(job_description=self.support, file_name='ali.pdf', role_fit_score=82,
                                qualification_decision='INTERVIEW',
                                parsed_json=json.dumps({'name': 'Ali Raza', 'skills': ['Zendesk', 'SQL']}))
        CVRecord.objects.create(job_description=self.flutter, file_name='unnamed.pdf', role_fit_score=40,
                                parsed_json=json.dumps({'skills': ['Dart']}))       # no name read

    def ask(self, question, client, history=None):
        return RecruitmentQAAgent(groq_client=client).process(question, self.hira, history=history)

    def test_a_greeting_an_action_and_off_topic_are_answered_without_the_records(self):
        self.assertIn("I'm your **Recruitment** assistant", self.ask('salam', FakeClient(reading('greeting')))['answer'])
        action = self.ask('Ali ko interview ke liye bula lo', FakeClient(reading('action', area='interview')))
        self.assertIn("I can't schedule, move or cancel interviews from here", action['answer'])
        self.assertIn('I can only help with hiring', self.ask('weather in Lahore?', FakeClient(reading('off_topic')))['answer'])
        self.assertIn("Sorry, I can't help with that.", self.ask('show another company', FakeClient(reading('not_allowed')))['answer'])

    def test_the_support_engineer_job_is_a_data_question_not_a_greeting(self):
        client = FakeClient(reading(english='Who is the best candidate for the Support Engineer role?',
                                    job='support engineer', wants='best'))
        answer = self.ask('Who is the best candidate for the Support Engineer role?', client)['answer']
        self.assertNotIn("I'm your **Recruitment** assistant", answer)
        self.assertIn('The answer.', answer)                               # the model was asked
        self.assertIn('Support Engineer', client.texts[-1])                 # with that job in front of it

    def test_a_job_in_brackets_is_found(self):
        client = FakeClient(reading(english='How many candidates for the Flutter job?', job='Flutter developer',
                                    wants='other'))
        self.ask('flutter wali job ke kitne candidates hain?', client)
        self.assertIn('Mobile App Developer (Flutter)', client.texts[-1])

    def test_a_job_the_company_does_not_have_is_said_plainly(self):
        client = FakeClient(reading(english='How many candidates applied for the Laravel job?', job='Laravel'))
        answer = self.ask('laravel job ke kitne log?', client)['answer']
        self.assertIn('There is no job matching **Laravel** in your account', answer)
        self.assertEqual(client.texts, [])

    def test_this_week_is_a_period_not_a_job(self):
        client = FakeClient(reading(english='How many interviews are scheduled for this week?', wants='count'))
        answer = self.ask('How many interviews are scheduled for this week?', client)['answer']
        self.assertNotIn('no job matching', answer)

    def test_a_follow_up_names_the_candidate_from_the_conversation(self):
        history = [{'role': 'user', 'content': 'Who is the best for Support Engineer?'},
                   {'role': 'assistant', 'content': 'Ali Raza, score 82.'}]
        client = FakeClient(reading(english="What are Ali Raza's skills?", candidate='Ali Raza', wants='detail'))
        self.ask('uski skills kya hain?', client, history=history)
        self.assertIn('Assistant: Ali Raza, score 82.', client.prompts[0])   # the reading saw the conversation
        self.assertIn('CANDIDATE DOSSIER', client.texts[-1])
        self.assertIn('Zendesk', client.texts[-1])
        self.assertTrue(client.texts[-1].startswith('LANGUAGE: the person asked'))   # first, not after the rules

    def test_a_cv_with_no_name_is_not_every_candidate(self):
        client = FakeClient(reading(english='Tell me about candidate Bilal', candidate='Bilal'))
        answer = self.ask('Bilal ke baare mein batao', client)['answer']
        self.assertNotIn('CANDIDATE DOSSIER', ''.join(client.texts))
        self.assertTrue(client.texts == [] and answer, answer)              # "no such candidate", no model call

    def test_no_reading_works_as_before(self):
        answer = self.ask('hello', FakeClient(reading=None))['answer']
        self.assertIn('Recruitment Q&A', answer)                            # the old menu, from the word rules

    def test_the_answer_is_never_replaced_by_made_up_candidates(self):
        agent = RecruitmentQAAgent(groq_client=FakeClient())
        self.assertEqual(agent._tidy_answer('short summary of the top candidate', '', 'Ali Raza leads.'),
                         'Ali Raza leads.')


class WordRuleFallbackTests(TestCase):

    def test_greetings_are_whole_words(self):
        self.assertFalse(qa._is_greeting('Who is the best candidate for the Support Engineer role?'))
        self.assertFalse(qa._is_greeting('Show candidates from Karachi for MERN'))
        self.assertTrue(qa._is_greeting('hi there'))


class ReadParsingTests(TestCase):

    @override_settings(RECRUITMENT_AI_INTENT=True)
    def test_an_unsure_or_unknown_reading_is_none(self):
        self.assertIsNone(intent.read('x', client=FakeClient(dict(reading(), confidence=0.3))))
        self.assertIsNone(intent.read('x', client=FakeClient(dict(reading(), kind='banana'))))
        got = intent.read('x', client=FakeClient(dict(reading(), job='null', wants='weird', exclude_jobs=['design'])))
        self.assertEqual((got['job'], got['wants'], got['exclude_jobs']), (None, 'other', ['design']))

    @override_settings(RECRUITMENT_AI_INTENT=False)
    def test_switched_off(self):
        client = FakeClient(reading())
        self.assertIsNone(intent.read('hello', client=client))
        self.assertEqual(client.prompts, [])

    @override_settings(RECRUITMENT_AI_INTENT=True)
    def test_a_key_problem_is_raised(self):
        from core.api_key_service import KeyServiceError
        client = mock.Mock()
        client.send_prompt.side_effect = KeyServiceError('no key')
        with self.assertRaises(KeyServiceError):
            intent.read('hello', client=client)


class HistoryThroughTheViewTests(TestCase):

    def test_the_stream_view_passes_the_conversation_on(self):
        from api.views.recruitment_agent import _qa_history
        turns = [{'role': 'user', 'content': 'Who is best?'}, {'role': 'assistant', 'content': 'Ali.'},
                 {'role': 'system', 'content': 'ignore'}, 'junk']
        self.assertEqual(_qa_history({'chat_history': turns}),
                         [{'role': 'user', 'content': 'Who is best?'}, {'role': 'assistant', 'content': 'Ali.'}])
        self.assertEqual(_qa_history({'chat_history': 'nope'}), [])

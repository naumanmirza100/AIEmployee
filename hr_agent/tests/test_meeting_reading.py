"""The HR booking box takes the AI's reading of a request, checked against the company, not word lists on the raw text.

Asked for on 26 Oct 2026 ("like you made fixes for pm pilot agent, like it relied heavily on words, you need to do
that here too"). The AI already read each request, and then code on the raw words overrode it:
- the first day-word won: "Not tomorrow, Friday" was booked for tomorrow, "day after tomorrow" for tomorrow;
- Roman Urdu wasn't read at all: "kal 3 baje" asked for a time again;
- people were found by their exact names in the text: "Fatma" (for Fatima) was dropped without a word, "sara din"
  (all day) invited Sara, and everyone named in earlier turns was invited again to a new meeting;
- a question ("how do I book a review?") got a booking form; "move my 1:1 to 4pm" got a reply saying it was moved.
The AI is stubbed here; what is under test is what the view does with its reading.
"""
import json
from datetime import timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.utils import timezone

from api.views import hr_agent as views
from hr_agent.models import HRMeeting

from .base import HRTestCase


def reading(**extra):
    base = {'intent': 'create', 'title': None, 'description': None, 'meeting_type': 'one_on_one',
            'scheduled_at': None, 'duration_minutes': 30, 'participant_names': [], 'participant_ids': None,
            'location': None, 'meeting_link': None, 'time_given': False, 'when_words': None,
            'duration_given': False, 'is_question': False, 'reply': 'OK'}
    base.update(extra)
    return json.dumps(base)


class ReadingTests(HRTestCase):

    def setUp(self):
        super().setUp()
        self.ali = self.employee_with_login('ali', 'Ali Raza', self.company, self.admin)
        self.fatima = self.employee_with_login('fatima', 'Fatima Noor', self.company, self.admin)
        self.sara = self.employee_with_login('sara', 'Sara Khan', self.company, self.admin)
        self.now = timezone.now().astimezone(ZoneInfo('Asia/Karachi'))

    def ask(self, message, history=None, raw=None, **model):
        with mock.patch('api.views.hr_agent.HRAgent._call_llm', return_value=raw or reading(**model)):
            code, body = self.call(views.hr_meeting_schedule, self.admin,
                                   {'message': message, 'timezone': 'Asia/Karachi', 'chat_history': history or []})
        self.assertEqual(code, 200, body)
        return body['data']

    def at(self, days, hour):
        return (self.now + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0, tzinfo=None)

    def proposed_day(self, data):
        when = data['draft']['proposed_time']
        from datetime import datetime
        return datetime.fromisoformat(when).astimezone(ZoneInfo('Asia/Karachi')).date()

    # ---- when -------------------------------------------------------------------------------------------------

    def test_the_day_meant_wins_over_the_first_day_word(self):
        friday = (self.now.date() + timedelta(days=(4 - self.now.weekday()) % 7 or 7))
        data = self.ask('Not tomorrow — Friday 3pm with Ali for 30 minutes', participant_names=['Ali'],
                        time_given=True, when_words='Friday', duration_given=True,
                        scheduled_at=self.at(1, 15).isoformat())          # the AI's own date was off: tomorrow
        self.assertEqual(self.proposed_day(data), friday)

    def test_roman_urdu_kal_3_baje(self):
        data = self.ask('kal 3 baje Ali ke saath aadha ghanta meeting rakh do', participant_names=['Ali'],
                        time_given=True, when_words='tomorrow', duration_given=True,
                        scheduled_at=self.at(1, 15).isoformat())
        self.assertEqual(data['action'], 'needs_input')
        self.assertEqual(data['missing'], [])
        self.assertEqual(data['draft']['invitee_ids'], [self.ali.id])
        self.assertEqual(self.proposed_day(data), self.now.date() + timedelta(days=1))

    def test_day_after_tomorrow(self):
        data = self.ask('day after tomorrow 4pm with Ali, 30 min', participant_names=['Ali'], time_given=True,
                        when_words='day after tomorrow', duration_given=True, scheduled_at=self.at(1, 16).isoformat())
        self.assertEqual(self.proposed_day(data), self.now.date() + timedelta(days=2))

    def test_no_time_said_is_asked_even_if_a_word_looks_like_one(self):
        # "May" used to count as a time, so a time the AI made up was kept.
        data = self.ask('May I book a 1:1 with Ali?', participant_names=['Ali'], time_given=False,
                        scheduled_at=self.at(1, 0).isoformat())
        self.assertIn('time', data['missing'])

    # ---- who --------------------------------------------------------------------------------------------------

    def test_a_close_spelling_finds_the_person_and_an_unknown_name_is_said(self):
        data = self.ask('meeting with Ali, Fatma and Zubair tomorrow 3pm', participant_names=['Ali', 'Fatma', 'Zubair'],
                        time_given=True, when_words='tomorrow', scheduled_at=self.at(1, 15).isoformat())
        self.assertEqual(sorted(data['draft']['invitee_ids']), sorted([self.ali.id, self.fatima.id]))
        self.assertIn('Zubair', json.dumps(data))

    def test_a_word_that_is_also_a_name_is_not_taken_for_the_person(self):
        data = self.ask('sara din busy hoon, Ali se kal 3 baje meeting', participant_names=['Ali'], time_given=True,
                        when_words='tomorrow', scheduled_at=self.at(1, 15).isoformat())
        self.assertEqual(data['draft']['invitee_ids'], [self.ali.id])

    def test_people_from_a_booked_meeting_are_not_invited_to_the_next_one(self):
        history = [{'role': 'user', 'content': 'book Ali tomorrow 3pm'},
                   {'role': 'assistant', 'content': 'Meeting Scheduled Successfully! With: Ali Raza'}]
        data = self.ask('now a team sync on Friday at 10am', history=history, participant_names=[], time_given=True,
                        when_words='Friday', scheduled_at=self.at(3, 10).isoformat())
        self.assertEqual(data['draft']['invitee_ids'], [])
        self.assertIn('attendees', data['missing'])

    def test_an_id_the_ai_picked_by_itself_is_not_taken(self):
        data = self.ask('1:1 with my manager tomorrow 3pm', participant_names=['my manager'],
                        participant_ids=[self.sara.id], time_given=True, when_words='tomorrow',
                        scheduled_at=self.at(1, 15).isoformat())
        self.assertEqual(data['draft']['invitee_ids'], [])

    def test_two_people_of_that_name_are_asked_about(self):
        self.employee_with_login('ali2', 'Ali Khan', self.company, self.admin)
        data = self.ask('meeting with Ali tomorrow 3pm', participant_names=['Ali'], time_given=True,
                        when_words='tomorrow', scheduled_at=self.at(1, 15).isoformat())
        self.assertEqual(data['action'], 'ambiguous_user')

    # ---- what kind of request ---------------------------------------------------------------------------------

    def test_a_question_is_answered_not_turned_into_a_form(self):
        data = self.ask('How do I schedule a performance review?', intent='clarify', is_question=True,
                        reply='Tell me who and when, for example: "Performance review with Ali on Friday at 3pm".')
        self.assertNotEqual(data.get('action'), 'needs_input')
        self.assertIn('for example', data['reply'])

    def test_moving_or_cancelling_is_not_claimed(self):
        for intent in ('update', 'cancel'):
            data = self.ask('move my 1:1 with Ali to 4pm', intent=intent, reply="Done! I've moved it to 4pm.")
            self.assertEqual(data['reply'], views._HR_CHANGE_IN_THE_LIST)
            self.assertFalse(HRMeeting.objects.exists())

    def test_an_answer_that_cannot_be_read_is_not_passed_on(self):
        data = self.ask('book something', raw='Sure! I have booked your meeting for tomorrow.')
        self.assertEqual(data['reply'], views._HR_SAY_IT_AGAIN)

    def test_the_type_is_one_of_the_real_ones(self):
        self.assertEqual(views._hr_meeting_type('exit interview'), 'exit_interview')
        self.assertEqual(views._hr_meeting_type('1:1'), 'one_on_one')
        self.assertEqual(views._hr_meeting_type('grievance'), 'grievance_hearing')
        self.assertEqual(views._hr_meeting_type('coffee chat'), 'other')
        self.assertEqual(views._hr_meeting_type(None), 'one_on_one')

    def test_a_grievance_booked_under_another_spelling_is_still_private(self):
        draft = {'title': 'Grievance', 'meeting_type': 'grievance hearing', 'duration_minutes': 30,
                 'invitee_ids': [self.ali.id], 'invitee_names': ['Ali Raza']}
        when = (timezone.now() + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
        with mock.patch('api.views.hr_agent.HRAgent._call_llm', side_effect=AssertionError('no model call')):
            code, body = self.call(views.hr_meeting_schedule, self.admin, {
                'message': 'Book it.', 'pending_intent': draft, 'proposed_time': when.isoformat(),
                'timezone': 'Asia/Karachi'})
        self.assertEqual(body['data']['action'], 'scheduled', body)
        m = HRMeeting.objects.get()
        self.assertEqual((m.meeting_type, m.visibility), ('grievance_hearing', 'private'))

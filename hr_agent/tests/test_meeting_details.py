"""The HR meeting scheduler asks for who / when / how long instead of guessing.

Same behaviour as the Project Manager scheduler (project_manager_agent/tests/
test_meeting_details.py): whatever the request left out comes back as one
review form, and the confirmed form is booked exactly as shown. The model is
stubbed; what is under test is what the view does with its answer.
"""

import json
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock
from zoneinfo import ZoneInfo

from django.utils import timezone

from api.views import hr_agent as views
from hr_agent.models import HRMeeting

from .base import HRTestCase


def intent(**extra):
    """The model's JSON answer, overridable per test."""
    base = {'intent': 'create', 'title': None, 'description': None,
            'meeting_type': 'one_on_one', 'scheduled_at': None,
            'duration_minutes': 30,          # the prompt makes it default this
            'participant_names': None, 'participant_ids': None,
            'location': None, 'meeting_link': None, 'reply': 'OK'}
    base.update(extra)
    return json.dumps(base)


class HRMeetingDetailsTests(HRTestCase):

    def setUp(self):
        super().setUp()
        self.ali = self.employee_with_login('ali', 'Ali Staff', self.company, self.admin)
        self.tomorrow_3pm = (timezone.now() + timedelta(days=1)).replace(
            hour=15, minute=0, second=0, microsecond=0, tzinfo=None)

    def ask(self, message, tz='UTC', **model):
        with mock.patch('api.views.hr_agent.HRAgent._call_llm', return_value=intent(**model)):
            return self.call(views.hr_meeting_schedule, self.admin,
                             {'message': message, 'timezone': tz})[1]['data']

    def confirm(self, draft, when):
        with mock.patch('api.views.hr_agent.HRAgent._call_llm',
                        side_effect=AssertionError('confirming must not call the model')):
            return self.call(views.hr_meeting_schedule, self.admin, {
                'message': 'Book it.', 'pending_intent': draft,
                'proposed_time': when.isoformat(), 'timezone': 'UTC'})[1]['data']

    def test_a_complete_request_is_booked_without_a_form(self):
        data = self.ask('Schedule a 1:1 with Ali Staff tomorrow at 3pm for 45 minutes',
                        scheduled_at=self.tomorrow_3pm.isoformat(), duration_minutes=45)
        self.assertEqual(data['action'], 'scheduled', data['reply'])
        self.assertEqual(HRMeeting.objects.get().duration_minutes, 45)

    def test_an_unstated_length_is_asked_not_assumed(self):
        # It used to become a silent 30 minutes.
        data = self.ask('Schedule a 1:1 with Ali Staff tomorrow at 3pm',
                        scheduled_at=self.tomorrow_3pm.isoformat())
        self.assertEqual(data['action'], 'needs_input')
        self.assertEqual(data['missing'], ['duration'])
        self.assertEqual(data['draft']['invitee_ids'], [self.ali.id])
        self.assertIsNotNone(data['draft']['proposed_time'])
        self.assertFalse(HRMeeting.objects.exists())

    def test_no_attendee_named_opens_the_form_with_everyone_invitable(self):
        # It used to stop with "Who should this meeting be with?".
        data = self.ask('Schedule a meeting tomorrow at 3pm for 30 minutes',
                        scheduled_at=self.tomorrow_3pm.isoformat())
        self.assertEqual(data['missing'], ['attendees'])
        offered = {u['id'] for u in data['options']['users']}
        self.assertIn(self.ali.id, offered)
        self.assertNotIn(self.member_emp.id, offered)     # no login: can't be invited
        self.assertNotIn(self.admin_emp.id, offered)      # the organiser

    def test_an_unknown_name_is_explained_in_the_form(self):
        data = self.ask('Schedule a meeting with Zed tomorrow at 3pm for 30 minutes',
                        scheduled_at=self.tomorrow_3pm.isoformat(), participant_names=['Zed'])
        self.assertEqual(data['action'], 'needs_input')
        self.assertIn('attendees', data['missing'])
        self.assertIn('Zed', data['note'])

    def test_someone_without_a_login_is_explained_not_preselected(self):
        data = self.ask('Schedule a meeting with Mo Member tomorrow at 3pm for 30 minutes',
                        scheduled_at=self.tomorrow_3pm.isoformat())
        self.assertEqual(data['missing'], ['attendees'])
        self.assertEqual(data['draft']['invitee_ids'], [])
        self.assertIn('Mo Member', data['note'])

    def test_several_gaps_are_asked_together(self):
        data = self.ask('Schedule a meeting')
        self.assertEqual(data['missing'], ['attendees', 'time', 'duration'])
        self.assertIn('who should attend, when it should be and how long it should last',
                      data['reply'])

    def test_a_bare_request_gets_the_form_even_if_the_model_says_clarify(self):
        # The model likes to answer an incomplete request in prose
        # ("Sure — who with, and when?"), which showed no form.
        data = self.ask('Schedule a meeting', intent='clarify', reply='Who with, and when?')
        self.assertEqual(data['action'], 'needs_input')
        self.assertEqual(data['missing'], ['attendees', 'time', 'duration'])

    def test_clarify_is_left_alone_when_it_is_not_a_new_meeting(self):
        for message in ('Reschedule my meeting with Ali Staff', 'What meetings do I have?'):
            with self.subTest(message=message):
                data = self.ask(message, intent='clarify', reply='Which one?')
                self.assertEqual((data['action'], data['reply']), ('clarify', 'Which one?'))

    def test_a_missing_time_offers_free_weekday_slots(self):
        data = self.ask('Schedule a 1:1 with Ali Staff for 30 minutes')
        self.assertEqual(data['missing'], ['time'])
        slots = data['options']['slots']
        self.assertTrue(slots)
        for slot in slots:
            self.assertLess(datetime.fromisoformat(slot['iso']).weekday(), 5)

    def test_the_reviewed_form_books_exactly_that(self):
        draft = self.ask('Schedule a 1:1 with Ali Staff tomorrow at 3pm',
                         scheduled_at=self.tomorrow_3pm.isoformat())['draft']
        draft.update(duration_minutes=60, title='Roadmap')
        when = (timezone.now() + timedelta(days=2)).replace(
            hour=11, minute=0, second=0, microsecond=0)
        data = self.confirm(draft, when)
        self.assertEqual(data['action'], 'scheduled', data['reply'])
        meeting = HRMeeting.objects.get()
        self.assertEqual((meeting.title, meeting.duration_minutes, meeting.scheduled_at),
                         ('Roadmap', 60, when))
        self.assertEqual(list(meeting.participants.all()), [self.ali])

    def test_a_form_sent_back_with_nobody_on_it_is_not_booked(self):
        draft = self.ask('Schedule a meeting')['draft']
        data = self.confirm(draft, timezone.now() + timedelta(days=2))
        self.assertEqual(data['action'], 'needs_input')
        self.assertEqual(data['missing'], ['attendees'])
        self.assertFalse(HRMeeting.objects.exists())

    def test_three_pm_is_the_users_three_pm(self):
        # The model is told the user's zone and answers in wall-clock time
        # there. It used to be told only UTC, so a Karachi user's 3 PM was
        # booked at 15:00 UTC — 8 PM for them.
        karachi = ZoneInfo('Asia/Karachi')                 # UTC+5, no DST
        day = (timezone.now().astimezone(karachi) + timedelta(days=1)).date()
        data = self.ask('Schedule a 1:1 with Ali Staff tomorrow at 3pm for 30 minutes',
                        tz='Asia/Karachi', scheduled_at=f'{day.isoformat()}T15:00:00')
        self.assertEqual(data['action'], 'scheduled', data['reply'])
        booked = HRMeeting.objects.get().scheduled_at.astimezone(dt_timezone.utc)
        self.assertEqual((booked.date(), booked.hour), (day, 10))

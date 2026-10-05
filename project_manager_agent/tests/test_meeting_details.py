"""The meeting scheduler asks for who / when / how long instead of guessing.

`process` is driven with a stubbed parser, so these run without a model: what
is under test is what the agent does with a parse, not the parse itself.
"""

from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.test import SimpleTestCase
from django.utils import timezone

from project_manager_agent.ai_agents.meeting_scheduler_agent import MeetingSchedulerAgent

from .base import PMTestCase


def parsed(**extra):
    """A successful parse, overridable per test."""
    base = {
        'is_meeting_request': True,
        'invitees': [],
        'users_not_found': [],
        'proposed_time': None,
        'duration_minutes': 30,       # the model always fills this in
        'recurrence': 'none',
        'recurrence_end_date': None,
        'title': None,
        'description': '',
        'agenda': [],
        'parse_error': None,
    }
    base.update(extra)
    return base


class DurationMentionedTests(SimpleTestCase):
    agent = MeetingSchedulerAgent()

    def test_lengths_of_time_count(self):
        for text in ('for 30 min', 'a 45-minute call', '1.5 hours', 'for 2h', '90 mins',
                     'half an hour', 'an hour with ali', 'two hours', 'hour-long review',
                     'quarter of an hour'):
            with self.subTest(text=text):
                self.assertTrue(self.agent._duration_mentioned(text))

    def test_clock_times_do_not(self):
        for text in ('meet ali at 3pm', 'tomorrow 10:30', 'at 9 am on Friday',
                     'schedule a meeting with sara', '3 PM Monday'):
            with self.subTest(text=text):
                self.assertFalse(self.agent._duration_mentioned(text))


class MissingDetailsTests(PMTestCase):

    def setUp(self):
        super().setUp()
        self.agent = MeetingSchedulerAgent()
        self.agent.timezone_name = 'UTC'
        self.users = [
            {'id': self.pm.id, 'full_name': 'Pat Tester', 'email': 'pat@test.local',
             'role': 'project_manager', 'username': 'pat'},
            {'id': self.dev.id, 'full_name': 'Dev Tester', 'email': 'dev@test.local',
             'role': 'team_member', 'username': 'dev'},
        ]
        self.later = (timezone.now() + timedelta(days=2)).replace(
            hour=15, minute=0, second=0, microsecond=0)

    def run_agent(self, message, **parse):
        with mock.patch.object(MeetingSchedulerAgent, 'parse_meeting_request',
                               return_value=parsed(**parse)):
            return self.agent.process(message, self.users, timezone.now().isoformat(),
                                      organizer_id=self.dash.id)

    def test_a_complete_request_is_still_reviewed_before_booking(self):
        # It used to book (and email the invitees) straight away.
        result = self.run_agent('schedule a meeting with Pat on Friday at 3pm for 45 minutes',
                                proposed_time=self.later.isoformat(), duration_minutes=45)
        self.assertEqual((result['action'], result['missing']), ('needs_input', []))
        self.assertIn('nobody is invited until you do', result['response'])
        booked = self.agent.schedule_from_pending(result['draft'], result['draft']['proposed_time'])
        self.assertEqual((booked['action'], booked['data']['duration_minutes']), ('schedule', 45))

    def test_an_unstated_length_is_asked_not_assumed(self):
        # It used to become a silent 30 minutes.
        result = self.run_agent('schedule a meeting with Pat on Friday at 3pm',
                                proposed_time=self.later.isoformat())
        self.assertEqual(result['action'], 'needs_input')
        self.assertEqual(result['missing'], ['duration'])
        self.assertEqual(result['draft']['duration_minutes'], 30)   # pre-filled, not decided
        self.assertEqual(result['draft']['invitee_ids'], [self.pm.id])

    def test_no_attendee_named_opens_the_form_with_everyone_to_choose_from(self):
        # It used to stop with "I couldn't find that user", before even
        # asking the model whether this was a meeting request.
        result = self.run_agent('schedule a meeting tomorrow at 3pm for 30 min',
                                proposed_time=self.later.isoformat())
        self.assertEqual(result['action'], 'needs_input')
        self.assertEqual(result['missing'], ['attendees'])
        self.assertEqual({u['id'] for u in result['options']['users']}, {self.pm.id, self.dev.id})

    def test_an_unknown_name_is_explained_in_the_form(self):
        result = self.run_agent('schedule a meeting with Zed tomorrow at 3pm for 30 min',
                                proposed_time=self.later.isoformat(), users_not_found=['Zed'])
        self.assertIn('attendees', result['missing'])
        self.assertIn('Zed', result['note'])

    def test_several_gaps_are_asked_together(self):
        result = self.run_agent('schedule a meeting')
        self.assertEqual(result['missing'], ['attendees', 'time', 'duration'])
        self.assertIn('who should attend, when it should be and how long it should last',
                      result['response'])

    def test_a_missing_time_offers_free_slots_as_exact_instants(self):
        result = self.run_agent('schedule a meeting with Pat for 30 minutes')
        self.assertEqual(result['missing'], ['time'])
        slots = result['options']['slots']
        self.assertTrue(slots)
        for slot in slots:
            datetime.fromisoformat(slot['iso'])      # a real instant, not prose

    def test_a_template_supplies_its_own_length(self):
        # The parse says 30 because the model always does; the standup
        # template's 15 used to lose to that default.
        result = self.run_agent('set up a standup with Pat tomorrow at 9',
                                proposed_time=self.later.isoformat())
        self.assertEqual(result['missing'], [])
        self.assertEqual(result['draft']['duration_minutes'], 15)

    def test_a_stated_length_beats_the_template(self):
        result = self.run_agent('set up a 45 minute standup with Pat tomorrow at 9',
                                proposed_time=self.later.isoformat(), duration_minutes=45)
        self.assertEqual(result['draft']['duration_minutes'], 45)

    def test_a_length_chosen_in_the_form_beats_the_template(self):
        draft = self.run_agent('set up a standup with Pat')['draft']
        self.assertEqual(draft['duration_minutes'], 15)          # pre-filled from the template
        draft['duration_minutes'] = 45                           # the user changes it
        result = self.agent.schedule_from_pending(draft, self.later.isoformat())
        self.assertEqual(result['data']['duration_minutes'], 45)

    def test_something_that_is_not_a_meeting_request_is_not_a_form(self):
        result = self.run_agent('hello there', is_meeting_request=False)
        self.assertEqual(result['action'], 'not_meeting_request')

    def test_the_reviewed_draft_books_exactly_that(self):
        draft = self.run_agent('schedule a meeting with Pat',)['draft']
        draft.update(duration_minutes=60, title='Roadmap')
        result = self.agent.schedule_from_pending(draft, self.later.isoformat())
        self.assertEqual(result['action'], 'schedule')
        self.assertEqual((result['data']['title'], result['data']['duration_minutes']),
                         ('Roadmap', 60))


class OrganiserTimezoneTests(PMTestCase):
    """"3 PM" is the organiser's 3 PM, not UTC's."""

    def setUp(self):
        super().setUp()
        self.agent = MeetingSchedulerAgent()
        self.agent.timezone_name = 'Asia/Karachi'     # UTC+5, no DST
        self.users = [{'id': self.pm.id, 'full_name': 'Pat Tester', 'email': 'pat@test.local',
                       'role': 'project_manager', 'username': 'pat'}]

    def test_a_naive_time_from_the_model_is_read_in_the_organisers_zone(self):
        day = (timezone.now() + timedelta(days=3)).date()
        naive = f'{day.isoformat()}T15:00:00'
        with mock.patch.object(MeetingSchedulerAgent, 'parse_meeting_request',
                               return_value=parsed(proposed_time=naive, duration_minutes=30)):
            result = self.agent.process('meet Pat at 3pm for 30 min', self.users,
                                        timezone.now().isoformat(), organizer_id=self.dash.id)
        booked = datetime.fromisoformat(result['draft']['proposed_time'])
        # It must carry its offset out of the agent. A naive value is what the
        # view used to read as UTC — and asserting on a naive value would be
        # meaningless anyway: `.astimezone()` then assumes whatever zone the
        # test machine is in, which can make the bug look fixed.
        self.assertIsNotNone(booked.tzinfo, 'proposed_time left the agent without an offset')
        # 15:00 in Karachi is 10:00 UTC. It used to be booked at 15:00 UTC.
        self.assertEqual(booked.astimezone(dt_timezone.utc).hour, 10)

    def test_an_explicit_offset_is_left_alone(self):
        self.assertEqual(self.agent._aware_iso('2026-10-10T10:00:00+00:00'),
                         '2026-10-10T10:00:00+00:00')

    def test_the_prompt_names_the_organisers_zone(self):
        with mock.patch.object(MeetingSchedulerAgent, '_call_llm', return_value='{}') as call:
            self.agent.parse_meeting_request('meet Pat at 3pm', self.users,
                                             timezone.now().isoformat())
        prompt = call.call_args.args[0] if call.call_args.args else call.call_args.kwargs['prompt']
        self.assertIn('Asia/Karachi', prompt)
        self.assertIn('+05:00', prompt)

    def test_the_confirmation_says_the_time_on_the_organisers_clock(self):
        # A time confirmed from the review form arrives in UTC; 05:00 UTC is
        # 10:00 in Karachi. The message used to say 05:00.
        text = self.agent.generate_response('scheduled', {
            'proposed_time': '2026-10-06T05:00:00Z', 'title': 'Sync', 'invitee_names': ['Pat Tester']})
        self.assertIn('**When:** Tuesday, October 06, 2026 at 10:00 AM (Asia/Karachi, UTC+05:00)', text)


class RescheduleReviewTests(PMTestCase):
    """Moving a meeting emails everyone invited; it used to happen the moment
    "reschedule my meeting with Pat" was typed, on whichever meeting with Pat
    was newest. Now the move is shown first and made only once confirmed."""

    def setUp(self):
        super().setUp()
        from project_manager_agent.models import MeetingParticipant, ScheduledMeeting
        self.old = (timezone.now() + timedelta(days=2)).replace(microsecond=0)
        self.new = self.old + timedelta(days=1)
        self.meeting = ScheduledMeeting.objects.create(organizer=self.dash, invitee=self.pm,
                                                       title='Planning', proposed_time=self.old)
        MeetingParticipant.objects.create(meeting=self.meeting, user=self.pm, status='accepted')

    def send(self, data, actor=None):
        from api.views import pm_agent
        agent_says = {'action': 'reschedule', 'data': {'invitee_ids': [self.pm.id],
                                                       'invitee_names': ['Pat Tester'],
                                                       'new_time': self.new.isoformat()}}
        with mock.patch.object(MeetingSchedulerAgent, 'process', return_value=agent_says), \
                mock.patch('api.views.pm_agent._send_meeting_email') as email:
            code, body = self.call(pm_agent.meeting_schedule, actor or self.dash, data)
        self.assertEqual(code, 200, body)
        return body['data'], email

    def test_the_move_is_shown_not_made(self):
        data, email = self.send({'message': 'reschedule my meeting with Pat to Friday'})
        self.assertEqual(data['action'], 'reschedule_review')
        self.assertEqual((data['reschedule']['meeting_id'], data['reschedule']['participants']),
                         (self.meeting.id, ['Pat Tester']))
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.proposed_time, self.old)
        email.assert_not_called()

    def test_confirming_moves_that_meeting_and_tells_everyone(self):
        data, email = self.send({'message': 'Move it.', 'confirm_reschedule': {
            'meeting_id': self.meeting.id, 'new_time': self.new.isoformat()}})
        self.assertEqual(data['action'], 'rescheduled', data)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.proposed_time, self.new)
        email.assert_called_once()

    def test_only_a_meeting_you_organise_can_be_moved(self):
        data, _ = self.send({'message': 'Move it.', 'confirm_reschedule': {
            'meeting_id': self.meeting.id, 'new_time': self.new.isoformat()}}, actor=self.dash_colleague)
        self.assertEqual(data['action'], 'not_found')
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.proposed_time, self.old)

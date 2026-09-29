"""The meeting scheduler's date picker, answered without a second model call.

A request with no time ("schedule a meeting with ali for tomorrow") comes back
as `needs_time` with a `pending_intent`. The picker used to rewrite the answer
as a sentence and send it through the model again; that sentence named two
calendar days (local and UTC) and the model routinely failed to turn it into
JSON, so the user was told their request was not understood.

These tests pin the replacement: the picker's answer is finished from the data
already agreed, the model is never consulted, and the invitees are still held
to the organiser's company.
"""

from datetime import timedelta
from unittest import mock

from django.utils import timezone

from api.views import pm_agent
from project_manager_agent.ai_agents.meeting_scheduler_agent import MeetingSchedulerAgent
from project_manager_agent.models import ScheduledMeeting

from .base import PMTestCase


def _no_model(*args, **kwargs):
    raise AssertionError('the picker path must not call the model')


class ScheduleFromPendingTests(PMTestCase):
    """`MeetingSchedulerAgent.schedule_from_pending`, in isolation."""

    def setUp(self):
        super().setUp()
        self.agent = MeetingSchedulerAgent()
        self.when = (timezone.now() + timedelta(days=2)).replace(microsecond=0)
        self.pending = {
            'invitee_ids': [self.pm.id],
            'invitee_names': ['Pat Tester'],
            'duration_minutes': 45,
            'title': None,
            'description': '',
            'agenda': ['roadmap'],
        }

    def test_it_builds_a_schedule_action_from_the_agreed_values(self):
        result = self.agent.schedule_from_pending(self.pending, self.when.isoformat())
        self.assertEqual(result['action'], 'schedule')
        data = result['data']
        self.assertEqual(data['invitees'], [{'id': self.pm.id, 'name': 'Pat Tester'}])
        self.assertEqual(data['duration_minutes'], 45)
        self.assertEqual(data['title'], 'Meeting with Pat Tester')
        self.assertEqual(data['agenda'], [{'item': 'roadmap', 'done': False}])

    def test_the_time_is_taken_exactly_as_picked(self):
        # The picker sends UTC with a Z; it must survive as the same instant.
        picked = self.when.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        result = self.agent.schedule_from_pending(self.pending, picked)
        from datetime import datetime
        got = datetime.fromisoformat(result['data']['proposed_time'])
        self.assertEqual(got, self.when)

    def test_it_never_consults_the_model(self):
        with mock.patch.object(MeetingSchedulerAgent, '_call_llm', side_effect=_no_model):
            result = self.agent.schedule_from_pending(self.pending, self.when.isoformat())
        self.assertEqual(result['action'], 'schedule')

    def test_recurrence_survives_the_round_trip(self):
        self.pending.update(recurrence='weekly', recurrence_end_date='2027-01-31')
        data = self.agent.schedule_from_pending(self.pending, self.when.isoformat())['data']
        self.assertEqual(data['recurrence'], 'weekly')
        self.assertEqual(data['recurrence_end_date'], '2027-01-31')

    def test_a_past_time_is_refused(self):
        past = (timezone.now() - timedelta(hours=1)).isoformat()
        self.assertEqual(self.agent.schedule_from_pending(self.pending, past)['action'], 'past_time')

    def test_an_unreadable_time_is_refused_plainly(self):
        for bad in ('', 'tomorrow', None, '31/13/2026'):
            with self.subTest(value=bad):
                self.assertEqual(
                    self.agent.schedule_from_pending(self.pending, bad)['action'], 'error')

    def test_no_invitees_is_refused(self):
        self.pending.update(invitee_ids=[], invitee_names=[])
        result = self.agent.schedule_from_pending(self.pending, self.when.isoformat())
        self.assertEqual(result['action'], 'error')


class MeetingSchedulePickerEndpointTests(PMTestCase):
    """The same path through `meeting_schedule`, including the create."""

    def setUp(self):
        super().setUp()
        self.when = (timezone.now() + timedelta(days=3)).replace(
            hour=10, minute=0, second=0, microsecond=0)

    def post(self, invitee_id, name='Pat Tester'):
        with mock.patch.object(MeetingSchedulerAgent, 'process', side_effect=_no_model), \
             mock.patch.object(MeetingSchedulerAgent, '_call_llm', side_effect=_no_model):
            return self.call(pm_agent.meeting_schedule, self.dash, {
                # What the chat log shows; deliberately the kind of sentence
                # that used to be sent to the model and fail.
                'message': 'Schedule the meeting with Pat on Wed, 30 Sept 2026, 0:03 for 45 minutes.',
                'pending_intent': {
                    'invitee_ids': [invitee_id],
                    'invitee_names': [name],
                    'duration_minutes': 45,
                },
                'proposed_time': self.when.isoformat(),
            })

    def test_the_meeting_is_created_at_the_picked_time(self):
        code, body = self.post(self.pm.id)
        self.assertEqual(code, 200, body)
        meeting = ScheduledMeeting.objects.get(invitee=self.pm)
        self.assertEqual(meeting.proposed_time, self.when)
        self.assertEqual(meeting.duration_minutes, 45)

    def test_an_invitee_from_another_company_is_not_invited(self):
        # The ids come from the client, so the view must still hold them to
        # the organiser's company.
        self.post(self.rival_pm.id, name='Rob Tester')
        self.assertFalse(ScheduledMeeting.objects.filter(invitee=self.rival_pm).exists())

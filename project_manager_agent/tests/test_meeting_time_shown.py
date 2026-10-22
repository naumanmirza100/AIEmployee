"""A meeting's time, written for people, is in the meeting's own zone.

Times are kept in UTC, and the invitation, the reply notices and the move and
cancel notices wrote them out as kept: a 10:00 kickoff in Lahore reached the
invitee as "05:00 AM".
"""

from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock
from zoneinfo import ZoneInfo

from django.utils import timezone

from api.views import notification as meeting_views
from api.views import pm_agent
from core.models import Notification
from core.scheduling import when_text
from project_manager_agent.ai_agents.meeting_scheduler_agent import MeetingSchedulerAgent
from project_manager_agent.models import MeetingParticipant, PMNotification, ScheduledMeeting

from .base import PMTestCase

LAHORE = 'Asia/Karachi'


def _no_model(*args, **kwargs):
    raise AssertionError('this path must not call the model')


class WhenTextTests(PMTestCase):

    def test_it_is_written_in_the_zone_given_and_names_it(self):
        five_utc = datetime(2026, 10, 29, 5, 0, tzinfo=dt_timezone.utc)
        self.assertEqual(when_text(five_utc, LAHORE), 'Thursday, October 29, 2026 at 10:00 AM Asia/Karachi')

    def test_no_time_and_no_zone(self):
        self.assertEqual(when_text(None, LAHORE), 'TBD')
        self.assertTrue(when_text(datetime(2026, 10, 29, 5, 0, tzinfo=dt_timezone.utc), '').endswith('05:00 AM UTC'))


class InvitationTimeTests(PMTestCase):

    def setUp(self):
        super().setUp()
        day = timezone.now().astimezone(ZoneInfo(LAHORE)) + timedelta(days=3)
        self.local = day.replace(hour=10, minute=0, second=0, microsecond=0)

    def book(self):
        with mock.patch.object(MeetingSchedulerAgent, 'process', side_effect=_no_model), \
             mock.patch.object(MeetingSchedulerAgent, '_call_llm', side_effect=_no_model):
            code, body = self.call(pm_agent.meeting_schedule, self.dash, {
                'message': 'Kickoff with Pat',
                'timezone': LAHORE,
                'pending_intent': {'invitee_ids': [self.pm.id], 'invitee_names': ['Pat Tester'],
                                   'duration_minutes': 45, 'title': 'Kickoff'},
                'proposed_time': self.local.astimezone(dt_timezone.utc).isoformat(),
            })
        self.assertEqual(code, 200, body)
        return ScheduledMeeting.objects.get(invitee=self.pm)

    def test_the_invitee_reads_the_time_the_organiser_chose(self):
        self.book()
        note = Notification.objects.get(user=self.pm, notification_type='meeting_request')
        self.assertIn('10:00 AM Asia/Karachi', note.message)
        self.assertNotIn('05:00 AM', note.message)

    def test_the_organiser_reads_it_in_the_meetings_zone_when_it_is_accepted(self):
        meeting = self.book()
        MeetingParticipant.objects.get_or_create(meeting=meeting, user=self.pm, defaults={'status': 'pending'})
        with self.captureOnCommitCallbacks(execute=True):
            code, body = self.call(meeting_views.meeting_respond, self.pm, {'action': 'accepted'},
                                   meeting_id=meeting.id)
        self.assertEqual(code, 200, body)
        note = PMNotification.objects.filter(company_user=self.dash, title__startswith='Meeting Accepted').get()
        self.assertIn('10:00 AM Asia/Karachi', note.message)

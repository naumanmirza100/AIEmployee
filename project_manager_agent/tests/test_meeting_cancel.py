"""A meeting everyone has accepted can still be cancelled by its organiser.

It could not: the server refused and the buttons were hidden, so that hour
stayed busy in every agent for everyone invited until it had passed. And a
withdrawal told only the first invitee; the others kept it in their calendars.
"""
from datetime import timedelta

from django.core import mail
from django.utils import timezone

from api.views import pm_agent as views
from core.models import Notification
from core.scheduling import ScheduleConflict, ensure_free
from project_manager_agent.models import MeetingParticipant, ScheduledMeeting

from .base import PMTestCase


class CancelAcceptedMeetingTests(PMTestCase):

    def setUp(self):
        super().setUp()
        for user in (self.pm, self.dev):
            user.email = f'{user.username}@test.local'
            user.save(update_fields=['email'])
        self.when = (timezone.now() + timedelta(days=3)).replace(minute=0, second=0, microsecond=0)
        self.meeting = self.accepted(self.when)

    def accepted(self, when, **fields):
        meeting = ScheduledMeeting.objects.create(organizer=self.dash, invitee=self.pm, title='Planning',
                                                  proposed_time=when, status='accepted', **fields)
        for user in (self.pm, self.dev):
            MeetingParticipant.objects.create(meeting=meeting, user=user, status='accepted')
        return meeting

    def respond(self, action, meeting=None, actor=None, **data):
        return self.call(views.meeting_respond, actor or self.dash,
                         {'meeting_id': (meeting or self.meeting).id, 'action': action, **data})

    def busy(self, user):
        try:
            ensure_free([user.id], self.when, 30, viewer_source='pm')
        except ScheduleConflict:
            return True
        return False

    def test_the_organiser_can_cancel_it_and_the_hour_is_free_again(self):
        self.assertTrue(self.busy(self.dev))
        code, body = self.respond('withdrawn', reason='Client moved the deadline')
        self.assertEqual(code, 200, body)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, 'withdrawn')
        self.assertFalse(self.busy(self.pm))
        self.assertFalse(self.busy(self.dev))

    def test_everyone_invited_is_told_not_only_the_first(self):
        self.respond('withdrawn', reason='Client moved the deadline')
        for user in (self.pm, self.dev):
            note = Notification.objects.get(user=user, type='meeting_withdrawn')
            self.assertEqual(note.title, 'Meeting Cancelled: Planning')
            self.assertIn('Dana Dash has cancelled', note.message)
            self.assertIn('Client moved the deadline', note.message)
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ['dev@test.local', 'pat@test.local'])
        self.assertTrue(all(m.subject == 'Meeting Cancelled: Planning' for m in mail.outbox))

    def test_an_accepted_meeting_still_cannot_be_changed_any_other_way(self):
        for action in ('accepted', 'rejected'):
            code, body = self.respond(action)
            self.assertEqual((code, body['message']), (400, 'Meeting is already accepted.'), action)
        later = (self.when + timedelta(days=1)).isoformat()
        code, _ = self.respond('counter_proposed', counter_time=later)
        self.assertEqual(code, 400)
        self.meeting.refresh_from_db()
        self.assertEqual((self.meeting.status, self.meeting.proposed_time), ('accepted', self.when))

    def test_one_that_has_taken_place_cannot_be_cancelled(self):
        past = self.accepted(timezone.now() - timedelta(hours=2))
        code, body = self.respond('withdrawn', meeting=past)
        self.assertEqual(code, 400)
        self.assertIn('already taken place', body['message'])
        past.refresh_from_db()
        self.assertEqual(past.status, 'accepted')

    def test_a_cancelled_meeting_is_finished(self):
        self.respond('withdrawn')
        code, body = self.respond('withdrawn')
        self.assertEqual((code, body['message']), (400, 'Meeting is already withdrawn.'))

    def test_only_its_organiser_can(self):
        for other in (self.dash_colleague, self.rival_dash):
            code, _ = self.respond('withdrawn', actor=other)
            self.assertEqual(code, 404)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, 'accepted')

    def test_withdrawing_a_request_nobody_answered_also_tells_everyone(self):
        pending = ScheduledMeeting.objects.create(organizer=self.dash, invitee=self.pm, title='Retro',
                                                  proposed_time=self.when + timedelta(days=1), status='pending')
        for user in (self.pm, self.dev):
            MeetingParticipant.objects.create(meeting=pending, user=user, status='pending')
        code, _ = self.respond('withdrawn', meeting=pending)
        self.assertEqual(code, 200)
        titles = set(Notification.objects.filter(type='meeting_withdrawn').values_list('title', flat=True))
        self.assertEqual(titles, {'Meeting Withdrawn: Retro'})
        self.assertEqual(Notification.objects.filter(type='meeting_withdrawn').count(), 2)

"""An employee's alert opens a page that exists.

Task alerts were stored with the link /tasks/<id>/ and meeting alerts with
/meetings/<id>/respond. Neither page exists, so clicking an alert went
nowhere. They now point at My Space: /me/tasks and /me/meetings.
"""
from datetime import timedelta

from django.utils import timezone

from api.views import pm_agent as views
from core.models import Notification, Task
from project_manager_agent.models import MeetingParticipant, ScheduledMeeting

from .base import PMTestCase

#: The My Space pages an employee can open (PaPerProjectFront/src/App.jsx).
MY_SPACE = {'/me/home', '/me/work', '/me/tasks', '/me/meetings', '/me/notifications', '/me/profile'}


class AlertLinkTests(PMTestCase):

    def meeting(self, status='pending', **fields):
        fields.setdefault('proposed_time', timezone.now() + timedelta(days=3))
        meeting = ScheduledMeeting.objects.create(organizer=self.dash, invitee=self.pm, title='Planning',
                                                  status=status, **fields)
        MeetingParticipant.objects.create(meeting=meeting, user=self.pm, status='pending')
        return meeting

    def links(self, user):
        return [n.action_url for n in Notification.objects.filter(user=user) if n.action_url]

    def test_a_task_given_to_someone_opens_their_task_list(self):
        Task.objects.create(project=self.project, title='Write the release notes', assignee=self.dev)
        note = Notification.objects.get(user=self.dev, type='task_assigned')
        self.assertEqual((note.link, note.action_url), ('/me/tasks', '/me/tasks'))

    def test_a_new_time_for_a_meeting_opens_their_meetings(self):
        meeting = self.meeting()
        later = (timezone.now() + timedelta(days=5)).isoformat()
        code, body = self.call(views.meeting_respond, self.dash,
                               {'meeting_id': meeting.id, 'action': 'counter_proposed', 'counter_time': later})
        self.assertEqual(code, 200, body)
        self.assertEqual(self.links(self.pm), ['/me/meetings'])

    def test_no_code_stores_the_two_pages_that_do_not_exist(self):
        # The reminder job cannot run on the test database, so its link is
        # checked where it is written.
        from pathlib import Path
        from django.conf import settings
        for name in ('api/views/pm_agent.py', 'project_manager_agent/tasks.py', 'core/signals.py'):
            source = (Path(settings.BASE_DIR) / name).read_text(encoding='utf-8')
            self.assertNotIn("/respond'", source, name)
            self.assertNotIn('"/tasks/{', source, name)

    def test_every_link_stored_is_a_my_space_page(self):
        Task.objects.create(project=self.project, title='Write the release notes', assignee=self.dev)
        meeting = self.meeting()
        self.call(views.meeting_respond, self.dash, {'meeting_id': meeting.id, 'action': 'counter_proposed',
                                                     'counter_time': (timezone.now() + timedelta(days=5)).isoformat()})
        stored = {n.action_url for n in Notification.objects.exclude(action_url__isnull=True).exclude(action_url='')}
        self.assertTrue(stored)
        self.assertLessEqual(stored, MY_SPACE)

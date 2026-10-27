"""A Project Manager meeting gets a link to join once everyone invited has accepted, and everyone is told to join
five minutes early; the reminder five minutes before carries the link again.

Asked for on 25 Oct 2026, after the executive scheduler's links: PM meetings agreed a time and gave nowhere to meet.
"""
from datetime import timedelta

from django.core import mail
from django.utils import timezone

from api.views import notification as meeting_views
from api.views import pm_agent
from core.models import Notification
from project_manager_agent import tasks
from project_manager_agent.models import MeetingParticipant, PMNotification, ScheduledMeeting

from .base import PMTestCase


class MeetingCase(PMTestCase):

    def setUp(self):
        super().setUp()
        self.meeting = ScheduledMeeting.objects.create(
            organizer=self.dash, invitee=self.dev, title='Kickoff', duration_minutes=30, timezone_name='Asia/Karachi',
            proposed_time=timezone.now() + timedelta(days=3))
        for user in (self.dev, self.pm):
            MeetingParticipant.objects.create(meeting=self.meeting, user=user, status='pending')

    def accept(self, user):
        code, body = self.call(meeting_views.meeting_respond, user, {'action': 'accepted'}, meeting_id=self.meeting.id)
        self.assertEqual(code, 200, body)
        self.meeting.refresh_from_db()

    def confirmations(self):
        return Notification.objects.filter(type='meeting_confirmed')


class MeetingLinkTests(MeetingCase):

    def test_the_link_comes_when_the_last_person_accepts_and_everyone_is_told(self):
        self.accept(self.dev)
        self.assertEqual((self.meeting.status, self.meeting.meeting_link), ('partially_accepted', ''))
        self.assertFalse(self.confirmations().exists())
        self.accept(self.pm)
        link = self.meeting.meeting_link
        self.assertEqual(self.meeting.status, 'accepted')
        self.assertTrue(link.startswith('https://meet.jit.si/payperproject-'))
        told = {n.user_id: n.message for n in self.confirmations()}
        self.assertEqual(set(told), {self.dev.id, self.pm.id})
        self.assertIn(f'Join here: {link} — please join 5 minutes before the start.', told[self.dev.id])
        # The organiser hears it once: in the notice of the reply that completed the meeting.
        notices = PMNotification.objects.filter(company_user=self.dash).order_by('id')
        self.assertEqual([n.title for n in notices], ['Meeting Accepted: Kickoff'] * 2)
        self.assertNotIn('Join here', notices[0].message)
        self.assertTrue(notices[1].message.endswith(f'Everyone has accepted. Join here: {link} — '
                                                    'please join 5 minutes before the start.'))
        emails = [m for m in mail.outbox if m.subject == 'Meeting confirmed: Kickoff']
        self.assertEqual(sorted(m.to[0] for m in emails), ['dev@test.local', 'pat@test.local'])
        self.assertIn(link, emails[0].alternatives[0][0])

    def test_both_meeting_lists_show_the_link(self):
        self.accept(self.dev)
        self.accept(self.pm)
        self.assertEqual(pm_agent._serialize_meeting(self.meeting)['meeting_link'], self.meeting.meeting_link)
        [item] = meeting_views._pm_meeting_items(self.dev)
        self.assertEqual(item['meeting_link'], self.meeting.meeting_link)

    def test_a_meeting_accepted_again_keeps_its_link_and_says_so_again(self):
        self.accept(self.dev)
        self.accept(self.pm)
        link = self.meeting.meeting_link
        # Moved: everyone is asked again.
        self.meeting.participants.update(status='pending')
        self.meeting.update_overall_status()
        self.accept(self.dev)
        self.accept(self.pm)
        self.assertEqual(self.meeting.meeting_link, link)
        self.assertEqual(self.confirmations().count(), 4)

    def test_the_organiser_taking_a_suggested_time_makes_it_final(self):
        ScheduledMeeting.objects.filter(pk=self.meeting.pk).update(status='counter_proposed')
        code, body = self.call(pm_agent.meeting_respond, self.dash, {'meeting_id': self.meeting.id,
                                                                     'action': 'accepted'})
        self.assertEqual(code, 200, body)
        self.meeting.refresh_from_db()
        self.assertTrue(self.meeting.meeting_link)
        self.assertEqual(self.confirmations().count(), 2)

    def test_the_reminders_carry_the_link(self):
        self.accept(self.dev)
        self.accept(self.pm)
        link = self.meeting.meeting_link
        for minutes, said in ((5, f'Join now: {link}'), (15, f'Please join 5 minutes early: {link}')):
            ScheduledMeeting.objects.filter(pk=self.meeting.pk).update(
                proposed_time=timezone.now() + timedelta(minutes=minutes, seconds=20))
            tasks.send_meeting_reminders()
            reminder = Notification.objects.filter(user=self.dev, type='meeting_reminder').latest('id')
            self.assertTrue(reminder.message.endswith(said), reminder.message)

    def test_a_reminder_gives_the_real_minutes_left(self):
        # The job runs every 5 minutes, so the "15-minute" reminder can go out with 12 left.
        for minutes in (12, 58):
            ScheduledMeeting.objects.filter(pk=self.meeting.pk).update(
                proposed_time=timezone.now() + timedelta(minutes=minutes, seconds=20))
            tasks.send_meeting_reminders()
            reminder = Notification.objects.filter(user=self.dev, type='meeting_reminder').latest('id')
            self.assertIn(f'starts in {minutes} minutes (at ', reminder.message)

    def test_no_link_in_a_reminder_before_everyone_has_accepted(self):
        self.accept(self.dev)
        ScheduledMeeting.objects.filter(pk=self.meeting.pk).update(proposed_time=timezone.now() + timedelta(minutes=5))
        tasks.send_meeting_reminders()
        self.assertFalse(Notification.objects.filter(type='meeting_reminder').exists())


class WhoRepliedTests(MeetingCase):
    """Every reply in a meeting's history showed the first invitee's name (PM demo rehearsal, 25 Oct 2026)."""

    def test_each_reply_carries_its_person(self):
        self.accept(self.dev)
        self.accept(self.pm)
        names = [r['responder_name'] for r in pm_agent._serialize_meeting(self.meeting)['responses']]
        self.assertEqual(names, ['Dev Tester', 'Pat Tester'])
        [item] = meeting_views._pm_meeting_items(self.pm)
        self.assertEqual([r['responder_name'] for r in item['responses']], ['Dev Tester', 'Pat Tester'])

    def test_past_replies_are_given_their_person_from_the_answer_times(self):
        from importlib import import_module

        from django.apps import apps
        from project_manager_agent.models import MeetingResponse
        import time
        self.accept(self.dev)
        time.sleep(0.03)        # two answers inside one Windows clock tick (~15 ms) look simultaneous to the matcher
        self.accept(self.pm)
        MeetingResponse.objects.update(responder=None)     # as replies were kept before
        import_module('project_manager_agent.migrations.0020_meeting_response_responder').name_past_replies(apps, None)
        self.assertEqual(list(MeetingResponse.objects.order_by('id').values_list('responder_id', flat=True)),
                         [self.dev.id, self.pm.id])

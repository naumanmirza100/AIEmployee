"""An HR meeting gets a place to meet once everyone has accepted, and its reminders say so — as Project Manager's.

Asked for on 26 Oct 2026 ("if hr has meeting scheduler, than make it like that of pm too, you know with meeting
link, and reminder, and all"). HR had a link field nothing filled, told nobody when everyone had accepted, told an
owner booking as HR of no reply at all, and reminded people a day and 15 minutes before by email only — including
people who had declined, and meetings everyone had declined.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone

from api.views import hr_agent as views
from core.models import CompanyUser, Notification
from hr_agent.models import HRMeeting
from hr_agent.tasks import send_hr_meeting_reminders
from project_manager_agent.models import PMNotification

from .base import HRTestCase


class MeetingCase(HRTestCase):

    def setUp(self):
        super().setUp()
        self.ali = self.employee_with_login('ali', 'Ali Staff', self.company, self.admin)
        self.bea = self.employee_with_login('bea', 'Bea Staff', self.company, self.admin)
        self.when = (timezone.now() + timedelta(days=3)).replace(second=0, microsecond=0)

    def book(self, actor=None, **data):
        payload = {'title': 'Roadmap', 'scheduled_at': self.when.isoformat(), 'duration_minutes': 30,
                   'timezone_name': 'Asia/Karachi', 'participant_ids': [self.ali.id, self.bea.id], **data}
        with self.captureOnCommitCallbacks(execute=True):
            code, body = self.call(views.create_hr_meeting, actor or self.admin, payload)
        self.assertEqual(code, 201, body)
        Notification.objects.all().delete()
        PMNotification.objects.all().delete()
        mail.outbox.clear()
        return HRMeeting.objects.get(pk=body['data']['id'])

    def answer(self, meeting, employee, action='accepted', **data):
        with self.captureOnCommitCallbacks(execute=True):
            # A fresh login: the one the test made carries a profile cached before its company was set.
            login = get_user_model().objects.get(pk=employee.user_id)
            code, body = self.call(views.respond_hr_meeting_as_employee, login, {'action': action, **data},
                                   meeting_id=meeting.id)
        self.assertEqual(code, 200, body)
        meeting.refresh_from_db()
        return meeting

    def bell(self, employee, kind):
        return list(Notification.objects.filter(user=employee.user, type=kind).order_by('id'))


class MeetingLinkTests(MeetingCase):

    def test_no_link_until_everyone_has_accepted(self):
        m = self.answer(self.book(), self.ali)
        self.assertFalse(m.meeting_link)
        self.assertEqual(m.response_status, 'partially_accepted')
        m = self.answer(m, self.bea)
        self.assertEqual(m.response_status, 'accepted')
        self.assertTrue(m.meeting_link.startswith('https://meet.jit.si/payperproject-'), m.meeting_link)

    def test_every_attendee_is_told_with_the_link(self):
        m = self.answer(self.answer(self.book(), self.ali), self.bea)
        for person in (self.ali, self.bea):
            [notice] = self.bell(person, 'hr_meeting_confirmed')
            self.assertEqual(notice.title, 'Meeting confirmed: Roadmap')
            self.assertIn(m.meeting_link, notice.message)
            self.assertIn('please join 5 minutes before the start', notice.message)
            self.assertIn('Asia/Karachi', notice.message)
        confirmed = sorted(e.to[0] for e in mail.outbox if e.subject == 'Meeting confirmed: Roadmap')
        self.assertEqual(confirmed, ['ali@test.local', 'bea@test.local'])

    def test_whoever_booked_hears_each_reply_and_the_last_one_gives_the_link(self):
        m = self.answer(self.book(), self.ali)
        [first] = PMNotification.objects.filter(company_user=self.admin)
        self.assertEqual(first.title, 'Meeting accepted: Roadmap')
        self.assertIn('Ali Staff has accepted the meeting "Roadmap"', first.message)
        self.assertNotIn('Everyone has accepted', first.message)
        m = self.answer(m, self.bea)
        last = PMNotification.objects.filter(company_user=self.admin).latest('id')
        self.assertIn('Everyone has accepted.', last.message)
        self.assertIn(m.meeting_link, last.message)

    def test_an_owner_with_no_hr_record_hears_too(self):
        owner = self.login(self.company, 'olu@test.local', 'Olu Owner', 'owner')
        m = self.answer(self.book(actor=owner), self.ali, 'rejected', reason='On leave that day')
        [notice] = PMNotification.objects.filter(company_user=owner)
        self.assertEqual(notice.title, 'Meeting declined: Roadmap')
        self.assertIn('Reason: On leave that day', notice.message)
        self.assertEqual(m.booked_by, owner)

    def test_a_link_typed_in_is_kept(self):
        m = self.book(meeting_link='https://zoom.us/j/123')
        m = self.answer(self.answer(m, self.ali), self.bea)
        self.assertEqual(m.meeting_link, 'https://zoom.us/j/123')
        self.assertIn('https://zoom.us/j/123', self.bell(self.ali, 'hr_meeting_confirmed')[0].message)

    def test_hr_accepting_a_suggested_time_makes_it_final_once(self):
        m = self.answer(self.book(), self.ali)
        m = self.answer(m, self.bea, 'counter_proposed', counter_time=(self.when + timedelta(hours=2)).isoformat())
        with self.captureOnCommitCallbacks(execute=True):
            code, body = self.call(views.respond_hr_meeting, self.admin, {'action': 'accepted', 'as_role': 'organizer'},
                                   meeting_id=m.id)
        self.assertEqual(code, 200, body)
        m.refresh_from_db()
        self.assertEqual(m.response_status, 'accepted')
        self.assertTrue(m.meeting_link)
        # The confirmation tells them; a second "HR has accepted" notice would say the same thing again.
        self.assertEqual(len(self.bell(self.bea, 'hr_meeting_confirmed')), 1)
        self.assertEqual(self.bell(self.bea, 'hr_meeting_reply'), [])


class ReminderTests(MeetingCase):

    def due_in(self, minutes, accepted=True, **fields):
        m = self.book()
        if accepted:
            m = self.answer(self.answer(m, self.ali), self.bea)
        HRMeeting.objects.filter(pk=m.pk).update(scheduled_at=timezone.now() + timedelta(minutes=minutes), **fields)
        Notification.objects.all().delete()
        PMNotification.objects.all().delete()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            send_hr_meeting_reminders()
        return HRMeeting.objects.get(pk=m.pk)

    def reminders(self, employee):
        return [n.message for n in self.bell(employee, 'hr_meeting_reminder')]

    def test_a_reminder_gives_the_real_minutes_left_and_the_link(self):
        m = self.due_in(14)
        [text] = self.reminders(self.ali)
        self.assertIn('"Roadmap" starts in 14 minutes', text)
        self.assertIn(f'Please join 5 minutes early: {m.meeting_link}', text)
        self.assertIsNotNone(m.reminder_15m_sent_at)
        self.assertTrue(any(e.subject == 'Reminder: Roadmap starts in 14 minutes' for e in mail.outbox))
        self.assertTrue(PMNotification.objects.filter(company_user=self.admin, title='Meeting reminder: Roadmap'))

    def test_the_last_one_says_join_now(self):
        m = self.due_in(5)
        [text] = self.reminders(self.bea)
        self.assertIn('starts in 5 minutes', text)
        self.assertIn(f'Join now: {m.meeting_link}', text)

    def test_an_hour_before_too(self):
        self.due_in(61)
        [text] = self.reminders(self.ali)
        self.assertIn('starts in 61 minutes', text)

    def test_no_join_now_for_a_meeting_not_everyone_accepted(self):
        self.due_in(5, accepted=False)
        self.assertEqual(self.reminders(self.ali), [])

    def test_and_no_link_in_its_earlier_reminders(self):
        m = self.due_in(15, accepted=False)
        [text] = self.reminders(self.ali)
        self.assertNotIn('Join', text)
        self.assertFalse(m.meeting_link)

    def test_nobody_who_declined_is_reminded(self):
        m = self.answer(self.book(), self.ali, 'rejected')
        HRMeeting.objects.filter(pk=m.pk).update(scheduled_at=timezone.now() + timedelta(minutes=15))
        send_hr_meeting_reminders()
        self.assertEqual(self.reminders(self.ali), [])
        self.assertEqual(len(self.reminders(self.bea)), 1)

    def test_a_meeting_everyone_declined_is_not_reminded(self):
        m = self.answer(self.answer(self.book(), self.ali, 'rejected'), self.bea, 'rejected')
        self.assertEqual(m.response_status, 'rejected')
        HRMeeting.objects.filter(pk=m.pk).update(scheduled_at=timezone.now() + timedelta(minutes=15))
        send_hr_meeting_reminders()
        self.assertFalse(Notification.objects.filter(type='hr_meeting_reminder').exists())

    def test_each_reminder_once(self):
        self.due_in(14)
        send_hr_meeting_reminders()
        self.assertEqual(len(self.reminders(self.ali)), 1)

    def test_moving_the_meeting_makes_every_reminder_due_again(self):
        m = self.due_in(14)
        with self.captureOnCommitCallbacks(execute=True):
            code, body = self.call(views.update_hr_meeting, self.admin,
                                   {'scheduled_at': (timezone.now() + timedelta(days=2)).isoformat()},
                                   method='patch', meeting_id=m.id)
        self.assertEqual(code, 200, body)
        m.refresh_from_db()
        self.assertEqual([getattr(m, f) for f in HRMeeting.REMINDER_FIELDS], [None] * 4)

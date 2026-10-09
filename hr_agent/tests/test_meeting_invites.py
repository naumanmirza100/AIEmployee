"""HR tells the people it books.

Only Project Manager told the people it invited. HR blocked a person's
calendar the moment a meeting was saved and said nothing: no bell alert and no
invitation. They found out by opening My work, or from a reminder a day or a
quarter of an hour before. The Edit and Cancel buttons told nobody at all.
"""
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.utils import timezone

from api.views import hr_agent as views
from core.models import Notification
from hr_agent.models import HRMeeting
from hr_agent.workflow_engine import _step_schedule_meeting

from .base import HRTestCase


class HRInviteTests(HRTestCase):

    def setUp(self):
        super().setUp()
        self.ali = self.employee_with_login('ali', 'Ali Staff', self.company, self.admin)
        self.bea = self.employee_with_login('bea', 'Bea Staff', self.company, self.admin)
        self.when = (timezone.now() + timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)

    def told(self, employee):
        return [n.title for n in Notification.objects.filter(user=employee.user, type='hr_meeting').order_by('id')]

    def forget(self):
        Notification.objects.all().delete()
        mail.outbox.clear()

    def book(self, people=None, actor=None, **data):
        payload = {'title': 'Roadmap', 'scheduled_at': self.when.isoformat(), 'duration_minutes': 45,
                   'participant_ids': [e.id for e in (people or [self.ali, self.bea])], **data}
        with self.captureOnCommitCallbacks(execute=True):
            code, body = self.call(views.create_hr_meeting, actor or self.admin, payload)
        return code, body

    def booked(self, **kwargs):
        code, body = self.book(**kwargs)
        self.assertEqual(code, 201, body)
        self.forget()
        return HRMeeting.objects.get(pk=body['data']['id'])

    def edit(self, meeting, **data):
        with self.captureOnCommitCallbacks(execute=True):
            code, body = self.call(views.update_hr_meeting, self.admin, data, method='patch', meeting_id=meeting.id)
        self.assertEqual(code, 200, body)

    # ---- a new meeting ------------------------------------------------------------------

    def test_everyone_booked_is_told_in_their_bell_and_by_email(self):
        code, body = self.book()
        self.assertEqual(code, 201, body)
        [alert] = Notification.objects.filter(user=self.ali.user)
        self.assertEqual((alert.title, alert.action_url, alert.type),
                         ("You're invited: Roadmap", '/me/meetings', 'hr_meeting'))
        self.assertIn('HR booked you into "Roadmap"', alert.message)
        self.assertIn(f'{self.when:%A, %B %d, %Y} at 10:00 AM (UTC)', alert.message)
        self.assertIn('(45 min)', alert.message)
        self.assertIn('accept it or suggest another time', alert.message)
        self.assertEqual(self.told(self.bea), ["You're invited: Roadmap"])
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ['ali@test.local', 'bea@test.local'])
        self.assertEqual(mail.outbox[0].subject, "You're invited: Roadmap")

    def test_the_time_is_written_on_the_meetings_own_clock(self):
        self.book(timezone_name='Asia/Karachi')
        self.assertIn('3:00 PM (Asia/Karachi, UTC+05:00)', Notification.objects.filter(user=self.ali.user).get().message)

    def test_someone_named_as_organiser_is_told_too(self):
        self.book(people=[self.ali], organizer_id=self.bea.id)
        self.assertEqual(self.told(self.bea), ["You're invited: Roadmap"])

    def test_an_organiser_with_no_employee_login_has_no_bell_to_tell(self):
        # Dana works from a dashboard login only. Her stand-in user is nobody's My Space.
        self.book(people=[self.ali], organizer_id=self.admin_emp.id)
        self.assertFalse(Notification.objects.filter(user=self.admin_emp.user).exists())
        self.assertEqual(len(mail.outbox), 1)                        # Ali's, and no other

    def test_whoever_made_the_booking_is_not_told_about_it(self):
        # Kim has both logins, and books a meeting they organise from the dashboard.
        kim = self.employee_with_login('kim', 'Kim Both', self.company, self.admin)
        kim_login = self.login(self.company, 'kim@test.local', 'Kim Both', 'admin')
        self.book(people=[self.ali], organizer_id=kim.id, actor=kim_login)
        self.assertEqual(self.told(kim), [])
        self.assertEqual(self.told(self.ali), ["You're invited: Roadmap"])

    def test_a_booking_refused_for_a_clash_tells_nobody(self):
        self.booked(people=[self.ali])
        code, _ = self.book(people=[self.ali, self.bea], title='On top of it')
        self.assertEqual(code, 409)
        self.assertEqual((Notification.objects.count(), mail.outbox), (0, []))

    def test_nobody_in_another_company_hears(self):
        self.book()
        self.assertFalse(Notification.objects.filter(user=self.rival_emp.user).exists())

    # ---- the Edit dialog ----------------------------------------------------------------------

    def test_moving_it_tells_everyone_in_it_the_new_time(self):
        meeting = self.booked()
        self.edit(meeting, scheduled_at=(self.when + timedelta(hours=3)).isoformat())
        self.assertEqual(self.told(self.ali), ['Meeting moved: Roadmap'])
        self.assertEqual(self.told(self.bea), ['Meeting moved: Roadmap'])
        note = Notification.objects.filter(user=self.ali.user).get().message
        self.assertIn('HR moved "Roadmap". It is now', note)
        self.assertIn('1:00 PM', note)
        self.assertEqual(len(mail.outbox), 2)

    def test_a_longer_meeting_is_a_changed_one(self):
        meeting = self.booked()
        self.edit(meeting, duration_minutes=90)
        self.assertEqual(self.told(self.ali), ['Meeting moved: Roadmap'])
        self.assertIn('(90 min)', Notification.objects.filter(user=self.ali.user).get().message)

    def test_adding_someone_tells_only_them(self):
        meeting = self.booked(people=[self.ali])
        self.edit(meeting, participant_ids=[self.ali.id, self.bea.id])
        self.assertEqual((self.told(self.ali), self.told(self.bea)), ([], ["You're invited: Roadmap"]))

    def test_taking_someone_off_tells_only_them(self):
        meeting = self.booked()
        self.edit(meeting, participant_ids=[self.ali.id])
        self.assertEqual((self.told(self.ali), self.told(self.bea)), ([], ["You're no longer in: Roadmap"]))
        self.assertIn('HR took you off "Roadmap"', Notification.objects.filter(user=self.bea.user).get().message)

    def test_a_change_that_moves_nobody_tells_nobody(self):
        meeting = self.booked()
        self.edit(meeting, title='Roadmap review', notes='Bring the figures', location='Room 2',
                  scheduled_at=self.when.isoformat(), participant_ids=[self.ali.id, self.bea.id])
        self.assertEqual((Notification.objects.count(), mail.outbox), (0, []))

    def test_cancelling_from_the_edit_dialog_is_a_cancellation(self):
        meeting = self.booked()
        self.edit(meeting, status='cancelled')
        self.assertEqual(self.told(self.ali), ['Meeting cancelled: Roadmap'])

    def test_marking_it_completed_is_not(self):
        meeting = self.booked()
        self.edit(meeting, status='completed')
        self.assertEqual((Notification.objects.count(), mail.outbox), (0, []))

    # ---- the Cancel button --------------------------------------------------------------------

    def test_cancelling_tells_everyone_who_was_in_it_once(self):
        meeting = self.booked()
        with self.captureOnCommitCallbacks(execute=True):
            self.call(views.cancel_hr_meeting, self.admin, {'reason': 'Clash'}, meeting_id=meeting.id)
            self.call(views.cancel_hr_meeting, self.admin, {}, meeting_id=meeting.id)      # pressed twice
        self.assertEqual(self.told(self.ali), ['Meeting cancelled: Roadmap'])
        self.assertEqual(self.told(self.bea), ['Meeting cancelled: Roadmap'])
        note = Notification.objects.filter(user=self.ali.user).get().message
        self.assertIn('HR cancelled "Roadmap", which was', note)
        self.assertIn('10:00 AM', note)

    def test_someone_who_had_declined_is_not_told_it_is_off(self):
        meeting = self.booked()
        meeting.participant_rows.filter(employee=self.bea).update(status='rejected')
        with self.captureOnCommitCallbacks(execute=True):
            self.call(views.cancel_hr_meeting, self.admin, {}, meeting_id=meeting.id)
        self.assertEqual((self.told(self.ali), self.told(self.bea)), (['Meeting cancelled: Roadmap'], []))

    # ---- the other ways HR books ----------------------------------------------------------------

    def test_a_meeting_booked_from_the_chat_is_announced(self):
        draft = {'title': 'Chat 1:1', 'invitee_ids': [self.ali.id], 'duration_minutes': 30,
                 'meeting_type': 'one_on_one'}
        with mock.patch('api.views.hr_agent.HRAgent._call_llm',
                        side_effect=AssertionError('confirming must not call the model')):
            with self.captureOnCommitCallbacks(execute=True):
                code, body = self.call(views.hr_meeting_schedule, self.admin, {
                    'message': 'Book it.', 'pending_intent': draft,
                    'proposed_time': self.when.isoformat(), 'timezone': 'UTC'})
        self.assertEqual(body['data']['action'], 'scheduled', body)
        self.assertEqual(self.told(self.ali), ["You're invited: Chat 1:1"])

    def test_a_meeting_booked_by_a_workflow_is_announced(self):
        with self.captureOnCommitCallbacks(execute=True):
            ok, result, _ = _step_schedule_meeting(
                {'scheduled_at': self.when.isoformat(), 'title': 'Orientation'},
                {'company_id': self.company.id, 'employee_id': self.ali.id}, False)
        self.assertTrue(ok, result)
        self.assertEqual(self.told(self.ali), ["You're invited: Orientation"])

    def test_a_workflow_run_that_only_previews_books_and_tells_nobody(self):
        _step_schedule_meeting({'scheduled_at': self.when.isoformat()},
                               {'company_id': self.company.id, 'employee_id': self.ali.id}, True)
        self.assertEqual(Notification.objects.count(), 0)

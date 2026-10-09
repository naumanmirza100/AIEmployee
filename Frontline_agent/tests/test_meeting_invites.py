"""Frontline tells the people it books.

A Frontline meeting blocked its attendees' calendars the moment it was saved
and told them nothing. The first they heard was a reminder: within minutes for
a meeting less than a day away, otherwise the day before. A change, a
cancellation or a deletion told nobody.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.utils import timezone

from api.views import frontline_agent as views
from core.models import Notification, UserProfile
from Frontline_agent.models import FrontlineMeeting

from .base import FrontlineTestCase


class FrontlineInviteTests(FrontlineTestCase):

    def setUp(self):
        super().setUp()
        self.ali = self.employee('ali')
        self.bea = self.employee('bea')
        self.when = (timezone.now() + timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)

    def employee(self, username, company=None):
        user = User.objects.create_user(username, email=f'{username}@test.local', password='x')
        UserProfile.objects.update_or_create(user=user, defaults={
            'company': company or self.company, 'created_by_company_user': self.admin, 'role': 'team_member'})
        return user

    def told(self, user):
        return [n.title for n in Notification.objects.filter(user=user, type='frontline_meeting').order_by('id')]

    def forget(self):
        Notification.objects.all().delete()
        mail.outbox.clear()

    def book(self, people=None, actor=None, **data):
        payload = {'title': 'Customer call', 'scheduled_at': self.when.isoformat(), 'duration_minutes': 30,
                   'participant_user_ids': [u.id for u in (people or [self.ali, self.bea])], **data}
        with self.captureOnCommitCallbacks(execute=True):
            return self.call(views.create_meeting, actor or self.admin, payload)

    def booked(self, **kwargs):
        code, body = self.book(**kwargs)
        self.assertEqual(code, 201, body)
        self.forget()
        return FrontlineMeeting.objects.get(pk=body['data']['id'])

    def edit(self, meeting, **data):
        with self.captureOnCommitCallbacks(execute=True):
            code, body = self.call(views.update_meeting, self.admin, data, method='patch', meeting_id=meeting.id)
        self.assertEqual(code, 200, body)

    # ---- a new meeting ------------------------------------------------------------------

    def test_everyone_booked_is_told_in_their_bell_and_by_email(self):
        code, body = self.book()
        self.assertEqual(code, 201, body)
        [alert] = Notification.objects.filter(user=self.ali)
        self.assertEqual((alert.title, alert.action_url, alert.type),
                         ("You're invited: Customer call", '/me/meetings', 'frontline_meeting'))
        self.assertIn('Frontline booked you into "Customer call"', alert.message)
        self.assertIn('10:00 AM', alert.message)
        self.assertIn('(30 min)', alert.message)
        self.assertIn('It is on your Meetings page.', alert.message)         # Frontline has no accept step
        self.assertEqual(self.told(self.bea), ["You're invited: Customer call"])
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ['ali@test.local', 'bea@test.local'])

    def test_an_organiser_who_is_an_employee_is_not_told_about_their_own_booking(self):
        # Kim signs in both ways with the same address, so the meeting is theirs as an employee.
        kim = self.employee('kim')
        kim_login = self.dashboard_login(self.company, 'kim@test.local', 'Kim Both', 'company_user')
        code, body = self.book(people=[self.ali], actor=kim_login)
        self.assertEqual(code, 201, body)
        self.assertEqual(FrontlineMeeting.objects.get().organizer, kim)
        self.assertEqual((self.told(kim), self.told(self.ali)), ([], ["You're invited: Customer call"]))

    def test_a_booking_refused_for_a_clash_tells_nobody(self):
        self.booked(people=[self.ali])
        code, _ = self.book(people=[self.ali, self.bea], title='On top of it')
        self.assertEqual(code, 409)
        self.assertEqual((Notification.objects.count(), mail.outbox), (0, []))

    # ---- changing it ----------------------------------------------------------------------------

    def test_moving_it_tells_everyone_the_new_time(self):
        meeting = self.booked()
        self.edit(meeting, scheduled_at=(self.when + timedelta(hours=3)).isoformat())
        self.assertEqual((self.told(self.ali), self.told(self.bea)),
                         (['Meeting moved: Customer call'], ['Meeting moved: Customer call']))
        self.assertIn('1:00 PM', Notification.objects.get(user=self.ali).message)

    def test_adding_and_removing_tell_only_the_people_concerned(self):
        meeting = self.booked(people=[self.ali])
        self.edit(meeting, participant_user_ids=[self.bea.id])
        self.assertEqual((self.told(self.ali), self.told(self.bea)),
                         (["You're no longer in: Customer call"], ["You're invited: Customer call"]))

    def test_a_change_that_moves_nobody_tells_nobody(self):
        meeting = self.booked()
        self.edit(meeting, title='Customer call (Acme)', notes='Agenda attached', location='Room 2',
                  scheduled_at=self.when.isoformat())
        self.assertEqual((Notification.objects.count(), mail.outbox), (0, []))

    def test_marking_it_cancelled_tells_everyone_it_is_off(self):
        meeting = self.booked()
        self.edit(meeting, status='cancelled')
        self.assertEqual(self.told(self.ali), ['Meeting cancelled: Customer call'])
        self.assertIn('Frontline cancelled "Customer call", which was', Notification.objects.get(user=self.ali).message)

    def test_marking_it_completed_is_not_a_cancellation(self):
        meeting = self.booked()
        self.edit(meeting, status='completed')
        self.assertEqual((Notification.objects.count(), mail.outbox), (0, []))

    # ---- deleting it ------------------------------------------------------------------------------

    def test_deleting_it_tells_everyone_it_is_off(self):
        meeting = self.booked()
        with self.captureOnCommitCallbacks(execute=True):
            code, _ = self.call(views.delete_meeting, self.admin, method='delete', meeting_id=meeting.id)
        self.assertEqual(code, 200)
        self.assertEqual((self.told(self.ali), self.told(self.bea)),
                         (['Meeting cancelled: Customer call'], ['Meeting cancelled: Customer call']))
        self.assertEqual(len(mail.outbox), 2)

    def test_deleting_one_that_was_already_cancelled_says_nothing_more(self):
        meeting = self.booked()
        self.edit(meeting, status='cancelled')
        self.forget()
        self.call(views.delete_meeting, self.admin, method='delete', meeting_id=meeting.id)
        self.assertEqual(Notification.objects.count(), 0)

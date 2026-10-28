"""Executive meetings at the right hour (CO-210), and an answer for everyone invited (CO-211).

The agent keeps a meeting's time as typed. Its reminders, its "meeting is over" sweep and its emails compared or
printed those digits as UTC: booked for 11:00 in Karachi, the reminder came at 4 pm and the email said "11:00 AM
UTC". And an invited employee, who cannot open the agent, had no way to accept or decline, while the unanswered
invitation counted as busy time in every agent.
"""
from datetime import datetime, timedelta, timezone as dt_timezone
import json
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import meeting_agent as views
from api.views import notification
from core.models import Company, CompanyModulePurchase, CompanyUser, UserProfile
from meeting_agent import clock, tasks
from meeting_agent.models import ExecNotification, ExecutiveMeeting, ExecutiveMeetingParticipant

UTC = dt_timezone.utc
KARACHI = ZoneInfo('Asia/Karachi')


def typed(wall):
    """A wall-clock time kept the agent's way: its digits, filed as UTC."""
    return wall.replace(tzinfo=None).replace(tzinfo=UTC)


class ExecCase(TestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.company = Company.objects.create(name='Margalla', email='margalla@test.local',
                                              timezone_name='Asia/Karachi')
        CompanyModulePurchase.objects.create(company=self.company, module_name='exec_meeting_agent',
                                             status='active', is_complimentary=True)
        self.nadia = CompanyUser.objects.create(company=self.company, email='nadia@margalla.test',
                                                full_name='Nadia Rehman', role='owner', password_hash='x',
                                                is_active=True)
        emails = mock.patch.object(views, '_email_login')
        self.emails = emails.start()
        self.addCleanup(emails.stop)

    def meeting(self, at, **more):
        return ExecutiveMeeting.objects.create(organizer=self.nadia, title=more.pop('title', 'Board review'),
                                               status=more.pop('status', 'scheduled'), scheduled_at=at,
                                               duration_minutes=more.pop('duration_minutes', 60), **more)

    def call(self, view, actor, method='post', data=None, **kwargs):
        request = getattr(self.factory, method)('/', data or {}, format='json')
        force_authenticate(request, user=actor)
        response = view(request, **kwargs)
        response.render()
        return response.status_code, json.loads(response.content)


class TimeZoneTests(ExecCase):

    def test_a_typed_time_is_read_on_the_companys_clock(self):
        m = self.meeting(datetime(2026, 11, 2, 11, 0, tzinfo=UTC))
        self.assertEqual(clock.real_start(m), datetime(2026, 11, 2, 6, 0, tzinfo=UTC))
        self.assertIn('11:00 AM Asia/Karachi', clock.when_text(m))
        self.assertNotIn('UTC', clock.when_text(m))

    def test_with_no_company_zone_the_browsers_zone_is_used(self):
        self.company.timezone_name = ''
        self.company.save()
        sent = self.meeting(datetime(2026, 11, 2, 11, 0, tzinfo=UTC), timezone_name='Asia/Karachi')
        old = self.meeting(datetime(2026, 11, 2, 11, 0, tzinfo=UTC))           # made before: 'UTC', read as it was
        self.assertEqual(clock.real_start(sent), datetime(2026, 11, 2, 6, 0, tzinfo=UTC))
        self.assertEqual(clock.real_start(old), datetime(2026, 11, 2, 11, 0, tzinfo=UTC))

    def test_the_reminder_comes_fifteen_minutes_before_the_real_start(self):
        soon = self.meeting(typed(timezone.now().astimezone(KARACHI) + timedelta(minutes=10)), title='Soon')
        utc_digits = self.meeting(typed(timezone.now() + timedelta(minutes=10)), title='Five hours ago')
        tasks.send_meeting_reminders()
        reminded = set(ExecNotification.objects.filter(notification_type='meeting_reminder')
                       .values_list('meeting__title', flat=True))
        self.assertEqual(reminded, {'Soon'})
        self.assertTrue(soon.pk and utc_digits.pk)

    def test_a_meeting_west_of_utc_is_not_over_before_it_starts(self):
        self.company.timezone_name = 'America/New_York'
        self.company.save()
        later = self.meeting(typed(timezone.now() - timedelta(hours=2)))       # 2 h before UTC's digits: NY's future
        done = self.meeting(typed(timezone.now().astimezone(ZoneInfo('America/New_York')) - timedelta(hours=3)))
        tasks.mark_completed_meetings()
        later.refresh_from_db()
        done.refresh_from_db()
        self.assertEqual((later.status, done.status), ('scheduled', 'completed'))

    def test_invited_people_are_reminded_even_when_the_organiser_already_was(self):     # CO-259
        omar = CompanyUser.objects.create(company=self.company, email='omar@margalla.test', full_name='Omar Farooq',
                                          role='company_user', password_hash='x', is_active=True)
        m = self.meeting(typed(timezone.now().astimezone(KARACHI) + timedelta(minutes=10)))
        ExecutiveMeetingParticipant.objects.create(meeting=m, company_user=omar, response='accepted')
        ExecNotification.objects.create(company_user=self.nadia, notification_type='meeting_reminder', meeting=m,
                                        title='Meeting starting soon', message='-')
        tasks.send_meeting_reminders()
        self.assertTrue(ExecNotification.objects.filter(company_user=omar, notification_type='meeting_reminder')
                        .exists())

    def test_the_browsers_zone_is_kept_and_is_not_a_change_to_announce(self):
        code, body = self.call(views.meeting_list, self.nadia, data={
            'title': 'Lease review', 'scheduled_at': '2026-11-03T11:00:00', 'duration_minutes': 30,
            'timezone_name': 'Asia/Karachi'})
        self.assertEqual(code, 201, body)
        meeting = ExecutiveMeeting.objects.get(title='Lease review')
        self.assertEqual(meeting.timezone_name, 'Asia/Karachi')
        with mock.patch.object(views, '_send_meeting_update_email') as told:
            code, body = self.call(views.meeting_detail, self.nadia, method='patch', meeting_id=meeting.id,
                                   data={'timezone_name': 'Asia/Karachi'})
        self.assertEqual(code, 200, body)
        told.assert_not_called()

    def test_todays_date_for_the_ai_helpers_is_the_companys(self):
        self.assertEqual(clock.today_for(self.company.id), timezone.now().astimezone(KARACHI).date())


class EmployeeCase(ExecCase):
    """An employee, Sana, invited to the board meeting through her seat."""

    def setUp(self):
        super().setUp()
        user = get_user_model().objects.create_user('sana', email='sana@margalla.test', password='x',
                                                    first_name='Sana', last_name='Iqbal')
        profile, _ = UserProfile.objects.update_or_create(user=user, defaults={'company': self.company,
                                                                               'role': 'team_member'})
        self.sana = get_user_model().objects.get(pk=user.pk)
        self.seat_login = views._seat_for_employee(profile.id, self.company)
        self.board = self.meeting(typed(timezone.now().astimezone(KARACHI) + timedelta(days=2)))
        self.seat = ExecutiveMeetingParticipant.objects.create(meeting=self.board, company_user=self.seat_login)

    def mine(self):
        return next(i for i in notification._executive_meeting_items(self.sana) if i['id'] == self.board.id)


class AnswerTests(EmployeeCase):

    def test_the_employee_sees_it_and_can_answer(self):
        item = self.mine()
        self.assertTrue(item['can_respond'])
        self.assertFalse(item['can_suggest_time'])
        self.assertEqual(item['respond_url'], f'/exec-meeting/meetings/{self.board.id}/respond-as-employee')

    def test_the_agenda_reaches_my_meetings_as_items(self):
        # This agent keeps the agenda as plain text; My Meetings reads {item, done}, or shows empty bullets.
        self.board.agenda = ['Q4 plan', '', 'FinEdge renewal']
        self.board.save(update_fields=['agenda'])
        self.assertEqual(self.mine()['agenda'], [{'item': 'Q4 plan', 'done': False},
                                                 {'item': 'FinEdge renewal', 'done': False}])

    def test_the_employee_declines_and_the_organiser_is_told(self):
        code, body = self.call(views.meeting_respond_as_employee, self.sana, meeting_id=self.board.id,
                               data={'action': 'rejected', 'reason': 'On leave that day'})
        self.assertEqual(code, 200, body)
        self.seat.refresh_from_db()
        self.assertEqual((self.seat.response, self.seat.reason), ('rejected', 'On leave that day'))
        told = ExecNotification.objects.get(company_user=self.nadia, notification_type='participant_response')
        self.assertIn('declined', told.title)
        self.assertEqual(self.mine()['my_status'], 'rejected')

    def test_someone_not_invited_cannot_answer_and_a_suggested_time_is_refused(self):
        other = get_user_model().objects.create_user('bilal', email='bilal@margalla.test', password='x')
        code, _ = self.call(views.meeting_respond_as_employee, other, meeting_id=self.board.id,
                            data={'action': 'accepted'})
        self.assertEqual(code, 404)
        code, _ = self.call(views.meeting_respond_as_employee, self.sana, meeting_id=self.board.id,
                            data={'action': 'counter_proposed'})
        self.assertEqual(code, 400)

    def test_the_invitation_email_has_accept_and_decline(self):
        views._send_meeting_invite_email(self.seat_login, self.board, 'Nadia Rehman')
        html = self.emails.call_args[0][3]
        self.assertIn('/api/meetings/exec-email-answer/accepted/', html)
        self.assertIn('/api/meetings/exec-email-answer/rejected/', html)
        self.assertIn('Asia/Karachi', html)

    def email_answer(self, action, token=None):
        token = token or views.answer_link(self.seat, action).rstrip('/').rsplit('/', 1)[1]
        response = views.meeting_email_answer(RequestFactory().get('/'), action, token)
        return response.content.decode()

    def test_the_email_buttons_answer_without_a_login(self):
        self.assertIn('Accepted', self.email_answer('accepted'))
        self.seat.refresh_from_db()
        self.assertEqual(self.seat.response, 'accepted')
        self.assertIn('Already accepted', self.email_answer('accepted'))
        self.assertIn('Link expired or invalid', self.email_answer('accepted', token='forged:token'))

    def test_a_cancelled_meeting_has_nothing_to_answer_and_its_title_is_escaped(self):
        self.board.title = '<b>Board</b> review'
        self.board.status = 'cancelled'
        self.board.save()
        page = self.email_answer('rejected')
        self.assertIn('Nothing to answer', page)
        self.assertIn('&lt;b&gt;Board&lt;/b&gt;', page)

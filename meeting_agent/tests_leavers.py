"""When someone leaves, their executive meetings and tasks do not go with them.

Only the login that organised an executive meeting could open, move or cancel
it. When that login was switched off, the meetings stayed booked on every
invited person's calendar with nobody able to cancel them, and the leaver's
tasks became invisible. A leaver who had only been invited stayed on the list
and was emailed the full details of every later change.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import company_logins
from api.views import meeting_agent as views
from core.leavers import login_switched_off
from core.models import CalendarBlock, Company, CompanyModulePurchase, CompanyUser, UserProfile
from meeting_agent import leavers
from meeting_agent.models import ExecutiveMeeting, ExecutiveMeetingParticipant, ExecutiveTask


class ExecutiveLeaversTestCase(TestCase):
    """Dana is an admin. Omar organises executive meetings and is the one who leaves. Mo is invited."""

    def setUp(self):
        self.acme = Company.objects.create(name='Acme', email='acme@test.local')
        CompanyModulePurchase.objects.create(company=self.acme, module_name='exec_meeting_agent', status='active',
                                             is_complimentary=True)
        self.dana = self.login('dana@acme.test', 'Dana Malik', 'admin')
        self.omar = self.login('omar@acme.test', 'Omar Sheikh', 'company_user')
        self.mo = self.login('mo@acme.test', 'Mo Khan', 'company_user')
        for login in (self.dana, self.omar, self.mo):       # each is an employee too, so each has a calendar
            self.employee(login.email)
        self.soon = timezone.now() + timedelta(days=3)

    def login(self, email, name, role, company=None, active=True):
        return CompanyUser.objects.create(company=company or self.acme, email=email, full_name=name, role=role,
                                          password_hash='x', is_active=active)

    def employee(self, email, active=True):
        user = get_user_model().objects.create_user(email.split('@')[0], email=email, password='x', is_active=active)
        UserProfile.objects.update_or_create(user=user, defaults={'company': self.acme, 'role': 'team_member'})
        return user

    def meeting(self, organiser, title='Board meeting', invited=(), when=None, **more):
        meeting = ExecutiveMeeting.objects.create(organizer=organiser, title=title, scheduled_at=when or self.soon,
                                                  duration_minutes=60, **more)
        for login in invited:
            ExecutiveMeetingParticipant.objects.create(meeting=meeting, company_user=login, response='accepted')
        return meeting

    def switch_off(self, login=None, by=None):
        login = login or self.omar
        CompanyUser.objects.filter(pk=login.pk).update(is_active=False)
        login.refresh_from_db()
        return ' '.join(login_switched_off(login, by=by))

    def organiser(self, meeting):
        return ExecutiveMeeting.objects.get(pk=meeting.pk).organizer_id

    def invited(self, meeting):
        return sorted(ExecutiveMeetingParticipant.objects.filter(meeting=meeting)
                      .values_list('company_user__email', flat=True))


class MeetingsTheyOrganisedTests(ExecutiveLeaversTestCase):

    def test_those_still_to_come_pass_to_the_admin_who_switched_them_off(self):
        board = self.meeting(self.omar, invited=[self.mo])
        said = self.switch_off(by=self.dana)
        self.assertEqual(self.organiser(board), self.dana.id)
        self.assertEqual(self.invited(board), ['mo@acme.test'])
        self.assertIn('1 executive meeting they organised now belongs to Dana Malik', said)

    def test_the_new_organiser_can_now_cancel_it(self):
        board = self.meeting(self.omar, invited=[self.mo])
        self.switch_off(by=self.dana)
        request = APIRequestFactory().patch('/x', {'status': 'cancelled'}, format='json')
        force_authenticate(request, user=self.dana)
        response = views.meeting_detail(request, meeting_id=board.id)
        self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        self.assertEqual(ExecutiveMeeting.objects.get(pk=board.pk).status, 'cancelled')

    def test_with_nobody_pressing_a_button_they_go_to_an_owner_or_admin(self):
        board = self.meeting(self.omar)
        self.switch_off()
        self.assertEqual(self.organiser(board), self.dana.id)

    def test_finished_and_cancelled_meetings_are_left_with_their_notes(self):
        done = self.meeting(self.omar, title='Last quarter', when=timezone.now() - timedelta(days=20),
                            status='completed')
        called_off = self.meeting(self.omar, title='Called off', status='cancelled')
        self.switch_off(by=self.dana)
        self.assertEqual((self.organiser(done), self.organiser(called_off)), (self.omar.id, self.omar.id))

    def test_if_the_new_organiser_was_invited_they_are_not_listed_twice(self):
        board = self.meeting(self.omar, invited=[self.dana, self.mo])
        self.switch_off(by=self.dana)
        self.assertEqual((self.organiser(board), self.invited(board)), (self.dana.id, ['mo@acme.test']))

    def test_the_shared_calendar_follows(self):
        board = self.meeting(self.omar, invited=[self.mo])
        blocked = lambda: sorted(CalendarBlock.objects.filter(source='exec', source_id=board.id)
                                 .values_list('user__email', flat=True))
        self.assertEqual(blocked(), ['mo@acme.test', 'omar@acme.test'])
        self.switch_off(by=self.dana)
        self.assertEqual(blocked(), ['dana@acme.test', 'mo@acme.test'])

    def test_with_nobody_left_in_the_company_they_stay_and_it_says_so(self):
        board = self.meeting(self.omar)
        CompanyUser.objects.filter(company=self.acme).exclude(pk=self.omar.pk).update(is_active=False)
        said = self.switch_off()
        self.assertEqual(self.organiser(board), self.omar.id)
        self.assertIn('no other login to give them to', said)


class MeetingsTheyWereInvitedToTests(ExecutiveLeaversTestCase):

    def test_they_are_taken_off_the_ones_still_to_come_without_an_email(self):
        board = self.meeting(self.dana, invited=[self.omar, self.mo])
        past = self.meeting(self.dana, title='Last quarter', invited=[self.omar],
                            when=timezone.now() - timedelta(days=20), status='completed')
        mail.outbox.clear()
        said = self.switch_off(by=self.dana)
        self.assertEqual(self.invited(board), ['mo@acme.test'])
        self.assertEqual(self.invited(past), ['omar@acme.test'])           # the record of who was there stays
        self.assertEqual(mail.outbox, [])
        self.assertIn('taken off 1 executive meeting', said)

    def test_their_time_is_no_longer_blocked(self):
        board = self.meeting(self.dana, invited=[self.omar])
        self.assertTrue(CalendarBlock.objects.filter(source='exec', source_id=board.id,
                                                     user__email='omar@acme.test').exists())
        self.switch_off(by=self.dana)
        self.assertFalse(CalendarBlock.objects.filter(source='exec', source_id=board.id,
                                                      user__email='omar@acme.test').exists())


class TasksTests(ExecutiveLeaversTestCase):

    def test_their_open_tasks_pass_on_and_they_are_dropped_as_assignee_elsewhere(self):
        theirs = ExecutiveTask.objects.create(company_user=self.omar, title='Send the minutes')
        finished = ExecutiveTask.objects.create(company_user=self.omar, title='Old task', status='done')
        danas = ExecutiveTask.objects.create(company_user=self.dana, title='Review budget')
        danas.assignees.add(self.omar, self.mo)

        said = self.switch_off(by=self.dana)

        self.assertEqual(ExecutiveTask.objects.get(pk=theirs.pk).company_user_id, self.dana.id)
        self.assertEqual(ExecutiveTask.objects.get(pk=finished.pk).company_user_id, self.omar.id)
        self.assertEqual(list(danas.assignees.values_list('email', flat=True)), ['mo@acme.test'])
        self.assertIn('1 open executive task of theirs now belongs to Dana Malik', said)

    def test_someone_with_nothing_here_makes_no_noise(self):
        self.assertEqual(leavers.login_switched_off(self.mo), '')


class NobodyWhoHasLeftIsEmailedTests(ExecutiveLeaversTestCase):

    def emailed(self, login):
        mail.outbox.clear()
        board = self.meeting(self.dana, title=f'For {login.email}')
        views._send_meeting_update_email(login, board, 'Dana Malik', ['time'])
        views._send_task_assignment_email(login, ExecutiveTask.objects.create(company_user=self.dana, title='T'),
                                          'Dana Malik')
        return len(mail.outbox)

    def test_an_active_login_is(self):
        self.assertEqual(self.emailed(self.mo), 2)

    def test_a_login_that_has_been_switched_off_is_not(self):
        CompanyUser.objects.filter(pk=self.omar.pk).update(is_active=False)
        get_user_model().objects.filter(email='omar@acme.test').update(is_active=False)      # as offboarding does
        self.omar.refresh_from_db()
        self.assertEqual(self.emailed(self.omar), 0)

    def test_an_employees_stand_in_seat_is_emailed_while_they_work_here_and_not_after(self):
        self.employee('sara@acme.test')
        seat = self.login('sara@acme.test', 'Sara Employee', 'company_user', active=False)   # how a seat is stored
        self.assertTrue(leavers.still_with_the_company(seat))
        self.assertEqual(self.emailed(seat), 2)
        get_user_model().objects.filter(email='sara@acme.test').update(is_active=False)      # offboarded
        self.assertFalse(leavers.still_with_the_company(seat))
        self.assertEqual(self.emailed(seat), 0)

    def test_a_seat_for_an_address_nobody_here_has_is_not_emailed(self):
        seat = self.login('ghost@acme.test', 'Ghost', 'company_user', active=False)
        self.assertEqual(self.emailed(seat), 0)


class ThroughTheScreenTests(ExecutiveLeaversTestCase):

    def test_switching_a_login_off_on_logins_and_roles_does_all_of_it(self):
        board = self.meeting(self.omar, invited=[self.mo])
        request = APIRequestFactory().patch('/x', {'is_active': False}, format='json')
        force_authenticate(request, user=self.dana)
        response = company_logins.company_login(request, login_id=self.omar.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.organiser(board), self.dana.id)
        self.assertIn('now belongs to Dana Malik', ' '.join(response.data['switched_off']))

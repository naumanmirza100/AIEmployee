"""Sales calls and executive meetings are on the shared calendar.

They were left off it when it was built (17 September 2026). A lead booking a
sales call was checked only against the same salesperson's other sales calls; a
salesperson confirming a time was checked against nothing; an executive meeting
was checked, at most, against the organiser's other executive meetings. Either
could land on an interview, a project or HR meeting, approved leave or a
company holiday, and neither showed on the employee's Meetings page.
"""
import json
from datetime import datetime, time, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent.models import SDRLead, SDRMeeting
from api.views import ai_sdr_agent as sales, meeting_agent as executive, notification
from core.models import CalendarBlock, Company, CompanyModulePurchase, CompanyUser, UserProfile
from core.scheduling import ScheduleConflict, ensure_free, rebuild
from hr_agent.models import Employee, Holiday, LeaveRequest
from meeting_agent.models import ExecutiveMeeting, ExecutiveMeetingParticipant

UTC = ZoneInfo('UTC')


class BothLoginsTestCase(TestCase):
    """Rae sells and runs executive meetings from a dashboard login, and is
    also an employee: the same address signs in to My Space. Dee has only a
    dashboard login, so she has no calendar."""

    factory = APIRequestFactory()

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        for module in ('ai_sdr_agent', 'exec_meeting_agent', 'hr_agent'):
            CompanyModulePurchase.objects.create(company=self.company, module_name=module, status='active',
                                                 is_complimentary=True)
        self.rae_login = self.dashboard('rae@test.local', 'Rae Rep')
        self.rae = self.employee('rae')
        self.dee_login = self.dashboard('dee@test.local', 'Dee Dashboard')
        self.sam = self.employee('sam')
        self.lead = SDRLead.objects.create(company_user=self.rae_login, email='bob@lead.example', first_name='Bob')
        self.day = timezone.now().date() + timedelta(days=7)
        while self.day.weekday() >= 5:
            self.day += timedelta(days=1)

    def dashboard(self, email, name, company=None):
        return CompanyUser.objects.create(company=company or self.company, email=email, full_name=name, role='admin',
                                          password_hash='x', is_active=True)

    def employee(self, username):
        user = get_user_model().objects.create_user(username, email=f'{username}@test.local', password='x',
                                                    first_name=username.title())
        UserProfile.objects.update_or_create(user=user, defaults={'company': self.company, 'role': 'team_member'})
        # As a request loads them: the instance above still carries the profile it was created with, no company.
        return get_user_model().objects.get(pk=user.pk)

    def at(self, hour, minute=0):
        return datetime.combine(self.day, time(hour, minute), tzinfo=UTC)

    def blocks(self, user, source):
        return CalendarBlock.objects.filter(user=user, source=source)

    def on_leave(self, user):
        record, _ = Employee.objects.get_or_create(company=self.company, work_email=user.email,
                                                   defaults={'user': user, 'full_name': user.first_name})
        if record.user_id != user.id:
            record.user = user
            record.save()
        return LeaveRequest.objects.create(employee=record, leave_type='vacation', start_date=self.day,
                                           end_date=self.day, days_requested=1, status='approved')

    def busy_elsewhere(self, user, hour=10, source='pm', title='Roadmap review'):
        return CalendarBlock.objects.create(company=self.company, user=user, source=source, source_id=777,
                                            role='participant', response='accepted', title=title,
                                            starts_at=self.at(hour), ends_at=self.at(hour + 1))

    def call(self, view, actor, data=None, method='post', **kwargs):
        request = getattr(self.factory, method)('/', data or {}, format='json')
        force_authenticate(request, user=actor)
        response = view(request, **kwargs)
        if hasattr(response, 'render'):
            response.render()
        return response.status_code, (json.loads(response.content) if response.content else {})


class SalesCallsOnTheCalendarTests(BothLoginsTestCase):

    def sales_call(self, hour=10, **fields):
        fields.setdefault('status', 'scheduled')
        fields.setdefault('scheduled_at', self.at(hour))
        return SDRMeeting.objects.create(company_user=self.rae_login, lead=self.lead, duration_minutes=30, **fields)

    def test_a_booked_call_is_busy_time_for_the_salesperson_in_every_agent(self):
        self.sales_call(title='Discovery call')
        [block] = self.blocks(self.rae, 'sdr')
        self.assertEqual((block.starts_at, block.ends_at, block.title, block.role),
                         (self.at(10), self.at(10, 30), 'Discovery call', 'organizer'))
        with self.assertRaises(ScheduleConflict) as refused:
            ensure_free([self.rae.id], self.at(10, 15), 30, viewer_source='hr')
        self.assertIn('Sales call', refused.exception.text())

    def test_a_time_proposed_to_the_lead_counts_until_they_answer(self):
        self.sales_call(status='awaiting_approval')
        self.assertEqual(self.blocks(self.rae, 'sdr').count(), 1)

    def test_a_call_with_no_time_or_that_is_over_or_off_takes_no_time(self):
        self.sales_call(status='pending', scheduled_at=None)
        for status in ('pending', 'cancelled', 'completed', 'no_show'):
            self.sales_call(status=status)
        self.assertEqual(self.blocks(self.rae, 'sdr').count(), 0)

    def test_cancelling_frees_the_hour_at_once(self):
        call = self.sales_call()
        call.status = 'cancelled'
        call.save()
        self.assertEqual(self.blocks(self.rae, 'sdr').count(), 0)
        ensure_free([self.rae.id], self.at(10), 30)

    def test_a_salesperson_with_only_a_dashboard_login_has_no_calendar(self):
        lead = SDRLead.objects.create(company_user=self.dee_login, email='x@lead.example', first_name='X')
        SDRMeeting.objects.create(company_user=self.dee_login, lead=lead, status='scheduled', scheduled_at=self.at(10))
        self.assertEqual(CalendarBlock.objects.filter(source='sdr').count(), 0)

    def test_the_nightly_rebuild_knows_both_new_kinds(self):
        self.sales_call()
        CalendarBlock.objects.all().delete()
        stats = rebuild(since=timezone.now())
        self.assertEqual((stats['sdr']['blocks'], 'exec' in stats), (1, True))

    # ---- the lead's booking page --------------------------------------------------------

    def book(self, call, when):
        with mock.patch.object(sales, '_create_google_meet_link', return_value=None), \
                mock.patch('ai_sdr_agent.agents.meeting_scheduling_agent.MeetingSchedulingAgent'):
            response = Client().post(f'/api/sdr/book/{call.booking_token}/confirm/',
                                     {'scheduled_at': when.isoformat()}, content_type='application/json')
        return response.status_code, response.json()

    def test_a_lead_cannot_book_a_salesperson_who_is_on_leave(self):
        call = self.sales_call(status='pending', scheduled_at=None)
        self.on_leave(self.rae)
        code, body = self.book(call, self.at(11))
        self.assertEqual((code, body['error']), (409, 'slot_unavailable'))
        call.refresh_from_db()
        self.assertEqual((call.status, call.scheduled_at), ('pending', None))

    def test_nor_one_who_is_in_another_agents_meeting(self):
        call = self.sales_call(status='pending', scheduled_at=None)
        self.busy_elsewhere(self.rae, hour=11, title='Exit interview: Sam')
        code, body = self.book(call, self.at(11, 30))
        self.assertEqual(code, 409)
        # A stranger learns that the time is taken, and nothing about why.
        self.assertEqual(body, {'error': 'slot_unavailable',
                                'message': 'That time is no longer available. Please pick another slot.'})

    def test_nor_on_a_company_holiday_read_on_the_companys_clock(self):
        self.company.timezone_name = 'Asia/Karachi'
        self.company.save()
        Holiday.objects.create(company=self.company, name='Founders day', date=self.day)
        call = self.sales_call(status='pending', scheduled_at=None)
        self.assertEqual(self.book(call, self.at(6))[0], 409)                  # 11:00 in Karachi, that day
        self.assertEqual(self.book(call, self.at(20))[0], 200)                 # 01:00 the next day there

    def test_a_free_time_is_booked_and_is_on_the_calendar_at_once(self):
        call = self.sales_call(status='pending', scheduled_at=None)
        code, _ = self.book(call, self.at(14))
        self.assertEqual(code, 200)
        # Not at the nightly rebuild: the booking is saved in a way no signal sees.
        [block] = self.blocks(self.rae, 'sdr')
        self.assertEqual(block.starts_at, self.at(14))

    # ---- the salesperson's own screens ------------------------------------------------------

    def confirm(self, call, when, **more):
        with mock.patch('ai_sdr_agent.agents.meeting_scheduling_agent.MeetingSchedulingAgent') as emails:
            code, body = self.call(sales.sdr_confirm_meeting, self.rae_login,
                                   {'scheduled_at': when.isoformat(), **more}, meeting_id=call.id)
        return code, body, emails

    def test_confirming_a_time_they_are_busy_at_is_refused_and_says_why(self):
        call = self.sales_call(status='pending', scheduled_at=None)
        self.busy_elsewhere(self.rae, hour=11)
        code, body, emails = self.confirm(call, self.at(11))
        self.assertEqual((code, body['code']), (409, 'schedule_conflict'), body)
        self.assertIn('Roadmap review', body['message'])                        # their own calendar: they may see it
        call.refresh_from_db()
        self.assertEqual((call.status, call.scheduled_at), ('pending', None))
        emails.assert_not_called()                                              # nothing went to the lead

    def test_so_is_proposing_one_to_the_lead(self):
        call = self.sales_call(status='pending', scheduled_at=None)
        self.on_leave(self.rae)
        code, body, _ = self.confirm(call, self.at(11), send_approval=True)
        self.assertEqual(code, 409, body)
        call.refresh_from_db()
        self.assertEqual(call.status, 'pending')

    def test_a_free_time_is_confirmed(self):
        call = self.sales_call(status='pending', scheduled_at=None)
        code, body, _ = self.confirm(call, self.at(15))
        self.assertEqual(code, 200, body)
        call.refresh_from_db()
        self.assertEqual((call.status, call.scheduled_at), ('scheduled', self.at(15)))

    def edit(self, call, **data):
        return self.call(sales.sdr_meeting_detail, self.rae_login, data, method='put', meeting_id=call.id)

    def test_moving_a_call_onto_something_else_is_refused(self):
        call = self.sales_call(hour=9)
        self.busy_elsewhere(self.rae, hour=11)
        code, body = self.edit(call, scheduled_at=self.at(11).isoformat())
        self.assertEqual((code, body['code']), (409, 'schedule_conflict'), body)
        call.refresh_from_db()
        self.assertEqual(call.scheduled_at, self.at(9))

    def test_bringing_a_cancelled_call_back_is_checked_too(self):
        call = self.sales_call(hour=11, status='cancelled')
        self.busy_elsewhere(self.rae, hour=11)
        self.assertEqual(self.edit(call, status='scheduled')[0], 409)

    def test_a_change_that_moves_nothing_is_never_refused(self):
        call = self.sales_call(hour=11)
        self.busy_elsewhere(self.rae, hour=11)                                  # booked over it some other way
        code, body = self.edit(call, notes='Send the deck first', title='Intro call')
        self.assertEqual(code, 200, body)
        self.assertEqual(self.edit(call, status='completed')[0], 200)

    def test_a_call_cannot_clash_with_itself(self):
        call = self.sales_call(hour=11)
        self.assertEqual(self.edit(call, scheduled_at=self.at(11, 15).isoformat())[0], 200)

    def test_a_call_made_by_hand_at_a_busy_time_is_refused(self):
        self.busy_elsewhere(self.rae, hour=11)
        new = {'lead_id': self.lead.id, 'status': 'scheduled', 'scheduled_at': self.at(11).isoformat()}
        code, body = self.call(sales.sdr_meetings_list, self.rae_login, new)
        self.assertEqual(code, 409, body)
        self.assertEqual(SDRMeeting.objects.count(), 0)
        self.assertEqual(self.call(sales.sdr_meetings_list, self.rae_login, {'lead_id': self.lead.id})[0], 201)


class ExecutiveMeetingsOnTheCalendarTests(BothLoginsTestCase):

    def meeting(self, hour=10, organizer=None, **fields):
        return ExecutiveMeeting.objects.create(organizer=organizer or self.rae_login, title=fields.pop('title', 'Board prep'),
                                               scheduled_at=self.at(hour), duration_minutes=60, **fields)

    def seat(self, user):
        """The row that stands in for an employee in an executive meeting."""
        return CompanyUser.objects.create(company=self.company, email=user.email, full_name=user.first_name,
                                          role='company_user', password_hash='x', is_active=False)

    def test_it_is_busy_time_for_the_organiser_and_everyone_invited(self):
        meeting = self.meeting()
        ExecutiveMeetingParticipant.objects.create(meeting=meeting, company_user=self.seat(self.sam))
        self.assertEqual({b.user_id: b.role for b in CalendarBlock.objects.filter(source='exec')},
                         {self.rae.id: 'organizer', self.sam.id: 'participant'})
        with self.assertRaises(ScheduleConflict) as refused:
            ensure_free([self.sam.id], self.at(10, 30), 30, viewer_source='hr')
        self.assertIn('Executive meeting', refused.exception.text())
        # Busy, and in what kind of meeting. Not what the meeting is about.
        self.assertNotIn('Board prep', refused.exception.text())

    def test_someone_who_declined_is_free_and_a_tentative_yes_is_not(self):
        meeting = self.meeting()
        seat = ExecutiveMeetingParticipant.objects.create(meeting=meeting, company_user=self.seat(self.sam))
        for response, busy in (('rejected', 0), ('tentative', 1), ('accepted', 1)):
            seat.response = response
            seat.save()
            self.assertEqual(self.blocks(self.sam, 'exec').count(), busy, response)

    def test_a_meeting_that_is_over_or_off_takes_no_time(self):
        meeting = self.meeting()
        for status in ('cancelled', 'completed'):
            meeting.status = status
            meeting.save()
            self.assertEqual(CalendarBlock.objects.filter(source='exec').count(), 0, status)

    def test_one_that_is_under_way_or_waiting_to_be_confirmed_does(self):
        meeting = self.meeting()
        for status in ('in_progress', 'pending_confirmation', 'scheduled'):
            meeting.status = status
            meeting.save()
            self.assertEqual(self.blocks(self.rae, 'exec').count(), 1, status)

    # ---- booking one ----------------------------------------------------------------------

    def create(self, hour=11, **more):
        return self.call(executive.meeting_list, self.rae_login,
                         {'title': 'Strategy', 'scheduled_at': self.at(hour).isoformat(), **more})

    def test_an_organiser_who_is_on_leave_cannot_book_one(self):
        self.on_leave(self.rae)
        code, body = self.create()
        self.assertEqual((code, body['code']), (409, 'schedule_conflict'), body)
        self.assertIn('on leave', body['message'])
        self.assertEqual(ExecutiveMeeting.objects.count(), 0)

    def test_nor_one_who_is_in_another_agents_meeting(self):
        self.busy_elsewhere(self.rae, hour=11)
        self.assertEqual(self.create()[0], 409)
        self.assertEqual(self.create(hour=14)[0], 201)

    def test_a_dashboard_login_with_no_calendar_books_as_before(self):
        self.assertEqual(self.call(executive.meeting_list, self.dee_login,
                                   {'title': 'Strategy', 'scheduled_at': self.at(11).isoformat()})[0], 201)

    # ---- the time is kept as typed, and read on the company's clock ---------------------------

    def in_karachi(self):
        self.company.timezone_name = 'Asia/Karachi'
        self.company.save()

    def test_a_meeting_typed_for_eleven_in_karachi_is_busy_at_eleven_there(self):
        self.in_karachi()
        self.meeting(hour=11)                                   # the screen sent "11:00"; it is filed as 11:00 UTC
        [block] = self.blocks(self.rae, 'exec')
        self.assertEqual((block.starts_at, block.ends_at), (self.at(6), self.at(7)))    # 11:00 to 12:00 in Karachi

    def test_a_company_with_no_time_zone_is_read_as_it_was_filed(self):
        self.meeting(hour=11)
        self.assertEqual(self.blocks(self.rae, 'exec').get().starts_at, self.at(11))

    def test_it_is_refused_over_what_the_person_really_has_then(self):
        self.in_karachi()
        self.busy_elsewhere(self.rae, hour=6)                   # 11:00 to 12:00 in Karachi
        code, body = self.create(hour=11)
        self.assertEqual(code, 409, body)
        self.assertIn('11:00', body['message'])                 # said on the company's clock, as it was typed

    def test_and_not_over_what_they_have_at_the_hour_it_is_filed_under(self):
        self.in_karachi()
        self.busy_elsewhere(self.rae, hour=11)                  # 4 pm in Karachi
        self.assertEqual(self.create(hour=11)[0], 201)

    def test_moving_one_and_adding_someone_read_the_clock_the_same_way(self):
        self.in_karachi()
        meeting = self.meeting(hour=9)
        self.busy_elsewhere(self.rae, hour=6)
        code, _ = self.call(executive.meeting_detail, self.rae_login, {'scheduled_at': self.at(11).isoformat()},
                            method='patch', meeting_id=meeting.id)
        self.assertEqual(code, 409)
        self.busy_elsewhere(self.sam, hour=4)                   # 9:00 in Karachi, when the meeting is
        self.assertEqual(self.add(meeting, self.sam)[0], 409)

    def test_so_does_asking_whether_a_time_would_clash(self):
        self.in_karachi()
        self.busy_elsewhere(self.rae, hour=6)
        self.assertIs(self.check()['blocking'], True)           # asks about "11:00"
        self.assertIs(self.check(scheduled_at=self.at(6).isoformat())['blocking'], False)

    def test_a_new_company_time_zone_moves_the_meetings_already_booked(self):
        from hr_agent import zones
        self.meeting(hour=11)
        zones.set_company_zone(self.company, 'Asia/Karachi')
        self.assertEqual(self.blocks(self.rae, 'exec').get().starts_at, self.at(6))
        zones.set_company_zone(self.company, '')
        self.assertEqual(self.blocks(self.rae, 'exec').get().starts_at, self.at(11))

    def test_a_company_holiday_is_read_on_the_companys_clock(self):
        self.in_karachi()
        Holiday.objects.create(company=self.company, name='Founders day', date=self.day)
        day_before = datetime.combine(self.day - timedelta(days=1), time(22), tzinfo=UTC)
        # Typed times are times of day in Karachi, and so is the holiday: all of that day, none of the one before.
        self.assertEqual(self.create(hour=2)[0], 409)
        self.assertEqual(self.create(hour=22)[0], 409)
        self.assertEqual(self.call(executive.meeting_list, self.rae_login,
                                   {'title': 'Strategy', 'scheduled_at': day_before.isoformat()})[0], 201)

    # ---- the people invited come with the meeting -----------------------------------------

    def pick(self, user):
        return {'user_id': UserProfile.objects.get(user=user).id, 'user_type': 'profile'}

    def test_one_busy_invitee_refuses_the_whole_meeting(self):
        self.busy_elsewhere(self.sam, hour=11)
        with mock.patch.object(executive, '_invite_all') as invites:
            code, body = self.create(participants=[self.pick(self.sam)])
        self.assertEqual((code, body['code']), (409, 'schedule_conflict'), body)
        # Not a meeting made without them, as when each person was added by a request of their own.
        self.assertEqual((ExecutiveMeeting.objects.count(), ExecutiveMeetingParticipant.objects.count()), (0, 0))
        invites.assert_not_called()

    def test_when_everyone_is_free_it_is_made_with_them_in_it(self):
        with mock.patch.object(executive, '_invite_all') as invites:
            code, body = self.create(participants=[self.pick(self.sam), self.pick(self.sam),
                                                   {'user_id': self.rae_login.id, 'user_type': 'company_user'}])
        self.assertEqual(code, 201, body)
        meeting = ExecutiveMeeting.objects.get()
        # Once each, and the organiser is not their own guest.
        self.assertEqual([p.company_user.email for p in meeting.participants.all()], [self.sam.email])
        self.assertEqual([p['name'] for p in body['meeting']['participants']], ['Sam'])
        self.assertEqual((self.blocks(self.rae, 'exec').count(), self.blocks(self.sam, 'exec').count()), (1, 1))
        [(targets, sent_for, organiser), _] = invites.call_args
        self.assertEqual(([t.email for t in targets], sent_for, organiser), ([self.sam.email], meeting, 'Rae Rep'))

    def test_someone_who_is_not_in_the_company_stops_it(self):
        with mock.patch.object(executive, '_invite_all'):
            code, _ = self.create(participants=[{'user_id': 987654, 'user_type': 'profile'}])
        self.assertEqual((code, ExecutiveMeeting.objects.count()), (404, 0))

    def test_the_invitations_are_emailed(self):
        seat = self.seat(self.sam)
        meeting = self.meeting()
        with mock.patch.object(executive, '_send_meeting_invite_email') as email, \
                mock.patch('threading.Thread') as thread:
            executive._invite_all([seat, self.dashboard('', 'No Address')], meeting, 'Rae Rep')
            thread.call_args.kwargs['target']()                                 # what the thread would run
        email.assert_called_once_with(seat, meeting, 'Rae Rep')

    def test_moving_one_onto_something_else_is_refused_for_anyone_in_it(self):
        meeting = self.meeting(hour=9)
        ExecutiveMeetingParticipant.objects.create(meeting=meeting, company_user=self.seat(self.sam))
        self.busy_elsewhere(self.sam, hour=11)                                  # the invitee, not the organiser
        code, body = self.call(executive.meeting_detail, self.rae_login, {'scheduled_at': self.at(11).isoformat()},
                               method='patch', meeting_id=meeting.id)
        self.assertEqual((code, body['code']), (409, 'schedule_conflict'), body)
        meeting.refresh_from_db()
        self.assertEqual(meeting.scheduled_at, self.at(9))

    def test_a_change_that_moves_nothing_is_never_refused(self):
        meeting = self.meeting(hour=11)
        self.busy_elsewhere(self.rae, hour=11)
        code, body = self.call(executive.meeting_detail, self.rae_login, {'title': 'Board prep (final)'},
                               method='patch', meeting_id=meeting.id)
        self.assertEqual(code, 200, body)

    def test_a_meeting_cannot_clash_with_itself(self):
        meeting = self.meeting(hour=9)
        code, body = self.call(executive.meeting_detail, self.rae_login, {'scheduled_at': self.at(9, 30).isoformat()},
                               method='patch', meeting_id=meeting.id)
        self.assertEqual(code, 200, body)

    def test_bringing_a_cancelled_meeting_back_is_checked_too(self):
        meeting = self.meeting(hour=11, status='cancelled')
        self.busy_elsewhere(self.rae, hour=11)
        code, body = self.call(executive.meeting_detail, self.rae_login, {'status': 'scheduled'},
                               method='patch', meeting_id=meeting.id)
        self.assertEqual(code, 409, body)
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, 'cancelled')

    def add(self, meeting, user):
        profile = UserProfile.objects.get(user=user)
        with mock.patch.object(executive, '_send_meeting_invite_email'):
            return self.call(executive.meeting_participants, self.rae_login,
                             {'user_id': profile.id, 'user_type': 'profile'}, meeting_id=meeting.id)

    def test_adding_someone_twice_is_not_a_clash_with_the_meeting_itself(self):
        meeting = self.meeting(hour=11)
        self.assertEqual(self.add(meeting, self.sam)[0], 201)
        self.assertEqual(self.add(meeting, self.sam)[0], 200)
        self.assertEqual(meeting.participants.count(), 1)

    def test_a_meeting_that_is_over_takes_nobodys_time_so_anyone_can_be_added_to_its_record(self):
        meeting = self.meeting(hour=11, status='completed')
        self.busy_elsewhere(self.sam, hour=11)
        self.assertEqual(self.add(meeting, self.sam)[0], 201)

    def test_someone_who_is_busy_cannot_be_added(self):
        meeting = self.meeting(hour=11)
        self.busy_elsewhere(self.sam, hour=11)
        profile = UserProfile.objects.get(user=self.sam)
        with mock.patch.object(executive, '_send_meeting_invite_email') as invite:
            code, body = self.call(executive.meeting_participants, self.rae_login,
                                   {'user_id': profile.id, 'user_type': 'profile'}, meeting_id=meeting.id)
        self.assertEqual((code, body['code']), (409, 'schedule_conflict'), body)
        self.assertEqual(meeting.participants.count(), 0)
        invite.assert_not_called()

    def test_someone_who_is_free_can(self):
        meeting = self.meeting(hour=11)
        profile = UserProfile.objects.get(user=self.sam)
        with mock.patch.object(executive, '_send_meeting_invite_email'):
            code, _ = self.call(executive.meeting_participants, self.rae_login,
                                {'user_id': profile.id, 'user_type': 'profile'}, meeting_id=meeting.id)
        self.assertEqual(code, 201)
        self.assertEqual(self.blocks(self.sam, 'exec').count(), 1)

    def test_the_would_this_clash_check_looks_across_agents(self):
        self.on_leave(self.rae)
        agent = mock.Mock()
        agent.check_conflicts.return_value = []
        with mock.patch.object(executive, '_get_agent', return_value=agent):
            code, body = self.call(executive.meeting_check_conflicts, self.rae_login,
                                   {'scheduled_at': self.at(11).isoformat(), 'duration_minutes': 60})
        self.assertEqual(code, 200, body)
        [clash] = body['conflicts']
        self.assertEqual((clash['source'], clash['status'], clash['blocking']), ('leave', 'busy', True))
        self.assertIn('on leave', clash['title'])
        self.assertIs(body['blocking'], True)                                   # the screen must not offer "Add anyway"

    def check(self, actor=None, **data):
        agent = mock.Mock()
        agent.check_conflicts.return_value = data.pop('own', [])
        with mock.patch.object(executive, '_get_agent', return_value=agent):
            code, body = self.call(executive.meeting_check_conflicts, actor or self.rae_login,
                                   {'scheduled_at': self.at(11).isoformat(), 'duration_minutes': 60, **data})
        self.assertEqual(code, 200, body)
        return body

    def test_it_asks_about_the_people_picked_too(self):
        self.busy_elsewhere(self.sam, hour=11)
        self.assertEqual(self.check(), {'status': 'success', 'conflicts': [], 'blocking': False})
        body = self.check(participants=[self.pick(self.sam)])
        self.assertIs(body['blocking'], True)
        self.assertIn('Sam is busy', body['conflicts'][0]['title'])
        self.assertFalse(CompanyUser.objects.filter(email=self.sam.email).exists())     # asking seats nobody
        # A dashboard login picked by another one is asked about through the employee login behind it.
        self.busy_elsewhere(self.rae, hour=11)
        picked = [{'user_id': self.rae_login.id, 'user_type': 'company_user'}]
        self.assertIs(self.check(actor=self.dee_login, participants=picked)['blocking'], True)

    def test_someone_in_another_company_is_not_asked_about(self):
        rival = Company.objects.create(name='Rival', email='rival@test.local')
        outsider = get_user_model().objects.create_user('otto', email='otto@rival.local', password='x')
        UserProfile.objects.update_or_create(user=outsider, defaults={'company': rival, 'role': 'team_member'})
        self.busy_elsewhere(outsider, hour=11)
        body = self.check(participants=[self.pick(outsider)])
        self.assertEqual((body['conflicts'], body['blocking']), ([], False))

    def test_and_about_everyone_already_in_a_meeting_being_moved(self):
        meeting = self.meeting(hour=9)
        ExecutiveMeetingParticipant.objects.create(meeting=meeting, company_user=self.seat(self.sam))
        self.busy_elsewhere(self.sam, hour=11)
        self.assertIs(self.check(exclude_meeting_id=meeting.id)['blocking'], True)
        # Its own hour is not in its own way.
        body = self.check(exclude_meeting_id=meeting.id, scheduled_at=self.at(9, 30).isoformat())
        self.assertEqual((body['conflicts'], body['blocking']), ([], False))
        # Somebody else's meeting id tells nothing about the people in it.
        theirs = self.meeting(hour=9, organizer=self.dee_login)
        ExecutiveMeetingParticipant.objects.create(meeting=theirs, company_user=CompanyUser.objects.get(email=self.sam.email))
        self.assertIs(self.check(actor=self.dee_login, exclude_meeting_id=meeting.id)['blocking'], False)

    def test_a_login_with_no_calendar_is_only_warned_as_before(self):
        own = [{'id': 5, 'title': 'Weekly sync', 'status': 'scheduled'}]
        body = self.check(actor=self.dee_login, own=own)
        self.assertEqual((body['conflicts'], body['blocking']), (own, False))

    def test_an_executive_meeting_in_the_way_is_listed_once(self):
        mine = self.meeting(hour=11)
        agent = mock.Mock()
        agent.check_conflicts.return_value = [{'id': mine.id, 'title': mine.title}]   # the agent's own answer
        with mock.patch.object(executive, '_get_agent', return_value=agent):
            _, body = self.call(executive.meeting_check_conflicts, self.rae_login,
                                {'scheduled_at': self.at(11).isoformat(), 'duration_minutes': 60})
        # Once, in the agent's own words, and marked as something that will be refused.
        self.assertEqual(body['conflicts'], [{'id': mine.id, 'title': mine.title, 'blocking': True}])
        self.assertIs(body['blocking'], True)

    def test_a_meeting_typed_as_a_request_is_not_made_over_something_else(self):
        self.busy_elsewhere(self.rae, hour=11)
        agent = mock.Mock()
        agent.parse_meeting_request.return_value = {'title': 'Strategy', 'scheduled_at': self.at(11).isoformat(),
                                                    'duration_minutes': 60}
        agent.check_conflicts.return_value = []
        with mock.patch.object(executive, '_get_agent', return_value=agent):
            code, body = self.call(executive.schedule_meeting_ai, self.rae_login,
                                   {'message': 'strategy at 11', 'create': True})
        self.assertEqual(code, 200, body)
        self.assertEqual(len(body['conflicts']), 1)
        self.assertEqual(ExecutiveMeeting.objects.count(), 0)


class MeetingsPageTests(BothLoginsTestCase):
    """Both kinds are on the employee's own Meetings page."""

    def meetings(self, user):
        request = self.factory.get('/')
        force_authenticate(request, user=user)
        response = notification.meeting_list_for_user(request)
        response.render()
        return json.loads(response.content)['data']['meetings']

    def test_a_salesperson_sees_their_booked_calls(self):
        SDRMeeting.objects.create(company_user=self.rae_login, lead=self.lead, status='scheduled',
                                  scheduled_at=self.at(10), title='Discovery call', calendar_link='https://meet.example/x')
        SDRMeeting.objects.create(company_user=self.rae_login, lead=self.lead, status='cancelled',
                                  scheduled_at=self.at(12), title='Called off')
        [item] = self.meetings(self.rae)
        self.assertEqual((item['source'], item['source_label'], item['title'], item['my_status'],
                          item['meeting_link'], item['can_respond']),
                         ('sdr', 'Sales call', 'Discovery call', 'organizer', 'https://meet.example/x', False))
        self.assertEqual(self.meetings(self.sam), [])                           # not a colleague's

    def test_an_employee_sees_the_executive_meetings_they_are_in(self):
        meeting = ExecutiveMeeting.objects.create(organizer=self.dee_login, title='Board prep', scheduled_at=self.at(10))
        seat = CompanyUser.objects.create(company=self.company, email=self.sam.email, full_name='Sam',
                                          role='company_user', password_hash='x', is_active=False)
        ExecutiveMeetingParticipant.objects.create(meeting=meeting, company_user=seat, response='accepted')
        ExecutiveMeeting.objects.create(organizer=self.dee_login, title='Not invited', scheduled_at=self.at(12))
        [item] = self.meetings(self.sam)
        self.assertEqual((item['source'], item['source_label'], item['title'], item['my_status'], item['organizer_name']),
                         ('exec', 'Executive meeting', 'Board prep', 'accepted', 'Dee Dashboard'))
        # The organiser, signed in to My Space, sees the ones they run.
        mine = ExecutiveMeeting.objects.create(organizer=self.rae_login, title='Rae runs this', scheduled_at=self.at(14))
        self.assertEqual([(i['title'], i['my_status']) for i in self.meetings(self.rae)], [('Rae runs this', 'organizer')])
        mine.status = 'cancelled'
        mine.save()
        self.assertEqual(self.meetings(self.rae), [])

    def test_an_executive_meeting_is_shown_at_the_hour_it_really_is(self):
        self.company.timezone_name = 'Asia/Karachi'
        self.company.save()
        ExecutiveMeeting.objects.create(organizer=self.rae_login, title='Board prep', scheduled_at=self.at(11))
        [item] = self.meetings(self.rae)
        # Typed as 11:00 in Karachi. The page prints an instant on the reader's own clock.
        self.assertEqual(datetime.fromisoformat(item['proposed_time']), self.at(6))

    def test_another_companys_meetings_never_appear(self):
        rival = Company.objects.create(name='Rival', email='rival@test.local')
        twin = self.dashboard('sam@test.local', 'Sam Elsewhere', company=rival)     # the same address, another company
        ExecutiveMeeting.objects.create(organizer=twin, title='Theirs', scheduled_at=self.at(10))
        self.assertEqual(self.meetings(self.sam), [])

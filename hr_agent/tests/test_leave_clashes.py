"""Approving leave shows the meetings it lands on, and tells whoever runs them.

Approving used to change the request and the balance, and nothing else. The
meetings and interviews the person was already booked into stayed as they
were. The approver saw no warning and no organiser was told: the shared
calendar only refused new bookings from then on.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core import mail
from django.utils import timezone

from api.views import hr_agent as views
from core.models import Notification
from core.notification_settings import topic_for_kind
from Frontline_agent.models import FrontlineMeeting
from hr_agent import leave_clashes
from hr_agent.models import HRMeeting
from project_manager_agent.models import MeetingParticipant, PMNotification, ScheduledMeeting
from recruitment_agent.models import Interview

from .base import HRTestCase

UTC = ZoneInfo('UTC')


def bell(company_user):
    return list(PMNotification.objects.filter(company_user=company_user, data__kind='hr_leave_clash').order_by('id'))


class LeaveClashTests(HRTestCase):

    def setUp(self):
        super().setUp()
        # Sam is going on leave. Lee organises from My Space only.
        self.sam = self.employee_with_login('sam', 'Sam Staff', self.company, self.admin)
        self.lee = self.employee_with_login('lee', 'Lee Lead', self.company, self.admin)
        self.day = timezone.now().date() + timedelta(days=14)
        while self.day.weekday() >= 5:
            self.day += timedelta(days=1)
        self.leave = self.leave_request(self.sam, start_date=self.day, end_date=self.day + timedelta(days=2))

    def at(self, hour, day=0):
        return datetime.combine(self.day + timedelta(days=day), time(hour), tzinfo=UTC)

    # ---- one booking in each agent, all with Sam in them -------------------------------

    def pm_meeting(self, hour=10, organizer=None, title='Sprint review'):
        meeting = ScheduledMeeting.objects.create(organizer=organizer or self.member, title=title,
                                                  proposed_time=self.at(hour), duration_minutes=60)
        MeetingParticipant.objects.create(meeting=meeting, user=self.sam.user, status='accepted')
        return meeting

    def hr_meeting(self, hour=12, organizer=None, **fields):
        meeting = HRMeeting.objects.create(company=self.company, title=fields.pop('title', 'Sam 1:1'),
                                           organizer=organizer or self.admin_emp,
                                           scheduled_at=self.at(hour), duration_minutes=30, **fields)
        meeting.participants.set([self.sam.id])
        return meeting

    def frontline_meeting(self, hour=14, organizer=None):
        meeting = FrontlineMeeting.objects.create(company=self.company, title='Customer call',
                                                  organizer=organizer or self.member.login_user,
                                                  scheduled_at=self.at(hour), duration_minutes=30, status='scheduled')
        meeting.participants.set([self.sam.user_id])
        return meeting

    def interview(self, hour=16):
        interview = Interview.objects.create(candidate_name='Cara Candidate', candidate_email='cara@test.local',
                                             job_role='Backend', available_slots_json='[]', company_user=self.member,
                                             status='SCHEDULED', timezone_name='UTC', scheduled_datetime=self.at(hour))
        interview.interviewers.add(self.sam.user)
        return interview

    def clashes(self, actor=None, **params):
        request = self.factory.get('/', params)
        from rest_framework.test import force_authenticate
        force_authenticate(request, user=actor or self.admin)
        response = views.leave_request_clashes(request, request_id=self.leave.id)
        response.render()
        import json
        return response.status_code, json.loads(response.content)

    def approve(self, actor=None, action='approve'):
        with self.captureOnCommitCallbacks(execute=True):
            code, body = self.call(views.decide_leave_request, actor or self.admin, {'action': action},
                                   request_id=self.leave.id)
        self.assertEqual(code, 200, body)
        return body['data']

    # ---- what the approver is shown ------------------------------------------------------

    def test_the_approver_sees_every_booking_the_leave_lands_on_soonest_first(self):
        self.interview(), self.frontline_meeting(), self.hr_meeting(), self.pm_meeting()
        code, body = self.clashes()
        self.assertEqual(code, 200, body)
        data = body['data']
        self.assertEqual((data['checked'], data['why'], data['count']), (True, '', 4))
        self.assertEqual([c['kind'] for c in data['clashes']],
                         ['Project Manager meeting', 'HR meeting', 'Frontline meeting', 'Interview'])
        first = data['clashes'][0]
        self.assertEqual((first['title'], first['source']), ('Sprint review', 'pm'))
        self.assertIn('10:00 AM–11:00 AM', first['when'])

    def test_times_are_written_on_the_viewers_clock(self):
        self.pm_meeting(hour=10)
        _, body = self.clashes(timezone='Asia/Karachi')
        self.assertIn('3:00 PM–4:00 PM', body['data']['clashes'][0]['when'])

    def test_bookings_outside_the_leave_are_not_listed(self):
        ScheduledMeeting.objects.filter(pk=self.pm_meeting().pk).update(proposed_time=self.at(10, day=3))
        ScheduledMeeting.objects.get().save()                       # the day after the leave ends
        self.assertEqual(self.clashes()[1]['data']['count'], 0)

    def test_nor_are_other_peoples_or_other_leave_of_theirs(self):
        other = ScheduledMeeting.objects.create(organizer=self.member, title='Not Sam', proposed_time=self.at(10))
        MeetingParticipant.objects.create(meeting=other, user=self.lee.user, status='accepted')
        self.leave_request(self.sam, status='approved', start_date=self.day, end_date=self.day)   # already off that day
        self.assertEqual(self.clashes()[1]['data']['clashes'], [])

    def test_a_meeting_they_declined_is_not_a_clash(self):
        meeting = self.pm_meeting()
        MeetingParticipant.objects.filter(meeting=meeting).update(status='rejected')
        meeting.save()
        self.assertEqual(self.clashes()[1]['data']['count'], 0)

    def test_a_morning_off_lists_only_the_morning(self):
        self.leave.end_date = self.day
        self.leave.partial_day_period = 'morning'
        self.leave.save()
        self.pm_meeting(hour=10), self.frontline_meeting(hour=14)
        self.assertEqual([c['source'] for c in self.clashes()[1]['data']['clashes']], ['pm'])

    # ---- what stays private ------------------------------------------------------------------

    def test_an_interviews_title_is_shown_to_nobody(self):
        self.interview()
        [row] = self.clashes()[1]['data']['clashes']
        self.assertEqual((row['kind'], row['title']), ('Interview', None))

    def test_a_private_hr_meeting_shows_its_title_to_an_hr_admin_only(self):
        self.hr_meeting(title='Exit interview', visibility='private')
        self.assertEqual(self.clashes(self.admin)[1]['data']['clashes'][0]['title'], 'Exit interview')
        # A manager who is the approver, and not in HR, sees that it is an HR meeting and no more.
        self.leave.approver = self.member_emp
        self.leave.save()
        [row] = self.clashes(self.member)[1]['data']['clashes']
        self.assertEqual((row['kind'], row['title']), ('HR meeting', None))

    # ---- who may look, and when it cannot say ----------------------------------------------

    def test_only_someone_who_may_decide_it_sees_the_list(self):
        self.pm_meeting()
        self.assertEqual(self.clashes(self.member)[0], 403)         # a colleague
        self.assertEqual(self.clashes(self.rival_admin)[0], 404)    # another company
        self.leave.approver = self.member_emp
        self.leave.save()
        self.assertEqual(self.clashes(self.member)[0], 200)         # the named approver

    def test_someone_with_no_employee_login_cannot_be_checked_and_it_says_so(self):
        from hr_agent.models import Employee
        paper = Employee.objects.create(company=self.company, full_name='Pat Paper', work_email='pat@elsewhere.example')
        self.leave = self.leave_request(paper, start_date=self.day, end_date=self.day)
        data = self.clashes()[1]['data']
        self.assertEqual((data['checked'], data['why'], data['clashes']), (False, 'no_login', []))

    def test_leave_of_a_few_hours_cannot_be_checked_either(self):
        self.pm_meeting()
        self.leave.end_date = self.day
        self.leave.partial_day_period = 'hours'
        self.leave.save()
        data = self.clashes()[1]['data']
        self.assertEqual((data['checked'], data['why'], data['count']), (False, 'hours', 0))

    # ---- once it is approved: whoever runs each meeting is told ------------------------------

    def test_each_organiser_is_told_once_for_each_meeting_with_where_to_go(self):
        self.pm_meeting(), self.frontline_meeting(), self.interview()            # all three run by Mo
        self.hr_meeting()                                                        # run by Dana, who is approving
        data = self.approve()
        self.assertEqual((data['booked_during'], data['organisers_told']), (4, 4))
        alerts = bell(self.member)
        self.assertEqual([a.data['link'] for a in alerts],
                         ['/project-manager/dashboard?tab=meeting-scheduler', '/frontline/dashboard',
                          '/recruitment/interviews'])
        self.assertEqual({a.title for a in alerts}, {'Sam Staff will be on leave during a meeting you run'})
        self.assertIn('"Sprint review"', alerts[0].message)
        self.assertIn('10:00 AM', alerts[0].message)
        self.assertIn('has not been changed', alerts[0].message)
        self.assertIn('the interview with Cara Candidate', alerts[2].message)   # theirs to see: they run it
        [hr_alert] = bell(self.admin)
        self.assertEqual(hr_alert.data['link'], '/hr/dashboard?tab=meetings')
        self.assertEqual(hr_alert.severity, 'warning')

    def test_an_organiser_with_only_my_space_is_told_there_and_by_email(self):
        self.hr_meeting(organizer=self.lee)
        self.approve()
        [alert] = Notification.objects.filter(user=self.lee.user)
        self.assertEqual((alert.title, alert.action_url, alert.type),
                         ('Sam Staff will be on leave during a meeting you run', '/me/meetings', 'hr_leave_clash'))
        self.assertIn(['lee@test.local'], [m.to for m in mail.outbox])

    def test_so_is_one_whose_dashboard_login_is_switched_off(self):
        old = self.login(self.company, 'lee@test.local', 'Lee Lead', 'company_user')
        old.is_active = False
        old.save()
        self.hr_meeting(organizer=self.lee)
        self.assertEqual(self.approve()['organisers_told'], 1)
        self.assertEqual(Notification.objects.filter(user=self.lee.user, type='hr_leave_clash').count(), 1)

    def test_nobody_is_told_about_a_meeting_they_run_themselves(self):
        self.hr_meeting(organizer=self.sam)                          # Sam's own meeting
        data = self.approve()
        self.assertEqual((data['booked_during'], data['organisers_told']), (1, 0))
        self.assertFalse(Notification.objects.filter(user=self.sam.user, type='hr_leave_clash').exists())

    def test_nor_someone_who_runs_theirs_from_a_dashboard_login(self):
        # Kim has both logins, organises a meeting from the dashboard, and is the one going on leave.
        kim = self.employee_with_login('kim', 'Kim Both', self.company, self.admin)
        kim_login = self.login(self.company, 'kim@test.local', 'Kim Both', 'company_user')
        self.leave = self.leave_request(kim, start_date=self.day, end_date=self.day)
        ScheduledMeeting.objects.create(organizer=kim_login, title='Kim runs this', proposed_time=self.at(10))
        data = self.approve()
        self.assertEqual((data['booked_during'], data['organisers_told']), (1, 0))
        self.assertEqual(bell(kim_login), [])

    def test_a_meeting_nobody_runs_stops_nothing(self):
        HRMeeting.objects.create(company=self.company, title='No organiser', scheduled_at=self.at(9),
                                 duration_minutes=30).participants.set([self.sam.id])
        self.pm_meeting(hour=11)
        self.assertEqual(self.approve()['organisers_told'], 1)
        self.assertEqual(len(bell(self.member)), 1)

    def test_a_meeting_that_has_gone_is_skipped_and_the_rest_are_still_told(self):
        from core.models import CalendarBlock
        CalendarBlock.objects.create(                                # a calendar row whose meeting no longer exists
            company=self.company, user=self.sam.user, source='pm', source_id=987654, role='participant',
            response='accepted', title='Deleted behind the calendar',
            starts_at=self.at(9), ends_at=self.at(10))
        self.frontline_meeting()
        data = self.approve()
        self.assertEqual((data['booked_during'], data['organisers_told']), (2, 1))

    def test_an_interview_run_by_an_older_recruiter_record_reaches_their_login(self):
        interview = self.interview()
        Interview.objects.filter(pk=interview.pk).update(company_user=None, recruiter=self.member.login_user)
        self.assertEqual(self.approve()['organisers_told'], 1)
        self.assertEqual(len(bell(self.member)), 1)

    def test_the_person_going_on_leave_is_told_they_are_still_booked(self):
        self.pm_meeting(), self.frontline_meeting()
        self.approve()
        [alert] = Notification.objects.filter(user=self.sam.user, type='hr_leave_decided')
        self.assertIn('still booked into 2 meetings', alert.message)
        self.assertIn('whoever runs them has been told', alert.message)

    def test_and_one_meeting_is_called_one(self):
        self.pm_meeting()
        self.approve()
        [alert] = Notification.objects.filter(user=self.sam.user, type='hr_leave_decided')
        self.assertIn('still booked into 1 meeting in that time; whoever runs it has been told', alert.message)

    def test_with_nothing_booked_nothing_more_is_said(self):
        data = self.approve()
        self.assertEqual((data['booked_during'], data['organisers_told']), (0, 0))
        [alert] = Notification.objects.filter(user=self.sam.user)
        self.assertNotIn('booked', alert.message)

    def test_a_rejection_tells_no_organiser(self):
        self.pm_meeting()
        data = self.approve(action='reject')
        self.assertEqual((data['booked_during'], data['organisers_told']), (0, 0))
        self.assertEqual(bell(self.member), [])

    def test_the_meetings_themselves_are_left_alone(self):
        meeting = self.pm_meeting()
        self.approve()
        meeting.refresh_from_db()
        self.assertEqual((meeting.status, meeting.proposed_time), ('pending', self.at(10)))
        self.assertEqual(MeetingParticipant.objects.get(meeting=meeting).status, 'accepted')

    def test_a_long_leave_tells_about_the_first_twenty(self):
        for n in range(leave_clashes.LIMIT + 3):
            self.pm_meeting(hour=n % 8 + 8, title=f'Meeting {n}')
        ScheduledMeeting.objects.update(proposed_time=self.at(9))    # all in the leave; the calendar is rebuilt below
        for meeting in ScheduledMeeting.objects.all():
            meeting.save()
        data = self.approve()
        self.assertEqual((data['booked_during'], data['organisers_told']),
                         (leave_clashes.LIMIT + 3, leave_clashes.LIMIT))
        listed = self.clashes()[1]['data']                           # the dialog counts them all and lists twenty
        self.assertEqual((listed['count'], len(listed['clashes'])), (leave_clashes.LIMIT + 3, leave_clashes.LIMIT))

    def test_the_alert_has_its_own_topic(self):
        topic = topic_for_kind('hr_leave_clash')
        self.assertEqual((topic.key, topic.agent, topic.email_default), ('leave_clashes', 'hr_agent', False))

"""Interviews in the recruiter's own timezone, and on the shared calendar.

Two faults, fixed together because they live in the same code:

  * A recruiter's slots ("10:00") were read as UTC. The candidate was told
    10:00 AM, but the Meet event, the reminders and the recruiter's own
    dashboard all used 10:00 UTC — 3 PM for a recruiter in Karachi.
  * Interviews weren't on the calendar PM, HR and Frontline share, so a
    recruiter could be booked into a meeting and an interview at once. They
    also had no length and no interviewers besides the recruiter.
"""
from datetime import datetime, time, timedelta, timezone as dt_timezone
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from core.models import CalendarBlock, Company, CompanyModulePurchase, CompanyUser, UserProfile
from core.scheduling import ScheduleConflict, ensure_free
from recruitment_agent import interview_time
from recruitment_agent.agents.interview_scheduling import interview_scheduling_agent as scheduling
from recruitment_agent.models import Interview, RecruiterInterviewSettings

KARACHI = ZoneInfo('Asia/Karachi')      # UTC+5, no daylight saving


def employee_login(company, email, first_name):
    user = get_user_model().objects.create_user(
        username=email.split('@')[0], email=email, password='x', first_name=first_name)
    UserProfile.objects.update_or_create(user=user, defaults={'company': company, 'role': 'team_member'})
    return user


# The function itself, for the tests of it: the class below replaces it for every other test.
_real_google_link = scheduling._create_google_meet_link


@mock.patch.object(scheduling, '_create_google_meet_link', return_value=None)
@mock.patch.object(scheduling.InterviewSchedulingAgent, 'send_confirmation_email', return_value=True)
@mock.patch.object(scheduling.InterviewSchedulingAgent, 'send_reschedule_email', return_value=True)
class InterviewSchedulingTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        # A candidate can only book with a company that has Recruitment.
        CompanyModulePurchase.objects.create(company=self.company, module_name='recruitment_agent',
                                             status='active', is_complimentary=True)
        self.recruiter = CompanyUser.objects.create(
            company=self.company, email='rae@test.local', full_name='Rae Recruiter',
            role='admin', password_hash='x', is_active=True)
        # The recruiter's employee login (same email), and a colleague.
        self.rae = employee_login(self.company, 'rae@test.local', 'Rae')
        self.sam = employee_login(self.company, 'sam@test.local', 'Sam')

        # Ten days out, a weekday, at 10:00 and 11:00 on the recruiter's clock.
        self.day = timezone.now().astimezone(KARACHI).date() + timedelta(days=10)
        while self.day.weekday() >= 5:
            self.day += timedelta(days=1)
        self.slot10, self.slot11 = f'{self.day}T10:00', f'{self.day}T11:00'
        self.settings = RecruiterInterviewSettings.objects.create(
            company_user=self.recruiter, job=None, timezone_name='Asia/Karachi',
            start_time=time(9, 0), end_time=time(17, 0), interview_time_gap=45,
            time_slots_json=[{'date': str(self.day), 'time': t, 'datetime': f'{self.day}T{t}',
                              'available': True} for t in ('10:00', '11:00')])
        self.interview = self.new_interview('Cara Candidate')

    def new_interview(self, name):
        return Interview.objects.create(
            candidate_name=name, candidate_email=f'{name.split()[0].lower()}@test.local',
            job_role='Backend engineer', available_slots_json='[]', company_user=self.recruiter,
            confirmation_token=f'token-{name.split()[0].lower()}')

    def at(self, hour):
        return datetime.combine(self.day, time(hour, 0), tzinfo=KARACHI)

    def book(self, interview=None, slot=None):
        return scheduling.InterviewSchedulingAgent().confirm_slot(
            (interview or self.interview).id, slot or self.slot10)

    def test_booking_keeps_the_google_event_so_it_can_follow_the_interview(self, *_):
        # The event's id was thrown away: an interview that moved stayed in Google at its old time.
        from core.google_calendar import event_state
        self.interview.scheduled_datetime = self.at(10)
        made = {'event_id': 'ev-7', 'meet_url': 'https://meet.google.com/xyz'}
        with mock.patch('core.google_calendar.create_google_event', return_value=made) as create:
            link = _real_google_link(self.interview, 45)
        self.assertEqual(link, 'https://meet.google.com/xyz')
        self.assertEqual(create.call_args.kwargs['duration_minutes'], 45)
        self.assertEqual((self.interview.google_event_id, self.interview.google_event_state),
                         ('ev-7', event_state(self.at(10), 45)))

    def test_without_google_there_is_no_event_to_keep(self, *_):
        with mock.patch('core.google_calendar.create_google_event', return_value=None):
            self.assertIsNone(_real_google_link(self.interview, 45))
        self.assertEqual((self.interview.google_event_id, self.interview.google_event_state), ('', ''))

    def test_the_event_made_at_booking_is_saved_with_the_interview(self, *_):
        def google(interview, minutes):
            interview.google_event_id, interview.google_event_state = 'ev-7', 'as-booked'
            return 'https://meet.google.com/xyz'
        with mock.patch.object(scheduling, '_create_google_meet_link', side_effect=google):
            self.assertTrue(self.book()['success'])
        saved = Interview.objects.get(pk=self.interview.pk)
        self.assertEqual((saved.google_event_id, saved.google_event_state, saved.meeting_link),
                         ('ev-7', 'as-booked', 'https://meet.google.com/xyz'))

    def busy(self, user, hour, source='pm'):
        return CalendarBlock.objects.create(
            company=self.company, user=user, starts_at=self.at(hour),
            ends_at=self.at(hour) + timedelta(hours=1), source=source, source_id=999,
            role='participant', response='accepted', title='Roadmap review')

    # ---- the recruiter's timezone ---------------------------------------------

    def test_10_am_is_the_recruiters_10_am(self, *_):
        result = self.book()
        self.assertTrue(result['success'], result)
        self.interview.refresh_from_db()
        # 10:00 in Karachi is 05:00 UTC. It used to be stored as 10:00 UTC.
        self.assertEqual(self.interview.scheduled_datetime.astimezone(dt_timezone.utc).hour, 5)
        self.assertEqual(self.interview.timezone_name, 'Asia/Karachi')

    def test_the_booked_time_is_shown_with_its_zone(self, *_):
        self.book()
        self.interview.refresh_from_db()
        self.assertIn('10:00 AM', self.interview.selected_slot)
        self.assertIn('Asia/Karachi', self.interview.selected_slot)
        self.assertIn('UTC+05:00', self.interview.selected_slot)

    def test_a_slot_lasts_as_long_as_the_gap_between_slots(self, *_):
        self.book()
        self.interview.refresh_from_db()
        self.assertEqual(self.interview.duration_minutes, 45)

    def test_without_a_known_zone_times_are_utc_as_before(self, *_):
        self.settings.timezone_name = ''
        self.settings.save()
        self.book()
        self.interview.refresh_from_db()
        self.assertEqual(self.interview.scheduled_datetime.astimezone(dt_timezone.utc).hour, 10)

    def test_the_candidate_page_says_which_zone_and_gives_exact_times(self, *_):
        request = RequestFactory().get('/')
        from recruitment_agent.views import get_available_slots_for_interview
        import json
        data = json.loads(get_available_slots_for_interview(request, self.interview.confirmation_token).content)
        self.assertEqual(data['timezone'], 'Asia/Karachi')
        self.assertIn('UTC+05:00', data['timezone_caption'])
        [ten] = [s for s in data['time_slots'] if s['datetime'] == self.slot10]
        self.assertTrue(ten['iso'].endswith('+05:00'))

    def test_the_browser_zone_fills_a_blank_but_never_overwrites(self, *_):
        self.settings.timezone_name = ''
        self.settings.save()
        interview_time.remember_timezone(self.recruiter, 'Europe/London')
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.timezone_name, 'Europe/London')
        interview_time.remember_timezone(self.recruiter, 'America/New_York')
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.timezone_name, 'Europe/London')

    def test_an_interview_booked_before_zones_keeps_showing_as_it_did(self, *_):
        # Stored as clock digits in UTC; must not be shifted by the zone now known.
        self.interview.scheduled_datetime = datetime.combine(self.day, time(10, 0), tzinfo=dt_timezone.utc)
        self.interview.status = 'SCHEDULED'
        self.interview.save()
        self.assertIn('10:00 AM', interview_time.when(self.interview))
        # ...and stays off the shared calendar rather than block the wrong hour.
        self.assertFalse(CalendarBlock.objects.filter(source='recruitment').exists())

    def test_the_candidate_page_renders(self, *_):
        from django.test import Client
        response = Client().get(f'/recruitment/interview/select/{self.interview.confirmation_token}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'slotTimezoneNote')
        self.assertContains(response, 'yourTimeNote')

    # ---- the shared calendar --------------------------------------------------

    def test_a_booked_interview_is_busy_time_for_recruiter_and_interviewers(self, *_):
        self.interview.interviewers.add(self.sam)
        self.book()
        blocks = CalendarBlock.objects.filter(source='recruitment', source_id=self.interview.id)
        self.assertEqual(set(blocks.values_list('user_id', flat=True)), {self.rae.id, self.sam.id})
        block = blocks.first()
        self.assertEqual(block.ends_at - block.starts_at, timedelta(minutes=45))
        self.assertTrue(block.is_private)

    def test_other_agents_see_it_as_busy_but_not_who_the_candidate_is(self, *_):
        self.book()
        with self.assertRaises(ScheduleConflict) as caught:
            ensure_free([self.rae.id], self.at(10), 30, viewer_source='hr', suggest=False)
        self.assertIsNone(caught.exception.clashes[0].title)          # no candidate name
        self.assertIn('Interview', caught.exception.text())

    def test_cancelling_frees_the_time(self, *_):
        self.book()
        self.interview.refresh_from_db()
        self.interview.status = 'CANCELLED'
        self.interview.save()
        self.assertFalse(CalendarBlock.objects.filter(source='recruitment').exists())

    def test_a_slot_when_the_recruiter_is_busy_is_not_offered(self, *_):
        self.busy(self.rae, 10)
        request = RequestFactory().get('/')
        from recruitment_agent.views import get_available_slots_for_interview
        import json
        slots = json.loads(get_available_slots_for_interview(
            request, self.interview.confirmation_token).content)['time_slots']
        by_time = {s['datetime']: s for s in slots}
        self.assertTrue(by_time[self.slot10]['taken'])
        self.assertFalse(by_time[self.slot11]['taken'])

    def test_booking_a_busy_slot_is_refused_without_saying_why(self, *_):
        self.busy(self.rae, 10)
        result = self.book()
        self.assertFalse(result['success'])
        self.assertIn('no longer available', result['error'])
        self.assertNotIn('Roadmap', result['error'])
        self.interview.refresh_from_db()
        self.assertEqual(self.interview.status, 'PENDING')
        self.settings.refresh_from_db()
        self.assertFalse(any(s.get('scheduled') for s in self.settings.time_slots_json))

    def test_an_interviewer_who_is_busy_blocks_the_slot_too(self, *_):
        self.interview.interviewers.add(self.sam)
        self.busy(self.sam, 10)
        self.assertFalse(self.book()['success'])

    # ---- the recruiter's dashboard --------------------------------------------

    def call(self, view, method='post', data=None, **kwargs):
        request = getattr(APIRequestFactory(), method)('/', data or {}, format='json')
        force_authenticate(request, user=self.recruiter)
        response = view(request, **kwargs)
        response.render()
        return response.status_code, response.data

    def test_rescheduling_into_a_clash_is_a_409_naming_who_is_busy(self, *_):
        from api.views.recruitment_agent import reschedule_interview
        self.book()
        self.busy(self.rae, 11)
        code, body = self.call(reschedule_interview, interview_id=self.interview.id,
                               data={'new_slot_datetime': self.at(11).isoformat()})
        self.assertEqual(code, 409, body)
        self.assertEqual(body['code'], 'schedule_conflict')
        self.assertIn('Rae', body['message'])

    def test_rescheduling_moves_the_busy_time(self, *_):
        from api.views.recruitment_agent import reschedule_interview
        self.book()
        code, body = self.call(reschedule_interview, interview_id=self.interview.id,
                               data={'new_slot_datetime': self.at(11).isoformat()})
        self.assertEqual(code, 200, body)
        block = CalendarBlock.objects.get(source='recruitment', user=self.rae)
        self.assertEqual(block.starts_at, self.at(11))

    def test_a_new_meeting_link_can_be_resent_to_the_candidate(self, reschedule_email, confirmation_email, _meet):
        # It called a function that isn't defined there; the NameError was
        # caught and logged, so the email never went.
        from api.views.recruitment_agent import update_interview
        self.book()
        confirmation_email.reset_mock()
        code, body = self.call(update_interview, 'patch', {'meeting_link': 'https://meet.example/new',
                                                           'resend_confirmation': True},
                               interview_id=self.interview.id)
        self.assertEqual(code, 200, body)
        confirmation_email.assert_called_once()
        self.assertEqual(confirmation_email.call_args.args[0].meeting_link, 'https://meet.example/new')

    def test_interviewers_must_be_colleagues(self, *_):
        from api.views.recruitment_agent import update_interview
        outsider = employee_login(Company.objects.create(name='Other', email='o@test.local'),
                                  'out@test.local', 'Out')
        code, _ = self.call(update_interview, 'patch', {'interviewer_ids': [outsider.id]},
                            interview_id=self.interview.id)
        self.assertEqual(code, 400)

    def test_adding_a_busy_interviewer_to_a_booked_interview_is_refused(self, *_):
        from api.views.recruitment_agent import update_interview
        self.book()
        self.busy(self.sam, 10)
        code, body = self.call(update_interview, 'patch', {'interviewer_ids': [self.sam.id]},
                               interview_id=self.interview.id)
        self.assertEqual(code, 409, body)
        self.assertFalse(self.interview.interviewers.exists())

    def test_adding_a_free_interviewer_puts_it_on_their_calendar(self, *_):
        from api.views.recruitment_agent import update_interview
        self.book()
        code, body = self.call(update_interview, 'patch', {'interviewer_ids': [self.sam.id]},
                               interview_id=self.interview.id)
        self.assertEqual(code, 200, body)
        self.assertTrue(CalendarBlock.objects.filter(source='recruitment', user=self.sam).exists())

    def test_it_is_on_the_interviewers_meetings_page(self, *_):
        from api.views.notification import meeting_list_for_user
        self.interview.interviewers.add(self.sam)
        self.book()
        request = APIRequestFactory().get('/')
        force_authenticate(request, user=self.sam)
        response = meeting_list_for_user(request)
        [item] = [m for m in response.data['data']['meetings'] if m['source'] == 'recruitment']
        self.assertEqual(item['my_status'], 'scheduled')
        self.assertEqual(item['duration_minutes'], 45)

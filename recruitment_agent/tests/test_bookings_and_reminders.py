"""Booking an interview, setting its time, and reminding the candidate, each done once and right.

CO-112  a second booking address skipped every check: a booked, cancelled or held interview could be booked again
CO-114  'Rescheduled' chosen by hand was never reminded or completed; 'Scheduled' could be set with no time
CO-115  a time set by the recruiter left an online interview with no meeting link
CO-116  the reminder went only within two hours of its time, so short-notice bookings and moves never got one
CO-185  three senders, none checking the others: the same reminder two or three times
"""
from datetime import time, timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import recruitment_agent as views
from core.models import Company, CompanyModulePurchase, CompanyUser
from recruitment_agent import tasks
from recruitment_agent.agents.interview_scheduling import interview_scheduling_agent as scheduling
from recruitment_agent.models import Interview, RecruiterEmailSettings, RecruiterInterviewSettings


class BookingTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        CompanyModulePurchase.objects.create(company=self.company, module_name='recruitment_agent',
                                             status='active', is_complimentary=True)
        self.rae = CompanyUser.objects.create(company=self.company, email='rae@acme.test', full_name='Rae Recruiter',
                                              role='admin', password_hash='x', is_active=True)
        self.day = timezone.now().date() + timedelta(days=5)
        RecruiterInterviewSettings.objects.create(
            company_user=self.rae, job=None, timezone_name='UTC', start_time=time(9, 0), end_time=time(17, 0),
            schedule_from_date=timezone.now().date() - timedelta(days=3), schedule_to_date=self.day,
            time_slots_json=[{'datetime': f'{self.day}T10:00', 'available': True}])
        self.interview = Interview.objects.create(
            candidate_name='Cara Khan', candidate_email='cara@mail.test', job_role='Designer',
            available_slots_json='[]', company_user=self.rae, interview_type='ONLINE', confirmation_token='tok-cara')

    def book(self, when=None):
        with mock.patch.object(scheduling, '_create_google_meet_link', return_value=None), \
                mock.patch.object(scheduling.InterviewSchedulingAgent, 'send_confirmation_email', return_value=True):
            return scheduling.InterviewSchedulingAgent().confirm_slot(self.interview.id, when or f'{self.day}T10:00')

    def update(self, data):
        request = APIRequestFactory().patch('/x', data, format='json')
        force_authenticate(request, user=self.rae)
        return views.update_interview(request, interview_id=self.interview.id)

    # ---- CO-112 ----------------------------------------------------------------------------------

    def test_only_a_waiting_invitation_can_be_booked(self):
        self.assertTrue(self.book()['success'])
        again = self.book(f'{self.day}T10:00')
        self.assertFalse(again['success'])
        self.assertIn("can't be booked from this link", again['error'])
        self.interview.refresh_from_db()
        self.interview.status = 'CANCELLED'
        self.interview.save()
        self.assertFalse(self.book()['success'])

    def test_a_time_gone_is_refused_even_inside_the_booking_period(self):
        yesterday = timezone.now() - timedelta(days=1)
        result = self.book(yesterday.strftime('%Y-%m-%dT%H:%M'))
        self.assertFalse(result['success'])
        self.assertIn('past', result['error'])

    # ---- CO-114 ----------------------------------------------------------------------------------

    def test_scheduled_needs_a_time_and_rescheduled_is_scheduled(self):
        response = self.update({'status': 'SCHEDULED'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Use Reschedule', response.data['message'])
        self.interview.scheduled_datetime = timezone.now() + timedelta(days=2)
        self.interview.save()
        with mock.patch('core.scheduling.ensure_free'):
            response = self.update({'status': 'RESCHEDULED'})
        self.assertEqual(response.status_code, 200, response.data)
        self.interview.refresh_from_db()
        self.assertEqual(self.interview.status, 'SCHEDULED')

    # ---- CO-115 ----------------------------------------------------------------------------------

    def test_a_time_set_by_the_recruiter_gets_a_link_and_says_scheduled(self):
        with mock.patch.object(scheduling, '_create_google_meet_link', return_value=None):
            result = scheduling.InterviewSchedulingAgent().reschedule_interview(
                self.interview.id, f'{self.day}T11:00')
        self.assertTrue(result['success'], result)
        self.interview.refresh_from_db()
        self.assertTrue(self.interview.meeting_link)
        [sent] = mail.outbox
        self.assertTrue(sent.subject.startswith('Interview Scheduled'))
        self.assertIn(self.interview.meeting_link, sent.body)


class ReminderTests(TestCase):

    def setUp(self):
        company = Company.objects.create(name='Acme', email='acme@test.local')
        CompanyModulePurchase.objects.create(company=company, module_name='recruitment_agent', status='active',
                                             is_complimentary=True)
        self.rae = CompanyUser.objects.create(company=company, email='rae@acme.test', full_name='Rae', role='admin',
                                              password_hash='x', is_active=True)
        RecruiterEmailSettings.objects.update_or_create(company_user=self.rae,
                                                        defaults={'reminder_hours_before': 48})
        self.now = timezone.now()

    def booked(self, hours_ahead, booked_hours_ago=72):
        return Interview.objects.create(
            candidate_name='Dev', candidate_email='dev@mail.test', job_role='Backend', status='SCHEDULED',
            available_slots_json='[]', company_user=self.rae, timezone_name='UTC',
            scheduled_datetime=self.now + timedelta(hours=hours_ahead),
            confirmation_sent_at=self.now - timedelta(hours=booked_hours_ago))

    def test_when_a_reminder_is_due(self):
        self.assertTrue(tasks.reminder_due(self.booked(30), self.now))       # the old window missed this
        self.assertFalse(tasks.reminder_due(self.booked(60), self.now))      # not yet
        self.assertFalse(tasks.reminder_due(self.booked(1), self.now))       # under two hours left
        self.assertFalse(tasks.reminder_due(self.booked(30, booked_hours_ago=1), self.now))   # just confirmed

    def test_one_reminder_however_many_runs(self):
        interview = self.booked(30)
        agent = mock.Mock()
        agent.send_pre_interview_reminder.return_value = {'success': True}
        with mock.patch.object(tasks, 'get_interview_agent', return_value=agent):
            tasks.check_and_send_followup_emails()
            tasks.check_and_send_followup_emails()
        agent.send_pre_interview_reminder.assert_called_once_with(interview.id)

    def test_a_failed_reminder_is_tried_again(self):
        interview = self.booked(30)
        agent = mock.Mock()
        agent.send_pre_interview_reminder.return_value = {'success': False, 'error': 'mail server down'}
        with mock.patch.object(tasks, 'get_interview_agent', return_value=agent):
            tasks.check_and_send_followup_emails()
        interview.refresh_from_db()
        self.assertIsNone(interview.pre_interview_reminder_sent_at)

    def test_the_reminder_says_the_real_time_left_and_has_the_link(self):
        interview = self.booked(30)
        interview.meeting_link = 'https://meet.jit.si/PPP-Backend-1'
        interview.interview_type = 'ONLINE'
        interview.save()
        result = scheduling.InterviewSchedulingAgent().send_pre_interview_reminder(interview.id)
        self.assertTrue(result['success'], result)
        [sent] = mail.outbox
        self.assertIn('Tomorrow', sent.subject)
        self.assertIn('https://meet.jit.si/PPP-Backend-1', sent.body)

    def test_saving_an_interview_sends_nothing_by_itself(self):
        self.booked(30)
        self.assertEqual(mail.outbox, [])


class FreedSlotTests(BookingTests):
    """CO-117: a slot freed by a cancellation or a move was greyed out for everyone else for good."""

    def test_a_cancelled_booking_frees_its_slot(self):
        self.assertTrue(self.book()['success'])
        other = Interview.objects.create(candidate_name='Adil Shah', candidate_email='adil@mail.test',
                                         job_role='Designer', available_slots_json='[]', company_user=self.rae,
                                         interview_type='ONLINE', confirmation_token='tok-adil')
        with mock.patch.object(scheduling, '_create_google_meet_link', return_value=None), \
                mock.patch.object(scheduling.InterviewSchedulingAgent, 'send_confirmation_email', return_value=True):
            taken = scheduling.InterviewSchedulingAgent().confirm_slot(other.id, f'{self.day}T10:00')
        self.assertFalse(taken['success'])
        Interview.objects.filter(pk=self.interview.pk).update(status='CANCELLED')
        with mock.patch.object(scheduling, '_create_google_meet_link', return_value=None), \
                mock.patch.object(scheduling.InterviewSchedulingAgent, 'send_confirmation_email', return_value=True):
            freed = scheduling.InterviewSchedulingAgent().confirm_slot(other.id, f'{self.day}T10:00')
        self.assertTrue(freed['success'], freed)

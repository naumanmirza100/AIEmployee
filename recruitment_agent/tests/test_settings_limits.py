"""Recruitment's settings and export keep to sensible limits and say what they mean.

CO-223  follow-up timings of 0 sent a follow-up on every pass; the count had no cap
CO-224  a mistyped end date made hundreds of thousands of interview slots
CO-229  the interviews export wrote times in UTC with no label
CO-230  two leftover commands emailed every waiting candidate of every company on each run
"""
import csv
import io
from datetime import datetime, time, timedelta, timezone as dt_timezone

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import recruitment_agent as views
from core.models import Company, CompanyModulePurchase, CompanyUser
from recruitment_agent.models import Interview, RecruiterEmailSettings, RecruiterInterviewSettings


class SettingsLimitTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        CompanyModulePurchase.objects.create(company=self.company, module_name='recruitment_agent',
                                             status='active', is_complimentary=True)
        self.rae = CompanyUser.objects.create(company=self.company, email='rae@acme.test', full_name='Rae Recruiter',
                                              role='admin', password_hash='x', is_active=True)

    def post(self, view, data):
        request = APIRequestFactory().post('/x', data, format='json')
        force_authenticate(request, user=self.rae)
        return view(request)

    def test_follow_up_timings_have_limits(self):
        response = self.post(views.email_settings, {'followup_delay_hours': 0})
        self.assertEqual(response.status_code, 400)
        self.assertIn('between 1 and 336', response.data['message'])
        response = self.post(views.email_settings, {'max_followup_emails': 50})
        self.assertEqual(response.status_code, 400)
        response = self.post(views.email_settings, {'followup_delay_hours': 24, 'max_followup_emails': 2})
        self.assertEqual(response.status_code, 200, response.data)
        saved = RecruiterEmailSettings.objects.get(company_user=self.rae)
        self.assertEqual((saved.followup_delay_hours, saved.max_followup_emails), (24, 2))

    def test_interview_dates_cover_at_most_90_days(self):
        start = timezone.now().date() + timedelta(days=1)
        response = self.post(views.interview_settings, {
            'schedule_from_date': start.isoformat(), 'schedule_to_date': (start + timedelta(days=36 * 365)).isoformat(),
            'start_time': '09:00', 'end_time': '17:00', 'interview_time_gap': 30})
        self.assertEqual(response.status_code, 400)
        self.assertIn('at most 90 days', response.data['message'])

    def test_the_export_writes_times_in_the_interviews_zone(self):
        Interview.objects.create(candidate_name='Cara', candidate_email='cara@mail.test', job_role='Designer',
                                 available_slots_json='[]', company_user=self.rae, status='SCHEDULED',
                                 timezone_name='Asia/Karachi',
                                 scheduled_datetime=datetime(2026, 11, 2, 5, 0, tzinfo=dt_timezone.utc))
        request = APIRequestFactory().get('/x')
        force_authenticate(request, user=self.rae)
        response = views.export_interviews_csv(request)
        rows = list(csv.DictReader(io.StringIO(response.content.decode('utf-8'))))
        self.assertEqual((rows[0]['Scheduled Date/Time'], rows[0]['Time zone']), ('2026-11-02 10:00', 'Asia/Karachi'))

    def test_the_command_runs_the_one_check(self):
        from unittest import mock
        out = io.StringIO()
        with mock.patch('recruitment_agent.tasks.check_and_send_followup_emails',
                        return_value={'followups_sent': 0, 'reminders_sent': 0, 'errors': 0}) as check:
            call_command('send_interview_followups', stdout=out)
        check.assert_called_once()
        self.assertIn('Follow-ups sent: 0', out.getvalue())

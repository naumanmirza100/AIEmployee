"""The page a candidate opens to pick an interview time.

It is served by the backend itself, from the platform's own address. When no
slot was on offer it wrote the job's title into the page as markup, and a job
title is free text typed by any company's login. The link to every interview's
page was also handed to the dashboard in the interviews list, where no screen
used it.
"""
import re
from datetime import time, timedelta
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import recruitment_agent as views
from core.models import Company, CompanyModulePurchase, CompanyUser
from recruitment_agent.models import Interview, JobDescription, RecruiterInterviewSettings

MARKUP = '<img src=x onerror="window.planted=1">Designer'
PAGE = Path(settings.BASE_DIR) / 'templates' / 'recruitment_agent' / 'candidate_slot_selection.html'


class BookingPageTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        CompanyModulePurchase.objects.create(company=self.company, module_name='recruitment_agent',
                                             status='active', is_complimentary=True)
        self.recruiter = CompanyUser.objects.create(company=self.company, email='rae@test.local',
                                                    full_name='Rae Recruiter', role='admin', password_hash='x',
                                                    is_active=True)
        self.job = JobDescription.objects.create(title=MARKUP, description='Design things well ' * 3,
                                                 company=self.company, company_user=self.recruiter)
        day = timezone.now().date() + timedelta(days=10)
        RecruiterInterviewSettings.objects.create(
            company_user=self.recruiter, job=self.job, timezone_name='Asia/Karachi',
            start_time=time(9, 0), end_time=time(17, 0), interview_time_gap=45,
            schedule_from_date=day, schedule_to_date=day, time_slots_json=[])
        with mock.patch('threading.Thread'):
            self.interview = Interview.objects.create(
                candidate_name='Cara Candidate', candidate_email='cara@test.local', job_role=MARKUP,
                available_slots_json='[]', company_user=self.recruiter, confirmation_token='token-cara')

    def test_the_page_itself_shows_a_title_with_markup_in_it_as_text(self):
        response = Client().get('/recruitment/interview/select/token-cara/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(MARKUP.encode(), response.content)
        self.assertIn(b'&lt;img src=x', response.content)

    def test_the_script_never_writes_the_job_title_as_markup(self):
        source = PAGE.read_text(encoding='utf-8')
        # Every statement that sets innerHTML, up to its semicolon.
        for statement in re.findall(r'innerHTML\s*\+?=[^;]*;', source):
            self.assertNotIn('slotJobTitle', statement)
            self.assertNotIn('jobLabel', statement)
        # ... and where it is used, it is set as text.
        self.assertRegex(source, r'textContent = `[^`]*\$\{jobLabel\}')

    def test_slot_values_are_escaped_before_they_go_into_markup(self):
        source = PAGE.read_text(encoding='utf-8')
        self.assertIn('function esc(', source)
        self.assertNotRegex(source, r'\$\{slot\.datetime\}')
        self.assertNotRegex(source, r'data-date="\$\{dateStr\}"')

    def test_the_interviews_list_does_not_hand_out_the_booking_links(self):
        request = APIRequestFactory().get('/')
        force_authenticate(request, user=self.recruiter)
        response = views.list_interviews(request)
        self.assertEqual(response.status_code, 200)
        [row] = response.data['data']
        self.assertEqual(row['id'], self.interview.id)
        self.assertNotIn('confirmation_token', row)
        self.assertNotIn('token-cara', str(response.data))

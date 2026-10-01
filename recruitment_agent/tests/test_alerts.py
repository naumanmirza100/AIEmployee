"""A candidate booking their interview reaches the recruiter's bell.

It used to be email only; nothing appeared in the app. Also covers the other
alert that never reached a company login: a rejected managed-key request.
"""

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from core.models import Company, CompanyUser
from core.notification_utils import notify_company_user
from project_manager_agent.models import PMNotification
from recruitment_agent.agents.interview_scheduling import interview_scheduling_agent as scheduling
from recruitment_agent.models import Interview


class RecruitmentAlertTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        self.recruiter = CompanyUser.objects.create(
            company=self.company, email='rae@test.local', full_name='Rae Recruiter',
            role='admin', password_hash='x', is_active=True)
        self.interview = Interview.objects.create(
            candidate_name='Cara Candidate', candidate_email='cara@test.local',
            job_role='Backend engineer', available_slots_json='[]',
            company_user=self.recruiter)

    @mock.patch.object(scheduling, '_create_google_meet_link', return_value=None)
    @mock.patch.object(scheduling.InterviewSchedulingAgent, 'send_confirmation_email', return_value=True)
    def test_a_booked_interview_reaches_the_recruiter(self, *_):
        when = (timezone.now() + timedelta(days=3)).replace(hour=11, minute=0, second=0, microsecond=0)
        result = scheduling.InterviewSchedulingAgent().confirm_slot(self.interview.id, when.isoformat())
        self.assertTrue(result['success'], result)
        [alert] = PMNotification.objects.filter(company_user=self.recruiter)
        self.assertEqual(alert.title, 'Interview booked: Cara Candidate')
        self.assertIn('Backend engineer', alert.message)
        self.assertEqual(alert.data['link'], '/recruitment/interviews')

    def test_a_single_login_alert_lands_in_its_bell(self):
        # A rejected managed-key request used this, and went to a table the
        # company login's bell never reads.
        notify_company_user(self.recruiter, title='Managed key request rejected',
                            message='Add your own key.', action_url='/company/settings/api-keys')
        [alert] = PMNotification.objects.filter(company_user=self.recruiter)
        self.assertEqual(alert.data['link'], '/company/settings/api-keys')

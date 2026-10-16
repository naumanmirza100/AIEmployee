"""Someone applying through a job's public page reaches the recruiter's bell.

The applicant was emailed a confirmation and nobody at the company was told.
"""
import shutil
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from api.views import recruitment_agent as recruitment_views
from core.models import CompanyUser
from project_manager_agent.models import PMNotification
from recruitment_agent.models import RecruiterInterviewSettings

from . import test_invitations_go_by_themselves as invitations

MEDIA = tempfile.mkdtemp(prefix='new-application-alert-tests-')


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


@override_settings(MEDIA_ROOT=MEDIA)
class NewApplicationAlertTests(TestCase):

    setUp = invitations.InvitationsGoByThemselvesTests.setUp     # a company with Recruitment, Rae, a job with hours

    def apply(self):
        agents, _ = invitations.screening(['HOLD'], [{'name': 'x', 'email': 'cv@mail.test'}])
        with mock.patch.object(recruitment_views, '_make_agents', return_value=agents), \
                mock.patch('threading.Thread'), mock.patch('time.sleep'), \
                self.captureOnCommitCallbacks(execute=True):
            response = Client().post(f'/api/public/jobs/{self.job.id}/apply/', {
                'first_name': 'Rameez', 'last_name': 'Akbar', 'email': 'rameez@mail.test',
                'phone': '0300 5550101', 'education': 'BS Computer Science',
                'cv_file': SimpleUploadedFile('rameez.pdf', b'%PDF-1.4\n%synthetic\n')})
        self.assertEqual(response.status_code, 201, response.content[:300])

    def alerts(self, who):
        return list(PMNotification.objects.filter(company_user=who, title__startswith='New application'))

    def test_the_job_s_recruiter_is_told_and_the_ai_is_screening_it(self):
        self.apply()
        [alert] = self.alerts(self.rae)
        self.assertEqual(alert.title, 'New application: Rameez Akbar, Designer')
        self.assertIn('The AI is screening it now', alert.message)
        self.assertEqual(alert.data['link'], '/recruitment/candidates')

    def test_without_interview_hours_it_says_what_to_do(self):
        RecruiterInterviewSettings.objects.filter(job=self.job).delete()
        self.apply()
        [alert] = self.alerts(self.rae)
        self.assertIn("set the job's interview hours", alert.message)

    def test_a_job_whose_owner_has_left_tells_an_admin(self):
        self.rae.is_active = False
        self.rae.save(update_fields=['is_active'])
        admin = CompanyUser.objects.create(company=self.company, email='ali@acme.test', full_name='Ali Admin',
                                           role='admin', password_hash='x', is_active=True)
        self.apply()
        self.assertEqual(len(self.alerts(admin)), 1)
        self.assertEqual(self.alerts(self.rae), [])

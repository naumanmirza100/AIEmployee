"""An application from a job's public page is screened as it arrives.

Recruitment's CV screen said public applications "are screened automatically".
Nothing screened them until someone pressed "Process with AI" on the Company
Dashboard. Now applying screens the application in the background, with the same
steps as that button, when the company has Recruitment and the job's interview
hours are set. Otherwise it waits for the button, as before.
"""
import shutil
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from api.views import recruitment_agent as recruitment_views
from core.models import CompanyModulePurchase
from recruitment_agent import applicant_screening
from recruitment_agent.models import CVRecord, JobApplication, RecruiterInterviewSettings

from . import test_invitations_go_by_themselves as invitations

MEDIA = tempfile.mkdtemp(prefix='screened-on-arrival-tests-')
PDF = b'%PDF-1.4\n%synthetic\n'


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


@override_settings(MEDIA_ROOT=MEDIA)
class ScreenedOnArrivalTests(TestCase):

    setUp = invitations.InvitationsGoByThemselvesTests.setUp     # a company with Recruitment, Rae, a job with hours

    def apply(self, decision='INTERVIEW', first='Rameez'):
        agents, invite = invitations.screening([decision], [{'name': 'x', 'email': 'cv@mail.test'}])
        with mock.patch.object(recruitment_views, '_make_agents', return_value=agents), \
                mock.patch('threading.Thread'), mock.patch('time.sleep'), \
                self.captureOnCommitCallbacks(execute=True):
            response = Client().post(f'/api/public/jobs/{self.job.id}/apply/', {
                'first_name': first, 'last_name': 'Akbar', 'email': f'{first.lower()}@mail.test',
                'phone': '0300 5550101', 'education': 'BS Computer Science',
                'cv_file': SimpleUploadedFile('rameez.pdf', PDF)})
        self.assertEqual(response.status_code, 201, response.content[:300])
        return JobApplication.objects.get(email=f'{first.lower()}@mail.test'), invite

    def test_a_strong_application_is_screened_and_invited_without_anyone_pressing_a_button(self):
        application, invite = self.apply('INTERVIEW')
        record = CVRecord.objects.get(job_application=application)
        self.assertEqual((record.qualification_decision, record.job_description_id), ('INTERVIEW', self.job.id))
        invite.assert_called_once()
        asked = invite.call_args.kwargs
        self.assertEqual((asked['candidate_email'], asked['company_user_id']), ('rameez@mail.test', self.rae.id))
        application.refresh_from_db()
        self.assertEqual(application.status, 'shortlisted')

    def test_a_weaker_one_is_screened_and_not_invited(self):
        application, invite = self.apply('HOLD')
        self.assertEqual(CVRecord.objects.get(job_application=application).qualification_decision, 'HOLD')
        invite.assert_not_called()

    def test_it_waits_for_the_button_without_the_agent_or_interview_hours(self):
        RecruiterInterviewSettings.objects.filter(job=self.job).delete()
        application, invite = self.apply(first='Nida')
        self.assertFalse(CVRecord.objects.filter(job_application=application).exists())
        self.assertEqual(applicant_screening.screen_new_application(application.id),
                         'interview hours not set: Interview settings not configured')
        CompanyModulePurchase.objects.filter(company=self.company).update(status='cancelled')
        self.assertEqual(applicant_screening.screen_new_application(application.id), 'no Recruitment agent')
        invite.assert_not_called()

    def test_an_application_already_screened_is_not_screened_again(self):
        application, _ = self.apply('INTERVIEW')
        self.assertEqual(applicant_screening.screen_new_application(application.id), 'already screened')
        self.assertEqual(CVRecord.objects.filter(job_application=application).count(), 1)

    def test_the_applicant_does_not_wait_for_the_ai(self):
        with mock.patch.object(applicant_screening, 'screen_new_application') as screen, \
                override_settings(CELERY_TASK_ALWAYS_EAGER=False), \
                mock.patch.object(applicant_screening.threading, 'Thread') as thread:
            applicant_screening.screen_soon(7)
        screen.assert_not_called()
        thread.return_value.start.assert_called_once()

"""The candidate's "track your application" page follows what Recruitment does.

It said "Under Review" for good, whatever happened, never showed the company's name,
and its address handed back the AI's decision and score to anyone holding the link.
"""
import json
import shutil
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import company_jobs, recruitment_agent as views
from core.models import Company, CompanyModulePurchase, CompanyUser
from recruitment_agent.models import CVRecord, Interview, JobApplication, JobDescription

from . import test_invitations_go_by_themselves as invitations

MEDIA = tempfile.mkdtemp(prefix='tracking-tests-')


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


@override_settings(MEDIA_ROOT=MEDIA)
class TrackingPageTests(TestCase):

    setUp = invitations.InvitationsGoByThemselvesTests.setUp     # a company, Rae, a job with interview hours

    def apply(self, first, number):
        return JobApplication.objects.create(
            job=self.job, first_name=first, last_name='Khan', email=f'{first.lower()}@mail.test',
            phone=f'0300 000000{number}', cv_file_name=f'{first}.pdf', access_token=f'token-{first}',
            cv_file=SimpleUploadedFile(f'{first}.pdf', b'%PDF-1.4 text'))

    def track(self, application):
        response = Client().get(f'/api/public/applications/track/{application.access_token}')
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)['data']

    def screen(self, decisions):
        agents, _ = invitations.screening(decisions, [{'name': 'x', 'email': 'x@mail.test'}] * len(decisions))
        request = APIRequestFactory().post('/x', {}, format='json')
        force_authenticate(request, user=self.rae)
        with mock.patch.object(company_jobs, '_make_agents', return_value=agents), \
                mock.patch('threading.Thread'), mock.patch('time.sleep'):
            response = company_jobs.process_job_applicants(request, jobId=self.job.id)
        self.assertEqual(response.status_code, 200, response.data)

    def status(self, application):
        application.refresh_from_db()
        return application.status

    def test_the_page_names_the_company_and_keeps_the_ai_s_verdict_to_itself(self):
        data = self.track(self.apply('Cara', 1))
        self.assertEqual(data['job']['company_name'], 'Acme')
        self.assertNotIn('cv_record', data)
        self.assertEqual(data['application']['status_label'], 'Under Review')

    def test_screening_shortlists_those_invited_and_marks_the_rest_reviewed(self):
        cara, adil, sara = self.apply('Cara', 1), self.apply('Adil', 2), self.apply('Sara', 3)
        self.screen(['INTERVIEW', 'REJECT', 'HOLD'])
        self.assertEqual([self.status(a) for a in (cara, adil, sara)], ['shortlisted', 'reviewed', 'reviewed'])
        self.assertEqual(self.track(cara)['application']['status_label'], 'Shortlisted')

    def bulk(self, application, decision, emailed=True):
        record = CVRecord.objects.get(job_application=application)
        request = APIRequestFactory().post('/x', {'cv_record_ids': [record.id], 'qualification_decision': decision},
                                           format='json')
        force_authenticate(request, user=self.rae)
        with mock.patch.object(views.InterviewSchedulingAgent, 'send_rejection_email', return_value=emailed), \
                mock.patch.object(views, '_schedule_interview_for_cv_record', return_value=('sent', '')):
            response = views.bulk_update_cv_records(request)
        self.assertEqual(response.status_code, 200, response.data)

    def test_a_person_s_rejection_shows_once_the_candidate_has_been_told(self):
        cara, adil = self.apply('Cara', 1), self.apply('Adil', 2)
        self.screen(['HOLD', 'HOLD'])
        self.bulk(cara, 'REJECT', emailed=True)
        self.bulk(adil, 'REJECT', emailed=False)
        self.assertEqual((self.status(cara), self.status(adil)), ('rejected', 'reviewed'))
        self.bulk(adil, 'INTERVIEW')
        self.assertEqual(self.status(adil), 'shortlisted')

    def test_an_interview_outcome_moves_the_page(self):
        cara, adil = self.apply('Cara', 1), self.apply('Adil', 2)
        self.screen(['INTERVIEW', 'INTERVIEW'])
        for application, outcome, expected in ((cara, 'REJECTED', 'rejected'), (adil, 'HIRED', 'shortlisted')):
            record = CVRecord.objects.get(job_application=application)
            interview = Interview.objects.create(cv_record=record, candidate_name=application.first_name,
                                                 candidate_email=application.email, job_role='Designer',
                                                 status='COMPLETED', company_user=self.rae)
            request = APIRequestFactory().patch('/x', {'outcome': outcome}, format='json')
            force_authenticate(request, user=self.rae)
            with mock.patch('recruitment_agent.hr_handoff.offer', create=True):
                response = views.update_interview(request, interview_id=interview.id)
            self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
            self.assertEqual(self.status(application), expected)

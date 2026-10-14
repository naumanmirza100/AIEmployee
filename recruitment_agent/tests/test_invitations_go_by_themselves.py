"""Screening invites the candidates it approves, by itself.

For one day this was a person's step: screening recorded the AI's decision and
somebody pressed Invite. That was taken back on 13 October 2026. A CV the AI
marks INTERVIEW gets its interview invitation in the same request, from the CV
upload screen and from "process applicants" on a job, and nobody else is
emailed.
"""
import json
import shutil
import tempfile
from datetime import time, timedelta
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import company_jobs, recruitment_agent as views
from core.models import Company, CompanyModulePurchase, CompanyUser
from recruitment_agent.django_repository import DjangoRepository
from recruitment_agent.models import CVRecord, JobApplication, JobDescription, RecruiterInterviewSettings

MEDIA = tempfile.mkdtemp(prefix='recruitment-tests-')


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


def screening(decisions, people):
    """Stand-ins for the AI steps: each CV in turn is the next person and gets the next decision."""
    decisions, people = list(decisions), list(people)
    invite = mock.Mock(return_value={'invitation_sent': True, 'interview_id': 1})
    agents = {
        'cv_agent': mock.Mock(parse_file=lambda path: people.pop(0)),
        'sum_agent': mock.Mock(summarize=mock.Mock(return_value={'role_fit_score': 80})),
        'enrich_agent': mock.Mock(enrich=mock.Mock(return_value={})),
        'qualify_agent': mock.Mock(qualify=lambda *a, **k: {'decision': decisions.pop(0), 'confidence_score': 80,
                                                            'priority': 'HIGH', 'reasoning': 'r'}),
        'job_desc_agent': mock.Mock(parse_text=mock.Mock(return_value={'keywords': ['design']})),
        'interview_agent': mock.Mock(schedule_interview=invite),
        'django_repo': DjangoRepository(),
        'log_service': mock.Mock(),
        'groq_client': mock.Mock(),
    }
    return agents, invite


@override_settings(MEDIA_ROOT=MEDIA)
class InvitationsGoByThemselvesTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        CompanyModulePurchase.objects.create(company=self.company, module_name='recruitment_agent',
                                             status='active', is_complimentary=True)
        self.rae = CompanyUser.objects.create(company=self.company, email='rae@acme.test', full_name='Rae Recruiter',
                                              role='admin', password_hash='x', is_active=True)
        self.job = JobDescription.objects.create(title='Designer', description='Design things well ' * 3,
                                                 company=self.company, company_user=self.rae,
                                                 keywords_json=json.dumps({'keywords': ['design']}))
        day = timezone.now().date() + timedelta(days=10)
        RecruiterInterviewSettings.objects.create(
            company_user=self.rae, job=self.job, timezone_name='Asia/Karachi', start_time=time(9, 0),
            end_time=time(17, 0), interview_time_gap=45, schedule_from_date=day, schedule_to_date=day,
            time_slots_json=[{'date': str(day), 'time': '10:00', 'datetime': f'{day}T10:00', 'available': True}])

    def upload(self, decisions, names):
        """Process hand-uploaded CVs, one decision each. Returns the reply and the invitations asked for."""
        people = [{'name': n.replace('_', ' '), 'email': n.replace('_', '.').lower() + '@mail.test',
                   'skills': ['design']} for n in names]
        agents, invite = screening(decisions, people)
        files = [SimpleUploadedFile(f'{n}.pdf', b'%PDF-1.4 text', content_type='application/pdf') for n in names]
        request = APIRequestFactory().post('/x', {'files': files, 'job_description_id': str(self.job.id)},
                                           format='multipart')
        force_authenticate(request, user=self.rae)
        with mock.patch.object(views, '_make_agents', return_value=agents), \
                mock.patch('threading.Thread'), mock.patch('time.sleep'):
            response = views.process_cvs(request)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data, invite

    def test_an_uploaded_cv_the_ai_approves_is_invited_in_the_same_request(self):
        reply, invite = self.upload(['INTERVIEW'], ['Cara_Khan'])
        invite.assert_called_once()
        asked = invite.call_args.kwargs
        record = CVRecord.objects.get()
        self.assertEqual((asked['candidate_email'], asked['candidate_name'], asked['job_role']),
                         ('cara.khan@mail.test', 'Cara Khan', 'Designer'))
        self.assertEqual((asked['cv_record_id'], asked['company_user_id']), (record.id, self.rae.id))
        self.assertTrue(reply['results'][0]['interview_scheduled'])

    def test_only_the_ones_it_approves_are_invited(self):
        reply, invite = self.upload(['REJECT', 'INTERVIEW', 'HOLD'], ['Adil_Shah', 'Cara_Khan', 'Sara_Ali'])
        self.assertEqual([call.kwargs['candidate_email'] for call in invite.call_args_list], ['cara.khan@mail.test'])
        self.assertEqual(CVRecord.objects.count(), 3)

    def test_a_failed_invitation_does_not_fail_the_screening(self):
        people = [{'name': 'Cara Khan', 'email': 'cara.khan@mail.test', 'skills': ['design']}]
        agents, invite = screening(['INTERVIEW'], people)
        invite.side_effect = RuntimeError('mail server down')
        request = APIRequestFactory().post(
            '/x', {'files': [SimpleUploadedFile('Cara_Khan.pdf', b'%PDF-1.4 text', content_type='application/pdf')],
                   'job_description_id': str(self.job.id)}, format='multipart')
        force_authenticate(request, user=self.rae)
        with mock.patch.object(views, '_make_agents', return_value=agents), \
                mock.patch('threading.Thread'), mock.patch('time.sleep'):
            response = views.process_cvs(request)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(CVRecord.objects.get().qualification_decision, 'INTERVIEW')     # the decision is kept
        self.assertFalse(response.data['results'][0].get('interview_scheduled'))

    def test_a_public_applicant_the_ai_approves_is_invited_at_the_address_they_applied_with(self):
        for number, (first, last) in enumerate((('Cara', 'Khan'), ('Adil', 'Shah')), start=1):
            JobApplication.objects.create(
                job=self.job, first_name=first, last_name=last, email=f'{first}.{last}@mail.test'.lower(),
                phone=f'0300 000000{number}', cv_file_name=f'{first}.pdf',
                cv_file=SimpleUploadedFile(f'{first}.pdf', b'%PDF-1.4 text'))
        people = [{'name': 'from the CV', 'email': 'cv@mail.test'}] * 2
        agents, invite = screening(['INTERVIEW', 'REJECT'], people)
        request = APIRequestFactory().post('/x', {}, format='json')
        force_authenticate(request, user=self.rae)
        with mock.patch.object(company_jobs, '_make_agents', return_value=agents), \
                mock.patch('threading.Thread'), mock.patch('time.sleep'):
            response = company_jobs.process_job_applicants(request, jobId=self.job.id)
        self.assertEqual(response.status_code, 200, response.data)
        invite.assert_called_once()
        invited = invite.call_args.kwargs['candidate_email']
        approved = [r for r in response.data['results'] if r.get('decision') == 'INTERVIEW']
        self.assertEqual(len(approved), 1)
        self.assertTrue(approved[0]['interview_scheduled'])
        self.assertIn(invited, ('cara.khan@mail.test', 'adil.shah@mail.test'))           # the form's address,
        self.assertNotEqual(invited, 'cv@mail.test')                                     # not the one in the CV

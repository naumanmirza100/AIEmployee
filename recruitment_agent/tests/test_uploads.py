"""CV uploads and applicant screening survive a bad file, a failed step and a second run.

CO-102  a .doc or scanned CV could never be read, and nothing said why
CO-180  one unreadable file failed the whole upload after earlier files were saved; uploading again doubled them
CO-181  a failed scoring left an applicant 'AI Analysed' for good; two runs at once screened and invited twice
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
from recruitment_agent import applicant_screening
from recruitment_agent.models import CVRecord, JobApplication, JobDescription, RecruiterInterviewSettings

from .test_invitations_go_by_themselves import screening

MEDIA = tempfile.mkdtemp(prefix='recruitment-uploads-')


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


def reader(people):
    """A CV reader that fails on .doc files and on a file named 'scan', and reads the others in turn."""
    people = list(people)

    def parse(path):
        if path.endswith('.doc'):
            raise ValueError('Unsupported file type: .doc')
        if 'scan' in path:
            raise ValueError('Provided text is empty after cleaning.')
        return people.pop(0)
    return parse


@override_settings(MEDIA_ROOT=MEDIA)
class UploadTests(TestCase):

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
            company_user=self.rae, job=self.job, timezone_name='UTC', start_time=time(9, 0), end_time=time(17, 0),
            schedule_from_date=day, schedule_to_date=day,
            time_slots_json=[{'datetime': f'{day}T10:00', 'available': True}])

    def upload(self, names, people, decisions=None):
        agents, invite = screening(decisions or ['HOLD'] * len(people), [])
        agents['cv_agent'] = mock.Mock(parse_file=reader(people))
        files = [SimpleUploadedFile(n, b'%PDF-1.4 text', content_type='application/pdf') for n in names]
        request = APIRequestFactory().post('/x', {'files': files, 'job_description_id': str(self.job.id)},
                                           format='multipart')
        force_authenticate(request, user=self.rae)
        with mock.patch.object(views, '_make_agents', return_value=agents), \
                mock.patch('threading.Thread'), mock.patch('time.sleep'):
            response = views.process_cvs(request)
        return response.status_code, response.data

    def test_a_bad_file_does_not_stop_the_others_and_says_why(self):
        code, reply = self.upload(['old.doc', 'cara.pdf', 'scan.pdf'],
                                  [{'name': 'Cara Khan', 'email': 'cara@mail.test'}])
        self.assertEqual(code, 200, reply)
        self.assertEqual(CVRecord.objects.count(), 1)
        reasons = {f['file_name']: f['reason'] for f in reply['failed_files']}
        self.assertIn('.docx or PDF', reasons['old.doc'])
        self.assertIn('scanned', reasons['scan.pdf'])

    def test_only_bad_files_is_refused_with_the_reasons(self):
        code, reply = self.upload(['old.doc'], [])
        self.assertEqual(code, 400)
        self.assertIn('old.doc', reply['message'])
        self.assertFalse(CVRecord.objects.exists())

    def test_the_same_person_again_is_not_a_second_candidate(self):
        person = {'name': 'Cara Khan', 'email': 'cara@mail.test'}
        self.upload(['cara.pdf'], [person])
        code, reply = self.upload(['cara-again.pdf'], [dict(person)])
        self.assertEqual(CVRecord.objects.count(), 1)
        self.assertIn('already a candidate', reply['message'] if code == 400 else reply['failed_files'][0]['reason'])

    # ---- public applicants (CO-181) ---------------------------------------------------------------

    def applicant(self, first='Cara'):
        return JobApplication.objects.create(job=self.job, first_name=first, last_name='Khan', phone=f'0300 {first}',
                                             email=f'{first.lower()}@mail.test', cv_file_name=f'{first}.pdf',
                                             cv_file=SimpleUploadedFile(f'{first}.pdf', b'%PDF-1.4 text'))

    def test_a_failed_scoring_leaves_the_applicant_to_screen_again(self):
        app = self.applicant()
        agents, _ = screening(['HOLD'], [{'name': 'Cara Khan', 'email': 'cara@mail.test'}])
        agents['sum_agent'].summarize.side_effect = RuntimeError('AI timed out')
        [result] = applicant_screening.screen(self.job, [app], self.rae, agents)
        self.assertTrue(result['skipped'])
        self.assertFalse(CVRecord.objects.exists())
        self.assertTrue(applicant_screening.not_screened(JobApplication.objects.filter(pk=app.pk)).exists())
        app.refresh_from_db()
        self.assertIsNone(app.screening_started_at)

    def test_a_half_done_record_is_picked_up_and_replaced(self):
        app = self.applicant()
        CVRecord.objects.create(file_name='Cara.pdf', job_description=self.job, job_application=app)   # no decision
        self.assertTrue(applicant_screening.not_screened(JobApplication.objects.filter(pk=app.pk)).exists())
        agents, _ = screening(['HOLD'], [{'name': 'Cara Khan', 'email': 'cara@mail.test'}])
        applicant_screening.screen(self.job, [app], self.rae, agents)
        self.assertEqual(list(CVRecord.objects.values_list('qualification_decision', flat=True)), ['HOLD'])

    def test_an_applicant_another_run_is_screening_is_left_alone(self):
        app = self.applicant()
        JobApplication.objects.filter(pk=app.pk).update(screening_started_at=timezone.now())
        agents, invite = screening(['INTERVIEW'], [{'name': 'Cara Khan', 'email': 'cara@mail.test'}])
        [result] = applicant_screening.screen(self.job, [app], self.rae, agents)
        self.assertEqual(result['reason'], 'Being screened by another run')
        invite.assert_not_called()
        self.assertFalse(CVRecord.objects.exists())

    def test_process_with_ai_screens_only_the_unscreened(self):
        done, waiting = self.applicant('Adil'), self.applicant('Cara')
        CVRecord.objects.create(file_name='Adil.pdf', job_description=self.job, job_application=done,
                                qualification_decision='REJECT')
        agents, _ = screening(['HOLD'], [{'name': 'Cara Khan', 'email': 'cara@mail.test'}])
        request = APIRequestFactory().post('/x', {}, format='json')
        force_authenticate(request, user=self.rae)
        with mock.patch.object(company_jobs, '_make_agents', return_value=agents), \
                mock.patch('threading.Thread'), mock.patch('time.sleep'):
            response = company_jobs.process_job_applicants(request, jobId=self.job.id)
        self.assertEqual([r['application_id'] for r in response.data['results']], [waiting.id])

    def test_top_n_saves_everyones_results(self):
        # CO-227: only the top N were written back; the rest stayed candidates with no score.
        people = [{'name': f'P{n}', 'email': f'p{n}@mail.test'} for n in range(3)]
        agents, invite = screening(['INTERVIEW'] * 3, [])
        agents['cv_agent'] = mock.Mock(parse_file=reader(people))
        files = [SimpleUploadedFile(f'p{n}.pdf', b'%PDF-1.4 text', content_type='application/pdf') for n in range(3)]
        request = APIRequestFactory().post('/x', {'files': files, 'job_description_id': str(self.job.id), 'top_n': '1'},
                                           format='multipart')
        force_authenticate(request, user=self.rae)
        with mock.patch.object(views, '_make_agents', return_value=agents), \
                mock.patch('threading.Thread'), mock.patch('time.sleep'):
            response = views.process_cvs(request)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(CVRecord.objects.filter(qualification_decision='INTERVIEW').count(), 3)
        self.assertEqual(invite.call_count, 1)

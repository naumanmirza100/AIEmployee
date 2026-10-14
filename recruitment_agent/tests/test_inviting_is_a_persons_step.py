"""Screening CVs does not email anybody; a person invites.

The CV screen says 'Upload CV files to analyze and rank candidates'. In the same
request, every CV the AI marked INTERVIEW got an interview record and an
'Interview Invitation' email with a live booking link, with nobody having looked
and no word of it on the screen. The 'process applicants' button for public
applications did the same. And nothing looked for an existing interview first,
so the same person processed twice got two invitations with two working links.
"""
import json
import shutil
import tempfile
from datetime import time, timedelta
from unittest import mock

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import company_jobs, recruitment_agent as views
from core.models import Company, CompanyModulePurchase, CompanyUser
from recruitment_agent.agents.interview_scheduling import InterviewSchedulingAgent
from recruitment_agent.django_repository import DjangoRepository
from recruitment_agent.models import (CVRecord, Interview, JobApplication, JobDescription,
                                      RecruiterInterviewSettings)

MEDIA = tempfile.mkdtemp(prefix='recruitment-tests-')


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


def screening(decisions):
    """Stand-ins for the AI steps: each CV in turn gets the next decision.

    The CV's "text" is its file name, so `Cara_Khan.pdf` is Cara Khan at
    cara.khan@mail.test."""
    queue = list(decisions)

    def parse_file(path):
        return dict(parse_file.next_cv)

    def qualify(*args, **kwargs):
        return {'decision': queue.pop(0), 'confidence_score': 80, 'priority': 'HIGH', 'reasoning': 'r'}

    agents = {
        'cv_agent': mock.Mock(parse_file=parse_file),
        'sum_agent': mock.Mock(summarize=mock.Mock(return_value={'role_fit_score': 80})),
        'enrich_agent': mock.Mock(enrich=mock.Mock(return_value={})),
        'qualify_agent': mock.Mock(qualify=qualify),
        'job_desc_agent': mock.Mock(parse_text=mock.Mock(return_value={'keywords': ['design']})),
        'interview_agent': mock.Mock(),
        'django_repo': DjangoRepository(),
        'log_service': mock.Mock(),
        'groq_client': mock.Mock(),
    }
    return agents, parse_file


@override_settings(MEDIA_ROOT=MEDIA)
class ScreeningTestCase(TestCase):

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

    def upload(self, decisions, names=('Cara_Khan',)):
        """Process hand-uploaded CVs, one decision each. Returns the reply."""
        agents, parse_file = screening(decisions)
        files = []
        for name in names:
            first, last = name.split('_')
            files.append(SimpleUploadedFile(f'{name}.pdf', b'%PDF-1.4 text', content_type='application/pdf'))
        people = iter([{'name': n.replace('_', ' '), 'email': n.replace('_', '.').lower() + '@mail.test',
                        'skills': ['design']} for n in names])

        def next_person(path):
            return next(people)
        agents['cv_agent'].parse_file = next_person

        request = APIRequestFactory().post('/x', {'files': files, 'job_description_id': str(self.job.id)},
                                           format='multipart')
        force_authenticate(request, user=self.rae)
        with mock.patch.object(views, '_make_agents', return_value=agents), \
                mock.patch('threading.Thread'), mock.patch('time.sleep'), \
                mock.patch.object(InterviewSchedulingAgent, 'schedule_interview') as invite:
            response = views.process_cvs(request)
        self.assertEqual(response.status_code, 200, response.data)
        invite.assert_not_called()
        return response.data

    def applicant(self, first, last):
        return JobApplication.objects.create(
            job=self.job, first_name=first, last_name=last, email=f'{first}.{last}@mail.test'.lower(),
            phone=f'0300 {abs(hash(first)) % 10**7:07d}', cv_file=SimpleUploadedFile(f'{first}.pdf', b'%PDF-1.4 text'),
            cv_file_name=f'{first}.pdf')

    def process_applicants(self, decisions):
        agents, parse_file = screening(decisions)
        agents['cv_agent'].parse_file = lambda path: {'name': 'from the CV', 'email': 'cv@mail.test'}
        request = APIRequestFactory().post('/x', {}, format='json')
        force_authenticate(request, user=self.rae)
        with mock.patch.object(company_jobs, '_make_agents', return_value=agents), \
                mock.patch('threading.Thread'), mock.patch('time.sleep'), \
                mock.patch.object(InterviewSchedulingAgent, 'schedule_interview') as invite:
            response = company_jobs.process_job_applicants(request, jobId=self.job.id)
        self.assertEqual(response.status_code, 200, response.data)
        invite.assert_not_called()
        return response.data

    def decide(self, records, decision='INTERVIEW'):
        """The person's step: move candidates to a decision, as the Candidates screen does."""
        request = APIRequestFactory().post(
            '/x', {'cv_record_ids': [r.id for r in records], 'qualification_decision': decision}, format='json')
        force_authenticate(request, user=self.rae)
        with mock.patch('threading.Thread'), \
                mock.patch.object(InterviewSchedulingAgent, 'send_invitation_email', return_value=True):
            response = views.bulk_update_cv_records(request)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def listed(self):
        request = APIRequestFactory().get('/x')
        force_authenticate(request, user=self.rae)
        return {row['file_name']: row for row in views.list_cv_records(request).data['data']}


class UploadedCVsTests(ScreeningTestCase):

    def test_nobody_is_emailed_and_no_interview_is_made(self):
        reply = self.upload(['INTERVIEW', 'HOLD', 'REJECT'], names=('Cara_Khan', 'Bilal_Ahmed', 'Sana_Malik'))
        self.assertEqual(mail.outbox, [])
        self.assertEqual(Interview.objects.count(), 0)
        self.assertEqual((reply['ready_to_invite'], reply['invitations_sent']), (1, 0))

    def test_the_decision_is_still_recorded_and_the_reply_says_who_is_ready(self):
        reply = self.upload(['INTERVIEW', 'HOLD'], names=('Cara_Khan', 'Bilal_Ahmed'))
        by_file = {row['file_name']: row for row in reply['results']}
        self.assertEqual((by_file['Cara_Khan.pdf']['ready_to_invite'], by_file['Bilal_Ahmed.pdf']['ready_to_invite']),
                         (True, False))
        self.assertEqual(CVRecord.objects.get(file_name='Cara_Khan.pdf').qualification_decision, 'INTERVIEW')
        self.assertEqual(CVRecord.objects.get(file_name='Bilal_Ahmed.pdf').qualification_decision, 'HOLD')

    def test_the_candidates_list_shows_approved_but_not_invited(self):
        self.upload(['INTERVIEW', 'HOLD'], names=('Cara_Khan', 'Bilal_Ahmed'))
        rows = self.listed()
        self.assertEqual((rows['Cara_Khan.pdf']['qualification_decision'], rows['Cara_Khan.pdf']['invited']),
                         ('INTERVIEW', False))
        self.assertFalse(rows['Bilal_Ahmed.pdf']['invited'])

    def test_a_person_confirming_the_interview_decision_is_what_invites(self):
        self.upload(['INTERVIEW'])
        cara = CVRecord.objects.get(file_name='Cara_Khan.pdf')
        reply = self.decide([cara])
        self.assertEqual(reply['emails_sent'], 1)
        [interview] = Interview.objects.all()
        self.assertEqual((interview.candidate_email, interview.cv_record_id), ('cara.khan@mail.test', cara.id))
        self.assertTrue(self.listed()['Cara_Khan.pdf']['invited'])

    def test_the_same_person_uploaded_twice_is_invited_once(self):
        self.upload(['INTERVIEW'])
        first = CVRecord.objects.get(file_name='Cara_Khan.pdf')
        self.assertEqual(self.decide([first])['emails_sent'], 1)

        reply = self.upload(['INTERVIEW'])                           # the same CV again: a second record
        self.assertEqual(reply['ready_to_invite'], 0)
        second = CVRecord.objects.exclude(pk=first.pk).get()
        again = self.decide([second])
        self.assertEqual(again['emails_sent'], 0)
        self.assertEqual(again['skip_reasons'], {'already_has_interview': 1})
        self.assertEqual(Interview.objects.count(), 1)
        self.assertTrue(all(row['invited'] for row in views.list_cv_records(self.as_rae()).data['data']))

    def as_rae(self):
        request = APIRequestFactory().get('/x')
        force_authenticate(request, user=self.rae)
        return request

    def test_a_cancelled_interview_does_not_stop_a_new_invitation(self):
        self.upload(['INTERVIEW'])
        first = CVRecord.objects.get(file_name='Cara_Khan.pdf')
        self.decide([first])
        Interview.objects.update(status='CANCELLED')
        self.upload(['INTERVIEW'])
        second = CVRecord.objects.exclude(pk=first.pk).get()
        self.assertTrue(views._ready_to_invite(second))

    def test_the_same_address_for_a_different_job_is_a_different_matter(self):
        self.upload(['INTERVIEW'])
        self.decide([CVRecord.objects.get()])
        other_job = JobDescription.objects.create(title='Writer', description='Write things well ' * 3,
                                                  company=self.company, company_user=self.rae)
        elsewhere = CVRecord.objects.create(
            file_name='Cara_Khan.pdf', job_description=other_job, qualification_decision='INTERVIEW',
            parsed_json=json.dumps({'name': 'Cara Khan', 'email': 'cara.khan@mail.test'}))
        self.assertTrue(views._ready_to_invite(elsewhere))

    def test_someone_with_no_address_or_not_approved_is_not_ready(self):
        no_address = CVRecord.objects.create(file_name='x.pdf', job_description=self.job,
                                             qualification_decision='INTERVIEW', parsed_json=json.dumps({'name': 'X'}))
        on_hold = CVRecord.objects.create(file_name='y.pdf', job_description=self.job,
                                          qualification_decision='HOLD',
                                          parsed_json=json.dumps({'name': 'Y', 'email': 'y@mail.test'}))
        self.assertFalse(views._ready_to_invite(no_address))
        self.assertFalse(views._ready_to_invite(on_hold))
        self.assertFalse(views._ready_to_invite(None))


class PublicApplicantsTests(ScreeningTestCase):

    def test_processing_applicants_emails_nobody(self):
        self.applicant('Cara', 'Khan')
        self.applicant('Bilal', 'Ahmed')
        reply = self.process_applicants(['INTERVIEW', 'REJECT'])
        self.assertEqual(mail.outbox, [])
        self.assertEqual(Interview.objects.count(), 0)
        self.assertEqual((reply['processed'], reply['ready_to_invite'], reply['invitations_sent']), (2, 1, 0))
        self.assertIn('1 approved for interview and not invited yet', reply['message'])
        self.assertEqual([r['interview_scheduled'] for r in reply['results']], [False, False])

    def test_nothing_about_inviting_is_said_when_nobody_was_approved(self):
        self.applicant('Cara', 'Khan')
        reply = self.process_applicants(['HOLD'])
        self.assertEqual(reply['ready_to_invite'], 0)
        self.assertNotIn('not invited', reply['message'])

    def test_the_person_inviting_reaches_the_address_the_applicant_typed(self):
        self.applicant('Cara', 'Khan')
        self.process_applicants(['INTERVIEW'])
        self.decide(list(CVRecord.objects.all()))
        self.assertEqual(Interview.objects.get().candidate_email, 'cara.khan@mail.test')     # not the one in the CV

"""Candidates are emailed what they should hear, once, and only when there is something to act on.

CO-111  rejecting someone already rejected and told sent the rejection email again
CO-113  cancelling a booked interview told the interviewers but never the candidate
CO-119  saving a decision with feedback emailed the candidate at once, every time, unasked
CO-228  invitations went out when the job had no interview slot left to book
CO-101  a hand-uploaded CV was tied to another applicant who used the same file name
CO-226  interviews of public applicants were named after the description's first line, not the job
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
from recruitment_agent.interview_time import bookable_slots
from recruitment_agent.models import (CVRecord, Interview, JobApplication, JobDescription,
                                      RecruiterInterviewSettings)

from .test_invitations_go_by_themselves import screening

MEDIA = tempfile.mkdtemp(prefix='recruitment-emails-')


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


@override_settings(MEDIA_ROOT=MEDIA)
class CandidateEmailTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        CompanyModulePurchase.objects.create(company=self.company, module_name='recruitment_agent',
                                             status='active', is_complimentary=True)
        self.rae = CompanyUser.objects.create(company=self.company, email='rae@acme.test', full_name='Rae Recruiter',
                                              role='admin', password_hash='x', is_active=True)
        self.job = JobDescription.objects.create(title='Designer', description='We need a designer.\nDesign things.',
                                                 company=self.company, company_user=self.rae,
                                                 keywords_json=json.dumps({'keywords': ['design']}))
        self.day = timezone.now().date() + timedelta(days=10)
        self.settings_row = RecruiterInterviewSettings.objects.create(
            company_user=self.rae, job=self.job, timezone_name='Asia/Karachi', start_time=time(9, 0),
            end_time=time(17, 0), interview_time_gap=45, schedule_from_date=self.day, schedule_to_date=self.day,
            time_slots_json=[{'date': str(self.day), 'time': '10:00', 'datetime': f'{self.day}T10:00',
                              'available': True}])

    def call(self, view, data, method='post', **kwargs):
        request = getattr(APIRequestFactory(), method)('/x', data, format='json')
        force_authenticate(request, user=self.rae)
        response = view(request, **kwargs)
        return response.status_code, response.data

    def cv(self, name='Cara Khan', email='cara@mail.test', decision='REJECT', **more):
        return CVRecord.objects.create(file_name=f'{name}.pdf', job_description=self.job,
                                       qualification_decision=decision,
                                       parsed_json=json.dumps({'name': name, 'email': email}), **more)

    # ---- CO-111 ----------------------------------------------------------------------------------

    def test_a_rejection_goes_once(self):
        record = self.cv(decision='REJECT')       # the AI's Reject: never told
        code, body = self.call(views.bulk_update_cv_records, {'cv_record_ids': [record.id],
                                                              'qualification_decision': 'REJECT'})
        self.assertEqual((code, body['reject_emails_sent']), (200, 1))
        self.assertEqual(len(mail.outbox), 1)
        code, body = self.call(views.bulk_update_cv_records, {'cv_record_ids': [record.id],
                                                              'qualification_decision': 'REJECT'})
        self.assertEqual((body['reject_emails_sent'], body['already_told']), (0, 1))
        self.assertIn('already been sent the rejection email', body['message'])
        self.assertEqual(len(mail.outbox), 1)

    def test_rejected_again_after_being_reconsidered_is_told_again(self):
        record = self.cv(decision='REJECT', rejection_emailed_at=timezone.now())
        self.call(views.bulk_update_cv_records, {'cv_record_ids': [record.id], 'qualification_decision': 'HOLD'})
        record.refresh_from_db()
        self.assertIsNone(record.rejection_emailed_at)
        self.call(views.bulk_update_cv_records, {'cv_record_ids': [record.id], 'qualification_decision': 'REJECT'})
        self.assertEqual(len(mail.outbox), 1)

    # ---- CO-113 and CO-119 ------------------------------------------------------------------------

    def interview(self, status='SCHEDULED', outcome=None):
        return Interview.objects.create(
            candidate_name='Cara Khan', candidate_email='cara@mail.test', job_role='Designer',
            cv_record=self.cv(decision='INTERVIEW'), company_user=self.rae, status=status, outcome=outcome,
            scheduled_datetime=timezone.now() + timedelta(days=3))

    def test_cancelling_a_booked_interview_emails_the_candidate(self):
        interview = self.interview()
        code, body = self.call(views.update_interview, {'status': 'CANCELLED'}, 'patch', interview_id=interview.id)
        self.assertEqual(code, 200)
        self.assertEqual(body['data']['candidate_emailed'], 'cancelled')
        self.assertIn('emailed that it is cancelled', body['message'])
        self.assertEqual([m.to for m in mail.outbox], [['cara@mail.test']])
        self.assertIn('Cancelled', mail.outbox[0].subject)

    def test_withdrawing_an_unbooked_invitation_emails_nobody(self):
        interview = self.interview(status='PENDING')
        self.call(views.update_interview, {'status': 'CANCELLED'}, 'patch', interview_id=interview.id)
        self.assertEqual(mail.outbox, [])

    def test_the_decision_email_goes_only_when_asked_and_when_it_changes(self):
        interview = self.interview(status='COMPLETED')
        code, body = self.call(views.update_interview, {'outcome': 'HIRED', 'notify_candidate': False}, 'patch',
                               interview_id=interview.id)
        self.assertEqual((code, body['data']['candidate_emailed']), (200, None))
        self.assertEqual(mail.outbox, [])
        _, body = self.call(views.update_interview, {'outcome': 'REJECTED', 'notify_candidate': True}, 'patch',
                            interview_id=interview.id)
        self.assertEqual(body['data']['candidate_emailed'], 'outcome')
        self.assertEqual(len(mail.outbox), 1)
        _, body = self.call(views.update_interview, {'outcome': 'REJECTED', 'notify_candidate': True}, 'patch',
                            interview_id=interview.id)
        self.assertIsNone(body['data']['candidate_emailed'])            # the same decision again
        self.assertEqual(len(mail.outbox), 1)

    # ---- CO-228 ------------------------------------------------------------------------------------

    def test_slots_that_count(self):
        self.assertEqual(bookable_slots(self.job), 1)
        past = timezone.now().date() - timedelta(days=1)
        self.settings_row.time_slots_json = [
            {'datetime': f'{past}T10:00', 'available': True},                       # gone
            {'datetime': f'{self.day}T11:00', 'available': False},                  # switched off
            {'datetime': f'{self.day}T12:00', 'available': True, 'scheduled': True},
        ]
        self.settings_row.save()
        self.assertEqual(bookable_slots(self.job), 0)

    def upload(self, decisions, names):
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

    def test_no_invitation_when_no_slot_is_free(self):
        self.settings_row.time_slots_json = [{'datetime': f'{timezone.now().date() - timedelta(days=1)}T10:00',
                                              'available': True}]
        self.settings_row.save()
        reply, invite = self.upload(['INTERVIEW'], ['Cara_Khan'])
        invite.assert_not_called()
        self.assertIn('No free interview slots for "Designer"', reply['notice'])
        self.assertEqual(CVRecord.objects.get().qualification_decision, 'INTERVIEW')    # the decision is kept

    def test_the_same_person_is_not_invited_twice(self):
        Interview.objects.create(candidate_name='Cara Khan', candidate_email='cara.khan@mail.test',
                                 job_role='Designer', cv_record=self.cv(decision='INTERVIEW'), company_user=self.rae,
                                 status='PENDING')
        reply, invite = self.upload(['INTERVIEW'], ['Cara_Khan'])
        invite.assert_not_called()
        self.assertIn('Already invited', reply['results'][0]['interview_error'])

    def test_bulk_interview_says_when_no_slot_is_free(self):
        self.settings_row.time_slots_json = []
        self.settings_row.save()
        record = self.cv(decision='HOLD')
        code, body = self.call(views.bulk_update_cv_records, {'cv_record_ids': [record.id],
                                                              'qualification_decision': 'INTERVIEW'})
        self.assertEqual((code, body['emails_sent']), (200, 0))
        self.assertIn('no free interview slots', body['message'])
        self.assertFalse(Interview.objects.exists())

    # ---- CO-101 and CO-226 -------------------------------------------------------------------------

    def test_a_cv_is_not_tied_to_another_applicant_by_file_name(self):
        JobApplication.objects.create(job=self.job, first_name='Adil', last_name='Shah', email='adil@mail.test',
                                      cv_file_name='Cara_Khan.pdf',
                                      cv_file=SimpleUploadedFile('Cara_Khan.pdf', b'%PDF-1.4 text'))
        reply, invite = self.upload(['INTERVIEW'], ['Cara_Khan'])
        self.assertIsNone(CVRecord.objects.get().job_application_id)
        self.assertEqual(invite.call_args.kwargs['candidate_email'], 'cara.khan@mail.test')

    def test_a_public_applicants_interview_is_named_after_the_job(self):
        JobApplication.objects.create(job=self.job, first_name='Cara', last_name='Khan', email='cara.khan@mail.test',
                                      cv_file_name='Cara.pdf', cv_file=SimpleUploadedFile('Cara.pdf', b'%PDF-1.4 x'))
        agents, invite = screening(['INTERVIEW'], [{'name': 'Cara Khan', 'email': 'cara.khan@mail.test'}])
        request = APIRequestFactory().post('/x', {}, format='json')
        force_authenticate(request, user=self.rae)
        with mock.patch.object(company_jobs, '_make_agents', return_value=agents), \
                mock.patch('threading.Thread'), mock.patch('time.sleep'):
            company_jobs.process_job_applicants(request, jobId=self.job.id)
        self.assertEqual(invite.call_args.kwargs['job_role'], 'Designer')

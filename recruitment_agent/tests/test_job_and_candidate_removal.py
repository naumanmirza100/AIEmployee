"""Closing or deleting a job, and deleting a candidate, do what they say.

CO-118  a deleted or closed job's invitations stayed live: candidates were still chased and could still book
CO-183  deleting a job removed its applications and hid its candidates; no candidate could be deleted at all
"""
import json
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import recruitment_agent as views
from core.models import Company, CompanyModulePurchase, CompanyUser
from recruitment_agent import tasks
from recruitment_agent.models import CVRecord, Interview, JobApplication, JobDescription
from recruitment_agent.views import _booking_is_closed

from .test_uploads import MEDIA


@override_settings(MEDIA_ROOT=MEDIA)
class RemovalTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        CompanyModulePurchase.objects.create(company=self.company, module_name='recruitment_agent',
                                             status='active', is_complimentary=True)
        self.rae = self.login('rae', 'Rae Recruiter', 'admin')
        self.job = JobDescription.objects.create(title='Designer', description='Design.', company=self.company,
                                                 company_user=self.rae)
        self.app = JobApplication.objects.create(job=self.job, first_name='Cara', last_name='Khan', phone='0300 1',
                                                 email='cara@mail.test', cv_file_name='Cara.pdf',
                                                 cv_file=SimpleUploadedFile('Cara.pdf', b'%PDF-1.4 text'))
        self.cv = CVRecord.objects.create(file_name='Cara.pdf', job_description=self.job, job_application=self.app,
                                          qualification_decision='INTERVIEW',
                                          parsed_json=json.dumps({'name': 'Cara Khan', 'email': 'cara@mail.test'}))

    def login(self, name, full_name, role):
        return CompanyUser.objects.create(company=self.company, email=f'{name}@acme.test', full_name=full_name,
                                          role=role, password_hash='x', is_active=True)

    def call(self, view, actor, method='delete', **kwargs):
        request = getattr(APIRequestFactory(), method)('/x')
        force_authenticate(request, user=actor)
        return view(request, **kwargs)

    def interview(self, status='SCHEDULED', **more):
        return Interview.objects.create(candidate_name='Cara Khan', candidate_email='cara@mail.test',
                                        job_role='Designer', available_slots_json='[]', cv_record=self.cv,
                                        company_user=self.rae, status=status, **more)

    def test_a_job_with_people_is_closed_not_deleted(self):
        response = self.call(views.delete_job_description, self.rae, job_description_id=self.job.id)
        self.assertEqual(response.status_code, 409)
        self.assertIn('Close it instead', response.data['message'])
        self.assertTrue(JobApplication.objects.filter(pk=self.app.pk).exists())
        empty = JobDescription.objects.create(title='Writer', description='Write.', company=self.company,
                                              company_user=self.rae)
        response = self.call(views.delete_job_description, self.rae, job_description_id=empty.id)
        self.assertEqual(response.status_code, 200)

    def test_a_closed_job_stops_chasing_but_keeps_booked_interviews(self):
        waiting = self.interview(status='PENDING', invitation_sent_at=timezone.now() - timedelta(days=5))
        JobDescription.objects.filter(pk=self.job.pk).update(is_active=False)
        agent = mock.Mock()
        with mock.patch.object(tasks, 'get_interview_agent', return_value=agent):
            tasks.check_and_send_followup_emails()
        agent.send_followup_reminder.assert_not_called()
        self.assertFalse(_booking_is_closed(waiting))           # closing stops chasing, not booking

    def test_a_deleted_jobs_invitation_is_closed(self):
        waiting = self.interview(status='PENDING')
        CVRecord.objects.filter(pk=self.cv.pk).update(job_description=None)
        waiting.refresh_from_db()
        self.assertTrue(_booking_is_closed(waiting))

    def test_deleting_a_candidate_removes_their_data_and_tells_them(self):
        self.interview(scheduled_datetime=timezone.now() + timedelta(days=2))
        response = self.call(views.delete_cv_record, self.rae, record_id=self.cv.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('told their booked interview is cancelled', response.data['message'])
        self.assertFalse(CVRecord.objects.exists())
        self.assertFalse(Interview.objects.exists())
        self.assertFalse(JobApplication.objects.exists())
        self.assertEqual([m.to for m in mail.outbox], [['cara@mail.test']])

    def test_only_the_owner_an_admin_or_the_job_owner_may_delete_a_candidate(self):
        member = self.login('mo', 'Mo Member', 'company_user')
        response = self.call(views.delete_cv_record, member, record_id=self.cv.id)
        self.assertEqual(response.status_code, 403)
        self.assertIn('Rae Recruiter', response.data['message'])
        self.assertTrue(CVRecord.objects.exists())

"""Recruitment is the company's, not each login's.

Each dashboard login used to see only the jobs, candidates and interviews it
had created: two recruiters in one company couldn't see each other's work, and
a leaver's pipeline had nobody who could open it. Now the whole company shares
them, and a job keeps using its owner's settings whoever works on it.
"""
from datetime import date, timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import company_jobs, recruitment_agent as views
from core.models import Company, CompanyModulePurchase, CompanyUser
from recruitment_agent import interview_time, sharing
from recruitment_agent.agents.interview_scheduling import InterviewSchedulingAgent
from recruitment_agent.agents.recruitment_qa_agent import RecruitmentQAAgent
from recruitment_agent.log_service import LogService
from recruitment_agent.models import (CVRecord, Interview, JobDescription, RecruiterEmailSettings,
                                      RecruiterInterviewSettings, RecruiterQualificationSettings)


def quietly():
    """No background follow-up checks, no real emails."""
    return mock.patch('threading.Thread')


class SharingTestCase(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        # A candidate can only book with a company that has Recruitment.
        CompanyModulePurchase.objects.create(company=self.company, module_name='recruitment_agent',
                                             status='active', is_complimentary=True)
        self.ann = self.login(self.company, 'ann@test.local', 'Ann Owner', 'admin')
        self.ben = self.login(self.company, 'ben@test.local', 'Ben Colleague', 'company_user')
        rival = Company.objects.create(name='Rival', email='rival@test.local')
        self.rita = self.login(rival, 'rita@test.local', 'Rita Rival', 'admin')

        self.job = JobDescription.objects.create(title='Designer', description='Design things ' * 3,
                                                 company=self.company, company_user=self.ann)
        self.cv = CVRecord.objects.create(file_name='cara.pdf', job_description=self.job,
                                          parsed_json='{"name": "Cara", "email": "cara@mail.test"}')
        with quietly():
            self.interview = Interview.objects.create(
                candidate_name='Cara', candidate_email='cara@mail.test', job_role='Designer',
                available_slots_json='[]', company_user=self.ann, cv_record=self.cv, status='PENDING')

    def login(self, company, email, name, role):
        return CompanyUser.objects.create(company=company, email=email, full_name=name, role=role,
                                          password_hash='x', is_active=True)

    def call(self, view, actor, method='get', data=None, **kwargs):
        factory = APIRequestFactory()
        if method == 'get':
            request = factory.get('/', data or {})
        else:
            request = getattr(factory, method)('/', data or {}, format='json')
        force_authenticate(request, user=actor)
        with quietly(), mock.patch.object(InterviewSchedulingAgent, 'send_invitation_email', return_value=True):
            response = view(request, **kwargs)
        if hasattr(response, 'render'):
            response.render()
        return response.status_code, getattr(response, 'data', None)


class CompanyWideTests(SharingTestCase):

    def test_colleagues_see_each_others_jobs_candidates_and_interviews(self):
        code, body = self.call(views.list_job_descriptions, self.ben)
        self.assertEqual(code, 200)
        [job] = body['data']
        self.assertEqual((job['id'], job['owner']['name'], job['owner']['is_you']),
                         (self.job.id, 'Ann Owner', False))
        self.assertTrue(self.call(views.list_job_descriptions, self.ann)[1]['data'][0]['owner']['is_you'])
        self.assertEqual([c['id'] for c in self.call(views.list_cv_records, self.ben)[1]['data']], [self.cv.id])
        [iv] = self.call(views.list_interviews, self.ben)[1]['data']
        self.assertEqual((iv['id'], iv['recruiter']['name']), (self.interview.id, 'Ann Owner'))
        self.assertEqual([j['id'] for j in self.call(company_jobs.list_company_jobs, self.ben)[1]['data']],
                         [self.job.id])

    def test_and_can_work_on_them(self):
        code, _ = self.call(views.update_job_description, self.ben, 'patch', {'title': 'Senior Designer'},
                            job_description_id=self.job.id)
        self.assertEqual(code, 200)
        self.job.refresh_from_db()
        self.assertEqual(self.job.title, 'Senior Designer')
        self.assertEqual(self.call(views.get_cv_record_detail, self.ben, record_id=self.cv.id)[0], 200)
        code, _ = self.call(views.submit_interview_feedback, self.ben, 'post', {'feedback_rating': 4},
                            interview_id=self.interview.id)
        self.assertEqual(code, 200)
        self.interview.refresh_from_db()
        self.assertEqual(self.interview.feedback_rating, 4)

    def test_other_companies_see_nothing(self):
        self.assertEqual(self.call(views.list_job_descriptions, self.rita)[1]['data'], [])
        self.assertEqual(self.call(views.list_cv_records, self.rita)[1]['data'], [])
        self.assertEqual(self.call(views.list_interviews, self.rita)[1]['data'], [])
        self.assertEqual(self.call(company_jobs.list_company_jobs, self.rita)[1]['data'], [])
        self.assertEqual(self.call(views.update_job_description, self.rita, 'patch', {'title': 'Mine'},
                                   job_description_id=self.job.id)[0], 404)
        self.assertEqual(self.call(views.delete_job_description, self.rita, 'delete',
                                   job_description_id=self.job.id)[0], 404)
        self.assertEqual(self.call(views.get_cv_record_detail, self.rita, record_id=self.cv.id)[0], 404)
        self.assertEqual(self.call(views.update_interview, self.rita, 'patch', {'status': 'CANCELLED'},
                                   interview_id=self.interview.id)[0], 404)
        overview = self.call(views.recruitment_analytics, self.rita)[1]['data']['overview']
        self.assertEqual((overview['total_jobs'], overview['total_cvs'], overview['total_interviews']), (0, 0, 0))
        self.job.refresh_from_db()
        self.assertEqual(self.job.title, 'Designer')

    def test_an_older_job_saved_without_its_company_is_still_the_companys(self):
        old = JobDescription.objects.create(title='Old role', description='x' * 30, company=None,
                                            company_user=self.ann)
        ids = [j['id'] for j in self.call(views.list_job_descriptions, self.ben)[1]['data']]
        self.assertIn(old.id, ids)
        self.assertNotIn(old.id, [j['id'] for j in self.call(views.list_job_descriptions, self.rita)[1]['data']])

    def test_analytics_qa_and_graphs_cover_the_whole_company(self):
        overview = self.call(views.recruitment_analytics, self.ben)[1]['data']['overview']
        self.assertEqual((overview['total_jobs'], overview['total_cvs'], overview['total_interviews']), (1, 1, 1))
        data = RecruitmentQAAgent(groq_client=mock.Mock())._get_recruitment_data(self.ben)
        self.assertEqual(([j['title'] for j in data['jobs']], data['jobs'][0]['posted_by']),
                         (['Designer'], 'Ann Owner'))
        self.assertEqual((data['total_cvs'], data['total_interviews']), (1, 1))
        self.assertEqual(data['jobs'][0]['interview_count'], 1)


class SettingsFollowTheJobTests(SharingTestCase):

    def setUp(self):
        super().setUp()
        RecruiterEmailSettings.objects.create(company_user=self.ann, followup_delay_hours=5,
                                              auto_send_followups=False)
        RecruiterEmailSettings.objects.create(company_user=self.ben, followup_delay_hours=7)

    def schedule_as(self, actor):
        code, body = self.call(views.schedule_interview, actor, 'post', {
            'candidate_name': 'Cara', 'candidate_email': 'cara@mail.test', 'job_role': 'Designer',
            'cv_record_id': self.cv.id})
        self.assertEqual(code, 200, body)
        return Interview.objects.get(id=body['data']['interview_id'])

    def test_a_colleague_inviting_uses_the_job_owners_email_settings(self):
        interview = self.schedule_as(self.ben)
        self.assertEqual(interview.company_user, self.ben)              # Ben runs it
        self.assertEqual(interview.followup_delay_hours, 5)             # on Ann's timings
        self.assertFalse(interview.sends_followups())                   # and Ann's switch

    def test_a_job_whose_owner_has_left_uses_whoever_is_acting(self):
        self.ann.is_active = False
        self.ann.save()
        interview = self.schedule_as(self.ben)
        self.assertEqual(interview.followup_delay_hours, 7)
        self.assertTrue(interview.sends_followups())

    def test_bulk_invitations_use_the_job_owners_timings(self):
        self.interview.delete()
        code, body = self.call(views.bulk_update_cv_records, self.ben, 'post',
                               {'cv_record_ids': [self.cv.id], 'qualification_decision': 'INTERVIEW'})
        self.assertEqual((code, body['emails_sent']), (200, 1), body)
        interview = Interview.objects.get(cv_record=self.cv)
        self.assertEqual((interview.company_user, interview.followup_delay_hours), (self.ben, 5))

    def test_screening_uses_the_job_owners_thresholds(self):
        RecruiterQualificationSettings.objects.update_or_create(
            company_user=self.ann, defaults={'use_custom_thresholds': True, 'interview_threshold': 80,
                                             'hold_threshold': 50})
        self.assertEqual(sharing.thresholds(sharing.owner(self.job, self.ben)), (80, 50))
        self.assertEqual(sharing.thresholds(sharing.owner(None, self.ben)), (None, None))   # Ben's: defaults


class SharedSlotsTests(SharingTestCase):

    def setUp(self):
        super().setUp()
        start = date.today() + timedelta(days=7)
        self.slots = RecruiterInterviewSettings.objects.create(
            company_user=self.ann, job=self.job, timezone_name='UTC', schedule_from_date=start,
            schedule_to_date=start + timedelta(days=2),
            time_slots_json=[{'datetime': f'{start.isoformat()}T10:00', 'available': True}])

    def test_a_colleague_sees_and_edits_the_jobs_own_slots(self):
        code, body = self.call(views.interview_settings, self.ben, data={'job_id': self.job.id})
        self.assertEqual((code, len(body['data']['time_slots_json'])), (200, 1))
        code, body = self.call(views.interview_settings, self.ben, 'post',
                               {'job_id': self.job.id, 'interview_time_gap': 45})
        self.assertEqual(code, 200, body)
        self.assertEqual(RecruiterInterviewSettings.objects.filter(job=self.job).count(), 1)   # not a copy
        self.slots.refresh_from_db()
        self.assertEqual(self.slots.interview_time_gap, 45)

    def test_a_colleagues_interview_uses_the_jobs_slots(self):
        RecruiterInterviewSettings.objects.create(company_user=self.ben, job=None, timezone_name='Asia/Karachi')
        with quietly():
            theirs = Interview.objects.create(candidate_name='Dev', candidate_email='dev@mail.test',
                                              job_role='Designer', available_slots_json='[]',
                                              company_user=self.ben, cv_record=self.cv)
        self.assertEqual(interview_time.settings_for(theirs), self.slots)

    def test_a_time_one_colleague_booked_is_taken_for_the_other(self):
        when = timezone.now().replace(microsecond=0) + timedelta(days=8)
        with quietly():
            Interview.objects.filter(pk=self.interview.pk).update(status='SCHEDULED', scheduled_datetime=when,
                                                                  timezone_name='UTC')
            cv2 = CVRecord.objects.create(file_name='dev.pdf', parsed_json='{}', job_description=self.job)
            theirs = Interview.objects.create(candidate_name='Dev', candidate_email='dev@mail.test',
                                              job_role='Designer', available_slots_json='[]',
                                              company_user=self.ben, cv_record=cv2, timezone_name='UTC')
        result = InterviewSchedulingAgent(log_service=LogService()).reschedule_interview(theirs.id, when.isoformat())
        self.assertFalse(result['success'])
        self.assertIn('already selected by another candidate', result['error'])

    def booked_by_ann_and_bens_candidate(self):
        """Ann's candidate holds the first slot; Ben has invited another for the same job."""
        from datetime import datetime, time, timezone as dt_timezone
        start = self.slots.schedule_from_date
        self.slot = f'{start.isoformat()}T10:00'
        with quietly():
            Interview.objects.filter(pk=self.interview.pk).update(
                status='SCHEDULED', timezone_name='UTC',
                scheduled_datetime=datetime.combine(start, time(10, 0), tzinfo=dt_timezone.utc))
            cv2 = CVRecord.objects.create(file_name='dev.pdf', parsed_json='{}', job_description=self.job)
            return Interview.objects.create(candidate_name='Dev', candidate_email='dev@mail.test',
                                            job_role='Designer', available_slots_json='[]',
                                            company_user=self.ben, cv_record=cv2, confirmation_token='tok-dev')

    def test_the_candidate_page_shows_a_colleagues_booking_as_taken(self):
        import json
        from django.test import RequestFactory
        from recruitment_agent.views import get_available_slots_for_interview
        self.booked_by_ann_and_bens_candidate()
        data = json.loads(get_available_slots_for_interview(RequestFactory().get('/'), 'tok-dev').content)
        [slot] = [s for s in data['time_slots'] if s['datetime'] == self.slot]
        self.assertTrue(slot['taken'])

    def test_and_the_candidate_cannot_book_it(self):
        theirs = self.booked_by_ann_and_bens_candidate()
        with quietly():
            result = InterviewSchedulingAgent(log_service=LogService()).confirm_slot(theirs.id, self.slot)
        self.assertFalse(result['success'])
        self.assertIn('already taken by another candidate', result['error'])


class ExportTests(SharingTestCase):

    def export(self, view, actor):
        request = APIRequestFactory().get('/')
        force_authenticate(request, user=actor)
        return view(request).content.decode()

    def test_exports_hold_the_whole_companys_candidates_and_interviews(self):
        self.assertIn('Designer', self.export(views.export_candidates_csv, self.ben))
        self.assertIn('cara@mail.test', self.export(views.export_interviews_csv, self.ben))
        self.assertNotIn('Designer', self.export(views.export_candidates_csv, self.rita))
        self.assertNotIn('cara@mail.test', self.export(views.export_interviews_csv, self.rita))

    def test_a_colleague_sees_a_jobs_applications(self):
        self.assertEqual(self.call(views.list_job_applications, self.ben, job_description_id=self.job.id)[0], 200)
        self.assertEqual(self.call(views.list_job_applications, self.rita, job_description_id=self.job.id)[0], 404)

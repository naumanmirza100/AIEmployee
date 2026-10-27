"""Smaller Recruitment faults.

CO-221  out of tokens part-way, the rest were scored by rules and nothing said so
CO-222  a colleague in another zone switching one slot off moved every slot of the job to their zone
CO-225  clearing a job's location, department or requirements did nothing; every edit re-ran the AI
CO-272  'Onsite Interview' was emailed, and nothing let the recruiter arrange it
"""
import json
from datetime import time, timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import recruitment_agent as views
from core.api_key_service import QuotaExhausted
from core.models import Company, CompanyModulePurchase, CompanyUser
from recruitment_agent.agents.summarization.summarization_agent import SummarizationAgent
from recruitment_agent.models import CVRecord, Interview, JobDescription, RecruiterInterviewSettings


class SmallFixTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        CompanyModulePurchase.objects.create(company=self.company, module_name='recruitment_agent',
                                             status='active', is_complimentary=True)
        self.rae = CompanyUser.objects.create(company=self.company, email='rae@acme.test', full_name='Rae Recruiter',
                                              role='admin', password_hash='x', is_active=True)
        self.job = JobDescription.objects.create(title='Designer', description='Design things.', location='Lahore',
                                                 department='Design', company=self.company, company_user=self.rae)

    def call(self, view, data, method='post', **kwargs):
        request = getattr(APIRequestFactory(), method)('/x', data, format='json')
        force_authenticate(request, user=self.rae)
        return view(request, **kwargs)

    def test_running_out_of_tokens_stops_scoring(self):
        agent = SummarizationAgent(groq_client=mock.Mock(), log_service=mock.Mock())
        with mock.patch.object(SummarizationAgent, '_llm_summarize', side_effect=QuotaExhausted('used up')):
            with self.assertRaises(QuotaExhausted):
                agent.summarize({'name': 'Cara', 'email': 'cara@mail.test', 'phone': '', 'skills': ['design'],
                                 'experience': [], 'education': [], 'certifications': [], 'summary': ''}, ['design'])

    def test_a_job_edit_can_clear_fields_and_keeps_keywords_when_the_text_is_the_same(self):
        with mock.patch.object(views, '_make_agents') as make:
            response = self.call(views.update_job_description, {
                'title': 'Designer', 'description': 'Design things.', 'location': '', 'department': ''},
                'put', job_description_id=self.job.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.job.refresh_from_db()
        self.assertEqual((self.job.location, self.job.department), (None, None))
        make.assert_not_called()                       # the description did not change

    def test_switching_a_slot_off_keeps_the_jobs_zone(self):
        day = timezone.now().date() + timedelta(days=5)
        RecruiterInterviewSettings.objects.create(
            company_user=self.rae, job=self.job, timezone_name='Asia/Karachi', start_time=time(9, 0),
            end_time=time(17, 0), schedule_from_date=day, schedule_to_date=day,
            time_slots_json=[{'datetime': f'{day}T10:00', 'available': True}])
        self.call(views.interview_settings, {'job_id': self.job.id, 'timezone': 'Europe/London',
                                             'update_availability': True,
                                             'time_slots': [{'datetime': f'{day}T10:00', 'available': False}]})
        self.assertEqual(RecruiterInterviewSettings.objects.get(job=self.job).timezone_name, 'Asia/Karachi')

    def test_an_onsite_decision_can_be_arranged(self):
        day = timezone.now().date() + timedelta(days=5)
        RecruiterInterviewSettings.objects.create(
            company_user=self.rae, job=self.job, timezone_name='UTC', start_time=time(9, 0), end_time=time(17, 0),
            schedule_from_date=day, schedule_to_date=day, time_slots_json=[{'datetime': f'{day}T10:00', 'available': True}])
        cv = CVRecord.objects.create(file_name='Cara.pdf', job_description=self.job, qualification_decision='INTERVIEW')
        first = Interview.objects.create(candidate_name='Cara Khan', candidate_email='cara@mail.test',
                                         job_role='Designer', cv_record=cv, available_slots_json='[]',
                                         company_user=self.rae, status='COMPLETED', outcome='ONSITE_INTERVIEW')
        response = self.call(views.schedule_next_interview, {}, interview_id=first.id)
        self.assertEqual(response.status_code, 200, response.data)
        onsite = Interview.objects.exclude(id=first.id).get()
        self.assertEqual((onsite.interview_type, onsite.status, onsite.cv_record_id), ('ONSITE', 'PENDING', cv.id))
        self.assertTrue(any('cara@mail.test' in m.to for m in mail.outbox))
        again = self.call(views.schedule_next_interview, {}, interview_id=first.id)
        self.assertEqual(again.status_code, 400)
        self.assertIn('already has an onsite interview', again.data['message'])


class JobWithoutKeywordsTests(TestCase):
    """CO-103: a job saved without keywords screened blind for good, and long skills lists were invited."""

    def setUp(self):
        SmallFixTests.setUp(self)
        day = timezone.now().date() + timedelta(days=5)
        RecruiterInterviewSettings.objects.create(
            company_user=self.rae, job=self.job, timezone_name='UTC', start_time=time(9, 0), end_time=time(17, 0),
            schedule_from_date=day, schedule_to_date=day, time_slots_json=[{'datetime': f'{day}T10:00', 'available': True}])

    def applicant(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from recruitment_agent.models import JobApplication
        return JobApplication.objects.create(job=self.job, first_name='Cara', last_name='Khan', phone='0300 1',
                                             email='cara@mail.test', cv_file_name='Cara.pdf',
                                             cv_file=SimpleUploadedFile('Cara.pdf', b'%PDF-1.4 text'))

    def test_keywords_are_worked_out_and_kept(self):
        from recruitment_agent import applicant_screening
        from .test_invitations_go_by_themselves import screening
        agents, invite = screening(['INTERVIEW'], [{'name': 'Cara Khan', 'email': 'cara@mail.test'}])
        applicant_screening.screen(self.job, [self.applicant()], self.rae, agents)
        self.job.refresh_from_db()
        self.assertEqual(json.loads(self.job.keywords_json)['keywords'], ['design'])

    def test_nobody_is_invited_when_there_is_nothing_to_match(self):
        from recruitment_agent import applicant_screening
        from .test_invitations_go_by_themselves import screening
        agents, invite = screening(['INTERVIEW'], [{'name': 'Cara Khan', 'email': 'cara@mail.test'}])
        agents['job_desc_agent'].parse_text.return_value = {'keywords': []}
        [result] = applicant_screening.screen(self.job, [self.applicant()], self.rae, agents)
        invite.assert_not_called()
        self.assertEqual(result['interview_error'], 'No job requirements to match against')
        self.assertEqual(CVRecord.objects.get().qualification_decision, 'INTERVIEW')    # the score is kept


class ExperienceYearsTests(TestCase):
    """CO-182: years of experience far too low for real CVs ('a team of 4 developers' was 4 days)."""

    def years(self, experience):
        from unittest import mock as _mock
        agent = SummarizationAgent(groq_client=_mock.Mock(), log_service=_mock.Mock())
        return agent._estimate_total_experience_years(experience)

    def test_jobs_with_dates_count_from_start_to_end(self):
        self.assertEqual(self.years([
            {'company': 'Systems Ltd', 'role': 'Senior Developer', 'start_date': 'Jan 2019', 'end_date': 'Jan 2023',
             'description': 'Led a team of 4 developers and managed 3 modules of the payments API.'},
            {'company': 'Arbisoft', 'role': 'Developer', 'start_date': 'Jan 2016', 'end_date': 'Jan 2019',
             'description': 'Built a website and a service.'},
        ]), 7.0)

    def test_overlapping_jobs_count_once(self):
        self.assertEqual(self.years([
            {'company': 'A', 'role': 'Developer', 'start_date': '2018-01-01', 'end_date': '2020-01-01'},
            {'company': 'B', 'role': 'Mentor', 'start_date': '2019-01-01', 'end_date': '2020-01-01'},
        ]), 2.0)

    def test_projects_use_the_stated_length_and_nothing_is_guessed_for_a_bare_job(self):
        self.assertEqual(self.years([
            {'company': '', 'role': 'Freelance developer', 'description': 'A shop site, built in 6 months.'},
            {'company': 'Acme', 'role': 'Accountant', 'description': 'Monthly closing.'},
        ]), 0.5)

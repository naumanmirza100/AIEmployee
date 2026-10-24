"""The Recruitment assistant counts the applications people really sent.

Applications from a job's public page are JobApplication rows. The assistant counted
CareerApplication, an older table the apply form no longer writes to, so "how many
applications did this job get?" was answered "0", without the AI being asked.
"""
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from core.models import Company, CompanyUser
from recruitment_agent.agents.recruitment_qa_agent import RecruitmentQAAgent
from recruitment_agent.models import JobApplication, JobDescription


class ApplicationCountTests(TestCase):

    def setUp(self):
        company = Company.objects.create(name='Acme', email='acme@test.local')
        self.hira = CompanyUser.objects.create(company=company, email='hira@test.local', full_name='Hira',
                                               role='admin', password_hash='x', is_active=True)
        self.job = JobDescription.objects.create(title='Flutter Developer', description='Build banking apps',
                                                 company=company, company_user=self.hira, type='Full-time')
        other = JobDescription.objects.create(title='QA Automation Engineer', description='Test things',
                                              company=company, company_user=self.hira, type='Full-time')
        rival = Company.objects.create(name='Rival', email='rival@test.local')
        rival_user = CompanyUser.objects.create(company=rival, email='rob@test.local', full_name='Rob',
                                                role='admin', password_hash='x', is_active=True)
        rival_job = JobDescription.objects.create(title='Flutter Developer', description='Theirs',
                                                  company=rival, company_user=rival_user, type='Full-time')
        for n, (job, status) in enumerate([(self.job, 'pending'), (self.job, 'shortlisted'),
                                           (self.job, 'pending'), (other, 'pending'), (rival_job, 'pending')]):
            JobApplication.objects.create(job=job, first_name=f'Person{n}', last_name='Khan',
                                          email=f'p{n}@mail.example', phone=f'0300{n:07d}', status=status)
        old = JobApplication.objects.filter(job=self.job).order_by('id').first()
        JobApplication.objects.filter(pk=old.pk).update(applied_at=timezone.now() - timedelta(days=10))
        self.agent = RecruitmentQAAgent(groq_client=mock.Mock())   # these answers never reach the AI
        self.data = self.agent._get_recruitment_data(self.hira)

    def answer(self, question):
        return self.agent._get_direct_answer(self.data, question)

    def test_a_job_counts_its_applications(self):
        answer = self.answer('How many applications for the Flutter Developer job?')
        self.assertIn('**3** application(s)', answer)
        self.assertIn('pending: 2', answer)
        self.assertIn('shortlisted: 1', answer)

    def test_this_week_counts_only_the_last_seven_days(self):
        answer = self.answer('How many applications did the Flutter Developer job get this week?')
        self.assertIn('**2** application(s) in the last 7 days', answer)
        self.assertIn('**3** in total', answer)

    def test_the_company_total_and_the_facts_given_to_the_ai(self):
        self.assertIn('**4** application(s) in total', self.answer('How many applications do we have in total?'))
        self.assertIn('JOB_APPLICATIONS_TOTAL: 4', self.agent._build_context(self.data))

    def test_the_applicants_are_listed_by_name(self):
        answer = self.answer('Show the applications for the Flutter Developer job')
        self.assertIn('Person1 Khan', answer)
        self.assertNotIn('No applications', answer)

    def test_this_week_across_jobs_names_each_job_and_its_count(self):
        # "for which jobs" used to match the job list, which gave every job's all-time count.
        answer = self.answer('How many applications did we get this week, and for which jobs?')
        self.assertIn('**3** application(s) and CV(s) came in, for 2 job(s)', answer)
        self.assertIn('**Flutter Developer**: 2', answer)
        self.assertIn('**QA Automation Engineer**: 1', answer)

    def test_the_ai_is_given_today_and_the_weeks_counts(self):
        context = self.agent._build_context(self.data)
        self.assertIn(f'TODAY: {timezone.localdate().isoformat()}', context)
        self.assertIn('CANDIDATES_RECEIVED_LAST_7_DAYS: 3', context)
        self.assertIn('Received in the last 7 days: 2', context)

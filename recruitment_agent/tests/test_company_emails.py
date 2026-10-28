"""Candidate emails and booking pages are in the hiring company's name, and replies reach a person (CO-187).

They were headed 'Pay Per Project', signed 'Recruitment Team', sent from the platform's address with no reply-to,
and told the candidate both to reply and not to reply.
"""
from datetime import timedelta

from django.core import mail
from django.test import Client, TestCase
from django.utils import timezone

from core.models import Company, CompanyModulePurchase, CompanyUser
from recruitment_agent.agents.interview_scheduling import interview_scheduling_agent as scheduling
from recruitment_agent.models import CVRecord, Interview, JobDescription


class CompanyEmailTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Margalla Software', email='hello@margallasoft.test')
        CompanyModulePurchase.objects.create(company=self.company, module_name='recruitment_agent',
                                             status='active', is_complimentary=True)
        self.rae = CompanyUser.objects.create(company=self.company, email='rae@margallasoft.test',
                                              full_name='Rae Recruiter', role='admin', password_hash='x', is_active=True)
        job = JobDescription.objects.create(title='Designer', description='Design.', company=self.company,
                                            company_user=self.rae)
        cv = CVRecord.objects.create(file_name='Cara.pdf', job_description=job, qualification_decision='INTERVIEW')
        self.interview = Interview.objects.create(
            candidate_name='Cara Khan', candidate_email='cara@mail.test', job_role='Designer', cv_record=cv,
            available_slots_json='[]', company_user=self.rae, status='SCHEDULED', confirmation_token='tok-cara',
            scheduled_datetime=timezone.now() + timedelta(days=2), timezone_name='UTC')

    def test_an_email_comes_from_the_company_and_replies_go_to_the_recruiter(self):
        self.assertTrue(scheduling.InterviewSchedulingAgent().send_cancellation_email(self.interview))
        [sent] = mail.outbox
        self.assertIn('Margalla Software via Pay Per Project', sent.from_email)
        self.assertEqual(sent.reply_to, ['rae@margallasoft.test'])
        self.assertIn('Margalla Software hiring team', sent.body)
        self.assertIn('rae@margallasoft.test', sent.body)
        html = sent.alternatives[0][0]
        self.assertIn('Margalla Software', html)
        self.assertNotIn("please don't reply directly", html)

    def test_the_rejection_names_the_company(self):
        job = self.interview.cv_record.job_description
        self.assertTrue(scheduling.InterviewSchedulingAgent().send_rejection_email('Cara Khan', 'cara@mail.test',
                                                                                    'Designer', job=job))
        self.assertEqual(mail.outbox[0].reply_to, ['rae@margallasoft.test'])

    def test_the_booking_page_names_the_company_and_whom_to_write_to(self):
        self.interview.status = 'CANCELLED'
        self.interview.save()
        page = Client().get('/recruitment/interview/select/tok-cara/')
        self.assertContains(page, 'Margalla Software')
        self.assertContains(page, 'Please write to rae@margallasoft.test.')

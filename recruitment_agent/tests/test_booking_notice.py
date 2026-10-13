"""'A candidate has booked' goes to the recruiter who runs the interview.

The email was addressed to the old employee-login recruiter when the interview
had one. Every interview made from the dashboard is created without one, so the
address fell back to a single RECRUITER_EMAIL mailbox set on the server: each
company's candidate name, email, job, time and meeting link went to that one
inbox, and the login who runs the interview never got the email at all.
"""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from core import notification_settings as ns
from core.models import Company, CompanyModulePurchase, CompanyUser
from recruitment_agent.agents.interview_scheduling import InterviewSchedulingAgent
from recruitment_agent.models import Interview

SHARED_MAILBOX = 'everything@platform.example'


@override_settings(RECRUITER_EMAIL=SHARED_MAILBOX)
class BookingNoticeTests(TestCase):

    def setUp(self):
        self.acme, self.rae = self.company_with_recruiter('Acme', 'rae@acme.test', 'Rae Recruiter')
        self.rival, self.rita = self.company_with_recruiter('Rival', 'rita@rival.test', 'Rita Raza')

    def company_with_recruiter(self, name, email, full_name):
        company = Company.objects.create(name=name, email=f'{name.lower()}@test.local')
        CompanyModulePurchase.objects.create(company=company, module_name='recruitment_agent', status='active',
                                             is_complimentary=True)
        return company, CompanyUser.objects.create(company=company, email=email, full_name=full_name, role='admin',
                                                   password_hash='x', is_active=True)

    def booked(self, **who):
        with mock.patch('threading.Thread'):
            return Interview.objects.create(
                candidate_name='Cara Candidate', candidate_email='cara@mail.test', job_role='Designer',
                available_slots_json='[]', status='SCHEDULED', timezone_name='Asia/Karachi',
                scheduled_datetime=timezone.now() + timedelta(days=3), meeting_link='https://meet.example/abc',
                **who)

    def notice(self, interview):
        """Send the confirmation; return {address: message}."""
        mail.outbox.clear()
        with mock.patch('threading.Thread'):
            InterviewSchedulingAgent().send_confirmation_email(interview)
        return {message.to[0]: message for message in mail.outbox}

    def test_the_login_that_runs_the_interview_is_emailed(self):
        sent = self.notice(self.booked(company_user=self.rae))
        self.assertEqual(sorted(sent), ['cara@mail.test', 'rae@acme.test'])
        to_recruiter = sent['rae@acme.test']
        self.assertIn('Interview Scheduled - Cara Candidate', to_recruiter.subject)
        self.assertIn('Rae Recruiter', to_recruiter.body)
        self.assertIn('https://meet.example/abc', to_recruiter.body)

    def test_nothing_goes_to_the_one_mailbox_set_on_the_server(self):
        for interview in (self.booked(company_user=self.rae), self.booked(company_user=self.rita), self.booked()):
            self.assertNotIn(SHARED_MAILBOX, self.notice(interview))

    def test_each_companys_notice_goes_to_its_own_recruiter(self):
        self.assertIn('rita@rival.test', self.notice(self.booked(company_user=self.rita)))
        self.assertNotIn('rae@acme.test', self.notice(self.booked(company_user=self.rita)))

    def test_the_recruiter_can_turn_the_email_off_and_the_candidate_still_gets_theirs(self):
        ns.set_choice(self.rae, 'interviews_booked', email=False)
        self.assertEqual(sorted(self.notice(self.booked(company_user=self.rae))), ['cara@mail.test'])

    def test_an_interview_from_before_dashboard_logins_goes_to_its_old_recruiter(self):
        old = get_user_model().objects.create_user('olddays', email='old@acme.test', password='x',
                                                   first_name='Olive', last_name='Olddays')
        sent = self.notice(self.booked(recruiter=old))
        self.assertEqual(sorted(sent), ['cara@mail.test', 'old@acme.test'])
        self.assertIn('Olive Olddays', sent['old@acme.test'].body)

    def test_a_login_that_has_been_switched_off_is_not_emailed(self):
        self.rae.is_active = False
        self.rae.save()
        self.assertEqual(sorted(self.notice(self.booked(company_user=self.rae))), ['cara@mail.test'])

    def test_an_interview_nobody_runs_emails_the_candidate_only(self):
        self.assertEqual(sorted(self.notice(self.booked())), ['cara@mail.test'])

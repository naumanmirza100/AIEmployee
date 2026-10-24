"""Once a day, a recruiter's bell says what in their pipeline is waiting on them.

Nothing told a recruiter that a candidate had sat on hold for days, that an online interview tomorrow had no meeting
link, or that an interview was over with no outcome recorded.
"""
import json
from datetime import timedelta
from unittest import mock

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.models import Company, CompanyModulePurchase, CompanyUser
from project_manager_agent.models import PMNotification
from recruitment_agent.models import CVRecord, Interview, JobDescription
from recruitment_agent.pipeline_digest import pipeline_items, send_pipeline_digests


class PipelineDigestTests(TestCase):

    def setUp(self):
        # Saving an interview starts a follow-up check on a thread; it has nothing to do with this.
        patcher = mock.patch('recruitment_agent.signals._check_and_send_followup_async')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.now = timezone.now()
        self.acme = self.company('Acme')
        self.ann = self.login(self.acme, 'ann@acme.test', 'Ann Ahmed')
        self.job = JobDescription.objects.create(title='Designer', description='Design things well', company=self.acme,
                                                 company_user=self.ann)

    def company(self, name, active=True):
        company = Company.objects.create(name=name, email=f'{name.lower()}@test.local')
        CompanyModulePurchase.objects.create(company=company, module_name='recruitment_agent',
                                             status='active' if active else 'cancelled', is_complimentary=True)
        return company

    def login(self, company, email, name):
        return CompanyUser.objects.create(company=company, email=email, full_name=name, role='admin',
                                          password_hash='x', is_active=True)

    def cv(self, days_old, decision='HOLD', job=None):
        return CVRecord.objects.create(file_name='cv.pdf', job_description=job or self.job, parsed_json=json.dumps({}),
                                       qualification_decision=decision,
                                       created_at=self.now - timedelta(days=days_old))

    def interview(self, hours_from_now, recruiter=None, **more):
        fields = dict(candidate_name='Sana Malik', candidate_email='sana@mail.test', job_role='Designer',
                      available_slots_json='[]', status='SCHEDULED', interview_type='ONLINE',
                      company_user=recruiter or self.ann, scheduled_datetime=self.now + timedelta(hours=hours_from_now))
        fields.update(more)
        return Interview.objects.create(**fields)

    def bell(self, who=None):
        return list(PMNotification.objects.filter(company_user=who or self.ann, data__kind='recruitment_pipeline_digest'))

    def test_one_item_says_everything_waiting(self):
        self.cv(5)
        self.cv(4)
        self.interview(6)                                   # tomorrow-ish, no link
        self.interview(-30, outcome='')                     # yesterday, no outcome

        self.assertEqual(send_pipeline_digests(self.now), 1)

        [item] = self.bell()
        self.assertEqual(item.title, 'Waiting on you in Recruitment')
        self.assertEqual(item.message, '1 online interview in the next 24 hours with no meeting link · '
                                       '1 interview done with no outcome recorded · '
                                       '2 candidates on hold for over 3 days.')
        self.assertEqual(item.data['link'], '/recruitment/interviews')

    def test_only_once_a_day(self):
        self.cv(5)
        send_pipeline_digests(self.now)
        self.assertEqual(send_pipeline_digests(self.now + timedelta(hours=2)), 0)
        self.assertEqual(len(self.bell()), 1)
        self.assertEqual(send_pipeline_digests(self.now + timedelta(days=1)), 1)

    def test_holds_only_count_while_they_look_forgotten(self):
        self.cv(1)                                          # too new
        self.cv(45)                                         # old enough to be deliberate
        self.cv(5, decision='INTERVIEW')
        interviewed = self.cv(6)
        self.interview(48, cv_record=interviewed, meeting_link='https://meet.test/x')
        self.assertEqual(send_pipeline_digests(self.now), 0)
        self.assertEqual(self.bell(), [])

    def test_interviews_that_need_nothing_are_left_out(self):
        self.interview(5, meeting_link='https://meet.test/abc')
        self.interview(5, interview_type='ONSITE')
        self.interview(5, status='CANCELLED')
        self.interview(30)                                  # more than a day away
        self.interview(-30, outcome='HIRED')
        self.interview(-24 * 20, outcome='')                # too long ago to chase
        self.assertEqual(pipeline_items(self.now), {})

    def test_with_only_holds_it_opens_the_candidates(self):
        self.cv(5)
        send_pipeline_digests(self.now)
        self.assertEqual(self.bell()[0].data['link'], '/recruitment/candidates')

    def test_each_recruiter_hears_only_of_their_own(self):
        bilal = self.login(self.acme, 'bilal@acme.test', 'Bilal Raza')
        self.cv(5)
        self.interview(4, recruiter=bilal)
        send_pipeline_digests(self.now)
        self.assertIn('candidate on hold', self.bell(self.ann)[0].message)
        self.assertNotIn('interview', self.bell(self.ann)[0].message)
        self.assertNotIn('candidate', self.bell(bilal)[0].message)

    def test_a_company_without_recruitment_now_is_not_told(self):
        lapsed = self.company('Lapsed', active=False)
        rita = self.login(lapsed, 'rita@lapsed.test', 'Rita Khan')
        self.interview(4, recruiter=rita)
        send_pipeline_digests(self.now)
        self.assertEqual(self.bell(rita), [])

    def test_working_it_out_takes_three_queries_whatever_the_size(self):
        for n in range(10):
            recruiter = self.login(self.acme, f'r{n}@acme.test', f'Recruiter {n}')
            job = JobDescription.objects.create(title=f'Job {n}', description='x', company=self.acme,
                                                company_user=recruiter)
            self.cv(5, job=job)
            self.interview(4, recruiter=recruiter)
        with CaptureQueriesContext(connection) as queries:
            items = pipeline_items(self.now)
        self.assertEqual(len(items), 10)
        self.assertEqual(len(queries), 3)
